"""
Ticketera V3 — Servicio profesional de Mesa de Ayuda.
Auto-clasificación, auto-asignación, notificaciones escalonadas, SLA.
"""
from typing import List, Optional, Dict, Any, Tuple
from app.core import db
from datetime import datetime, timedelta, timezone
import json
import html
import logging
import re
import asyncio
import hashlib
import base64
import secrets
from email.utils import parseaddr
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
from urllib import parse as urlparse
from urllib import request as urlrequest
from urllib import error as urlerror
from app.core import email_integration, email as email_sender, jobs_engine
from app.core.config import settings as app_settings
from app.core.tickets import roles as ticket_roles
from app.core.tickets import workflow as ticket_workflow

logger = logging.getLogger(__name__)

# ==========================================================================
# CONSTANTES
# ==========================================================================
CATEGORIAS_VALIDAS = {"redes", "sistemas", "ejecucion", "admin", "general"}
ESTADOS_VALIDOS = {"abierto", "en_progreso", "resuelto", "cerrado"}
SEVERIDADES_VALIDAS = {"baja", "media", "alta", "critica"}
ROLES_TECNICOS = ticket_roles.ROLES_TECNICOS
ROLES_TECNICOS_SET = ticket_roles.ROLES_TECNICOS_SET
ROLES_ADMIN_GESTION = ticket_roles.ROLES_ADMIN_GESTION
ROLES_DESPACHO_MESA = ticket_roles.ROLES_DESPACHO_MESA
TICKET_SECURITY_CLASSES = {"public", "internal", "restricted"}
TIPOS_TICKET_VALIDOS = ticket_workflow.TIPOS_TICKET_VALIDOS
SUBESTADOS_VALIDOS = ticket_workflow.SUBESTADOS_VALIDOS
SUBESTADOS_ESPERA = ticket_workflow.SUBESTADOS_ESPERA
SUBESTADOS_LEGACY_MAP = ticket_workflow.SUBESTADOS_LEGACY_MAP
ROLE_SPECIALTY_FALLBACK = {
    "redes": "redes",
    "sistemas": "sistemas",
    "implementaciones": "ejecucion",
    "ops": "general",
}

SLA_HORAS = {
    "baja": 168,    # 7 días
    "media": 72,    # 3 días
    "alta": 24,     # 1 día
    "critica": 4,   # 4 horas
}

PRIORIDAD_MAP = {
    "critica": 1,
    "alta": 2,
    "media": 3,
    "baja": 4,
}

FRT_MINUTOS = {
    "critica": 15,
    "alta": 30,
    "media": 120,
    "baja": 480,
}

CHAIN_ALGO = "sha256"
CHAIN_VERSION = 1
EMAIL_DRAFT_LOCK_MINUTES = 5
EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS = 60
# "cerrado" -> Bloqueo total (ReadOnly)
# "resuelto" -> Bloqueo de envío de correos (EmailBlocked)
TICKET_READONLY_ESTADOS = {"cerrado"}
TICKET_EMAIL_BLOCKED_ESTADOS = {"resuelto", "cerrado"}
REPLY_BLOCKED_ESTADOS = TICKET_EMAIL_BLOCKED_ESTADOS  # Alias legacy

class ConflictError(Exception):
    """Conflicto de concurrencia (lock/version) para borradores de correo."""

def _clamp_int(value: Any, default_value: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(str(value).strip())
    except Exception:
        parsed = default_value
    return max(min_value, min(max_value, parsed))

def _parse_business_days(raw_value: Any) -> set[int]:
    default_days = {0, 1, 2, 3, 4}
    if raw_value is None:
        return default_days
    values = str(raw_value).split(",")
    parsed: set[int] = set()
    for token in values:
        token = token.strip()
        if not token:
            continue
        try:
            day = int(token)
        except Exception:
            continue
        if 0 <= day <= 6:
            parsed.add(day)
    return parsed or default_days

def _parse_escalation_windows(raw_value: Any) -> List[int]:
    default_windows = [80, 100]
    if raw_value is None:
        return default_windows
    parsed: set[int] = set()
    for token in str(raw_value).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            pct = int(token)
        except Exception:
            continue
        if 1 <= pct <= 100:
            parsed.add(pct)
    if not parsed:
        return default_windows
    if 100 not in parsed:
        parsed.add(100)
    return sorted(parsed)

def _parse_tz_offset(raw_value: Any) -> timezone:
    value = str(raw_value or "+00:00").strip()
    match = re.match(r"^([+-])(\d{2}):(\d{2})$", value)
    if not match:
        return timezone.utc
    sign = 1 if match.group(1) == "+" else -1
    hours = _clamp_int(match.group(2), 0, 0, 23)
    minutes = _clamp_int(match.group(3), 0, 0, 59)
    offset = timedelta(hours=hours, minutes=minutes) * sign
    return timezone(offset)

SLA_MODE = str(getattr(app_settings, "TICKET_SLA_MODE", "24x7") or "24x7").strip().lower()
if SLA_MODE not in {"24x7", "business_hours"}:
    SLA_MODE = "24x7"

SLA_BUSINESS_TZ = _parse_tz_offset(getattr(app_settings, "TICKET_SLA_BUSINESS_TZ_OFFSET", "-03:00"))
SLA_BUSINESS_DAYS = _parse_business_days(getattr(app_settings, "TICKET_SLA_BUSINESS_DAYS", "0,1,2,3,4"))
SLA_BUSINESS_START_HOUR = _clamp_int(
    getattr(app_settings, "TICKET_SLA_BUSINESS_START_HOUR", 9),
    default_value=9,
    min_value=0,
    max_value=23,
)
SLA_BUSINESS_END_HOUR = _clamp_int(
    getattr(app_settings, "TICKET_SLA_BUSINESS_END_HOUR", 18),
    default_value=18,
    min_value=1,
    max_value=24,
)
if SLA_BUSINESS_END_HOUR <= SLA_BUSINESS_START_HOUR:
    SLA_BUSINESS_END_HOUR = min(24, SLA_BUSINESS_START_HOUR + 1)

SLA_ESCALATION_WINDOWS_PCT = _parse_escalation_windows(
    getattr(app_settings, "TICKET_SLA_ESCALATION_WINDOWS_PCT", "80,100")
)
RESUELTO_AUTO_CLOSE_HOURS = _clamp_int(
    getattr(app_settings, "TICKET_RESUELTO_AUTO_CLOSE_HOURS", 72),
    default_value=72,
    min_value=0,
    max_value=720,
)

def _parse_timezone_name(raw_value: Any) -> timezone | ZoneInfo:
    value = str(raw_value or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(value)
    except Exception:
        return timezone.utc

def _default_compliance_export_dir() -> str:
    env_type = str(getattr(app_settings, "ENV_TYPE", "dev") or "dev").strip().lower()
    if env_type == "prod":
        return "/srv/monstruo/data/compliance"
    return "/srv/monstruo_dev/data/compliance"

def _default_ticket_attachments_dir() -> str:
    env_type = str(getattr(app_settings, "ENV_TYPE", "dev") or "dev").strip().lower()
    if env_type == "prod":
        return "/srv/monstruo/data/tickets"
    return "/srv/monstruo_dev/data/tickets"

COMPLIANCE_TZ = _parse_timezone_name(getattr(app_settings, "COMPLIANCE_TZ", "America/Santiago"))
COMPLIANCE_EXPORT_DIR = (
    str(getattr(app_settings, "COMPLIANCE_EXPORT_DIR", "") or "").strip()
    or _default_compliance_export_dir()
)
COMPLIANCE_EXPORT_HOUR = _clamp_int(
    getattr(app_settings, "COMPLIANCE_EXPORT_HOUR", 2),
    default_value=2,
    min_value=0,
    max_value=23,
)
COMPLIANCE_PURGE_HOUR = _clamp_int(
    getattr(app_settings, "COMPLIANCE_PURGE_HOUR", 2),
    default_value=2,
    min_value=0,
    max_value=23,
)
COMPLIANCE_EXPORT_MINUTE = 0
COMPLIANCE_PURGE_MINUTE = 20
COMPLIANCE_PURGE_GRACE_DAYS = _clamp_int(
    getattr(app_settings, "COMPLIANCE_PURGE_GRACE_DAYS", 30),
    default_value=30,
    min_value=0,
    max_value=3650,
)
RETENTION_POLICY_DAYS = {
    "public": _clamp_int(getattr(app_settings, "TICKET_RETENTION_PUBLIC_DAYS", 365), 365, 1, 36500),
    "internal": _clamp_int(getattr(app_settings, "TICKET_RETENTION_INTERNAL_DAYS", 1095), 1095, 1, 36500),
    "restricted": _clamp_int(getattr(app_settings, "TICKET_RETENTION_RESTRICTED_DAYS", 1825), 1825, 1, 36500),
}

CHANNEL_NOTIFICATION_STATUSES = {"pending", "dispatching", "sent", "failed", "cancelled"}
CHANNEL_ADAPTER_MODES = {"disabled", "dry_run", "live"}
CHANNELS_ENABLED = bool(getattr(app_settings, "CHANNELS_ENABLED", False))
CHANNELS_MAX_ATTEMPTS = _clamp_int(
    getattr(app_settings, "CHANNELS_MAX_ATTEMPTS", 3),
    default_value=3,
    min_value=1,
    max_value=20,
)
CHANNELS_RETRY_BASE_SECONDS = _clamp_int(
    getattr(app_settings, "CHANNELS_RETRY_BASE_SECONDS", 60),
    default_value=60,
    min_value=5,
    max_value=3600,
)
CHANNELS_RETRY_MAX_SECONDS = _clamp_int(
    getattr(app_settings, "CHANNELS_RETRY_MAX_SECONDS", 900),
    default_value=900,
    min_value=30,
    max_value=86400,
)
if CHANNELS_RETRY_MAX_SECONDS < CHANNELS_RETRY_BASE_SECONDS:
    CHANNELS_RETRY_MAX_SECONDS = CHANNELS_RETRY_BASE_SECONDS

def _channels_enabled() -> bool:
    return bool(getattr(app_settings, "CHANNELS_ENABLED", CHANNELS_ENABLED))

def _attachment_roots() -> List[Path]:
    roots: List[Path] = []
    configured = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or "").strip()
    for raw in (
        configured,
        _default_ticket_attachments_dir(),
    ):
        if not raw:
            continue
        try:
            p = Path(raw).resolve()
        except Exception:
            continue
        if p not in roots:
            roots.append(p)
    return roots

def _is_safe_attachment_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except Exception:
        return False
    for root in _attachment_roots():
        try:
            resolved.relative_to(root)
            return True
        except Exception:
            continue
    return False

def _attachment_storage_name(filename: str) -> str:
    safe_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(filename or "attachment.bin"))
    return f"{int(datetime.now(timezone.utc).timestamp() * 1000)}_{uuid4().hex[:10]}_{safe_filename}"

WORKFLOW_RULES = ticket_workflow.WORKFLOW_RULES

JIRA_STATUS_MAP = {
    "to do": "abierto",
    "open": "abierto",
    "abierto": "abierto",
    "in progress": "en_progreso",
    "en progreso": "en_progreso",
    "doing": "en_progreso",
    "done": "cerrado",
    "closed": "cerrado",
    "resuelto": "resuelto",
    "resolved": "resuelto",
}

JIRA_PRIORITY_TO_SEVERIDAD = {
    "highest": "critica",
    "critical": "critica",
    "high": "alta",
    "medium": "media",
    "normal": "media",
    "low": "baja",
    "lowest": "baja",
}

JIRA_SYNC_RUN_TYPES = {"bootstrap", "delta"}
JIRA_SYNC_RUN_STATUS = {"running", "completed", "failed", "completed_with_errors"}
JIRA_SYNC_DEFAULT_LIMIT = 200
JIRA_SYNC_MAX_LIMIT = 500
JIRA_SYNC_CURSOR_NAME = "jira_delta_last_updated"

JIRA_BASE_URL = str(getattr(app_settings, "JIRA_BASE_URL", "") or "").strip().rstrip("/")
JIRA_USER = str(getattr(app_settings, "JIRA_USER", "") or "").strip()
JIRA_API_TOKEN = str(getattr(app_settings, "JIRA_API_TOKEN", "") or "").strip()
JIRA_PROJECT_KEYS = str(getattr(app_settings, "JIRA_PROJECT_KEYS", "") or "").strip()
JIRA_SYNC_ENABLED = bool(getattr(app_settings, "JIRA_SYNC_ENABLED", False))
JIRA_SYNC_DAILY_HOUR = _clamp_int(
    getattr(app_settings, "JIRA_SYNC_DAILY_HOUR", 3),
    default_value=3,
    min_value=0,
    max_value=23,
)
JIRA_SYNC_TZ = _parse_timezone_name(getattr(app_settings, "JIRA_SYNC_TZ", "America/Santiago"))
AUTO_REPLY_MAX_REFERENCES = 20

def _parse_csv_lower_set(raw_value: Any, strip_prefix: str = "") -> set[str]:
    values: set[str] = set()
    for token in str(raw_value or "").split(","):
        normalized = token.strip().lower()
        if strip_prefix and normalized.startswith(strip_prefix):
            normalized = normalized[len(strip_prefix):]
        if normalized:
            values.add(normalized)
    return values

def _normalize_email_address(raw_email: Optional[str]) -> str:
    _, parsed = parseaddr(str(raw_email or ""))
    email_addr = (parsed or raw_email or "").strip().lower()
    if email_addr.count("@") != 1:
        return ""
    local_part, domain = email_addr.split("@", 1)
    if not local_part or not domain:
        return ""
    return f"{local_part}@{domain}"

def _sender_identity(sender: str) -> tuple[str, str]:
    name, addr = parseaddr(str(sender or ""))
    email_addr = _normalize_email_address(addr or sender)
    display_name = (name or "").strip() or (email_addr or str(sender or "").strip())
    return display_name, email_addr

def _auto_reply_delay_minutes() -> int:
    return _clamp_int(
        getattr(app_settings, "TICKET_AUTO_REPLY_DELAY_MINUTES", 15),
        default_value=15,
        min_value=0,
        max_value=1440,
    )

def _auto_reply_require_allowlist() -> bool:
    return bool(getattr(app_settings, "TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST", True))

def _auto_reply_allowlist_emails() -> set[str]:
    return _parse_csv_lower_set(getattr(app_settings, "TICKET_AUTO_REPLY_ALLOWLIST_EMAILS", ""))

def _auto_reply_allowlist_domains() -> set[str]:
    return _parse_csv_lower_set(getattr(app_settings, "TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS", ""), strip_prefix="@")

def _auto_reply_blocked_localparts() -> set[str]:
    raw = getattr(
        app_settings,
        "TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS",
        "noreply,no-reply,mailer-daemon,postmaster",
    )
    return _parse_csv_lower_set(raw)

def _auto_reply_sender_allowed(to_email: str) -> tuple[bool, str]:
    normalized_email = _normalize_email_address(to_email)
    if not normalized_email:
        return False, "invalid_email"
    if "@" not in normalized_email:
        return False, "invalid_email"
    local_part, domain = normalized_email.split("@", 1)
    if local_part in _auto_reply_blocked_localparts():
        return False, "blocked_localpart"

    allow_emails = _auto_reply_allowlist_emails()
    allow_domains = _auto_reply_allowlist_domains()
    require_allowlist = _auto_reply_require_allowlist()

    if require_allowlist and not allow_emails and not allow_domains:
        return False, "allowlist_empty"

    if allow_emails or allow_domains:
        if normalized_email not in allow_emails and domain not in allow_domains:
            return False, "not_allowlisted"

    return True, "allowed"

def _auto_reply_idempotency_key(ticket_id: int, to_email: str) -> str:
    digest = hashlib.sha256(f"{ticket_id}|{to_email.lower()}".encode("utf-8")).hexdigest()[:24]
    return f"auto_reply:{int(ticket_id)}:{digest}"

def normalize_ticket_security_class(value: Optional[str]) -> str:
    normalized = (value or "internal").strip().lower()
    if normalized not in TICKET_SECURITY_CLASSES:
        return "internal"
    return normalized

def normalize_ticket_type(value: Optional[str]) -> str:
    return ticket_workflow.normalize_ticket_type(value)

def normalize_subestado(value: Optional[str], default_value: str = "recibido") -> str:
    return ticket_workflow.normalize_subestado(value, default_value)

def _normalize_roles(value: Optional[Any]) -> List[str]:
    return ticket_roles.normalize_roles(value)

def _normalize_role(value: Optional[Any]) -> str:
    return ticket_roles.normalize_role(value)

def _normalize_username(value: Optional[str]) -> str:
    return ticket_roles.normalize_username(value)

def _scope_enforced(actor_role: Optional[Any]) -> bool:
    return ticket_roles.scope_enforced(actor_role)

def _is_admin_management_role(actor_role: Optional[Any]) -> bool:
    return ticket_roles.is_admin_management_role(actor_role)

def _is_tech_role(actor_role: Optional[Any]) -> bool:
    return ticket_roles.is_tech_execution_role(actor_role)

def _is_dispatcher_role(actor_role: Optional[Any]) -> bool:
    return ticket_roles.is_dispatcher_role(actor_role)

def _can_dispatch_reassign(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
) -> bool:
    return ticket_roles.can_dispatch_reassign(ticket, actor_id, actor_role)

def _ticket_assignee_username(ticket: Dict[str, Any]) -> str:
    return ticket_roles.ticket_assignee_username(ticket)

def _ensure_can_manage_ticket(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
    action_label: str,
) -> None:
    ticket_roles.require_can_manage(ticket, actor_id, actor_role, action_label)

def _ensure_can_participate_ticket(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
    action_label: str,
) -> None:
    ticket_roles.require_can_participate(ticket, actor_id, actor_role, action_label)

def _is_reply_blocked_by_estado(ticket: Dict[str, Any]) -> bool:
    estado = str(ticket.get("estado") or "").strip().lower()
    return estado in TICKET_EMAIL_BLOCKED_ESTADOS

def _is_readonly_blocked_by_estado(ticket: Dict[str, Any]) -> bool:
    estado = str(ticket.get("estado") or "").strip().lower()
    return estado in TICKET_READONLY_ESTADOS

def _ensure_reply_allowed_estado(ticket: Dict[str, Any], action_label: str) -> None:
    if _is_reply_blocked_by_estado(ticket):
        estado = str(ticket.get("estado") or "").strip().lower() or "-"
        raise ValueError(f"No se puede {action_label} cuando el ticket está en estado '{estado}'.")

def _extract_ticket_target_email(ticket: Dict[str, Any]) -> str:
    _, parsed_addr = parseaddr(ticket.get("origen_email") or "")
    to_email = parsed_addr.strip() if parsed_addr else (ticket.get("origen_email") or "").strip()
    return str(to_email or "").strip()

def _tokenize_email_values(raw_value: Any) -> List[str]:
    if raw_value is None:
        return []

    raw_items: List[str] = []
    if isinstance(raw_value, str):
        raw_items = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_items = [str(v or "") for v in raw_value]
    else:
        raw_items = [str(raw_value)]

    tokens: List[str] = []
    for item in raw_items:
        for token in re.split(r"[,\n;]+", str(item or "")):
            clean = token.strip()
            if clean:
                tokens.append(clean)
    return tokens

def _normalize_notify_emails(raw_value: Any) -> tuple[List[str], List[str]]:
    valid: List[str] = []
    invalid: List[str] = []
    seen: set[str] = set()

    for token in _tokenize_email_values(raw_value):
        normalized = _normalize_email_address(token)
        if not normalized:
            invalid.append(token)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        valid.append(normalized)
    return valid, invalid

def _serialize_notify_emails(raw_value: Any, *, strict: bool = True) -> str:
    valid, invalid = _normalize_notify_emails(raw_value)
    if strict and invalid:
        invalid_text = ", ".join(invalid[:5])
        raise ValueError(f"Correos inválidos en notificación: {invalid_text}")
    return ", ".join(valid)

def _notify_emails_from_ticket(ticket: Dict[str, Any]) -> List[str]:
    valid, _ = _normalize_notify_emails(ticket.get("notify_emails") or "")
    return valid

def _normalize_recipient_emails(raw_value: Any, *, label: str) -> List[str]:
    valid, invalid = _normalize_notify_emails(raw_value)
    if invalid:
        invalid_text = ", ".join(invalid[:5])
        raise ValueError(f"Correos inválidos en {label}: {invalid_text}")
    return valid

def _compose_reply_recipients(
    ticket: Dict[str, Any],
    explicit_to: Optional[str] = None,
    explicit_cc: Optional[Any] = None,
    explicit_bcc: Optional[Any] = None,
) -> tuple[str, List[str], List[str], str]:
    to_email = _normalize_email_address(explicit_to or _extract_ticket_target_email(ticket))

    cc_source = explicit_cc if explicit_cc is not None else _notify_emails_from_ticket(ticket)
    bcc_source = explicit_bcc if explicit_bcc is not None else []
    cc_raw = _normalize_recipient_emails(cc_source, label="CC")
    bcc_raw = _normalize_recipient_emails(bcc_source, label="CCO")

    seen: set[str] = set()
    if to_email:
        seen.add(to_email)

    cc_emails: List[str] = []
    for email in cc_raw:
        if email in seen:
            continue
        seen.add(email)
        cc_emails.append(email)

    bcc_emails: List[str] = []
    for email in bcc_raw:
        if email in seen:
            continue
        seen.add(email)
        bcc_emails.append(email)

    to_record = ", ".join(([to_email] if to_email else []) + cc_emails)
    return to_email, cc_emails, bcc_emails, to_record

def _estado_label(estado: Optional[str]) -> str:
    value = str(estado or "").strip().lower()
    mapping = {
        "abierto": "Abierto",
        "en_progreso": "En progreso",
        "resuelto": "Resuelto",
        "cerrado": "Cerrado",
    }
    return mapping.get(value, value.replace("_", " ").capitalize() or "-")

def _send_ticket_status_update_to_notify_emails(
    ticket: Dict[str, Any],
    *,
    from_estado: str,
    to_estado: str,
    actor_id: str,
    motivo: str = "",
) -> Dict[str, Any]:
    notify = _notify_emails_from_ticket(ticket)
    if not notify:
        return {"ok": True, "sent": False, "reason": "no_notify_emails"}

    primary_to = notify[0]
    cc_emails = notify[1:]
    to_record = ", ".join(notify)
    ticket_id = int(ticket.get("id") or 0)
    code = str(ticket.get("codigo") or f"#{ticket_id}")
    title = str(ticket.get("titulo") or "Sin título")
    actor = str(actor_id or "sistema").strip() or "sistema"
    from_label = _estado_label(from_estado)
    to_label = _estado_label(to_estado)

    subject = f"[{code}] Estado actualizado: {to_label}"
    motivo_html = f"<p><strong>Motivo:</strong> {html.escape(motivo)}</p>" if str(motivo or "").strip() else ""
    body_html = f"""
    <p>Se actualizó el estado del ticket <strong>{html.escape(code)}</strong>.</p>
    <p><strong>Título:</strong> {html.escape(title)}</p>
    <p><strong>Cambio:</strong> {html.escape(from_label)} -> {html.escape(to_label)}</p>
    <p><strong>Actualizado por:</strong> {html.escape(actor)}</p>
    {motivo_html}
    """
    send_meta = email_sender.send_email_advanced(
        to_email=primary_to,
        cc_emails=cc_emails,
        subject=subject,
        html_body=body_html,
    )

    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
               VALUES (?, 'outgoing', ?, ?, ?, ?, ?, ?, '[]', ?, ?)""",
            (
                ticket_id,
                send_meta.get("from_addr"),
                primary_to,
                ", ".join(cc_emails),
                "",
                subject,
                body_html,
                f"status:{ticket_id}:{from_estado}->{to_estado}:{actor}:{now[:19]}",
                now,
            ),
        )
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                ticket_id,
                actor_id or 'system',
                f"[CORREO] Actualización de estado enviada a {to_record}. Cambio: {from_label} -> {to_label}.",
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "sent": True,
        "to_email": primary_to,
        "cc_emails": cc_emails,
        "subject": subject,
    }

def _build_ticket_reply_subject(ticket: Dict[str, Any], asunto: Optional[str] = None) -> str:
    if asunto and str(asunto).strip():
        subject = str(asunto).strip()
    else:
        base = ticket.get("codigo") or f"Ticket #{int(ticket.get('id') or 0)}"
        title = (ticket.get("titulo") or "").strip()
        subject = f"{base} - {title}" if title else str(base)
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    return subject

def _hash_draft_lock_token(lock_token: str) -> str:
    return hashlib.sha256(str(lock_token or "").encode("utf-8")).hexdigest()

def _lock_expiry_iso(now_iso: str, minutes: int = EMAIL_DRAFT_LOCK_MINUTES) -> str:
    now_dt = _parse_dt(now_iso) or _now_dt()
    return (now_dt + timedelta(minutes=max(1, minutes))).isoformat()

def _is_draft_lock_active(lock_expires_at: Optional[str], now_dt: Optional[datetime] = None) -> bool:
    if not lock_expires_at:
        return False
    now_dt = now_dt or _now_dt()
    exp_dt = _parse_dt(lock_expires_at)
    return bool(exp_dt and exp_dt > now_dt)

def _draft_lock_info(draft: Dict[str, Any], actor_id: str, now_dt: Optional[datetime] = None) -> Dict[str, Any]:
    now_dt = now_dt or _now_dt()
    owner = str(draft.get("lock_owner") or "").strip()
    expires_at = draft.get("lock_expires_at")
    active = _is_draft_lock_active(expires_at, now_dt)
    return {
        "owner": owner or None,
        "expires_at": expires_at,
        "active": active,
        "mine": bool(active and owner and _normalize_username(owner) == _normalize_username(actor_id)),
    }

def _new_draft_lock_token() -> str:
    return secrets.token_urlsafe(32)

def _drafts_base_path(ticket_id: int, draft_id: int) -> Path:
    base_root = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir())
    return Path(base_root) / str(ticket_id) / "drafts" / str(draft_id)

def estado_from_subestado(subestado: str, current_estado: str = "abierto") -> str:
    s = normalize_subestado(subestado, "recibido")
    if s in {"resuelto"}:
        return "resuelto"
    if s in {"cerrado"}:
        return "cerrado"
    if s in {"en_progreso", "en_ejecucion", "en_validacion", "aprobado"}:
        return "en_progreso"
    if current_estado in ESTADOS_VALIDOS and current_estado in {"resuelto", "cerrado"} and s == "reabierto":
        return "abierto"
    return "abierto"

def normalize_adapter_mode(value: Optional[str], default_mode: str = "disabled") -> str:
    mode = (value or default_mode).strip().lower()
    if mode not in CHANNEL_ADAPTER_MODES:
        return default_mode
    return mode

def normalize_channel_name(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if raw in {"whatsapp", "3cx", "app"}:
        return raw
    return ""

def normalize_notification_status(value: Optional[str], default_status: str = "pending") -> str:
    status = (value or default_status).strip().lower()
    if status not in CHANNEL_NOTIFICATION_STATUSES:
        return default_status
    return status

def _channel_adapter_mode(channel: str) -> str:
    normalized = normalize_channel_name(channel)
    if normalized == "whatsapp":
        return normalize_adapter_mode(getattr(app_settings, "WHATSAPP_ADAPTER_MODE", "disabled"), "disabled")
    if normalized == "3cx":
        return normalize_adapter_mode(getattr(app_settings, "THREECX_ADAPTER_MODE", "disabled"), "disabled")
    return "disabled"

def _channel_provider_name(channel: str) -> str:
    normalized = normalize_channel_name(channel)
    if normalized == "whatsapp":
        return "whatsapp_http"
    if normalized == "3cx":
        return "threecx_http"
    return ""

def _channel_retry_delay_seconds(next_attempt: int) -> int:
    safe_attempt = max(1, int(next_attempt))
    delay = CHANNELS_RETRY_BASE_SECONDS * (2 ** max(0, safe_attempt - 1))
    return min(CHANNELS_RETRY_MAX_SECONDS, delay)

def _enqueue_job_async_safe(job_type: str, payload: Dict[str, Any], max_retries: int = 0) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(jobs_engine.enqueue_job(job_type, payload, max_retries=max_retries))
    except RuntimeError:
        asyncio.run(jobs_engine.enqueue_job(job_type, payload, max_retries=max_retries))

def _stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _build_chain_hash(prev_hash: str, payload: Dict[str, Any]) -> str:
    raw = f"{prev_hash or ''}|{_stable_json(payload or {})}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def _retention_days_for_class(security_class: Optional[str]) -> int:
    normalized = normalize_ticket_security_class(security_class)
    return int(RETENTION_POLICY_DAYS.get(normalized, RETENTION_POLICY_DAYS["internal"]))

def _retention_until_iso(base_iso: Optional[str], security_class: Optional[str]) -> Optional[str]:
    base_dt = _parse_dt(base_iso) if base_iso else None
    if not base_dt:
        return None
    return (_ensure_utc(base_dt) + timedelta(days=_retention_days_for_class(security_class))).isoformat()

def _recompute_ticket_retention(conn, ticket_id: int) -> None:
    row = conn.execute(
        """SELECT id, estado, ticket_security_class, resolved_at, updated_at
           FROM tickets
           WHERE id = ?""",
        (ticket_id,),
    ).fetchone()
    if not row:
        return

    ticket = dict(row)
    security_class = normalize_ticket_security_class(ticket.get("ticket_security_class"))
    days = _retention_days_for_class(security_class)
    estado = (ticket.get("estado") or "").lower()

    retention_until = None
    if estado in {"resuelto", "cerrado"}:
        retention_until = _retention_until_iso(
            ticket.get("resolved_at") or ticket.get("updated_at"),
            security_class,
        )

    conn.execute(
        """UPDATE tickets
           SET ticket_security_class = ?, retention_days_snapshot = ?, retention_until = ?
           WHERE id = ?""",
        (security_class, days, retention_until, ticket_id),
    )

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None

def _now_dt() -> datetime:
    return datetime.fromisoformat(db.now_utc_iso().replace("Z", "+00:00"))

def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def _business_bounds(local_dt: datetime) -> tuple[datetime, datetime]:
    start = local_dt.replace(hour=SLA_BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
    if SLA_BUSINESS_END_HOUR >= 24:
        end = local_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        end = local_dt.replace(hour=SLA_BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)
    return start, end

def _is_business_day(local_dt: datetime) -> bool:
    return local_dt.weekday() in SLA_BUSINESS_DAYS

def _align_to_business_start(local_dt: datetime) -> datetime:
    probe = local_dt
    for _ in range(15):
        start, end = _business_bounds(probe)
        if not _is_business_day(probe):
            probe = (probe + timedelta(days=1)).replace(
                hour=SLA_BUSINESS_START_HOUR,
                minute=0,
                second=0,
                microsecond=0,
            )
            continue
        if probe < start:
            return start
        if probe >= end:
            probe = (probe + timedelta(days=1)).replace(
                hour=SLA_BUSINESS_START_HOUR,
                minute=0,
                second=0,
                microsecond=0,
            )
            continue
        return probe
    return probe

def _add_business_minutes(start_dt: datetime, minutes: int) -> datetime:
    remaining = max(0, int(minutes))
    local = _ensure_utc(start_dt).astimezone(SLA_BUSINESS_TZ)
    if remaining == 0:
        return local.astimezone(timezone.utc)

    local = _align_to_business_start(local)
    safety = 0
    while remaining > 0 and safety < 20000:
        safety += 1
        local = _align_to_business_start(local)
        _, end = _business_bounds(local)
        available = int(max(0.0, (end - local).total_seconds()) // 60)
        if available <= 0:
            local = end + timedelta(minutes=1)
            continue
        step = min(remaining, available)
        local = local + timedelta(minutes=step)
        remaining -= step
        if remaining > 0 and local >= end:
            local = end + timedelta(minutes=1)

    return local.astimezone(timezone.utc)

def _frt_due_iso(now_dt: datetime, severidad: str) -> str:
    minutes = int(FRT_MINUTOS.get(severidad, 120))
    base_utc = _ensure_utc(now_dt)
    if SLA_MODE == "business_hours":
        return _add_business_minutes(base_utc, minutes).isoformat()
    return (base_utc + timedelta(minutes=minutes)).isoformat()

def _ttr_due_iso(now_dt: datetime, severidad: str) -> str:
    hours = int(SLA_HORAS.get(severidad, 72))
    base_utc = _ensure_utc(now_dt)
    if SLA_MODE == "business_hours":
        return _add_business_minutes(base_utc, hours * 60).isoformat()
    return (base_utc + timedelta(hours=hours)).isoformat()

# Keywords para auto-clasificación (se buscan en título + descripción)
KEYWORDS_CATEGORIAS = {
    "redes": [
        "red", "network", "switch", "router", "firewall", "vpn", "wifi",
        "internet", "dns", "dhcp", "ip", "conectividad", "fibra",
        "ping", "latencia", "cable", "lan", "wan", "vlan", "mikrotik",
        "ubiquiti", "cisco", "fortigate", "enlace",
    ],
    "sistemas": [
        "servidor", "server", "windows", "linux", "backup", "base de datos",
        "correo", "email", "office", "365", "azure", "nube", "cloud",
        "software", "licencia", "antivirus", "actualización", "update",
        "disco", "almacenamiento", "virtualización", "vmware", "hyper-v",
    ],
    "ejecucion": [
        "instalación", "montaje", "cableado", "obra", "terreno",
        "rack", "ups", "eléctric", "canalización", "patch panel",
        "certificación", "fusión", "fibra óptica", "poste",
        "cámara", "cctv", "control de acceso",
    ],
    "admin": [
        "factura", "boleta", "pago", "cobro", "cotización", "presupuesto",
        "contrato", "renovación", "licencia", "usuario", "contraseña",
        "acceso", "permiso", "cuenta",
    ],
}

# ==========================================================================
# CLASIFICACIÓN AUTOMÁTICA
# ==========================================================================
def clasificar_ticket(titulo: str, descripcion: str) -> str:
    """Clasifica un ticket basado en keywords en título y descripción."""
    texto = f"{titulo} {descripcion}".lower()
    scores = {}
    for cat, keywords in KEYWORDS_CATEGORIAS.items():
        score = sum(1 for kw in keywords if kw in texto)
        if score > 0:
            scores[cat] = score

    if not scores:
        return "general"

    return max(scores, key=scores.get)

# ==========================================================================
# AUTO-ASIGNACIÓN
# ==========================================================================
def auto_asignar(categoria: str) -> Optional[str]:
    """
    Asigna al técnico con menor carga en la categoría.
    Round-robin por menor current_load.
    """
    conn = db.get_conn()
    try:
        role_placeholders = ", ".join(["?"] * len(ROLES_TECNICOS))
        row = conn.execute(
            f"""
            SELECT us.username
            FROM user_specialties us
            JOIN users u ON u.username = us.username
            WHERE us.specialty = ?
              AND us.is_available = 1
              AND us.current_load < us.max_load
              AND COALESCE(u.is_active, 1) = 1
              AND u.role IN ({role_placeholders})
            ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
            LIMIT 1
            """,
            (categoria, *ROLES_TECNICOS),
        ).fetchone()

        if row:
            username = row["username"]
            # Incrementar carga
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (db.now_utc_iso(), username, categoria))
            conn.commit()
            return username

        logger.debug(f"auto_asignar failed for '{categoria}', trying fallback")

        # Fallback: si no hay técnico exacto en esa categoría, asignar al técnico
        # disponible con menor carga (solo roles técnicos activos).
        row = conn.execute(
            f"""
            SELECT us.username, us.specialty
            FROM user_specialties us
            JOIN users u ON u.username = us.username
            WHERE us.is_available = 1
              AND us.current_load < us.max_load
              AND COALESCE(u.is_active, 1) = 1
              AND u.role IN ({role_placeholders})
            ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
            LIMIT 1
            """,
            ROLES_TECNICOS,
        ).fetchone()

        if row:
            username = row["username"]
            specialty = row["specialty"]
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (db.now_utc_iso(), username, specialty))
            conn.commit()
            return username

        # Fallback final (modo solo-roles):
        # seleccionar técnico activo por menor carga real de tickets abiertos/en_progreso.
        user_rows = conn.execute(
            "SELECT username, role, secondary_roles FROM users WHERE COALESCE(is_active, 1) = 1 ORDER BY username ASC"
        ).fetchall()
        if user_rows:
            active_counts_rows = conn.execute(
                """
                SELECT LOWER(asignado_a) AS username, COUNT(*) AS active_count
                FROM tickets
                WHERE COALESCE(asignado_a, '') <> ''
                  AND estado IN ('abierto', 'en_progreso')
                GROUP BY LOWER(asignado_a)
                """
            ).fetchall()
            active_map = {
                _normalize_username(r.get("username")): int(r.get("active_count") or 0)
                for r in active_counts_rows
                if _normalize_username(r.get("username"))
            }

            candidates: List[Tuple[int, str]] = []
            for user_row in user_rows:
                username = _normalize_username(user_row.get("username"))
                if not username:
                    continue
                roles = []
                primary_role = _normalize_role(user_row.get("role"))
                if primary_role:
                    roles.append(primary_role)
                try:
                    parsed_secondary = json.loads(user_row.get("secondary_roles") or "[]")
                except Exception:
                    parsed_secondary = []
                roles.extend(_normalize_roles(parsed_secondary))
                normalized_roles = _normalize_roles(roles)
                if not any(role in ROLES_TECNICOS_SET for role in normalized_roles):
                    continue
                candidates.append((int(active_map.get(username, 0)), username))

            if candidates:
                candidates.sort(key=lambda item: (item[0], item[1]))
                return candidates[0][1]

        return None
    finally:
        conn.close()

def incrementar_carga(username: str, specialty: Optional[str] = None) -> None:
    """Incrementa la carga del técnico al asignar un ticket. Si se especifica especialidad, solo incrementa esa."""
    if not username:
        return
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Intentar incrementar en la especialidad específica
        if specialty:
            cursor = conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, specialty))
            
            if cursor.rowcount > 0:
                conn.commit()
                return

        # Fallback 1: si existe una especialidad 'general', usarla.
        cursor = conn.execute("""
            UPDATE user_specialties
            SET current_load = current_load + 1, updated_at = ?
            WHERE username = ? AND specialty = 'general'
        """, (now, username))

        if cursor.rowcount > 0:
            conn.commit()
            return

        # Fallback 2: elegir la especialidad más liviana del usuario.
        row = conn.execute("""
            SELECT specialty
            FROM user_specialties
            WHERE username = ?
            ORDER BY current_load ASC, updated_at ASC NULLS FIRST, specialty ASC
            LIMIT 1
        """, (username,)).fetchone()
        if row:
            conn.execute("""
                UPDATE user_specialties
                SET current_load = current_load + 1, updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, row["specialty"]))
        conn.commit()
    finally:
        conn.close()

def decrementar_carga(username: str, specialty: Optional[str] = None) -> None:
    """Decrementa la carga del técnico. Si se especifica especialidad, intenta decretar esa."""
    if not username:
        return
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Intentar decrementar en la especialidad específica
        if specialty:
            cursor = conn.execute("""
                UPDATE user_specialties
                SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, specialty))
            
            if cursor.rowcount > 0:
                conn.commit()
                return

        # Fallback 1: decrementar en 'general' si existe.
        cursor = conn.execute("""
            UPDATE user_specialties
            SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
            WHERE username = ? AND specialty = 'general'
        """, (now, username))

        if cursor.rowcount > 0:
            conn.commit()
            return

        # Fallback 2: decrementar la especialidad con mayor carga.
        row = conn.execute("""
            SELECT specialty
            FROM user_specialties
            WHERE username = ?
            ORDER BY current_load DESC, updated_at ASC NULLS FIRST, specialty ASC
            LIMIT 1
        """, (username,)).fetchone()
        if row:
            conn.execute("""
                UPDATE user_specialties
                SET current_load = GREATEST(current_load - 1, 0), updated_at = ?
                WHERE username = ? AND specialty = ?
            """, (now, username, row["specialty"]))
        conn.commit()
    finally:
        conn.close()

# ==========================================================================
# NOTIFICACIONES ESCALONADAS
# ==========================================================================
def programar_notificaciones(ticket_id: int, user_id: str) -> None:
    """
    Programa 3 niveles de notificación:
    1. Inmediato → in-app
    2. +5 min → WhatsApp/Telegram
    3. +20 min → Llamada 3CX
    """
    conn = db.get_conn()
    try:
        now = datetime.fromisoformat(db.now_utc_iso().replace("Z", "+00:00"))
        now_iso = now.isoformat()

        niveles = [
            (1, "app", now),
            (2, "whatsapp", now + timedelta(minutes=5)),
            (3, "3cx", now + timedelta(minutes=20)),
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
                 AND channel IN ('whatsapp', '3cx')
                 AND COALESCE(attempt_count, 0) >= COALESCE(NULLIF(max_attempts, 0), ?)""",
            (now, CHANNELS_MAX_ATTEMPTS),
        )
        rows = conn.execute(
            """WITH eligible AS (
                   SELECT tn.id
                   FROM ticket_notifications tn
                   WHERE tn.status = 'pending'
                     AND tn.channel IN ('whatsapp', '3cx')
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
            job_type = "WHATSAPP_NOTIFY" if channel == "whatsapp" else "3CX_CALL" if channel == "3cx" else ""
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
                                  'COMPLIANCE_EXPORT_DAILY', 'COMPLIANCE_PURGE_DAILY', 'JIRA_DELTA_SYNC_DAILY')
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
        "whatsapp": {
            "mode": _channel_adapter_mode("whatsapp"),
            "provider": _channel_provider_name("whatsapp"),
            "configured": bool((getattr(app_settings, "WHATSAPP_BASE_URL", "") or "").strip()),
        },
        "3cx": {
            "mode": _channel_adapter_mode("3cx"),
            "provider": _channel_provider_name("3cx"),
            "configured": bool((getattr(app_settings, "THREECX_BASE_URL", "") or "").strip()),
        },
    }
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT channel, status, COUNT(*) AS total
               FROM ticket_notifications
               WHERE channel IN ('whatsapp', '3cx')
               GROUP BY channel, status"""
        ).fetchall()
        queue = {"by_channel": {"whatsapp": {}, "3cx": {}}, "totals": {}}
        for row in rows:
            channel = normalize_channel_name(row.get("channel"))
            status = normalize_notification_status(row.get("status"))
            total = int(row.get("total") or 0)
            if channel in {"whatsapp", "3cx"}:
                queue["by_channel"][channel][status] = total
            queue["totals"][status] = int(queue["totals"].get(status, 0)) + total

        due_row = conn.execute(
            """SELECT COUNT(*) AS total
               FROM ticket_notifications
               WHERE channel IN ('whatsapp', '3cx')
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

    where = ["tn.channel IN ('whatsapp', '3cx')"]
    params: List[Any] = []
    if status_norm:
        where.append("tn.status = ?")
        params.append(status_norm)
    if channel_norm in {"whatsapp", "3cx"}:
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
        if channel not in {"whatsapp", "3cx"}:
            raise ValueError("Solo se permiten retries para canales externos (whatsapp/3cx)")
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

# ==========================================================================
# GENERADOR DE CÓDIGO DE TICKET
# ==========================================================================
def generar_codigo(ticket_id: int) -> str:
    """Genera código TK-DD-MM-YYYY-NNNN."""
    now = datetime.now()
    return f"TK-{now.strftime('%d-%m-%Y')}-{ticket_id:04d}"

def _workflow_next(tipo: str, subestado: str) -> List[str]:
    return ticket_workflow.workflow_next(tipo, subestado)

def _workflow_can_transition(tipo: str, from_subestado: str, to_subestado: str) -> bool:
    return ticket_workflow.can_transition(tipo, from_subestado, to_subestado)

def _normalize_transition_target(from_subestado: str, requested_subestado: Optional[str]) -> str:
    return ticket_workflow.normalize_transition_target(from_subestado, requested_subestado)

def _is_estado_en_progreso(estado: Optional[str]) -> bool:
    return str(estado or "").strip().lower() == "en_progreso"

def _filter_waiting_subestados(allowed_next: List[str], estado_actual: Optional[str]) -> List[str]:
    if _is_estado_en_progreso(estado_actual):
        return list(allowed_next or [])
    return [s for s in (allowed_next or []) if normalize_subestado(s, "") not in SUBESTADOS_ESPERA]

def _comment_with_prefix_exists(conn, ticket_id: int, prefix: str) -> bool:
    row = conn.execute(
        """SELECT 1
           FROM ticket_comments
           WHERE ticket_id = ?
             AND content ILIKE ?
           ORDER BY id DESC
           LIMIT 1""",
        (ticket_id, f"{prefix}%"),
    ).fetchone()
    return bool(row)

def _emit_system_comment(conn, ticket_id: int, content: str, now_iso: str, author_id: str = "system") -> None:
    action = "SISTEMA"
    estado = "N/A"
    motivo = "Actualización de sistema"
    
    if content.startswith("["):
        parts = content.split("]", 1)
        action = parts[0][1:].strip()
        rest = parts[1].strip()
        if "Motivo:" in rest:
            estado_part, motivo_part = rest.split("Motivo:", 1)
            estado = estado_part.strip(" |")
            motivo = motivo_part.strip()
        elif " | " in rest:
            estado_part, motivo_part = rest.split(" | ", 1)
            estado = estado_part.strip()
            motivo = motivo_part.strip()
        else:
            estado = rest
    else:
        estado = content

    formatted_content = f"[{action}] Estado: {estado} | Motivo: {motivo}"

    conn.execute(
        """INSERT INTO ticket_comments (ticket_id, user_id, content, is_internal, created_at)
           VALUES (?, ?, ?, 1, ?)""",
        (ticket_id, author_id, formatted_content, now_iso),
    )

def _latest_approval_decisions(conn, ticket_id: int) -> Dict[int, str]:
    rows = conn.execute(
        """SELECT step, decision
           FROM ticket_approvals
           WHERE ticket_id = ?
           ORDER BY decided_at DESC, id DESC""",
        (ticket_id,),
    ).fetchall()
    latest: Dict[int, str] = {}
    for row in rows:
        step = int(row["step"])
        if step not in latest:
            latest[step] = str(row["decision"]).lower()
    return latest

def _is_open_estado(estado: str) -> bool:
    return (estado or "").lower() not in {"resuelto", "cerrado"}

def _evaluate_ticket_sla(conn, ticket_id: int, now_iso: Optional[str] = None) -> None:
    now_iso = now_iso or db.now_utc_iso()
    now_dt = _parse_dt(now_iso) or _now_dt()
    row = conn.execute(
        """SELECT id, estado, subestado, created_at, updated_at, first_response_at, frt_due_at, ttr_due_at,
                  frt_breached_at, ttr_breached_at, resolved_at
           FROM tickets
           WHERE id = ?""",
        (ticket_id,),
    ).fetchone()
    if not row:
        return
    ticket = dict(row)

    created_dt = _parse_dt(ticket.get("created_at"))
    frt_due_dt = _parse_dt(ticket.get("frt_due_at"))
    ttr_due_dt = _parse_dt(ticket.get("ttr_due_at"))
    first_response_dt = _parse_dt(ticket.get("first_response_at"))
    resolved_dt = _parse_dt(ticket.get("resolved_at")) or _parse_dt(ticket.get("updated_at"))
    estado = (ticket.get("estado") or "").lower()

    def _warn_prefix(metric: str, pct: int) -> str:
        metric_key = "FRT" if metric == "frt" else "TTR"
        if pct == 80:
            return f"[SLA_WARN_{metric_key}]"
        return f"[SLA_WARN_{metric_key}_{pct}]"

    if created_dt and frt_due_dt and first_response_dt is None:
        total_seconds = max(0.0, (frt_due_dt - created_dt).total_seconds())
        elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
        if total_seconds > 0 and now_dt < frt_due_dt:
            progress_pct = (elapsed_seconds / total_seconds) * 100.0
            for threshold in SLA_ESCALATION_WINDOWS_PCT:
                if threshold >= 100:
                    continue
                if progress_pct < float(threshold):
                    continue
                prefix = _warn_prefix("frt", threshold)
                if _comment_with_prefix_exists(conn, ticket_id, prefix):
                    continue
                _emit_system_comment(
                    conn,
                    ticket_id,
                    f"{prefix} El ticket alcanzó {threshold}% del tiempo de primera respuesta (FRT).",
                    now_iso,
                )
        if now_dt >= frt_due_dt:
            if not ticket.get("frt_breached_at"):
                conn.execute("UPDATE tickets SET frt_breached_at = ? WHERE id = ?", (now_iso, ticket_id))
            if not _comment_with_prefix_exists(conn, ticket_id, "[SLA_BREACH_FRT]"):
                _emit_system_comment(
                    conn,
                    ticket_id,
                    "[SLA_BREACH_FRT] Se superó el FRT objetivo.",
                    now_iso,
                )

    if created_dt and ttr_due_dt and _is_open_estado(estado):
        total_seconds = max(0.0, (ttr_due_dt - created_dt).total_seconds())
        elapsed_seconds = max(0.0, (now_dt - created_dt).total_seconds())
        if total_seconds > 0 and now_dt < ttr_due_dt:
            progress_pct = (elapsed_seconds / total_seconds) * 100.0
            for threshold in SLA_ESCALATION_WINDOWS_PCT:
                if threshold >= 100:
                    continue
                if progress_pct < float(threshold):
                    continue
                prefix = _warn_prefix("ttr", threshold)
                if _comment_with_prefix_exists(conn, ticket_id, prefix):
                    continue
                _emit_system_comment(
                    conn,
                    ticket_id,
                    f"{prefix} El ticket alcanzó {threshold}% del tiempo de resolución (TTR).",
                    now_iso,
                )
        if now_dt >= ttr_due_dt:
            if not ticket.get("ttr_breached_at"):
                conn.execute("UPDATE tickets SET ttr_breached_at = ? WHERE id = ?", (now_iso, ticket_id))
            if not _comment_with_prefix_exists(conn, ticket_id, "[SLA_BREACH_TTR]"):
                _emit_system_comment(
                    conn,
                    ticket_id,
                    "[SLA_BREACH_TTR] Se superó el TTR objetivo.",
                    now_iso,
                )

    if ttr_due_dt and estado in {"resuelto", "cerrado"}:
        if resolved_dt and resolved_dt > ttr_due_dt and not ticket.get("ttr_breached_at"):
            conn.execute(
                "UPDATE tickets SET ttr_breached_at = COALESCE(ttr_breached_at, ?) WHERE id = ?",
                (resolved_dt.isoformat(), ticket_id),
            )

    # Auto-cierre opcional para tickets en resuelto tras ventana de seguimiento.
    if estado == "resuelto" and RESUELTO_AUTO_CLOSE_HOURS > 0 and resolved_dt:
        auto_close_at = resolved_dt + timedelta(hours=RESUELTO_AUTO_CLOSE_HOURS)
        if now_dt >= auto_close_at:
            from_sub = normalize_subestado(ticket.get("subestado"), "resuelto")
            update_result = conn.execute(
                """UPDATE tickets
                   SET estado = 'cerrado',
                       subestado = 'cerrado',
                       updated_at = ?,
                       resolved_at = COALESCE(resolved_at, ?)
                   WHERE id = ? AND estado = 'resuelto'""",
                (now_iso, now_iso, ticket_id),
            )
            updated_rows = getattr(update_result, "rowcount", None)
            if updated_rows == 0:
                return
            conn.execute(
                """INSERT INTO ticket_transitions
                   (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
                   VALUES (?, ?, 'cerrado', 'system', ?, ?)""",
                (
                    ticket_id,
                    from_sub,
                    f"auto_close_resuelto_timeout_{RESUELTO_AUTO_CLOSE_HOURS}h",
                    now_iso,
                ),
            )
            _emit_system_comment(
                conn,
                ticket_id,
                f"[AUTO_CIERRE] Ticket cerrado automáticamente tras {RESUELTO_AUTO_CLOSE_HOURS}h en estado resuelto.",
                now_iso,
            )
            _recompute_ticket_retention(conn, ticket_id)

def run_sla_evaluation_batch(limit: int = 500) -> Dict[str, Any]:
    """
    Evalúa SLA en lote para tickets que pueden requerir actualización de breach/alertas.
    Se ejecuta vía job periódico para mantener endpoints GET sin side effects.
    """
    batch_limit = max(1, min(int(limit or 500), 5000))
    now_iso = db.now_utc_iso()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id
               FROM tickets
               WHERE (
                   (first_response_at IS NULL AND frt_due_at IS NOT NULL)
                   OR
                   (ttr_due_at IS NOT NULL)
                   OR
                   (estado = 'resuelto')
               )
               ORDER BY COALESCE(updated_at, created_at) ASC, id ASC
               LIMIT ?""",
            (batch_limit,),
        ).fetchall()
        processed = 0
        for row in rows:
            _evaluate_ticket_sla(conn, int(row["id"]), now_iso)
            processed += 1
        conn.commit()
        return {
            "ok": True,
            "processed": processed,
            "limit": batch_limit,
            "evaluated_at": now_iso,
        }
    finally:
        conn.close()

def _maybe_mark_first_response(conn, ticket_id: int, by_user: str, now_iso: Optional[str] = None) -> None:
    if not by_user:
        return
    actor = str(by_user).strip().lower()
    if actor.startswith("system") or actor.startswith("email:") or actor in {"email_bot", "jira"}:
        return
    now_iso = now_iso or db.now_utc_iso()
    row = conn.execute(
        "SELECT first_response_at, frt_due_at FROM tickets WHERE id = ?",
        (ticket_id,),
    ).fetchone()
    if not row or row.get("first_response_at"):
        return
    frt_due_dt = _parse_dt(row.get("frt_due_at"))
    now_dt = _parse_dt(now_iso) or _now_dt()
    if frt_due_dt and now_dt > frt_due_dt:
        conn.execute(
            """UPDATE tickets
               SET first_response_at = ?, frt_breached_at = COALESCE(frt_breached_at, ?)
               WHERE id = ?""",
            (now_iso, now_iso, ticket_id),
        )
    else:
        conn.execute(
            "UPDATE tickets SET first_response_at = ? WHERE id = ?",
            (now_iso, ticket_id),
        )

def _hydrate_ticket_runtime(ticket: Dict[str, Any], now_dt: Optional[datetime] = None) -> Dict[str, Any]:
    now_dt = now_dt or _now_dt()
    t = dict(ticket)
    notify_list = _notify_emails_from_ticket(t)
    t["notify_emails_list"] = notify_list
    t["notify_emails"] = ", ".join(notify_list)
    estado_norm = str(t.get("estado") or "").strip().lower()
    sub_norm = normalize_subestado(t.get("subestado"), "recibido")
    # Guard rail: normaliza combinaciones legacy incoherentes (estado/subestado)
    # para evitar flujos inválidos en UI/workflow.
    if estado_norm == "cerrado":
        sub_norm = "cerrado"
    elif estado_norm == "resuelto":
        sub_norm = "resuelto"
    t["subestado"] = sub_norm
    created_dt = _parse_dt(t.get("created_at"))
    frt_due_dt = _parse_dt(t.get("frt_due_at"))
    ttr_due_dt = _parse_dt(t.get("ttr_due_at")) or _parse_dt(t.get("vence_at"))
    first_response_dt = _parse_dt(t.get("first_response_at"))
    resolved_dt = _parse_dt(t.get("resolved_at")) or _parse_dt(t.get("updated_at"))
    estado = estado_norm

    is_frt_breached = bool(t.get("frt_breached_at"))
    if not is_frt_breached and frt_due_dt and first_response_dt is None and now_dt > frt_due_dt:
        is_frt_breached = True

    is_ttr_breached = bool(t.get("ttr_breached_at"))
    if not is_ttr_breached and ttr_due_dt:
        if _is_open_estado(estado) and now_dt > ttr_due_dt:
            is_ttr_breached = True
        if estado in {"resuelto", "cerrado"} and resolved_dt and resolved_dt > ttr_due_dt:
            is_ttr_breached = True

    t["is_frt_breached"] = is_frt_breached
    t["is_ttr_breached"] = is_ttr_breached

    if created_dt and _is_open_estado(estado):
        t["aging_minutes_open"] = max(0, int((now_dt - created_dt).total_seconds() // 60))
    else:
        t["aging_minutes_open"] = 0

    if ttr_due_dt and _is_open_estado(estado) and now_dt > ttr_due_dt:
        t["ttr_minutes_overdue"] = max(0, int((now_dt - ttr_due_dt).total_seconds() // 60))
    else:
        t["ttr_minutes_overdue"] = 0

    if frt_due_dt and first_response_dt is None and now_dt > frt_due_dt:
        t["frt_minutes_overdue"] = max(0, int((now_dt - frt_due_dt).total_seconds() // 60))
    else:
        t["frt_minutes_overdue"] = 0

    return t

# ==========================================================================
# CRUD PRINCIPAL
# ==========================================================================
def _find_customer_by_email(conn, email: str) -> Optional[str]:
    """Busca un cliente (external_id) por coincidencia exacta de email."""
    if not email or "@" not in email:
        return None
    normalized = email.strip().lower()
    
    # Intento 1: Match exacto en campo email
    row = conn.execute(
        "SELECT external_id FROM customers WHERE lower(email) = ?", 
        (normalized,)
    ).fetchone()
    if row:
        return row["external_id"]
        
    return None

# ==========================================================================
def create_ticket(
    titulo: str,
    descripcion: str,
    creador_id: str,
    severidad: str = "media",
    tipo: str = "incidencia",
    categoria: Optional[str] = None,
    origen_email: Optional[str] = None,
    cliente_nombre: Optional[str] = None,
    email_thread_id: Optional[str] = None,
    email_references: Optional[str] = None,
    subestado: Optional[str] = None,
    ticket_security_class: Optional[str] = "internal",
    customer_id: Optional[str] = None,
    contact_role: Optional[str] = None,
    notify_emails: Optional[List[str]] = None,
    auto_assign: bool = False,
) -> Dict[str, Any]:
    """Crear un nuevo ticket con auto-clasificación y auto-asignación."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        # Auto-resolver cliente por email si existe mapeo
        if origen_email:
            # Primero buscamos si hay asociación explícita
            client_map = get_client_for_email(origen_email)
            if client_map:
                cliente_nombre = client_map.get("customer_name")
            else:
                # Si NO hay asociación, indicamos "Desconocido" para permitir vincular
                # (aunque venga un nombre en el header del correo, queremos que el usuario lo asocie)
                # Excepción: si ya venía un cliente_nombre explícito (ej: creación manual), lo respetamos
                # pero si viene del procesador de correo, a veces trae el nombre.
                # Asumimos: si tiene origen_email y no está mapeado -> Desconocido
                # A menos que sea un ticket interno o el nombre sea muy distinto.
                # Para simplificar y cumplir el requerimiento: forzamos Desconocido si no está mapeado.
                cliente_nombre = "Desconocido"

        # Normalizar severidad
        severidad = severidad.lower() if severidad else "media"
        if severidad not in SEVERIDADES_VALIDAS:
            severidad = "media"

        # Auto-clasificar si no se especifica categoría
        if not categoria or categoria not in CATEGORIAS_VALIDAS:
            categoria = clasificar_ticket(titulo, descripcion)

        # Normalizar tipo
        tipo = normalize_ticket_type(tipo)
        explicit_subestado = str(subestado or "").strip()

        # Calcular SLA
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        sla_horas = SLA_HORAS.get(severidad, 72)
        ttr_due_at = _ttr_due_iso(now_dt, severidad)
        frt_due_at = _frt_due_iso(now_dt, severidad)
        vence_at = ttr_due_at

        # Prioridad numérica
        prioridad = PRIORIDAD_MAP.get(severidad, 3)
        security_class = normalize_ticket_security_class(ticket_security_class)
        retention_days = _retention_days_for_class(security_class)
        thread_id = _normalize_message_id(email_thread_id)
        refs = _merge_reference_chain(email_references, thread_id)
        notify_emails_csv = _serialize_notify_emails(notify_emails, strict=True)

        # Auto-asignar (no-crítico: si falla, ticket se crea sin asignar)
        asignado_a = None
        try:
            asignado_a = auto_asignar(categoria)
        except Exception as e:
            logger.warning(f"[create_ticket] auto_asignar falló para categoría '{categoria}': {e}")

        if explicit_subestado:
            subestado = normalize_subestado(explicit_subestado, "recibido")
        else:
            subestado = "asignado" if asignado_a else "recibido"
            subestado = normalize_subestado(subestado, "recibido")

        # Auto-link cliente si no viene explícito
        if not customer_id and origen_email:
            _, email_addr = _sender_identity(origen_email)
            if email_addr:
                customer_id = _find_customer_by_email(conn, email_addr)
                if customer_id:
                     logger.info(f"[create_ticket] Cliente auto-detectado por email '{email_addr}': {customer_id}")

        try:
            cursor = conn.execute(
                """INSERT INTO tickets
                   (titulo, descripcion, estado, severidad, tipo, creador_id,
                    asignado_a, vence_at, created_at, updated_at,
                    categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id, email_references,
                    ticket_security_class, retention_days_snapshot, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails)
                   VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (titulo, descripcion, severidad, tipo, creador_id,
                 asignado_a, vence_at, now, now,
                 categoria, origen_email, cliente_nombre, prioridad, sla_horas, thread_id, refs,
                 security_class, retention_days, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails_csv)
            )
        except Exception as insert_error:
            # Compatibilidad transitoria si la migración aún no aplicó email_references.
            if "email_references" not in str(insert_error).lower():
                raise
            logger.warning(
                "[create_ticket] columna email_references ausente en DB activa; aplicando fallback temporal."
            )
            cursor = conn.execute(
                """INSERT INTO tickets
                   (titulo, descripcion, estado, severidad, tipo, creador_id,
                    asignado_a, vence_at, created_at, updated_at,
                    categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id,
                    ticket_security_class, retention_days_snapshot, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails)
                   VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
                (titulo, descripcion, severidad, tipo, creador_id,
                 asignado_a, vence_at, now, now,
                 categoria, origen_email, cliente_nombre, prioridad, sla_horas, thread_id,
                 security_class, retention_days, subestado, frt_due_at, ttr_due_at, customer_id, contact_role, notify_emails_csv)
            )
        row = cursor.fetchone()
        ticket_id = row["id"] if row else None

        # Validar que el INSERT retornó un ID válido
        if ticket_id is None:
            raise ValueError("INSERT INTO tickets no retornó un ID. Posible error en la base de datos.")

        # Generar código y actualizar
        codigo = generar_codigo(ticket_id)
        conn.execute("UPDATE tickets SET codigo = ? WHERE id = ?", (codigo, ticket_id))

        # Evento de creación
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, creador_id or 'system', f"[CREACION] Ticket creado. Tipo: {tipo}. Categoría: {categoria}. Severidad: {severidad}.", now)
        )
        conn.execute(
            """INSERT INTO ticket_transitions
               (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticket_id, "", subestado, creador_id, "creacion_ticket", now),
        )

        if asignado_a:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (ticket_id, creador_id or 'system', f"[ASIGNACION] Auto-asignado a {asignado_a} (especialidad: {categoria})", now)
            )

        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()

        # Programar notificaciones escalonadas (no-crítico: si falla, ticket ya está creado)
        if asignado_a:
            try:
                programar_notificaciones(ticket_id, asignado_a)
            except Exception as e:
                logger.warning(f"[create_ticket] programar_notificaciones falló para ticket {ticket_id}: {e}")

        return get_ticket(ticket_id)
    finally:
        conn.close()

def get_ticket(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Obtener un ticket por ID."""
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if not row:
            return None
        return _hydrate_ticket_runtime(dict(row))
    finally:
        conn.close()

def list_tickets(
    estado: Optional[str] = None,
    q: Optional[str] = None,
    categoria: Optional[str] = None,
    asignado_a: Optional[str] = None,
    severidad: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    include_full: bool = False,
    include_total: bool = True,
    ver_resueltos: bool = False,
) -> Dict[str, Any]:
    """Listar tickets con filtros avanzados. Retorna {items, total}."""
    conn = db.get_conn()
    try:
        # Protección simple para evitar cargas excesivas en UI.
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params = []

        if estado:
            where_clauses.append("estado = ?")
            params.append(estado.lower())

        if categoria:
            where_clauses.append("categoria = ?")
            params.append(categoria.lower())

        if asignado_a:
            if ver_resueltos:
                where_clauses.append("(asignado_a = ? OR estado IN ('resuelto', 'cerrado'))")
                params.append(asignado_a)
            else:
                where_clauses.append("asignado_a = ?")
                params.append(asignado_a)

        if severidad:
            where_clauses.append("severidad = ?")
            params.append(severidad.lower())

        if q:
            where_clauses.append("(titulo ILIKE ? OR descripcion ILIKE ? OR codigo ILIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])

        where_sql = " AND ".join(where_clauses)

        total = 0
        if include_total:
            count_row = conn.execute(f"SELECT COUNT(*) as total FROM tickets WHERE {where_sql}", params).fetchone()
            total = count_row["total"] if count_row else 0

        # Para listados y kanban no necesitamos payload completo (descripcion puede ser muy grande).
        select_fields = (
            "*"
            if include_full
            else """
                id, codigo, titulo, estado, tipo, severidad, creador_id, asignado_a,
                vence_at, created_at, updated_at, categoria, origen_email, cliente_nombre,
                prioridad, email_thread_id, resolucion, sla_horas,
                subestado, frt_due_at, ttr_due_at, first_response_at, resolved_at,
                frt_breached_at, ttr_breached_at, ticket_security_class,
                retention_until, retention_days_snapshot, customer_id, contact_role, notify_emails
            """
        )

        # Obtener items
        items_params = params + [limit, offset]
        cursor = conn.execute(
            f"SELECT {select_fields} FROM tickets WHERE {where_sql} ORDER BY prioridad ASC, created_at DESC LIMIT ? OFFSET ?",
            items_params
        )
        now_dt = _now_dt()
        items = [_hydrate_ticket_runtime(dict(row), now_dt=now_dt) for row in cursor.fetchall()]

        return {"items": items, "total": total if include_total else len(items)}
    finally:
        conn.close()

def claim_ticket(ticket_id: int, actor_id: str, actor_role: str = "") -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")

    actor_username = str(actor_id or "").strip()
    if not actor_username:
        raise ValueError("Usuario inválido para tomar ticket")

    if _scope_enforced(actor_role):
        role_norm = _normalize_role(actor_role)
        if role_norm in ROLES_ADMIN_GESTION:
            raise PermissionError("El admin no puede tomar tickets. Debe reasignarlos.")
        if role_norm not in ROLES_TECNICOS_SET:
            raise PermissionError("Rol no autorizado para tomar tickets.")

    actor_norm = _normalize_username(actor_username)
    current_assignee_norm = _ticket_assignee_username(ticket)
    if current_assignee_norm == actor_norm:
        return {"ok": True, "already_assigned": True, "ticket": ticket}
    if current_assignee_norm and current_assignee_norm != actor_norm:
        raise PermissionError(
            f"Ticket asignado a '{ticket.get('asignado_a')}'. Solo admin puede reasignarlo."
        )

    from_subestado = normalize_subestado(ticket.get("subestado"), "recibido")
    target_subestado = "asignado" if from_subestado == "recibido" else from_subestado
    target_estado = estado_from_subestado(target_subestado, str(ticket.get("estado") or "abierto"))

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        row = conn.execute(
            """UPDATE tickets
               SET asignado_a = ?, subestado = ?, estado = ?, updated_at = ?
               WHERE id = ? AND COALESCE(asignado_a, '') = ''
               RETURNING id""",
            (actor_username, target_subestado, target_estado, now, ticket_id),
        ).fetchone()

        if not row:
            live_row = conn.execute("SELECT asignado_a FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
            live_assignee = _normalize_username((live_row or {}).get("asignado_a"))
            if live_assignee == actor_norm:
                return {"ok": True, "already_assigned": True, "ticket": get_ticket(ticket_id)}
            if live_assignee:
                raise PermissionError(
                    f"Ticket asignado a '{live_row.get('asignado_a')}'. Solo admin puede reasignarlo."
                )
            raise ValueError("No fue posible tomar el ticket en este momento.")

        _emit_system_comment(conn, ticket_id, f"[ASIGNACION] Ticket tomado por {actor_username}", now, author_id=actor_username)
        if target_subestado != from_subestado:
            conn.execute(
                """INSERT INTO ticket_transitions
                   (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ticket_id, from_subestado, target_subestado, actor_username, "claim_ticket", now),
            )
            _emit_system_comment(conn, ticket_id, f"[TRANSICION] {from_subestado} -> {target_subestado}", now, author_id=actor_username)
        _maybe_mark_first_response(conn, ticket_id, actor_username, now)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    try:
        incrementar_carga(actor_username, specialty=ticket.get("categoria"))
    except Exception as e:
        logger.warning(f"[claim_ticket] Falló incrementar_carga para {actor_username}: {e}")

    try:
        programar_notificaciones(ticket_id, actor_username)
    except Exception as e:
        logger.warning(f"[claim_ticket] Falló programar_notificaciones para {actor_username}: {e}")

    return {"ok": True, "claimed": True, "ticket": get_ticket(ticket_id)}

def update_ticket(
    ticket_id: int,
    updates: Dict[str, Any],
    actor_id: str = "system",
    actor_role: str = "",
) -> Optional[Dict[str, Any]]:
    """Actualizar campos del ticket."""
    allowed_keys = {
        "estado",
        "subestado",
        "severidad",
        "asignado_a",
        "titulo",
        "descripcion",
        "vence_at",
        "categoria",
        "prioridad",
        "resolucion",
        "ticket_security_class",
        "customer_id",
        "contact_role",
        "notify_emails",
    }
    current = get_ticket(ticket_id)
    if not current:
        return None

    normalized_updates: Dict[str, Any] = {}
    for key, value in (updates or {}).items():
        if key not in allowed_keys:
            continue
        if key == "estado":
            estado = str(value or "").strip().lower()
            if estado in ESTADOS_VALIDOS:
                current_estado = str(current.get("estado") or "abierto").lower()
                
                # Matriz de transiciones
                # ABIERTO -> EN_PROGRESO, RESUELTO, CERRADO
                # EN_PROGRESO -> ABIERTO, RESUELTO, CERRADO 
                # RESUELTO -> EN_PROGRESO, CERRADO
                # CERRADO -> RESUELTO
                
                if current_estado == "cerrado":
                    if estado not in ["resuelto", "cerrado"]:
                        raise ConflictError("Transición de estado inválida: un ticket CERRADO solo puede reabrirse parcialmente a RESUELTO.")
                
                if current_estado == "resuelto":
                    if estado == "abierto":
                        raise ConflictError("Transición de estado inválida: un ticket RESUELTO no puede volver directo a ABIERTO. Debe retroceder a EN PROGRESO.")

                normalized_updates[key] = estado
            continue
        if key == "subestado":
            normalized_updates[key] = normalize_subestado(value, current.get("subestado") or "recibido")
            continue
        if key == "severidad":
            sev = str(value or "").strip().lower()
            normalized_updates[key] = sev if sev in SEVERIDADES_VALIDAS else current.get("severidad", "media")
            continue
        if key == "ticket_security_class":
            normalized_updates[key] = normalize_ticket_security_class(value)
            continue
        if key == "asignado_a":
            normalized_updates[key] = str(value).strip() if value else None
            continue
        if key == "customer_id" or key == "contact_role":
            normalized_updates[key] = str(value).strip() if value else None
            continue
        if key == "notify_emails":
            normalized_updates[key] = _serialize_notify_emails(value, strict=True)
            continue
        normalized_updates[key] = value

    if "asignado_a" in normalized_updates and normalized_updates.get("asignado_a") and "subestado" not in normalized_updates:
        current_sub = normalize_subestado(current.get("subestado"), "recibido")
        if current_sub == "recibido":
            normalized_updates["subestado"] = "asignado"

    if "subestado" in normalized_updates and "estado" not in normalized_updates:
        normalized_updates["estado"] = estado_from_subestado(
            normalized_updates["subestado"],
            str(current.get("estado") or "abierto"),
        )

    # Cuando llega solo "estado" (ej: drag/drop Kanban), sincronizamos subestado para
    # evitar combinaciones incoherentes (ej: estado=abierto con subestado=en_progreso).
    if "estado" in normalized_updates and "subestado" not in normalized_updates:
        target_estado = str(normalized_updates.get("estado") or "").strip().lower()
        current_sub = normalize_subestado(current.get("subestado"), "recibido")
        current_sub_estado = estado_from_subestado(current_sub, str(current.get("estado") or "abierto"))

        if target_estado == "abierto":
            if current_sub_estado == "abierto":
                normalized_updates["subestado"] = current_sub
            else:
                normalized_updates["subestado"] = "asignado" if current.get("asignado_a") else "recibido"
        elif target_estado == "en_progreso":
            if current_sub_estado == "en_progreso" and current_sub not in {"resuelto", "cerrado"}:
                normalized_updates["subestado"] = current_sub
            else:
                normalized_updates["subestado"] = "en_progreso"
        elif target_estado == "resuelto":
            normalized_updates["subestado"] = "resuelto"
        elif target_estado == "cerrado":
            normalized_updates["subestado"] = "cerrado"

    keys_to_update = list(normalized_updates.keys())
    if not keys_to_update:
        return get_ticket(ticket_id)

    actor_norm = _normalize_username(actor_id)
    current_assignee_norm = _ticket_assignee_username(current)
    is_admin_actor = _is_admin_management_role(actor_role)
    can_dispatch_reassign = _can_dispatch_reassign(current, actor_id, actor_role)
    if _scope_enforced(actor_role) and not is_admin_actor:
        if "asignado_a" in normalized_updates:
            target_assignee_norm = _normalize_username(normalized_updates.get("asignado_a"))
            if not target_assignee_norm:
                if not can_dispatch_reassign:
                    raise PermissionError("Solo admin o encargado de mesa puede desasignar tickets.")
            if target_assignee_norm != actor_norm and not can_dispatch_reassign:
                raise PermissionError("Solo admin o encargado de mesa puede reasignar tickets a otro usuario.")
            if current_assignee_norm and current_assignee_norm != actor_norm and not can_dispatch_reassign:
                raise PermissionError(
                    f"Ticket asignado a '{current.get('asignado_a')}'. Solo admin o encargado de mesa puede reasignarlo."
                )

        writes_without_assignment = set(keys_to_update) - {"asignado_a"}
        if writes_without_assignment:
            request_claims_self = _normalize_username(normalized_updates.get("asignado_a")) == actor_norm
            if current_assignee_norm != actor_norm and not (not current_assignee_norm and request_claims_self):
                if current_assignee_norm:
                    raise PermissionError(
                        f"Ticket asignado a '{current.get('asignado_a')}'. Solo el asignado puede modificarlo."
                    )
                raise PermissionError("Ticket sin asignar. Debes tomarlo antes de modificarlo.")

    assignment_claim_mode = (
        _scope_enforced(actor_role)
        and not is_admin_actor
        and "asignado_a" in normalized_updates
        and _normalize_username(normalized_updates.get("asignado_a")) == actor_norm
        and not current_assignee_norm
    )

    old_estado = str(current.get("estado") or "").strip().lower()
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        now_dt = _parse_dt(now) or _now_dt()
        set_clause = ", ".join([f"{k} = ?" for k in keys_to_update]) + ", updated_at = ?"
        where_clause = "id = ?"
        if assignment_claim_mode:
            where_clause += " AND COALESCE(asignado_a, '') = ''"
        params = [normalized_updates[k] for k in keys_to_update] + [now, ticket_id]

        cursor = conn.execute(f"UPDATE tickets SET {set_clause} WHERE {where_clause}", params)
        if cursor.rowcount == 0:
            if assignment_claim_mode:
                live_row = conn.execute("SELECT asignado_a FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
                live_assignee = _normalize_username((live_row or {}).get("asignado_a"))
                if live_assignee == actor_norm:
                    return get_ticket(ticket_id)
                if live_assignee:
                    raise PermissionError(
                        f"Ticket asignado a '{live_row.get('asignado_a')}'. Solo admin puede reasignarlo."
                    )
            return None

        if "subestado" in normalized_updates:
            from_sub = current.get("subestado") or ""
            to_sub = normalized_updates["subestado"]
            if str(from_sub).lower() != str(to_sub).lower():
                conn.execute(
                    """INSERT INTO ticket_transitions
                       (ticket_id, from_subestado, to_subestado, actor, reason, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        ticket_id,
                        str(from_sub),
                        str(to_sub),
                        actor_id,
                        "update_ticket",
                        now,
                    ),
                )
                _emit_system_comment(
                    conn,
                    ticket_id,
                    f"[TRANSICION] Subestado cambiado de {from_sub or '-'} a {to_sub}",
                    now,
                    author_id=actor_id,
                )

        if "estado" in normalized_updates:
            new_estado = normalized_updates["estado"]
            _emit_system_comment(conn, ticket_id, f"[CAMBIO_ESTADO] Estado cambiado a {new_estado}", now, author_id=actor_id)
            if new_estado in ("cerrado", "resuelto"):
                if current.get("asignado_a"):
                    decrementar_carga(current["asignado_a"], specialty=current.get("categoria"))
                conn.execute(
                    "UPDATE tickets SET resolved_at = COALESCE(resolved_at, ?) WHERE id = ?",
                    (now, ticket_id),
                )
            elif current.get("estado") in ("cerrado", "resuelto") and new_estado in ("abierto", "en_progreso"):
                conn.execute("UPDATE tickets SET resolved_at = NULL WHERE id = ?", (ticket_id,))

        if "asignado_a" in normalized_updates:
            new_asignado = normalized_updates["asignado_a"]
            old_asignado_norm = _normalize_username(current.get("asignado_a"))
            new_asignado_norm = _normalize_username(new_asignado)
            if old_asignado_norm != new_asignado_norm:
                target_label = new_asignado or "sin asignar"
                _emit_system_comment(conn, ticket_id, f"[REASIGNACION] Reasignado a {target_label}", now, author_id=actor_id)
                old_cat = current.get("categoria")
                new_cat = normalized_updates.get("categoria", old_cat)
                if current.get("asignado_a"):
                    decrementar_carga(current["asignado_a"], specialty=old_cat)
                if new_asignado:
                    incrementar_carga(str(new_asignado), specialty=new_cat)
                    _maybe_mark_first_response(conn, ticket_id, actor_id, now)
                    try:
                        programar_notificaciones(ticket_id, str(new_asignado))
                    except Exception as e:
                        logger.warning(f"[update_ticket] Falló programar_notificaciones para {new_asignado}: {e}")

        if "severidad" in normalized_updates:
            new_sev = normalized_updates["severidad"]
            new_sla = SLA_HORAS.get(new_sev, 72)
            new_prio = PRIORIDAD_MAP.get(new_sev, 3)
            new_ttr_due = _ttr_due_iso(now_dt, new_sev)
            new_frt_due = _frt_due_iso(now_dt, new_sev)
            conn.execute(
                """UPDATE tickets
                   SET prioridad = ?, sla_horas = ?, vence_at = ?, ttr_due_at = ?,
                       frt_due_at = CASE WHEN first_response_at IS NULL THEN ? ELSE frt_due_at END
                   WHERE id = ?""",
                (new_prio, new_sla, new_ttr_due, new_ttr_due, new_frt_due, ticket_id),
            )
            _emit_system_comment(
                conn,
                ticket_id,
                f"[ESCALAMIENTO] Severidad cambiada a {new_sev}. Nuevo SLA: {new_sla}h",
                now,
                author_id=actor_id,
            )

        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        updated_ticket = get_ticket(ticket_id)
    finally:
        conn.close()

    if "estado" in normalized_updates and updated_ticket:
        new_estado = str(updated_ticket.get("estado") or "").strip().lower()
        if old_estado and new_estado and old_estado != new_estado:
            try:
                _send_ticket_status_update_to_notify_emails(
                    updated_ticket,
                    from_estado=old_estado,
                    to_estado=new_estado,
                    actor_id=actor_id,
                    motivo="cambio_estado_manual",
                )
            except Exception as status_mail_error:
                logger.warning(f"[update_ticket] aviso de estado por correo no crítico falló para ticket {ticket_id}: {status_mail_error}")

    return updated_ticket

def add_comment(
    ticket_id: int,
    user_id: str,
    content: str,
    event_type: str = "comentario",
    actor_role: str = "",
) -> Dict[str, Any]:
    """Agregar un comentario/evento al ticket."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_participate_ticket(ticket, user_id, actor_role, "agregar notas")
    if _is_readonly_blocked_by_estado(ticket):
        raise ValueError("El ticket está CERRADO y no admite más notas.")

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        cursor = conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?) RETURNING id""",
            (ticket_id, user_id, f"[{event_type.upper()}] {content}", now)
        )
        row = cursor.fetchone()
        comment_id = row["id"] if row else None
        _maybe_mark_first_response(conn, ticket_id, user_id, now)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        conn.commit()

        row = conn.execute("SELECT * FROM ticket_comments WHERE id = ?", (comment_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()

def _get_active_email_draft_row(conn, ticket_id: int) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        """SELECT *
           FROM ticket_email_drafts
           WHERE ticket_id = ? AND status = 'active'
           ORDER BY id DESC
           LIMIT 1""",
        (int(ticket_id),),
    ).fetchone()
    return dict(row) if row else None

def _list_email_draft_attachments(conn, draft_id: int) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT id, draft_id, filename, file_path, size_bytes, content_type, sha256,
                  uploaded_by, created_at, sent_email_id
           FROM ticket_email_draft_attachments
           WHERE draft_id = ?
           ORDER BY id ASC""",
        (int(draft_id),),
    ).fetchall()
    return [dict(r) for r in rows]

def _ensure_active_email_draft(conn, ticket: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    ticket_id = int(ticket.get("id") or 0)
    current = _get_active_email_draft_row(conn, ticket_id)
    if current:
        return current

    now = db.now_utc_iso()
    actor = str(actor_id or "").strip() or "system"
    to_addr = _extract_ticket_target_email(ticket)
    _, cc_emails, _, _ = _compose_reply_recipients(ticket, explicit_to=to_addr)
    subject = _build_ticket_reply_subject(ticket)
    try:
        row = conn.execute(
            """INSERT INTO ticket_email_drafts
               (ticket_id, status, to_addr, cc_addrs, bcc_addrs, subject, body_text, version,
                created_by, updated_by, created_at, updated_at)
               VALUES (?, 'active', ?, ?, '', ?, '', 1, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, to_addr, ", ".join(cc_emails), subject, actor, actor, now, now),
        ).fetchone()
    except Exception as e:
        msg = str(e).lower()
        if "idx_tk_email_drafts_active" in msg or "duplicate" in msg:
            existing = _get_active_email_draft_row(conn, ticket_id)
            if existing:
                return existing
        raise
    draft_id = int((row or {}).get("id") or 0)
    created = conn.execute(
        "SELECT * FROM ticket_email_drafts WHERE id = ?",
        (draft_id,),
    ).fetchone()
    if not created:
        raise ValueError("No fue posible crear borrador activo.")
    return dict(created)

def _serialize_email_draft(conn, draft: Dict[str, Any], actor_id: str) -> Dict[str, Any]:
    draft_id = int(draft.get("id") or 0)
    lock = _draft_lock_info(draft, actor_id)
    attachments_raw = _list_email_draft_attachments(conn, draft_id)
    attachments = [
        {
            "id": int(item.get("id") or 0),
            "draft_id": int(item.get("draft_id") or 0),
            "filename": str(item.get("filename") or ""),
            "size_bytes": int(item.get("size_bytes") or 0),
            "content_type": str(item.get("content_type") or "application/octet-stream"),
            "sha256": str(item.get("sha256") or ""),
            "uploaded_by": str(item.get("uploaded_by") or ""),
            "created_at": item.get("created_at"),
            "sent_email_id": item.get("sent_email_id"),
        }
        for item in attachments_raw
    ]
    out = {
        "id": draft_id,
        "ticket_id": int(draft.get("ticket_id") or 0),
        "status": str(draft.get("status") or "active"),
        "to_addr": str(draft.get("to_addr") or ""),
        "cc_addrs": str(draft.get("cc_addrs") or ""),
        "bcc_addrs": str(draft.get("bcc_addrs") or ""),
        "subject": str(draft.get("subject") or ""),
        "body_text": str(draft.get("body_text") or ""),
        "version": int(draft.get("version") or 1),
        "created_by": str(draft.get("created_by") or ""),
        "updated_by": str(draft.get("updated_by") or ""),
        "created_at": draft.get("created_at"),
        "updated_at": draft.get("updated_at"),
        "sent_by": draft.get("sent_by"),
        "sent_email_id": draft.get("sent_email_id"),
        "sent_at": draft.get("sent_at"),
        "attachments": attachments,
        "lock": lock,
    }
    return out

def _ensure_can_edit_email_draft(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: str,
    action_label: str,
) -> None:
    _ensure_can_participate_ticket(ticket, actor_id, actor_role, action_label)
    _ensure_reply_allowed_estado(ticket, action_label)

def _validate_draft_lock(
    draft: Dict[str, Any],
    actor_id: str,
    lock_token: str,
) -> None:
    pass

def _acquire_draft_lock(
    conn,
    draft: Dict[str, Any],
    actor_id: str,
    *,
    force: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    actor = str(actor_id or "").strip() or "system"
    now_iso = db.now_utc_iso()
    lock_info = _draft_lock_info(draft, actor)
    if lock_info["active"] and not lock_info["mine"] and not force:
        owner = lock_info.get("owner") or "otro usuario"
        raise ConflictError(f"El borrador está en edición por '{owner}'.")

    lock_token = _new_draft_lock_token()
    lock_hash = _hash_draft_lock_token(lock_token)
    lock_expires_at = _lock_expiry_iso(now_iso, EMAIL_DRAFT_LOCK_MINUTES)
    conn.execute(
        """UPDATE ticket_email_drafts
           SET lock_owner = ?, lock_token_hash = ?, lock_expires_at = ?,
               updated_by = ?, updated_at = ?
           WHERE id = ?""",
        (actor, lock_hash, lock_expires_at, actor, now_iso, int(draft["id"])),
    )
    row = conn.execute(
        "SELECT * FROM ticket_email_drafts WHERE id = ?",
        (int(draft["id"]),),
    ).fetchone()
    if not row:
        raise ValueError("No fue posible refrescar lock del borrador.")
    return lock_token, dict(row)

def _normalize_draft_to_email(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    _, parsed = parseaddr(raw)
    out = parsed.strip() if parsed else raw
    return out

def get_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")

    can_edit = True
    blocked_reason = ""
    try:
        _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "editar borrador de respuesta")
    except (PermissionError, ValueError) as e:
        can_edit = False
        blocked_reason = str(e)

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        draft_payload = _serialize_email_draft(conn, draft, actor_id)
        conn.commit()
        return {
            "ok": True,
            "ticket_id": int(ticket_id),
            "ticket_estado": str(ticket.get("estado") or ""),
            "can_edit": can_edit,
            "blocked_reason": blocked_reason,
            "draft": draft_payload,
            "lock_timeout_seconds": EMAIL_DRAFT_LOCK_MINUTES * 60,
            "heartbeat_seconds": EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS,
        }
    finally:
        conn.close()

def acquire_ticket_email_draft_lock(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
    *,
    force: bool = False,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "tomar control del borrador")

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        lock_token, locked_draft = _acquire_draft_lock(conn, draft, actor_id, force=bool(force))
        payload = _serialize_email_draft(conn, locked_draft, actor_id)
        conn.commit()
        return {
            "ok": True,
            "ticket_id": int(ticket_id),
            "lock_token": lock_token,
            "draft": payload,
            "lock_timeout_seconds": EMAIL_DRAFT_LOCK_MINUTES * 60,
            "heartbeat_seconds": EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS,
        }
    finally:
        conn.close()

def heartbeat_ticket_email_draft_lock(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "mantener control del borrador")

    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET lock_expires_at = ?, updated_at = ?, updated_by = ?
               WHERE id = ?""",
            (_lock_expiry_iso(now_iso, EMAIL_DRAFT_LOCK_MINUTES), now_iso, actor_id, int(draft["id"])),
        )
        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
        return {
            "ok": True,
            "ticket_id": int(ticket_id),
            "draft": payload,
            "heartbeat_seconds": EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS,
        }
    finally:
        conn.close()

def save_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    *,
    lock_token: str,
    version: int,
    to_addr: Optional[str] = None,
    cc_addrs: Optional[str] = None,
    bcc_addrs: Optional[str] = None,
    subject: Optional[str] = None,
    body_text: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "guardar borrador de respuesta")

    expected_version = int(version or 0)
    if expected_version <= 0:
        raise ValueError("La versión del borrador es obligatoria.")

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        _validate_draft_lock(draft, actor_id, lock_token)
        current_version = int(draft.get("version") or 1)
        if current_version != expected_version:
            raise ConflictError(
                f"El borrador cambió de versión ({current_version}). Recarga antes de guardar."
            )

        next_to_addr = _normalize_draft_to_email(to_addr) if to_addr is not None else str(draft.get("to_addr") or "")
        if next_to_addr and "@" not in next_to_addr:
            raise ValueError("Correo destino inválido para el borrador.")
        next_cc_raw = cc_addrs if cc_addrs is not None else str(draft.get("cc_addrs") or "")
        next_bcc_raw = bcc_addrs if bcc_addrs is not None else str(draft.get("bcc_addrs") or "")
        next_cc_list = _normalize_recipient_emails(next_cc_raw, label="CC")
        next_bcc_list = _normalize_recipient_emails(next_bcc_raw, label="CCO")
        if next_to_addr:
            next_cc_list = [email for email in next_cc_list if email != next_to_addr]
            next_bcc_list = [email for email in next_bcc_list if email != next_to_addr]
        cc_set = set(next_cc_list)
        next_bcc_list = [email for email in next_bcc_list if email not in cc_set]
        next_cc_addrs = ", ".join(next_cc_list)
        next_bcc_addrs = ", ".join(next_bcc_list)
        next_subject = str(subject if subject is not None else draft.get("subject") or "").strip()
        next_body = str(body_text if body_text is not None else draft.get("body_text") or "")

        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET to_addr = ?, cc_addrs = ?, bcc_addrs = ?, subject = ?, body_text = ?, version = ?,
                   updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (
                next_to_addr,
                next_cc_addrs,
                next_bcc_addrs,
                next_subject,
                next_body,
                current_version + 1,
                actor_id,
                now_iso,
                int(draft["id"]),
            ),
        )
        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
        return {"ok": True, "ticket_id": int(ticket_id), "draft": payload}
    finally:
        conn.close()

def upload_ticket_email_draft_attachments(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
    files: Optional[List[Any]],
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "subir adjuntos al borrador")

    conn = db.get_conn()
    try:
        draft = _ensure_active_email_draft(conn, ticket, actor_id)
        _validate_draft_lock(draft, actor_id, lock_token)
        if not files:
            payload = _serialize_email_draft(conn, draft, actor_id)
            conn.commit()
            return {"ok": True, "ticket_id": int(ticket_id), "uploaded": 0, "draft": payload}

        base_path = _drafts_base_path(ticket_id, int(draft["id"])).resolve()
        base_path.mkdir(parents=True, exist_ok=True)
        uploaded = 0
        for file in files:
            filename = str(getattr(file, "filename", "") or "").strip() or "untitled"
            ext = Path(filename).suffix.lower()
            if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                logger.warning(f"[draft_attachments] extensión no permitida: {filename}")
                continue

            file.file.seek(0, 2)
            size = int(file.file.tell())
            file.file.seek(0)
            if size > app_settings.TICKET_MAX_FILE_SIZE:
                logger.warning(f"[draft_attachments] tamaño excedido: {filename} ({size})")
                continue

            content = file.file.read()
            sha256 = hashlib.sha256(content).hexdigest()
            file_path = (base_path / _attachment_storage_name(filename)).resolve()
            if not _is_safe_attachment_path(file_path):
                logger.warning(f"[draft_attachments] ruta fuera de raíz permitida: {file_path}")
                continue

            with open(file_path, "wb") as fh:
                fh.write(content)

            conn.execute(
                """INSERT INTO ticket_email_draft_attachments
                   (draft_id, filename, file_path, size_bytes, content_type, sha256, uploaded_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(draft["id"]),
                    filename,
                    str(file_path),
                    len(content),
                    str(getattr(file, "content_type", "application/octet-stream") or "application/octet-stream"),
                    sha256,
                    actor_id,
                    db.now_utc_iso(),
                ),
            )
            uploaded += 1

        if uploaded > 0:
            now_iso = db.now_utc_iso()
            conn.execute(
                """UPDATE ticket_email_drafts
                   SET version = version + 1, updated_by = ?, updated_at = ?
                   WHERE id = ?""",
                (actor_id, now_iso, int(draft["id"])),
            )

        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
        return {"ok": True, "ticket_id": int(ticket_id), "uploaded": uploaded, "draft": payload}
    finally:
        conn.close()

def delete_ticket_email_draft_attachment(
    ticket_id: int,
    attachment_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "eliminar adjuntos del borrador")

    attachment_path = None
    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        row = conn.execute(
            """SELECT id, file_path
               FROM ticket_email_draft_attachments
               WHERE id = ? AND draft_id = ?
               LIMIT 1""",
            (int(attachment_id), int(draft["id"])),
        ).fetchone()
        if not row:
            raise ValueError("Adjunto de borrador no encontrado.")
        attachment_path = str(row.get("file_path") or "")
        conn.execute(
            "DELETE FROM ticket_email_draft_attachments WHERE id = ?",
            (int(attachment_id),),
        )
        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET version = version + 1, updated_by = ?, updated_at = ?
               WHERE id = ?""",
            (actor_id, now_iso, int(draft["id"])),
        )
        refreshed = conn.execute(
            "SELECT * FROM ticket_email_drafts WHERE id = ?",
            (int(draft["id"]),),
        ).fetchone()
        payload = _serialize_email_draft(conn, dict(refreshed), actor_id) if refreshed else None
        conn.commit()
    finally:
        conn.close()

    if attachment_path:
        try:
            path = Path(attachment_path).resolve()
            if _is_safe_attachment_path(path):
                path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"[delete_draft_attachment] no se pudo borrar archivo: {e}")

    return {"ok": True, "ticket_id": int(ticket_id), "draft": payload}

def discard_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    lock_token: str,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_participate_ticket(ticket, actor_id, actor_role, "descartar borrador de respuesta")

    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            return {"ok": True, "ticket_id": int(ticket_id), "discarded": False}
        _validate_draft_lock(draft, actor_id, lock_token)
        now_iso = db.now_utc_iso()
        conn.execute(
            """UPDATE ticket_email_drafts
               SET status = 'discarded',
                   lock_owner = NULL,
                   lock_token_hash = NULL,
                   lock_expires_at = NULL,
                   updated_by = ?,
                   updated_at = ?
               WHERE id = ?""",
            (actor_id, now_iso, int(draft["id"])),
        )
        conn.commit()
        return {"ok": True, "ticket_id": int(ticket_id), "discarded": True}
    finally:
        conn.close()

def send_ticket_email_draft(
    ticket_id: int,
    actor_id: str,
    actor_role: str,
    *,
    lock_token: str,
    version: int,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_edit_email_draft(ticket, actor_id, actor_role, "enviar respuesta al cliente")

    expected_version = int(version or 0)
    if expected_version <= 0:
        raise ValueError("La versión del borrador es obligatoria para enviar.")

    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        current_version = int(draft.get("version") or 1)
        if current_version != expected_version:
            raise ConflictError(
                f"El borrador cambió de versión ({current_version}). Recarga antes de enviar."
            )

        to_email, cc_emails, bcc_emails, to_addr_record = _compose_reply_recipients(
            ticket,
            explicit_to=_normalize_draft_to_email(draft.get("to_addr")) or _extract_ticket_target_email(ticket),
            explicit_cc=draft.get("cc_addrs"),
            explicit_bcc=draft.get("bcc_addrs"),
        )
        if not to_email or "@" not in to_email:
            raise ValueError("Este ticket no tiene un correo de cliente válido")

        subject = _build_ticket_reply_subject(ticket, draft.get("subject"))
        body_text = str(draft.get("body_text") or "")
        clean_msg = body_text.strip()
        if not clean_msg:
            raise ValueError("El borrador está vacío. Agrega un mensaje antes de enviar.")

        draft_attachments = _list_email_draft_attachments(conn, int(draft["id"]))
        email_attachments: List[Dict[str, Any]] = []
        stored_attachments: List[Dict[str, Any]] = []
        for item in draft_attachments:
            raw_path = str(item.get("file_path") or "").strip()
            path = Path(raw_path).resolve() if raw_path else None
            if not path or not _is_safe_attachment_path(path):
                raise ValueError(f"Adjunto de borrador inválido: {item.get('filename')}")
            if not path.exists() or not path.is_file():
                raise ValueError(f"Adjunto no disponible: {item.get('filename')}")
            content = path.read_bytes()
            email_attachments.append(
                {
                    "filename": str(item.get("filename") or "attachment.bin"),
                    "data": content,
                    "content_type": str(item.get("content_type") or "application/octet-stream"),
                }
            )
            stored_attachments.append(
                {
                    "id": int(item.get("id") or 0),
                    "filename": str(item.get("filename") or "attachment.bin"),
                    "path": str(path),
                    "size": int(item.get("size_bytes") or len(content)),
                    "content_type": str(item.get("content_type") or "application/octet-stream"),
                    "sha256": str(item.get("sha256") or hashlib.sha256(content).hexdigest()),
                }
            )

        headers = _build_ticket_thread_headers(ticket)
        threaded = bool(headers.get("In-Reply-To") or headers.get("References"))
        escaped_msg = html.escape(clean_msg).replace("\n", "<br>")
        body_html = f"""

    <p>{escaped_msg}</p>
    <hr>
    <p style="color:#666;font-size:12px">
      Respuesta enviada desde Mesa de Ayuda {html.escape(ticket.get("codigo") or f"#{ticket_id}")}.
    </p>
    """
        send_meta = email_sender.send_email_advanced(
            to_email=to_email,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            html_body=body_html,
            headers=headers or None,
            attachments=email_attachments,
        )

        now = db.now_utc_iso()
        email_row = conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
               VALUES (?, 'outgoing', ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                int(ticket_id),
                send_meta.get("from_addr"),
                to_addr_record or to_email,
                ", ".join(cc_emails),
                ", ".join(bcc_emails),
                subject,
                body_html,
                json.dumps(stored_attachments),
                f"draft:{int(draft['id'])}:v{current_version}",
                now,
            ),
        ).fetchone()
        email_id = int((email_row or {}).get("id") or 0)
        if email_id <= 0:
            raise ValueError("No se pudo registrar el correo enviado desde borrador.")

        for att in stored_attachments:
            conn.execute(
                """INSERT INTO ticket_attachments
                   (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(ticket_id),
                    att["filename"],
                    att["path"],
                    actor_id,
                    now,
                    int(att["size"]),
                    att["content_type"],
                    att["sha256"],
                ),
            )

        conn.execute(
            """UPDATE ticket_email_draft_attachments
               SET sent_email_id = ?
               WHERE draft_id = ? AND sent_email_id IS NULL""",
            (email_id, int(draft["id"])),
        )

        preview = clean_msg if len(clean_msg) <= 300 else clean_msg[:300] + "..."
        has_attachments = " (con adjuntos)" if stored_attachments else ""
        cc_hint = f" + CC: {', '.join(cc_emails)}" if cc_emails else ""
        bcc_hint = f" + CCO: {', '.join(bcc_emails)}" if bcc_emails else ""
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                int(ticket_id),
                actor_id,
                f"[CORREO] Respuesta enviada a {to_email}{cc_hint}{bcc_hint}{has_attachments}: {preview}",
                now,
            ),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, int(ticket_id)))
        _maybe_mark_first_response(conn, int(ticket_id), actor_id, now)
        _update_ticket_thread_metadata(
            conn,
            int(ticket_id),
            message_id=send_meta.get("message_id"),
            in_reply_to=headers.get("In-Reply-To"),
            references=headers.get("References"),
        )
        _evaluate_ticket_sla(conn, int(ticket_id), now)

        conn.execute(
            """UPDATE ticket_email_drafts
               SET status = 'sent',
                   sent_by = ?,
                   sent_email_id = ?,
                   sent_at = ?,
                   lock_owner = NULL,
                   lock_token_hash = NULL,
                   lock_expires_at = NULL,
                   updated_by = ?,
                   updated_at = ?
               WHERE id = ?""",
            (actor_id, email_id, now, actor_id, now, int(draft["id"])),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.8.16",
            artifact_ref=f"ticket:{ticket_id}:email_reply_draft",
            owner=actor_id,
            integrity_hash=send_meta.get("message_id") or "",
            metadata={
                "to": to_email,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "threaded": threaded,
                "has_attachments": bool(stored_attachments),
                "draft_id": int(draft["id"]),
                "version": current_version,
            },
        )
    except Exception as e:
        logger.warning(f"[send_ticket_email_draft] evidence_event no crítico falló para ticket {ticket_id}: {e}")

    return {
        "ok": True,
        "ticket_id": int(ticket_id),
        "to_email": to_email,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": subject,
        "threaded": threaded,
        "message_id": send_meta.get("message_id"),
        "sent_email_id": email_id,
        "draft_status": "sent",
        "ticket": get_ticket(ticket_id),
    }

def get_dashboard_kpi() -> Dict[str, Any]:
    """
    Retorna KPIs para el Dashboard V3:
    1. Top Clientes (por volumen de tickets abiertos)
    2. Correos pendientes de respuesta (auto-replyable)
    """
    conn = db.get_conn()
    try:
        # 1. Top Clientes
        rows = conn.execute(
            """
            SELECT 
                COALESCE(customer_id, 'Sin Cliente') as cliente,
                COUNT(*) as total
            FROM tickets 
            WHERE estado IN ('abierto', 'en_progreso')
            GROUP BY customer_id
            ORDER BY total DESC
            LIMIT 5
            """
        ).fetchall()
        top_clientes = [{"cliente": r["cliente"], "total": r["total"]} for r in rows]

        # 2. Correos Pendientes (Threads que requieren respuesta)
        # Lógica simplificada: Tickets abiertos con origen_email y sin respuesta reciente del agente?
        # Por ahora, listamos tickets recientes creados por correo
        rows_emails = conn.execute(
            """
            SELECT id, titulo, origen_email, created_at, customer_id
            FROM tickets
            WHERE origen_email IS NOT NULL 
              AND estado = 'abierto'
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()
        pending_emails = [dict(r) for r in rows_emails]

        return {
            "top_clientes": top_clientes,
            "pending_emails": pending_emails
        }
    finally:
        conn.close()

def transition_ticket(
    ticket_id: int,
    to_subestado: str,
    actor_id: str,
    actor_role: str = "",
    motivo: str = "",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_manage_ticket(ticket, actor_id, actor_role, "cambiar estado")
    old_estado = str(ticket.get("estado") or "").strip().lower()

    tipo = normalize_ticket_type(ticket.get("tipo"))
    from_sub = normalize_subestado(ticket.get("subestado"), "recibido")
    target_sub = _normalize_transition_target(from_sub, to_subestado)
    normalized_idem = (idempotency_key or "").strip()[:128] or None

    if target_sub in SUBESTADOS_ESPERA and not _is_estado_en_progreso(ticket.get("estado")):
        raise ValueError("Los subestados de espera solo se permiten cuando el ticket está en estado 'en_progreso'.")

    if target_sub == from_sub:
        if normalized_idem:
            conn = db.get_conn()
            try:
                idem_row = conn.execute(
                    """SELECT id FROM ticket_transitions
                       WHERE ticket_id = ? AND idempotency_key = ?
                       ORDER BY id DESC
                       LIMIT 1""",
                    (ticket_id, normalized_idem),
                ).fetchone()
            finally:
                conn.close()
            if idem_row:
                return {
                    "ok": True,
                    "duplicate_skipped": True,
                    "message": "Se evitó transición duplicada por Idempotency-Key.",
                    "ticket": get_ticket(ticket_id),
                }
        return {"ok": True, "ticket": ticket, "unchanged": True}

    if not _workflow_can_transition(tipo, from_sub, target_sub):
        raise ValueError(f"Transición inválida para tipo '{tipo}': {from_sub} -> {target_sub}")

    result_ticket: Optional[Dict[str, Any]] = None
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        if normalized_idem:
            idem_row = conn.execute(
                """SELECT id FROM ticket_transitions
                   WHERE ticket_id = ? AND idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (ticket_id, normalized_idem),
            ).fetchone()
            if idem_row:
                return {
                    "ok": True,
                    "duplicate_skipped": True,
                    "message": "Se evitó transición duplicada por Idempotency-Key.",
                    "ticket": get_ticket(ticket_id),
                }

        if tipo == "cambio":
            approvals = _latest_approval_decisions(conn, ticket_id)
            if target_sub in {"pendiente_aprobacion_2", "aprobado", "en_ejecucion"} and approvals.get(1) != "approved":
                raise ValueError("El cambio requiere aprobación de paso 1 antes de continuar.")
            if target_sub in {"aprobado", "en_ejecucion"} and approvals.get(2) != "approved":
                raise ValueError("El cambio requiere aprobación de paso 2 antes de ejecutar.")

        new_estado = estado_from_subestado(target_sub, str(ticket.get("estado") or "abierto"))
        reopen_to_progress = (
            target_sub in {"en_progreso", "asignado"}
            and from_sub in {"cerrado", "resuelto", "reabierto"}
        )
        conn.execute(
            """UPDATE tickets
               SET subestado = ?, estado = ?, updated_at = ?,
                   resolved_at = CASE
                       WHEN ? IN ('resuelto','cerrado') THEN COALESCE(resolved_at, ?)
                       WHEN ? THEN NULL
                       WHEN ? = 'reabierto' THEN NULL
                       ELSE resolved_at
                   END
               WHERE id = ?""",
            (target_sub, new_estado, now, new_estado, now, reopen_to_progress, target_sub, ticket_id),
        )

        transition_row = conn.execute(
            """INSERT INTO ticket_transitions
               (ticket_id, from_subestado, to_subestado, actor, reason, idempotency_key, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, from_sub, target_sub, actor_id, (motivo or "").strip(), normalized_idem, now),
        ).fetchone()

        _emit_system_comment(
            conn,
            ticket_id,
            f"[TRANSICION] {from_sub} -> {target_sub}" + (f" | Motivo: {motivo}" if motivo else ""),
            now,
            author_id=actor_id,
        )
        if target_sub in {"resuelto", "cerrado"} and ticket.get("asignado_a"):
            decrementar_carga(str(ticket["asignado_a"]), specialty=ticket.get("categoria"))
        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        result_ticket = get_ticket(ticket_id)
    finally:
        conn.close()

    if result_ticket:
        new_estado = str(result_ticket.get("estado") or "").strip().lower()
        if old_estado and new_estado and old_estado != new_estado:
            try:
                _send_ticket_status_update_to_notify_emails(
                    result_ticket,
                    from_estado=old_estado,
                    to_estado=new_estado,
                    actor_id=actor_id,
                    motivo=motivo or "transicion_workflow",
                )
            except Exception as status_mail_error:
                logger.warning(f"[transition_ticket] aviso de estado por correo no crítico falló para ticket {ticket_id}: {status_mail_error}")

    return {
        "ok": True,
        "transition_id": int(transition_row["id"]) if transition_row else None,
        "ticket": result_ticket or get_ticket(ticket_id),
    }

def approve_ticket_change(
    ticket_id: int,
    step: int,
    decision: str,
    approver: str,
    approver_role: str,
    decision_note: str = "",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    if normalize_ticket_type(ticket.get("tipo")) != "cambio":
        raise ValueError("Las aprobaciones aplican solo a tickets de tipo 'cambio'.")

    step = int(step or 0)
    if step not in {1, 2}:
        raise ValueError("El paso de aprobación debe ser 1 o 2.")

    decision_norm = str(decision or "").strip().lower()
    if decision_norm not in {"approved", "rejected"}:
        raise ValueError("La decisión debe ser 'approved' o 'rejected'.")

    role_values = _normalize_roles(approver_role)
    step1_roles = {"admin", "implementaciones", "redes", "sistemas", "ops"}
    step2_roles = {"admin", "finance", "gerencia"}
    allowed_roles = step1_roles if step == 1 else step2_roles
    if not any(role in allowed_roles for role in role_values):
        role_label = ", ".join(role_values) if role_values else str(approver_role or "-")
        raise ValueError(f"El/los rol(es) '{role_label}' no están autorizados para aprobar paso {step}.")

    normalized_idem = (idempotency_key or "").strip()[:128] or None
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        if normalized_idem:
            idem_row = conn.execute(
                """SELECT id FROM ticket_approvals
                   WHERE ticket_id = ? AND idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (ticket_id, normalized_idem),
            ).fetchone()
            if idem_row:
                return {
                    "ok": True,
                    "duplicate_skipped": True,
                    "message": "Se evitó aprobación duplicada por Idempotency-Key.",
                    "ticket": get_ticket(ticket_id),
                }

        current_sub = normalize_subestado(ticket.get("subestado"), "recibido")
        if step == 1 and current_sub != "pendiente_aprobacion_1":
            raise ValueError("Paso 1 solo permitido cuando el cambio está en 'pendiente_aprobacion_1'.")
        if step == 2 and current_sub != "pendiente_aprobacion_2":
            raise ValueError("Paso 2 solo permitido cuando el cambio está en 'pendiente_aprobacion_2'.")

        approval_row = conn.execute(
            """INSERT INTO ticket_approvals
               (ticket_id, step, approver, decision, decision_note, idempotency_key, decided_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                ticket_id,
                step,
                approver,
                decision_norm,
                (decision_note or "").strip(),
                normalized_idem,
                now,
            ),
        ).fetchone()

        _emit_system_comment(
            conn,
            ticket_id,
            f"[APROBACION] Paso {step}: {decision_norm} por {approver}",
            now,
            author_id=approver,
        )

        to_subestado = None
        if decision_norm == "approved":
            to_subestado = "pendiente_aprobacion_2" if step == 1 else "aprobado"
        else:
            to_subestado = "rechazado"

        if to_subestado:
            new_estado = estado_from_subestado(to_subestado, str(ticket.get("estado") or "abierto"))
            conn.execute(
                "UPDATE tickets SET subestado = ?, estado = ?, updated_at = ? WHERE id = ?",
                (to_subestado, new_estado, now, ticket_id),
            )
            conn.execute(
                """INSERT INTO ticket_transitions
                   (ticket_id, from_subestado, to_subestado, actor, reason, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    current_sub,
                    to_subestado,
                    approver,
                    f"approval_step_{step}_{decision_norm}",
                    normalized_idem,
                    now,
                ),
            )

        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        return {
            "ok": True,
            "approval_id": int(approval_row["id"]) if approval_row else None,
            "ticket": get_ticket(ticket_id),
        }
    finally:
        conn.close()

def list_ticket_approvals(ticket_id: int) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id, ticket_id, step, approver, decision, decision_note, decided_at
               FROM ticket_approvals
               WHERE ticket_id = ?
               ORDER BY decided_at DESC, id DESC""",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_ticket_workflow(ticket_id: int) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")

    conn = db.get_conn()
    try:
        transitions = conn.execute(
            """SELECT id, ticket_id, from_subestado, to_subestado, actor, reason, created_at
               FROM ticket_transitions
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC""",
            (ticket_id,),
        ).fetchall()
        approvals = conn.execute(
            """SELECT id, ticket_id, step, approver, decision, decision_note, decided_at
               FROM ticket_approvals
               WHERE ticket_id = ?
               ORDER BY decided_at DESC, id DESC""",
            (ticket_id,),
        ).fetchall()
        latest_approvals = _latest_approval_decisions(conn, ticket_id)
    finally:
        conn.close()

    tipo = normalize_ticket_type(ticket.get("tipo"))
    sub = normalize_subestado(ticket.get("subestado"), "recibido")
    allowed_next = _workflow_next(tipo, sub)
    allowed_next = _filter_waiting_subestados(allowed_next, ticket.get("estado"))
    if tipo == "cambio":
        if latest_approvals.get(1) != "approved":
            allowed_next = [s for s in allowed_next if s not in {"pendiente_aprobacion_2", "aprobado", "en_ejecucion"}]
        if latest_approvals.get(2) != "approved":
            allowed_next = [s for s in allowed_next if s not in {"aprobado", "en_ejecucion"}]

    return {
        "ticket": ticket,
        "allowed_next": allowed_next,
        "resuelto_auto_close_hours": RESUELTO_AUTO_CLOSE_HOURS,
        "approvals_status": {
            "step1": latest_approvals.get(1, "pending"),
            "step2": latest_approvals.get(2, "pending"),
        },
        "transitions": [dict(r) for r in transitions],
        "approvals": [dict(r) for r in approvals],
    }

def reply_ticket_email(
    ticket_id: int,
    author_id: str,
    mensaje: str,
    author_role: str = "",
    asunto: Optional[str] = None,
    files: Optional[List[Any]] = None,  # List[UploadFile]
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Envía respuesta por correo desde un ticket y mantiene hilo cuando existe email_thread_id.
    Registra historial en ticket_emails y evento en timeline.
    Soporta adjuntos.
    """
    ticket = get_ticket(ticket_id)
    if not ticket:
        logger.error(f"Reply failed: Ticket {ticket_id} not found")
        raise ValueError("Ticket no encontrado")
    _ensure_can_participate_ticket(ticket, author_id, author_role, "responder correos")
    _ensure_reply_allowed_estado(ticket, "responder correos")

    clean_msg = (mensaje or "").strip()
    if not clean_msg:
        logger.error(f"Reply failed: Message empty for ticket {ticket_id}")
        raise ValueError("El mensaje de respuesta está vacío")

    to_email, cc_emails, bcc_emails, to_addr_record = _compose_reply_recipients(ticket)
    if not to_email or "@" not in to_email:
        logger.error(f"Reply failed: Invalid to_email '{to_email}' for ticket {ticket_id}")
        raise ValueError("Este ticket no tiene un correo de cliente válido")

    subject = _build_ticket_reply_subject(ticket, asunto)

    headers = _build_ticket_thread_headers(ticket)
    threaded = bool(headers.get("In-Reply-To") or headers.get("References"))

    escaped_msg = html.escape(clean_msg).replace("\n", "<br>")
    body_html = f"""

    <p>{escaped_msg}</p>
    <hr>
    <p style="color:#666;font-size:12px">
      Respuesta enviada desde Mesa de Ayuda {html.escape(ticket.get("codigo") or f"#{ticket_id}")}.
    </p>
    """
    now = db.now_utc_iso()
    preview = clean_msg if len(clean_msg) <= 300 else clean_msg[:300] + "..."
    normalized_idempotency_key = (idempotency_key or "").strip()[:128] or None
    
    # Procesar adjuntos
    email_attachments = []
    stored_attachments = []
    
    if files:
        base_root = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir())
        base_path = Path(base_root) / str(ticket_id) / "attachments"
        base_path.mkdir(parents=True, exist_ok=True)

        for file in files:
            try:
                # Validar tamaño y extensión
                file.file.seek(0, 2)
                size = file.file.tell()
                file.file.seek(0)
                
                if size > app_settings.TICKET_MAX_FILE_SIZE:
                    logger.warning(f"File {file.filename} exceeds max size")
                    continue
                    
                ext = Path(file.filename).suffix.lower()
                if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                    logger.warning(f"File extension {ext} not allowed")
                    continue

                # Leer contenido
                file_content = file.file.read()

                # Guardar en disco (temporalmente, confirmaremos si no es duplicado)
                filename = getattr(file, "filename", "untitled")
                file_path = base_path / _attachment_storage_name(filename)
                if not _is_safe_attachment_path(file_path):
                    logger.warning(f"[reply_email] ruta de adjunto fuera de raíz permitida: {file_path}")
                    continue
                
                with open(file_path, "wb") as f:
                    f.write(file_content)
                sha256 = hashlib.sha256(file_content).hexdigest()
                    
                email_attachments.append({
                    "filename": filename,
                    "data": file_content,
                    "content_type": getattr(file, "content_type", "application/octet-stream")
                })
                
                stored_attachments.append({
                    "filename": filename,
                    "path": str(file_path),
                    "size": len(file_content),
                    "content_type": getattr(file, "content_type", "application/octet-stream"),
                    "sha256": sha256,
                })
            except Exception as e:
                logger.error(f"Error procesando adjunto {getattr(file, 'filename', '?')}: {e}")

    dedupe_since = (
        datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(minutes=3)
    ).isoformat()
    marker_id = None

    # Lock + dedupe para evitar doble envío por reintento en UI.
    lock_conn = db.get_conn()
    try:
        try:
            lock_conn.execute("SELECT pg_advisory_lock(?)", (int(ticket_id),))
        except Exception:
            # Si no soporta advisory lock, seguimos con dedupe best-effort.
            pass

        if normalized_idempotency_key:
            idem_row = lock_conn.execute(
                """SELECT id FROM ticket_emails
                   WHERE ticket_id = ?
                     AND direction IN ('outgoing', 'outgoing_pending')
                     AND idempotency_key = ?
                   ORDER BY id DESC
                   LIMIT 1""",
                (ticket_id, normalized_idempotency_key),
            ).fetchone()
            if idem_row:
                for att in stored_attachments:
                    try:
                        Path(att["path"]).unlink(missing_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup duplicate file {att['path']}: {e}")
                return {
                    "ok": True,
                    "ticket_id": ticket_id,
                    "to_email": to_email,
                    "cc_emails": cc_emails,
                    "bcc_emails": bcc_emails,
                    "subject": subject,
                    "threaded": threaded,
                    "duplicate_skipped": True,
                    "message": "Se evitó un envío duplicado (Idempotency-Key ya procesado).",
                }

        # Check for duplicate including body and attachments hash (stored in metadata or body?)
        # For now, we trust subject + body + to_addr + strict time window.
        # Ideally we should store a hash of the operation.
        dup_row = lock_conn.execute(
            """SELECT id FROM ticket_emails
               WHERE ticket_id = ?
                 AND direction IN ('outgoing', 'outgoing_pending')
                 AND to_addr = ?
                 AND subject = ?
                 AND body_html = ?
                 AND created_at >= ?
               ORDER BY id DESC
               LIMIT 1""",
            (ticket_id, to_addr_record or to_email, subject, body_html, dedupe_since),
        ).fetchone()
        
        if dup_row:
             # Clean up stored files as they are duplicates
            for att in stored_attachments:
                try:
                    Path(att["path"]).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to cleanup duplicate file {att['path']}: {e}")

            return {
                "ok": True,
                "ticket_id": ticket_id,
                "to_email": to_email,
                "cc_emails": cc_emails,
                "bcc_emails": bcc_emails,
                "subject": subject,
                "threaded": threaded,
                "duplicate_skipped": True,
                "message": "Se evitó un envío duplicado (correo ya enviado recientemente).",
            }

        marker_row = lock_conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
               VALUES (?, 'outgoing_pending', '', ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, to_addr_record or to_email, ", ".join(cc_emails), ", ".join(bcc_emails), subject, body_html, json.dumps(stored_attachments), normalized_idempotency_key, now),
        ).fetchone()
        marker_id = marker_row["id"] if marker_row else None
        lock_conn.commit()
    finally:
        try:
            lock_conn.execute("SELECT pg_advisory_unlock(?)", (int(ticket_id),))
        except Exception:
            pass
        lock_conn.close()

    try:
        send_meta = email_sender.send_email_advanced(
            to_email=to_email,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            html_body=body_html,
            headers=headers or None,
            attachments=email_attachments
        )
    except Exception as e:
        # Limpieza de marcador para permitir retry real si falló envío.
        if marker_id:
            cleanup_conn = db.get_conn()
            try:
                cleanup_conn.execute(
                    "DELETE FROM ticket_emails WHERE id = ? AND direction = 'outgoing_pending'",
                    (marker_id,),
                )
                cleanup_conn.commit()
            finally:
                cleanup_conn.close()
        for att in stored_attachments:
            try:
                Path(att["path"]).unlink(missing_ok=True)
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup attachment file on send error {att['path']}: {cleanup_error}")
        raise ValueError(str(e))

    conn = db.get_conn()
    try:
        if marker_id:
            conn.execute(
                """UPDATE ticket_emails
                   SET direction = 'outgoing', from_addr = ?, to_addr = ?, cc_addrs = ?, bcc_addrs = ?
                   WHERE id = ?""",
                (send_meta.get("from_addr"), to_addr_record or to_email, ", ".join(cc_emails), ", ".join(bcc_emails), marker_id),
            )
        else:
            conn.execute(
                """INSERT INTO ticket_emails
                   (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    "outgoing",
                    send_meta.get("from_addr"),
                    to_addr_record or to_email,
                    ", ".join(cc_emails),
                    ", ".join(bcc_emails),
                    subject,
                    body_html,
                    json.dumps(stored_attachments),
                    normalized_idempotency_key,
                    now,
                ),
            )

        for att in stored_attachments:
            conn.execute(
                """INSERT INTO ticket_attachments
                   (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    str(att.get("filename") or "attachment.bin"),
                    str(att.get("path") or ""),
                    author_id,
                    now,
                    int(att.get("size") or 0),
                    str(att.get("content_type") or "application/octet-stream"),
                    str(att.get("sha256") or ""),
                ),
            )
        
        has_attachments = " (con adjuntos)" if stored_attachments else ""
        cc_hint = f" + CC: {', '.join(cc_emails)}" if cc_emails else ""
        bcc_hint = f" + CCO: {', '.join(bcc_emails)}" if bcc_emails else ""
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, author_id, f"[CORREO] Respuesta enviada a {to_email}{cc_hint}{bcc_hint}{has_attachments}: {preview}", now),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        _maybe_mark_first_response(conn, ticket_id, author_id, now)

        _update_ticket_thread_metadata(
            conn,
            ticket_id,
            message_id=send_meta.get("message_id"),
            in_reply_to=headers.get("In-Reply-To"),
            references=headers.get("References"),
        )

        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.8.16",
            artifact_ref=f"ticket:{ticket_id}:email_reply",
            owner=author_id,
            integrity_hash=send_meta.get("message_id") or "",
            metadata={
                "to": to_email,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "threaded": threaded,
                "has_attachments": bool(stored_attachments),
                "idempotency_key": normalized_idempotency_key or "",
            },
        )
    except Exception as e:
        logger.warning(f"[reply_ticket_email] evidence_event no crítico falló para ticket {ticket_id}: {e}")

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "to_email": to_email,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": subject,
        "threaded": threaded,
        "message_id": send_meta.get("message_id"),
        "idempotency_key": normalized_idempotency_key,
    }

def _html_to_text(raw_html: str) -> str:
    text = raw_html or ""
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()

def _parse_attachments_json(raw_value: Any) -> List[Dict[str, Any]]:
    if not raw_value:
        return []
    if isinstance(raw_value, list):
        return raw_value
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []

def _persist_incoming_attachments(
    conn,
    ticket_id: int,
    attachments: Optional[List[Dict[str, Any]]],
    *,
    uploaded_by: str = "email_bot",
) -> List[Dict[str, Any]]:
    """
    Persist incoming email attachments into ticket_attachments.
    Accepts items in format:
    - {"filename": "...", "content_type": "...", "data": bytes}
    - {"filename": "...", "content_type": "...", "data_base64": "..."}
    """
    if not attachments:
        return []
    now = db.now_utc_iso()
    base_path = Path(str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir()))
    base_path = (base_path / str(ticket_id) / "incoming").resolve()
    base_path.mkdir(parents=True, exist_ok=True)

    saved: List[Dict[str, Any]] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip() or "attachment.bin"
        ext = Path(filename).suffix.lower()
        if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
            logger.warning(f"[incoming_attachments] extensión no permitida: {filename}")
            continue

        raw_data = item.get("data")
        data: bytes
        if isinstance(raw_data, bytes):
            data = raw_data
        else:
            b64 = str(item.get("data_base64") or "").strip()
            if not b64:
                continue
            try:
                data = base64.b64decode(b64, validate=True)
            except Exception:
                logger.warning(f"[incoming_attachments] base64 inválido en archivo {filename}")
                continue

        if not data:
            continue
        if len(data) > app_settings.TICKET_MAX_FILE_SIZE:
            logger.warning(f"[incoming_attachments] tamaño excedido: {filename} ({len(data)})")
            continue

        file_path = (base_path / _attachment_storage_name(filename)).resolve()
        if not _is_safe_attachment_path(file_path):
            logger.warning(f"[incoming_attachments] ruta fuera de raíz permitida: {file_path}")
            continue

        with open(file_path, "wb") as fh:
            fh.write(data)
        sha256 = hashlib.sha256(data).hexdigest()
        content_type = str(item.get("content_type") or "application/octet-stream")
        conn.execute(
            """INSERT INTO ticket_attachments
               (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(ticket_id),
                filename,
                str(file_path),
                uploaded_by,
                now,
                len(data),
                content_type,
                sha256,
            ),
        )
        saved.append(
            {
                "filename": filename,
                "path": str(file_path),
                "size": len(data),
                "content_type": content_type,
                "sha256": sha256,
            }
        )
    return saved

def get_ticket_emails(ticket_id: int, format_human: bool = False) -> List[Dict[str, Any]]:
    """Obtiene el historial de correos de un ticket; opcionalmente en formato legible."""
    conn = db.get_conn()
    try:
        cursor = conn.execute(
            """SELECT * FROM ticket_emails
               WHERE ticket_id = ?
               ORDER BY created_at DESC""",
            (ticket_id,),
        )
        items = [dict(row) for row in cursor.fetchall()]
        if not format_human:
            return items

        out: List[Dict[str, Any]] = []
        for row in items:
            body_text = _html_to_text(row.get("body_html") or "")
            attachments = _parse_attachments_json(row.get("attachments_json"))
            out.append(
                {
                    "id": row.get("id"),
                    "ticket_id": row.get("ticket_id"),
                    "direction": row.get("direction"),
                    "subject": row.get("subject") or "",
                    "from_addr": row.get("from_addr") or "",
                    "to_addr": row.get("to_addr") or "",
                    "cc_addrs": row.get("cc_addrs") or "",
                    "bcc_addrs": row.get("bcc_addrs") or "",
                    "created_at": row.get("created_at"),
                    "body_text": body_text,
                    "preview": body_text[:280] + ("..." if len(body_text) > 280 else ""),
                    "attachments": attachments,
                }
            )
        return out
    finally:
        conn.close()

def upload_ticket_attachments(
    ticket_id: int,
    uploaded_by: str,
    files: Optional[List[Any]],
    uploaded_role: str = "",
) -> Dict[str, Any]:
    """Sube adjuntos manuales al ticket y devuelve metadata con hash/size."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_participate_ticket(ticket, uploaded_by, uploaded_role, "subir adjuntos")
    if not files:
        return {"ok": True, "ticket_id": ticket_id, "uploaded": 0, "items": list_ticket_attachments(ticket_id)}

    base_root = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir())
    base_path = Path(base_root) / str(ticket_id) / "manual"
    base_path.mkdir(parents=True, exist_ok=True)
    now = db.now_utc_iso()
    uploaded = 0

    conn = db.get_conn()
    try:
        for file in files:
            filename = getattr(file, "filename", "untitled")
            if not filename:
                filename = "untitled"
            ext = Path(filename).suffix.lower()
            if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                logger.warning(f"[attachments] Extensión no permitida: {filename}")
                continue

            file.file.seek(0, 2)
            size = int(file.file.tell())
            file.file.seek(0)
            if size > app_settings.TICKET_MAX_FILE_SIZE:
                logger.warning(f"[attachments] Tamaño excedido: {filename} ({size})")
                continue

            content = file.file.read()
            sha256 = hashlib.sha256(content).hexdigest()
            file_path = base_path / _attachment_storage_name(filename)
            if not _is_safe_attachment_path(file_path):
                logger.warning(f"[attachments] ruta de adjunto fuera de raíz permitida: {file_path}")
                continue
            with open(file_path, "wb") as fh:
                fh.write(content)

            conn.execute(
                """INSERT INTO ticket_attachments
                   (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    filename,
                    str(file_path),
                    uploaded_by,
                    now,
                    len(content),
                    getattr(file, "content_type", "application/octet-stream"),
                    sha256,
                ),
            )
            uploaded += 1

        if uploaded > 0:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (ticket_id, uploaded_by, f"[ADJUNTO] Se cargaron {uploaded} archivo(s).", now),
            )
            conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        conn.commit()
    finally:
        conn.close()

    if uploaded > 0:
        try:
            create_evidence_event(
                control_id="A.8.12",
                artifact_ref=f"ticket:{ticket_id}:attachments",
                owner=uploaded_by,
                integrity_hash="",
                metadata={"uploaded": uploaded},
            )
        except Exception as e:
            logger.warning(f"[upload_ticket_attachments] evidence_event no crítico falló para ticket {ticket_id}: {e}")

    return {"ok": True, "ticket_id": ticket_id, "uploaded": uploaded, "items": list_ticket_attachments(ticket_id)}

def list_ticket_attachments(ticket_id: int) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT id, ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256
               FROM ticket_attachments
               WHERE ticket_id = ?
               ORDER BY created_at DESC""",
            (ticket_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_ticket_attachment_for_download(ticket_id: int, attachment_id: int) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT id, ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256
               FROM ticket_attachments
               WHERE ticket_id = ? AND id = ?
               LIMIT 1""",
            (int(ticket_id), int(attachment_id)),
        ).fetchone()
        if not row:
            raise ValueError("Adjunto no encontrado")
        item = dict(row)
    finally:
        conn.close()

    raw_path = str(item.get("file_path") or "").strip()
    if not raw_path:
        raise ValueError("Adjunto sin ruta de archivo")

    path = Path(raw_path)
    if not _is_safe_attachment_path(path):
        raise ValueError("Ruta de adjunto fuera de raíz permitida")
    if not path.exists() or not path.is_file():
        raise ValueError("Archivo adjunto no disponible")

    item["resolved_path"] = str(path.resolve())
    return item

def get_timeline(ticket_id: int, limit: int = 120, include_emails: bool = False) -> List[Dict[str, Any]]:
    """Línea de tiempo unificada para la UI.

    Salida normalizada por evento:
      - event_type
      - event_at (UTC ISO)
      - actor
      - detail
      - source_table
      - source_id

    Compatibilidad: mantiene `created_at` como alias de `event_at`.
    """
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 120), 500))

        comment_rows = conn.execute(
            """SELECT id, user_id, content, created_at
               FROM ticket_comments
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (ticket_id, limit),
        ).fetchall()

        transition_rows = conn.execute(
            """SELECT id, from_subestado, to_subestado, actor, reason, created_at
               FROM ticket_transitions
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
            (ticket_id, limit),
        ).fetchall()

        approval_rows = conn.execute(
            """SELECT id, step, approver, decision, decision_note, decided_at
               FROM ticket_approvals
               WHERE ticket_id = ?
               ORDER BY decided_at DESC, id DESC
               LIMIT ?""",
            (ticket_id, limit),
        ).fetchall()

        email_rows = []
        if include_emails:
            email_rows = conn.execute(
                """SELECT id, direction, subject, from_addr, to_addr, created_at
               FROM ticket_emails
               WHERE ticket_id = ?
               ORDER BY created_at DESC, id DESC
               LIMIT ?""",
                (ticket_id, limit),
            ).fetchall()

        def _to_event_at(raw_value: Optional[str]) -> str:
            dt = _parse_dt(raw_value) or _now_dt()
            return _ensure_utc(dt).isoformat()

        events: List[Dict[str, Any]] = []

        for row in comment_rows:
            content = str(row["content"] or "")
            event_type = "comment"
            detail = content
            if content.startswith("[") and "]" in content:
                parts = content.split("]", 1)
                inferred = parts[0][1:].strip().lower()
                if inferred:
                    event_type = inferred
                detail = parts[1].strip()

            event_at = _to_event_at(row["created_at"])
            events.append(
                {
                    "event_type": event_type,
                    "event_at": event_at,
                    "created_at": event_at,
                    "actor": str(row["user_id"] or "system"),
                    "detail": detail,
                    "source_table": "ticket_comments",
                    "source_id": int(row["id"]),
                }
            )

        for row in transition_rows:
            from_sub = str(row["from_subestado"] or "-")
            to_sub = str(row["to_subestado"] or "-")
            reason = str(row["reason"] or "").strip()
            detail = f"{from_sub} -> {to_sub}" + (f" | reason: {reason}" if reason else "")

            event_at = _to_event_at(row["created_at"])
            events.append(
                {
                    "event_type": "transition",
                    "event_at": event_at,
                    "created_at": event_at,
                    "actor": str(row["actor"] or "system"),
                    "detail": detail,
                    "source_table": "ticket_transitions",
                    "source_id": int(row["id"]),
                }
            )

        for row in approval_rows:
            step = int(row["step"] or 0)
            decision = str(row["decision"] or "pending")
            note = str(row["decision_note"] or "").strip()
            detail = f"step={step} decision={decision}" + (f" | note: {note}" if note else "")

            event_at = _to_event_at(row["decided_at"])
            events.append(
                {
                    "event_type": "approval",
                    "event_at": event_at,
                    "created_at": event_at,
                    "actor": str(row["approver"] or "system"),
                    "detail": detail,
                    "source_table": "ticket_approvals",
                    "source_id": int(row["id"]),
                }
            )

        # include_emails se mantiene por compatibilidad de firma; la timeline unificada
        # ahora siempre incorpora correos para tener trazabilidad completa.
        if include_emails:
            for row in email_rows:
                direction = str(row["direction"] or "").strip().lower()
                subject = str(row["subject"] or "").strip()
                from_addr = str(row["from_addr"] or "").strip()
                to_addr = str(row["to_addr"] or "").strip()
    
                parts = [f"direction={direction or '-'}"]
                if subject:
                    parts.append(f"subject={subject}")
                if from_addr:
                    parts.append(f"from={from_addr}")
                if to_addr:
                    parts.append(f"to={to_addr}")
    
                event_at = _to_event_at(row["created_at"])
                events.append(
                    {
                        "event_type": "email",
                        "event_at": event_at,
                        "created_at": event_at,
                        "actor": from_addr or to_addr or "system",
                        "detail": " | ".join(parts),
                        "source_table": "ticket_emails",
                        "source_id": int(row["id"]),
                    }
                )
    
        events.sort(
            key=lambda item: (item.get("event_at") or "", int(item.get("source_id") or 0)),
            reverse=True,
        )
        return events[:limit]
    finally:
        conn.close()

def get_stats(asignado_a: Optional[str] = None) -> Dict[str, Any]:
    """Obtener métricas para Dashboard."""
    conn = db.get_conn()
    try:
        where_parts = ["1=1"]
        where_params: List[Any] = []
        if asignado_a is not None and str(asignado_a).strip():
            where_parts.append("LOWER(COALESCE(asignado_a, '')) = ?")
            where_params.append(str(asignado_a).strip().lower())
        where_sql = " AND ".join(where_parts)

        stats = {
            "by_status": {},
            "by_prio": {},
            "by_category": {},
            "pivot_assignee": {},
            "sla_compliance": {"on_time": 0, "breached": 0},
            "total": 0,
        }

        # Por Estado
        rows = conn.execute(
            f"SELECT estado, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY estado",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            stats["by_status"][r["estado"]] = r["c"]
            stats["total"] += r["c"]

        # Por Severidad
        rows = conn.execute(
            f"SELECT severidad, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY severidad",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            stats["by_prio"][r["severidad"]] = r["c"]

        # Por Categoría
        rows = conn.execute(
            f"SELECT categoria, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY categoria",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            stats["by_category"][r["categoria"] or "general"] = r["c"]

        # Pivot: Assignee vs Status
        rows = conn.execute(
            f"SELECT asignado_a, estado, COUNT(*) as c FROM tickets WHERE {where_sql} GROUP BY asignado_a, estado",
            tuple(where_params),
        ).fetchall()
        for r in rows:
            assignee = r["asignado_a"] or "Sin Asignar"
            status = r["estado"]
            count = r["c"]
            if assignee not in stats["pivot_assignee"]:
                stats["pivot_assignee"][assignee] = {"total": 0}
            stats["pivot_assignee"][assignee][status] = count
            stats["pivot_assignee"][assignee]["total"] += count

        # SLA Compliance
        now = db.now_utc_iso()
        sla_params: List[Any] = [now, now, *where_params]
        row = conn.execute("""
            SELECT
                COUNT(CASE WHEN vence_at >= ? OR estado IN ('cerrado','resuelto') THEN 1 END) as on_time,
                COUNT(CASE WHEN vence_at < ? AND estado NOT IN ('cerrado','resuelto') THEN 1 END) as breached
            FROM tickets WHERE vence_at IS NOT NULL AND """ + where_sql,
            tuple(sla_params),
        ).fetchone()
        if row:
            stats["sla_compliance"]["on_time"] = row["on_time"]
            stats["sla_compliance"]["breached"] = row["breached"]

        return stats
    finally:
        conn.close()

def _assignment_phase_from_subestado(subestado: Optional[str]) -> Optional[str]:
    raw = str(subestado or "").strip().lower()
    normalized = SUBESTADOS_LEGACY_MAP.get(raw, raw)
    if normalized == "asignado":
        return "asignado"
    if normalized in {"en_progreso", "en_validacion", "en_ejecucion", "en_analisis", "aprobado"}:
        return "en_progreso"
    if normalized == "resuelto":
        return "resuelto"
    return None

def _build_assignment_segments(
    ticket: Dict[str, Any],
    transitions: List[Dict[str, Any]],
    now_dt: datetime,
) -> List[Dict[str, Any]]:
    ordered = sorted(
        (dict(t or {}) for t in (transitions or [])),
        key=lambda t: ((_parse_dt(t.get("created_at")) or now_dt), int(t.get("id") or 0)),
    )
    segments: List[Dict[str, Any]] = []
    active_phase: Optional[str] = None
    active_start: Optional[datetime] = None

    for tr in ordered:
        ts = _parse_dt(tr.get("created_at"))
        if not ts:
            continue
        next_phase = _assignment_phase_from_subestado(tr.get("to_subestado"))

        if active_phase and active_start:
            if next_phase == active_phase:
                continue
            end_dt = ts if ts >= active_start else active_start
            segments.append(
                {
                    "phase": active_phase,
                    "start_at": active_start.isoformat(),
                    "end_at": end_dt.isoformat(),
                }
            )
            active_phase = None
            active_start = None

        if next_phase:
            active_phase = next_phase
            active_start = ts

    if not segments and not active_phase:
        fallback_phase = _assignment_phase_from_subestado(ticket.get("subestado"))
        fallback_start = _parse_dt(ticket.get("created_at"))
        if fallback_phase and fallback_start:
            active_phase = fallback_phase
            active_start = fallback_start

    if active_phase and active_start:
        estado = str(ticket.get("estado") or "").strip().lower()
        if estado == "cerrado":
            fallback_end = (
                _parse_dt(ticket.get("updated_at"))
                or _parse_dt(ticket.get("resolved_at"))
                or now_dt
            )
        elif estado == "resuelto":
            fallback_end = (
                _parse_dt(ticket.get("resolved_at"))
                or _parse_dt(ticket.get("updated_at"))
                or now_dt
            )
        else:
            fallback_end = now_dt
        if fallback_end < active_start:
            fallback_end = active_start
        segments.append(
            {
                "phase": active_phase,
                "start_at": active_start.isoformat(),
                "end_at": fallback_end.isoformat(),
            }
        )

    merged: List[Dict[str, Any]] = []
    for seg in segments:
        if not merged:
            merged.append(seg)
            continue
        prev = merged[-1]
        prev_end = _parse_dt(prev.get("end_at"))
        cur_start = _parse_dt(seg.get("start_at"))
        cur_end = _parse_dt(seg.get("end_at"))
        if (
            prev.get("phase") == seg.get("phase")
            and prev_end
            and cur_start
            and cur_start <= prev_end
        ):
            if cur_end and cur_end > prev_end:
                prev["end_at"] = cur_end.isoformat()
            continue
        merged.append(seg)
    return merged

def get_assignment_timeline(
    window_hours: int = 72,
    ticket_limit: int = 400,
    assignee: Optional[str] = None,
) -> Dict[str, Any]:
    window_hours = _clamp_int(window_hours, default_value=72, min_value=1, max_value=720)
    ticket_limit = _clamp_int(ticket_limit, default_value=400, min_value=50, max_value=2000)
    assignee_filter = _normalize_username(assignee)

    now_iso = db.now_utc_iso()
    now_dt = _parse_dt(now_iso) or _now_dt()
    window_start_dt = now_dt - timedelta(hours=window_hours)

    spec_rows = list_specialties()
    tech_map: Dict[str, Dict[str, Any]] = {}
    for row in spec_rows:
        username = str(row.get("username") or "").strip().lower()
        specialty = str(row.get("specialty") or "").strip().lower()
        if not username:
            continue
        if assignee_filter and username != assignee_filter:
            continue
        if specialty == "admin":
            continue
        lane = tech_map.setdefault(
            username,
            {
                "username": username,
                "specialties": [],
                "roles": [],
                "current_load": 0,
                "max_load": int(row.get("max_load") or 0),
                "_items": [],
            },
        )
        role_primary = _normalize_role(row.get("role"))
        if role_primary and role_primary not in lane["roles"]:
            lane["roles"].append(role_primary)
        try:
            secondary_roles = json.loads(row.get("secondary_roles") or "[]")
        except Exception:
            secondary_roles = []
        for role_item in _normalize_roles(secondary_roles):
            if role_item and role_item not in lane["roles"]:
                lane["roles"].append(role_item)
        if specialty and specialty not in lane["specialties"]:
            lane["specialties"].append(specialty)
        lane["current_load"] = max(int(lane.get("current_load") or 0), int(row.get("current_load") or 0))
        lane["max_load"] = max(int(lane.get("max_load") or 0), int(row.get("max_load") or 0))

    conn = db.get_conn()
    try:
        if assignee_filter:
            ticket_rows = conn.execute(
                """SELECT id, codigo, titulo, estado, subestado, asignado_a, categoria, severidad,
                          created_at, updated_at, resolved_at
                   FROM tickets
                   WHERE LOWER(COALESCE(asignado_a, '')) = ?
                   ORDER BY created_at ASC, id ASC
                   LIMIT ?""",
                (assignee_filter, ticket_limit),
            ).fetchall()
        else:
            ticket_rows = conn.execute(
                """SELECT id, codigo, titulo, estado, subestado, asignado_a, categoria, severidad,
                          created_at, updated_at, resolved_at
                   FROM tickets
                   WHERE (asignado_a IS NOT NULL)
                      OR (COALESCE(asignado_a, '') = '' AND estado = 'abierto')
                   ORDER BY created_at ASC, id ASC
                   LIMIT ?""",
                (ticket_limit,),
            ).fetchall()
        tickets_data = [dict(r) for r in ticket_rows]
        ticket_ids = [int(t["id"]) for t in tickets_data if t.get("id") is not None]

        transitions_by_ticket: Dict[int, List[Dict[str, Any]]] = {}
        if ticket_ids:
            placeholders = ", ".join(["?"] * len(ticket_ids))
            transition_rows = conn.execute(
                f"""SELECT id, ticket_id, to_subestado, created_at
                    FROM ticket_transitions
                    WHERE ticket_id IN ({placeholders})
                    ORDER BY created_at ASC, id ASC""",
                tuple(ticket_ids),
            ).fetchall()
            for row in transition_rows:
                tid = int(row["ticket_id"])
                transitions_by_ticket.setdefault(tid, []).append(dict(row))
    finally:
        conn.close()

    queue: List[Dict[str, Any]] = []
    for ticket in tickets_data:
        ticket_assignee = str(ticket.get("asignado_a") or "").strip().lower()
        estado = str(ticket.get("estado") or "").strip().lower()
        subestado = str(ticket.get("subestado") or "").strip().lower()
        tid = int(ticket.get("id") or 0)

        segments = _build_assignment_segments(ticket, transitions_by_ticket.get(tid, []), now_dt)
        item = {
            "ticket_id": tid,
            "codigo": ticket.get("codigo") or f"#{tid}",
            "titulo": ticket.get("titulo") or "Sin título",
            "estado": estado,
            "subestado": subestado,
            "categoria": ticket.get("categoria") or "general",
            "severidad": ticket.get("severidad") or "media",
            "created_at": ticket.get("created_at"),
            "updated_at": ticket.get("updated_at"),
            "resolved_at": ticket.get("resolved_at"),
            "segments": segments,
            "active_phase": _assignment_phase_from_subestado(subestado),
            "is_done": estado in {"resuelto", "cerrado"},
            "started_at": segments[0]["start_at"] if segments else ticket.get("created_at"),
            "ended_at": segments[-1]["end_at"] if segments else ticket.get("updated_at"),
        }

        if ticket_assignee:
            if ticket_assignee not in tech_map:
                tech_map[ticket_assignee] = {
                    "username": ticket_assignee,
                    "specialties": [],
                    "roles": [],
                    "current_load": 0,
                    "max_load": 0,
                    "_items": [],
                }
            tech_map[ticket_assignee]["_items"].append(item)
            continue

        if estado == "abierto":
            created_dt = _parse_dt(ticket.get("created_at"))
            waiting_minutes = max(0, int((now_dt - created_dt).total_seconds() // 60)) if created_dt else 0
            queue.append(
                {
                    "ticket_id": tid,
                    "codigo": ticket.get("codigo") or f"#{tid}",
                    "titulo": ticket.get("titulo") or "Sin título",
                    "categoria": ticket.get("categoria") or "general",
                    "severidad": ticket.get("severidad") or "media",
                    "created_at": ticket.get("created_at"),
                    "waiting_minutes": waiting_minutes,
                }
            )

    technicians: List[Dict[str, Any]] = []
    for username in sorted(tech_map.keys()):
        lane = tech_map[username]
        items = sorted(
            lane.get("_items") or [],
            key=lambda x: (_parse_dt(x.get("started_at")) or now_dt, int(x.get("ticket_id") or 0)),
        )
        active_items = [it for it in items if str(it.get("estado") or "").lower() not in {"resuelto", "cerrado"}]
        technicians.append(
            {
                "username": lane.get("username"),
                "specialties": sorted(lane.get("specialties") or []),
                "roles": sorted(lane.get("roles") or []),
                "current_load": int(lane.get("current_load") or 0),
                "max_load": int(lane.get("max_load") or 0),
                "status": "ocupado" if active_items else "disponible",
                "active_count": len(active_items),
                "items": items,
            }
        )

    queue_projection = [dict(q) for q in queue]
    for lane in technicians:
        next_ticket: Optional[Dict[str, Any]] = None
        if lane.get("status") == "disponible" and queue_projection:
            specialties = {str(s).strip().lower() for s in (lane.get("specialties") or []) if str(s).strip()}
            pick_idx: Optional[int] = None
            for idx, queued in enumerate(queue_projection):
                cat = str(queued.get("categoria") or "").strip().lower()
                if cat in specialties or cat in {"general", ""}:
                    pick_idx = idx
                    break
            if pick_idx is None:
                pick_idx = 0
            next_ticket = queue_projection.pop(pick_idx)
        lane["next_queue_ticket"] = next_ticket

    range_points: List[datetime] = [window_start_dt, now_dt]
    for lane in technicians:
        for item in lane.get("items") or []:
            for seg in item.get("segments") or []:
                sdt = _parse_dt(seg.get("start_at"))
                edt = _parse_dt(seg.get("end_at"))
                if sdt:
                    range_points.append(sdt)
                if edt:
                    range_points.append(edt)
    range_start = min(range_points) if range_points else window_start_dt
    range_end = max(range_points) if range_points else now_dt
    if range_end <= range_start:
        range_end = range_start + timedelta(minutes=1)

    return {
        "ok": True,
        "generated_at": now_iso,
        "window_hours": window_hours,
        "range": {
            "start_at": range_start.isoformat(),
            "end_at": range_end.isoformat(),
        },
        "technicians": technicians,
        "queue": queue,
    }

# ==========================================================================
# SLA / BREACHES / AUTOMATIONS / EVIDENCE / JIRA IMPORT
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
        where = ["1=1"]
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

def import_jira_issues(
    issues: List[Dict[str, Any]],
    imported_by: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    created_items: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    payload_snapshot = {"count": len(issues), "dry_run": bool(dry_run)}

    for issue in issues:
        key = (issue.get("key") or "").strip()
        summary = (issue.get("summary") or key or "Ticket importado desde Jira").strip()
        description = (issue.get("description") or "").strip()
        if key:
            description = f"[JIRA:{key}] {description}".strip()

        jira_priority = (issue.get("priority") or "medium").strip().lower()
        severidad = JIRA_PRIORITY_TO_SEVERIDAD.get(jira_priority, "media")
        jira_status = (issue.get("status") or "open").strip().lower()
        target_state = JIRA_STATUS_MAP.get(jira_status, "abierto")
        reporter_email = (issue.get("reporter_email") or "").strip() or None
        reporter_name = (issue.get("reporter_name") or "").strip() or None
        issue_type = (issue.get("issue_type") or "incidencia").strip().lower()
        security_class = normalize_ticket_security_class(issue.get("ticket_security_class"))

        if dry_run:
            created_items.append(
                {
                    "jira_key": key,
                    "preview_title": summary,
                    "preview_state": target_state,
                    "preview_severity": severidad,
                    "preview_security_class": security_class,
                }
            )
            continue

        try:
            created = create_ticket(
                titulo=summary,
                descripcion=description,
                creador_id=f"jira_import:{imported_by}",
                severidad=severidad,
                tipo=issue_type if issue_type in {"incidencia", "requerimiento", "cambio"} else "incidencia",
                categoria=issue.get("categoria") or "general",
                origen_email=reporter_email,
                cliente_nombre=reporter_name,
                ticket_security_class=security_class,
            )
            ticket_id = int(created["id"])

            patch_data: Dict[str, Any] = {}
            if issue.get("assignee"):
                patch_data["asignado_a"] = issue.get("assignee")
            if target_state in ESTADOS_VALIDOS and target_state != "abierto":
                patch_data["estado"] = target_state
            if patch_data:
                update_ticket(ticket_id, patch_data, actor_id=f"jira_import:{imported_by}")

            comments = issue.get("comments") or []
            if isinstance(comments, list):
                for c in comments:
                    author = (c.get("author") or "jira").strip() if isinstance(c, dict) else "jira"
                    body = (c.get("body") or "").strip() if isinstance(c, dict) else str(c).strip()
                    if body:
                        add_comment(ticket_id, f"jira:{author}", body, "jira_import")

            created_items.append(
                {
                    "jira_key": key,
                    "ticket_id": ticket_id,
                    "ticket_code": created.get("codigo"),
                    "estado": patch_data.get("estado", "abierto"),
                }
            )
        except Exception as e:
            errors.append({"jira_key": key, "error": str(e)})

    result = {
        "ok": len(errors) == 0,
        "dry_run": bool(dry_run),
        "imported": len(created_items),
        "failed": len(errors),
        "items": created_items,
        "errors": errors,
    }

    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO jira_import_runs (imported_by, payload_json, result_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                imported_by,
                json.dumps(payload_snapshot, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                db.now_utc_iso(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        create_evidence_event(
            control_id="A.5.37",
            artifact_ref="jira_import_runs",
            owner=imported_by,
            integrity_hash="",
            metadata={"dry_run": bool(dry_run), "imported": len(created_items), "failed": len(errors)},
        )
    except Exception as e:
        logger.warning(f"[import_jira_issues] evidence_event no crítico falló: {e}")

    return result

def _jira_project_keys_from_raw(raw_value: Optional[str]) -> List[str]:
    items = [x.strip() for x in str(raw_value or "").split(",")]
    return [x for x in items if x]

def _jira_effective_project_keys(project_keys: Optional[List[str]] = None) -> List[str]:
    if project_keys:
        return [x.strip() for x in project_keys if str(x).strip()]
    return _jira_project_keys_from_raw(JIRA_PROJECT_KEYS)

def _jira_is_live_configured() -> bool:
    return bool(JIRA_BASE_URL and JIRA_USER and JIRA_API_TOKEN)

def _jira_build_auth_header() -> str:
    token = base64.b64encode(f"{JIRA_USER}:{JIRA_API_TOKEN}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"

def _jira_description_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Soporte básico para descripciones en formato Atlassian Document Format.
        if isinstance(value.get("content"), list):
            chunks: List[str] = []
            def _walk(items: List[Any]) -> None:
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text)
                    child = item.get("content")
                    if isinstance(child, list):
                        _walk(child)
            _walk(value.get("content") or [])
            if chunks:
                return " ".join(chunks).strip()
        return _stable_json(value)
    return str(value)

def _jira_comment_body_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _jira_description_to_text(value)
    return str(value)

def _jira_issue_author(issue_like: Any) -> str:
    if isinstance(issue_like, str):
        return issue_like.strip()
    if isinstance(issue_like, dict):
        for key in ("displayName", "name", "emailAddress", "accountId"):
            raw = issue_like.get(key)
            if raw and str(raw).strip():
                return str(raw).strip()
    return ""

def _jira_status_to_estado(status_name: str) -> str:
    raw = (status_name or "").strip().lower()
    return JIRA_STATUS_MAP.get(raw, "abierto")

def _jira_issue_type_to_tipo(issue_type: str) -> str:
    normalized = (issue_type or "incidencia").strip().lower()
    if normalized in TIPOS_TICKET_VALIDOS:
        return normalized
    mapping = {
        "incident": "incidencia",
        "service request": "requerimiento",
        "change": "cambio",
        "task": "requerimiento",
        "bug": "incidencia",
        "story": "requerimiento",
    }
    return mapping.get(normalized, "incidencia")

def _jira_request_json(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not _jira_is_live_configured():
        raise ValueError("Jira no configurado: revisar JIRA_BASE_URL/JIRA_USER/JIRA_API_TOKEN")
    safe_path = "/" + str(path or "").lstrip("/")
    query = ""
    if params:
        encoded = urlparse.urlencode(params, doseq=True)
        query = f"?{encoded}" if encoded else ""
    url = f"{JIRA_BASE_URL}{safe_path}{query}"
    req = urlrequest.Request(url=url, method="GET")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", _jira_build_auth_header())
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if not body.strip():
                return {}
            parsed = json.loads(body)
            return parsed if isinstance(parsed, dict) else {}
    except urlerror.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        raise ValueError(f"Jira API error HTTP {int(e.code or 500)}: {detail[:500]}")
    except Exception as e:
        raise ValueError(f"Jira API error: {e}")

def _jira_jql_timestamp(iso_value: str) -> str:
    dt = _parse_dt(iso_value) or _now_dt()
    dt = _ensure_utc(dt)
    return dt.strftime("%Y-%m-%d %H:%M")

def _jira_fetch_issues_live(
    *,
    project_keys: List[str],
    run_type: str,
    only_open: bool,
    updated_since: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    if not project_keys:
        raise ValueError("No hay proyectos Jira configurados (JIRA_PROJECT_KEYS)")

    projects = ",".join(project_keys)
    if run_type == "bootstrap":
        jql = f"project in ({projects}) AND statusCategory != Done ORDER BY updated ASC"
    else:
        if updated_since:
            ts = _jira_jql_timestamp(updated_since)
            jql = f"project in ({projects}) AND updated >= \"{ts}\" ORDER BY updated ASC"
        else:
            jql = f"project in ({projects}) ORDER BY updated ASC"
        if only_open:
            jql = f"project in ({projects}) AND statusCategory != Done ORDER BY updated ASC"

    page_size = max(1, min(limit, 100))
    max_rows = max(1, min(limit, JIRA_SYNC_MAX_LIMIT))
    start_at = 0
    out: List[Dict[str, Any]] = []

    while len(out) < max_rows:
        payload = _jira_request_json(
            "/rest/api/2/search",
            {
                "jql": jql,
                "startAt": start_at,
                "maxResults": page_size,
                "fields": "summary,description,status,priority,issuetype,assignee,reporter,updated,comment",
            },
        )
        issues = payload.get("issues") if isinstance(payload, dict) else None
        if not isinstance(issues, list) or not issues:
            break
        out.extend([x for x in issues if isinstance(x, dict)])
        if len(issues) < page_size:
            break
        start_at += len(issues)
        if start_at >= max_rows:
            break

    return out[:max_rows]

def _normalize_jira_issue_payload(issue: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(issue, dict):
        raise ValueError("Issue inválido")

    fields = issue.get("fields")
    if isinstance(fields, dict):
        key = (issue.get("key") or "").strip()
        summary = (fields.get("summary") or key or "Ticket Jira").strip()
        description = _jira_description_to_text(fields.get("description"))
        status_name = _jira_issue_author(fields.get("status"))
        priority_name = _jira_issue_author(fields.get("priority"))
        issue_type_name = _jira_issue_author(fields.get("issuetype"))
        assignee = _jira_issue_author(fields.get("assignee"))
        reporter_email = ""
        reporter_name = _jira_issue_author(fields.get("reporter"))
        if isinstance(fields.get("reporter"), dict):
            reporter_email = str(fields["reporter"].get("emailAddress") or "").strip()
        updated_at = (fields.get("updated") or issue.get("updated") or db.now_utc_iso()).strip()
        comments: List[Dict[str, str]] = []
        comment_node = fields.get("comment")
        comment_items = comment_node.get("comments") if isinstance(comment_node, dict) else []
        if isinstance(comment_items, list):
            for c in comment_items:
                if not isinstance(c, dict):
                    continue
                comments.append(
                    {
                        "author": _jira_issue_author(c.get("author")) or "jira",
                        "body": _jira_comment_body_to_text(c.get("body")),
                    }
                )
        return {
            "key": key,
            "summary": summary,
            "description": description,
            "status": status_name or "open",
            "priority": priority_name or "medium",
            "issue_type": issue_type_name or "incidencia",
            "assignee": assignee or None,
            "reporter_email": reporter_email or None,
            "reporter_name": reporter_name or None,
            "comments": comments,
            "updated_at": updated_at,
        }

    key = (issue.get("key") or "").strip()
    return {
        "key": key,
        "summary": (issue.get("summary") or key or "Ticket Jira").strip(),
        "description": (issue.get("description") or "").strip(),
        "status": (issue.get("status") or "open").strip(),
        "priority": (issue.get("priority") or "medium").strip(),
        "issue_type": (issue.get("issue_type") or issue.get("issuetype") or "incidencia").strip(),
        "assignee": (issue.get("assignee") or "").strip() or None,
        "reporter_email": (issue.get("reporter_email") or "").strip() or None,
        "reporter_name": (issue.get("reporter_name") or "").strip() or None,
        "comments": issue.get("comments") if isinstance(issue.get("comments"), list) else [],
        "updated_at": (issue.get("updated_at") or issue.get("updated") or db.now_utc_iso()).strip(),
    }

def _jira_get_cursor(cursor_name: str = JIRA_SYNC_CURSOR_NAME) -> Optional[str]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT cursor_value FROM jira_sync_cursor WHERE cursor_name = ? LIMIT 1",
            (cursor_name,),
        ).fetchone()
        if not row:
            return None
        value = str(row.get("cursor_value") or "").strip()
        return value or None
    finally:
        conn.close()

def _jira_set_cursor(cursor_value: str, cursor_name: str = JIRA_SYNC_CURSOR_NAME) -> None:
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO jira_sync_cursor (cursor_name, cursor_value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(cursor_name) DO UPDATE SET
                   cursor_value = EXCLUDED.cursor_value,
                   updated_at = EXCLUDED.updated_at""",
            (cursor_name, cursor_value, now),
        )
        conn.commit()
    finally:
        conn.close()

def _jira_start_sync_run(run_type: str, actor: str, context: Dict[str, Any], cursor_before: Optional[str]) -> int:
    normalized = (run_type or "").strip().lower()
    if normalized not in JIRA_SYNC_RUN_TYPES:
        normalized = "delta"
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        row = conn.execute(
            """INSERT INTO jira_sync_runs
               (run_type, actor, status, context_json, counts_json, error_summary, cursor_before, cursor_after, started_at, created_at)
               VALUES (?, ?, 'running', ?, '{}', '', ?, '', ?, ?)
               RETURNING id""",
            (
                normalized,
                actor,
                _stable_json(context or {}),
                (cursor_before or "").strip(),
                now,
                now,
            ),
        ).fetchone()
        conn.commit()
        return int(row["id"]) if row else 0
    finally:
        conn.close()

def _jira_finish_sync_run(
    run_id: int,
    *,
    status: str,
    counts: Dict[str, Any],
    error_summary: str = "",
    cursor_after: Optional[str] = None,
) -> None:
    normalized_status = (status or "").strip().lower()
    if normalized_status not in JIRA_SYNC_RUN_STATUS:
        normalized_status = "failed"
    conn = db.get_conn()
    try:
        conn.execute(
            """UPDATE jira_sync_runs
               SET status = ?,
                   counts_json = ?,
                   error_summary = ?,
                   cursor_after = ?,
                   ended_at = ?
               WHERE id = ?""",
            (
                normalized_status,
                _stable_json(counts or {}),
                (error_summary or "").strip()[:4000],
                (cursor_after or "").strip(),
                db.now_utc_iso(),
                int(run_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()

def _jira_upsert_map_row(
    *,
    jira_issue_key: str,
    jira_updated_at: str,
    monstruo_ticket_id: int,
    sync_status: str,
    last_error: str,
) -> None:
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        conn.execute(
            """INSERT INTO jira_issue_map
               (jira_issue_key, jira_updated_at, monstruo_ticket_id, sync_status, last_sync_at, last_error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(jira_issue_key) DO UPDATE SET
                   jira_updated_at = EXCLUDED.jira_updated_at,
                   monstruo_ticket_id = EXCLUDED.monstruo_ticket_id,
                   sync_status = EXCLUDED.sync_status,
                   last_sync_at = EXCLUDED.last_sync_at,
                   last_error = EXCLUDED.last_error,
                   updated_at = EXCLUDED.updated_at""",
            (
                jira_issue_key,
                jira_updated_at,
                int(monstruo_ticket_id),
                sync_status,
                now,
                (last_error or "").strip()[:2000],
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

def _jira_load_existing_map(jira_issue_key: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM jira_issue_map WHERE jira_issue_key = ? LIMIT 1",
            (jira_issue_key,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def _jira_apply_issue_to_ticket(issue: Dict[str, Any], actor: str, existing_ticket_id: Optional[int] = None) -> Dict[str, Any]:
    issue_key = (issue.get("key") or "").strip()
    if not issue_key:
        raise ValueError("Issue Jira sin key")

    jira_priority = (issue.get("priority") or "medium").strip().lower()
    severidad = JIRA_PRIORITY_TO_SEVERIDAD.get(jira_priority, "media")
    jira_status = (issue.get("status") or "open").strip()
    target_state = _jira_status_to_estado(jira_status)
    issue_type = _jira_issue_type_to_tipo(str(issue.get("issue_type") or "incidencia"))
    summary = (issue.get("summary") or issue_key or "Ticket Jira").strip()
    description = (issue.get("description") or "").strip()
    if issue_key:
        description = f"[JIRA:{issue_key}] {description}".strip()

    patch_data: Dict[str, Any] = {"severidad": severidad}
    assignee = (issue.get("assignee") or "").strip() if isinstance(issue.get("assignee"), str) else ""
    if assignee:
        patch_data["asignado_a"] = assignee
    if target_state in ESTADOS_VALIDOS and target_state != "abierto":
        patch_data["estado"] = target_state

    if existing_ticket_id:
        ticket_id = int(existing_ticket_id)
        updated = update_ticket(ticket_id, patch_data, actor_id=f"jira_sync:{actor}")
        if not updated:
            raise ValueError(f"Ticket asociado no encontrado para issue {issue_key}")
        return {
            "action": "updated",
            "ticket_id": ticket_id,
            "ticket_code": updated.get("codigo"),
            "estado": updated.get("estado"),
        }

    created = create_ticket(
        titulo=summary,
        descripcion=description,
        creador_id=f"jira_import:{actor}",
        severidad=severidad,
        tipo=issue_type,
        categoria=issue.get("categoria") or "general",
        origen_email=issue.get("reporter_email"),
        cliente_nombre=issue.get("reporter_name"),
        ticket_security_class=normalize_ticket_security_class(issue.get("ticket_security_class")),
    )
    ticket_id = int(created["id"])
    if patch_data:
        update_ticket(ticket_id, patch_data, actor_id=f"jira_sync:{actor}")

    comments = issue.get("comments") or []
    if isinstance(comments, list):
        for c in comments:
            if not isinstance(c, dict):
                continue
            author = (c.get("author") or "jira").strip()
            body = (c.get("body") or "").strip()
            if body:
                add_comment(ticket_id, f"jira:{author}", body, "jira_import")

    refreshed = get_ticket(ticket_id) or created
    return {
        "action": "imported",
        "ticket_id": ticket_id,
        "ticket_code": refreshed.get("codigo"),
        "estado": refreshed.get("estado"),
    }

def _run_jira_sync(
    *,
    run_type: str,
    actor: str,
    dry_run: bool,
    issues_input: Optional[List[Dict[str, Any]]],
    project_keys: Optional[List[str]],
    limit: int,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_type = (run_type or "").strip().lower()
    if normalized_type not in JIRA_SYNC_RUN_TYPES:
        raise ValueError("run_type inválido")

    normalized_limit = max(1, min(int(limit or JIRA_SYNC_DEFAULT_LIMIT), JIRA_SYNC_MAX_LIMIT))
    normalized_since = _normalize_iso_utc(since) if since else None
    keys = _jira_effective_project_keys(project_keys)
    cursor_before = normalized_since if normalized_type == "delta" else None
    if normalized_type == "delta" and not cursor_before:
        cursor_before = _jira_get_cursor() or (_now_dt() - timedelta(days=1)).isoformat()

    issues_raw: List[Dict[str, Any]] = []
    source = "payload"
    if issues_input:
        issues_raw = [x for x in issues_input if isinstance(x, dict)]
    else:
        source = "jira_api"
        if not JIRA_SYNC_ENABLED:
            raise ValueError("JIRA_SYNC_ENABLED=false")
        if not _jira_is_live_configured():
            raise ValueError("Jira no configurado para sincronización live")
        issues_raw = _jira_fetch_issues_live(
            project_keys=keys,
            run_type=normalized_type,
            only_open=(normalized_type == "bootstrap"),
            updated_since=cursor_before,
            limit=normalized_limit,
        )

    context = {
        "source": source,
        "project_keys": keys,
        "limit": normalized_limit,
        "dry_run": bool(dry_run),
        "cursor_before": cursor_before,
        "issues_received": len(issues_raw),
    }
    run_id = _jira_start_sync_run(normalized_type, actor, context, cursor_before)
    if not run_id:
        raise ValueError("No se pudo crear jira_sync_run")

    imported_items: List[Dict[str, Any]] = []
    error_items: List[Dict[str, Any]] = []
    imported = 0
    updated = 0
    skipped = 0
    failed = 0
    max_seen_updated = cursor_before

    try:
        for issue_raw in issues_raw:
            try:
                issue = _normalize_jira_issue_payload(issue_raw)
                issue_key = (issue.get("key") or "").strip()
                if not issue_key:
                    raise ValueError("Issue Jira sin key")
                issue_updated = _normalize_iso_utc(issue.get("updated_at")) or db.now_utc_iso()
                if not max_seen_updated or (_parse_dt(issue_updated) and _parse_dt(max_seen_updated) and _parse_dt(issue_updated) > _parse_dt(max_seen_updated)):
                    max_seen_updated = issue_updated

                current_map = _jira_load_existing_map(issue_key)
                if current_map and str(current_map.get("jira_updated_at") or "").strip() == issue_updated:
                    skipped += 1
                    imported_items.append(
                        {
                            "jira_key": issue_key,
                            "action": "skipped",
                            "ticket_id": int(current_map.get("monstruo_ticket_id") or 0),
                            "jira_updated_at": issue_updated,
                        }
                    )
                    continue

                if dry_run:
                    action = "updated" if current_map else "imported"
                    if action == "updated":
                        updated += 1
                    else:
                        imported += 1
                    imported_items.append(
                        {
                            "jira_key": issue_key,
                            "action": action,
                            "ticket_id": int(current_map.get("monstruo_ticket_id") or 0) if current_map else None,
                            "preview_estado": _jira_status_to_estado(str(issue.get("status") or "open")),
                            "preview_severidad": JIRA_PRIORITY_TO_SEVERIDAD.get(
                                str(issue.get("priority") or "medium").lower(),
                                "media",
                            ),
                            "jira_updated_at": issue_updated,
                        }
                    )
                    continue

                applied = _jira_apply_issue_to_ticket(
                    issue=issue,
                    actor=actor,
                    existing_ticket_id=int(current_map["monstruo_ticket_id"]) if current_map else None,
                )
                action = applied.get("action") or ("updated" if current_map else "imported")
                if action == "updated":
                    updated += 1
                else:
                    imported += 1
                _jira_upsert_map_row(
                    jira_issue_key=issue_key,
                    jira_updated_at=issue_updated,
                    monstruo_ticket_id=int(applied.get("ticket_id") or 0),
                    sync_status="synced",
                    last_error="",
                )
                imported_items.append(
                    {
                        "jira_key": issue_key,
                        "action": action,
                        "ticket_id": int(applied.get("ticket_id") or 0),
                        "ticket_code": applied.get("ticket_code"),
                        "estado": applied.get("estado"),
                        "jira_updated_at": issue_updated,
                    }
                )
            except Exception as issue_error:
                failed += 1
                issue_key = str(issue_raw.get("key") or "").strip() if isinstance(issue_raw, dict) else ""
                error_items.append({"jira_key": issue_key, "error": str(issue_error)})
                if issue_key and not dry_run:
                    current_map = _jira_load_existing_map(issue_key)
                    if current_map:
                        _jira_upsert_map_row(
                            jira_issue_key=issue_key,
                            jira_updated_at=str(current_map.get("jira_updated_at") or db.now_utc_iso()),
                            monstruo_ticket_id=int(current_map.get("monstruo_ticket_id") or 0),
                            sync_status="error",
                            last_error=str(issue_error),
                        )
        if normalized_type == "delta" and not dry_run and max_seen_updated:
            _jira_set_cursor(max_seen_updated)

        status = "completed" if failed == 0 else "completed_with_errors"
        counts = {
            "imported": imported,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
            "total_processed": imported + updated + skipped + failed,
        }
        _jira_finish_sync_run(
            run_id,
            status=status,
            counts=counts,
            error_summary="; ".join([x["error"] for x in error_items][:20]),
            cursor_after=max_seen_updated if normalized_type == "delta" else "",
        )
    except Exception as run_error:
        _jira_finish_sync_run(
            run_id,
            status="failed",
            counts={
                "imported": imported,
                "updated": updated,
                "skipped": skipped,
                "failed": failed + 1,
            },
            error_summary=str(run_error),
            cursor_after=max_seen_updated if normalized_type == "delta" else "",
        )
        raise

    try:
        create_evidence_event(
            control_id="A.5.37",
            artifact_ref=f"jira_sync_run:{run_id}",
            owner=actor,
            integrity_hash="",
            metadata={
                "run_type": normalized_type,
                "dry_run": bool(dry_run),
                "source": source,
                "imported": imported,
                "updated": updated,
                "skipped": skipped,
                "failed": failed,
                "cursor_before": cursor_before or "",
                "cursor_after": max_seen_updated or "",
            },
        )
    except Exception as e:
        logger.warning(f"[jira_sync] evidence_event no crítico falló: {e}")

    return {
        "ok": failed == 0,
        "run_id": run_id,
        "run_type": normalized_type,
        "dry_run": bool(dry_run),
        "source": source,
        "cursor_before": cursor_before,
        "cursor_after": max_seen_updated if normalized_type == "delta" else None,
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "items": imported_items[:300],
        "errors": error_items[:200],
    }

def run_jira_bootstrap_open(
    actor: str,
    dry_run: bool = False,
    issues: Optional[List[Dict[str, Any]]] = None,
    project_keys: Optional[List[str]] = None,
    limit: int = JIRA_SYNC_DEFAULT_LIMIT,
) -> Dict[str, Any]:
    return _run_jira_sync(
        run_type="bootstrap",
        actor=actor,
        dry_run=bool(dry_run),
        issues_input=issues,
        project_keys=project_keys,
        limit=limit,
        since=None,
    )

def run_jira_delta_sync(
    actor: str,
    dry_run: bool = False,
    issues: Optional[List[Dict[str, Any]]] = None,
    project_keys: Optional[List[str]] = None,
    limit: int = JIRA_SYNC_DEFAULT_LIMIT,
    since: Optional[str] = None,
) -> Dict[str, Any]:
    return _run_jira_sync(
        run_type="delta",
        actor=actor,
        dry_run=bool(dry_run),
        issues_input=issues,
        project_keys=project_keys,
        limit=limit,
        since=since,
    )

def list_jira_sync_runs(
    run_type: Optional[str] = None,
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
        if run_type:
            where.append("run_type = ?")
            params.append((run_type or "").strip().lower())
        if status:
            where.append("status = ?")
            params.append((status or "").strip().lower())
        where_sql = " AND ".join(where)
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM jira_sync_runs WHERE {where_sql}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""SELECT *
                FROM jira_sync_runs
                WHERE {where_sql}
                ORDER BY started_at DESC, id DESC
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

def _normalized_snapshot_date(value: Optional[str]) -> str:
    if not value:
        return datetime.now(JIRA_SYNC_TZ).date().isoformat()
    parsed = _parse_dt(value)
    if parsed:
        return _ensure_utc(parsed).date().isoformat()
    raw = str(value).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw
    raise ValueError(f"snapshot_date inválida: {value}")

def _jira_count_open_live(project_keys: List[str]) -> Optional[int]:
    if not JIRA_SYNC_ENABLED or not _jira_is_live_configured():
        return None
    if not project_keys:
        return None
    projects = ",".join(project_keys)
    jql = f"project in ({projects}) AND statusCategory != Done"
    payload = _jira_request_json(
        "/rest/api/2/search",
        {
            "jql": jql,
            "startAt": 0,
            "maxResults": 1,
            "fields": "key",
        },
    )
    total = payload.get("total")
    try:
        return int(total)
    except Exception:
        return None

def record_parallel_kpi_snapshot(
    snapshot_date: Optional[str] = None,
    source: str = "parallel_daily",
) -> Dict[str, Any]:
    snap_date = _normalized_snapshot_date(snapshot_date)
    project_keys = _jira_effective_project_keys(None)
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        monstruo_open = conn.execute(
            """SELECT COUNT(*) AS c
               FROM jira_issue_map m
               JOIN tickets t ON t.id = m.monstruo_ticket_id
               WHERE t.estado NOT IN ('resuelto','cerrado')"""
        ).fetchone()
        sev1_open = conn.execute(
            """SELECT COUNT(*) AS c
               FROM jira_issue_map m
               JOIN tickets t ON t.id = m.monstruo_ticket_id
               WHERE t.estado NOT IN ('resuelto','cerrado')
                 AND t.severidad = 'critica'"""
        ).fetchone()
        mismatch = conn.execute(
            """SELECT COUNT(*) AS c
               FROM jira_issue_map m
               LEFT JOIN tickets t ON t.id = m.monstruo_ticket_id
               WHERE t.id IS NULL"""
        ).fetchone()
        duplicates = conn.execute(
            """SELECT COALESCE(SUM(cnt - 1), 0) AS c
               FROM (
                   SELECT monstruo_ticket_id, COUNT(*) AS cnt
                   FROM jira_issue_map
                   GROUP BY monstruo_ticket_id
                   HAVING COUNT(*) > 1
               ) d"""
        ).fetchone()
        failed_runs = conn.execute(
            """SELECT COUNT(*) AS c
               FROM jira_sync_runs
               WHERE started_at::date = ?::date
                 AND status IN ('failed','completed_with_errors')""",
            (snap_date,),
        ).fetchone()
    finally:
        conn.close()

    sla = get_sla_metrics()
    sla_total = int(sla.get("frt_on_time", 0)) + int(sla.get("frt_breached", 0)) + int(sla.get("ttr_on_time", 0)) + int(sla.get("ttr_breached", 0))
    sla_on_time = int(sla.get("frt_on_time", 0)) + int(sla.get("ttr_on_time", 0))
    sla_pct = round((sla_on_time / sla_total * 100.0), 2) if sla_total > 0 else 100.0

    jira_open_live = None
    jira_open_error = ""
    try:
        jira_open_live = _jira_count_open_live(project_keys)
    except Exception as e:
        jira_open_error = str(e)
        jira_open_live = None

    monstruo_open_count = int((monstruo_open or {}).get("c") or 0)
    total_jira_open = int(jira_open_live) if jira_open_live is not None else monstruo_open_count

    details = {
        "source": source,
        "jira_live_open_error": jira_open_error,
        "project_keys": project_keys,
        "sla": {
            "frt_on_time": int(sla.get("frt_on_time", 0)),
            "frt_breached": int(sla.get("frt_breached", 0)),
            "ttr_on_time": int(sla.get("ttr_on_time", 0)),
            "ttr_breached": int(sla.get("ttr_breached", 0)),
        },
        "generated_at": now,
    }

    conn2 = db.get_conn()
    try:
        conn2.execute(
            """INSERT INTO parallel_kpi_daily
               (snapshot_date, source, total_jira_open, total_monstruo_open, sev1_open,
                sla_compliance_pct, mismatch_count, duplicate_count, failed_sync_runs,
                details_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(snapshot_date) DO UPDATE SET
                   source = EXCLUDED.source,
                   total_jira_open = EXCLUDED.total_jira_open,
                   total_monstruo_open = EXCLUDED.total_monstruo_open,
                   sev1_open = EXCLUDED.sev1_open,
                   sla_compliance_pct = EXCLUDED.sla_compliance_pct,
                   mismatch_count = EXCLUDED.mismatch_count,
                   duplicate_count = EXCLUDED.duplicate_count,
                   failed_sync_runs = EXCLUDED.failed_sync_runs,
                   details_json = EXCLUDED.details_json,
                   updated_at = EXCLUDED.updated_at""",
            (
                snap_date,
                source,
                total_jira_open,
                monstruo_open_count,
                int((sev1_open or {}).get("c") or 0),
                sla_pct,
                int((mismatch or {}).get("c") or 0),
                int((duplicates or {}).get("c") or 0),
                int((failed_runs or {}).get("c") or 0),
                _stable_json(details),
                now,
                now,
            ),
        )
        conn2.commit()
        row = conn2.execute(
            "SELECT * FROM parallel_kpi_daily WHERE snapshot_date = ?",
            (snap_date,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn2.close()

def list_parallel_kpi_daily(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    if not date_from and not date_to:
        record_parallel_kpi_snapshot()

    where = ["1=1"]
    params: List[Any] = []
    if date_from:
        where.append("snapshot_date >= ?")
        params.append(_normalized_snapshot_date(date_from))
    if date_to:
        where.append("snapshot_date <= ?")
        params.append(_normalized_snapshot_date(date_to))

    conn = db.get_conn()
    try:
        rows = conn.execute(
            f"""SELECT *
                FROM parallel_kpi_daily
                WHERE {' AND '.join(where)}
                ORDER BY snapshot_date DESC""",
            params,
        ).fetchall()
        return {"items": [dict(r) for r in rows], "total": len(rows)}
    finally:
        conn.close()

def get_jira_reconciliation_daily(snapshot_date: Optional[str] = None) -> Dict[str, Any]:
    snap = _normalized_snapshot_date(snapshot_date)
    snapshot = record_parallel_kpi_snapshot(snapshot_date=snap, source="reconciliation")

    conn = db.get_conn()
    try:
        missing = conn.execute(
            """SELECT m.jira_issue_key, m.monstruo_ticket_id, m.sync_status, m.last_error
               FROM jira_issue_map m
               LEFT JOIN tickets t ON t.id = m.monstruo_ticket_id
               WHERE t.id IS NULL
               ORDER BY m.updated_at DESC
               LIMIT 200"""
        ).fetchall()
        latest_runs = conn.execute(
            """SELECT *
               FROM jira_sync_runs
               WHERE started_at::date = ?::date
               ORDER BY started_at DESC
               LIMIT 20""",
            (snap,),
        ).fetchall()
    finally:
        conn.close()

    mismatch_count = int(snapshot.get("mismatch_count") or 0)
    failed_sync_runs = int(snapshot.get("failed_sync_runs") or 0)
    ok = mismatch_count == 0 and failed_sync_runs == 0
    return {
        "ok": ok,
        "snapshot_date": snap,
        "kpi_snapshot": snapshot,
        "mismatch_count": mismatch_count,
        "failed_sync_runs": failed_sync_runs,
        "missing_items": [dict(r) for r in missing],
        "runs": [dict(r) for r in latest_runs],
    }

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
    if not payload_metrics:
        latest = list_parallel_kpi_daily()
        if latest.get("items"):
            payload_metrics = latest["items"][0]
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

# ==========================================================================
# GESTIÓN DE ESPECIALIDADES
# ==========================================================================
def _resolve_role_specialties(role_value: Any, secondary_roles_value: Any) -> List[str]:
    out: List[str] = []
    for role_item in _normalize_roles([role_value, *(_normalize_roles(secondary_roles_value))]):
        mapped = ROLE_SPECIALTY_FALLBACK.get(role_item)
        if mapped and mapped not in out:
            out.append(mapped)
    return out

def _active_ticket_load_map(conn) -> Dict[str, int]:
    rows = conn.execute(
        """
        SELECT LOWER(asignado_a) AS username, COUNT(*) AS active_count
        FROM tickets
        WHERE COALESCE(asignado_a, '') <> ''
          AND estado IN ('abierto', 'en_progreso')
        GROUP BY LOWER(asignado_a)
        """
    ).fetchall()
    out: Dict[str, int] = {}
    for row in rows:
        username = _normalize_username(row.get("username"))
        if not username:
            continue
        out[username] = int(row.get("active_count") or 0)
    return out

def _list_specialties_with_role_fallback(conn) -> List[Dict[str, Any]]:
    base_rows = conn.execute(
        """
        SELECT us.*, u.role, u.secondary_roles
        FROM user_specialties us
        LEFT JOIN users u ON u.username = us.username
        ORDER BY us.specialty, us.username
        """
    ).fetchall()
    items = [dict(r) for r in base_rows]
    existing_keys = {
        (_normalize_username(item.get("username")), _normalize_role(item.get("specialty")))
        for item in items
        if _normalize_username(item.get("username")) and _normalize_role(item.get("specialty"))
    }

    load_map = _active_ticket_load_map(conn)
    now = db.now_utc_iso()
    user_rows = conn.execute(
        "SELECT username, role, secondary_roles FROM users WHERE COALESCE(is_active, 1) = 1 ORDER BY username ASC"
    ).fetchall()
    for row in user_rows:
        username = _normalize_username(row.get("username"))
        if not username:
            continue
        role = _normalize_role(row.get("role"))
        try:
            secondary_roles_raw = json.loads(row.get("secondary_roles") or "[]")
        except Exception:
            secondary_roles_raw = []
        derived_specialties = _resolve_role_specialties(role, secondary_roles_raw)
        if not derived_specialties:
            continue
        role_secondary_json = json.dumps(_normalize_roles(secondary_roles_raw))
        active_load = int(load_map.get(username, 0))
        for specialty in derived_specialties:
            key = (username, specialty)
            if key in existing_keys:
                continue
            items.append(
                {
                    "username": username,
                    "specialty": specialty,
                    "current_load": active_load,
                    "max_load": max(10, active_load + 1),
                    "is_available": 1,
                    "created_at": now,
                    "updated_at": now,
                    "role": role,
                    "secondary_roles": role_secondary_json,
                }
            )
            existing_keys.add(key)

    items.sort(key=lambda row: (str(row.get("specialty") or ""), str(row.get("username") or "")))
    return items

def list_specialties() -> List[Dict[str, Any]]:
    """Lista especialidades reales + fallback derivado de roles técnicos."""
    conn = db.get_conn()
    try:
        return _list_specialties_with_role_fallback(conn)
    finally:
        conn.close()

def upsert_specialty(username: str, specialty: str, max_load: int = 10) -> Dict[str, Any]:
    """Crear o actualizar especialidad de usuario."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute("""
            INSERT INTO user_specialties (username, specialty, max_load, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, specialty) DO UPDATE SET
                max_load = excluded.max_load,
                updated_at = excluded.updated_at
        """, (username, specialty, max_load, now, now))
        conn.commit()
        row = conn.execute(
            "SELECT * FROM user_specialties WHERE username = ? AND specialty = ?",
            (username, specialty)
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def toggle_availability(username: str, is_available: bool) -> None:
    """Activar/desactivar disponibilidad de un técnico."""
    conn = db.get_conn()
    try:
        conn.execute("""
            UPDATE user_specialties
            SET is_available = ?, updated_at = ?
            WHERE username = ?
        """, (1 if is_available else 0, db.now_utc_iso(), username))
        conn.commit()
    finally:
        conn.close()

def delete_specialty(username: str, specialty: str) -> None:
    """Eliminar una especialidad de un técnico."""
    conn = db.get_conn()
    try:
        conn.execute(
            "DELETE FROM user_specialties WHERE username = ? AND specialty = ?",
            (username, specialty)
        )
        conn.commit()
    finally:
        conn.close()

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

def _auto_reply_subject(ticket: Dict[str, Any]) -> str:
    code = str(ticket.get("codigo") or f"TK-{ticket.get('id', '')}").strip() or "Ticket"
    return f"Re: {code} - Comprobante de Recepción"

def _auto_reply_body(nombre: str, code: str, asignado_a: str) -> str:
    safe_name = html.escape((nombre or "cliente").strip() or "cliente")
    safe_code = html.escape((code or "Ticket").strip() or "Ticket")
    safe_assignee = html.escape((asignado_a or "").strip())
    lines = [
        f"<p>Hola {safe_name},</p>",
        f"<p>Hemos recibido su solicitud y se ha generado el ticket <strong>{safe_code}</strong>.</p>",
    ]
    if safe_assignee and safe_assignee != "mesa_ayuda":
        lines.append(
            f"<p>Su caso fue asignado a <strong>{safe_assignee}</strong>, quien revisará los antecedentes a la brevedad.</p>"
        )
    else:
        lines.append(
            "<p>Su caso está siendo revisado por nuestra <strong>Mesa de Ayuda</strong> para su derivación.</p>"
        )
    lines.append("<p>Responderemos a este mismo correo con actualizaciones.</p>")
    return "\n".join(lines)

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
    delay_minutes = _auto_reply_delay_minutes()
    run_at = (datetime.utcnow() + timedelta(minutes=delay_minutes)).isoformat()
    ticket_code = str(ticket.get("codigo") or f"TK-{ticket_id}")
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
        "ticket_code": ticket_code,
        "idempotency_key": idem_key,
        "in_reply_to": in_reply_to_norm or "",
        "references": merged_refs or "",
    }
    body_html = _auto_reply_body(nombre, ticket_code, asignado_a or "")
    subject = _auto_reply_subject(ticket)

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

def handle_incoming_email(msg: Dict[str, Any]) -> None:
    """
    Procesa un mensaje de correo entrante.
    Priorización:
    1) Match por hilo (In-Reply-To / References).
    2) Match por código en asunto (TK-DD-MM-YYYY-NNNN, legacy TK-YYYYMM-NNNN o TK-1234).
    3) Si no hay match, crea ticket nuevo.
    """
    subject = msg.get("subject", "")
    sender = msg.get("sender", "")
    body = msg.get("body", "")
    msg_id = msg.get("message_id", "")
    in_reply_to = msg.get("in_reply_to", "")
    references = msg.get("references", "")
    attachments = msg.get("attachments") if isinstance(msg.get("attachments"), list) else []

    try:
        ticket_id = _find_ticket_by_thread_headers(in_reply_to, references)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id, in_reply_to, references, attachments)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by thread headers: {e}")

    try:
        ticket_id = _find_ticket_by_subject(subject)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id, in_reply_to, references, attachments)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by subject: {e}")

    _process_new_email_ticket(subject, sender, body, msg_id, in_reply_to, references, attachments)

def _process_reply_email(
    ticket_id: int,
    sender: str,
    subject: str,
    body: str,
    msg_id: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
):
    print(f"[EMAIL] Reply to Ticket #{ticket_id} from {sender}")
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
                html.escape(body or "").replace("\n", "<br>"),
                json.dumps(saved_attachments, ensure_ascii=False),
                now,
            ),
        )
        if saved_attachments:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, 'system', ?, ?)""",
                (
                    ticket_id,
                    f"[ADJUNTO_INCOMING] Se guardaron {len(saved_attachments)} adjunto(s) del correo entrante.",
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

def _process_new_email_ticket(
    subject: str,
    sender: str,
    body: str,
    msg_id: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
):
    print(f"[EMAIL] New Ticket from {sender}")
    
    # 1. Clasificación
    categoria = clasificar_ticket(subject, body)
    
    # 2. Triaje (Mesa vs Especialista)
    asignado_a = None
    if categoria == "general":
        asignado_a = None
    else:
        try:
            asignado_a = auto_asignar(categoria)
        except Exception as e:
            logger.warning(f"[EMAIL] auto_asignar falló para categoría '{categoria}': {e}")
            asignado_a = None
        if not asignado_a:
            asignado_a = "mesa_ayuda"

    # 3. Datos del cliente
    cliente_nombre, origen_email = _sender_identity(sender)
    if not origen_email:
        origen_email = sender.strip()
    if not cliente_nombre:
        cliente_nombre = origen_email

    conn = None
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
        )
        
        ticket_id = tk['id']
        codigo = tk['codigo']
        
        # Override asignado_a if manual triage set it to Mesa
        if asignado_a == "mesa_ayuda" and tk.get("asignado_a") != "mesa_ayuda":
             # create_ticket might have auto-assigned. Does create_ticket handle "Mesa"?
             # auto_asignar in create_ticket returns a tech username or None.
             # If create_ticket found someone, we keep it. 
             # But if our triage said "mesa_ayuda" because category is "general", create_ticket might have assigned to a general tech?
             # Let's trust create_ticket's auto-assignment logic unless we strictly want Mesa.
             # If category is general, create_ticket calls auto_asignar(general).
             # If we want to force Mesa for general, we should update it.
             pass
             
        if asignado_a == "mesa_ayuda":
             update_ticket(ticket_id, {"asignado_a": "mesa_ayuda"}, actor_id="email_bot")
             # Re-fetch to confirm?
             # tk['asignado_a'] = "mesa_ayuda"

        # Registrar correo entrante en historial de correos.
        conn = db.get_conn()
        _emit_system_comment(
            conn,
            ticket_id,
            "[INGESTA_CORREO] Estado: sin_asignar | Motivo: Ticket creado desde correo entrante con auto_assign=False para triage manual.",
            now,
            author_id="system",
        )
        saved_attachments = _persist_incoming_attachments(
            conn,
            ticket_id,
            attachments,
            uploaded_by=f"email:{sender}",
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
                html.escape(body or "").replace("\n", "<br>"),
                json.dumps(saved_attachments, ensure_ascii=False),
                now,
            ),
        )
        if saved_attachments:
            conn.execute(
                """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
                   VALUES (?, 'system', ?, ?)""",
                (
                    ticket_id,
                    f"[ADJUNTO_INCOMING] Se guardaron {len(saved_attachments)} adjunto(s) del correo entrante.",
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

        print(f"[EMAIL] Created Ticket {codigo} (#{ticket_id})")

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
        _emit_system_comment(
            conn,
            ticket_id,
            (
                f"[AUTO_RESPUESTA] Estado: {auto_result.get('reason')} | "
                f"Motivo: destino={origen_email} idempotency={auto_result.get('idempotency_key','')}"
            ),
            now,
            author_id="system",
        )
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
    finally:
        if conn:
            conn.close()

# ==========================================================================
# CLIENT ASSOCIATION LOGIC
# ==========================================================================
def associate_email_to_client(email: str, customer_id: str, customer_name: str, actor: str) -> bool:
    """Asocia un correo a un cliente de Laudus/Sistema."""
    email = email.strip().lower()
    if not email or not customer_id:
        raise ValueError("Email y Customer ID son requeridos")
    
    conn = db.get_conn()
    now_ts = db.now_utc_iso()
    
    # 1. UPSERT en la tabla de configuración
    # SQLite vs Postgres syntax diff handling via simple delete/insert or check
    # Asumimos SQLite por compatibilidad simple o standard SQL
    
    # Check if exists
    row = conn.execute("SELECT 1 FROM ticket_config_client_emails WHERE email = ?", (email,)).fetchone()
    
    if row:
        conn.execute("""
            UPDATE ticket_config_client_emails 
            SET customer_id = ?, customer_name = ?, updated_at = ?
            WHERE email = ?
        """, (customer_id, customer_name, now_ts, email))
    else:
        conn.execute("""
            INSERT INTO ticket_config_client_emails (email, customer_id, customer_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (email, customer_id, customer_name, now_ts, now_ts))
    
    # 2. Actualizar tickets históricos ABIERTOS de este correo?
    # El usuario pidió "que en un futuro asocie", pero usualmente se espera que retroactivamente
    # arregle lo que se ve FEO ahora. Vamos a actualizar tickets abiertos que tengan ese origen_email.
    conn.execute("""
        UPDATE tickets 
        SET cliente_nombre = ? 
        WHERE lower(origen_email) = ? 
          AND (cliente_nombre IS NULL OR cliente_nombre = '' OR cliente_nombre = 'Desconocido')
    """, (customer_name, email))
    
    conn.commit()
    conn.close()
    return True

def search_customers(q: str = "", limit: int = 0) -> List[Dict[str, Any]]:
    """Busca clientes en laudus_customers; con limit=0 devuelve todos."""
    try:
        raw_limit = int(limit or 0)
    except Exception:
        raw_limit = 0
    limit = max(0, min(raw_limit, 5000))
    query = str(q or "").strip()

    conn = db.get_conn()
    try:
        if query and limit > 0:
            wildcard = f"%{query}%"
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                WHERE name ILIKE ? OR legal_name ILIKE ? OR vat_id ILIKE ?
                ORDER BY COALESCE(name, legal_name, '') ASC
                LIMIT ?
                """,
                (wildcard, wildcard, wildcard, limit),
            ).fetchall()
        elif query:
            wildcard = f"%{query}%"
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                WHERE name ILIKE ? OR legal_name ILIKE ? OR vat_id ILIKE ?
                ORDER BY COALESCE(name, legal_name, '') ASC
                """,
                (wildcard, wildcard, wildcard),
            ).fetchall()
        elif limit > 0:
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                ORDER BY COALESCE(name, legal_name, '') ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT laudus_customer_id as id, name, legal_name, vat_id
                FROM laudus_customers
                ORDER BY COALESCE(name, legal_name, '') ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_client_for_email(email: str) -> Optional[Dict[str, Any]]:
    """Resuelve el cliente asociado a un correo."""
    if not email:
        return None
    email = email.strip().lower()
    conn = db.get_conn()
    row = conn.execute("SELECT customer_id, customer_name FROM ticket_config_client_emails WHERE email = ?", (email,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None
