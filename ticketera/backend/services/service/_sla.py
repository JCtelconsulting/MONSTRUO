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
# SLA / BREACHES / AUTOMATIONS / EVIDENCE
# ==========================================================================
def get_sla_metrics(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    severity: Optional[str] = None,
    assignee: Optional[str] = None,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        now_iso = db.now_utc_iso()
        now_dt = _parse_dt(now_iso) or _now_dt()
        where = ["COALESCE(is_trashed, FALSE) = FALSE"]
        params: List[Any] = []

        if date_from:
            where.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("created_at <= ?")
            params.append(date_to)
        if severity:
            where.append("severidad = ?")
            params.append(severity.lower())
        if assignee:
            where.append("asignado_a = ?")
            params.append(assignee)

        where_sql = " AND ".join(where)

        totals = conn.execute(
            f"""SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN estado IN ('resuelto','cerrado') THEN 1 END) AS closed_total,
                    COUNT(CASE WHEN estado NOT IN ('resuelto','cerrado') THEN 1 END) AS open_total,
                    COUNT(CASE WHEN ttr_due_at::timestamptz < ?::timestamptz AND estado NOT IN ('resuelto','cerrado') THEN 1 END) AS breached_open,
                    COUNT(CASE WHEN estado IN ('resuelto','cerrado') AND (ttr_due_at IS NULL OR COALESCE(resolved_at, updated_at)::timestamptz <= ttr_due_at::timestamptz) THEN 1 END) AS closed_on_time
                FROM tickets
                WHERE {where_sql}""",
            (now_iso, *params),
        ).fetchone()

        frt_row = conn.execute(
            f"""SELECT
                    COUNT(CASE WHEN first_response_at IS NOT NULL AND frt_due_at IS NOT NULL AND first_response_at::timestamptz <= frt_due_at::timestamptz THEN 1 END) AS frt_on_time,
                    COUNT(CASE WHEN first_response_at IS NULL AND frt_due_at IS NOT NULL AND frt_due_at::timestamptz < ?::timestamptz THEN 1 END) AS frt_breached_open,
                    COUNT(CASE WHEN first_response_at IS NOT NULL AND frt_due_at IS NOT NULL AND first_response_at::timestamptz > frt_due_at::timestamptz THEN 1 END) AS frt_breached_late
                FROM tickets
                WHERE {where_sql}""",
            (now_iso, *params),
        ).fetchone()

        ttr_row = conn.execute(
            f"""SELECT
                    COUNT(CASE WHEN estado IN ('resuelto','cerrado') AND ttr_due_at IS NOT NULL AND COALESCE(resolved_at, updated_at)::timestamptz <= ttr_due_at::timestamptz THEN 1 END) AS ttr_on_time,
                    COUNT(CASE WHEN estado IN ('resuelto','cerrado') AND ttr_due_at IS NOT NULL AND COALESCE(resolved_at, updated_at)::timestamptz > ttr_due_at::timestamptz THEN 1 END) AS ttr_breached_closed,
                    COUNT(CASE WHEN estado NOT IN ('resuelto','cerrado') AND ttr_due_at IS NOT NULL AND ttr_due_at::timestamptz < ?::timestamptz THEN 1 END) AS ttr_breached_open
                FROM tickets
                WHERE {where_sql}""",
            (now_iso, *params),
        ).fetchone()

        by_severity_rows = conn.execute(
            f"""SELECT severidad, COUNT(*) AS total
                FROM tickets
                WHERE {where_sql}
                GROUP BY severidad""",
            params,
        ).fetchall()

        by_assignee_rows = conn.execute(
            f"""SELECT COALESCE(asignado_a, 'sin_asignar') AS assignee, COUNT(*) AS total
                FROM tickets
                WHERE {where_sql}
                GROUP BY COALESCE(asignado_a, 'sin_asignar')""",
            params,
        ).fetchall()

        avg_resolution = conn.execute(
            f"""SELECT
                    COALESCE(AVG(EXTRACT(EPOCH FROM ((updated_at::timestamptz) - (created_at::timestamptz))) / 3600.0), 0) AS avg_resolution_hours
                FROM tickets
                WHERE {where_sql}
                  AND estado IN ('resuelto','cerrado')""",
            params,
        ).fetchone()

        aging_rows = conn.execute(
            f"""SELECT
                    COUNT(CASE WHEN estado NOT IN ('resuelto','cerrado') AND EXTRACT(EPOCH FROM (?::timestamptz - created_at::timestamptz))/60.0 < 60 THEN 1 END) AS bucket_lt_1h,
                    COUNT(CASE WHEN estado NOT IN ('resuelto','cerrado') AND EXTRACT(EPOCH FROM (?::timestamptz - created_at::timestamptz))/60.0 >= 60 AND EXTRACT(EPOCH FROM (?::timestamptz - created_at::timestamptz))/60.0 < 240 THEN 1 END) AS bucket_1h_4h,
                    COUNT(CASE WHEN estado NOT IN ('resuelto','cerrado') AND EXTRACT(EPOCH FROM (?::timestamptz - created_at::timestamptz))/60.0 >= 240 AND EXTRACT(EPOCH FROM (?::timestamptz - created_at::timestamptz))/60.0 < 1440 THEN 1 END) AS bucket_4h_24h,
                    COUNT(CASE WHEN estado NOT IN ('resuelto','cerrado') AND EXTRACT(EPOCH FROM (?::timestamptz - created_at::timestamptz))/60.0 >= 1440 THEN 1 END) AS bucket_gt_24h
                FROM tickets
                WHERE {where_sql}""",
            (now_iso, now_iso, now_iso, now_iso, now_iso, now_iso, *params),
        ).fetchone()

        historical_row = conn.execute(
            f"""
            WITH assignment_times AS (
                SELECT ticket_id, MIN(created_at) AS assigned_at
                FROM ticket_transitions
                WHERE LOWER(COALESCE(to_subestado, '')) = 'asignado'
                GROUP BY ticket_id
            ),
            auto_reply_times AS (
                SELECT ticket_id, MIN(created_at) AS auto_reply_at
                FROM ticket_emails
                WHERE direction = 'auto_reply'
                GROUP BY ticket_id
            )
            SELECT
                COUNT(*) AS total_tickets,
                COUNT(CASE WHEN COALESCE(TRIM(origen_email), '') <> '' THEN 1 END) AS email_total,
                COUNT(CASE
                    WHEN COALESCE(TRIM(origen_email), '') <> ''
                     AND ar.auto_reply_at IS NOT NULL
                     AND EXTRACT(EPOCH FROM (ar.auto_reply_at::timestamptz - tickets.created_at::timestamptz))/60.0 <= ?::numeric
                    THEN 1
                END) AS auto_reply_on_time,
                COUNT(CASE
                    WHEN COALESCE(TRIM(origen_email), '') <> ''
                     AND ar.auto_reply_at IS NOT NULL
                     AND EXTRACT(EPOCH FROM (ar.auto_reply_at::timestamptz - tickets.created_at::timestamptz))/60.0 > ?::numeric
                    THEN 1
                END) AS auto_reply_late,
                COUNT(CASE
                    WHEN COALESCE(TRIM(origen_email), '') <> ''
                     AND ar.auto_reply_at IS NULL
                     AND EXTRACT(EPOCH FROM (?::timestamptz - tickets.created_at::timestamptz))/60.0 > ?::numeric
                    THEN 1
                END) AS auto_reply_pending_breached,
                COUNT(CASE
                    WHEN at.assigned_at IS NOT NULL
                     AND EXTRACT(EPOCH FROM (at.assigned_at::timestamptz - tickets.created_at::timestamptz))/60.0 <= ?::numeric
                    THEN 1
                END) AS assignment_on_time,
                COUNT(CASE
                    WHEN at.assigned_at IS NOT NULL
                     AND EXTRACT(EPOCH FROM (at.assigned_at::timestamptz - tickets.created_at::timestamptz))/60.0 > ?::numeric
                    THEN 1
                END) AS assignment_late,
                COUNT(CASE
                    WHEN at.assigned_at IS NULL
                     AND tickets.estado NOT IN ('resuelto','cerrado')
                     AND EXTRACT(EPOCH FROM (?::timestamptz - tickets.created_at::timestamptz))/60.0 > ?::numeric
                    THEN 1
                END) AS assignment_pending_breached,
                COUNT(CASE
                    WHEN tickets.estado IN ('resuelto','cerrado')
                     AND EXTRACT(EPOCH FROM (COALESCE(tickets.resolved_at, tickets.updated_at)::timestamptz - tickets.created_at::timestamptz))/60.0 <= ?::numeric
                    THEN 1
                END) AS resolution_on_time,
                COUNT(CASE
                    WHEN tickets.estado IN ('resuelto','cerrado')
                     AND EXTRACT(EPOCH FROM (COALESCE(tickets.resolved_at, tickets.updated_at)::timestamptz - tickets.created_at::timestamptz))/60.0 > ?::numeric
                    THEN 1
                END) AS resolution_late,
                COUNT(CASE
                    WHEN tickets.estado NOT IN ('resuelto','cerrado')
                     AND EXTRACT(EPOCH FROM (?::timestamptz - tickets.created_at::timestamptz))/60.0 > ?::numeric
                    THEN 1
                END) AS resolution_pending_breached
            FROM tickets
            LEFT JOIN assignment_times at ON at.ticket_id = tickets.id
            LEFT JOIN auto_reply_times ar ON ar.ticket_id = tickets.id
            WHERE {where_sql}
            """,
            (
                AUTO_REPLY_SLA_MINUTES,
                AUTO_REPLY_SLA_MINUTES,
                now_iso,
                AUTO_REPLY_SLA_MINUTES,
                ASSIGNMENT_SLA_MINUTES,
                ASSIGNMENT_SLA_MINUTES,
                now_iso,
                ASSIGNMENT_SLA_MINUTES,
                RESOLUTION_SLA_MINUTES,
                RESOLUTION_SLA_MINUTES,
                now_iso,
                RESOLUTION_SLA_MINUTES,
                *params,
            ),
        ).fetchone()

        def _build_historical_bucket(total_count: Any, on_time: Any, late: Any, pending_breached: Any) -> Dict[str, Any]:
            total_val = int(total_count or 0)
            on_time_val = int(on_time or 0)
            late_val = int(late or 0)
            pending_val = int(pending_breached or 0)
            breached_val = late_val + pending_val
            pct = round((on_time_val / total_val) * 100.0, 2) if total_val > 0 else 0.0
            return {
                "total": total_val,
                "on_time": on_time_val,
                "late": late_val,
                "pending_breached": pending_val,
                "breached": breached_val,
                "compliance_pct": pct,
            }

        total = int(totals["total"] or 0)
        breached_open = int(totals["breached_open"] or 0)
        breach_rate = (breached_open / total * 100.0) if total > 0 else 0.0
        frt_breached = int((frt_row["frt_breached_open"] or 0) + (frt_row["frt_breached_late"] or 0))
        ttr_breached = int((ttr_row["ttr_breached_closed"] or 0) + (ttr_row["ttr_breached_open"] or 0))

        return {
            "total": total,
            "open_total": int(totals["open_total"] or 0),
            "closed_total": int(totals["closed_total"] or 0),
            "breached_open": breached_open,
            "closed_on_time": int(totals["closed_on_time"] or 0),
            "breach_rate_pct": round(breach_rate, 2),
            "avg_resolution_hours": round(float(avg_resolution["avg_resolution_hours"] or 0), 2),
            "frt_on_time": int(frt_row["frt_on_time"] or 0),
            "frt_breached": frt_breached,
            "ttr_on_time": int(ttr_row["ttr_on_time"] or 0),
            "ttr_breached": ttr_breached,
            "sla_mode": SLA_MODE,
            "escalation_windows_pct": SLA_ESCALATION_WINDOWS_PCT,
            "targets": {
                "auto_reply_minutes": AUTO_REPLY_SLA_MINUTES,
                "assignment_minutes": ASSIGNMENT_SLA_MINUTES,
                "resolution_minutes": RESOLUTION_SLA_MINUTES,
            },
            "historical_sla": {
                "auto_reply": _build_historical_bucket(
                    historical_row["email_total"] if historical_row else 0,
                    historical_row["auto_reply_on_time"] if historical_row else 0,
                    historical_row["auto_reply_late"] if historical_row else 0,
                    historical_row["auto_reply_pending_breached"] if historical_row else 0,
                ),
                "assignment": _build_historical_bucket(
                    historical_row["total_tickets"] if historical_row else 0,
                    historical_row["assignment_on_time"] if historical_row else 0,
                    historical_row["assignment_late"] if historical_row else 0,
                    historical_row["assignment_pending_breached"] if historical_row else 0,
                ),
                "resolution": _build_historical_bucket(
                    historical_row["total_tickets"] if historical_row else 0,
                    historical_row["resolution_on_time"] if historical_row else 0,
                    historical_row["resolution_late"] if historical_row else 0,
                    historical_row["resolution_pending_breached"] if historical_row else 0,
                ),
            },
            "business_hours": {
                "timezone_offset": str(getattr(app_settings, "TICKET_SLA_BUSINESS_TZ_OFFSET", "-03:00")),
                "days": sorted(list(SLA_BUSINESS_DAYS)),
                "start_hour": SLA_BUSINESS_START_HOUR,
                "end_hour": SLA_BUSINESS_END_HOUR,
            },
            "aging_buckets": {
                "lt_1h": int(aging_rows["bucket_lt_1h"] or 0),
                "1h_4h": int(aging_rows["bucket_1h_4h"] or 0),
                "4h_24h": int(aging_rows["bucket_4h_24h"] or 0),
                "gt_24h": int(aging_rows["bucket_gt_24h"] or 0),
            },
            "by_severity": [dict(r) for r in by_severity_rows],
            "by_assignee": [dict(r) for r in by_assignee_rows],
            "filters": {
                "date_from": date_from,
                "date_to": date_to,
                "severity": severity,
                "assignee": assignee,
            },
            "generated_at": now_dt.isoformat(),
        }
    finally:
        conn.close()

def list_sla_breaches(
    severity: Optional[str] = None,
    assignee: Optional[str] = None,
    breach_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        now_iso = db.now_utc_iso()
        breach = (breach_type or "ttr").strip().lower()
        if breach not in {"frt", "ttr"}:
            breach = "ttr"

        where: List[str]
        params: List[Any]
        if breach == "frt":
            where = [
                "frt_due_at IS NOT NULL",
                "first_response_at IS NULL",
                "frt_due_at::timestamptz < ?::timestamptz",
            ]
            params = [now_iso]
        else:
            where = [
                "ttr_due_at IS NOT NULL",
                "("
                "(estado NOT IN ('resuelto','cerrado') AND ttr_due_at::timestamptz < ?::timestamptz)"
                " OR "
                "(estado IN ('resuelto','cerrado') AND COALESCE(resolved_at, updated_at)::timestamptz > ttr_due_at::timestamptz)"
                ")",
            ]
            params = [now_iso]

        if severity:
            where.append("severidad = ?")
            params.append(severity.lower())
        if assignee:
            where.append("asignado_a = ?")
            params.append(assignee)

        where_sql = " AND ".join(where)
        total_row = conn.execute(
            f"SELECT COUNT(*) AS c FROM tickets WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT id, codigo, titulo, estado, subestado, tipo, severidad, asignado_a, created_at, updated_at,
                       frt_due_at, ttr_due_at, resolved_at,
                       CASE
                           WHEN ? = 'frt' THEN GREATEST(0, EXTRACT(EPOCH FROM (?::timestamptz - frt_due_at::timestamptz))/60.0)
                           ELSE GREATEST(
                               0,
                               EXTRACT(EPOCH FROM (
                                   CASE
                                       WHEN estado IN ('resuelto','cerrado') THEN COALESCE(resolved_at, updated_at)::timestamptz
                                       ELSE ?::timestamptz
                                   END
                                   - ttr_due_at::timestamptz
                               ))/60.0
                           )
                       END AS minutes_overdue
                FROM tickets
                WHERE {where_sql}
                ORDER BY minutes_overdue DESC, created_at ASC
                LIMIT ? OFFSET ?""",
            (breach, now_iso, now_iso, *params, limit, offset),
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": int(total_row["c"] or 0),
            "limit": limit,
            "offset": offset,
            "breach_type": breach,
        }
    finally:
        conn.close()

def upsert_automation_rule(
    name: str,
    match_json: Dict[str, Any],
    action_json: Dict[str, Any],
    created_by: str,
    is_active: bool = True,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """INSERT INTO ticket_automation_rules
               (name, is_active, match_json, action_json, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   is_active = EXCLUDED.is_active,
                   match_json = EXCLUDED.match_json,
                   action_json = EXCLUDED.action_json,
                   updated_at = EXCLUDED.updated_at""",
            (
                (name or "").strip(),
                1 if is_active else 0,
                json.dumps(match_json or {}, ensure_ascii=False),
                json.dumps(action_json or {}, ensure_ascii=False),
                created_by,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM ticket_automation_rules WHERE name = ?",
            ((name or "").strip(),),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def list_automation_rules(only_active: bool = False) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        where = "WHERE is_active = 1" if only_active else ""
        rows = conn.execute(
            f"""SELECT * FROM ticket_automation_rules
                {where}
                ORDER BY updated_at DESC, id DESC"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def create_evidence_event(
    control_id: str,
    artifact_ref: str,
    owner: str,
    integrity_hash: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        metadata_json = _stable_json(metadata or {})
        prev_row = conn.execute(
            "SELECT chain_hash FROM evidence_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev_hash = (prev_row["chain_hash"] if prev_row else "") or ""
        payload = {
            "control_id": (control_id or "").strip(),
            "artifact_ref": (artifact_ref or "").strip(),
            "owner": (owner or "").strip(),
            "integrity_hash": (integrity_hash or "").strip(),
            "metadata_json": metadata_json,
            "created_at": now,
        }
        chain_hash = _build_chain_hash(prev_hash, payload)
        row = conn.execute(
            """INSERT INTO evidence_events
               (control_id, artifact_ref, owner, integrity_hash, metadata_json, created_at,
                chain_prev_hash, chain_hash, chain_algo, chain_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                payload["control_id"],
                payload["artifact_ref"],
                payload["owner"],
                payload["integrity_hash"],
                metadata_json,
                now,
                prev_hash,
                chain_hash,
                CHAIN_ALGO,
                CHAIN_VERSION,
            ),
        ).fetchone()
        conn.commit()
        event_id = int(row["id"]) if row else None
        if event_id is None:
            return {}
        created = conn.execute("SELECT * FROM evidence_events WHERE id = ?", (event_id,)).fetchone()
        return dict(created) if created else {}
    finally:
        conn.close()

def list_evidence_events(
    control_id: Optional[str] = None,
    owner: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        where = ["1=1"]
        params: List[Any] = []
        if control_id:
            where.append("control_id = ?")
            params.append(control_id)
        if owner:
            where.append("owner = ?")
            params.append(owner)
        where_sql = " AND ".join(where)

        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM evidence_events WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT * FROM evidence_events
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
        return {"items": [dict(r) for r in rows], "total": int(total["c"] or 0), "limit": limit, "offset": offset}
    finally:
        conn.close()

def _normalize_iso_utc(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = _parse_dt(value)
    if not parsed:
        raise ValueError(f"Fecha inválida: {value}")
    return _ensure_utc(parsed).isoformat()

def _normalize_compliance_scope(scope: Optional[str]) -> str:
    normalized = (scope or "both").strip().lower()
    if normalized not in {"audit", "evidence", "both"}:
        return "both"
    return normalized

def _artifact_exists_with_hash(manifest_path: str, artifact_hash: str) -> bool:
    path = Path(str(manifest_path or "").strip())
    if not path.exists() or not path.is_file():
        return False
    expected_hash = str(artifact_hash or "").strip()
    if not expected_hash:
        return True
    try:
        return _sha256_file(path) == expected_hash
    except Exception:
        return False

def _compliance_run_duplicate_decision(run: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Decide if idempotent call should return duplicate_skipped.
    Returns (should_skip, reason).
    """
    status = str(run.get("status") or "").strip().lower()
    manifest_path = str(run.get("manifest_path") or "").strip()
    artifact_hash = str(run.get("artifact_hash") or "").strip()
    has_artifact = _artifact_exists_with_hash(manifest_path, artifact_hash)

    if status in {"completed", "completed_with_errors"} and has_artifact:
        return True, "completed_artifact_exists"
    if status == "running":
        return True, "run_in_progress"
    if status == "failed":
        return False, "previous_failed"
    if status in {"completed", "completed_with_errors"} and not has_artifact:
        return False, "artifact_missing_or_invalid"
    return False, "allow_rerun"

def _retention_case_sql() -> str:
    return (
        f"CASE "
        f"WHEN COALESCE(ticket_security_class, 'internal') = 'public' THEN {RETENTION_POLICY_DAYS['public']} "
        f"WHEN COALESCE(ticket_security_class, 'internal') = 'restricted' THEN {RETENTION_POLICY_DAYS['restricted']} "
        f"ELSE {RETENTION_POLICY_DAYS['internal']} END"
    )

def list_ticket_legal_holds(
    ticket_id: Optional[int] = None,
    active: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        where = ["1=1"]
        params: List[Any] = []
        if ticket_id is not None:
            where.append("ticket_id = ?")
            params.append(int(ticket_id))
        if active is not None:
            where.append("is_active = ?")
            params.append(1 if active else 0)
        where_sql = " AND ".join(where)

        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM ticket_legal_holds WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT *
                FROM ticket_legal_holds
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": int(total["c"] or 0),
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()

def create_ticket_legal_hold(
    ticket_id: int,
    reason: str,
    actor: str,
    case_ref: Optional[str] = None,
) -> Dict[str, Any]:
    reason_clean = (reason or "").strip()
    if not reason_clean:
        raise ValueError("reason es obligatorio")

    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not exists:
            raise ValueError("Ticket no encontrado")

        now = db.now_utc_iso()
        row = conn.execute(
            """INSERT INTO ticket_legal_holds
               (ticket_id, reason, case_ref, created_by, created_at, is_active)
               VALUES (?, ?, ?, ?, ?, 1)
               RETURNING id""",
            (int(ticket_id), reason_clean, (case_ref or "").strip(), actor, now),
        ).fetchone()
        conn.commit()
        hold_id = int(row["id"]) if row else 0
        hold = conn.execute(
            "SELECT * FROM ticket_legal_holds WHERE id = ?",
            (hold_id,),
        ).fetchone()
        result = dict(hold) if hold else {}
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.5.30",
            artifact_ref=f"ticket:{ticket_id}:legal_hold:{result.get('id')}",
            owner=actor,
            integrity_hash="",
            metadata={"ticket_id": ticket_id, "reason": reason_clean, "case_ref": (case_ref or "").strip()},
        )
    except Exception as e:
        logger.warning(f"[create_ticket_legal_hold] evidence_event no crítico falló: {e}")
    return result

def release_ticket_legal_hold(
    hold_id: int,
    release_note: str,
    actor: str,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM ticket_legal_holds WHERE id = ?",
            (int(hold_id),),
        ).fetchone()
        if not row:
            raise ValueError("Legal hold no encontrado")
        hold = dict(row)
        if int(hold.get("is_active") or 0) == 0:
            raise ValueError("Legal hold ya está liberado")

        now = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_legal_holds
               SET is_active = 0,
                   released_by = ?,
                   released_at = ?,
                   release_note = ?
               WHERE id = ?""",
            (actor, now, (release_note or "").strip(), int(hold_id)),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM ticket_legal_holds WHERE id = ?",
            (int(hold_id),),
        ).fetchone()
        result = dict(updated) if updated else {}
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.5.30",
            artifact_ref=f"ticket:{result.get('ticket_id')}:legal_hold_release:{hold_id}",
            owner=actor,
            integrity_hash="",
            metadata={"hold_id": hold_id, "release_note": (release_note or "").strip()},
        )
    except Exception as e:
        logger.warning(f"[release_ticket_legal_hold] evidence_event no crítico falló: {e}")
    return result

def run_compliance_export(
    actor: str,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    scope: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_scope = _normalize_compliance_scope(scope)
    from_iso = _normalize_iso_utc(from_ts)
    to_iso = _normalize_iso_utc(to_ts)
    normalized_idem = (idempotency_key or "").strip()[:128] or None
    now = db.now_utc_iso()

    if from_iso and to_iso and _parse_dt(from_iso) and _parse_dt(to_iso):
        if _parse_dt(from_iso) >= _parse_dt(to_iso):
            raise ValueError("from_ts debe ser menor que to_ts")

    conn = db.get_conn()
    run_id = None
    try:
        if normalized_idem:
            existing = conn.execute(
                """SELECT * FROM compliance_export_runs
                   WHERE idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (normalized_idem,),
            ).fetchone()
            if existing:
                out = dict(existing)
                should_skip, reason = _compliance_run_duplicate_decision(out)
                out["duplicate_skipped"] = bool(should_skip)
                out["duplicate_skipped_reason"] = reason
                out["artifact_exists"] = _artifact_exists_with_hash(
                    str(out.get("manifest_path") or ""),
                    str(out.get("artifact_hash") or ""),
                )
                out["artifact_verified_at"] = db.now_utc_iso()
                if should_skip:
                    return out

        row = conn.execute(
            """INSERT INTO compliance_export_runs
               (scope, from_ts, to_ts, status, actor, idempotency_key, created_at, started_at)
               VALUES (?, ?, ?, 'running', ?, ?, ?, ?)
               RETURNING id""",
            (normalized_scope, from_iso, to_iso, actor, normalized_idem or "", now, now),
        ).fetchone()
        run_id = int(row["id"]) if row else None
        if not run_id:
            raise ValueError("No se pudo iniciar run de export compliance")

        audit_where = ["1=1"]
        evidence_where = ["1=1"]
        audit_params: List[Any] = []
        evidence_params: List[Any] = []
        if from_iso:
            audit_where.append("timestamp::timestamptz >= ?::timestamptz")
            evidence_where.append("created_at::timestamptz >= ?::timestamptz")
            audit_params.append(from_iso)
            evidence_params.append(from_iso)
        if to_iso:
            audit_where.append("timestamp::timestamptz < ?::timestamptz")
            evidence_where.append("created_at::timestamptz < ?::timestamptz")
            audit_params.append(to_iso)
            evidence_params.append(to_iso)

        audit_rows: List[Dict[str, Any]] = []
        evidence_rows: List[Dict[str, Any]] = []
        if normalized_scope in {"audit", "both"}:
            audit_rows = [
                dict(r)
                for r in conn.execute(
                    f"""SELECT id, timestamp, actor, action, target, ip_address, severity, metadata_json,
                               chain_prev_hash, chain_hash, chain_algo, chain_version
                        FROM audit_logs
                        WHERE {' AND '.join(audit_where)}
                        ORDER BY id ASC""",
                    audit_params,
                ).fetchall()
            ]
        if normalized_scope in {"evidence", "both"}:
            evidence_rows = [
                dict(r)
                for r in conn.execute(
                    f"""SELECT id, control_id, artifact_ref, owner, integrity_hash, metadata_json, created_at,
                               chain_prev_hash, chain_hash, chain_algo, chain_version
                        FROM evidence_events
                        WHERE {' AND '.join(evidence_where)}
                        ORDER BY id ASC""",
                    evidence_params,
                ).fetchall()
            ]

        run_dir = Path(COMPLIANCE_EXPORT_DIR) / datetime.now(COMPLIANCE_TZ).strftime("%Y/%m/%d") / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)

        files_manifest: List[Dict[str, Any]] = []
        if audit_rows:
            audit_path = run_dir / "audit_logs.json"
            audit_path.write_text(_stable_json(audit_rows), encoding="utf-8")
            files_manifest.append(
                {"name": "audit_logs.json", "path": str(audit_path), "rows": len(audit_rows), "sha256": _sha256_file(audit_path)}
            )
        if evidence_rows:
            evidence_path = run_dir / "evidence_events.json"
            evidence_path.write_text(_stable_json(evidence_rows), encoding="utf-8")
            files_manifest.append(
                {"name": "evidence_events.json", "path": str(evidence_path), "rows": len(evidence_rows), "sha256": _sha256_file(evidence_path)}
            )

        manifest_payload = {
            "run_id": run_id,
            "scope": normalized_scope,
            "from_ts": from_iso,
            "to_ts": to_iso,
            "generated_at": now,
            "files": files_manifest,
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(_stable_json(manifest_payload), encoding="utf-8")
        manifest_hash = _sha256_file(manifest_path)

        counts = {
            "audit_rows": len(audit_rows),
            "evidence_rows": len(evidence_rows),
            "files": len(files_manifest),
        }
        completed = db.now_utc_iso()
        conn.execute(
            """UPDATE compliance_export_runs
               SET status = 'completed',
                   artifact_dir = ?,
                   manifest_path = ?,
                   artifact_hash = ?,
                   counts_json = ?,
                   completed_at = ?
               WHERE id = ?""",
            (
                str(run_dir),
                str(manifest_path),
                manifest_hash,
                _stable_json(counts),
                completed,
                run_id,
            ),
        )
        conn.commit()
    except Exception as e:
        if run_id:
            conn.execute(
                """UPDATE compliance_export_runs
                   SET status = 'failed', error = ?, completed_at = ?
                   WHERE id = ?""",
                (str(e), db.now_utc_iso(), run_id),
            )
            conn.commit()
        raise
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.8.15",
            artifact_ref=f"compliance_export:{run_id}",
            owner=actor,
            integrity_hash=manifest_hash,
            metadata={
                "run_id": run_id,
                "scope": normalized_scope,
                "from_ts": from_iso,
                "to_ts": to_iso,
                "manifest_path": str(manifest_path),
                "artifact_dir": str(run_dir),
                "counts": counts,
            },
        )
    except Exception as e:
        logger.warning(f"[run_compliance_export] evidence_event no crítico falló: {e}")

    return {
        "ok": True,
        "run_id": run_id,
        "scope": normalized_scope,
        "from_ts": from_iso,
        "to_ts": to_iso,
        "artifact_dir": str(run_dir),
        "manifest_path": str(manifest_path),
        "artifact_hash": manifest_hash,
        "artifact_exists": _artifact_exists_with_hash(str(manifest_path), manifest_hash),
        "artifact_verified_at": db.now_utc_iso(),
        "counts": counts,
        "duplicate_skipped": False,
        "duplicate_skipped_reason": "",
    }

def list_compliance_export_runs(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        where = ["1=1"]
        params: List[Any] = []
        if status:
            where.append("status = ?")
            params.append((status or "").strip().lower())
        where_sql = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM compliance_export_runs WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT *
                FROM compliance_export_runs
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
        verified_at = db.now_utc_iso()
        items: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["artifact_exists"] = _artifact_exists_with_hash(
                str(item.get("manifest_path") or ""),
                str(item.get("artifact_hash") or ""),
            )
            item["artifact_verified_at"] = verified_at
            items.append(item)
        return {"items": items, "total": int(total["c"] or 0), "limit": limit, "offset": offset}
    finally:
        conn.close()

def _list_purge_candidates(conn, as_of_iso: str, max_tickets: Optional[int] = None) -> List[Dict[str, Any]]:
    query = f"""
        SELECT t.id, t.codigo, t.estado, t.ticket_security_class, t.retention_until
        FROM tickets t
        WHERE t.estado IN ('resuelto', 'cerrado')
          AND t.retention_until IS NOT NULL
          AND (t.retention_until::timestamptz + make_interval(days => {COMPLIANCE_PURGE_GRACE_DAYS})) <= ?::timestamptz
          AND NOT EXISTS (
              SELECT 1
              FROM ticket_legal_holds h
              WHERE h.ticket_id = t.id
                AND h.is_active = 1
          )
        ORDER BY t.retention_until ASC, t.id ASC
    """
    params: List[Any] = [as_of_iso]
    if max_tickets is not None:
        query += " LIMIT ?"
        params.append(int(max_tickets))
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]

def run_compliance_purge(
    actor: str,
    dry_run: bool = False,
    as_of: Optional[str] = None,
    max_tickets: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    as_of_iso = _normalize_iso_utc(as_of) or db.now_utc_iso()
    max_items = max(1, min(int(max_tickets or 500), 5000))
    normalized_idem = (idempotency_key or "").strip()[:128] or None
    now = db.now_utc_iso()
    conn = db.get_conn()
    run_id = None

    try:
        if normalized_idem:
            existing = conn.execute(
                """SELECT * FROM compliance_purge_runs
                   WHERE idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (normalized_idem,),
            ).fetchone()
            if existing:
                out = dict(existing)
                status_existing = str(out.get("status") or "").strip().lower()
                if status_existing in {"completed", "completed_with_errors", "running"}:
                    out["duplicate_skipped"] = True
                    out["duplicate_skipped_reason"] = (
                        "run_in_progress" if status_existing == "running" else "completed_run_exists"
                    )
                    return out

        row = conn.execute(
            """INSERT INTO compliance_purge_runs
               (dry_run, as_of, status, actor, idempotency_key, created_at, started_at)
               VALUES (?, ?, 'running', ?, ?, ?, ?)
               RETURNING id""",
            (1 if dry_run else 0, as_of_iso, actor, normalized_idem or "", now, now),
        ).fetchone()
        run_id = int(row["id"]) if row else None
        if not run_id:
            raise ValueError("No se pudo iniciar run de purge compliance")

        candidates = _list_purge_candidates(conn, as_of_iso, None if dry_run else max_items)
        summary: Dict[str, Any] = {
            "as_of": as_of_iso,
            "grace_days": COMPLIANCE_PURGE_GRACE_DAYS,
            "dry_run": bool(dry_run),
            "total_candidates": len(candidates),
            "sample": candidates[:50],
            "deleted_tickets": 0,
            "deleted_attachments": 0,
            "deleted_files": 0,
            "errors": [],
        }

        if not dry_run:
            file_paths_to_remove: List[str] = []
            deleted_ticket_ids: List[int] = []
            for candidate in candidates:
                ticket_id = int(candidate["id"])
                try:
                    conn.execute("SAVEPOINT purge_ticket")
                    att_rows = conn.execute(
                        "SELECT file_path FROM ticket_attachments WHERE ticket_id = ?",
                        (ticket_id,),
                    ).fetchall()
                    file_paths_to_remove.extend([str(r["file_path"] or "") for r in att_rows if r.get("file_path")])

                    conn.execute("DELETE FROM ticket_emails WHERE ticket_id = ?", (ticket_id,))
                    conn.execute("DELETE FROM ticket_comments WHERE ticket_id = ?", (ticket_id,))
                    conn.execute("DELETE FROM ticket_transitions WHERE ticket_id = ?", (ticket_id,))
                    conn.execute("DELETE FROM ticket_approvals WHERE ticket_id = ?", (ticket_id,))
                    conn.execute(
                        """DELETE FROM ticket_notification_attempts
                           WHERE notification_id IN (
                               SELECT id FROM ticket_notifications WHERE ticket_id = ?
                           )""",
                        (ticket_id,),
                    )
                    conn.execute("DELETE FROM ticket_notifications WHERE ticket_id = ?", (ticket_id,))
                    conn.execute("DELETE FROM ticket_attachments WHERE ticket_id = ?", (ticket_id,))
                    conn.execute("DELETE FROM ticket_legal_holds WHERE ticket_id = ?", (ticket_id,))
                    conn.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
                    conn.execute("RELEASE SAVEPOINT purge_ticket")
                    deleted_ticket_ids.append(ticket_id)
                except Exception as ticket_error:
                    conn.execute("ROLLBACK TO SAVEPOINT purge_ticket")
                    conn.execute("RELEASE SAVEPOINT purge_ticket")
                    summary["errors"].append({"ticket_id": ticket_id, "error": str(ticket_error)})

            conn.commit()

            deleted_files = 0
            for raw_path in file_paths_to_remove:
                if not raw_path:
                    continue
                try:
                    Path(raw_path).unlink(missing_ok=True)
                    deleted_files += 1
                except Exception as file_error:
                    summary["errors"].append({"file_path": raw_path, "error": str(file_error)})

            summary["deleted_tickets"] = len(deleted_ticket_ids)
            summary["deleted_attachments"] = len(file_paths_to_remove)
            summary["deleted_files"] = deleted_files

        completed = db.now_utc_iso()
        final_status = "completed" if len(summary.get("errors", [])) == 0 else "completed_with_errors"
        conn.execute(
            """UPDATE compliance_purge_runs
               SET status = ?, summary_json = ?, completed_at = ?
               WHERE id = ?""",
            (final_status, _stable_json(summary), completed, run_id),
        )
        conn.commit()
    except Exception as e:
        if run_id:
            conn.execute(
                """UPDATE compliance_purge_runs
                   SET status = 'failed', error = ?, completed_at = ?
                   WHERE id = ?""",
                (str(e), db.now_utc_iso(), run_id),
            )
            conn.commit()
        raise
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.8.10",
            artifact_ref=f"compliance_purge:{run_id}",
            owner=actor,
            integrity_hash="",
            metadata=summary,
        )
    except Exception as e:
        logger.warning(f"[run_compliance_purge] evidence_event no crítico falló: {e}")
    return {
        "ok": True,
        "run_id": run_id,
        "status": final_status,
        "summary": summary,
        "duplicate_skipped": False,
        "duplicate_skipped_reason": "",
    }

def list_compliance_purge_runs(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))
        where = ["1=1"]
        params: List[Any] = []
        if status:
            where.append("status = ?")
            params.append((status or "").strip().lower())
        where_sql = " AND ".join(where)

        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM compliance_purge_runs WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT *
                FROM compliance_purge_runs
                WHERE {where_sql}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?""",
            (*params, limit, offset),
        ).fetchall()
        return {"items": [dict(r) for r in rows], "total": int(total["c"] or 0), "limit": limit, "offset": offset}
    finally:
        conn.close()

def verify_hash_chain(
    stream: str,
    from_id: Optional[int] = None,
    to_id: Optional[int] = None,
) -> Dict[str, Any]:
    stream_norm = (stream or "").strip().lower()
    if stream_norm not in {"audit", "evidence"}:
        raise ValueError("stream debe ser 'audit' o 'evidence'")

    if stream_norm == "audit":
        table_name = "audit_logs"
        payload_fields: Tuple[str, ...] = (
            "timestamp",
            "actor",
            "action",
            "target",
            "ip_address",
            "severity",
            "metadata_json",
        )
    else:
        table_name = "evidence_events"
        payload_fields = (
            "control_id",
            "artifact_ref",
            "owner",
            "integrity_hash",
            "metadata_json",
            "created_at",
        )

    conn = db.get_conn()
    try:
        where = ["1=1"]
        params: List[Any] = []
        if from_id is not None:
            where.append("id >= ?")
            params.append(int(from_id))
        if to_id is not None:
            where.append("id <= ?")
            params.append(int(to_id))
        where_sql = " AND ".join(where)

        start_prev_hash = ""
        if from_id is not None:
            prev_row = conn.execute(
                f"SELECT chain_hash FROM {table_name} WHERE id < ? ORDER BY id DESC LIMIT 1",
                (int(from_id),),
            ).fetchone()
            start_prev_hash = (prev_row["chain_hash"] if prev_row else "") or ""

        select_fields = ", ".join(["id", *payload_fields, "chain_prev_hash", "chain_hash"])
        rows = conn.execute(
            f"""SELECT {select_fields}
                FROM {table_name}
                WHERE {where_sql}
                ORDER BY id ASC""",
            params,
        ).fetchall()

        prev_hash = start_prev_hash
        total = 0
        first_invalid_id: Optional[int] = None
        first_invalid_reason = ""
        last_checked_id: Optional[int] = None

        for row in rows:
            total += 1
            record = dict(row)
            payload = {field: (record.get(field) if record.get(field) is not None else "") for field in payload_fields}
            expected_hash = _build_chain_hash(prev_hash, payload)
            chain_prev = (record.get("chain_prev_hash") or "")
            chain_hash = (record.get("chain_hash") or "")
            last_checked_id = int(record["id"])
            if chain_prev != prev_hash:
                first_invalid_id = last_checked_id
                first_invalid_reason = "chain_prev_hash mismatch"
                break
            if chain_hash != expected_hash:
                first_invalid_id = last_checked_id
                first_invalid_reason = "chain_hash mismatch"
                break
            prev_hash = chain_hash

        return {
            "ok": first_invalid_id is None,
            "stream": stream_norm,
            "total_checked": total,
            "first_invalid_id": first_invalid_id,
            "first_invalid_reason": first_invalid_reason,
            "from_id": from_id,
            "to_id": to_id,
            "last_checked_id": last_checked_id,
        }
    finally:
        conn.close()

def record_parallel_go_no_go_decision(
    *,
    decision: str,
    decided_by: str,
    signers: List[str],
    rationale: str,
    evidence_refs: Optional[List[str]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    decided_at: Optional[str] = None,
) -> Dict[str, Any]:
    normalized = (decision or "").strip().lower()
    if normalized not in {"go", "no_go"}:
        raise ValueError("decision debe ser 'go' o 'no_go'")
    if not signers:
        raise ValueError("signers es obligatorio")

    when = _normalize_iso_utc(decided_at) or db.now_utc_iso()
    now = db.now_utc_iso()
    payload_metrics = metrics or {}
    conn = db.get_conn()
    try:
        row = conn.execute(
            """INSERT INTO parallel_decisions
               (decision, decided_at, decided_by, signers_json, rationale, evidence_refs_json, metrics_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                normalized,
                when,
                decided_by,
                _stable_json(signers),
                (rationale or "").strip(),
                _stable_json(evidence_refs or []),
                _stable_json(payload_metrics),
                now,
            ),
        ).fetchone()
        conn.commit()
        decision_id = int(row["id"]) if row else 0
        out_row = conn.execute(
            "SELECT * FROM parallel_decisions WHERE id = ?",
            (decision_id,),
        ).fetchone()
        result = dict(out_row) if out_row else {}
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.5.37",
            artifact_ref=f"parallel_go_no_go:{result.get('id')}",
            owner=decided_by,
            integrity_hash="",
            metadata={
                "decision": normalized,
                "signers": signers,
                "evidence_refs": evidence_refs or [],
            },
        )
    except Exception as e:
        logger.warning(f"[parallel_go_no_go] evidence_event no crítico falló: {e}")
    return result


def list_parallel_kpi_daily(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Lista snapshots KPI diarios del período de migración paralela."""
    conn = db.get_conn()
    try:
        clauses: List[str] = []
        params: List[Any] = []
        if date_from:
            clauses.append("snapshot_date >= ?")
            params.append(date_from[:10])
        if date_to:
            clauses.append("snapshot_date <= ?")
            params.append(date_to[:10])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM parallel_kpi_daily {where} ORDER BY snapshot_date DESC LIMIT 90",
            params,
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    except Exception:
        return {"items": []}
    finally:
        conn.close()


def record_parallel_kpi_snapshot(
    snapshot_date: str,
    metrics: Dict[str, Any],
    recorded_by: str = "system",
) -> Dict[str, Any]:
    """Registra un snapshot KPI diario del período de migración paralela."""
    conn = db.get_conn()
    try:
        now = _now_dt().isoformat()
        row = conn.execute(
            """
            INSERT INTO parallel_kpi_daily (snapshot_date, metrics_json, recorded_by, recorded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_date) DO UPDATE
              SET metrics_json = excluded.metrics_json,
                  recorded_by  = excluded.recorded_by,
                  recorded_at  = excluded.recorded_at
            RETURNING *
            """,
            (snapshot_date[:10], _stable_json(metrics), recorded_by, now),
        ).fetchone()
        conn.commit()
        return dict(row) if row else {}
    finally:
        conn.close()

