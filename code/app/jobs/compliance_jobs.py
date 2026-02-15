"""
Jobs recurrentes de Compliance Core para Ticketera.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.core import db, jobs_engine, tickets_service


def _next_run_iso(hour: int, minute: int) -> str:
    now_utc = datetime.now(timezone.utc)
    local_now = now_utc.astimezone(tickets_service.COMPLIANCE_TZ)
    target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local_now:
        target = target + timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat()


async def _schedule_next(job_type: str, payload: Dict[str, Any], hour: int, minute: int) -> None:
    next_run = _next_run_iso(hour, minute)
    conn = db.get_conn()
    try:
        exists = conn.execute(
            """SELECT 1
               FROM sys_jobs
               WHERE job_type = ?
                 AND status IN ('PENDING', 'RETRY')
                 AND next_run_at::timestamptz >= ?::timestamptz
               LIMIT 1""",
            (job_type, next_run),
        ).fetchone()
    finally:
        conn.close()

    if exists:
        return

    await jobs_engine.enqueue_job(job_type, payload=payload, max_retries=1)
    conn2 = db.get_conn()
    try:
        conn2.execute(
            """UPDATE sys_jobs
               SET next_run_at = ?
               WHERE id = (
                   SELECT MAX(id)
                   FROM sys_jobs
                   WHERE job_type = ?
               )""",
            (next_run, job_type),
        )
        conn2.commit()
    finally:
        conn2.close()


async def compliance_export_daily(payload: Dict[str, Any] = None) -> None:
    payload = payload or {}
    local_now = datetime.now(timezone.utc).astimezone(tickets_service.COMPLIANCE_TZ)
    day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    from_local = day_start_local - timedelta(days=1)
    to_local = day_start_local
    idem = f"compliance-export-{from_local.date().isoformat()}"

    try:
        tickets_service.run_compliance_export(
            actor="system:compliance_export_daily",
            from_ts=from_local.astimezone(timezone.utc).isoformat(),
            to_ts=to_local.astimezone(timezone.utc).isoformat(),
            scope="both",
            idempotency_key=idem,
        )
    except Exception as e:
        print(f"[ComplianceJob] Export daily failed: {e}")

    if payload.get("recurring", True):
        await _schedule_next(
            "COMPLIANCE_EXPORT_DAILY",
            {"recurring": True},
            tickets_service.COMPLIANCE_EXPORT_HOUR,
            tickets_service.COMPLIANCE_EXPORT_MINUTE,
        )


async def compliance_purge_daily(payload: Dict[str, Any] = None) -> None:
    payload = payload or {}
    local_now = datetime.now(timezone.utc).astimezone(tickets_service.COMPLIANCE_TZ)
    idem = f"compliance-purge-{local_now.date().isoformat()}"

    try:
        tickets_service.run_compliance_purge(
            actor="system:compliance_purge_daily",
            dry_run=False,
            as_of=datetime.now(timezone.utc).isoformat(),
            max_tickets=500,
            idempotency_key=idem,
        )
    except Exception as e:
        print(f"[ComplianceJob] Purge daily failed: {e}")

    if payload.get("recurring", True):
        await _schedule_next(
            "COMPLIANCE_PURGE_DAILY",
            {"recurring": True},
            tickets_service.COMPLIANCE_PURGE_HOUR,
            tickets_service.COMPLIANCE_PURGE_MINUTE,
        )
