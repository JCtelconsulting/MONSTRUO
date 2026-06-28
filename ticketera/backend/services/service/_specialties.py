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
# GESTIÓN DE ESPECIALIDADES
# ==========================================================================
def _resolve_role_specialties(role_value: Any, secondary_roles_value: Any) -> List[str]:
    out: List[str] = []
    for role_item in _normalize_roles([role_value, *(_normalize_roles(secondary_roles_value))]):
        mapped = ROLE_SPECIALTY_FALLBACK.get(role_item)
        if mapped and mapped not in out:
            out.append(mapped)
    return out


# Mapeo de especialidad (área del usuario) -> categoría de ticket. Las especialidades
# que no aparecen aquí (p.ej. 'general' de ops) no acotan por categoría: ese usuario
# verá solo los tickets asignados a él.
SPECIALTY_TO_CATEGORIA = {
    "redes": "redes",
    "sistemas": "sistemas",
    "ejecucion": "ejecucion",
    "warehouse": "bodega",
}

# Categorías de ticket válidas: un rol que ya es una categoría (p.ej. 'gerencia')
# acota directamente a esa categoría.
_CATEGORIAS_TICKET = {"redes", "sistemas", "ejecucion", "admin", "bodega", "gerencia"}

# Roles no técnicos que igualmente se acotan por área (gerencia ve solo su área).
_ROLES_ACOTADOS_EXTRA = {"gerencia"}


def categorias_visibles_para_roles(roles: Any) -> Optional[List[str]]:
    """Categorías (áreas) que un usuario puede ver en Lista/Archivados.

    - None  => ve TODO (admin / encargado de mesa).
    - lista => acotado a esas categorías (además de los tickets asignados a él).
    - []    => sin área mapeable: verá solo los tickets asignados a él.

    Liga la visibilidad al ÁREA, no a la persona: si cambia el personal de un
    área, la vista sigue funcionando sin reconfigurar nada.
    """
    normalized = _normalize_roles(roles)
    # Gestión global (admin / encargado de mesa) ve todo.
    if any(r in ticket_roles.ROLES_ADMIN_GESTION for r in normalized):
        return None
    # Solo se acota por área a roles técnicos o de gerencia. Cualquier otro rol
    # (desconocido / lectura) conserva el comportamiento previo: ve todo.
    acota = any(
        (r in ROLES_TECNICOS_SET) or (r in _ROLES_ACOTADOS_EXTRA)
        for r in normalized
    )
    if not acota:
        return None
    cats: List[str] = []
    for role in normalized:
        spec = ROLE_SPECIALTY_FALLBACK.get(role)
        cat = SPECIALTY_TO_CATEGORIA.get(spec) if spec else None
        if not cat and role in _CATEGORIAS_TICKET:
            cat = role
        if cat and cat not in cats:
            cats.append(cat)
    return cats

def _active_ticket_load_map(conn) -> Dict[str, int]:
    rows = conn.execute(
        """
        SELECT LOWER(asignado_a) AS username, COUNT(*) AS active_count
        FROM tickets
        WHERE COALESCE(asignado_a, '') <> ''
          AND estado IN ('abierto', 'en_progreso')
        GROUP BY LOWER(asignado_a)
        """
    ).fetchall()
    out: Dict[str, int] = {}
    for row in rows:
        username = _normalize_username(row.get("username"))
        if not username:
            continue
        out[username] = int(row.get("active_count") or 0)
    return out

def _list_specialties_with_role_fallback(conn) -> List[Dict[str, Any]]:
    # El patrón del LIKE va como PARÁMETRO (no inline): psycopg interpreta el '%' del SQL
    # como placeholder y rompe la query si se escribe '%"tks"%' literal.
    base_rows = conn.execute(
        """
        SELECT us.*, u.role, u.secondary_roles
        FROM user_specialties us
        LEFT JOIN users u ON u.username = us.username
        WHERE COALESCE(u.allowed_modules, '') LIKE ?
        ORDER BY us.specialty, us.username
        """,
        ('%"tks"%',),
    ).fetchall()
    items = [dict(r) for r in base_rows]
    existing_keys = {
        (_normalize_username(item.get("username")), _normalize_role(item.get("specialty")))
        for item in items
        if _normalize_username(item.get("username")) and _normalize_role(item.get("specialty"))
    }

    load_map = _active_ticket_load_map(conn)
    now = db.now_utc_iso()
    user_rows = conn.execute(
        "SELECT username, role, secondary_roles FROM users WHERE COALESCE(is_active, 1) = 1 "
        "AND COALESCE(allowed_modules, '') LIKE ? ORDER BY username ASC",
        ('%"tks"%',),
    ).fetchall()
    for row in user_rows:
        username = _normalize_username(row.get("username"))
        if not username:
            continue
        role = _normalize_role(row.get("role"))
        try:
            secondary_roles_raw = json.loads(row.get("secondary_roles") or "[]")
        except Exception:
            secondary_roles_raw = []
        derived_specialties = _resolve_role_specialties(role, secondary_roles_raw)
        if not derived_specialties:
            # Gerencia no tiene rol técnico, pero debe poder ser asignado como un usuario
            # más (Diego aprueba/rechaza requerimientos, pero también recibe tickets normales).
            if role == "gerencia":
                key = (username, "gerencia")
                if key not in existing_keys:
                    active_load = int(load_map.get(username, 0))
                    items.append(
                        {
                            "username": username,
                            "specialty": "gerencia",
                            "current_load": active_load,
                            "max_load": max(10, active_load + 1),
                            "is_available": 1,
                            "created_at": now,
                            "updated_at": now,
                            "role": role,
                            "secondary_roles": json.dumps(_normalize_roles(secondary_roles_raw)),
                        }
                    )
                    existing_keys.add(key)
            continue
        role_secondary_json = json.dumps(_normalize_roles(secondary_roles_raw))
        active_load = int(load_map.get(username, 0))
        for specialty in derived_specialties:
            key = (username, specialty)
            if key in existing_keys:
                continue
            items.append(
                {
                    "username": username,
                    "specialty": specialty,
                    "current_load": active_load,
                    "max_load": max(10, active_load + 1),
                    "is_available": 1,
                    "created_at": now,
                    "updated_at": now,
                    "role": role,
                    "secondary_roles": role_secondary_json,
                }
            )
            existing_keys.add(key)

    items.sort(key=lambda row: (str(row.get("specialty") or ""), str(row.get("username") or "")))

    # Enriquecer cada item con el nombre real del usuario (desde auth.users, la identidad
    # central). Si no hay nombre cargado, queda vacío y el frontend deriva del correo (fallback).
    name_map: Dict[str, str] = {}
    try:
        name_rows = conn.execute(
            "SELECT username, first_name, last_name FROM users WHERE COALESCE(allowed_modules, '') LIKE ?",
            ('%"tks"%',),
        ).fetchall()
        for nr in name_rows:
            u = _normalize_username(nr.get("username"))
            if u:
                name_map[u] = f"{(nr.get('first_name') or '').strip()} {(nr.get('last_name') or '').strip()}".strip()
    except Exception:
        name_map = {}
    for item in items:
        item["display_name"] = name_map.get(_normalize_username(item.get("username")), "")

    return items

def list_specialties() -> List[Dict[str, Any]]:
    """Lista especialidades reales + fallback derivado de roles técnicos."""
    conn = db.get_conn()
    try:
        items = _list_specialties_with_role_fallback(conn)
        return [row for row in items if _normalize_username(row.get("username")) != "mesa_ayuda"]
    finally:
        conn.close()

def upsert_specialty(username: str, specialty: str, max_load: int = 10) -> Dict[str, Any]:
    """Crear o actualizar especialidad de usuario."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute("""
            INSERT INTO user_specialties (username, specialty, max_load, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, specialty) DO UPDATE SET
                max_load = excluded.max_load,
                updated_at = excluded.updated_at
        """, (username, specialty, max_load, now, now))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_specialties WHERE username = ? AND specialty = ?",
            (username, specialty)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def toggle_availability(username: str, is_available: bool) -> None:
    """Activar/desactivar disponibilidad de un técnico."""
    conn = db.get_conn()
    try:
        conn.execute("""
            UPDATE user_specialties
            SET is_available = ?, updated_at = ?
            WHERE username = ?
        """, (1 if is_available else 0, db.now_utc_iso(), username))
        conn.commit()
    finally:
        conn.close()

def delete_specialty(username: str, specialty: str) -> None:
    """Eliminar una especialidad de un técnico."""
    conn = db.get_conn()
    try:
        conn.execute(
            "DELETE FROM user_specialties WHERE username = ? AND specialty = ?",
            (username, specialty)
        )
        conn.commit()
    finally:
        conn.close()

