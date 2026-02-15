"""
Jobs recurrentes para paralelo Jira + MONSTRUO.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.core import db, jobs_engine, tickets_service


def _next_run_iso(hour: int, minute: int = 0) -> str:
    now_utc = datetime.now(timezone.utc)
    local_now = now_utc.astimezone(tickets_service.JIRA_SYNC_TZ)
    target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= local_now:
        target = target + timedelta(days=1)
    return target.astimezone(timezone.utc).isoformat()


async def _schedule_next(job_type: str, payload: Dict[str, Any], hour: int, minute: int = 0) -> None:
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


async def jira_delta_sync_daily(payload: Dict[str, Any] = None) -> None:
    payload = payload or {}
    actor = "system:jira_delta_sync_daily"
    dry_run = bool(payload.get("dry_run", False))
    limit = int(payload.get("limit", tickets_service.JIRA_SYNC_DEFAULT_LIMIT) or tickets_service.JIRA_SYNC_DEFAULT_LIMIT)

    if not tickets_service.JIRA_SYNC_ENABLED:
        print("[JiraParallelJob] Delta daily skipped: JIRA_SYNC_ENABLED=false")
    else:
        try:
            tickets_service.run_jira_delta_sync(
                actor=actor,
                dry_run=dry_run,
                issues=None,
                project_keys=None,
                limit=limit,
                since=None,
            )
        except Exception as e:
            # Debe fallar controlado y nunca romper el worker principal.
            print(f"[JiraParallelJob] Delta daily failed: {e}")

    try:
        tickets_service.record_parallel_kpi_snapshot(source="parallel_daily_job")
    except Exception as e:
        print(f"[JiraParallelJob] KPI snapshot failed: {e}")

    if payload.get("recurring", True):
        await _schedule_next(
            "JIRA_DELTA_SYNC_DAILY",
            {"recurring": True, "dry_run": False},
            tickets_service.JIRA_SYNC_DAILY_HOUR,
            0,
        )
