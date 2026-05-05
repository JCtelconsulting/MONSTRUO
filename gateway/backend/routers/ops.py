from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from plataforma.core import db, deps, security

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ops", tags=["ops"])
LEGACY_OPS_FALLBACK_URL = os.getenv("LEGACY_OPS_FALLBACK_URL", "").strip()


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

        row = _fetchone_safe(conn, "SELECT count(*) as cnt FROM tickets WHERE estado = 'cerrado'")
        stats["kpis"]["tickets_closed"] = row.get("cnt") or 0

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
            LIMIT 10
            """
        )

        row = _fetchone_safe(conn, "SELECT count(*) as cnt FROM customers")
        stats["kpis"]["total_customers"] = row.get("cnt") or 0

        # --- System console data ---
        system_events = []

        # Email polling last run
        email_job = _fetchone_safe(
            conn,
            """
            SELECT status, updated_at, last_error
            FROM sys_jobs
            WHERE job_type = 'EMAIL_POLLING'
            ORDER BY updated_at DESC
            LIMIT 1
            """
        )
        if email_job:
            is_failed = email_job.get("status") == "FAILED"
            system_events.append({
                "source": "email_polling",
                "label": "Email Polling",
                "status": "error" if is_failed else "ok",
                "msg": email_job.get("last_error") or ("OK" if not is_failed else "Fallo desconocido"),
                "ts": email_job.get("updated_at") or "",
            })
            if is_failed:
                stats["system_status"] = "degraded"

        # SLA escalations last 24h
        sla_escalations = _fetchall_safe(
            conn,
            """
            SELECT id, titulo, updated_at
            FROM tickets
            WHERE severidad = 'critica'
              AND estado NOT IN ('cerrado', 'resuelto')
              AND updated_at >= ?
            ORDER BY updated_at DESC
            LIMIT 5
            """,
            (cutoff,),
        )
        for t in sla_escalations:
            system_events.append({
                "source": "sla",
                "label": "SLA Breach",
                "status": "warn",
                "msg": f"Ticket #{t.get('id')} — {(t.get('titulo') or '')[:60]}",
                "ts": t.get("updated_at") or "",
            })

        # Stale running jobs (stuck)
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        stale_jobs = _fetchall_safe(
            conn,
            """
            SELECT job_type, updated_at
            FROM sys_jobs
            WHERE status = 'RUNNING'
              AND updated_at <= ?
            ORDER BY updated_at ASC
            LIMIT 5
            """,
            (stale_cutoff,),
        )
        for j in stale_jobs:
            system_events.append({
                "source": "stale_job",
                "label": "Job Atascado",
                "status": "warn",
                "msg": f"{j.get('job_type')} lleva más de 30 min en RUNNING",
                "ts": j.get("updated_at") or "",
            })
            stats["system_status"] = "degraded"

        # Recent job failures (last 24h count already computed, add detail)
        stats["jobs_health"]["stale_running"] = len(stale_jobs)

        # Sort events by ts descending
        system_events.sort(key=lambda x: x.get("ts") or "", reverse=True)
        stats["system_events"] = system_events

        if _should_use_legacy_fallback(stats):
            return _fetch_legacy_dashboard(sess) or stats
        return stats
    finally:
        conn.close()


# ============================================================================
# Reporte de errores frontend → dashboard
# ============================================================================

class ClientErrorReport(BaseModel):
    """Payload que envía el JS del frontend cuando captura un error."""
    message: str = Field(..., max_length=2000)
    severity: str = Field("error", pattern=r"^(error|warning|info)$")
    source: Optional[str] = Field("", max_length=500)        # archivo:linea
    stack: Optional[str] = Field("", max_length=8000)        # stack trace
    user_agent: Optional[str] = Field("", max_length=500)
    url: Optional[str] = Field("", max_length=1000)          # URL donde ocurrió
    app: Optional[str] = Field("", max_length=50)            # gateway, ticketera, gta...
    extra: Optional[Dict[str, Any]] = None


@router.post("/client-errors")
async def report_client_error(
    body: ClientErrorReport,
    request: Request,
):
    """Recibe errores capturados en el frontend y los persiste en core.audit_logs.

    Endpoint público: los errores tempranos pueden ocurrir antes del login,
    y los datos guardados no son sensibles (mensaje + stack + URL pública).
    El payload está limitado por max_length de cada campo en ClientErrorReport
    para mitigar abuso.

    El dashboard de Ops los muestra agrupados por hora en system_events.
    Para listarlos: GET /api/ops/client-errors/recent (requiere admin.settings).
    """
    # actor: si hay cookie de sesión válida, lo extraemos; si no, "anonymous"
    actor = "anonymous"
    try:
        auth_cookie = request.cookies.get("access_token") or ""
        if auth_cookie:
            payload = security.verify_token(auth_cookie)
            if payload and payload.get("sub"):
                actor = str(payload["sub"])
    except Exception:
        pass
    ip = request.client.host if request.client else ""
    now = datetime.now(timezone.utc).isoformat()

    metadata = {
        "source": body.source or "",
        "stack": (body.stack or "")[:8000],
        "user_agent": body.user_agent or request.headers.get("user-agent", "")[:500],
        "url": body.url or "",
        "app": body.app or "",
    }
    if body.extra:
        metadata["extra"] = body.extra

    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO core.audit_logs
               (timestamp, actor, action, target, ip_address, metadata_json, severity)
               VALUES (?, ?, 'frontend_error', ?, ?, ?, ?)""",
            (
                now,
                actor or "anonymous",
                (body.message or "")[:200],
                ip,
                json.dumps(metadata, ensure_ascii=False),
                body.severity,
            ),
        )
        conn.commit()
        logger.warning(
            "[frontend_error] %s severity=%s actor=%s app=%s url=%s",
            body.message[:120], body.severity, actor, body.app, body.url,
        )
    except Exception as e:
        logger.error(f"No se pudo persistir frontend_error: {e}")
        # No fallamos el endpoint para no perder más errores en cascada
    finally:
        conn.close()

    return {"ok": True, "ts": now}


@router.get("/client-errors/recent")
async def list_recent_client_errors(
    limit: int = 50,
    _sess: Dict[str, Any] = Depends(deps.require_permission("admin.settings")),
):
    """Lista errores frontend recientes para el dashboard de Ops.

    Solo admin.settings — incluye stacks y URLs internas.
    El parámetro _sess solo está para activar el guard de permiso vía Depends.
    """
    limit = max(1, min(int(limit), 200))
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id, timestamp, actor, target AS message, ip_address,
                      metadata_json, severity
               FROM core.audit_logs
               WHERE action = 'frontend_error'
               ORDER BY id DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        items: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.pop("metadata_json", "{}") or "{}")
            except Exception:
                d["metadata"] = {}
            items.append(d)
        return {"items": items, "total": len(items)}
    finally:
        conn.close()
