from __future__ import annotations
from typing import List, Optional, Dict, Any, Tuple
from plataforma.core import db
from datetime import datetime, timedelta, timezone
import json
import html
import logging
import mimetypes
import threading
import re
import asyncio
import hashlib
import base64
import secrets
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from urllib import parse as urlparse
from plataforma.core import email as email_sender, jobs_engine, google_chat
from plataforma.core.config import settings as app_settings
from ticketera.backend.services import roles as ticket_roles
from ticketera.backend.services import workflow as ticket_workflow
from ._helpers import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ==========================================================================
# CLASIFICACIÓN AUTOMÁTICA
# ==========================================================================
def clasificar_ticket(titulo: str, descripcion: str) -> str:
    """Clasifica un ticket basado en keywords en título y descripción."""
    texto = f"{titulo} {descripcion}".lower()
    scores = {}
    for cat, keywords in KEYWORDS_CATEGORIAS.items():
        score = sum(1 for kw in keywords if kw in texto)
        if score > 0:
            scores[cat] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)

# ==========================================================================
# AUTO-ASIGNACIÓN
# ==========================================================================
def auto_asignar(categoria: str) -> Optional[str]:
    """
    Asigna al técnico con menor carga en la categoría.
    Round-robin por menor current_load.
    """
    conn = db.get_conn()
    try:
        role_placeholders = ", ".join(["?"] * len(ROLES_TECNICOS))
        row = conn.execute(
            f"""
            SELECT us.username
            FROM user_specialties us
            JOIN users u ON u.username = us.username
            WHERE us.specialty = ?
              AND us.is_available = 1
              AND us.current_load < us.max_load
              AND COALESCE(u.is_active, 1) = 1
              AND u.role IN ({role_placeholders})
            ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
            LIMIT 1
            """,
            (categoria, *ROLES_TECNICOS),
        ).fetchone()

        if row:
            username = row["username"]
            # Incrementar carga
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (db.now_utc_iso(), username, categoria))
            conn.commit()
            return username

        logger.debug(f"auto_asignar failed for '{categoria}', trying fallback")

        # Fallback: si no hay técnico exacto en esa categoría, asignar al técnico
        # disponible con menor carga (solo roles técnicos activos).
        row = conn.execute(
            f"""
            SELECT us.username, us.specialty
            FROM user_specialties us
            JOIN users u ON u.username = us.username
            WHERE us.is_available = 1
              AND us.current_load < us.max_load
              AND COALESCE(u.is_active, 1) = 1
              AND u.role IN ({role_placeholders})
            ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
            LIMIT 1
            """,
            ROLES_TECNICOS,
        ).fetchone()

        if row:
            username = row["username"]
            specialty = row["specialty"]
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (db.now_utc_iso(), username, specialty))
            conn.commit()
            return username

        # Fallback final (modo solo-roles):
        # seleccionar técnico activo por menor carga real de tickets abiertos/en_progreso.
        user_rows = conn.execute(
            "SELECT username, role, secondary_roles FROM users WHERE COALESCE(is_active, 1) = 1 ORDER BY username ASC"
        ).fetchall()
        if user_rows:
            active_counts_rows = conn.execute(
                """
                SELECT LOWER(asignado_a) AS username, COUNT(*) AS active_count
                FROM tickets
                WHERE COALESCE(asignado_a, '') <> ''
                  AND estado IN ('abierto', 'en_progreso')
                GROUP BY LOWER(asignado_a)
                """
            ).fetchall()
            active_map = {
                _normalize_username(r.get("username")): int(r.get("active_count") or 0)
                for r in active_counts_rows
                if _normalize_username(r.get("username"))
            }

            candidates: List[Tuple[int, str]] = []
            for user_row in user_rows:
                username = _normalize_username(user_row.get("username"))
                if not username:
                    continue
                roles = []
                primary_role = _normalize_role(user_row.get("role"))
                if primary_role:
                    roles.append(primary_role)
                try:
                    parsed_secondary = json.loads(user_row.get("secondary_roles") or "[]")
                except Exception:
                    parsed_secondary = []
                roles.extend(_normalize_roles(parsed_secondary))
                normalized_roles = _normalize_roles(roles)
                if not any(role in ROLES_TECNICOS_SET for role in normalized_roles):
                    continue
                candidates.append((int(active_map.get(username, 0)), username))

            if candidates:
                candidates.sort(key=lambda item: (item[0], item[1]))
                return candidates[0][1]

        return None
    finally:
        conn.close()

def incrementar_carga(username: str, specialty: Optional[str] = None) -> None:
    """Incrementa la carga del técnico al asignar un ticket. Si se especifica especialidad, solo incrementa esa."""
    if not username:
        return
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Intentar incrementar en la especialidad específica
        if specialty:
            cursor = conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, specialty))
            
            if cursor.rowcount > 0:
                conn.commit()
                return

        # Fallback 1: si existe una especialidad 'general', usarla.
        cursor = conn.execute("""
            UPDATE user_specialties
            SET current_load = current_load + 1, updated_at = ?
            WHERE username = ? AND specialty = 'general'
        """, (now, username))

        if cursor.rowcount > 0:
            conn.commit()
            return

        # Fallback 2: elegir la especialidad más liviana del usuario.
        row = conn.execute("""
            SELECT specialty
            FROM user_specialties
            WHERE username = ?
            ORDER BY current_load ASC, updated_at ASC NULLS FIRST, specialty ASC
            LIMIT 1
        """, (username,)).fetchone()
        if row:
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, row["specialty"]))
        conn.commit()
    finally:
        conn.close()

def decrementar_carga(username: str, specialty: Optional[str] = None) -> None:
    """Decrementa la carga del técnico. Si se especifica especialidad, intenta decretar esa."""
    if not username:
        return
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Intentar decrementar en la especialidad específica
        if specialty:
            cursor = conn.execute("""
                UPDATE user_specialties
                SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, specialty))
            
            if cursor.rowcount > 0:
                conn.commit()
                return

        # Fallback 1: decrementar en 'general' si existe.
        cursor = conn.execute("""
            UPDATE user_specialties
            SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
            WHERE username = ? AND specialty = 'general'
        """, (now, username))

        if cursor.rowcount > 0:
            conn.commit()
            return

        # Fallback 2: decrementar la especialidad con mayor carga.
        row = conn.execute("""
            SELECT specialty
            FROM user_specialties
            WHERE username = ?
            ORDER BY current_load DESC, updated_at ASC NULLS FIRST, specialty ASC
            LIMIT 1
        """, (username,)).fetchone()
        if row:
            conn.execute("""
                UPDATE user_specialties
                SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, row["specialty"]))
        conn.commit()
    finally:
        conn.close()

