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
from ._crud import (  # noqa: PLC0415
    create_ticket,
    get_ticket,
    generar_codigo,
    _emit_system_comment,
    _evaluate_ticket_sla,
    _persist_incoming_attachments,
    _build_incoming_email_body_html,
)

logger = logging.getLogger(__name__)

# ==========================================================================
# PROCESAMIENTO DE CORREOS (INCOMING)
# ==========================================================================
def _extract_message_ids(raw_header: str) -> List[str]:
    if not raw_header:
        return []
    found = re.findall(r"<[^>]+>", raw_header)
    if found:
        return found
    return [p.strip() for p in raw_header.split() if p.strip()]

def _message_id_variants(message_id: str) -> List[str]:
    raw = (message_id or "").strip()
    if not raw:
        return []
    core = raw.strip("<>").strip()
    variants = [raw]
    if core:
        if core not in variants:
            variants.append(core)
        bracketed = f"<{core}>"
        if bracketed not in variants:
            variants.append(bracketed)
    return variants

def _normalize_message_id(message_id: Optional[str]) -> str:
    raw = str(message_id or "").strip()
    if not raw:
        return ""
    core = raw.strip("<>").strip()
    if not core:
        return ""
    return f"<{core}>"

def _normalize_message_ids(raw_header: Optional[str]) -> List[str]:
    out: List[str] = []
    for token in _extract_message_ids(str(raw_header or "")):
        normalized = _normalize_message_id(token)
        if normalized:
            out.append(normalized)
    return out

def _merge_reference_chain(*raw_headers: Optional[str], max_items: int = AUTO_REPLY_MAX_REFERENCES) -> str:
    dedupe: set[str] = set()
    ordered: List[str] = []
    for raw in raw_headers:
        for token in _normalize_message_ids(raw):
            marker = token.lower()
            if marker in dedupe:
                continue
            dedupe.add(marker)
            ordered.append(token)
    if max_items > 0 and len(ordered) > max_items:
        ordered = ordered[-max_items:]
    return " ".join(ordered)

def _build_ticket_thread_headers(ticket: Dict[str, Any]) -> Dict[str, str]:
    thread_id = _normalize_message_id(ticket.get("email_thread_id"))
    references = _merge_reference_chain(ticket.get("email_references"), thread_id)
    headers: Dict[str, str] = {}
    if thread_id:
        headers["In-Reply-To"] = thread_id
    if references:
        headers["References"] = references
    return headers

def _update_ticket_thread_metadata(
    conn,
    ticket_id: int,
    message_id: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> None:
    row = conn.execute(
        "SELECT email_thread_id, email_references FROM tickets WHERE id = ? LIMIT 1",
        (ticket_id,),
    ).fetchone()
    if not row:
        return
    current_thread = _normalize_message_id(row.get("email_thread_id"))
    current_refs = str(row.get("email_references") or "")
    new_message_id = _normalize_message_id(message_id)

    merged_refs = _merge_reference_chain(
        current_refs,
        current_thread,
        in_reply_to,
        references,
        new_message_id,
    )
    next_thread = new_message_id or current_thread

    if next_thread != (row.get("email_thread_id") or "") or merged_refs != current_refs:
        conn.execute(
            """UPDATE tickets
               SET email_thread_id = ?, email_references = ?, updated_at = ?
               WHERE id = ?""",
            (next_thread, merged_refs, db.now_utc_iso(), ticket_id),
        )

def _find_ticket_by_thread_headers(in_reply_to: str, references: str) -> Optional[int]:
    conn = db.get_conn()
    try:
        candidates: List[str] = []
        dedupe: set[str] = set()
        for candidate in (_normalize_message_ids(in_reply_to) + _normalize_message_ids(references)):
            marker = candidate.lower()
            if marker in dedupe:
                continue
            dedupe.add(marker)
            candidates.append(candidate)
        for candidate in candidates:
            for token in _message_id_variants(candidate):
                row = conn.execute(
                    """SELECT id
                       FROM tickets
                       WHERE email_thread_id = ?
                          OR email_references ILIKE ?
                       ORDER BY id DESC
                       LIMIT 1""",
                    (token, f"%{token}%"),
                ).fetchone()
                if row:
                    return int(row["id"])
        return None
    finally:
        conn.close()

def _find_ticket_by_subject(subject: str) -> Optional[int]:
    conn = db.get_conn()
    try:
        # Formato actual: TK-DD-MM-YYYY-NNNN
        # Formato legacy: TK-YYYYMM-NNNN
        for pattern in (
            r"(TK-\d{2}-\d{2}-\d{4}-\d{4,})",
            r"(TK-\d{6}-\d{4,})",
            r"(TK-\d{4,})",
        ):
            code_match = re.search(pattern, subject or "", re.IGNORECASE)
            if code_match:
                code = code_match.group(1).upper()
                row = conn.execute(
                    "SELECT id FROM tickets WHERE UPPER(codigo) = UPPER(?) ORDER BY id DESC LIMIT 1",
                    (code,),
                ).fetchone()
                if row:
                    return int(row["id"])

        # Fallback legacy: TK-1234 (id directo).
        legacy_match = re.search(r"TK-(\d+)", subject or "", re.IGNORECASE)
        if legacy_match:
            row = conn.execute("SELECT id FROM tickets WHERE id = ?", (int(legacy_match.group(1)),)).fetchone()
            if row:
                return int(row["id"])
        return None
    finally:
        conn.close()

def _auto_reply_subject_default(ticket: Dict[str, Any]) -> str:
    code = str(ticket.get("codigo") or f"TK-{ticket.get('id', '')}").strip() or "Ticket"
    title = str(ticket.get("titulo") or "").strip()
    if title:
        return f"Re: [{code}] {title}"
    return f"Re: [{code}] Comprobante de Recepción"

def _auto_reply_subject(conn, ticket: Dict[str, Any], nombre: str = "", asignado_a: str = "") -> str:
    template = _get_system_setting(conn, AUTO_REPLY_SUBJECT_SETTING_KEY, "").strip()
    if not template:
        return _auto_reply_subject_default(ticket)
    rendered = _render_text_template(
        template,
        _ticketera_template_context(ticket=ticket, customer_name=nombre, assignee_name=asignado_a),
    ).strip()
    return rendered or _auto_reply_subject_default(ticket)

def _auto_reply_body(conn, ticket: Dict[str, Any], nombre: str, asignado_a: str) -> str:
    template = _get_system_setting(conn, AUTO_REPLY_BODY_SETTING_KEY, DEFAULT_AUTO_REPLY_BODY_TEMPLATE)
    rendered = _render_text_template(
        template,
        _ticketera_template_context(ticket=ticket, customer_name=nombre, assignee_name=asignado_a),
    ).strip() or DEFAULT_AUTO_REPLY_BODY_TEMPLATE
    return "<p>" + html.escape(rendered).replace("\n", "<br>") + "</p>"

def should_schedule_auto_reply(conn, ticket_id: int, to_email: str) -> tuple[bool, str, Optional[str]]:
    # 1. Traer de settings de DB
    row = conn.execute("SELECT value FROM system_settings WHERE key = 'ticket_auto_reply_enabled'").fetchone()
    db_enabled = None
    if row and row["value"]:
        db_enabled = str(row["value"]).lower() in ["true", "1", "yes"]
    
    # 2. Fallback a .env
    env_enabled = bool(getattr(app_settings, "TICKET_AUTO_REPLY_ENABLED", False))
    
    is_enabled = db_enabled if db_enabled is not None else env_enabled
    if not is_enabled:
        return False, "auto_reply_disabled", None

    normalized = _normalize_email_address(to_email)
    allowed, reason = _auto_reply_sender_allowed(normalized)
    if not allowed:
        return False, reason, None

    idem_key = _auto_reply_idempotency_key(ticket_id, normalized)
    existing = conn.execute(
        """SELECT 1
           FROM ticket_emails
           WHERE ticket_id = ?
             AND idempotency_key = ?
             AND direction IN ('auto_reply_pending', 'auto_reply')
           LIMIT 1""",
        (ticket_id, idem_key),
    ).fetchone()
    if existing:
        return False, "already_scheduled_or_sent", idem_key

    return True, "allowed", idem_key

def schedule_auto_reply_for_ticket(
    conn,
    ticket: Dict[str, Any],
    to_email: str,
    nombre: str,
    asignado_a: Optional[str],
    in_reply_to: Optional[str],
    references: Optional[str],
) -> Dict[str, Any]:
    ticket_id = int(ticket["id"])
    now = db.now_utc_iso()
    ok, reason, idem_key = should_schedule_auto_reply(conn, ticket_id, to_email)
    if not ok:
        logger.info(f"[AUTO_REPLY] skip ticket={ticket_id} to={to_email}: {reason}")
        return {"scheduled": False, "reason": reason, "ticket_id": ticket_id}

    normalized_to = _normalize_email_address(to_email)
    delay_minutes = _auto_reply_delay_minutes(conn)
    run_at = (datetime.utcnow() + timedelta(minutes=delay_minutes)).isoformat()
    thread_headers = _build_ticket_thread_headers(ticket)
    in_reply_to_norm = _normalize_message_id(in_reply_to) or thread_headers.get("In-Reply-To")
    merged_refs = _merge_reference_chain(
        thread_headers.get("References"),
        references,
        in_reply_to,
    )
    payload = {
        "ticket_id": ticket_id,
        "email": normalized_to,
        "nombre": nombre,
        "asignado_a": asignado_a or "",
        "ticket_code": str(ticket.get("codigo") or generar_codigo(ticket_id)),
        "idempotency_key": idem_key,
        "in_reply_to": in_reply_to_norm or "",
        "references": merged_refs or "",
    }
    body_html = _auto_reply_body(conn, ticket, nombre, asignado_a or "")
    subject = _auto_reply_subject(conn, ticket, nombre, asignado_a or "")

    # Nunca enviar en línea durante el procesamiento de correo entrante.
    # Incluso con delay=0, encolamos el job para evitar bloquear el ciclo de ingestión
    # y mantener tiempos de respuesta estables.
    if delay_minutes <= 0:
        run_at = datetime.utcnow().isoformat()

    conn.execute(
        """INSERT INTO ticket_emails
           (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, idempotency_key, created_at)
           VALUES (?, 'auto_reply_pending', '', ?, ?, ?, '[]', ?, ?)""",
        (ticket_id, normalized_to, subject, body_html, idem_key, now),
    )
    conn.execute(
        """INSERT INTO sys_jobs
           (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
           VALUES ('SEND_AUTO_RESPONSE', 'PENDING', ?, ?, 0, 3, ?, ?)""",
        (json.dumps(payload), run_at, now, now),
    )
    return {
        "scheduled": True,
        "reason": "scheduled",
        "ticket_id": ticket_id,
        "idempotency_key": idem_key,
        "next_run_at": run_at,
        "delay_minutes": delay_minutes,
    }

def handle_incoming_email(msg: Dict[str, Any]) -> Optional[int]:
    """
    Procesa un mensaje de correo entrante. Devuelve el ticket_id resultante
    (sea reply a uno existente o ticket nuevo) o None si no se pudo procesar.
    Priorización:
    1) Match por hilo (In-Reply-To / References).
    2) Match por código en asunto (TK-DD-MM-YYYY-NNNN, legacy TK-YYYYMM-NNNN o TK-1234).
    3) Si no hay match, crea ticket nuevo.

    Los matchers (header/subject) loggean su propio error y se sigue al
    siguiente paso. Un fallo en el procesamiento real (reply o nuevo ticket)
    se propaga al caller para que el poller pueda NO marcar Seen y
    reintentar en el próximo ciclo.
    """
    subject = msg.get("subject", "")
    sender = msg.get("sender", "")
    body = msg.get("body", "")
    body_html = msg.get("body_html", "")
    msg_id = msg.get("message_id", "")
    in_reply_to = msg.get("in_reply_to", "")
    references = msg.get("references", "")
    attachments = msg.get("attachments") if isinstance(msg.get("attachments"), list) else []

    try:
        ticket_id = _find_ticket_by_thread_headers(in_reply_to, references)
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by thread headers: {e}")
        ticket_id = None
    if ticket_id:
        _process_reply_email(ticket_id, sender, subject, body, msg_id, in_reply_to, references, attachments, body_html=body_html)
        return ticket_id

    try:
        ticket_id = _find_ticket_by_subject(subject)
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by subject: {e}")
        ticket_id = None
    if ticket_id:
        _process_reply_email(ticket_id, sender, subject, body, msg_id, in_reply_to, references, attachments, body_html=body_html)
        return ticket_id

    return _process_new_email_ticket(subject, sender, body, msg_id, in_reply_to, references, attachments, body_html=body_html)

def _process_reply_email(
    ticket_id: int,
    sender: str,
    subject: str,
    body: str,
    msg_id: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    body_html: Optional[str] = None,
) -> int:
    logger.info("[EMAIL] Reply to Ticket #%s from %s", ticket_id, sender)
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        preview = (body or "").strip()
        if len(preview) > 600:
            preview = preview[:600] + "..."

        conn.execute(
            "INSERT INTO ticket_comments (ticket_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, f"email:{sender}", f"[CORREO_ENTRANTE] {preview}", now)
        )
        saved_attachments = _persist_incoming_attachments(
            conn,
            ticket_id,
            attachments,
            uploaded_by=f"email:{sender}",
        )
        stored_body_html = _build_incoming_email_body_html(
            ticket_id=ticket_id,
            body_text=body,
            raw_html=body_html,
            attachments=saved_attachments,
        )
        conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id,
                "incoming",
                sender,
                "",
                subject or "",
                stored_body_html,
                json.dumps(saved_attachments, ensure_ascii=False),
                now,
            ),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        _update_ticket_thread_metadata(
            conn,
            ticket_id,
            message_id=msg_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()
    return int(ticket_id)

def _process_new_email_ticket(
    subject: str,
    sender: str,
    body: str,
    msg_id: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    body_html: Optional[str] = None,
) -> Optional[int]:
    logger.info("[EMAIL] New Ticket from %s", sender)
    
    # 1. Clasificación
    categoria = clasificar_ticket(subject, body)
    # 2. Triaje: por correo entrante se crea SIEMPRE sin asignación (cola manual)
    asignado_a = None

    # 3. Datos del cliente
    cliente_nombre, origen_email = _sender_identity(sender)
    if not origen_email:
        origen_email = sender.strip()
    if not cliente_nombre:
        cliente_nombre = origen_email

    conn = None
    ticket_id: Optional[int] = None
    now = db.now_utc_iso()
    thread_id = _normalize_message_id(msg_id) or _normalize_message_id(in_reply_to)
    thread_refs = _merge_reference_chain(references, in_reply_to, msg_id)

    # 4. Crear Ticket
    try:
        tk = create_ticket(
            titulo=subject,
            descripcion=body,
            creador_id="email_bot",
            categoria=categoria,
            origen_email=origen_email,
            cliente_nombre=cliente_nombre,
            email_thread_id=thread_id,
            email_references=thread_refs,
            auto_assign=False,
        )
        
        ticket_id = tk['id']
        codigo = tk['codigo']
        # Registrar correo entrante en historial de correos.
        conn = db.get_conn()
        saved_attachments = _persist_incoming_attachments(
            conn,
            ticket_id,
            attachments,
            uploaded_by=f"email:{sender}",
        )
        stored_body_html = _build_incoming_email_body_html(
            ticket_id=ticket_id,
            body_text=body,
            raw_html=body_html,
            attachments=saved_attachments,
        )
        conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id,
                "incoming",
                sender,
                "",
                subject or "",
                stored_body_html,
                json.dumps(saved_attachments, ensure_ascii=False),
                now,
            ),
        )
        _update_ticket_thread_metadata(
            conn,
            ticket_id,
            message_id=msg_id,
            in_reply_to=in_reply_to,
            references=references,
        )

        logger.info("[EMAIL] Created Ticket %s (#%s)", codigo, ticket_id)

        _emit_system_comment(
            conn,
            ticket_id,
            "[CREACIÓN] Ticket generado [Estado: Sin asignar]",
            now,
            author_id="system",
        )

        # 5. Programar Auto-Respuesta Segura (allowlist + antiloop + one-shot)
        auto_result = schedule_auto_reply_for_ticket(
            conn,
            tk,
            origen_email,
            cliente_nombre,
            asignado_a,
            in_reply_to,
            references,
        )
        # Nota: Se eliminó la emisión de comentario [AUTO_RESPUESTA] programada
        # por petición del usuario para evitar ruido en la línea de tiempo.
        conn.commit()
        if auto_result.get("scheduled"):
            logger.info(
                f"[AUTO_REPLY] scheduled ticket={ticket_id} to={origen_email} "
                f"delay={auto_result.get('delay_minutes')}m"
            )
        else:
            logger.info(
                f"[AUTO_REPLY] skipped ticket={ticket_id} to={origen_email} "
                f"reason={auto_result.get('reason')}"
            )

    except Exception as e:
        logger.error(f"[EMAIL] Error creating ticket: {e}")
        raise
    finally:
        if conn:
            conn.close()
    return ticket_id

