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
from ._classify import auto_asignar, clasificar_ticket, incrementar_carga, decrementar_carga
from ._notifications import programar_notificaciones, notify_client_resolution
from ._specialties import list_specialties
from ._customers import get_client_for_email
from ._sla import create_evidence_event

logger = logging.getLogger(__name__)

# ==========================================================================
# GENERADOR DE CÓDIGO DE TICKET
# ==========================================================================
def generar_codigo(ticket_id: int) -> str:
    """Genera código público simple TK-2154+."""
    normalized_id = max(1, int(ticket_id or 1))
    public_number = TICKET_PUBLIC_CODE_START + normalized_id - 1
    return f"TK-{public_number}"

def _workflow_next(tipo: str, subestado: str) -> List[str]:
    return ticket_workflow.workflow_next(tipo, subestado)

def _workflow_can_transition(tipo: str, from_subestado: str, to_subestado: str) -> bool:
    return ticket_workflow.can_transition(tipo, from_subestado, to_subestado)

def _normalize_transition_target(from_subestado: str, requested_subestado: Optional[str]) -> str:
    return ticket_workflow.normalize_transition_target(from_subestado, requested_subestado)

def _is_estado_en_progreso(estado: Optional[str]) -> bool:
    return str(estado or "").strip().lower() == "en_progreso"

def _filter_waiting_subestados(allowed_next: List[str], estado_actual: Optional[str]) -> List[str]:
    if _is_estado_en_progreso(estado_actual):
        return list(allowed_next or [])
    return [s for s in (allowed_next or []) if normalize_subestado(s, "") not in SUBESTADOS_ESPERA]

def _validate_main_status_transition(current_estado: str, target_estado: str) -> None:
    current = str(current_estado or "").strip().lower()
    target = str(target_estado or "").strip().lower()
    if current not in MAIN_STATUS_SEQUENCE or target not in MAIN_STATUS_SEQUENCE:
        return
    if current == target:
        return
    current_idx = MAIN_STATUS_SEQUENCE.index(current)
    target_idx = MAIN_STATUS_SEQUENCE.index(target)
    if abs(target_idx - current_idx) > 1:
        raise ConflictError(
            "Transición de estado inválida: solo se permite avanzar o retroceder un estado a la vez "
            f"({current} -> {target})."
        )

def _comment_with_prefix_exists(conn, ticket_id: int, prefix: str) -> bool:
    row = conn.execute(
        """SELECT 1
           FROM ticket_comments
           WHERE ticket_id = ?
             AND content ILIKE ?
           ORDER BY id DESC
           LIMIT 1""",
        (ticket_id, f"{prefix}%"),
    ).fetchone()
    return bool(row)

def _emit_system_comment(conn, ticket_id: int, content: str, now_iso: str, author_id: str = "system") -> None:
    conn.execute(
        """INSERT INTO ticket_comments (ticket_id, user_id, content, is_internal, created_at)
           VALUES (?, ?, ?, 1, ?)""",
        (ticket_id, author_id, content, now_iso),
    )

def _latest_approval_decisions(conn, ticket_id: int) -> Dict[int, str]:
    rows = conn.execute(
        """SELECT step, decision
           FROM ticket_approvals
           WHERE ticket_id = ?
           ORDER BY decided_at DESC, id DESC""",
        (ticket_id,),
    ).fetchall()
    latest: Dict[int, str] = {}
    for row in rows:
        step = int(row["step"])
        if step not in latest:
            latest[step] = str(row["decision"]).lower()
    return latest

def _is_open_estado(estado: str) -> bool:
    return (estado or "").lower() not in {"resuelto", "cerrado"}

def _evaluate_ticket_sla(conn, ticket_id: int, now_iso: Optional[str] = None) -> None:
    now_iso = now_iso or db.now_utc_iso()
    now_dt = _parse_dt(now_iso) or _now_dt()
    row = conn.execute(
        """SELECT id, estado, subestado, created_at, updated_at, first_response_at, frt_due_at, ttr_due_at,
                  frt_breached_at, ttr_breached_at, resolved_at
           FROM tickets
           WHERE id = ?""",
        (ticket_id,),
    ).fetchone()
    if not row:
        return
    ticket = dict(row)

    created_dt = _parse_dt(ticket.get("created_at"))
    frt_due_dt = _parse_dt(ticket.get("frt_due_at"))
    ttr_due_dt = _parse_dt(ticket.get("ttr_due_at"))
    first_response_dt = _parse_dt(ticket.get("first_response_at"))
    resolved_dt = _parse_dt(ticket.get("resolved_at")) or _parse_dt(ticket.get("updated_at"))
    estado = (ticket.get("estado") or "").lower()

    def _warn_prefix(metric: str, pct: int) -> str:
        metric_key = "FRT" if metric == "frt" else "TTR"
        if pct == 80:
            return f"[SLA_WARN_{metric_key}]"
        return f"[SLA_WARN_{metric_key}_{pct}]"

    if created_dt and frt_due_dt and first_response_dt is None:
        total_seconds = max(0.0, (frt_due_dt - created_dt).total_seconds())
        elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
        if total_seconds > 0 and now_dt < frt_due_dt:
            progress_pct = (elapsed_seconds / total_seconds) * 100.0
            for threshold in SLA_ESCALATION_WINDOWS_PCT:
                if threshold >= 100:
                    continue
                if progress_pct < float(threshold):
                    continue
                prefix = _warn_prefix("frt", threshold)
                if _comment_with_prefix_exists(conn, ticket_id, prefix):
                    continue
                _emit_system_comment(
                    conn,
                    ticket_id,
                    f"{prefix} El ticket alcanzó {threshold}% del tiempo de primera respuesta (FRT).",
                    now_iso,
                )
        if now_dt >= frt_due_dt:
            if not ticket.get("frt_breached_at"):
                conn.execute("UPDATE tickets SET frt_breached_at = ? WHERE id = ?", (now_iso, ticket_id))
            if not _comment_with_prefix_exists(conn, ticket_id, "[SLA_BREACH_FRT]"):
                _emit_system_comment(
                    conn,
                    ticket_id,
                    "[SLA_BREACH_FRT] Se superó el FRT objetivo.",
                    now_iso,
                )

    if created_dt and ttr_due_dt and _is_open_estado(estado):
        total_seconds = max(0.0, (ttr_due_dt - created_dt).total_seconds())
        elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
        if total_seconds > 0 and now_dt < ttr_due_dt:
            progress_pct = (elapsed_seconds / total_seconds) * 100.0
            for threshold in SLA_ESCALATION_WINDOWS_PCT:
                if threshold >= 100:
                    continue
                if progress_pct < float(threshold):
                    continue
                prefix = _warn_prefix("ttr", threshold)
                if _comment_with_prefix_exists(conn, ticket_id, prefix):
                    continue
                _emit_system_comment(
                    conn,
                    ticket_id,
                    f"{prefix} El ticket alcanzó {threshold}% del tiempo de resolución (TTR).",
                    now_iso,
                )
        if now_dt >= ttr_due_dt:
            if not ticket.get("ttr_breached_at"):
                conn.execute("UPDATE tickets SET ttr_breached_at = ? WHERE id = ?", (now_iso, ticket_id))
            if not _comment_with_prefix_exists(conn, ticket_id, "[SLA_BREACH_TTR]"):
                _emit_system_comment(
                    conn,
                    ticket_id,
                    "[SLA_BREACH_TTR] Se superó el TTR objetivo.",
                    now_iso,
                )

    if ttr_due_dt and estado in {"resuelto", "cerrado"}:
        if resolved_dt and resolved_dt > ttr_due_dt and not ticket.get("ttr_breached_at"):
            conn.execute(
                "UPDATE tickets SET ttr_breached_at = COALESCE(ttr_breached_at, ?) WHERE id = ?",
                (resolved_dt.isoformat(), ticket_id),
            )

    # Auto-cierre opcional para tickets en resuelto tras ventana de seguimiento.
    if estado == "resuelto" and RESUELTO_AUTO_CLOSE_HOURS > 0 and resolved_dt:
        auto_close_at = resolved_dt + timedelta(hours=RESUELTO_AUTO_CLOSE_HOURS)
        if now_dt >= auto_close_at:
            from_sub = normalize_subestado(ticket.get("subestado"), "resuelto")
            update_result = conn.execute(
                """UPDATE tickets
                   SET estado = 'cerrado',
                       subestado = 'cerrado',
                       updated_at = ?,
                       resolved_at = COALESCE(resolved_at, ?)
                   WHERE id = ? AND estado = 'resuelto'""",
                (now_iso, now_iso, ticket_id),
            )
            updated_rows = getattr(update_result, "rowcount", None)
            if updated_rows == 0:
                return
            conn.execute(
                """INSERT INTO ticket_transitions
                   (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
                   VALUES (?, ?, 'cerrado', 'system', ?, ?)""",
                (
                    ticket_id,
                    from_sub,
                    f"auto_close_resuelto_timeout_{RESUELTO_AUTO_CLOSE_HOURS}h",
                    now_iso,
                ),
            )
            _emit_system_comment(
                conn,
                ticket_id,
                f"[AUTO_CIERRE] Ticket cerrado automáticamente tras {RESUELTO_AUTO_CLOSE_HOURS}h en estado resuelto.",
                now_iso,
            )
            _recompute_ticket_retention(conn, ticket_id)

def run_sla_evaluation_batch(limit: int = 500) -> Dict[str, Any]:
    """
    Evalúa SLA en lote para tickets que pueden requerir actualización de breach/alertas.
    Se ejecuta vía job periódico para mantener endpoints GET sin side effects.
    """
    batch_limit = max(1, min(int(limit or 500), 5000))
    now_iso = db.now_utc_iso()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id
               FROM tickets
               WHERE COALESCE(is_trashed, FALSE) = FALSE
                 AND (
                   (first_response_at IS NULL AND frt_due_at IS NOT NULL)
                   OR
                   (ttr_due_at IS NOT NULL)
                   OR
                   (estado = 'resuelto')
               )
               ORDER BY COALESCE(updated_at, created_at) ASC, id ASC
               LIMIT ?""",
            (batch_limit,),
        ).fetchall()
        processed = 0
        for row in rows:
            _evaluate_ticket_sla(conn, int(row["id"]), now_iso)
            processed += 1
        conn.commit()
        return {
            "ok": True,
            "processed": processed,
            "limit": batch_limit,
            "evaluated_at": now_iso,
        }
    finally:
        conn.close()

def _maybe_mark_first_response(conn, ticket_id: int, by_user: str, now_iso: Optional[str] = None) -> None:
    if not by_user:
        return
    actor = str(by_user).strip().lower()
    if actor.startswith("system") or actor.startswith("email:") or actor == "email_bot":
        return
    now_iso = now_iso or db.now_utc_iso()
    row = conn.execute(
        "SELECT first_response_at, frt_due_at FROM tickets WHERE id = ?",
        (ticket_id,),
    ).fetchone()
    if not row or row.get("first_response_at"):
        return
    frt_due_dt = _parse_dt(row.get("frt_due_at"))
    now_dt = _parse_dt(now_iso) or _now_dt()
    if frt_due_dt and now_dt > frt_due_dt:
        conn.execute(
            """UPDATE tickets
               SET first_response_at = ?, frt_breached_at = COALESCE(frt_breached_at, ?)
               WHERE id = ?""",
            (now_iso, now_iso, ticket_id),
        )
    else:
        conn.execute(
            "UPDATE tickets SET first_response_at = ? WHERE id = ?",
            (now_iso, ticket_id),
        )

def _hydrate_ticket_runtime(ticket: Dict[str, Any], now_dt: Optional[datetime] = None) -> Dict[str, Any]:
    now_dt = now_dt or _now_dt()
    t = dict(ticket)
    notify_list = _notify_emails_from_ticket(t)
    t["notify_emails_list"] = notify_list
    t["notify_emails"] = ", ".join(notify_list)
    t["is_trashed"] = _db_bool(t.get("is_trashed"))
    estado_norm = str(t.get("estado") or "").strip().lower()
    sub_norm = normalize_subestado(t.get("subestado"), "recibido")
    # Guard rail: normaliza combinaciones legacy incoherentes (estado/subestado)
    # para evitar flujos inválidos en UI/workflow.
    if estado_norm == "cerrado":
        sub_norm = "cerrado"
    elif estado_norm == "resuelto":
        sub_norm = "resuelto"
    t["subestado"] = sub_norm
    t["display_estado"] = _ticket_display_status(t)
    created_dt = _parse_dt(t.get("created_at"))
    frt_due_dt = _parse_dt(t.get("frt_due_at"))
    ttr_due_dt = _parse_dt(t.get("ttr_due_at")) or _parse_dt(t.get("vence_at"))
    first_response_dt = _parse_dt(t.get("first_response_at"))
    resolved_dt = _parse_dt(t.get("resolved_at")) or _parse_dt(t.get("updated_at"))
    estado = estado_norm

    is_frt_breached = bool(t.get("frt_breached_at"))
    if not is_frt_breached and frt_due_dt and first_response_dt is None and now_dt > frt_due_dt:
        is_frt_breached = True

    is_ttr_breached = bool(t.get("ttr_breached_at"))
    if not is_ttr_breached and ttr_due_dt:
        if _is_open_estado(estado) and now_dt > ttr_due_dt:
            is_ttr_breached = True
        if estado in {"resuelto", "cerrado"} and resolved_dt and resolved_dt > ttr_due_dt:
            is_ttr_breached = True

    t["is_frt_breached"] = is_frt_breached
    t["is_ttr_breached"] = is_ttr_breached

    if created_dt and _is_open_estado(estado):
        t["aging_minutes_open"] = max(0, int((now_dt - created_dt).total_seconds() // 60))
    else:
        t["aging_minutes_open"] = 0

    if ttr_due_dt and _is_open_estado(estado) and now_dt > ttr_due_dt:
        t["ttr_minutes_overdue"] = max(0, int((now_dt - ttr_due_dt).total_seconds() // 60))
    else:
        t["ttr_minutes_overdue"] = 0

    if frt_due_dt and first_response_dt is None and now_dt > frt_due_dt:
        t["frt_minutes_overdue"] = max(0, int((now_dt - frt_due_dt).total_seconds() // 60))
    else:
        t["frt_minutes_overdue"] = 0

    return t

# ==========================================================================
# CRUD PRINCIPAL
# ==========================================================================
def _find_customer_by_email(conn, email: str) -> Optional[str]:
    """Busca un cliente (external_id) por coincidencia exacta de email."""
    if not email or "@" not in email:
        return None
    normalized = email.strip().lower()
    
    # Intento 1: Match exacto en campo email
    row = conn.execute(
        "SELECT external_id FROM customers WHERE lower(email) = ?", 
        (normalized,)
    ).fetchone()
    if row:
        return row["external_id"]
        
    return None

# ==========================================================================
def create_ticket(
    titulo: str,
    descripcion: str,
    creador_id: str,
    severidad: str = "media",
    tipo: str = "incidencia",
    categoria: Optional[str] = None,
    origen_email: Optional[str] = None,
    cliente_nombre: Optional[str] = None,
    email_thread_id: Optional[str] = None,
    email_references: Optional[str] = None,
    subestado: Optional[str] = None,
    ticket_security_class: Optional[str] = "internal",
    customer_id: Optional[str] = None,
    contact_role: Optional[str] = None,
    notify_emails: Optional[List[str]] = None,
    auto_assign: bool = False,
) -> Dict[str, Any]:
    """Crear un nuevo ticket con auto-clasificación y auto-asignación."""
    from ._email import _normalize_message_id, _merge_reference_chain  # noqa: PLC0415
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        # Auto-resolver cliente por email si existe mapeo
        if origen_email:
            # Primero buscamos si hay asociación explícita
            client_map = get_client_for_email(origen_email)
            if client_map:
                cliente_nombre = client_map.get("customer_name")
            else:
                # Si NO hay asociación, indicamos "Desconocido" para permitir vincular
                # (aunque venga un nombre en el header del correo, queremos que el usuario lo asocie)
                # Excepción: si ya venía un cliente_nombre explícito (ej: creación manual), lo respetamos
                # pero si viene del procesador de correo, a veces trae el nombre.
                # Asumimos: si tiene origen_email y no está mapeado -> Desconocido
                # A menos que sea un ticket interno o el nombre sea muy distinto.
                # Para simplificar y cumplir el requerimiento: forzamos Desconocido si no está mapeado.
                cliente_nombre = "Desconocido"

        # Normalizar severidad
        severidad = severidad.lower() if severidad else "media"
        if severidad not in SEVERIDADES_VALIDAS:
            severidad = "media"

        explicit_categoria = str(categoria or "").strip().lower()
        if explicit_categoria in CATEGORIAS_VALIDAS:
            categoria = explicit_categoria
        else:
            routed_categoria = _resolve_routing_category_for_email(conn, origen_email) if origen_email else None
            categoria = routed_categoria or clasificar_ticket(titulo, descripcion)

        # Normalizar tipo
        tipo = normalize_ticket_type(tipo)
        explicit_subestado = str(subestado or "").strip()

        # Calcular SLA
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        sla_horas = SLA_HORAS.get(severidad, 72)
        ttr_due_at = _ttr_due_iso(now_dt, severidad)
        frt_due_at = _frt_due_iso(now_dt, severidad)
        vence_at = ttr_due_at

        # Prioridad numérica
        prioridad = PRIORIDAD_MAP.get(severidad, 3)
        security_class = normalize_ticket_security_class(ticket_security_class)
        retention_days = _retention_days_for_class(security_class)
        thread_id = _normalize_message_id(email_thread_id)
        refs = _merge_reference_chain(email_references, thread_id)
        notify_emails_csv = _serialize_notify_emails(notify_emails, strict=True)

        # Auto-asignar (no-crítico: si falla, ticket se crea sin asignar)
        asignado_a = None
        if auto_assign:
            try:
                asignado_a = auto_asignar(categoria)
            except Exception as e:
                logger.warning(f"[create_ticket] auto_asignar falló para categoría '{categoria}': {e}")

        if explicit_subestado:
            subestado = normalize_subestado(explicit_subestado, "recibido")
        else:
            subestado = "asignado" if asignado_a else "sin_asignar"
            subestado = normalize_subestado(subestado, "recibido")

        # Auto-link cliente si no viene explícito
        if not customer_id and origen_email:
            _, email_addr = _sender_identity(origen_email)
            if email_addr:
                customer_id = _find_customer_by_email(conn, email_addr)
                if customer_id:
                     logger.info(f"[create_ticket] Cliente auto-detectado por email '{email_addr}': {customer_id}")

        try:
            cursor = conn.execute(
                """INSERT INTO tickets
                   (titulo, descripcion, estado, severidad, tipo, creador_id,
                    asignado_a, vence_at, created_at, updated_at,
                    categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id, email_references,
                    ticket_security_class, retention_days_snapshot, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails)
                   VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (titulo, descripcion, severidad, tipo, creador_id,
                 asignado_a, vence_at, now, now,
                 categoria, origen_email, cliente_nombre, prioridad, sla_horas, thread_id, refs,
                 security_class, retention_days, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails_csv)
            )
        except Exception as insert_error:
            # Compatibilidad transitoria si la migración aún no aplicó email_references.
            if "email_references" not in str(insert_error).lower():
                raise
            logger.warning(
                "[create_ticket] columna email_references ausente en DB activa; aplicando fallback temporal."
            )
            cursor = conn.execute(
                """INSERT INTO tickets
                   (titulo, descripcion, estado, severidad, tipo, creador_id,
                    asignado_a, vence_at, created_at, updated_at,
                    categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id,
                    ticket_security_class, retention_days_snapshot, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails)
                   VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (titulo, descripcion, severidad, tipo, creador_id,
                 asignado_a, vence_at, now, now,
                 categoria, origen_email, cliente_nombre, prioridad, sla_horas, thread_id,
                 security_class, retention_days, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails_csv)
            )
        row = cursor.fetchone()
        ticket_id = row["id"] if row else None

        # Validar que el INSERT retornó un ID válido
        if ticket_id is None:
            raise ValueError("INSERT INTO tickets no retornó un ID. Posible error en la base de datos.")

        # Generar código y actualizar
        codigo = generar_codigo(ticket_id)
        conn.execute("UPDATE tickets SET codigo = ? WHERE id = ?", (codigo, ticket_id))

        conn.execute(
            """INSERT INTO ticket_transitions
               (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticket_id, "", subestado, creador_id, "creacion_ticket", now),
        )

        if asignado_a:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (ticket_id, creador_id or 'system', f"[ASIGNACION] Auto-asignado a {asignado_a} (especialidad: {categoria})", now)
            )

        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        created_ticket = get_ticket(ticket_id)

        # Programar notificaciones escalonadas (no-crítico: si falla, ticket ya está creado)
        if created_ticket:
            threading.Thread(
                target=notify_helpdesk_new_ticket,
                args=(created_ticket,),
                daemon=True,
            ).start()

        if asignado_a:
            try:
                programar_notificaciones(ticket_id, asignado_a)
            except Exception as e:
                logger.warning(f"[create_ticket] programar_notificaciones falló para ticket {ticket_id}: {e}")

        return created_ticket
    finally:
        conn.close()

def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Obtener un ticket por ID."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not row:
            return None
        return _hydrate_ticket_runtime(dict(row))
    finally:
        conn.close()

def list_tickets(
    estado: Optional[str] = None,
    estados: Optional[List[str]] = None,
    q: Optional[str] = None,
    categoria: Optional[str] = None,
    asignado_a: Optional[str] = None,
    severidad: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    include_full: bool = False,
    include_total: bool = True,
    ver_resueltos: bool = False,
    trashed_only: bool = False,
    customer_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Dict[str, Any]:
    """Listar tickets con filtros avanzados. Retorna {items, total}."""
    conn = db.get_conn()
    try:
        # Protección simple para evitar cargas excesivas en UI.
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params = []

        if trashed_only:
            where_clauses.append("COALESCE(is_trashed, FALSE) = TRUE")
        else:
            where_clauses.append("COALESCE(is_trashed, FALSE) = FALSE")

        if estados:
            placeholders = ", ".join(["?" for _ in estados])
            where_clauses.append(f"estado IN ({placeholders})")
            params.extend([e.lower() for e in estados])
        elif estado:
            where_clauses.append("estado = ?")
            params.append(estado.lower())

        if categoria:
            where_clauses.append("categoria = ?")
            params.append(categoria.lower())

        if asignado_a:
            if ver_resueltos:
                where_clauses.append("(asignado_a = ? OR estado IN ('resuelto', 'cerrado'))")
                params.append(asignado_a)
            else:
                where_clauses.append("asignado_a = ?")
                params.append(asignado_a)

        if severidad:
            where_clauses.append("severidad = ?")
            params.append(severidad.lower())

        if customer_id:
            where_clauses.append("LOWER(COALESCE(customer_id, '')) = ?")
            params.append(customer_id.strip().lower())

        if created_after:
            where_clauses.append("created_at >= ?")
            params.append(created_after)

        if created_before:
            where_clauses.append("created_at <= ?")
            params.append(created_before)

        if q:
            where_clauses.append("(titulo ILIKE ? OR descripcion ILIKE ? OR codigo ILIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        where_sql = " AND ".join(where_clauses)

        total = 0
        if include_total:
            count_row = conn.execute(f"SELECT COUNT(*) as total FROM tickets WHERE {where_sql}", params).fetchone()
            total = count_row["total"] if count_row else 0

        # Para listados y kanban no necesitamos payload completo (descripcion puede ser muy grande).
        select_fields = (
            "*"
            if include_full
            else """
                id, codigo, titulo, estado, tipo, severidad, creador_id, asignado_a,
                vence_at, created_at, updated_at, categoria, origen_email, cliente_nombre,
                prioridad, email_thread_id, resolucion, sla_horas,
                subestado, frt_due_at, ttr_due_at, first_response_at, resolved_at,
                frt_breached_at, ttr_breached_at, ticket_security_class,
                retention_until, retention_days_snapshot, customer_id, contact_role, notify_emails,
                is_trashed, trashed_at, trashed_by, trash_reason,
                trash_prev_estado, trash_prev_subestado, trash_prev_asignado_a
            """
        )

        # Obtener items
        items_params = params + [limit, offset]
        cursor = conn.execute(
            f"SELECT {select_fields} FROM tickets WHERE {where_sql} ORDER BY prioridad ASC, created_at DESC LIMIT ? OFFSET ?",
            items_params
        )
        now_dt = _now_dt()
        items = [_hydrate_ticket_runtime(dict(row), now_dt=now_dt) for row in cursor.fetchall()]

        return {"items": items, "total": total if include_total else len(items)}
    finally:
        conn.close()

def claim_ticket(ticket_id: int, actor_id: str, actor_role: str = "") -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "tomar el ticket")

    actor_username = str(actor_id or "").strip()
    if not actor_username:
        raise ValueError("Usuario inválido para tomar ticket")

    if _scope_enforced(actor_role):
        role_norm = _normalize_role(actor_role)
        if role_norm in ROLES_ADMIN_GESTION:
            raise PermissionError("El admin no puede tomar tickets. Debe reasignarlos.")
        if role_norm not in ROLES_TECNICOS_SET:
            raise PermissionError("Rol no autorizado para tomar tickets.")

    actor_norm = _normalize_username(actor_username)
    current_assignee_norm = _ticket_assignee_username(ticket)
    if current_assignee_norm == actor_norm:
        return {"ok": True, "already_assigned": True, "ticket": ticket}
    if current_assignee_norm and current_assignee_norm != actor_norm:
        raise PermissionError(
            f"Ticket asignado a '{ticket.get('asignado_a')}'. Solo admin puede reasignarlo."
        )

    from_subestado = normalize_subestado(ticket.get("subestado"), "recibido")
    target_subestado = "asignado" if from_subestado == "recibido" else from_subestado
    target_estado = estado_from_subestado(target_subestado, str(ticket.get("estado") or "abierto"))

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        row = conn.execute(
            """UPDATE tickets
               SET asignado_a = ?, subestado = ?, estado = ?, updated_at = ?
               WHERE id = ? AND COALESCE(asignado_a, '') = ''
               RETURNING id""",
            (actor_username, target_subestado, target_estado, now, ticket_id),
        ).fetchone()

        if not row:
            live_row = conn.execute("SELECT asignado_a FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            live_assignee = _normalize_username((live_row or {}).get("asignado_a"))
            if live_assignee == actor_norm:
                return {"ok": True, "already_assigned": True, "ticket": get_ticket(ticket_id)}
            if live_assignee:
                raise PermissionError(
                    f"Ticket asignado a '{live_row.get('asignado_a')}'. Solo admin puede reasignarlo."
                )
            raise ValueError("No fue posible tomar el ticket en este momento.")

        _emit_system_comment(conn, ticket_id, f"[ASIGNACION] Ticket tomado por {actor_username}", now, author_id=actor_username)
        if target_subestado != from_subestado:
            conn.execute(
                """INSERT INTO ticket_transitions
                   (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ticket_id, from_subestado, target_subestado, actor_username, "claim_ticket", now),
            )
            _emit_system_comment(conn, ticket_id, f"[TRANSICION] {from_subestado} -> {target_subestado}", now, author_id=actor_username)
        _maybe_mark_first_response(conn, ticket_id, actor_username, now)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    try:
        incrementar_carga(actor_username, specialty=ticket.get("categoria"))
    except Exception as e:
        logger.warning(f"[claim_ticket] Falló incrementar_carga para {actor_username}: {e}")

    try:
        programar_notificaciones(ticket_id, actor_username)
    except Exception as e:
        logger.warning(f"[claim_ticket] Falló programar_notificaciones para {actor_username}: {e}")

    return {"ok": True, "claimed": True, "ticket": get_ticket(ticket_id)}

def update_ticket(
    ticket_id: int,
    updates: Dict[str, Any],
    actor_id: str = "system",
    actor_role: str = "",
) -> Optional[Dict[str, Any]]:
    """Actualizar campos del ticket."""
    allowed_keys = {
        "estado",
        "subestado",
        "severidad",
        "asignado_a",
        "titulo",
        "descripcion",
        "vence_at",
        "categoria",
        "prioridad",
        "resolucion",
        "ticket_security_class",
        "customer_id",
        "contact_role",
        "notify_emails",
    }
    current = get_ticket(ticket_id)
    if not current:
        return None
    _ensure_ticket_not_trashed(current, "modificar el ticket")

    normalized_updates: Dict[str, Any] = {}
    for key, value in (updates or {}).items():
        if key not in allowed_keys:
            continue
        if key == "estado":
            estado = str(value or "").strip().lower()
            if estado in ESTADOS_VALIDOS:
                current_estado = str(current.get("estado") or "abierto").lower()
                _validate_main_status_transition(current_estado, estado)
                normalized_updates[key] = estado
            continue
        if key == "subestado":
            normalized_updates[key] = normalize_subestado(value, current.get("subestado") or "recibido")
            continue
        if key == "severidad":
            sev = str(value or "").strip().lower()
            normalized_updates[key] = sev if sev in SEVERIDADES_VALIDAS else current.get("severidad", "media")
            continue
        if key == "ticket_security_class":
            normalized_updates[key] = normalize_ticket_security_class(value)
            continue
        if key == "asignado_a":
            normalized_updates[key] = str(value).strip() if value else None
            continue
        if key == "customer_id" or key == "contact_role":
            normalized_updates[key] = str(value).strip() if value else None
            continue
        if key == "notify_emails":
            normalized_updates[key] = _serialize_notify_emails(value, strict=True)
            continue
        normalized_updates[key] = value

    if "asignado_a" in normalized_updates and normalized_updates.get("asignado_a") and "subestado" not in normalized_updates:
        current_sub = normalize_subestado(current.get("subestado"), "recibido")
        # Si tiene asignado y está en recibido, forzamos asignado.
        if current_sub == "recibido":
            normalized_updates["subestado"] = "asignado"

    if "subestado" in normalized_updates and "estado" not in normalized_updates:
        normalized_updates["estado"] = estado_from_subestado(
            normalized_updates["subestado"],
            str(current.get("estado") or "abierto"),
        )

    # Cuando llega solo "estado" (ej: drag/drop Kanban), sincronizamos subestado para
    # evitar combinaciones incoherentes (ej: estado=abierto con subestado=en_progreso).
    if "estado" in normalized_updates and "subestado" not in normalized_updates:
        target_estado = str(normalized_updates.get("estado") or "").strip().lower()
        current_sub = normalize_subestado(current.get("subestado"), "recibido")
        current_sub_estado = estado_from_subestado(current_sub, str(current.get("estado") or "abierto"))

        if target_estado == "abierto":
            if current_sub_estado == "abierto":
                normalized_updates["subestado"] = current_sub
            else:
                normalized_updates["subestado"] = "asignado" if current.get("asignado_a") else "recibido"
        elif target_estado == "en_progreso":
            if current_sub_estado == "en_progreso" and current_sub not in {"resuelto", "cerrado"}:
                normalized_updates["subestado"] = current_sub
            else:
                normalized_updates["subestado"] = "en_progreso"
        elif target_estado == "resuelto":
            normalized_updates["subestado"] = "resuelto"
        elif target_estado == "cerrado":
            normalized_updates["subestado"] = "cerrado"

    keys_to_update = list(normalized_updates.keys())
    if not keys_to_update:
        return get_ticket(ticket_id)

    actor_norm = _normalize_username(actor_id)
    current_assignee_norm = _ticket_assignee_username(current)
    is_admin_actor = _is_admin_management_role(actor_role)
    can_dispatch_reassign = _can_dispatch_reassign(current, actor_id, actor_role)
    if _scope_enforced(actor_role) and not is_admin_actor:
        if "asignado_a" in normalized_updates:
            target_assignee_norm = _normalize_username(normalized_updates.get("asignado_a"))
            if not target_assignee_norm:
                if not can_dispatch_reassign:
                    raise PermissionError("Solo admin o encargado de mesa puede desasignar tickets.")
            if target_assignee_norm != actor_norm and not can_dispatch_reassign:
                raise PermissionError("Solo admin o encargado de mesa puede reasignar tickets a otro usuario.")
            if current_assignee_norm and current_assignee_norm != actor_norm and not can_dispatch_reassign:
                raise PermissionError(
                    f"Ticket asignado a '{current.get('asignado_a')}'. Solo admin o encargado de mesa puede reasignarlo."
                )

        writes_without_assignment = set(keys_to_update) - {"asignado_a"}
        if writes_without_assignment:
            request_claims_self = _normalize_username(normalized_updates.get("asignado_a")) == actor_norm
            if current_assignee_norm != actor_norm and not (not current_assignee_norm and request_claims_self):
                if current_assignee_norm:
                    raise PermissionError(
                        f"Ticket asignado a '{current.get('asignado_a')}'. Solo el asignado puede modificarlo."
                    )
                raise PermissionError("Ticket sin asignar. Debes tomarlo antes de modificarlo.")

    assignment_claim_mode = (
        _scope_enforced(actor_role)
        and not is_admin_actor
        and "asignado_a" in normalized_updates
        and _normalize_username(normalized_updates.get("asignado_a")) == actor_norm
        and not current_assignee_norm
    )

    old_estado = str(current.get("estado") or "").strip().lower()
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        now_dt = _parse_dt(now) or _now_dt()
        set_clause = ", ".join([f"{k} = ?" for k in keys_to_update]) + ", updated_at = ?"
        where_clause = "id = ?"
        if assignment_claim_mode:
            where_clause += " AND COALESCE(asignado_a, '') = ''"
        params = [normalized_updates[k] for k in keys_to_update] + [now, ticket_id]

        cursor = conn.execute(f"UPDATE tickets SET {set_clause} WHERE {where_clause}", params)
        if cursor.rowcount == 0:
            if assignment_claim_mode:
                live_row = conn.execute("SELECT asignado_a FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
                live_assignee = _normalize_username((live_row or {}).get("asignado_a"))
                if live_assignee == actor_norm:
                    return get_ticket(ticket_id)
                if live_assignee:
                    raise PermissionError(
                        f"Ticket asignado a '{live_row.get('asignado_a')}'. Solo admin puede reasignarlo."
                    )
            return None

        if "subestado" in normalized_updates:
            from_sub = current.get("subestado") or ""
            to_sub = normalized_updates["subestado"]
            if str(from_sub).lower() != str(to_sub).lower():
                conn.execute(
                    """INSERT INTO ticket_transitions
                       (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        ticket_id,
                        str(from_sub),
                        str(to_sub),
                        actor_id,
                        "update_ticket",
                        now,
                    ),
                )
                # Solo emitir nota de sistema si NO es una asignación (para no duplicar avisos)
                # Eliminada emisión de [TRANSICION] por ser redundante con la visual de estados
                # if "asignado_a" not in normalized_updates:
                #     _emit_system_comment(
                #         conn,
                #         ticket_id,
                #         f"[TRANSICION] Subestado cambiado de {from_sub or '-'} a {to_sub}",
                #         now,
                #         author_id="system",
                #     )

        if "estado" in normalized_updates:
            new_estado = normalized_updates["estado"]
            if "asignado_a" not in normalized_updates:
                clean_estado = str(new_estado).replace("_", " ")
                _emit_system_comment(conn, ticket_id, f"[CAMBIO_ESTADO] Estado cambiado a {clean_estado}", now, author_id="system")
            if new_estado in ("cerrado", "resuelto"):
                if current.get("asignado_a"):
                    decrementar_carga(current["asignado_a"], specialty=current.get("categoria"))
                conn.execute(
                    "UPDATE tickets SET resolved_at = COALESCE(resolved_at, ?) WHERE id = ?",
                    (now, ticket_id),
                )
            elif current.get("estado") in ("cerrado", "resuelto") and new_estado in ("abierto", "en_progreso"):
                conn.execute("UPDATE tickets SET resolved_at = NULL WHERE id = ?", (ticket_id,))

        if "asignado_a" in normalized_updates:
            new_asignado = normalized_updates["asignado_a"]
            old_asignado_norm = _normalize_username(current.get("asignado_a"))
            new_asignado_norm = _normalize_username(new_asignado)
            if old_asignado_norm != new_asignado_norm:
                # Nota automática SOLO cuando pasa de sin asignar -> asignado.
                if not old_asignado_norm and new_asignado_norm:
                    # Usamos prefijo para el badge de la UI, pero autor system para ocultar nombre y centrar.
                    _emit_system_comment(conn, ticket_id, f"[ASIGNACION] Asignado a {new_asignado}", now, author_id="system")
                old_cat = current.get("categoria")
                new_cat = normalized_updates.get("categoria", old_cat)
                if current.get("asignado_a"):
                    decrementar_carga(current["asignado_a"], specialty=old_cat)
                if new_asignado:
                    incrementar_carga(str(new_asignado), specialty=new_cat)
                    _maybe_mark_first_response(conn, ticket_id, actor_id, now)
                    try:
                        programar_notificaciones(ticket_id, str(new_asignado))
                    except Exception as e:
                        logger.warning(f"[update_ticket] Falló programar_notificaciones para {new_asignado}: {e}")

        if "severidad" in normalized_updates:
            new_sev = normalized_updates["severidad"]
            new_sla = SLA_HORAS.get(new_sev, 72)
            new_prio = PRIORIDAD_MAP.get(new_sev, 3)
            new_ttr_due = _ttr_due_iso(now_dt, new_sev)
            new_frt_due = _frt_due_iso(now_dt, new_sev)
            conn.execute(
                """UPDATE tickets
                   SET prioridad = ?, sla_horas = ?, vence_at = ?, ttr_due_at = ?,
                       frt_due_at = CASE WHEN first_response_at IS NULL THEN ? ELSE frt_due_at END
                   WHERE id = ?""",
                (new_prio, new_sla, new_ttr_due, new_ttr_due, new_frt_due, ticket_id),
            )
            _emit_system_comment(
                conn,
                ticket_id,
                f"[ESCALAMIENTO] Severidad cambiada a {new_sev}. Nuevo SLA: {_format_sla_minutes_label(TTR_MINUTOS.get(new_sev, RESOLUTION_SLA_MINUTES))}",
                now,
                author_id="system",
            )

        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        updated_ticket = get_ticket(ticket_id)
    finally:
        conn.close()

    # --- Notificaciones post-commit de asignación ---
    if updated_ticket and "asignado_a" in normalized_updates:
        new_asignado = normalized_updates["asignado_a"]
        old_asignado_norm = _normalize_username(current.get("asignado_a"))
        new_asignado_norm = _normalize_username(new_asignado)
        
        # Disparar si es una nueva asignación real
        if new_asignado_norm and old_asignado_norm != new_asignado_norm:
            # Enviar notificaciones en segundo plano para no bloquear la API
            threading.Thread(
                target=notify_client_assignment, 
                args=(updated_ticket, new_asignado),
                daemon=True
            ).start()
            threading.Thread(
                target=notify_specialist_assignment, 
                args=(new_asignado_norm, updated_ticket),
                daemon=True
            ).start()

    if "estado" in normalized_updates and updated_ticket:
        new_estado = str(updated_ticket.get("estado") or "").strip().lower()
        if old_estado and new_estado and old_estado != new_estado:
            if new_estado == "resuelto":
                threading.Thread(target=notify_client_resolution, args=(updated_ticket,), daemon=True).start()

            try:
                _send_ticket_status_update_to_notify_emails(
                    updated_ticket,
                    from_estado=old_estado,
                    to_estado=new_estado,
                    actor_id=actor_id,
                    motivo="cambio_estado_manual",
                )
            except Exception as status_mail_error:
                logger.warning(f"[update_ticket] aviso de estado por correo no crítico falló para ticket {ticket_id}: {status_mail_error}")

    return updated_ticket

def move_ticket_to_trash(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_manage_ticket_trash(ticket, actor_id, actor_role, "enviar tickets a papelera")
    if _ticket_is_trashed(ticket):
        return {"ok": True, "already_trashed": True, "ticket": ticket}

    prev_estado = str(ticket.get("estado") or "abierto").strip().lower() or "abierto"
    prev_subestado = normalize_subestado(ticket.get("subestado"), "recibido")
    prev_assignee = str(ticket.get("asignado_a") or "").strip() or None
    trash_reason = str(reason or "").strip()

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """UPDATE tickets
               SET is_trashed = TRUE,
                   trashed_at = ?,
                   trashed_by = ?,
                   trash_reason = ?,
                   trash_prev_estado = ?,
                   trash_prev_subestado = ?,
                   trash_prev_asignado_a = ?,
                   estado = 'cerrado',
                   subestado = 'cerrado',
                   updated_at = ?,
                   resolved_at = COALESCE(resolved_at, ?)
               WHERE id = ?""",
            (
                now,
                actor_id,
                trash_reason,
                prev_estado,
                prev_subestado,
                prev_assignee,
                now,
                now,
                ticket_id,
            ),
        )
        reason_suffix = f" | Motivo: {trash_reason}" if trash_reason else ""
        _emit_system_comment(
            conn,
            ticket_id,
            f"[PAPELERA] Ticket enviado a papelera por {actor_id}{reason_suffix}",
            now,
            author_id=actor_id,
        )
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    if prev_assignee and prev_estado not in {"resuelto", "cerrado"}:
        try:
            decrementar_carga(prev_assignee, specialty=ticket.get("categoria"))
        except Exception as e:
            logger.warning(f"[move_ticket_to_trash] Falló decrementar_carga para {prev_assignee}: {e}")

    return {"ok": True, "ticket": get_ticket(ticket_id)}

def restore_ticket_from_trash(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_manage_ticket_trash(ticket, actor_id, actor_role, "restaurar tickets desde papelera")
    if not _ticket_is_trashed(ticket):
        return {"ok": True, "already_restored": True, "ticket": ticket}

    prev_estado = str(ticket.get("trash_prev_estado") or "abierto").strip().lower() or "abierto"
    prev_assignee = str(ticket.get("trash_prev_asignado_a") or "").strip() or None
    prev_subestado_raw = ticket.get("trash_prev_subestado")
    if prev_estado == "en_progreso":
        fallback_subestado = "en_progreso"
    elif prev_estado == "resuelto":
        fallback_subestado = "resuelto"
    elif prev_estado == "cerrado":
        fallback_subestado = "cerrado"
    else:
        fallback_subestado = "asignado" if prev_assignee else "recibido"
    prev_subestado = normalize_subestado(prev_subestado_raw, fallback_subestado)

    if prev_estado not in ESTADOS_VALIDOS:
        prev_estado = "abierto"
    if prev_estado == "abierto" and prev_subestado in {"resuelto", "cerrado", "en_progreso"}:
        prev_subestado = "asignado" if prev_assignee else "recibido"
    elif prev_estado == "en_progreso" and prev_subestado in {"resuelto", "cerrado", "recibido"}:
        prev_subestado = "en_progreso"
    elif prev_estado == "resuelto":
        prev_subestado = "resuelto"
    elif prev_estado == "cerrado":
        prev_subestado = "cerrado"

    restored_estado = estado_from_subestado(prev_subestado, prev_estado)
    should_clear_resolved_at = restored_estado in {"abierto", "en_progreso"}

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """UPDATE tickets
               SET is_trashed = FALSE,
                   trashed_at = NULL,
                   trashed_by = NULL,
                   trash_reason = '',
                   estado = ?,
                   subestado = ?,
                   asignado_a = ?,
                   updated_at = ?,
                   resolved_at = CASE WHEN ? THEN NULL ELSE resolved_at END,
                   trash_prev_estado = NULL,
                   trash_prev_subestado = NULL,
                   trash_prev_asignado_a = NULL
               WHERE id = ?""",
            (
                restored_estado,
                prev_subestado,
                prev_assignee,
                now,
                should_clear_resolved_at,
                ticket_id,
            ),
        )
        _emit_system_comment(
            conn,
            ticket_id,
            f"[PAPELERA] Ticket restaurado por {actor_id} a estado {restored_estado}",
            now,
            author_id=actor_id,
        )
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    if prev_assignee and restored_estado not in {"resuelto", "cerrado"}:
        try:
            incrementar_carga(prev_assignee, specialty=ticket.get("categoria"))
        except Exception as e:
            logger.warning(f"[restore_ticket_from_trash] Falló incrementar_carga para {prev_assignee}: {e}")

    return {"ok": True, "ticket": get_ticket(ticket_id)}

def add_comment(
    ticket_id: int,
    user_id: str,
    content: str,
    event_type: str = "comentario",
    actor_role: str = "",
) -> Dict[str, Any]:
    """Agregar un comentario/evento al ticket."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "agregar notas")
    _ensure_can_participate_ticket(ticket, user_id, actor_role, "agregar notas")
    if _is_readonly_blocked_by_estado(ticket):
        raise ValueError("El ticket está CERRADO y no admite más notas.")

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        cursor = conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?) RETURNING id""",
            (ticket_id, user_id, f"[{event_type.upper()}] {content}", now)
        )
        row = cursor.fetchone()
        comment_id = row["id"] if row else None
        _maybe_mark_first_response(conn, ticket_id, user_id, now)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        conn.commit()

        row = conn.execute("SELECT * FROM ticket_comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def _get_active_email_draft_row(conn, ticket_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """SELECT *
           FROM ticket_email_drafts
           WHERE ticket_id = ? AND status = 'active'
           ORDER BY id DESC
           LIMIT 1""",
        (int(ticket_id),),
    ).fetchone()
    return dict(row) if row else None

def _list_email_draft_attachments(conn, draft_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, draft_id, filename, file_path, size_bytes, content_type, sha256,
                  uploaded_by, created_at, sent_email_id
           FROM ticket_email_draft_attachments
           WHERE draft_id = ?
           ORDER BY id ASC""",
        (int(draft_id),),
    ).fetchall()
    return [dict(r) for r in rows]

def _ensure_active_email_draft(conn, ticket: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    ticket_id = int(ticket.get("id") or 0)
    current = _get_active_email_draft_row(conn, ticket_id)
    if current:
        return current

    now = db.now_utc_iso()
    actor = str(actor_id or "").strip() or "system"
    to_addr = _extract_ticket_target_email(ticket)
    _, cc_emails, _, _ = _compose_reply_recipients(ticket, explicit_to=to_addr)
    subject = _build_ticket_reply_subject(ticket)
    try:
        row = conn.execute(
            """INSERT INTO ticket_email_drafts
               (ticket_id, status, to_addr, cc_addrs, bcc_addrs, subject, body_text, version,
                created_by, updated_by, created_at, updated_at)
               VALUES (?, 'active', ?, ?, '', ?, '', 1, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, to_addr, ", ".join(cc_emails), subject, actor, actor, now, now),
        ).fetchone()
    except Exception as e:
        msg = str(e).lower()
        if "idx_tk_email_drafts_active" in msg or "duplicate" in msg:
            existing = _get_active_email_draft_row(conn, ticket_id)
            if existing:
                return existing
        raise
    draft_id = int((row or {}).get("id") or 0)
    created = conn.execute(
        "SELECT * FROM ticket_email_drafts WHERE id = ?",
        (draft_id,),
    ).fetchone()
    if not created:
        raise ValueError("No fue posible crear borrador activo.")
    return dict(created)

def _serialize_email_draft(conn, draft: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    draft_id = int(draft.get("id") or 0)
    lock = _draft_lock_info(draft, actor_id)
    attachments_raw = _list_email_draft_attachments(conn, draft_id)
    attachments = [
        {
            "id": int(item.get("id") or 0),
            "draft_id": int(item.get("draft_id") or 0),
            "filename": str(item.get("filename") or ""),
            "size_bytes": int(item.get("size_bytes") or 0),
            "content_type": str(item.get("content_type") or "application/octet-stream"),
            "sha256": str(item.get("sha256") or ""),
            "uploaded_by": str(item.get("uploaded_by") or ""),
            "created_at": item.get("created_at"),
            "sent_email_id": item.get("sent_email_id"),
        }
        for item in attachments_raw
    ]
    out = {
        "id": draft_id,
        "ticket_id": int(draft.get("ticket_id") or 0),
        "status": str(draft.get("status") or "active"),
        "to_addr": str(draft.get("to_addr") or ""),
        "cc_addrs": str(draft.get("cc_addrs") or ""),
        "bcc_addrs": str(draft.get("bcc_addrs") or ""),
        "subject": str(draft.get("subject") or ""),
        "body_text": str(draft.get("body_text") or ""),
        "version": int(draft.get("version") or 1),
        "created_by": str(draft.get("created_by") or ""),
        "updated_by": str(draft.get("updated_by") or ""),
        "created_at": draft.get("created_at"),
        "updated_at": draft.get("updated_at"),
        "sent_by": draft.get("sent_by"),
        "sent_email_id": draft.get("sent_email_id"),
        "sent_at": draft.get("sent_at"),
        "attachments": attachments,
        "lock": lock,
    }
    return out

def _ensure_can_edit_email_draft(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: str,
    action_label: str,
) -> None:
    _ensure_can_participate_ticket(ticket, actor_id, actor_role, action_label)
    _ensure_reply_allowed_estado(ticket, action_label)

def _validate_draft_lock(
    draft: Dict[str, Any],
    actor_id: str,
    lock_token: str,
) -> None:
    pass

def _acquire_draft_lock(
    conn,
    draft: Dict[str, Any],
    actor_id: str,
    *,
    force: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    actor = str(actor_id or "").strip() or "system"
    now_iso = db.now_utc_iso()
    lock_info = _draft_lock_info(draft, actor)
    if lock_info["active"] and not lock_info["mine"] and not force:
        owner = lock_info.get("owner") or "otro usuario"
        raise ConflictError(f"El borrador está en edición por '{owner}'.")

    lock_token = _new_draft_lock_token()
    lock_hash = _hash_draft_lock_token(lock_token)
    lock_expires_at = _lock_expiry_iso(now_iso, EMAIL_DRAFT_LOCK_MINUTES)
    conn.execute(
        """UPDATE ticket_email_drafts
           SET lock_owner = ?, lock_token_hash = ?, lock_expires_at = ?,
               updated_by = ?, updated_at = ?
           WHERE id = ?""",
        (actor, lock_hash, lock_expires_at, actor, now_iso, int(draft["id"])),
    )
    row = conn.execute(
        "SELECT * FROM ticket_email_drafts WHERE id = ?",
        (int(draft["id"]),),
    ).fetchone()
    if not row:
        raise ValueError("No fue posible refrescar lock del borrador.")
    return lock_token, dict(row)

def _normalize_draft_to_email(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    _, parsed = parseaddr(raw)
    out = parsed.strip() if parsed else raw
    return out

def get_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")

    can_edit = True
    blocked_reason = ""
    try:
        _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "editar borrador de respuesta")
    except (PermissionError, ValueError) as e:
        can_edit = False
        blocked_reason = str(e)

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        draft_payload = _serialize_email_draft(conn, draft, actor_id)
        conn.commit()
        return {
            "ok": True,
            "ticket_id": int(ticket_id),
            "ticket_estado": str(ticket.get("estado") or ""),
            "can_edit": can_edit,
            "blocked_reason": blocked_reason,
            "draft": draft_payload,
            "lock_timeout_seconds": EMAIL_DRAFT_LOCK_MINUTES * 60,
            "heartbeat_seconds": EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS,
        }
    finally:
        conn.close()

def acquire_ticket_email_draft_lock(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
    *,
    force: bool = False,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "tomar control del borrador")

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        lock_token, locked_draft = _acquire_draft_lock(conn, draft, actor_id, force=bool(force))
        payload = _serialize_email_draft(conn, locked_draft, actor_id)
        conn.commit()
        return {
            "ok": True,
            "ticket_id": int(ticket_id),
            "lock_token": lock_token,
            "draft": payload,
            "lock_timeout_seconds": EMAIL_DRAFT_LOCK_MINUTES * 60,
            "heartbeat_seconds": EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS,
        }
    finally:
        conn.close()

def heartbeat_ticket_email_draft_lock(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "mantener control del borrador")

    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET lock_expires_at = ?, updated_at = ?, updated_by = ?
               WHERE id = ?""",
            (_lock_expiry_iso(now_iso, EMAIL_DRAFT_LOCK_MINUTES), now_iso, actor_id, int(draft["id"])),
        )
        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
        return {
            "ok": True,
            "ticket_id": int(ticket_id),
            "draft": payload,
            "heartbeat_seconds": EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS,
        }
    finally:
        conn.close()

def save_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    *,
    lock_token: str,
    version: int,
    to_addr: Optional[str] = None,
    cc_addrs: Optional[str] = None,
    bcc_addrs: Optional[str] = None,
    subject: Optional[str] = None,
    body_text: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "guardar borrador de respuesta")

    expected_version = int(version or 0)
    if expected_version <= 0:
        raise ValueError("La versión del borrador es obligatoria.")

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        _validate_draft_lock(draft, actor_id, lock_token)
        current_version = int(draft.get("version") or 1)
        if current_version != expected_version:
            raise ConflictError(
                f"El borrador cambió de versión ({current_version}). Recarga antes de guardar."
            )

        next_to_addr = _normalize_draft_to_email(to_addr) if to_addr is not None else str(draft.get("to_addr") or "")
        if next_to_addr and "@" not in next_to_addr:
            raise ValueError("Correo destino inválido para el borrador.")
        next_cc_raw = cc_addrs if cc_addrs is not None else str(draft.get("cc_addrs") or "")
        next_bcc_raw = bcc_addrs if bcc_addrs is not None else str(draft.get("bcc_addrs") or "")
        next_cc_list = _normalize_recipient_emails(next_cc_raw, label="CC")
        next_bcc_list = _normalize_recipient_emails(next_bcc_raw, label="CCO")
        if next_to_addr:
            next_cc_list = [email for email in next_cc_list if email != next_to_addr]
            next_bcc_list = [email for email in next_bcc_list if email != next_to_addr]
        cc_set = set(next_cc_list)
        next_bcc_list = [email for email in next_bcc_list if email not in cc_set]
        next_cc_addrs = ", ".join(next_cc_list)
        next_bcc_addrs = ", ".join(next_bcc_list)
        next_subject = str(subject if subject is not None else draft.get("subject") or "").strip()
        next_body = str(body_text if body_text is not None else draft.get("body_text") or "")

        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET to_addr = ?, cc_addrs = ?, bcc_addrs = ?, subject = ?, body_text = ?, version = ?,
                   updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (
                next_to_addr,
                next_cc_addrs,
                next_bcc_addrs,
                next_subject,
                next_body,
                current_version + 1,
                actor_id,
                now_iso,
                int(draft["id"]),
            ),
        )
        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
        return {"ok": True, "ticket_id": int(ticket_id), "draft": payload}
    finally:
        conn.close()

def upload_ticket_email_draft_attachments(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
    files: Optional[List[Any]],
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "subir adjuntos al borrador")

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        _validate_draft_lock(draft, actor_id, lock_token)
        if not files:
            payload = _serialize_email_draft(conn, draft, actor_id)
            conn.commit()
            return {"ok": True, "ticket_id": int(ticket_id), "uploaded": 0, "draft": payload}

        base_path = _drafts_base_path(ticket_id, int(draft["id"])).resolve()
        base_path.mkdir(parents=True, exist_ok=True)
        uploaded = 0
        for file in files:
            filename = str(getattr(file, "filename", "") or "").strip() or "untitled"
            ext = Path(filename).suffix.lower()
            if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                logger.warning(f"[draft_attachments] extensión no permitida: {filename}")
                continue

            file.file.seek(0, 2)
            size = int(file.file.tell())
            file.file.seek(0)
            if size > app_settings.TICKET_MAX_FILE_SIZE:
                logger.warning(f"[draft_attachments] tamaño excedido: {filename} ({size})")
                continue

            content = file.file.read()
            sha256 = hashlib.sha256(content).hexdigest()
            file_path = (base_path / _attachment_storage_name(filename)).resolve()
            if not _is_safe_attachment_path(file_path):
                logger.warning(f"[draft_attachments] ruta fuera de raíz permitida: {file_path}")
                continue

            with open(file_path, "wb") as fh:
                fh.write(content)

            conn.execute(
                """INSERT INTO ticket_email_draft_attachments
                   (draft_id, filename, file_path, size_bytes, content_type, sha256, uploaded_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(draft["id"]),
                    filename,
                    str(file_path),
                    len(content),
                    str(getattr(file, "content_type", "application/octet-stream") or "application/octet-stream"),
                    sha256,
                    actor_id,
                    db.now_utc_iso(),
                ),
            )
            uploaded += 1

        if uploaded > 0:
            now_iso = db.now_utc_iso()
            conn.execute(
                """UPDATE ticket_email_drafts
                   SET version = version + 1, updated_by = ?, updated_at = ?
                   WHERE id = ?""",
                (actor_id, now_iso, int(draft["id"])),
            )

        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
        return {"ok": True, "ticket_id": int(ticket_id), "uploaded": uploaded, "draft": payload}
    finally:
        conn.close()

def delete_ticket_email_draft_attachment(
    ticket_id: int,
    attachment_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "eliminar adjuntos del borrador")

    attachment_path = None
    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        row = conn.execute(
            """SELECT id, file_path
               FROM ticket_email_draft_attachments
               WHERE id = ? AND draft_id = ?
               LIMIT 1""",
            (int(attachment_id), int(draft["id"])),
        ).fetchone()
        if not row:
            raise ValueError("Adjunto de borrador no encontrado.")
        attachment_path = str(row.get("file_path") or "")
        conn.execute(
            "DELETE FROM ticket_email_draft_attachments WHERE id = ?",
            (int(attachment_id),),
        )
        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET version = version + 1, updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (actor_id, now_iso, int(draft["id"])),
        )
        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
    finally:
        conn.close()

    if attachment_path:
        try:
            path = Path(attachment_path).resolve()
            if _is_safe_attachment_path(path):
                path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"[delete_draft_attachment] no se pudo borrar archivo: {e}")

    return {"ok": True, "ticket_id": int(ticket_id), "draft": payload}

def discard_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "descartar borradores")
    _ensure_can_participate_ticket(ticket, actor_id, actor_role, "descartar borrador de respuesta")

    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            return {"ok": True, "ticket_id": int(ticket_id), "discarded": False}
        _validate_draft_lock(draft, actor_id, lock_token)
        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET status = 'discarded',
                   lock_owner = NULL,
                   lock_token_hash = NULL,
                   lock_expires_at = NULL,
                   updated_by = ?,
                   updated_at = ?
               WHERE id = ?""",
            (actor_id, now_iso, int(draft["id"])),
        )
        conn.commit()
        return {"ok": True, "ticket_id": int(ticket_id), "discarded": True}
    finally:
        conn.close()

def _build_ticket_reply_body_html(message_text: str) -> str:
    escaped_msg = html.escape(str(message_text or "").strip()).replace("\n", "<br>")
    return f"<p>{escaped_msg}</p>"

def _prepare_uploaded_reply_attachments(ticket_id: int, files: Optional[List[Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    email_attachments: List[Dict[str, Any]] = []
    stored_attachments: List[Dict[str, Any]] = []
    if not files:
        return email_attachments, stored_attachments

    base_root = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir())
    base_path = Path(base_root) / str(ticket_id) / "attachments"
    base_path.mkdir(parents=True, exist_ok=True)

    for file in files:
        try:
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
            if size > app_settings.TICKET_MAX_FILE_SIZE:
                logger.warning(f"File {file.filename} exceeds max size")
                continue

            filename = getattr(file, "filename", "untitled")
            ext = Path(filename).suffix.lower()
            if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                logger.warning(f"File extension {ext} not allowed")
                continue

            file_content = file.file.read()
            file_path = base_path / _attachment_storage_name(filename)
            if not _is_safe_attachment_path(file_path):
                logger.warning(f"[reply_email] ruta de adjunto fuera de raíz permitida: {file_path}")
                continue

            with open(file_path, "wb") as fh:
                fh.write(file_content)

            sha256 = hashlib.sha256(file_content).hexdigest()
            content_type = getattr(file, "content_type", "application/octet-stream")
            email_attachments.append(
                {
                    "filename": filename,
                    "data": file_content,
                    "content_type": content_type,
                }
            )
            stored_attachments.append(
                {
                    "filename": filename,
                    "path": str(file_path),
                    "size": len(file_content),
                    "content_type": content_type,
                    "sha256": sha256,
                }
            )
        except Exception as e:
            logger.error(f"Error procesando adjunto {getattr(file, 'filename', '?')}: {e}")

    return email_attachments, stored_attachments

def _send_ticket_reply_email(
    *,
    ticket: Dict[str, Any],
    author_id: str,
    clean_msg: str,
    to_email: str,
    cc_emails: List[str],
    bcc_emails: List[str],
    to_addr_record: str,
    email_attachments: Optional[List[Dict[str, Any]]] = None,
    stored_attachments: Optional[List[Dict[str, Any]]] = None,
    idempotency_key: Optional[str] = None,
    artifact_ref: Optional[str] = None,
    evidence_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from ._email import _build_ticket_thread_headers, _update_ticket_thread_metadata  # noqa: PLC0415
    ticket_id = int(ticket.get("id") or 0)
    clean_msg = str(clean_msg or "").strip()
    if not clean_msg:
        raise ValueError("El mensaje de respuesta está vacío")
    if not to_email or "@" not in str(to_email):
        raise ValueError("Este ticket no tiene un correo de cliente válido")

    subject = _build_ticket_reply_subject(ticket)
    headers = _build_ticket_thread_headers(ticket)
    threaded = bool(headers.get("In-Reply-To") or headers.get("References"))
    body_html = _build_ticket_reply_body_html(clean_msg)
    now = db.now_utc_iso()
    preview = clean_msg if len(clean_msg) <= 300 else clean_msg[:300] + "..."
    normalized_idempotency_key = (idempotency_key or "").strip()[:128] or None
    email_attachments = list(email_attachments or [])
    stored_attachments = list(stored_attachments or [])

    dedupe_since = (
        datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(minutes=3)
    ).isoformat()
    marker_id = None

    lock_conn = db.get_conn()
    try:
        try:
            lock_conn.execute("SELECT pg_advisory_lock(?)", (ticket_id,))
        except Exception:
            pass

        if normalized_idempotency_key:
            idem_row = lock_conn.execute(
                """SELECT id, direction FROM ticket_emails
                   WHERE ticket_id = ?
                     AND direction IN ('outgoing', 'outgoing_pending')
                     AND idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (ticket_id, normalized_idempotency_key),
            ).fetchone()
            if idem_row:
                for att in stored_attachments:
                    try:
                        Path(att["path"]).unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup duplicate file {att['path']}: {e}")
                return {
                    "ok": True,
                    "ticket_id": ticket_id,
                    "to_email": to_email,
                    "cc_emails": cc_emails,
                    "bcc_emails": bcc_emails,
                    "subject": subject,
                    "threaded": threaded,
                    "duplicate_skipped": True,
                    "message": "Se evitó un envío duplicado (Idempotency-Key ya procesado).",
                    "sent_email_id": int(idem_row.get("id") or 0),
                    "email_direction": str(idem_row.get("direction") or ""),
                }

        dup_row = lock_conn.execute(
            """SELECT id, direction FROM ticket_emails
               WHERE ticket_id = ?
                 AND direction IN ('outgoing', 'outgoing_pending')
                 AND to_addr = ?
                 AND subject = ?
                 AND body_html = ?
                 AND created_at >= ?
               ORDER BY id DESC
               LIMIT 1""",
            (ticket_id, to_addr_record or to_email, subject, body_html, dedupe_since),
        ).fetchone()
        if dup_row:
            for att in stored_attachments:
                try:
                    Path(att["path"]).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup duplicate file {att['path']}: {e}")
            return {
                "ok": True,
                "ticket_id": ticket_id,
                "to_email": to_email,
                "cc_emails": cc_emails,
                "bcc_emails": bcc_emails,
                "subject": subject,
                "threaded": threaded,
                "duplicate_skipped": True,
                "message": "Se evitó un envío duplicado (correo ya enviado recientemente).",
                "sent_email_id": int(dup_row.get("id") or 0),
                "email_direction": str(dup_row.get("direction") or ""),
            }

        marker_row = lock_conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
               VALUES (?, 'outgoing_pending', '', ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                ticket_id,
                to_addr_record or to_email,
                ", ".join(cc_emails),
                ", ".join(bcc_emails),
                subject,
                body_html,
                json.dumps(stored_attachments),
                normalized_idempotency_key,
                now,
            ),
        ).fetchone()
        marker_id = int((marker_row or {}).get("id") or 0)
        lock_conn.commit()
    finally:
        try:
            lock_conn.execute("SELECT pg_advisory_unlock(?)", (ticket_id,))
        except Exception:
            pass
        lock_conn.close()

    try:
        send_meta = email_sender.send_email_advanced(
            to_email=to_email,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            html_body=body_html,
            headers=headers or None,
            attachments=email_attachments,
        )
    except Exception as e:
        if marker_id:
            cleanup_conn = db.get_conn()
            try:
                cleanup_conn.execute(
                    "DELETE FROM ticket_emails WHERE id = ? AND direction = 'outgoing_pending'",
                    (marker_id,),
                )
                cleanup_conn.commit()
            finally:
                cleanup_conn.close()
        for att in stored_attachments:
            try:
                Path(att["path"]).unlink(missing_ok=True)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup attachment file on send error {att['path']}: {cleanup_error}")
        raise ValueError(str(e))

    conn = db.get_conn()
    try:
        email_id = marker_id
        if marker_id:
            conn.execute(
                """UPDATE ticket_emails
                   SET direction = 'outgoing', from_addr = ?, to_addr = ?, cc_addrs = ?, bcc_addrs = ?
                   WHERE id = ?""",
                (
                    send_meta.get("from_addr"),
                    to_addr_record or to_email,
                    ", ".join(cc_emails),
                    ", ".join(bcc_emails),
                    marker_id,
                ),
            )
        else:
            email_row = conn.execute(
                """INSERT INTO ticket_emails
                   (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    ticket_id,
                    "outgoing",
                    send_meta.get("from_addr"),
                    to_addr_record or to_email,
                    ", ".join(cc_emails),
                    ", ".join(bcc_emails),
                    subject,
                    body_html,
                    json.dumps(stored_attachments),
                    normalized_idempotency_key,
                    now,
                ),
            ).fetchone()
            email_id = int((email_row or {}).get("id") or 0)

        updated_stored_attachments = []
        for att in stored_attachments:
            inserted = conn.execute(
                """INSERT INTO ticket_attachments
                   (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (
                    ticket_id,
                    str(att.get("filename") or "attachment.bin"),
                    str(att.get("path") or ""),
                    author_id,
                    now,
                    int(att.get("size") or 0),
                    str(att.get("content_type") or "application/octet-stream"),
                    str(att.get("sha256") or ""),
                ),
            ).fetchone()
            att_id = int((inserted or {}).get("id") or 0)
            new_att = dict(att)
            new_att["id"] = att_id
            new_att["attachment_id"] = att_id
            updated_stored_attachments.append(new_att)

        if updated_stored_attachments:
            conn.execute(
                "UPDATE ticket_emails SET attachments_json = ? WHERE id = ?",
                (json.dumps(updated_stored_attachments), email_id)
            )

        has_attachments = " (con adjuntos)" if stored_attachments else ""
        cc_hint = f" + CC: {', '.join(cc_emails)}" if cc_emails else ""
        bcc_hint = f" + CCO: {', '.join(bcc_emails)}" if bcc_emails else ""
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                ticket_id,
                author_id,
                f"[CORREO] Respuesta enviada a {to_email}{cc_hint}{bcc_hint}{has_attachments}: {preview}",
                now,
            ),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        _maybe_mark_first_response(conn, ticket_id, author_id, now)
        _update_ticket_thread_metadata(
            conn,
            ticket_id,
            message_id=send_meta.get("message_id"),
            in_reply_to=headers.get("In-Reply-To"),
            references=headers.get("References"),
        )
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.8.16",
            artifact_ref=artifact_ref or f"ticket:{ticket_id}:email_reply",
            owner=author_id,
            integrity_hash=send_meta.get("message_id") or "",
            metadata={
                "to": to_email,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "threaded": threaded,
                "has_attachments": bool(stored_attachments),
                "idempotency_key": normalized_idempotency_key or "",
                **(evidence_metadata or {}),
            },
        )
    except Exception as e:
        logger.warning(f"[_send_ticket_reply_email] evidence_event no crítico falló para ticket {ticket_id}: {e}")

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "to_email": to_email,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": subject,
        "threaded": threaded,
        "message_id": send_meta.get("message_id"),
        "idempotency_key": normalized_idempotency_key,
        "sent_email_id": int(email_id or 0),
        "body_html": body_html,
        "duplicate_skipped": False,
    }

def send_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    *,
    lock_token: str,
    version: int,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "enviar respuesta al cliente")

    expected_version = int(version or 0)
    if expected_version <= 0:
        raise ValueError("La versión del borrador es obligatoria para enviar.")

    draft_id = 0
    current_version = 0
    to_email = ""
    cc_emails: List[str] = []
    bcc_emails: List[str] = []
    to_addr_record = ""
    clean_msg = ""
    email_attachments: List[Dict[str, Any]] = []
    stored_attachments: List[Dict[str, Any]] = []
    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        draft_id = int(draft.get("id") or 0)
        current_version = int(draft.get("version") or 1)
        if current_version != expected_version:
            raise ConflictError(
                f"El borrador cambió de versión ({current_version}). Recarga antes de enviar."
            )

        to_email, cc_emails, bcc_emails, to_addr_record = _compose_reply_recipients(
            ticket,
            explicit_to=_normalize_draft_to_email(draft.get("to_addr")) or _extract_ticket_target_email(ticket),
            explicit_cc=draft.get("cc_addrs"),
            explicit_bcc=draft.get("bcc_addrs"),
        )
        if not to_email or "@" not in to_email:
            raise ValueError("Este ticket no tiene un correo de cliente válido")

        body_text = str(draft.get("body_text") or "")
        clean_msg = body_text.strip()
        if not clean_msg:
            raise ValueError("El borrador está vacío. Agrega un mensaje antes de enviar.")

        draft_attachments = _list_email_draft_attachments(conn, draft_id)
        for item in draft_attachments:
            raw_path = str(item.get("file_path") or "").strip()
            path = Path(raw_path).resolve() if raw_path else None
            if not path or not _is_safe_attachment_path(path):
                raise ValueError(f"Adjunto de borrador inválido: {item.get('filename')}")
            if not path.exists() or not path.is_file():
                raise ValueError(f"Adjunto no disponible: {item.get('filename')}")
            content = path.read_bytes()
            email_attachments.append(
                {
                    "filename": str(item.get("filename") or "attachment.bin"),
                    "data": content,
                    "content_type": str(item.get("content_type") or "application/octet-stream"),
                }
            )
            stored_attachments.append(
                {
                    "id": int(item.get("id") or 0),
                    "filename": str(item.get("filename") or "attachment.bin"),
                    "path": str(path),
                    "size": int(item.get("size_bytes") or len(content)),
                    "content_type": str(item.get("content_type") or "application/octet-stream"),
                    "sha256": str(item.get("sha256") or hashlib.sha256(content).hexdigest()),
                }
            )
    finally:
        conn.close()

    send_result = _send_ticket_reply_email(
        ticket=ticket,
        author_id=actor_id,
        clean_msg=clean_msg,
        to_email=to_email,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        to_addr_record=to_addr_record,
        email_attachments=email_attachments,
        stored_attachments=stored_attachments,
        idempotency_key=f"draft:{draft_id}:v{current_version}",
        artifact_ref=f"ticket:{ticket_id}:email_reply_draft",
        evidence_metadata={
            "draft_id": draft_id,
            "version": current_version,
        },
    )
    email_id = int(send_result.get("sent_email_id") or 0)
    email_direction = str(send_result.get("email_direction") or "outgoing").strip().lower()
    should_mark_sent = (not send_result.get("duplicate_skipped")) or email_direction == "outgoing"
    draft_status = "active"

    if should_mark_sent and email_id > 0:
        now = db.now_utc_iso()
        conn = db.get_conn()
        try:
            conn.execute(
                """UPDATE ticket_email_draft_attachments
                   SET sent_email_id = ?
                   WHERE draft_id = ? AND sent_email_id IS NULL""",
                (email_id, draft_id),
            )
            conn.execute(
                """UPDATE ticket_email_drafts
                   SET status = 'sent',
                       sent_by = ?,
                       sent_email_id = ?,
                       sent_at = ?,
                       lock_owner = NULL,
                       lock_token_hash = NULL,
                       lock_expires_at = NULL,
                       updated_by = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (actor_id, email_id, now, actor_id, now, draft_id),
            )
            conn.commit()
            draft_status = "sent"
        finally:
            conn.close()

    return {
        "ok": True,
        "ticket_id": int(ticket_id),
        "to_email": to_email,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": send_result.get("subject"),
        "threaded": bool(send_result.get("threaded")),
        "message_id": send_result.get("message_id"),
        "sent_email_id": email_id,
        "draft_status": draft_status,
        "ticket": get_ticket(ticket_id),
    }

def get_dashboard_kpi() -> Dict[str, Any]:
    """
    Retorna KPIs para el Dashboard V3:
    1. Top Clientes (por volumen de tickets abiertos)
    2. Correos pendientes de respuesta (auto-replyable)
    """
    conn = db.get_conn()
    try:
        # 1. Top Clientes
        rows = conn.execute(
            """
            SELECT 
                COALESCE(customer_id, 'Sin Cliente') as cliente,
                COUNT(*) as total
            FROM tickets 
            WHERE estado IN ('abierto', 'en_progreso')
              AND COALESCE(is_trashed, FALSE) = FALSE
            GROUP BY customer_id
            ORDER BY total DESC
            LIMIT 5
            """
        ).fetchall()
        top_clientes = [{"cliente": r["cliente"], "total": r["total"]} for r in rows]

        # 2. Correos Pendientes (Threads que requieren respuesta)
        # Lógica simplificada: Tickets abiertos con origen_email y sin respuesta reciente del agente?
        # Por ahora, listamos tickets recientes creados por correo
        rows_emails = conn.execute(
            """
            SELECT id, titulo, origen_email, created_at, customer_id
            FROM tickets
            WHERE origen_email IS NOT NULL 
              AND estado = 'abierto'
              AND COALESCE(is_trashed, FALSE) = FALSE
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
        pending_emails = [dict(r) for r in rows_emails]

        return {
            "top_clientes": top_clientes,
            "pending_emails": pending_emails
        }
    finally:
        conn.close()

def _gerencia_username(conn) -> Optional[str]:
    """Usuario activo con rol gerencia, para auto-asignar los 'pendiente_gerencia'.
    Dinámico: si mañana cambia la persona del rol, no hay que tocar código."""
    try:
        row = conn.execute(
            "SELECT username FROM users WHERE role = 'gerencia' AND COALESCE(is_active, 1) = 1 "
            "ORDER BY username ASC LIMIT 1"
        ).fetchone()
    except Exception:
        return None
    return str(row["username"]) if row and row["username"] else None


def transition_ticket(
    ticket_id: int,
    to_subestado: str,
    actor_id: str,
    actor_role: str = "",
    motivo: str = "",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "cambiar estado")
    _ensure_can_manage_ticket(ticket, actor_id, actor_role, "cambiar estado")
    old_estado = str(ticket.get("estado") or "").strip().lower()

    tipo = normalize_ticket_type(ticket.get("tipo"))
    from_sub = normalize_subestado(ticket.get("subestado"), "recibido")
    target_sub = _normalize_transition_target(from_sub, to_subestado)
    normalized_idem = (idempotency_key or "").strip()[:128] or None

    if target_sub in SUBESTADOS_ESPERA and not _is_estado_en_progreso(ticket.get("estado")):
        raise ValueError("Los subestados de espera solo se permiten cuando el ticket está en estado 'en_progreso'.")

    if target_sub == from_sub:
        if normalized_idem:
            conn = db.get_conn()
            try:
                idem_row = conn.execute(
                    """SELECT id FROM ticket_transitions
                       WHERE ticket_id = ? AND idempotency_key = ?
                       ORDER BY id DESC
                       LIMIT 1""",
                    (ticket_id, normalized_idem),
                ).fetchone()
            finally:
                conn.close()
            if idem_row:
                return {
                    "ok": True,
                    "duplicate_skipped": True,
                    "message": "Se evitó transición duplicada por Idempotency-Key.",
                    "ticket": get_ticket(ticket_id),
                }
        return {"ok": True, "ticket": ticket, "unchanged": True}

    if not _workflow_can_transition(tipo, from_sub, target_sub):
        raise ValueError(f"Transición inválida para tipo '{tipo}': {from_sub} -> {target_sub}")

    result_ticket: Optional[Dict[str, Any]] = None
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        if normalized_idem:
            idem_row = conn.execute(
                """SELECT id FROM ticket_transitions
                   WHERE ticket_id = ? AND idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (ticket_id, normalized_idem),
            ).fetchone()
            if idem_row:
                return {
                    "ok": True,
                    "duplicate_skipped": True,
                    "message": "Se evitó transición duplicada por Idempotency-Key.",
                    "ticket": get_ticket(ticket_id),
                }

        if tipo == "cambio":
            approvals = _latest_approval_decisions(conn, ticket_id)
            if target_sub in {"pendiente_aprobacion_2", "aprobado", "en_ejecucion"} and approvals.get(1) != "approved":
                raise ValueError("El cambio requiere aprobación de paso 1 antes de continuar.")
            if target_sub in {"aprobado", "en_ejecucion"} and approvals.get(2) != "approved":
                raise ValueError("El cambio requiere aprobación de paso 2 antes de ejecutar.")

        new_estado = estado_from_subestado(target_sub, str(ticket.get("estado") or "abierto"))
        reopen_to_progress = (
            target_sub in {"en_progreso", "asignado"}
            and from_sub in {"cerrado", "resuelto", "reabierto"}
        )
        conn.execute(
            """UPDATE tickets
               SET subestado = ?, estado = ?, updated_at = ?,
                   resolved_at = CASE
                       WHEN ? IN ('resuelto','cerrado') THEN COALESCE(resolved_at, ?)
                       WHEN ? THEN NULL
                       WHEN ? = 'reabierto' THEN NULL
                       ELSE resolved_at
                   END
               WHERE id = ?""",
            (target_sub, new_estado, now, new_estado, now, reopen_to_progress, target_sub, ticket_id),
        )

        transition_row = conn.execute(
            """INSERT INTO ticket_transitions
               (ticket_id, from_subestado, to_subestado, actor, reason, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, from_sub, target_sub, actor_id, (motivo or "").strip(), normalized_idem, now),
        ).fetchone()

        _emit_system_comment(
            conn,
            ticket_id,
            f"[TRANSICION] {from_sub} -> {target_sub}" + (f" | Motivo: {motivo}" if motivo else ""),
            now,
            author_id=actor_id,
        )
        # Pendiente Gerencia: auto-asignar al gerente (rol gerencia) para que le aparezca
        # como pendiente de su aprobación. Guardamos el asignado previo para restaurarlo
        # cuando gerencia decida (ver gerencia_decision).
        if target_sub == "pendiente_gerencia":
            _ger_user = _gerencia_username(conn)
            if _ger_user and _ger_user != ticket.get("asignado_a"):
                _prev = (ticket.get("asignado_a") or "").strip()
                conn.execute(
                    "UPDATE tickets SET asignado_a = ?, updated_at = ? WHERE id = ?",
                    (_ger_user, now, ticket_id),
                )
                _emit_system_comment(
                    conn,
                    ticket_id,
                    f"[GERENCIA] En aprobación de {_ger_user}. Asignado previo: {_prev}",
                    now,
                    author_id=actor_id,
                )
        if target_sub in {"resuelto", "cerrado"} and ticket.get("asignado_a"):
            decrementar_carga(str(ticket["asignado_a"]), specialty=ticket.get("categoria"))
        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        result_ticket = get_ticket(ticket_id)
    finally:
        conn.close()

    if result_ticket:
        new_estado = str(result_ticket.get("estado") or "").strip().lower()
        if old_estado and new_estado and old_estado != new_estado:
            if new_estado == "resuelto":
                threading.Thread(target=notify_client_resolution, args=(result_ticket,), daemon=True).start()

            try:
                _send_ticket_status_update_to_notify_emails(
                    result_ticket,
                    from_estado=old_estado,
                    to_estado=new_estado,
                    actor_id=actor_id,
                    motivo=motivo,
                )
            except Exception as status_mail_error:
                logger.warning(f"[transition_ticket] aviso de estado por correo no crítico falló para ticket {ticket_id}: {status_mail_error}")

    return {
        "ok": True,
        "transition_id": int(transition_row["id"]) if transition_row else None,
        "ticket": result_ticket or get_ticket(ticket_id),
    }

def approve_ticket_change(
    ticket_id: int,
    step: int,
    decision: str,
    approver: str,
    approver_role: str,
    decision_note: str = "",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "aprobar cambios")
    if normalize_ticket_type(ticket.get("tipo")) != "cambio":
        raise ValueError("Las aprobaciones aplican solo a tickets de tipo 'cambio'.")

    step = int(step or 0)
    if step not in {1, 2}:
        raise ValueError("El paso de aprobación debe ser 1 o 2.")

    decision_norm = str(decision or "").strip().lower()
    if decision_norm not in {"approved", "rejected"}:
        raise ValueError("La decisión debe ser 'approved' o 'rejected'.")

    role_values = _normalize_roles(approver_role)
    step1_roles = {"admin", "implementaciones", "redes", "sistemas", "ops"}
    step2_roles = {"admin", "finance", "gerencia"}
    allowed_roles = step1_roles if step == 1 else step2_roles
    if not any(role in allowed_roles for role in role_values):
        role_label = ", ".join(role_values) if role_values else str(approver_role or "-")
        raise ValueError(f"El/los rol(es) '{role_label}' no están autorizados para aprobar paso {step}.")

    normalized_idem = (idempotency_key or "").strip()[:128] or None
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        if normalized_idem:
            idem_row = conn.execute(
                """SELECT id FROM ticket_approvals
                   WHERE ticket_id = ? AND idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (ticket_id, normalized_idem),
            ).fetchone()
            if idem_row:
                return {
                    "ok": True,
                    "duplicate_skipped": True,
                    "message": "Se evitó aprobación duplicada por Idempotency-Key.",
                    "ticket": get_ticket(ticket_id),
                }

        current_sub = normalize_subestado(ticket.get("subestado"), "recibido")
        if step == 1 and current_sub != "pendiente_aprobacion_1":
            raise ValueError("Paso 1 solo permitido cuando el cambio está en 'pendiente_aprobacion_1'.")
        if step == 2 and current_sub != "pendiente_aprobacion_2":
            raise ValueError("Paso 2 solo permitido cuando el cambio está en 'pendiente_aprobacion_2'.")

        approval_row = conn.execute(
            """INSERT INTO ticket_approvals
               (ticket_id, step, approver, decision, decision_note, idempotency_key, decided_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                ticket_id,
                step,
                approver,
                decision_norm,
                (decision_note or "").strip(),
                normalized_idem,
                now,
            ),
        ).fetchone()

        _emit_system_comment(
            conn,
            ticket_id,
            f"[APROBACION] Paso {step}: {decision_norm} por {approver}",
            now,
            author_id=approver,
        )

        to_subestado = None
        if decision_norm == "approved":
            to_subestado = "pendiente_aprobacion_2" if step == 1 else "aprobado"
        else:
            to_subestado = "rechazado"

        if to_subestado:
            new_estado = estado_from_subestado(to_subestado, str(ticket.get("estado") or "abierto"))
            conn.execute(
                "UPDATE tickets SET subestado = ?, estado = ?, updated_at = ? WHERE id = ?",
                (to_subestado, new_estado, now, ticket_id),
            )
            conn.execute(
                """INSERT INTO ticket_transitions
                   (ticket_id, from_subestado, to_subestado, actor, reason, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    current_sub,
                    to_subestado,
                    approver,
                    f"approval_step_{step}_{decision_norm}",
                    normalized_idem,
                    now,
                ),
            )

        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        return {
            "ok": True,
            "approval_id": int(approval_row["id"]) if approval_row else None,
            "ticket": get_ticket(ticket_id),
        }
    finally:
        conn.close()

def gerencia_decision(ticket_id: int, decision: str, note: str, actor_id: str, actor_roles) -> Dict[str, Any]:
    """Aprueba o rechaza un ticket que está en 'pendiente_gerencia' (rol gerencia/admin).
    Registra la decisión + nota como comentario y devuelve el ticket a en_progreso."""
    roles = {str(r).strip().lower() for r in (actor_roles or [])}
    if not (roles & {"gerencia", "admin"}):
        raise PermissionError("Solo gerencia o admin pueden aprobar/rechazar.")
    dec = (decision or "").strip().lower()
    if dec not in {"aprobado", "rechazado"}:
        raise ValueError("decision debe ser 'aprobado' o 'rechazado'.")
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT subestado FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not row:
            raise ValueError("Ticket no encontrado.")
        if normalize_subestado(row["subestado"]) != "pendiente_gerencia":
            raise ValueError("El ticket no está en 'Pendiente Gerencia'.")
        now_iso = db.now_utc_iso()
        verbo = "APROBÓ" if dec == "aprobado" else "RECHAZÓ"
        nota_txt = f" Nota: {note.strip()}" if (note or "").strip() else ""
        _emit_system_comment(
            conn, ticket_id, f"[GERENCIA] {actor_id} {verbo} el requerimiento.{nota_txt}", now_iso, author_id=actor_id
        )
        # Restaurar al técnico que tenía el ticket antes de mandarlo a aprobación de gerencia.
        prev_row = conn.execute(
            "SELECT content FROM ticket_comments WHERE ticket_id = ? "
            "AND content LIKE ? ORDER BY id DESC LIMIT 1",
            (ticket_id, "[GERENCIA] En aprobación%"),
        ).fetchone()
        prev_assignee = None
        marker_found = False
        if prev_row and prev_row["content"]:
            marker = "Asignado previo:"
            txt = str(prev_row["content"])
            if marker in txt:
                marker_found = True
                prev_assignee = txt.split(marker, 1)[1].strip() or None
        if marker_found:
            # Sabemos quién lo tenía: restauramos (prev_assignee None = estaba sin asignar).
            conn.execute(
                "UPDATE tickets SET subestado = 'en_progreso', estado = 'en_progreso', "
                "asignado_a = ?, updated_at = ? WHERE id = ?",
                (prev_assignee, now_iso, ticket_id),
            )
        else:
            # No hay marker (entró a pendiente_gerencia por otra vía): NO tocar asignado_a
            # para no dejar el ticket huérfano; solo devolver a en_progreso.
            conn.execute(
                "UPDATE tickets SET subestado = 'en_progreso', estado = 'en_progreso', "
                "updated_at = ? WHERE id = ?",
                (now_iso, ticket_id),
            )
        if prev_assignee:
            _emit_system_comment(
                conn, ticket_id, f"[GERENCIA] Devuelto a {prev_assignee} tras la decisión.", now_iso, author_id=actor_id
            )
        conn.commit()
        return {"ok": True, "decision": dec, "estado": "en_progreso", "subestado": "en_progreso", "ticket": get_ticket(ticket_id)}
    finally:
        conn.close()


def list_ticket_approvals(ticket_id: int) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id, ticket_id, step, approver, decision, decision_note, decided_at
               FROM ticket_approvals
               WHERE ticket_id = ?
               ORDER BY decided_at DESC, id DESC""",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_ticket_workflow(ticket_id: int) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")

    conn = db.get_conn()
    try:
        transitions = conn.execute(
            """SELECT id, ticket_id, from_subestado, to_subestado, actor, reason, created_at
               FROM ticket_transitions
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC""",
            (ticket_id,),
        ).fetchall()
        approvals = conn.execute(
            """SELECT id, ticket_id, step, approver, decision, decision_note, decided_at
               FROM ticket_approvals
               WHERE ticket_id = ?
               ORDER BY decided_at DESC, id DESC""",
            (ticket_id,),
        ).fetchall()
        latest_approvals = _latest_approval_decisions(conn, ticket_id)
    finally:
        conn.close()

    tipo = normalize_ticket_type(ticket.get("tipo"))
    sub = normalize_subestado(ticket.get("subestado"), "recibido")
    allowed_next: List[str] = []
    if not _ticket_is_trashed(ticket):
        allowed_next = _workflow_next(tipo, sub)
        allowed_next = _filter_waiting_subestados(allowed_next, ticket.get("estado"))
    if tipo == "cambio" and not _ticket_is_trashed(ticket):
        if latest_approvals.get(1) != "approved":
            allowed_next = [s for s in allowed_next if s not in {"pendiente_aprobacion_2", "aprobado", "en_ejecucion"}]
        if latest_approvals.get(2) != "approved":
            allowed_next = [s for s in allowed_next if s not in {"aprobado", "en_ejecucion"}]

    return {
        "ticket": ticket,
        "allowed_next": allowed_next,
        "resuelto_auto_close_hours": RESUELTO_AUTO_CLOSE_HOURS,
        "approvals_status": {
            "step1": latest_approvals.get(1, "pending"),
            "step2": latest_approvals.get(2, "pending"),
        },
        "transitions": [dict(r) for r in transitions],
        "approvals": [dict(r) for r in approvals],
    }

def reply_ticket_email(
    ticket_id: int,
    author_id: str,
    mensaje: str,
    author_role: str = "",
    asunto: Optional[str] = None,
    to_addr: Optional[str] = None,
    cc_addrs: Optional[Any] = None,
    bcc_addrs: Optional[Any] = None,
    files: Optional[List[Any]] = None,  # List[UploadFile]
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envía respuesta por correo desde un ticket y mantiene hilo cuando existe email_thread_id.
    Registra historial en ticket_emails y evento en timeline.
    Soporta adjuntos.
    """
    ticket = get_ticket(ticket_id)
    if not ticket:
        logger.error(f"Reply failed: Ticket {ticket_id} not found")
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "responder correos")
    _ensure_can_participate_ticket(ticket, author_id, author_role, "responder correos")
    _ensure_reply_allowed_estado(ticket, "responder correos")

    clean_msg = (mensaje or "").strip()
    if not clean_msg:
        logger.error(f"Reply failed: Message empty for ticket {ticket_id}")
        raise ValueError("El mensaje de respuesta está vacío")

    to_email, cc_emails, bcc_emails, to_addr_record = _compose_reply_recipients(
        ticket,
        explicit_to=to_addr,
        explicit_cc=cc_addrs,
        explicit_bcc=bcc_addrs,
    )
    if not to_email or "@" not in to_email:
        logger.error(f"Reply failed: Invalid to_email '{to_email}' for ticket {ticket_id}")
        raise ValueError("Este ticket no tiene un correo de cliente válido")
    email_attachments, stored_attachments = _prepare_uploaded_reply_attachments(ticket_id, files)
    return _send_ticket_reply_email(
        ticket=ticket,
        author_id=author_id,
        clean_msg=clean_msg,
        to_email=to_email,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        to_addr_record=to_addr_record,
        email_attachments=email_attachments,
        stored_attachments=stored_attachments,
        idempotency_key=idempotency_key,
    )

def _html_to_text(raw_html: str) -> str:
    text = raw_html or ""
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()

def _parse_attachments_json(raw_value: Any) -> List[Dict[str, Any]]:
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return raw_value
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []

def _normalize_incoming_email_content_id(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if value.lower().startswith("cid:"):
        value = value[4:]
    return value.strip().strip("<>").strip().lower()

def _sanitize_incoming_email_numeric_attr(raw_value: Any, *, allow_percent: bool = False) -> Optional[str]:
    value = str(raw_value or "").strip()
    if not value:
        return None
    pattern = r"^\d{1,4}%?$" if allow_percent else r"^\d{1,4}$"
    if not re.match(pattern, value):
        return None
    if not allow_percent and value.endswith("%"):
        return None
    return value

def _sanitize_incoming_email_url(
    raw_value: Any,
    *,
    allow_cid: bool = False,
    allow_data_image: bool = False,
    allow_http: bool = False,
    allow_mailto: bool = False,
    allow_tel: bool = False,
) -> Optional[str]:
    value = html.unescape(str(raw_value or "").strip())
    if not value:
        return None
    lowered = value.lower()
    if allow_cid and lowered.startswith("cid:"):
        normalized_cid = _normalize_incoming_email_content_id(value)
        return f"cid:{normalized_cid}" if normalized_cid else None
    if allow_data_image and lowered.startswith("data:image/"):
        return value
    if lowered.startswith("//"):
        return None

    parsed = urlparse.urlsplit(value)
    scheme = parsed.scheme.lower()
    if not scheme:
        if value.startswith("#"):
            return value
        return value
    if scheme in {"http", "https"}:
        return value if allow_http else None
    if scheme == "mailto":
        return value if allow_mailto else None
    if scheme == "tel":
        return value if allow_tel else None
    return None

def _sanitize_incoming_email_attr(tag: str, name: str, raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    if name == "href":
        return _sanitize_incoming_email_url(
            value,
            allow_http=True,
            allow_mailto=True,
            allow_tel=True,
        )
    if name == "src":
        return _sanitize_incoming_email_url(
            value,
            allow_cid=True,
            allow_data_image=True,
            allow_http=False,
        )
    if name in {"width", "height"}:
        return _sanitize_incoming_email_numeric_attr(value, allow_percent=True)
    if name in {"border", "cellpadding", "cellspacing", "colspan", "rowspan"}:
        return _sanitize_incoming_email_numeric_attr(value, allow_percent=False)
    if name in {"align", "valign", "dir"}:
        normalized = value.lower()
        allowed_values = {
            "align": {"left", "center", "right", "justify"},
            "valign": {"top", "middle", "bottom"},
            "dir": {"ltr", "rtl", "auto"},
        }
        return normalized if normalized in allowed_values.get(name, set()) else None
    return value

def _sanitize_incoming_email_html(raw_html: Any) -> str:
    source = str(raw_html or "").strip()
    if not source:
        return ""
    parser = _IncomingEmailHtmlSanitizer()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        logger.warning(f"[incoming_email_html] sanitizer fallback: {exc}")
        return ""
    return parser.get_html().strip()

def _plain_text_to_email_html(raw_text: Any) -> str:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    escaped = html.escape(text)
    return escaped.replace("\n", "<br>")

def _incoming_email_attachment_inline_url(ticket_id: int, attachment_id: int) -> str:
    return f"api/tks/tickets/{int(ticket_id)}/attachments/{int(attachment_id)}/download?inline=1"

def _rewrite_incoming_email_inline_sources(
    body_html: str,
    ticket_id: int,
    attachments: Optional[List[Dict[str, Any]]],
) -> str:
    html_value = str(body_html or "").strip()
    if not html_value or not attachments:
        return html_value

    cid_map: Dict[str, int] = {}
    for item in attachments:
        if not isinstance(item, dict):
            continue
        attachment_id = int(item.get("attachment_id") or item.get("id") or 0)
        content_id = _normalize_incoming_email_content_id(item.get("content_id"))
        if attachment_id > 0 and content_id and content_id not in cid_map:
            cid_map[content_id] = attachment_id

    if not cid_map:
        return html_value

    def _replace(match: re.Match[str]) -> str:
        attr = match.group("attr")
        quote = match.group("quote")
        cid_value = _normalize_incoming_email_content_id(match.group("cid"))
        attachment_id = cid_map.get(cid_value)
        if not attachment_id:
            return match.group(0)
        return f'{attr}={quote}{_incoming_email_attachment_inline_url(ticket_id, attachment_id)}{quote}'

    return re.sub(
        r'(?P<attr>\bsrc)\s*=\s*(?P<quote>[\'"])\s*cid:(?P<cid>.*?)(?P=quote)',
        _replace,
        html_value,
        flags=re.IGNORECASE,
    )

def _build_incoming_email_body_html(
    *,
    ticket_id: int,
    body_text: Any,
    raw_html: Any = "",
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    sanitized_html = _sanitize_incoming_email_html(raw_html)
    if not sanitized_html:
        sanitized_html = _plain_text_to_email_html(body_text)
    if not sanitized_html:
        return ""
    return _rewrite_incoming_email_inline_sources(sanitized_html, ticket_id, attachments)

def _persist_incoming_attachments(
    conn,
    ticket_id: int,
    attachments: Optional[List[Dict[str, Any]]],
    *,
    uploaded_by: str = "email_bot",
) -> List[Dict[str, Any]]:
    """
    Persist incoming email attachments into ticket_attachments.
    Accepts items in format:
    - {"filename": "...", "content_type": "...", "data": bytes}
    - {"filename": "...", "content_type": "...", "data_base64": "..."}
    """
    if not attachments:
        return []
    now = db.now_utc_iso()
    base_path = Path(str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir()))
    base_path = (base_path / str(ticket_id) / "incoming").resolve()
    base_path.mkdir(parents=True, exist_ok=True)

    saved: List[Dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip() or "attachment.bin"
        ext = Path(filename).suffix.lower()
        if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
            logger.warning(f"[incoming_attachments] extensión no permitida: {filename}")
            continue

        raw_data = item.get("data")
        data: bytes
        if isinstance(raw_data, bytes):
            data = raw_data
        else:
            b64 = str(item.get("data_base64") or "").strip()
            if not b64:
                continue
            try:
                data = base64.b64decode(b64, validate=True)
            except Exception:
                logger.warning(f"[incoming_attachments] base64 inválido en archivo {filename}")
                continue

        if not data:
            continue
        if len(data) > app_settings.TICKET_MAX_FILE_SIZE:
            logger.warning(f"[incoming_attachments] tamaño excedido: {filename} ({len(data)})")
            continue

        file_path = (base_path / _attachment_storage_name(filename)).resolve()
        if not _is_safe_attachment_path(file_path):
            logger.warning(f"[incoming_attachments] ruta fuera de raíz permitida: {file_path}")
            continue

        with open(file_path, "wb") as fh:
            fh.write(data)
        sha256 = hashlib.sha256(data).hexdigest()
        content_type = str(item.get("content_type") or "application/octet-stream")
        content_id = _normalize_incoming_email_content_id(item.get("content_id"))
        disposition = str(item.get("disposition") or "").strip().lower()
        is_inline = bool(item.get("is_inline")) or bool(content_id) or "inline" in disposition
        inserted = conn.execute(
            """INSERT INTO ticket_attachments
               (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                int(ticket_id),
                filename,
                str(file_path),
                uploaded_by,
                now,
                len(data),
                content_type,
                sha256,
            ),
        ).fetchone()
        attachment_id = int((inserted or {}).get("id") or 0)
        saved.append(
            {
                "id": attachment_id,
                "attachment_id": attachment_id,
                "filename": filename,
                "path": str(file_path),
                "size": len(data),
                "size_bytes": len(data),
                "content_type": content_type,
                "sha256": sha256,
                "content_id": content_id,
                "disposition": disposition,
                "is_inline": is_inline,
            }
        )
    return saved

def get_ticket_emails(ticket_id: int, format_human: bool = False) -> List[Dict[str, Any]]:
    """Obtiene el historial de correos de un ticket; opcionalmente en formato legible."""
    conn = db.get_conn()
    try:
        cursor = conn.execute(
            """SELECT * FROM ticket_emails
               WHERE ticket_id = ?
               ORDER BY created_at DESC""",
            (ticket_id,),
        )
        items = [dict(row) for row in cursor.fetchall()]
        if not format_human:
            return items

        out: List[Dict[str, Any]] = []
        for row in items:
            body_text = _html_to_text(row.get("body_html") or "")
            attachments = _parse_attachments_json(row.get("attachments_json"))
            out.append(
                {
                    "id": row.get("id"),
                    "ticket_id": row.get("ticket_id"),
                    "direction": row.get("direction"),
                    "subject": row.get("subject") or "",
                    "from_addr": row.get("from_addr") or "",
                    "to_addr": row.get("to_addr") or "",
                    "cc_addrs": row.get("cc_addrs") or "",
                    "bcc_addrs": row.get("bcc_addrs") or "",
                    "created_at": row.get("created_at"),
                    "body_text": body_text,
                    "preview": body_text[:280] + ("..." if len(body_text) > 280 else ""),
                    "attachments": attachments,
                }
            )
        return out
    finally:
        conn.close()

def upload_ticket_attachments(
    ticket_id: int,
    uploaded_by: str,
    files: Optional[List[Any]],
    uploaded_role: str = "",
) -> Dict[str, Any]:
    """Sube adjuntos manuales al ticket y devuelve metadata con hash/size."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_ticket_not_trashed(ticket, "subir adjuntos")
    _ensure_can_participate_ticket(ticket, uploaded_by, uploaded_role, "subir adjuntos")
    if not files:
        return {"ok": True, "ticket_id": ticket_id, "uploaded": 0, "items": list_ticket_attachments(ticket_id)}

    base_root = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir())
    base_path = Path(base_root) / str(ticket_id) / "manual"
    base_path.mkdir(parents=True, exist_ok=True)
    now = db.now_utc_iso()
    uploaded = 0

    conn = db.get_conn()
    try:
        for file in files:
            filename = getattr(file, "filename", "untitled")
            if not filename:
                filename = "untitled"
            ext = Path(filename).suffix.lower()
            if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                logger.warning(f"[attachments] Extensión no permitida: {filename}")
                continue

            file.file.seek(0, 2)
            size = int(file.file.tell())
            file.file.seek(0)
            if size > app_settings.TICKET_MAX_FILE_SIZE:
                logger.warning(f"[attachments] Tamaño excedido: {filename} ({size})")
                continue

            content = file.file.read()
            sha256 = hashlib.sha256(content).hexdigest()
            file_path = base_path / _attachment_storage_name(filename)
            if not _is_safe_attachment_path(file_path):
                logger.warning(f"[attachments] ruta de adjunto fuera de raíz permitida: {file_path}")
                continue
            with open(file_path, "wb") as fh:
                fh.write(content)

            conn.execute(
                """INSERT INTO ticket_attachments
                   (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    filename,
                    str(file_path),
                    uploaded_by,
                    now,
                    len(content),
                    getattr(file, "content_type", "application/octet-stream"),
                    sha256,
                ),
            )
            uploaded += 1

        if uploaded > 0:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (ticket_id, uploaded_by, f"[ADJUNTO] Se cargaron {uploaded} archivo(s).", now),
            )
            conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        conn.commit()
    finally:
        conn.close()

    if uploaded > 0:
        try:
            create_evidence_event(
                control_id="A.8.12",
                artifact_ref=f"ticket:{ticket_id}:attachments",
                owner=uploaded_by,
                integrity_hash="",
                metadata={"uploaded": uploaded},
            )
        except Exception as e:
            logger.warning(f"[upload_ticket_attachments] evidence_event no crítico falló para ticket {ticket_id}: {e}")

    return {"ok": True, "ticket_id": ticket_id, "uploaded": uploaded, "items": list_ticket_attachments(ticket_id)}

def list_ticket_attachments(ticket_id: int) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id, ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256
               FROM ticket_attachments
               WHERE ticket_id = ?
               ORDER BY created_at DESC""",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_ticket_attachment_for_download(ticket_id: int, attachment_id: int) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT id, ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256
               FROM ticket_attachments
               WHERE ticket_id = ? AND id = ?
               LIMIT 1""",
            (int(ticket_id), int(attachment_id)),
        ).fetchone()
        if not row:
            raise ValueError("Adjunto no encontrado")
        item = dict(row)
    finally:
        conn.close()

    raw_path = str(item.get("file_path") or "").strip()
    if not raw_path:
        raise ValueError("Adjunto sin ruta de archivo")

    path = Path(raw_path)
    if not _is_safe_attachment_path(path):
        raise ValueError("Ruta de adjunto fuera de raíz permitida")
    if not path.exists() or not path.is_file():
        raise ValueError("Archivo adjunto no disponible")

    item["resolved_path"] = str(path.resolve())
    item["content_type"] = (
        str(item.get("content_type") or "").strip()
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )
    return item

def get_timeline(ticket_id: int, limit: int = 120, include_emails: bool = False) -> List[Dict[str, Any]]:
    """Línea de tiempo unificada para la UI.

    Salida normalizada por evento:
      - event_type
      - event_at (UTC ISO)
      - actor
      - detail
      - source_table
      - source_id

    Compatibilidad: mantiene `created_at` como alias de `event_at`.
    """
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 120), 500))

        comment_rows = conn.execute(
            """SELECT id, user_id, content, created_at
               FROM ticket_comments
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (ticket_id, limit),
        ).fetchall()

        transition_rows = conn.execute(
            """SELECT id, from_subestado, to_subestado, actor, reason, created_at
               FROM ticket_transitions
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (ticket_id, limit),
        ).fetchall()

        approval_rows = conn.execute(
            """SELECT id, step, approver, decision, decision_note, decided_at
               FROM ticket_approvals
               WHERE ticket_id = ?
               ORDER BY decided_at DESC, id DESC
               LIMIT ?""",
            (ticket_id, limit),
        ).fetchall()

        email_rows = []
        if include_emails:
            email_rows = conn.execute(
                """SELECT id, direction, subject, from_addr, to_addr, created_at
               FROM ticket_emails
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
                (ticket_id, limit),
            ).fetchall()

        def _to_event_at(raw_value: Optional[str]) -> str:
            dt = _parse_dt(raw_value) or _now_dt()
            return _ensure_utc(dt).isoformat()

        events: List[Dict[str, Any]] = []

        for row in comment_rows:
            content = str(row["content"] or "")
            event_type = "comment"
            detail = content
            if content.startswith("[") and "]" in content:
                parts = content.split("]", 1)
                inferred = parts[0][1:].strip().lower()
                if inferred:
                    event_type = inferred
                detail = parts[1].strip()

            event_at = _to_event_at(row["created_at"])
            events.append(
                {
                    "event_type": event_type,
                    "event_at": event_at,
                    "created_at": event_at,
                    "actor": str(row["user_id"] or "system"),
                    "detail": detail,
                    "source_table": "ticket_comments",
                    "source_id": int(row["id"]),
                }
            )

        for row in transition_rows:
            to_sub = str(row["to_subestado"] or "-")
            reason = str(row["reason"] or "").strip()
            detail = f"Estado: cambiado a {to_sub}"

            event_at = _to_event_at(row["created_at"])
            events.append(
                {
                    "event_type": "transition",
                    "event_at": event_at,
                    "created_at": event_at,
                    "actor": str(row["actor"] or "system"),
                    "detail": detail,
                    "source_table": "ticket_transitions",
                    "source_id": int(row["id"]),
                }
            )

        for row in approval_rows:
            step = int(row["step"] or 0)
            decision = str(row["decision"] or "pending")
            note = str(row["decision_note"] or "").strip()
            detail = f"step={step} decision={decision}" + (f" | note: {note}" if note else "")

            event_at = _to_event_at(row["decided_at"])
            events.append(
                {
                    "event_type": "approval",
                    "event_at": event_at,
                    "created_at": event_at,
                    "actor": str(row["approver"] or "system"),
                    "detail": detail,
                    "source_table": "ticket_approvals",
                    "source_id": int(row["id"]),
                }
            )

        # include_emails se mantiene por compatibilidad de firma; la timeline unificada
        # ahora siempre incorpora correos para tener trazabilidad completa.
        if include_emails:
            for row in email_rows:
                direction = str(row["direction"] or "").strip().lower()
                subject = str(row["subject"] or "").strip()
                from_addr = str(row["from_addr"] or "").strip()
                to_addr = str(row["to_addr"] or "").strip()
    
                parts = [f"direction={direction or '-'}"]
                if subject:
                    parts.append(f"subject={subject}")
                if from_addr:
                    parts.append(f"from={from_addr}")
                if to_addr:
                    parts.append(f"to={to_addr}")
    
                event_at = _to_event_at(row["created_at"])
                events.append(
                    {
                        "event_type": "email",
                        "event_at": event_at,
                        "created_at": event_at,
                        "actor": from_addr or to_addr or "system",
                        "detail": " | ".join(parts),
                        "source_table": "ticket_emails",
                        "source_id": int(row["id"]),
                    }
                )
    
        events.sort(
            key=lambda item: (item.get("event_at") or "", int(item.get("source_id") or 0)),
            reverse=True,
        )
        return events[:limit]
    finally:
        conn.close()

def get_stats(asignado_a: Optional[str] = None) -> Dict[str, Any]:
    """Obtener métricas para Dashboard."""
    conn = db.get_conn()
    try:
        where_parts = ["1=1", "COALESCE(is_trashed, FALSE) = FALSE"]
        where_params: List[Any] = []
        if asignado_a is not None and str(asignado_a).strip():
            where_parts.append("LOWER(COALESCE(asignado_a, '')) = ?")
            where_params.append(str(asignado_a).strip().lower())
        where_sql = " AND ".join(where_parts)

        stats = {
            "by_status": {},
            "by_prio": {},
            "by_category": {},
            "pivot_assignee": {},
            "sla_compliance": {"on_time": 0, "breached": 0},
            "total": 0,
        }

        # Por Estado
        rows = conn.execute(
            f"SELECT estado, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY estado",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            stats["by_status"][r["estado"]] = r["c"]
            stats["total"] += r["c"]

        # Por Severidad
        rows = conn.execute(
            f"SELECT severidad, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY severidad",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            stats["by_prio"][r["severidad"]] = r["c"]

        # Por Categoría
        rows = conn.execute(
            f"SELECT categoria, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY categoria",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            stats["by_category"][r["categoria"] or "general"] = r["c"]

        # Pivot: Assignee vs Status
        rows = conn.execute(
            f"SELECT asignado_a, estado, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY asignado_a, estado",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            assignee = r["asignado_a"] or "Sin Asignar"
            status = r["estado"]
            count = r["c"]
            if assignee not in stats["pivot_assignee"]:
                stats["pivot_assignee"][assignee] = {"total": 0}
            stats["pivot_assignee"][assignee][status] = count
            stats["pivot_assignee"][assignee]["total"] += count

        # SLA Compliance
        now = db.now_utc_iso()
        sla_params: List[Any] = [now, now, *where_params]
        row = conn.execute("""
            SELECT
                COUNT(CASE WHEN vence_at >= ? OR estado IN ('cerrado','resuelto') THEN 1 END) as on_time,
                COUNT(CASE WHEN vence_at < ? AND estado NOT IN ('cerrado','resuelto') THEN 1 END) as breached
            FROM tickets WHERE vence_at IS NOT NULL AND """ + where_sql,
            tuple(sla_params),
        ).fetchone()
        if row:
            stats["sla_compliance"]["on_time"] = row["on_time"]
            stats["sla_compliance"]["breached"] = row["breached"]

        return stats
    finally:
        conn.close()

def _assignment_phase_from_subestado(subestado: Optional[str]) -> Optional[str]:
    raw = str(subestado or "").strip().lower()
    normalized = SUBESTADOS_LEGACY_MAP.get(raw, raw)
    if normalized == "asignado":
        return "asignado"
    if normalized in {"en_progreso", "en_validacion", "en_ejecucion", "en_analisis", "aprobado"}:
        return "en_progreso"
    if normalized == "resuelto":
        return "resuelto"
    return None

def _build_assignment_segments(
    ticket: Dict[str, Any],
    transitions: List[Dict[str, Any]],
    now_dt: datetime,
) -> List[Dict[str, Any]]:
    ordered = sorted(
        (dict(t or {}) for t in (transitions or [])),
        key=lambda t: ((_parse_dt(t.get("created_at")) or now_dt), int(t.get("id") or 0)),
    )
    segments: List[Dict[str, Any]] = []
    active_phase: Optional[str] = None
    active_start: Optional[datetime] = None

    for tr in ordered:
        ts = _parse_dt(tr.get("created_at"))
        if not ts:
            continue
        next_phase = _assignment_phase_from_subestado(tr.get("to_subestado"))

        if active_phase and active_start:
            if next_phase == active_phase:
                continue
            end_dt = ts if ts >= active_start else active_start
            segments.append(
                {
                    "phase": active_phase,
                    "start_at": active_start.isoformat(),
                    "end_at": end_dt.isoformat(),
                }
            )
            active_phase = None
            active_start = None

        if next_phase:
            active_phase = next_phase
            active_start = ts

    if not segments and not active_phase:
        fallback_phase = _assignment_phase_from_subestado(ticket.get("subestado"))
        fallback_start = _parse_dt(ticket.get("created_at"))
        if fallback_phase and fallback_start:
            active_phase = fallback_phase
            active_start = fallback_start

    if active_phase and active_start:
        estado = str(ticket.get("estado") or "").strip().lower()
        if estado == "cerrado":
            fallback_end = (
                _parse_dt(ticket.get("updated_at"))
                or _parse_dt(ticket.get("resolved_at"))
                or now_dt
            )
        elif estado == "resuelto":
            fallback_end = (
                _parse_dt(ticket.get("resolved_at"))
                or _parse_dt(ticket.get("updated_at"))
                or now_dt
            )
        else:
            fallback_end = now_dt
        if fallback_end < active_start:
            fallback_end = active_start
        segments.append(
            {
                "phase": active_phase,
                "start_at": active_start.isoformat(),
                "end_at": fallback_end.isoformat(),
            }
        )

    merged: List[Dict[str, Any]] = []
    for seg in segments:
        if not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        prev_end = _parse_dt(prev.get("end_at"))
        cur_start = _parse_dt(seg.get("start_at"))
        cur_end = _parse_dt(seg.get("end_at"))
        if (
            prev.get("phase") == seg.get("phase")
            and prev_end
            and cur_start
            and cur_start <= prev_end
        ):
            if cur_end and cur_end > prev_end:
                prev["end_at"] = cur_end.isoformat()
            continue
        merged.append(seg)
    return merged

def get_assignment_timeline(
    window_hours: int = 72,
    ticket_limit: int = 400,
    assignee: Optional[str] = None,
) -> Dict[str, Any]:
    window_hours = _clamp_int(window_hours, default_value=72, min_value=1, max_value=720)
    ticket_limit = _clamp_int(ticket_limit, default_value=400, min_value=50, max_value=2000)
    assignee_filter = _normalize_username(assignee)

    now_iso = db.now_utc_iso()
    now_dt = _parse_dt(now_iso) or _now_dt()
    window_start_dt = now_dt - timedelta(hours=window_hours)

    spec_rows = list_specialties()
    tech_map: Dict[str, Dict[str, Any]] = {}
    for row in spec_rows:
        username = str(row.get("username") or "").strip().lower()
        specialty = str(row.get("specialty") or "").strip().lower()
        if not username:
            continue
        if assignee_filter and username != assignee_filter:
            continue
        if specialty == "admin":
            continue
        lane = tech_map.setdefault(
            username,
            {
                "username": username,
                "specialties": [],
                "roles": [],
                "current_load": 0,
                "max_load": int(row.get("max_load") or 0),
                "_items": [],
            },
        )
        role_primary = _normalize_role(row.get("role"))
        if role_primary and role_primary not in lane["roles"]:
            lane["roles"].append(role_primary)
        try:
            secondary_roles = json.loads(row.get("secondary_roles") or "[]")
        except Exception:
            secondary_roles = []
        for role_item in _normalize_roles(secondary_roles):
            if role_item and role_item not in lane["roles"]:
                lane["roles"].append(role_item)
        if specialty and specialty not in lane["specialties"]:
            lane["specialties"].append(specialty)
        lane["current_load"] = max(int(lane.get("current_load") or 0), int(row.get("current_load") or 0))
        lane["max_load"] = max(int(lane.get("max_load") or 0), int(row.get("max_load") or 0))

    conn = db.get_conn()
    try:
        if assignee_filter:
            ticket_rows = conn.execute(
                """SELECT id, codigo, titulo, estado, subestado, asignado_a, categoria, severidad,
                          created_at, updated_at, resolved_at
                   FROM tickets
                   WHERE LOWER(COALESCE(asignado_a, '')) = ?
                     AND COALESCE(is_trashed, FALSE) = FALSE
                   ORDER BY created_at ASC, id ASC
                   LIMIT ?""",
                (assignee_filter, ticket_limit),
            ).fetchall()
        else:
            ticket_rows = conn.execute(
                """SELECT id, codigo, titulo, estado, subestado, asignado_a, categoria, severidad,
                          created_at, updated_at, resolved_at
                   FROM tickets
                   WHERE COALESCE(is_trashed, FALSE) = FALSE
                     AND ((asignado_a IS NOT NULL)
                      OR (COALESCE(asignado_a, '') = '' AND estado = 'abierto')
                     )
                   ORDER BY created_at ASC, id ASC
                   LIMIT ?""",
                (ticket_limit,),
            ).fetchall()
        tickets_data = [dict(r) for r in ticket_rows]
        ticket_ids = [int(t["id"]) for t in tickets_data if t.get("id") is not None]

        transitions_by_ticket: Dict[int, List[Dict[str, Any]]] = {}
        if ticket_ids:
            placeholders = ", ".join(["?"] * len(ticket_ids))
            transition_rows = conn.execute(
                f"""SELECT id, ticket_id, to_subestado, created_at
                    FROM ticket_transitions
                    WHERE ticket_id IN ({placeholders})
                    ORDER BY created_at ASC, id ASC""",
                tuple(ticket_ids),
            ).fetchall()
            for row in transition_rows:
                tid = int(row["ticket_id"])
                transitions_by_ticket.setdefault(tid, []).append(dict(row))
    finally:
        conn.close()

    queue: List[Dict[str, Any]] = []
    for ticket in tickets_data:
        ticket_assignee = str(ticket.get("asignado_a") or "").strip().lower()
        estado = str(ticket.get("estado") or "").strip().lower()
        subestado = str(ticket.get("subestado") or "").strip().lower()
        tid = int(ticket.get("id") or 0)

        segments = _build_assignment_segments(ticket, transitions_by_ticket.get(tid, []), now_dt)
        item = {
            "ticket_id": tid,
            "codigo": ticket.get("codigo") or f"#{tid}",
            "titulo": ticket.get("titulo") or "Sin título",
            "estado": estado,
            "subestado": subestado,
            "categoria": ticket.get("categoria") or "general",
            "severidad": ticket.get("severidad") or "media",
            "created_at": ticket.get("created_at"),
            "updated_at": ticket.get("updated_at"),
            "resolved_at": ticket.get("resolved_at"),
            "segments": segments,
            "active_phase": _assignment_phase_from_subestado(subestado),
            "is_done": estado in {"resuelto", "cerrado"},
            "started_at": segments[0]["start_at"] if segments else ticket.get("created_at"),
            "ended_at": segments[-1]["end_at"] if segments else ticket.get("updated_at"),
        }

        if ticket_assignee:
            if ticket_assignee not in tech_map:
                tech_map[ticket_assignee] = {
                    "username": ticket_assignee,
                    "specialties": [],
                    "roles": [],
                    "current_load": 0,
                    "max_load": 0,
                    "_items": [],
                }
            tech_map[ticket_assignee]["_items"].append(item)
            continue

        if estado == "abierto":
            created_dt = _parse_dt(ticket.get("created_at"))
            waiting_minutes = max(0, int((now_dt - created_dt).total_seconds() // 60)) if created_dt else 0
            queue.append(
                {
                    "ticket_id": tid,
                    "codigo": ticket.get("codigo") or f"#{tid}",
                    "titulo": ticket.get("titulo") or "Sin título",
                    "categoria": ticket.get("categoria") or "general",
                    "severidad": ticket.get("severidad") or "media",
                    "created_at": ticket.get("created_at"),
                    "waiting_minutes": waiting_minutes,
                }
            )

    technicians: List[Dict[str, Any]] = []
    for username in sorted(tech_map.keys()):
        lane = tech_map[username]
        items = sorted(
            lane.get("_items") or [],
            key=lambda x: (_parse_dt(x.get("started_at")) or now_dt, int(x.get("ticket_id") or 0)),
        )
        active_items = [it for it in items if str(it.get("estado") or "").lower() not in {"resuelto", "cerrado"}]
        technicians.append(
            {
                "username": lane.get("username"),
                "specialties": sorted(lane.get("specialties") or []),
                "roles": sorted(lane.get("roles") or []),
                "current_load": int(lane.get("current_load") or 0),
                "max_load": int(lane.get("max_load") or 0),
                "status": "ocupado" if active_items else "disponible",
                "active_count": len(active_items),
                "items": items,
            }
        )

    queue_projection = [dict(q) for q in queue]
    for lane in technicians:
        next_ticket: Optional[Dict[str, Any]] = None
        if lane.get("status") == "disponible" and queue_projection:
            specialties = {str(s).strip().lower() for s in (lane.get("specialties") or []) if str(s).strip()}
            pick_idx: Optional[int] = None
            for idx, queued in enumerate(queue_projection):
                cat = str(queued.get("categoria") or "").strip().lower()
                if cat in specialties or cat in {"general", ""}:
                    pick_idx = idx
                    break
            if pick_idx is None:
                pick_idx = 0
            next_ticket = queue_projection.pop(pick_idx)
        lane["next_queue_ticket"] = next_ticket

    range_points: List[datetime] = [window_start_dt, now_dt]
    for lane in technicians:
        for item in lane.get("items") or []:
            for seg in item.get("segments") or []:
                sdt = _parse_dt(seg.get("start_at"))
                edt = _parse_dt(seg.get("end_at"))
                if sdt:
                    range_points.append(sdt)
                if edt:
                    range_points.append(edt)
    range_start = min(range_points) if range_points else window_start_dt
    range_end = max(range_points) if range_points else now_dt
    if range_end <= range_start:
        range_end = range_start + timedelta(minutes=1)

    return {
        "ok": True,
        "generated_at": now_iso,
        "window_hours": window_hours,
        "range": {
            "start_at": range_start.isoformat(),
            "end_at": range_end.isoformat(),
        },
        "technicians": technicians,
        "queue": queue,
    }

