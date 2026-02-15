import asyncio
import json
import traceback
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict
from app.core import db

# Configuration
POLL_INTERVAL = 30  # seconds
JOB_HANDLERS: Dict[str, Callable] = {}
logger = logging.getLogger(__name__)

def register_job(job_type: str, handler: Callable):
    """Register a python function to a job type string."""
    JOB_HANDLERS[job_type] = handler

async def enqueue_job(job_type: str, payload: dict = {}, max_retries: int = 3):
    """Public helper to enqueue a job."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """INSERT INTO sys_jobs 
               (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
               VALUES (?, 'PENDING', ?, ?, 0, ?, ?, ?)""",
            (job_type, json.dumps(payload), now, max_retries, now, now)
        )
        conn.commit()
    finally:
        conn.close()

async def process_job(job_row):
    """Execute a single job with retry logic."""
    job_id, job_type, payload_str, retries, max_retries = job_row['id'], job_row['job_type'], job_row['payload'], job_row['retries_count'], job_row['max_retries']
    
    handler = JOB_HANDLERS.get(job_type)
    conn = db.get_conn()
    now = db.now_utc_iso()
    
    if not handler:
        # Fatal error, unknown handler
        conn.execute("UPDATE sys_jobs SET status='FAILED', last_error='Unknown Handler', updated_at=? WHERE id=?", (now, job_id))
        conn.commit()
        conn.close()
        return

    try:
        # Parse payload
        payload = json.loads(payload_str)
        
        # Execute (Sync or Async support?)
        # For simplicity, we assume handlers are functions we can call. 
        # If they are async, we await them. If sync, we run in thread.
        if asyncio.iscoroutinefunction(handler):
            await handler(payload)
        else:
            await asyncio.to_thread(handler, payload)
            
        # Success
        conn.execute("UPDATE sys_jobs SET status='COMPLETED', updated_at=? WHERE id=?", (now, job_id))
        
    except Exception as e:
        error_msg = str(e) + "\n" + traceback.format_exc()
        print(f"[JobEngine] Job {job_id} ({job_type}) FAILED: {e}")
        
        if retries < max_retries:
            # Backoff: 2^retries * 60 seconds
            delay = (2 ** retries) * 60
            next_run = (datetime.utcnow() + timedelta(seconds=delay)).isoformat()
            conn.execute(
                "UPDATE sys_jobs SET status='RETRY', retries_count=retries_count+1, next_run_at=?, last_error=?, updated_at=? WHERE id=?",
                (next_run, error_msg, now, job_id)
            )
        else:
            # DLQ
            conn.execute(
                "UPDATE sys_jobs SET status='FAILED', last_error=?, updated_at=? WHERE id=?",
                (error_msg, now, job_id)
            )
    finally:
        conn.commit()
        conn.close()

async def worker_loop():
    """Background loop to poll and execute jobs."""
    print("[JobEngine] Worker started.")
    while True:
        try:
            conn = db.get_conn()
            now = db.now_utc_iso()
            
            # Simple locking mechanism: UPDATE ... RETURN is not fully concurrent-safe in SQLite without proper transaction modes,
            # but for this scale (single instance), a simple SELECT ... then UPDATE is "okay" if we accept rare race conditions 
            # or if we only have 1 worker. 
            # Better strategy for SQLite: Transaction exclusive.
            
            cursor = conn.execute(
                "SELECT id, job_type, payload, retries_count, max_retries FROM sys_jobs WHERE status IN ('PENDING', 'RETRY') AND next_run_at <= ? ORDER BY next_run_at ASC LIMIT 1",
                (now,)
            )
            row = cursor.fetchone()
            
            if row:
                job_data = dict(row)
                # Lock it
                conn.execute("UPDATE sys_jobs SET status='RUNNING', updated_at=? WHERE id=?", (now, job_data['id']))
                conn.commit()
                conn.close() # Free connection for execution phase
                
                # Process
                await process_job(job_data)
                
                # Loop immediately to check for more jobs
                continue
            else:
                conn.close()
                
            # No jobs, sleep
            await asyncio.sleep(POLL_INTERVAL)
            
        except asyncio.CancelledError:
            print("[JobEngine] Stopping worker.")
            break
        except Exception as e:
            print(f"[JobEngine] Loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)

# ==========================================================================
# EMAIL JOBS IMPL
# ==========================================================================
async def poll_email_job(payload: dict):
    from app.core import email_integration, tickets_service
    
    print("[JobEngine] Polling emails...")
    processor = email_integration.EmailProcessor()
    try:
        processor.connect()
        emails = processor.fetch_unread()
        print(f"[JobEngine] Found {len(emails)} unread emails.")
        
        for email_data in emails:
            try:
                tickets_service.handle_incoming_email(email_data)
            except Exception as e:
                print(f"[JobEngine] Error handling email {email_data.get('message_id')}: {e}")
                
    except Exception as e:
        print(f"[JobEngine] Email polling error: {e}")
    finally:
        processor.close()

    # Re-schedule self
    interval = int(processor.config.get('email_polling_interval', 60)) if processor.config else 60
    await enqueue_job("EMAIL_POLLING", {}, max_retries=0)
    # Note: enqueue_job sets run_at=now. Ideally we want delay.
    # Hack: Update next_run_at manually or sleep? 
    # Better: Update the just-inserted job to delay
    conn = db.get_conn()
    try:
        next_run = (datetime.utcnow() + timedelta(seconds=interval)).isoformat()
        # Get last inserted ID? Or just trust the queue. 
        # A bit hacky to re-enqueue immediately. Let's stick to simple loop for now.
        # However, enqueue_job sets status=PENDING and next_run=now.
        # We need a proper scheduling mechanism. 
        # For MVP: Update the job we just inserted (highest ID)
        conn.execute("UPDATE sys_jobs SET next_run_at = ? WHERE id = (SELECT MAX(id) FROM sys_jobs WHERE job_type='EMAIL_POLLING')", (next_run,))
        conn.commit()
    finally:
        conn.close()

async def send_auto_response_job(payload: dict):
    from app.core import email, tickets_service

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
        # Lock por ticket para evitar doble ejecución concurrente.
        try:
            lock_row = lock_conn.execute(
                "SELECT pg_try_advisory_lock(?) AS locked",
                (ticket_id,),
            ).fetchone()
            lock_acquired = bool(lock_row and lock_row.get("locked"))
        except Exception:
            # Best effort en motores/driver sin soporte.
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

        code = str(ticket.get("codigo") or payload.get("ticket_code") or f"TK-{ticket_id}")
        subject = tickets_service._auto_reply_subject(ticket)
        body = tickets_service._auto_reply_body(
            str(payload.get("nombre") or ticket.get("cliente_nombre") or "cliente"),
            code,
            str(payload.get("asignado_a") or ticket.get("asignado_a") or "mesa_ayuda"),
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
        lock_conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, 'system', ?, ?)""",
            (ticket_id, f"[AUTO_REPLY] Auto-respuesta enviada a {to_email}.", now),
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
            except Exception:
                pass
        lock_conn.close()

# Register default jobs
register_job("EMAIL_POLLING", poll_email_job)
register_job("SEND_AUTO_RESPONSE", send_auto_response_job)
