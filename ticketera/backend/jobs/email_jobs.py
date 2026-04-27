import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from plataforma.core import db, email, email_integration, jobs_engine
from ticketera.backend import service as tickets_service

logger = logging.getLogger(__name__)

async def poll_email_job(payload: dict):
    print("[JobEngine] Polling emails...")
    payload = payload or {}
    interval = 120

    def _sync_poll():
        processor = email_integration.EmailProcessor()
        found_interval = 120
        try:
            processor.connect()
            emails = processor.fetch_unread()
            if emails:
                print(f"[JobEngine] Found {len(emails)} unread emails.")
            else:
                pass

            for email_data in emails:
                try:
                    tickets_service.handle_incoming_email(email_data)
                except Exception as e:
                    print(f"[JobEngine] Error handling email {email_data.get('message_id')}: {e}")
        except Exception as e:
            print(f"[JobEngine] Email polling error: {e}")
        finally:
            processor.close()
            try:
                if processor.config:
                    found_interval = int(processor.config.get("email_polling_interval", 120) or 120)
            except Exception:
                pass
        return found_interval

    interval = await asyncio.to_thread(_sync_poll)
    interval = max(30, min(interval, 1800))
    if bool(payload.get("recurring", True)):
        await jobs_engine.enqueue_unique_job(
            "EMAIL_POLLING",
            {"recurring": True},
            max_retries=0,
            next_run_at=jobs_engine._next_run_iso(interval),
            update_existing_next_run=False,
        )

async def send_auto_response_job(payload: dict):
    raw_ticket_id = payload.get("ticket_id")
    if raw_ticket_id is None:
        raise ValueError("payload.ticket_id requerido")
    ticket_id = int(raw_ticket_id)

    to_email = tickets_service._normalize_email_address(payload.get("email"))
    if not to_email:
        raise ValueError("payload.email inválido")

    idempotency_key = (payload.get("idempotency_key") or "").strip()[:128]
    if not idempotency_key:
        idempotency_key = tickets_service._auto_reply_idempotency_key(ticket_id, to_email)

    lock_conn = db.get_conn()
    lock_acquired = False
    marker_id = None
    now = db.now_utc_iso()

    try:
        try:
            lock_row = lock_conn.execute(
                "SELECT pg_try_advisory_lock(?) AS locked",
                (ticket_id,),
            ).fetchone()
            lock_acquired = bool(lock_row and lock_row.get("locked"))
        except Exception:
            lock_acquired = True

        if not lock_acquired:
            raise RuntimeError(f"ticket lock busy: {ticket_id}")

        ticket = tickets_service.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket no encontrado: {ticket_id}")

        allowed, reason = tickets_service._auto_reply_sender_allowed(to_email)
        if not allowed:
            logger.info(f"[AUTO_REPLY] skip ticket={ticket_id} to={to_email}: {reason}")
            lock_conn.execute(
                """UPDATE ticket_emails
                   SET direction='auto_reply_skipped'
                   WHERE ticket_id = ?
                     AND direction='auto_reply_pending'
                     AND idempotency_key = ?""",
                (ticket_id, idempotency_key),
            )
            lock_conn.commit()
            return

        sent_row = lock_conn.execute(
            """SELECT id
               FROM ticket_emails
               WHERE ticket_id = ?
                 AND direction = 'auto_reply'
                 AND idempotency_key = ?
               ORDER BY id DESC
               LIMIT 1""",
            (ticket_id, idempotency_key),
        ).fetchone()
        if sent_row:
            logger.info(f"[AUTO_REPLY] duplicate skipped ticket={ticket_id} key={idempotency_key}")
            return

        pending_row = lock_conn.execute(
            """SELECT id
               FROM ticket_emails
               WHERE ticket_id = ?
                 AND direction = 'auto_reply_pending'
                 AND idempotency_key = ?
               ORDER BY id DESC
               LIMIT 1""",
            (ticket_id, idempotency_key),
        ).fetchone()
        if pending_row:
            marker_id = int(pending_row["id"])
        else:
            marker = lock_conn.execute(
                """INSERT INTO ticket_emails
                   (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, idempotency_key, created_at)
                   VALUES (?, 'auto_reply_pending', '', ?, '', '', '[]', ?, ?)
                   RETURNING id""",
                (ticket_id, to_email, idempotency_key, now),
            ).fetchone()
            marker_id = int(marker["id"]) if marker else None
            lock_conn.commit()

        subject = tickets_service._auto_reply_subject(
            lock_conn,
            ticket,
            str(payload.get("nombre") or ticket.get("cliente_nombre") or "cliente"),
            str(payload.get("asignado_a") or ticket.get("asignado_a") or ""),
        )
        body = tickets_service._auto_reply_body(
            lock_conn,
            ticket,
            str(payload.get("nombre") or ticket.get("cliente_nombre") or "cliente"),
            str(payload.get("asignado_a") or ticket.get("asignado_a") or ""),
        )

        base_headers = tickets_service._build_ticket_thread_headers(ticket)
        payload_in_reply_to = tickets_service._normalize_message_id(payload.get("in_reply_to"))
        payload_references = tickets_service._merge_reference_chain(payload.get("references"), payload_in_reply_to)
        in_reply_to = payload_in_reply_to or base_headers.get("In-Reply-To")
        references = tickets_service._merge_reference_chain(
            base_headers.get("References"),
            payload_references,
            in_reply_to,
        )
        headers = {}
        if in_reply_to:
            headers["In-Reply-To"] = in_reply_to
        if references:
            headers["References"] = references

        send_meta = email.send_email_advanced(
            to_email=to_email,
            subject=subject,
            html_body=body,
            headers=headers or None,
        )
        if isinstance(send_meta, bool) and not send_meta:
            raise RuntimeError("SMTP envío devolvió False")
        if isinstance(send_meta, dict) and send_meta.get("ok") is False:
            raise RuntimeError("SMTP envío rechazado")

        lock_conn.execute(
            """UPDATE ticket_emails
               SET direction = 'auto_reply',
                   from_addr = ?,
                   to_addr = ?,
                   subject = ?,
                   body_html = ?,
                   attachments_json = '[]'
               WHERE id = ?""",
            (
                str((send_meta or {}).get("from_addr") or ""),
                to_email,
                subject,
                body,
                marker_id,
            ),
        )
        tickets_service._emit_system_comment(
            lock_conn,
            ticket_id,
            "[CAMBIO_ESTADO] Estado: cambiado a auto-respondido",
            now,
            author_id="system",
        )
        lock_conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        tickets_service._update_ticket_thread_metadata(
            lock_conn,
            ticket_id,
            message_id=(send_meta or {}).get("message_id"),
            in_reply_to=in_reply_to,
            references=references,
        )
        lock_conn.commit()
        logger.info(
            f"[AUTO_REPLY] sent ticket={ticket_id} to={to_email} key={idempotency_key}"
        )
    except Exception as e:
        logger.error(f"[AUTO_REPLY] failed ticket={ticket_id} to={to_email}: {e}")
        raise
    finally:
        if lock_acquired:
            try:
                lock_conn.execute("SELECT pg_advisory_unlock(?)", (ticket_id,))
                lock_conn.execute("SELECT pg_advisory_unlock(?)", (ticket_id,))
            except Exception:
                pass
        lock_conn.close()

async def auto_close_tickets_job(payload: dict):
    logger.info("[JobEngine] Revisando tickets para Auto-Cierre...")
    conn = db.get_conn()
    now = db.now_utc_iso()
    interval_horas = 24

    try:
        row = conn.execute("SELECT value FROM system_settings WHERE key = 'ticket_auto_close_time'").fetchone()
        if row and row["value"]:
            try:
                interval_horas = max(1, int(row["value"]))
            except ValueError:
                pass
        
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=interval_horas)).isoformat()
        stale_tickets = conn.execute(
            """SELECT id
               FROM tickets
               WHERE estado = 'resuelto'
                 AND updated_at::timestamptz <= ?::timestamptz""",
            (cutoff,),
        ).fetchall()

        count = 0
        for t in stale_tickets:
            tid = int(t["id"])
            try:
                tickets_service.update_ticket(
                    ticket_id=tid,
                    updates={"estado": "cerrado"},
                    actor_id="system",
                    actor_role="admin"
                )
                
                conn.execute(
                    """INSERT INTO ticket_comments (ticket_id, user_id, content, is_internal, created_at)
                       VALUES (?, 'system', ?, 1, ?)""",
                    (tid, f"El ticket ha sido CERRADO automáticamente por alcanzar el plazo de inactividad de {interval_horas} Hrs.", now),
                )
                conn.commit()
                count += 1
            except Exception as e:
                logger.error(f"[JobEngine] Error al auto-cerrar ticket {tid}: {e}")
                conn.rollback()

        if count > 0:
            logger.info(f"[JobEngine] Se auto-cerraron {count} tickets.")
    except Exception as e:
        logger.error(f"[JobEngine] Error general auto-cerrando tickets: {e}")
    finally:
        conn.close()

    if bool(payload.get("recurring", True)):
        await jobs_engine.enqueue_unique_job(
            "AUTO_CLOSE_TICKETS",
            {"recurring": True},
            max_retries=0,
            next_run_at=jobs_engine._next_run_iso(3 * 3600),
            update_existing_next_run=False,
        )
