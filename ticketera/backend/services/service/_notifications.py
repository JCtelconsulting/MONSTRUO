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
# NOTIFICACIONES ESCALONADAS
# ==========================================================================
def programar_notificaciones(ticket_id: int, user_id: str) -> None:
    """
    Programa 2 niveles de notificación:
    1. Inmediato → in-app
    2. +5 min → Google Chat DM al especialista
    """
    conn = db.get_conn()
    try:
        now = datetime.fromisoformat(db.now_utc_iso().replace("Z", "+00:00"))
        now_iso = now.isoformat()

        niveles = [
            (1, "app", now),
            (2, "google_chat", now + timedelta(minutes=5)),
        ]

        for level, channel, scheduled in niveles:
            conn.execute("""
                INSERT INTO ticket_notifications
                (
                    ticket_id, user_id, channel, status, escalation_level,
                    scheduled_at, next_retry_at, attempt_count, max_attempts,
                    provider, provider_ref, last_error, error, created_at, updated_at
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, 0, ?, '', '', '', '', ?, ?)
            """, (
                ticket_id,
                user_id,
                channel,
                level,
                scheduled.isoformat(),
                scheduled.isoformat(),
                CHANNELS_MAX_ATTEMPTS,
                now_iso,
                now_iso,
            ))

        conn.commit()
    finally:
        conn.close()

def marcar_notificacion_vista(ticket_id: int, user_id: str) -> None:
    """Cuando el técnico ve el ticket, cancela las notificaciones pendientes."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute("""
            UPDATE ticket_notifications
            SET status = 'cancelled', seen_at = ?
            WHERE ticket_id = ? AND user_id = ? AND status = 'pending'
        """, (now, ticket_id, user_id))
        conn.commit()
    finally:
        conn.close()

def get_notificaciones_pendientes(user_id: str) -> List[Dict[str, Any]]:
    """Obtiene notificaciones in-app pendientes para un usuario."""
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT tn.*, t.titulo, t.codigo, t.severidad, t.categoria
            FROM ticket_notifications tn
            JOIN tickets t ON t.id = tn.ticket_id
            WHERE tn.user_id = ? AND tn.channel = 'app'
              AND tn.status IN ('pending', 'sent')
            ORDER BY tn.created_at DESC
            LIMIT 50
        """, (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def log_notification_attempt(
    notification_id: int,
    *,
    attempt_no: int,
    attempt_type: str,
    channel: str,
    status: str,
    provider: str = "",
    adapter_mode: str = "",
    provider_ref: str = "",
    http_status: Optional[int] = None,
    latency_ms: Optional[int] = None,
    error: str = "",
    idempotency_key: Optional[str] = None,
) -> None:
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO ticket_notification_attempts
               (notification_id, attempt_no, attempt_type, channel, provider, adapter_mode, status,
                provider_ref, http_status, latency_ms, error, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(notification_id),
                max(0, int(attempt_no)),
                (attempt_type or "dispatch").strip().lower(),
                normalize_channel_name(channel) or "unknown",
                (provider or "").strip(),
                normalize_adapter_mode(adapter_mode),
                (status or "").strip().lower() or "unknown",
                (provider_ref or "").strip(),
                http_status if http_status is not None else None,
                latency_ms if latency_ms is not None else None,
                (error or "").strip(),
                (idempotency_key or "").strip()[:128],
                db.now_utc_iso(),
            ),
        )
        conn.commit()
    except Exception as e:
        # Logging best effort: no impacta el flujo principal de entrega.
        logger.warning(f"[ticket_notifications] intento no pudo registrarse para {notification_id}: {e}")
    finally:
        conn.close()

def _get_auto_close_hours() -> int:
    """Recupera el tiempo de auto-cierre configurado en system_settings."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'ticket_auto_close_time'").fetchone()
        if row and row["value"]:
            try:
                return max(1, int(row["value"]))
            except ValueError:
                pass
    except Exception as e:
        logger.warning(f"Error al recuperar ticket_auto_close_time: {e}")
    finally:
        conn.close()
    return 24

def notify_client_resolution(ticket: Dict[str, Any]) -> None:
    """Envía un correo al cliente informando que el ticket ha sido resuelto."""
    from ._crud import get_ticket  # noqa: PLC0415
    from ._email import _build_ticket_thread_headers, _update_ticket_thread_metadata  # noqa: PLC0415
    ticket_id = int(ticket["id"])
    # Recargar ticket para capturar metadatos de hilo actualizados (evitar carrera con asignación)
    ticket = get_ticket(ticket_id) or ticket
    to_email, cc_emails, bcc_emails, to_record = _compose_reply_recipients(ticket)

    if not to_email or "@" not in to_email:
        return

    conn = db.get_conn()
    try:
        subject, body_html = _render_ticketera_mail_template(
            conn,
            MAIL_TEMPLATE_KEY_RESOLUTION,
            _ticketera_template_context(ticket=ticket, auto_close_hours=_get_auto_close_hours()),
        )
        headers = _build_ticket_thread_headers(ticket)
        now = db.now_utc_iso()
        send_meta = email_sender.send_email_advanced(
            to_email=to_email,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            html_body=body_html,
            headers=headers
        )
        conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, created_at)
               VALUES (?, 'outgoing', ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticket_id,
                send_meta.get("from_addr") or "soporte",
                to_record or to_email,
                ", ".join(cc_emails),
                ", ".join(bcc_emails),
                subject,
                body_html,
                now
            )
        )
        # Actualizar metadatos de hilo para que el próximo correo se enganche a este
        _update_ticket_thread_metadata(
            conn,
            ticket_id,
            message_id=send_meta.get("message_id"),
            in_reply_to=headers.get("In-Reply-To"),
            references=headers.get("References")
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Error al enviar correo de resolución para ticket {ticket_id}: {e}")
    finally:
        conn.close()

async def _schedule_next_process_notifications(delay_seconds: int = 60) -> None:
    next_run = (datetime.now(timezone.utc) + timedelta(seconds=max(5, int(delay_seconds or 60)))).isoformat()
    await jobs_engine.enqueue_unique_job(
        "PROCESS_NOTIFICATIONS",
        {"recurring": True},
        max_retries=0,
        next_run_at=next_run,
        update_existing_next_run=False,
    )

async def process_pending_notifications(payload: Dict[str, Any] = None):
    """
    Busca notificaciones elegibles para canales externos y encola jobs por canal.
    La confirmación de entrega ocurre en el worker del canal (status=sent).
    """
    payload = payload or {}
    recurring = bool(payload.get("recurring", True))
    if not _channels_enabled():
        logger.info("[ticket_notifications] CHANNELS_ENABLED=false, ciclo de dispatch omitido.")
        if recurring:
            # Evitar churn cuando canales externos están deshabilitados.
            await _schedule_next_process_notifications(delay_seconds=600)
        return

    claimed_rows: List[Dict[str, Any]] = []
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        conn.execute(
            """UPDATE ticket_notifications
               SET status = 'failed',
                   last_error = CASE
                       WHEN COALESCE(last_error, '') = '' THEN 'Max attempts alcanzado'
                       ELSE last_error
                   END,
                   error = CASE
                       WHEN COALESCE(error, '') = '' THEN 'Max attempts alcanzado'
                       ELSE error
                   END,
                   locked_at = NULL,
                   updated_at = ?
               WHERE status = 'pending'
                 AND channel IN ('google_chat')
                 AND COALESCE(attempt_count, 0) >= COALESCE(NULLIF(max_attempts, 0), ?)""",
            (now, CHANNELS_MAX_ATTEMPTS),
        )
        rows = conn.execute(
            """WITH eligible AS (
                   SELECT tn.id
                   FROM ticket_notifications tn
                   WHERE tn.status = 'pending'
                     AND tn.channel IN ('google_chat')
                     AND COALESCE(tn.next_retry_at, tn.scheduled_at)::timestamptz <= ?::timestamptz
                     AND COALESCE(tn.attempt_count, 0) < COALESCE(NULLIF(tn.max_attempts, 0), ?)
                   ORDER BY COALESCE(tn.next_retry_at, tn.scheduled_at) ASC, tn.id ASC
                   LIMIT 50
               )
               UPDATE ticket_notifications tn
               SET status = 'dispatching',
                   locked_at = ?,
                   updated_at = ?
               FROM eligible e
               WHERE tn.id = e.id
                 AND tn.status = 'pending'
               RETURNING tn.id, tn.channel""",
            (now, CHANNELS_MAX_ATTEMPTS, now, now),
        ).fetchall()
        claimed_rows = [dict(r) for r in rows]
        conn.commit()
    finally:
        conn.close()

    if claimed_rows:
        for row in claimed_rows:
            notif_id = int(row["id"])
            channel = normalize_channel_name(row.get("channel"))
            job_type = "GOOGLE_CHAT_NOTIFY" if channel == "google_chat" else ""
            if not job_type:
                conn = db.get_conn()
                try:
                    now_fail = db.now_utc_iso()
                    error_msg = f"Canal no soportado: {row.get('channel')}"
                    conn.execute(
                        """UPDATE ticket_notifications
                           SET status='failed',
                               last_error=?,
                               error=?,
                               locked_at=NULL,
                               updated_at=?
                           WHERE id=?""",
                        (error_msg, error_msg, now_fail, notif_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                continue

            try:
                await jobs_engine.enqueue_job(job_type, {"notification_id": notif_id}, max_retries=0)
            except Exception as enqueue_error:
                logger.error(f"[ticket_notifications] Error encolando notification_id={notif_id}: {enqueue_error}")
                conn = db.get_conn()
                try:
                    now_fail = db.now_utc_iso()
                    conn.execute(
                        """UPDATE ticket_notifications
                           SET status='pending',
                               last_error=?,
                               error=?,
                               locked_at=NULL,
                               updated_at=?
                           WHERE id=?""",
                        (str(enqueue_error), str(enqueue_error), now_fail, notif_id),
                    )
                    conn.commit()
                finally:
                    conn.close()

    if recurring:
        await _schedule_next_process_notifications(delay_seconds=60)

def get_jobs_queue_health() -> Dict[str, Any]:
    """
    Métricas operativas de cola para jobs críticos de Ticketera.
    """
    now_iso = db.now_utc_iso()
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT job_type,
                      COUNT(*) FILTER (
                          WHERE status = 'PENDING'
                            AND next_run_at::timestamptz <= ?::timestamptz
                      ) AS due_now,
                      COUNT(*) FILTER (
                          WHERE status = 'RUNNING'
                            AND updated_at::timestamptz < ?::timestamptz
                      ) AS stale_running,
                      COUNT(*) FILTER (
                          WHERE created_at::timestamptz >= (?::timestamptz - INTERVAL '60 minutes')
                      ) AS created_last_hour
               FROM sys_jobs
               WHERE job_type IN ('EMAIL_POLLING', 'PROCESS_NOTIFICATIONS', 'CHECK_TICKET_SLA', 'TKS_SLA_EVALUATE',
                                  'COMPLIANCE_EXPORT_DAILY', 'COMPLIANCE_PURGE_DAILY', 'GOOGLE_CHAT_NOTIFY')
               GROUP BY job_type
               ORDER BY job_type""",
            (now_iso, stale_cutoff, now_iso),
        ).fetchall()
        by_job_type: Dict[str, Dict[str, int]] = {}
        totals = {"due_now": 0, "stale_running": 0, "created_last_hour": 0}
        for row in rows:
            job_type = str(row.get("job_type") or "")
            metrics = {
                "due_now": int(row.get("due_now") or 0),
                "stale_running": int(row.get("stale_running") or 0),
                "created_last_hour": int(row.get("created_last_hour") or 0),
            }
            by_job_type[job_type] = metrics
            totals["due_now"] += metrics["due_now"]
            totals["stale_running"] += metrics["stale_running"]
            totals["created_last_hour"] += metrics["created_last_hour"]
        return {
            "generated_at": now_iso,
            "stale_cutoff": stale_cutoff,
            "by_job_type": by_job_type,
            "totals": totals,
        }
    finally:
        conn.close()

def get_channels_status() -> Dict[str, Any]:
    now = db.now_utc_iso()
    adapters = {
        "google_chat": {
            "mode": _channel_adapter_mode("google_chat"),
            "provider": _channel_provider_name("google_chat"),
            "configured": bool((getattr(app_settings, "GOOGLE_CHAT_SPACE_WEBHOOK", "") or "").strip()),
        },
    }
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT channel, status, COUNT(*) AS total
               FROM ticket_notifications
               WHERE channel IN ('google_chat')
               GROUP BY channel, status"""
        ).fetchall()
        queue = {"by_channel": {"google_chat": {}}, "totals": {}}
        for row in rows:
            channel = normalize_channel_name(row.get("channel"))
            status = normalize_notification_status(row.get("status"))
            total = int(row.get("total") or 0)
            if channel == "google_chat":
                queue["by_channel"][channel][status] = total
            queue["totals"][status] = int(queue["totals"].get(status, 0)) + total

        due_row = conn.execute(
            """SELECT COUNT(*) AS total
               FROM ticket_notifications
               WHERE channel IN ('google_chat')
                 AND status = 'pending'
                 AND COALESCE(next_retry_at, scheduled_at)::timestamptz <= ?::timestamptz""",
            (now,),
        ).fetchone()
    finally:
        conn.close()

    return {
        "channels_enabled": _channels_enabled(),
        "max_attempts_default": CHANNELS_MAX_ATTEMPTS,
        "retry_policy": {
            "base_seconds": CHANNELS_RETRY_BASE_SECONDS,
            "max_seconds": CHANNELS_RETRY_MAX_SECONDS,
        },
        "adapters": adapters,
        "queue": queue,
        "pending_due_now": int((due_row or {}).get("total") or 0),
        "generated_at": now,
    }

def list_channel_notifications(
    status: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    status_norm = normalize_notification_status(status, default_status="")
    channel_norm = normalize_channel_name(channel)

    where = ["tn.channel IN ('google_chat')"]
    params: List[Any] = []
    if status_norm:
        where.append("tn.status = ?")
        params.append(status_norm)
    if channel_norm == "google_chat":
        where.append("tn.channel = ?")
        params.append(channel_norm)
    where_sql = " AND ".join(where)

    conn = db.get_conn()
    try:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM ticket_notifications tn WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT tn.id, tn.ticket_id, tn.user_id, tn.channel, tn.status,
                       tn.provider, tn.provider_ref, tn.attempt_count, tn.max_attempts,
                       tn.scheduled_at, tn.next_retry_at, tn.sent_at, tn.seen_at,
                       tn.last_error, tn.locked_at, tn.updated_at, tn.created_at,
                       tn.escalation_level, t.codigo, t.titulo
                FROM ticket_notifications tn
                JOIN tickets t ON t.id = tn.ticket_id
                WHERE {where_sql}
                ORDER BY COALESCE(tn.updated_at, tn.created_at) DESC, tn.id DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
        items = [dict(r) for r in rows]
    finally:
        conn.close()

    return {
        "items": items,
        "total": int((total_row or {}).get("c") or 0),
        "limit": limit,
        "offset": offset,
        "filters": {"status": status_norm or None, "channel": channel_norm or None},
    }

def retry_channel_notification(
    notification_id: int,
    actor: str,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    notif_id = int(notification_id)
    normalized_idem = (idempotency_key or "").strip()[:128]
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT *
               FROM ticket_notifications
               WHERE id = ?""",
            (notif_id,),
        ).fetchone()
        if not row:
            raise ValueError("Notificación no encontrada")
        item = dict(row)
        channel = normalize_channel_name(item.get("channel"))
        if channel != "google_chat":
            raise ValueError("Solo se permiten retries para canales externos (google_chat)")
        status_now = normalize_notification_status(item.get("status"))
        if status_now == "dispatching":
            raise ValueError("Notificación en curso de despacho; espere a que termine")

        if normalized_idem:
            existing = conn.execute(
                """SELECT 1
                   FROM ticket_notification_attempts
                   WHERE notification_id = ?
                     AND attempt_type = 'manual_retry'
                     AND idempotency_key = ?
                   LIMIT 1""",
                (notif_id, normalized_idem),
            ).fetchone()
            if existing:
                latest = conn.execute(
                    "SELECT * FROM ticket_notifications WHERE id = ?",
                    (notif_id,),
                ).fetchone()
                out = dict(latest) if latest else item
                return {"ok": True, "duplicate_skipped": True, "item": out}

        conn.execute(
            """UPDATE ticket_notifications
               SET status = 'pending',
                   attempt_count = 0,
                   max_attempts = CASE
                       WHEN COALESCE(max_attempts, 0) <= 0 THEN ?
                       ELSE max_attempts
                   END,
                   next_retry_at = ?,
                   locked_at = NULL,
                   last_error = '',
                   error = '',
                   updated_at = ?
               WHERE id = ?""",
            (CHANNELS_MAX_ATTEMPTS, now, now, notif_id),
        )
        try:
            conn.execute(
                """INSERT INTO ticket_notification_attempts
                   (notification_id, attempt_no, attempt_type, channel, provider, adapter_mode, status,
                    provider_ref, http_status, latency_ms, error, idempotency_key, created_at)
                   VALUES (?, 0, 'manual_retry', ?, '', ?, 'accepted', '', NULL, NULL, ?, ?, ?)""",
                (
                    notif_id,
                    channel,
                    _channel_adapter_mode(channel),
                    f"manual_retry actor={actor}",
                    normalized_idem,
                    now,
                ),
            )
        except Exception as insert_error:
            if normalized_idem and "idx_tk_notif_attempts_idem" in str(insert_error):
                conn.rollback()
                latest = conn.execute(
                    "SELECT * FROM ticket_notifications WHERE id = ?",
                    (notif_id,),
                ).fetchone()
                out = dict(latest) if latest else item
                return {"ok": True, "duplicate_skipped": True, "item": out}
            raise
        conn.commit()
        refreshed = conn.execute("SELECT * FROM ticket_notifications WHERE id = ?", (notif_id,)).fetchone()
        result_item = dict(refreshed) if refreshed else {}
    finally:
        conn.close()

    _enqueue_job_async_safe("PROCESS_NOTIFICATIONS", {"recurring": False}, max_retries=0)
    return {"ok": True, "item": result_item, "queued": True, "duplicate_skipped": False}

