from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends

from core import db, deps, security

router = APIRouter(prefix="/api/ops", tags=["ops"])
LEGACY_OPS_FALLBACK_URL = os.getenv(
    "LEGACY_OPS_FALLBACK_URL",
    "http://172.17.0.1:9000/api/ops/dashboard",
).strip()


def _fetchone_safe(conn, sql: str, params: tuple[Any, ...] = ()) -> Dict[str, Any]:
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else {}
    except Exception:
        return {}


def _fetchall_safe(conn, sql: str, params: tuple[Any, ...] = ()) -> list[Dict[str, Any]]:
    try:
        return [dict(item) for item in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def _normalize_recent_failures(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("recent_failures")
    if not isinstance(items, list):
        payload["recent_failures"] = []
        return payload

    normalized: list[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fixed = dict(item)
        if "error_msg" not in fixed:
            fixed["error_msg"] = fixed.get("last_error") or ""
        if "started_at" not in fixed:
            fixed["started_at"] = fixed.get("updated_at") or ""
        normalized.append(fixed)
    payload["recent_failures"] = normalized
    return payload


def _should_use_legacy_fallback(stats: Dict[str, Any]) -> bool:
    kpis = stats.get("kpis") if isinstance(stats.get("kpis"), dict) else {}
    return (
        (kpis.get("sales_today_count") or 0) == 0
        and float(kpis.get("sales_today_amount") or 0) == 0.0
        and (kpis.get("tickets_open") or 0) == 0
        and (kpis.get("tickets_critical") or 0) == 0
        and (kpis.get("total_customers") or 0) == 0
    )


def _fetch_legacy_dashboard(sess: Dict[str, Any]) -> Dict[str, Any] | None:
    if not LEGACY_OPS_FALLBACK_URL:
        return None

    token = security.create_access_token(
        sess["username"],
        sess["role"],
        roles=sess.get("roles"),
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(LEGACY_OPS_FALLBACK_URL, headers=headers)
        if response.status_code >= 400:
            return None
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        return _normalize_recent_failures(payload)
    except Exception:
        return None


@router.get("/dashboard", response_model=Dict[str, Any])
def get_dashboard_stats(
    sess: dict = Depends(deps.require_permission("dashboard:read")),
):
    conn = db.get_conn()
    try:
        stats: Dict[str, Any] = {
            "system_status": "healthy",
            "kpis": {},
            "jobs_health": {},
            "recent_failures": [],
        }

        today = db.now_utc_iso()[:10]

        row = _fetchone_safe(
            conn,
            "SELECT count(*) as cnt, sum(total_final) as total FROM invoices WHERE status = 'ISSUED' AND issued_at LIKE ?",
            (f"{today}%",),
        )
        sales_today_count = row.get("cnt") or 0
        sales_today_amount = row.get("total") or 0.0
        if sales_today_count == 0 and float(sales_today_amount or 0) == 0.0:
            row_laudus = _fetchone_safe(
                conn,
                """
                SELECT count(*) as cnt, sum(total_amount) as total
                FROM laudus_invoices
                WHERE doc_date LIKE ?
                """,
                (f"{today}%",),
            )
            sales_today_count = row_laudus.get("cnt") or 0
            sales_today_amount = row_laudus.get("total") or 0.0

        stats["kpis"]["sales_today_count"] = sales_today_count
        stats["kpis"]["sales_today_amount"] = sales_today_amount

        row = _fetchone_safe(conn, "SELECT count(*) as cnt FROM tickets WHERE estado != 'cerrado'")
        stats["kpis"]["tickets_open"] = row.get("cnt") or 0

        row = _fetchone_safe(
            conn,
            "SELECT count(*) as cnt FROM tickets WHERE severidad = 'critica' AND estado != 'cerrado'"
        )
        stats["kpis"]["tickets_critical"] = row.get("cnt") or 0

        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        row = _fetchone_safe(
            conn,
            """
            SELECT count(*) as cnt
            FROM sys_jobs
            WHERE status = 'FAILED' AND updated_at >= ?
            """,
            (cutoff,),
        )
        failures_24h = row.get("cnt") or 0
        stats["jobs_health"]["failures_24h"] = failures_24h
        if failures_24h > 0:
            stats["system_status"] = "degraded"

        stats["recent_failures"] = _fetchall_safe(
            conn,
            """
            SELECT
                job_type,
                COALESCE(last_error, '') as error_msg,
                updated_at as started_at,
                last_error,
                updated_at
            FROM sys_jobs
            WHERE status = 'FAILED'
            ORDER BY updated_at DESC
            LIMIT 5
            """
        )

        row = _fetchone_safe(conn, "SELECT count(*) as cnt FROM customers")
        stats["kpis"]["total_customers"] = row.get("cnt") or 0
        if _should_use_legacy_fallback(stats):
            return _fetch_legacy_dashboard(sess) or stats
        return stats
    finally:
        conn.close()
