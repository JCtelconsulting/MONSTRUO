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
# CLIENT ASSOCIATION LOGIC
# ==========================================================================
def associate_email_to_client(email: str, customer_id: str, customer_name: str, actor: str) -> bool:
    """Asocia un correo a un cliente de Laudus/Sistema."""
    email = email.strip().lower()
    if not email or not customer_id:
        raise ValueError("Email y Customer ID son requeridos")
    
    conn = db.get_conn()
    now_ts = db.now_utc_iso()
    
    # 1. UPSERT en la tabla de configuración
    # SQLite vs Postgres syntax diff handling via simple delete/insert or check
    # Asumimos SQLite por compatibilidad simple o standard SQL
    
    # Check if exists
    row = conn.execute("SELECT 1 FROM ticket_config_client_emails WHERE email = ?", (email,)).fetchone()
    
    if row:
        conn.execute("""
            UPDATE ticket_config_client_emails 
            SET customer_id = ?, customer_name = ?, updated_at = ?
            WHERE email = ?
        """, (customer_id, customer_name, now_ts, email))
    else:
        conn.execute("""
            INSERT INTO ticket_config_client_emails (email, customer_id, customer_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email, customer_id, customer_name, now_ts, now_ts))
    
    # 2. Actualizar tickets históricos ABIERTOS de este correo?
    # El usuario pidió "que en un futuro asocie", pero usualmente se espera que retroactivamente
    # arregle lo que se ve FEO ahora. Vamos a actualizar tickets abiertos que tengan ese origen_email.
    conn.execute("""
        UPDATE tickets 
        SET cliente_nombre = ? 
        WHERE lower(origen_email) = ? 
          AND (cliente_nombre IS NULL OR cliente_nombre = '' OR cliente_nombre = 'Desconocido')
    """, (customer_name, email))
    
    conn.commit()
    conn.close()
    return True

def bulk_assign_customer_by_email(
    origen_email: str,
    customer_id: str,
    customer_name: str,
) -> Dict[str, Any]:
    """
    Asocia todos los tickets que tengan el mismo origen_email (o dominio)
    al cliente indicado. Retorna cuántos tickets fueron actualizados.
    """
    email = str(origen_email or "").strip().lower()
    if not email or not customer_id:
        raise ValueError("Email y customer_id son requeridos")

    conn = db.get_conn()
    try:
        # Tickets con mismo email exacto sin cliente asignado
        by_email = conn.execute(
            """UPDATE tks.tickets
               SET customer_id = ?, cliente_nombre = ?
               WHERE LOWER(COALESCE(origen_email, '')) = ?
                 AND (customer_id IS NULL OR customer_id = '')
               RETURNING id""",
            (customer_id, customer_name, email),
        ).fetchall()

        # Tickets con mismo dominio sin cliente asignado
        dominio = email.split("@")[1] if "@" in email else None
        by_domain = []
        if dominio:
            by_domain = conn.execute(
                """UPDATE tks.tickets
                   SET customer_id = ?, cliente_nombre = ?
                   WHERE LOWER(COALESCE(origen_email, '')) LIKE ?
                     AND (customer_id IS NULL OR customer_id = '')
                   RETURNING id""",
                (customer_id, customer_name, f"%@{dominio}"),
            ).fetchall()

        conn.commit()
        total = len(by_email) + len(by_domain)
        return {
            "ok": True,
            "updated": total,
            "by_email": len(by_email),
            "by_domain": len(by_domain),
            "dominio": dominio,
        }
    finally:
        conn.close()


def search_customers(q: str = "", limit: int = 0) -> List[Dict[str, Any]]:
    """Busca clientes en laudus_customers; con limit=0 devuelve todos."""
    try:
        raw_limit = int(limit or 0)
    except Exception:
        raw_limit = 0
    limit = max(0, min(raw_limit, 5000))
    query = str(q or "").strip()

    conn = db.get_conn()
    try:
        if query and limit > 0:
            wildcard = f"%{query}%"
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                WHERE name ILIKE ? OR legal_name ILIKE ? OR vat_id ILIKE ?
                ORDER BY COALESCE(name, legal_name, '') ASC
                LIMIT ?
                """,
                (wildcard, wildcard, wildcard, limit),
            ).fetchall()
        elif query:
            wildcard = f"%{query}%"
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                WHERE name ILIKE ? OR legal_name ILIKE ? OR vat_id ILIKE ?
                ORDER BY COALESCE(name, legal_name, '') ASC
                """,
                (wildcard, wildcard, wildcard),
            ).fetchall()
        elif limit > 0:
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                ORDER BY COALESCE(name, legal_name, '') ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                ORDER BY COALESCE(name, legal_name, '') ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_client_for_email(email: str) -> Optional[Dict[str, Any]]:
    """Resuelve el cliente asociado a un correo."""
    if not email:
        return None
    email = email.strip().lower()
    conn = db.get_conn()
    row = conn.execute("SELECT customer_id, customer_name FROM ticket_config_client_emails WHERE email = ?", (email,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


# ==========================================================================
# DIRECTORIO DE CLIENTES
# ==========================================================================

def get_directorio_clientes(q: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna la lista de clientes que tienen tickets registrados,
    con conteos por estado para el panel lateral del Directorio.
    """
    conn = db.get_conn()
    try:
        # Clientes conocidos (con nombre) que tienen tickets
        rows = conn.execute(
            """
            SELECT
                t.customer_id,
                COALESCE(t.customer_id, 'sin_cliente') as id,
                COALESCE(
                    MAX(cce.customer_name),
                    MAX(t.cliente_nombre),
                    t.customer_id,
                    'Sin Cliente'
                ) as nombre,
                COUNT(*) as total,
                SUM(CASE WHEN t.estado IN ('abierto', 'en_progreso') AND COALESCE(t.is_trashed, FALSE) = FALSE THEN 1 ELSE 0 END) as activos,
                SUM(CASE WHEN t.estado IN ('resuelto', 'cerrado') THEN 1 ELSE 0 END) as resueltos
            FROM tickets t
            LEFT JOIN ticket_config_client_emails cce
                ON LOWER(t.origen_email) = LOWER(cce.email)
            WHERE t.customer_id IS NOT NULL AND t.customer_id != ''
            GROUP BY t.customer_id
            ORDER BY activos DESC, total DESC
            """
        ).fetchall()

        clientes = []
        for r in rows:
            nombre = str(r.get("nombre") or r.get("id") or "Sin Cliente")
            if q and q.strip():
                if q.strip().lower() not in nombre.lower():
                    continue
            clientes.append({
                "id": str(r.get("id") or ""),
                "nombre": nombre,
                "total": int(r.get("total") or 0),
                "activos": int(r.get("activos") or 0),
                "resueltos": int(r.get("resueltos") or 0),
            })

        return {"items": clientes, "total": len(clientes)}
    finally:
        conn.close()


def get_directorio_metricas(
    customer_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Dict[str, Any]:
    """
    KPIs de un cliente en un rango de fechas para el encabezado
    analítico del Directorio: volumen, SLA, tiempo de respuesta.
    """
    conn = db.get_conn()
    try:
        where = ["1=1"]
        params: List[Any] = []

        if customer_id:
            where.append("LOWER(COALESCE(customer_id, '')) = ?")
            params.append(customer_id.strip().lower())

        if created_after:
            where.append("created_at >= ?")
            params.append(created_after)

        if created_before:
            where.append("created_at <= ?")
            params.append(created_before)

        where_sql = " AND ".join(where)

        row = conn.execute(
            f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN estado IN ('resuelto', 'cerrado') THEN 1 ELSE 0 END) as resueltos,
                SUM(CASE WHEN estado IN ('abierto', 'en_progreso')
                         AND COALESCE(is_trashed, FALSE) = FALSE THEN 1 ELSE 0 END) as activos,
                SUM(CASE WHEN COALESCE(sla_frt_breached, FALSE) = TRUE THEN 1 ELSE 0 END) as sla_frt_incumplidos,
                SUM(CASE WHEN COALESCE(sla_ttr_breached, FALSE) = TRUE THEN 1 ELSE 0 END) as sla_ttr_incumplidos,
                AVG(
                    CASE
                        WHEN first_response_at IS NOT NULL AND created_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (first_response_at::timestamp - created_at::timestamp)) / 60.0
                    END
                ) as avg_frt_minutos,
                AVG(
                    CASE
                        WHEN resolved_at IS NOT NULL AND created_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (resolved_at::timestamp - created_at::timestamp)) / 60.0
                    END
                ) as avg_ttr_minutos
            FROM tickets
            WHERE {where_sql}
            """,
            params,
        ).fetchone()

        if not row:
            return {"total": 0, "resueltos": 0, "activos": 0}

        total = int(row.get("total") or 0)
        resueltos = int(row.get("resueltos") or 0)
        activos = int(row.get("activos") or 0)
        sla_frt = int(row.get("sla_frt_incumplidos") or 0)
        sla_ttr = int(row.get("sla_ttr_incumplidos") or 0)

        avg_frt = row.get("avg_frt_minutos")
        avg_ttr = row.get("avg_ttr_minutos")

        cumplimiento_pct = None
        if total > 0:
            cumplimiento_pct = round(100 * (1 - (sla_ttr / total)), 1)

        return {
            "total": total,
            "resueltos": resueltos,
            "activos": activos,
            "sla_frt_incumplidos": sla_frt,
            "sla_ttr_incumplidos": sla_ttr,
            "cumplimiento_sla_pct": cumplimiento_pct,
            "avg_frt_minutos": round(float(avg_frt), 1) if avg_frt else None,
            "avg_ttr_minutos": round(float(avg_ttr), 1) if avg_ttr else None,
        }
    except Exception as e:
        logger.error(f"[get_directorio_metricas] Error: {e}")
        return {"total": 0, "resueltos": 0, "activos": 0, "error": str(e)}
    finally:
        conn.close()
