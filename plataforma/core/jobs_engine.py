import asyncio
import json
import traceback
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

from core import db

# Configuration
POLL_INTERVAL = 30  # seconds
JOB_HANDLERS: Dict[str, Callable] = {}
logger = logging.getLogger(__name__)

def register_job(job_type: str, handler: Callable) -> None:
    """Register a python function to a job type string."""
    JOB_HANDLERS[job_type] = handler

def _as_payload_json(payload: Optional[dict]) -> str:
    return json.dumps(payload or {}, ensure_ascii=False)


def _next_run_iso(delay_seconds: int = 0) -> str:
    delay = max(0, int(delay_seconds or 0))
    return (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()


def _normalize_max_retries(value: Any, default: int = 3) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(0, min(parsed, 20))


async def enqueue_job(
    job_type: str,
    payload: Optional[dict] = None,
    max_retries: int = 3,
    next_run_at: Optional[str] = None,
) -> int:
    """Enqueue a job. Returns inserted job id."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        row = conn.execute(
            """INSERT INTO sys_jobs 
               (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
               VALUES (?, 'PENDING', ?, ?, 0, ?, ?, ?)
               RETURNING id""",
            (
                str(job_type or "").strip(),
                _as_payload_json(payload),
                (next_run_at or now),
                _normalize_max_retries(max_retries, 3),
                now,
                now,
            ),
        ).fetchone()
        conn.commit()
        return int(row["id"]) if row and row.get("id") is not None else 0
    finally:
        conn.close()


async def enqueue_unique_job(
    job_type: str,
    payload: Optional[dict] = None,
    *,
    max_retries: int = 3,
    next_run_at: Optional[str] = None,
    update_existing_next_run: bool = False,
) -> Dict[str, Any]:
    """
    Enqueue a recurring job only if there is no PENDING/RETRY row for the same type.
    Returns metadata: {enqueued, duplicate, job_id}.
    """
    normalized_job = str(job_type or "").strip()
    if not normalized_job:
        raise ValueError("job_type requerido")

    target_run_at = (next_run_at or db.now_utc_iso())
    conn = db.get_conn()
    try:
        existing = conn.execute(
            """SELECT id, next_run_at
               FROM sys_jobs
               WHERE job_type = ?
                 AND status IN ('PENDING', 'RETRY')
               ORDER BY next_run_at ASC, id ASC
               LIMIT 1""",
            (normalized_job,),
        ).fetchone()
        if existing:
            existing_id = int(existing["id"])
            if update_existing_next_run:
                conn.execute(
                    """UPDATE sys_jobs
                       SET next_run_at = LEAST(next_run_at::timestamptz, ?::timestamptz)::text,
                           updated_at = ?
                       WHERE id = ?""",
                    (target_run_at, db.now_utc_iso(), existing_id),
                )
                conn.commit()
            return {"enqueued": False, "duplicate": True, "job_id": existing_id}

        inserted = conn.execute(
            """INSERT INTO sys_jobs
               (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
               VALUES (?, 'PENDING', ?, ?, 0, ?, ?, ?)
               RETURNING id""",
            (
                normalized_job,
                _as_payload_json(payload),
                target_run_at,
                _normalize_max_retries(max_retries, 3),
                db.now_utc_iso(),
                db.now_utc_iso(),
            ),
        ).fetchone()
        conn.commit()
        return {"enqueued": True, "duplicate": False, "job_id": int(inserted["id"])}
    except Exception as e:
        conn.rollback()
        # Handle race condition when partial unique indexes are enabled.
        if "idx_sys_jobs_unique_pending_email" in str(e) or "idx_sys_jobs_unique_pending_notifications" in str(e):
            existing = conn.execute(
                """SELECT id
                   FROM sys_jobs
                   WHERE job_type = ?
                     AND status IN ('PENDING', 'RETRY')
                   ORDER BY next_run_at ASC, id ASC
                   LIMIT 1""",
                (normalized_job,),
            ).fetchone()
            return {
                "enqueued": False,
                "duplicate": True,
                "job_id": int(existing["id"]) if existing else 0,
            }
        raise
    finally:
        conn.close()


def recover_stale_running_jobs(stale_minutes: int = 20) -> Dict[str, Any]:
    """
    Move stale RUNNING jobs to RETRY. Returns summary by job_type.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max(1, int(stale_minutes or 20)))).isoformat()
    now = db.now_utc_iso()
    stale_marker = (
        f"[RECOVER_STALE] moved to RETRY at {now} because RUNNING exceeded {max(1, int(stale_minutes or 20))}m."
    )
    skipped_marker = (
        f"[RECOVER_STALE] stale RUNNING could not move to RETRY at {now} due to active PENDING/RETRY for same recurring job_type."
    )
    unique_recurring_types = {"EMAIL_POLLING", "PROCESS_NOTIFICATIONS"}
    conn = db.get_conn()
    try:
        stale_rows = conn.execute(
            """SELECT id, job_type
               FROM sys_jobs
               WHERE status = 'RUNNING'
                 AND updated_at::timestamptz < ?::timestamptz
               ORDER BY updated_at::timestamptz ASC, id ASC""",
            (cutoff,),
        ).fetchall()
        recovered_rows = []
        skipped_duplicates = 0
        for row in stale_rows:
            job_id = int(row["id"])
            job_type = str(row.get("job_type") or "")
            can_move_to_retry = True
            if job_type in unique_recurring_types:
                existing = conn.execute(
                    """SELECT id
                       FROM sys_jobs
                       WHERE job_type = ?
                         AND status IN ('PENDING', 'RETRY')
                         AND id <> ?
                       ORDER BY id ASC
                       LIMIT 1""",
                    (job_type, job_id),
                ).fetchone()
                can_move_to_retry = not bool(existing)

            if can_move_to_retry:
                conn.execute(
                    """UPDATE sys_jobs
                       SET status = 'RETRY',
                           next_run_at = ?,
                           updated_at = ?,
                           last_error = CASE
                               WHEN COALESCE(last_error, '') = '' THEN ?
                               ELSE (last_error || E'\n' || ?)
                           END
                       WHERE id = ?""",
                    (now, now, stale_marker, stale_marker, job_id),
                )
                recovered_rows.append({"id": job_id, "job_type": job_type})
            else:
                conn.execute(
                    """UPDATE sys_jobs
                       SET status = 'FAILED',
                           updated_at = ?,
                           last_error = CASE
                               WHEN COALESCE(last_error, '') = '' THEN ?
                               ELSE (last_error || E'\n' || ?)
                           END
                       WHERE id = ?""",
                    (now, skipped_marker, skipped_marker, job_id),
                )
                skipped_duplicates += 1
        conn.commit()
        by_type: Dict[str, int] = {}
        for row in recovered_rows:
            job_type = str(row.get("job_type") or "unknown")
            by_type[job_type] = by_type.get(job_type, 0) + 1
        return {
            "recovered": len(recovered_rows),
            "skipped_duplicates": skipped_duplicates,
            "by_type": by_type,
            "cutoff": cutoff,
        }
    finally:
        conn.close()


def cleanup_old_jobs(retention_days: int = 14) -> Dict[str, Any]:
    keep_days = max(1, min(int(retention_days or 14), 365))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
    conn = db.get_conn()
    try:
        row = conn.execute(
            """DELETE FROM sys_jobs
               WHERE status IN ('COMPLETED', 'FAILED')
                 AND updated_at::timestamptz < ?::timestamptz
               RETURNING id""",
            (cutoff,),
        ).fetchall()
        conn.commit()
        return {"deleted": len(row), "cutoff": cutoff, "retention_days": keep_days}
    finally:
        conn.close()


async def process_job(job_row):
    """Execute a single job with retry logic."""
    job_id = int(job_row["id"])
    job_type = str(job_row["job_type"])
    payload_str = job_row.get("payload") or "{}"
    retries = int(job_row.get("retries_count") or 0)
    max_retries = _normalize_max_retries(job_row.get("max_retries"), 3)

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
        payload = json.loads(payload_str) if isinstance(payload_str, str) else (payload_str or {})
        if not isinstance(payload, dict):
            payload = {}
        
        # Execute (Sync or Async support?)
        # For simplicity, we assume handlers are functions we can call. 
        # If they are async, we await them. If sync, we run in thread.
        if asyncio.iscoroutinefunction(handler):
            await handler(payload)
        else:
            await asyncio.to_thread(handler, payload)
            
        # Success
        conn.execute("UPDATE sys_jobs SET status='COMPLETED', updated_at=? WHERE id=?", (db.now_utc_iso(), job_id))

    except Exception as e:
        error_msg = str(e) + "\n" + traceback.format_exc()
        print(f"[JobEngine] Job {job_id} ({job_type}) FAILED: {e}")

        if retries < max_retries:
            # Backoff: 2^retries * 60 seconds
            delay = (2 ** retries) * 60
            next_run = _next_run_iso(delay)
            conn.execute(
                "UPDATE sys_jobs SET status='RETRY', retries_count=retries_count+1, next_run_at=?, last_error=?, updated_at=? WHERE id=?",
                (next_run, error_msg, db.now_utc_iso(), job_id)
            )
        else:
            # DLQ
            conn.execute(
                "UPDATE sys_jobs SET status='FAILED', last_error=?, updated_at=? WHERE id=?",
                (error_msg, db.now_utc_iso(), job_id)
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
            row = conn.execute(
                """WITH candidate AS (
                       SELECT id
                       FROM sys_jobs
                       WHERE status IN ('PENDING', 'RETRY')
                         AND next_run_at::timestamptz <= ?::timestamptz
                       ORDER BY next_run_at::timestamptz ASC, id ASC
                       LIMIT 1
                       FOR UPDATE SKIP LOCKED
                   )
                   UPDATE sys_jobs j
                   SET status = 'RUNNING',
                       updated_at = ?
                   FROM candidate c
                   WHERE j.id = c.id
                   RETURNING j.id, j.job_type, j.payload, j.retries_count, j.max_retries""",
                (now, now),
            ).fetchone()
            conn.commit()
            conn.close()  # Free connection for execution phase

            if row:
                await process_job(dict(row))
                continue

            # No jobs, sleep
            await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            print("[JobEngine] Stopping worker.")
            break
        except Exception as e:
            print(f"[JobEngine] Loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)

# ==========================================================================
# SYSTEM JOBS IMPL
# ==========================================================================

async def cleanup_sys_jobs_job(payload: Optional[dict] = None) -> None:
    payload = payload or {}
    retention_days = int(payload.get("retention_days", 14) or 14)
    result = cleanup_old_jobs(retention_days=retention_days)
    logger.info(
        "[JobEngine] cleanup sys_jobs deleted=%s retention_days=%s cutoff=%s",
        result.get("deleted"),
        result.get("retention_days"),
        result.get("cutoff"),
    )
    if bool(payload.get("recurring", True)):
        await enqueue_unique_job(
            "CLEANUP_SYS_JOBS",
            {"recurring": True, "retention_days": retention_days},
            max_retries=1,
            next_run_at=_next_run_iso(24 * 60 * 60),
            update_existing_next_run=False,
        )

async def recover_stale_jobs_job(payload: dict):
    stale_minutes = int(payload.get("stale_minutes", 20) or 20)
    result = recover_stale_running_jobs(stale_minutes=stale_minutes)
    if result.get("recovered", 0) > 0:
        print(f"[JobEngine] Recovered {result['recovered']} stale jobs.")

    if bool(payload.get("recurring", True)):
        await enqueue_unique_job(
            "RECOVER_STALE_JOBS",
            {"recurring": True, "stale_minutes": stale_minutes},
            max_retries=1,
            next_run_at=_next_run_iso(10 * 60), # Cada 10 min
            update_existing_next_run=False,
        )

# Register default jobs
register_job("CLEANUP_SYS_JOBS", cleanup_sys_jobs_job)
register_job("RECOVER_STALE_JOBS", recover_stale_jobs_job)
