"""
Ticketera V3 — Servicio profesional de Mesa de Ayuda.
Auto-clasificación, auto-asignación, notificaciones escalonadas, SLA.
"""
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
from urllib import request as urlrequest
from urllib import error as urlerror
from plataforma.core import email_integration, email as email_sender, jobs_engine
from plataforma.core.config import settings as app_settings
from tickets import roles as ticket_roles
from tickets import workflow as ticket_workflow

logger = logging.getLogger(__name__)

# ==========================================================================
# CONSTANTES
# ==========================================================================
CATEGORIAS_VALIDAS = {"redes", "sistemas", "ejecucion", "admin", "general"}
ESTADOS_VALIDOS = {"abierto", "en_progreso", "resuelto", "cerrado"}
MAIN_STATUS_SEQUENCE = ("abierto", "en_progreso", "resuelto", "cerrado")
SEVERIDADES_VALIDAS = {"baja", "media", "alta", "critica"}
ROLES_TECNICOS = ticket_roles.ROLES_TECNICOS
ROLES_TECNICOS_SET = ticket_roles.ROLES_TECNICOS_SET
ROLES_ADMIN_GESTION = ticket_roles.ROLES_ADMIN_GESTION
ROLES_DESPACHO_MESA = ticket_roles.ROLES_DESPACHO_MESA
HELPDESK_MANAGER_ROLE = "encargado_mesa"
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

AUTO_REPLY_SLA_MINUTES = 30
ASSIGNMENT_SLA_MINUTES = 60
RESOLUTION_SLA_MINUTES = 150
SLA_STORAGE_HOURS = 3

SLA_HORAS = {
    "baja": SLA_STORAGE_HOURS,
    "media": SLA_STORAGE_HOURS,
    "alta": SLA_STORAGE_HOURS,
    "critica": SLA_STORAGE_HOURS,
}

PRIORIDAD_MAP = {
    "critica": 1,
    "alta": 2,
    "media": 3,
    "baja": 4,
}

FRT_MINUTOS = {
    "critica": ASSIGNMENT_SLA_MINUTES,
    "alta": ASSIGNMENT_SLA_MINUTES,
    "media": ASSIGNMENT_SLA_MINUTES,
    "baja": ASSIGNMENT_SLA_MINUTES,
}

TTR_MINUTOS = {
    "critica": RESOLUTION_SLA_MINUTES,
    "alta": RESOLUTION_SLA_MINUTES,
    "media": RESOLUTION_SLA_MINUTES,
    "baja": RESOLUTION_SLA_MINUTES,
}

TICKET_PUBLIC_CODE_START = max(1, int(getattr(app_settings, "TICKET_PUBLIC_CODE_START", 2154) or 2154))

CHAIN_ALGO = "sha256"
CHAIN_VERSION = 1
EMAIL_DRAFT_LOCK_MINUTES = 5
EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS = 60
# "cerrado" -> Bloqueo total (ReadOnly)
# El correo al cliente se permite mientras el ticket siga activo.
TICKET_READONLY_ESTADOS = {"cerrado"}
TICKET_EMAIL_ALLOWED_ESTADOS = {"abierto", "en_progreso"}
TICKET_EMAIL_BLOCKED_ESTADOS = set(ESTADOS_VALIDOS) - TICKET_EMAIL_ALLOWED_ESTADOS
REPLY_BLOCKED_ESTADOS = TICKET_EMAIL_BLOCKED_ESTADOS  # Alias legacy
INCOMING_EMAIL_ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "code", "div", "em", "hr", "i",
    "img", "li", "ol", "p", "pre", "span", "strong", "table", "tbody",
    "td", "th", "thead", "tr", "u", "ul",
}
INCOMING_EMAIL_VOID_TAGS = {"br", "hr", "img"}
INCOMING_EMAIL_DROP_TAGS = {
    "base", "button", "embed", "form", "iframe", "input", "link", "math",
    "meta", "object", "script", "select", "style", "svg", "textarea",
}
INCOMING_EMAIL_ALLOWED_ATTRS = {
    "*": {"align", "dir", "title"},
    "a": {"href", "title"},
    "img": {"alt", "height", "src", "title", "width"},
    "table": {"border", "cellpadding", "cellspacing"},
    "tbody": set(),
    "td": {"align", "colspan", "rowspan", "valign"},
    "th": {"align", "colspan", "rowspan", "valign"},
    "thead": set(),
    "tr": {"align", "valign"},
}

class ConflictError(Exception):
    """Conflicto de concurrencia (lock/version) para borradores de correo."""


class _IncomingEmailHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._emit_tag(tag, attrs, closing=False)

    def handle_startendtag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self._emit_tag(tag, attrs, closing=True)

    def handle_endtag(self, tag: str) -> None:
        normalized = str(tag or "").strip().lower()
        if not normalized:
            return
        if self._drop_depth:
            if normalized in INCOMING_EMAIL_DROP_TAGS:
                self._drop_depth = max(0, self._drop_depth - 1)
            return
        if normalized in INCOMING_EMAIL_ALLOWED_TAGS and normalized not in INCOMING_EMAIL_VOID_TAGS:
            self.parts.append(f"</{normalized}>")

    def handle_data(self, data: str) -> None:
        if self._drop_depth or not data:
            return
        self.parts.append(html.escape(data))

    def handle_comment(self, data: str) -> None:
        return

    def get_html(self) -> str:
        return "".join(self.parts)

    def _emit_tag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
        *,
        closing: bool,
    ) -> None:
        normalized = str(tag or "").strip().lower()
        if not normalized:
            return
        if self._drop_depth:
            if normalized in INCOMING_EMAIL_DROP_TAGS and not closing:
                self._drop_depth += 1
            return
        if normalized in INCOMING_EMAIL_DROP_TAGS:
            self._drop_depth = 1
            return
        if normalized not in INCOMING_EMAIL_ALLOWED_TAGS:
            return

        cleaned_attrs: List[Tuple[str, str]] = []
        allowed_attrs = set(INCOMING_EMAIL_ALLOWED_ATTRS.get("*", set()))
        allowed_attrs.update(INCOMING_EMAIL_ALLOWED_ATTRS.get(normalized, set()))
        for raw_name, raw_value in attrs:
            name = str(raw_name or "").strip().lower()
            if not name or name.startswith("on") or name not in allowed_attrs:
                continue
            value = _sanitize_incoming_email_attr(normalized, name, raw_value)
            if value is None or value == "":
                continue
            cleaned_attrs.append((name, value))

        if normalized == "a" and any(name == "href" for name, _ in cleaned_attrs):
            cleaned_attrs.append(("rel", "noopener noreferrer nofollow"))
            cleaned_attrs.append(("target", "_blank"))
        if normalized == "img" and not any(name == "src" for name, _ in cleaned_attrs):
            return

        attrs_html = "".join(
            f' {name}="{html.escape(value, quote=True)}"' for name, value in cleaned_attrs
        )
        if normalized in INCOMING_EMAIL_VOID_TAGS:
            self.parts.append(f"<{normalized}{attrs_html}>")
            return
        if closing:
            self.parts.append(f"<{normalized}{attrs_html}></{normalized}>")
            return
        self.parts.append(f"<{normalized}{attrs_html}>")

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
    return str(Path(__file__).resolve().parent / "data" / "compliance")

def _default_ticket_attachments_dir() -> str:
    return str(Path(__file__).resolve().parent / "data" / "tickets")

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
EMAIL_ROUTE_MATCH_TYPES = {"email", "domain"}
AUTO_REPLY_SUBJECT_SETTING_KEY = "ticket_auto_reply_subject_template"
AUTO_REPLY_BODY_SETTING_KEY = "ticket_auto_reply_body_template"
HELPDESK_NEW_TICKET_SUBJECT_SETTING_KEY = "ticket_helpdesk_new_ticket_subject_template"
HELPDESK_NEW_TICKET_BODY_SETTING_KEY = "ticket_helpdesk_new_ticket_body_template"
CLIENT_ASSIGNMENT_SUBJECT_SETTING_KEY = "ticket_client_assignment_subject_template"
CLIENT_ASSIGNMENT_BODY_SETTING_KEY = "ticket_client_assignment_body_template"
SPECIALIST_ASSIGNMENT_SUBJECT_SETTING_KEY = "ticket_specialist_assignment_subject_template"
SPECIALIST_ASSIGNMENT_BODY_SETTING_KEY = "ticket_specialist_assignment_body_template"
RESOLUTION_SUBJECT_SETTING_KEY = "ticket_resolution_subject_template"
RESOLUTION_BODY_SETTING_KEY = "ticket_resolution_body_template"
MAIL_TEMPLATE_KEY_AUTO_REPLY = "auto_reply"
MAIL_TEMPLATE_KEY_HELPDESK_NEW_TICKET = "helpdesk_new_ticket"
MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT = "client_assignment"
MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT = "specialist_assignment"
MAIL_TEMPLATE_KEY_RESOLUTION = "ticket_resolution"
DEFAULT_REPLY_SUBJECT_TEMPLATE = "Re: [{{ticket_code}}] {{ticket_title}}"
DEFAULT_AUTO_REPLY_BODY_TEMPLATE = (
    "Estimado Cliente,\n\n"
    "Hemos recibido su solicitud y se ha generado el ticket {{ticket_code}}.\n"
    "Su caso quedó a la espera de la asignación a un especialista.\n\n"
    "Saludos."
)
DEFAULT_HELPDESK_NEW_TICKET_SUBJECT_TEMPLATE = "Nuevo TK en Mesa: {{ticket_code}}"
DEFAULT_HELPDESK_NEW_TICKET_BODY_TEMPLATE = (
    "Hola,\n\n"
    "Ha ingresado un nuevo ticket en la mesa de ayuda:\n"
    "Ticket: {{ticket_code}}\n"
    "Titulo: {{ticket_title}}\n"
    "Categoria: {{ticket_category}}\n"
    "Severidad: {{ticket_severity}}\n"
    "Cliente: {{customer_name}}\n"
    "Correo de contacto: {{customer_email}}\n"
    "Asignado a: {{ticket_assignee}}\n"
    "SLA comprometido: {{sla_summary}}\n\n"
    "Puedes revisarlo en la ticketera.\n\n"
    "Saludos."
)
DEFAULT_CLIENT_ASSIGNMENT_BODY_TEMPLATE = (
    "Estimado Cliente,\n\n"
    "Su ticket {{ticket_code}} se ha asignado al especialista {{assignee_name}}.\n\n"
    "Saludos."
)
DEFAULT_SPECIALIST_ASSIGNMENT_SUBJECT_TEMPLATE = "Nuevo Ticket Asignado: {{ticket_code}}"
DEFAULT_SPECIALIST_ASSIGNMENT_BODY_TEMPLATE = (
    "Hola,\n\n"
    "Se te ha asignado un nuevo ticket en la ticketera:\n"
    "Ticket: {{ticket_code}}\n"
    "Titulo: {{ticket_title}}\n"
    "SLA comprometido: {{sla_summary}}\n\n"
    "Puedes revisarlo en el sistema.\n\n"
    "Saludos."
)
DEFAULT_RESOLUTION_BODY_TEMPLATE = (
    "Estimado Cliente,\n\n"
    "Le informamos que su ticket {{ticket_code}} ya esta listo y ha sido marcado como RESUELTO.\n"
    "Si no recibimos comentarios adicionales de su parte en las proximas {{auto_close_hours}} horas, el ticket se cerrara automaticamente.\n\n"
    "Gracias por su preferencia.\n"
    "Saludos."
)
TICKETERA_MAIL_TEMPLATE_DEFS: Dict[str, Dict[str, str]] = {
    MAIL_TEMPLATE_KEY_AUTO_REPLY: {
        "key": MAIL_TEMPLATE_KEY_AUTO_REPLY,
        "label": "Auto-respuesta",
        "description": "Acuse automatico al cliente cuando entra un ticket por correo.",
        "subject_setting_key": AUTO_REPLY_SUBJECT_SETTING_KEY,
        "body_setting_key": AUTO_REPLY_BODY_SETTING_KEY,
        "default_subject_template": DEFAULT_REPLY_SUBJECT_TEMPLATE,
        "default_body_template": DEFAULT_AUTO_REPLY_BODY_TEMPLATE,
        "default_subject_fallback_label": "Comprobante de Recepcion",
    },
    MAIL_TEMPLATE_KEY_HELPDESK_NEW_TICKET: {
        "key": MAIL_TEMPLATE_KEY_HELPDESK_NEW_TICKET,
        "label": "Aviso nuevo TK mesa",
        "description": "Correo al encargado de mesa cuando ingresa un ticket nuevo.",
        "subject_setting_key": HELPDESK_NEW_TICKET_SUBJECT_SETTING_KEY,
        "body_setting_key": HELPDESK_NEW_TICKET_BODY_SETTING_KEY,
        "default_subject_template": DEFAULT_HELPDESK_NEW_TICKET_SUBJECT_TEMPLATE,
        "default_body_template": DEFAULT_HELPDESK_NEW_TICKET_BODY_TEMPLATE,
        "default_subject_fallback_label": "Nuevo Ticket",
    },
    MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT: {
        "key": MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT,
        "label": "Asignacion de especialista",
        "description": "Correo al cliente cuando su ticket queda asignado.",
        "subject_setting_key": CLIENT_ASSIGNMENT_SUBJECT_SETTING_KEY,
        "body_setting_key": CLIENT_ASSIGNMENT_BODY_SETTING_KEY,
        "default_subject_template": DEFAULT_REPLY_SUBJECT_TEMPLATE,
        "default_body_template": DEFAULT_CLIENT_ASSIGNMENT_BODY_TEMPLATE,
        "default_subject_fallback_label": "Asignacion de Especialista",
    },
    MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT: {
        "key": MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT,
        "label": "Notificacion de especialista",
        "description": "Correo al tecnico/especialista cuando se le asigna un ticket.",
        "subject_setting_key": SPECIALIST_ASSIGNMENT_SUBJECT_SETTING_KEY,
        "body_setting_key": SPECIALIST_ASSIGNMENT_BODY_SETTING_KEY,
        "default_subject_template": DEFAULT_SPECIALIST_ASSIGNMENT_SUBJECT_TEMPLATE,
        "default_body_template": DEFAULT_SPECIALIST_ASSIGNMENT_BODY_TEMPLATE,
        "default_subject_fallback_label": "",
    },
    MAIL_TEMPLATE_KEY_RESOLUTION: {
        "key": MAIL_TEMPLATE_KEY_RESOLUTION,
        "label": "Cierre de TK",
        "description": "Correo al cliente cuando el ticket queda resuelto y empieza el conteo de auto-cierre.",
        "subject_setting_key": RESOLUTION_SUBJECT_SETTING_KEY,
        "body_setting_key": RESOLUTION_BODY_SETTING_KEY,
        "default_subject_template": DEFAULT_REPLY_SUBJECT_TEMPLATE,
        "default_body_template": DEFAULT_RESOLUTION_BODY_TEMPLATE,
        "default_subject_fallback_label": "Ticket Resuelto",
    },
}

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

def _extract_email_domain(raw_email: Optional[str]) -> str:
    normalized = _normalize_email_address(raw_email)
    if "@" not in normalized:
        return ""
    return normalized.split("@", 1)[1].strip().lower()

def _normalize_email_route_match_value(match_type: str, match_value: Any) -> str:
    normalized_type = str(match_type or "").strip().lower()
    raw_value = str(match_value or "").strip().lower()
    if normalized_type == "email":
        return _normalize_email_address(raw_value)
    if normalized_type == "domain":
        if "@" in raw_value:
            raw_value = raw_value.split("@", 1)[1]
        raw_value = raw_value.lstrip("@").strip().lower()
        if not raw_value:
            return ""
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
        if any(ch not in allowed for ch in raw_value):
            return ""
        if "." not in raw_value:
            return ""
        return raw_value
    return ""

def _get_system_setting(conn, key: str, default_value: str = "") -> str:
    row = conn.execute("SELECT value FROM system_settings WHERE key = ?", ((key or "").strip(),)).fetchone()
    value = None
    if row:
        if isinstance(row, dict):
            value = row.get("value")
        else:
            try:
                value = row["value"]
            except Exception:
                getter = getattr(row, "get", None)
                if callable(getter):
                    try:
                        value = getter("value")
                    except Exception:
                        value = None
    if value in (None, ""):
        return default_value
    if not isinstance(value, (str, int, float, bool)):
        return default_value
    return str(value)

def _upsert_system_setting(
    conn,
    key: str,
    value: Any,
    *,
    group_name: str = "ticketera",
    is_sensitive: bool = False,
    now_iso: Optional[str] = None,
) -> None:
    now_iso = now_iso or db.now_utc_iso()
    conn.execute(
        """INSERT INTO system_settings (key, value, group_name, is_sensitive, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
               value = EXCLUDED.value,
               group_name = EXCLUDED.group_name,
               is_sensitive = EXCLUDED.is_sensitive,
               updated_at = EXCLUDED.updated_at""",
        (
            str(key or "").strip(),
            str(value or ""),
            str(group_name or "ticketera").strip() or "ticketera",
            bool(is_sensitive),
            now_iso,
        ),
    )

def _sender_identity(sender: str) -> tuple[str, str]:
    name, addr = parseaddr(str(sender or ""))
    email_addr = _normalize_email_address(addr or sender)
    display_name = (name or "").strip() or (email_addr or str(sender or "").strip())
    return display_name, email_addr

def _format_sla_minutes_label(total_minutes: Any) -> str:
    safe_minutes = max(0, int(float(total_minutes or 0)))
    if safe_minutes == 60:
        return "1 hora"
    if safe_minutes % 60 == 0 and safe_minutes >= 120:
        hours = safe_minutes // 60
        return f"{hours} horas"
    if safe_minutes < 60:
        return f"{safe_minutes} minutos"
    hours = safe_minutes / 60.0
    return f"{hours:.1f}".rstrip("0").rstrip(".") + " horas"

def _ticket_sla_summary_label() -> str:
    return (
        f"auto-respuesta {_format_sla_minutes_label(AUTO_REPLY_SLA_MINUTES)}, "
        f"asignación {_format_sla_minutes_label(ASSIGNMENT_SLA_MINUTES)} y "
        f"resolución {_format_sla_minutes_label(RESOLUTION_SLA_MINUTES)}"
    )

def _auto_reply_delay_minutes(conn=None) -> int:
    db_value = None
    if conn is not None:
        try:
            row = conn.execute("SELECT value FROM system_settings WHERE key = 'ticket_auto_reply_time'").fetchone()
            if row and row.get("value") not in (None, ""):
                db_value = row.get("value")
        except Exception:
            db_value = None

    source_value = db_value if db_value is not None else getattr(app_settings, "TICKET_AUTO_REPLY_DELAY_MINUTES", AUTO_REPLY_SLA_MINUTES)
    return _clamp_int(
        source_value,
        default_value=AUTO_REPLY_SLA_MINUTES,
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
        # En runtime DEV permitir auto-respuesta inmediata si no hay allowlist cargada.
        return True, "allowed_no_allowlist"

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

def _parse_secondary_roles_value(value: Optional[Any]) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return _normalize_roles(value)
    try:
        parsed = json.loads(value or "[]")
    except Exception:
        parsed = value
    return _normalize_roles(parsed)

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

def _db_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "si", "sí"}

def _ticket_is_trashed(ticket: Optional[Dict[str, Any]]) -> bool:
    return _db_bool((ticket or {}).get("is_trashed"))

def _ticket_display_status(ticket: Optional[Dict[str, Any]]) -> str:
    if _ticket_is_trashed(ticket):
        return "papelera"
    return str((ticket or {}).get("estado") or "").strip().lower()

def _is_readonly_blocked_by_estado(ticket: Dict[str, Any]) -> bool:
    estado = str(ticket.get("estado") or "").strip().lower()
    return estado in TICKET_READONLY_ESTADOS

def _ensure_ticket_not_trashed(ticket: Dict[str, Any], action_label: str) -> None:
    if not _ticket_is_trashed(ticket):
        return
    raise ValueError(
        f"El ticket está en papelera. Restáuralo antes de {action_label}."
    )

def _ensure_reply_allowed_estado(ticket: Dict[str, Any], action_label: str) -> None:
    _ensure_ticket_not_trashed(ticket, action_label)
    if _is_reply_blocked_by_estado(ticket):
        estado = str(ticket.get("estado") or "").strip().lower() or "-"
        raise ValueError(
            f"No se puede {action_label} cuando el ticket está en estado '{estado}'. "
            "Solo está permitido en 'abierto' o 'en_progreso'."
        )

def _ensure_can_manage_ticket_trash(
    ticket: Dict[str, Any],
    actor_id: str,
    actor_role: Optional[Any],
    action_label: str,
) -> None:
    if not _scope_enforced(actor_role):
        return
    if _is_admin_management_role(actor_role):
        return
    raise PermissionError(
        f"Solo admin o encargado de mesa puede {action_label}."
    )

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

def _render_text_template(template: Any, context: Dict[str, Any]) -> str:
    rendered = str(template or "")
    safe_context = {str(key): str(value or "") for key, value in (context or {}).items()}
    for key, value in safe_context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered

def _format_assignee_name(raw: str) -> str:
    val = (raw or "").strip()
    if not val or val.lower() == "sin asignar":
        return "Sin asignar"
    if "@" in val:
        local_part = val.split("@")[0]
        # Ej: juan.lopez -> Juan Lopez
        name_parts = local_part.replace(".", " ").replace("-", " ").replace("_", " ").split()
        return " ".join(p.capitalize() for p in name_parts)
    return val.capitalize()

def _ticketera_template_context(
    *,
    ticket: Dict[str, Any],
    customer_name: str = "",
    assignee_name: str = "",
    auto_close_hours: Any = "",
) -> Dict[str, str]:
    ticket_id = int(ticket.get("id") or 0)
    raw_assignee = str(assignee_name or ticket.get("asignado_a") or "").strip()
    formatted_assignee = _format_assignee_name(raw_assignee) if raw_assignee else "Sin asignar"
    return {
        "customer_name": str(customer_name or ticket.get("cliente_nombre") or "Cliente").strip() or "Cliente",
        "customer_email": _extract_ticket_target_email(ticket) or "-",
        "ticket_code": str(ticket.get("codigo") or generar_codigo(ticket_id) or "Ticket").strip() or "Ticket",
        "ticket_title": str(ticket.get("titulo") or "").strip(),
        "ticket_category": str(ticket.get("categoria") or "general").strip() or "general",
        "ticket_severity": str(ticket.get("severidad") or "-").strip() or "-",
        "ticket_assignee": formatted_assignee,
        "assignee_name": formatted_assignee,
        "auto_close_hours": str(auto_close_hours or "").strip(),
        "auto_reply_sla": _format_sla_minutes_label(AUTO_REPLY_SLA_MINUTES),
        "assignment_sla": _format_sla_minutes_label(ASSIGNMENT_SLA_MINUTES),
        "resolution_sla": _format_sla_minutes_label(RESOLUTION_SLA_MINUTES),
        "sla_summary": _ticket_sla_summary_label(),
    }

def _append_specialist_sla_note(body_html: Any) -> str:
    rendered = str(body_html or "")
    if "sla" in rendered.lower():
        return rendered
    summary = html.escape(_ticket_sla_summary_label())
    return f"{rendered}<p><strong>SLA comprometido:</strong> {summary}.</p>"

def _get_ticketera_mail_template_def(template_key: str) -> Dict[str, str]:
    normalized = str(template_key or "").strip().lower()
    template_def = TICKETERA_MAIL_TEMPLATE_DEFS.get(normalized)
    if not template_def:
        raise ValueError("Plantilla de Ticketera no reconocida.")
    return template_def

def _serialize_ticketera_mail_template(
    conn,
    template_key: str,
) -> Dict[str, Any]:
    template_def = _get_ticketera_mail_template_def(template_key)
    stored_subject = _get_system_setting(conn, template_def["subject_setting_key"], "")
    stored_body = _get_system_setting(conn, template_def["body_setting_key"], "")
    default_subject = template_def.get("default_subject_template", "")
    default_body = template_def.get("default_body_template", "")
    use_default_subject = not str(stored_subject or "").strip()
    use_default_body = not str(stored_body or "").strip()
    return {
        "key": template_def["key"],
        "label": template_def.get("label", template_key),
        "description": template_def.get("description", ""),
        "subject_template": str(stored_subject or "").strip() or default_subject,
        "body_template": str(stored_body or "") or default_body,
        "uses_default_subject": use_default_subject,
        "uses_default_body": use_default_body,
    }

def list_ticketera_mail_templates() -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        return [
            _serialize_ticketera_mail_template(conn, template_key)
            for template_key in (
                MAIL_TEMPLATE_KEY_AUTO_REPLY,
                MAIL_TEMPLATE_KEY_HELPDESK_NEW_TICKET,
                MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT,
                MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT,
                MAIL_TEMPLATE_KEY_RESOLUTION,
            )
        ]
    finally:
        conn.close()


def get_monthly_report_data(year: int = None, month: int = None) -> Dict[str, Any]:
    """Genera un informe detallado de actividad de tickets para un mes específico."""
    now = datetime.now(timezone.utc)
    target_year = year or now.year
    target_month = month or now.month

    # Rango del mes
    start_date = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
    if target_month == 12:
        end_date = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_date = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc)

    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()

    conn = db.get_conn()
    try:
        # 1. Totales Generales
        totals = conn.execute("""
            SELECT
                COUNT(*) as creados,
                COUNT(CASE WHEN estado = 'cerrado' OR estado = 'resuelto' THEN 1 END) as terminados,
                COUNT(CASE WHEN estado NOT IN ('cerrado', 'resuelto') THEN 1 END) as pendientes
            FROM tickets
            WHERE created_at >= ? AND created_at < ?
              AND COALESCE(is_trashed, FALSE) = FALSE
        """, (start_iso, end_iso)).fetchone()

        # 2. Desglose por Cliente
        by_customer = conn.execute("""
            SELECT
                COALESCE(cliente_nombre, 'Sin Cliente / Directo') as nombre,
                COUNT(*) as total
            FROM tickets
            WHERE created_at >= ? AND created_at < ?
              AND COALESCE(is_trashed, FALSE) = FALSE
            GROUP BY cliente_nombre
            ORDER BY total DESC
            LIMIT 15
        """, (start_iso, end_iso)).fetchall()

        # 3. Desglose por Categoría
        by_category = conn.execute("""
            SELECT
                COALESCE(categoria, 'general') as cat,
                COUNT(*) as total
            FROM tickets
            WHERE created_at >= ? AND created_at < ?
              AND COALESCE(is_trashed, FALSE) = FALSE
            GROUP BY categoria
            ORDER BY total DESC
        """, (start_iso, end_iso)).fetchall()

        # 4. Rendimiento SLA (basado en resueltos en el mes)
        sla_stats = conn.execute("""
            SELECT
                COUNT(*) as total_resueltos,
                COUNT(CASE WHEN resolved_at <= ttr_due_at OR ttr_due_at IS NULL THEN 1 END) as a_tiempo
            FROM tickets
            WHERE resolved_at >= ? AND resolved_at < ?
              AND COALESCE(is_trashed, FALSE) = FALSE
        """, (start_iso, end_iso)).fetchone()

        return {
            "period": f"{target_year}-{target_month:02d}",
            "totals": dict(totals),
            "by_customer": [dict(r) for r in by_customer],
            "by_category": [dict(r) for r in by_category],
            "sla": dict(sla_stats),
            "generated_at": db.now_utc_iso()
        }
    finally:
        conn.close()

def get_ticketera_mail_template(template_key: str) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        return _serialize_ticketera_mail_template(conn, template_key)
    finally:
        conn.close()

def update_ticketera_mail_template(
    template_key: str,
    subject_template: str,
    body_template: str,
    actor_id: str,
) -> Dict[str, Any]:
    template_def = _get_ticketera_mail_template_def(template_key)
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        _upsert_system_setting(
            conn,
            template_def["subject_setting_key"],
            str(subject_template or "").strip(),
            group_name="ticketera",
            now_iso=now,
        )
        _upsert_system_setting(
            conn,
            template_def["body_setting_key"],
            str(body_template or ""),
            group_name="ticketera",
            now_iso=now,
        )
        conn.commit()
        updated = _serialize_ticketera_mail_template(conn, template_key)
        updated["updated_by"] = str(actor_id or "").strip()
        updated["updated_at"] = now
        return updated
    finally:
        conn.close()

def get_ticketera_templates() -> Dict[str, str]:
    template = get_ticketera_mail_template(MAIL_TEMPLATE_KEY_AUTO_REPLY)
    return {
        "subject_template": str(template.get("subject_template") or ""),
        "body_template": str(template.get("body_template") or ""),
    }

def update_ticketera_templates(subject_template: str, body_template: str, actor_id: str) -> Dict[str, str]:
    updated = update_ticketera_mail_template(
        MAIL_TEMPLATE_KEY_AUTO_REPLY,
        subject_template,
        body_template,
        actor_id,
    )
    return {
        "subject_template": str(updated.get("subject_template") or ""),
        "body_template": str(updated.get("body_template") or ""),
        "updated_by": str(updated.get("updated_by") or "").strip(),
        "updated_at": updated.get("updated_at"),
    }

def _ticketera_template_text_to_html(text: Any) -> str:
    normalized = str(text or "").replace("\r\n", "\n").strip()
    if not normalized:
        return ""
    paragraphs = [chunk.strip() for chunk in normalized.split("\n\n") if chunk.strip()]
    if not paragraphs:
        return ""
    return "".join(
        f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>"
        for paragraph in paragraphs
    )

def _render_ticketera_mail_subject(
    conn,
    template_key: str,
    context: Dict[str, Any],
) -> str:
    template_def = _get_ticketera_mail_template_def(template_key)
    stored_template = _get_system_setting(conn, template_def["subject_setting_key"], "").strip()
    using_default = not stored_template
    base_template = stored_template or template_def.get("default_subject_template", "")
    rendered = _render_text_template(base_template, context).strip()
    title = str(context.get("ticket_title") or "").strip()
    fallback_label = str(template_def.get("default_subject_fallback_label") or "").strip()
    if using_default and not title and fallback_label:
        return f"Re: [{context.get('ticket_code')}] {fallback_label}"
    return rendered or (f"Re: [{context.get('ticket_code')}] {fallback_label}" if fallback_label else str(base_template).strip())

def _render_ticketera_mail_body_html(
    conn,
    template_key: str,
    context: Dict[str, Any],
) -> str:
    template_def = _get_ticketera_mail_template_def(template_key)
    stored_template = _get_system_setting(conn, template_def["body_setting_key"], "")
    base_template = stored_template or template_def.get("default_body_template", "")
    rendered = _render_text_template(base_template, context).strip() or template_def.get("default_body_template", "")
    return _ticketera_template_text_to_html(rendered)

def _render_ticketera_mail_template(
    conn,
    template_key: str,
    context: Dict[str, Any],
) -> Tuple[str, str]:
    return (
        _render_ticketera_mail_subject(conn, template_key, context),
        _render_ticketera_mail_body_html(conn, template_key, context),
    )

def _serialize_email_route_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "match_type": str(row.get("match_type") or "").strip().lower(),
        "match_value": str(row.get("match_value") or "").strip().lower(),
        "categoria": str(row.get("categoria") or "").strip().lower(),
        "is_active": bool(int(row.get("is_active") or 0)),
        "created_by": str(row.get("created_by") or "").strip(),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }

def list_ticketera_routing_rules(*, only_active: bool = False) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        where = "WHERE is_active = true" if only_active else ""
        rows = conn.execute(
            f"""SELECT id, match_type, match_value, categoria, is_active, created_by, created_at, updated_at
                FROM ticket_config_email_routes
                {where}
                ORDER BY match_type ASC, match_value ASC, id ASC"""
        ).fetchall()
        return [_serialize_email_route_row(dict(row)) for row in rows]
    finally:
        conn.close()

def upsert_ticketera_routing_rule(
    *,
    rule_id: Optional[int] = None,
    match_type: str,
    match_value: str,
    categoria: str,
    actor_id: str,
    is_active: bool = True,
    customer_id: Optional[str] = None,
    customer_name: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_type = str(match_type or "").strip().lower()
    if normalized_type not in EMAIL_ROUTE_MATCH_TYPES:
        raise ValueError("Tipo de regla inválido. Usa 'email' o 'domain'.")

    normalized_value = _normalize_email_route_match_value(normalized_type, match_value)
    if not normalized_value:
        raise ValueError("Valor de regla inválido para el tipo seleccionado.")

    normalized_categoria = str(categoria or "").strip().lower()
    if normalized_categoria not in CATEGORIAS_VALIDAS:
        raise ValueError("Categoría inválida para routing Ticketera.")

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        normalized_actor = str(actor_id or "").strip()
        target_rule_id = int(rule_id or 0)
        if target_rule_id > 0:
            existing = conn.execute(
                """SELECT id
                   FROM ticket_config_email_routes
                   WHERE id = ?
                   LIMIT 1""",
                (target_rule_id,),
            ).fetchone()
            if not existing:
                raise ValueError("La regla de routing indicada no existe.")
            duplicated = conn.execute(
                """SELECT id
                   FROM ticket_config_email_routes
                   WHERE match_type = ? AND match_value = ? AND id <> ?
                   LIMIT 1""",
                (normalized_type, normalized_value, target_rule_id),
            ).fetchone()
            if duplicated:
                raise ValueError("Ya existe otra regla con ese correo o dominio.")
            conn.execute(
                """UPDATE ticket_config_email_routes
                   SET match_type = ?,
                       match_value = ?,
                       categoria = ?,
                       is_active = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (
                    normalized_type,
                    normalized_value,
                    normalized_categoria,
                    bool(is_active),
                    now,
                    target_rule_id,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO ticket_config_email_routes
                   (match_type, match_value, categoria, is_active, created_by, created_at, updated_at, customer_id, customer_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(match_type, match_value) DO UPDATE SET
                       categoria = EXCLUDED.categoria,
                       is_active = EXCLUDED.is_active,
                       updated_at = EXCLUDED.updated_at,
                       customer_id = EXCLUDED.customer_id,
                       customer_name = EXCLUDED.customer_name""",
                (
                    normalized_type,
                    normalized_value,
                    normalized_categoria,
                    bool(is_active),
                    normalized_actor,
                    now,
                    now,
                    customer_id or None,
                    customer_name or None,
                ),
            )
        conn.commit()
        if target_rule_id > 0:
            row = conn.execute(
                """SELECT id, match_type, match_value, categoria, is_active, created_by, created_at, updated_at
                   FROM ticket_config_email_routes
                   WHERE id = ?
                   LIMIT 1""",
                (target_rule_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT id, match_type, match_value, categoria, is_active, created_by, created_at, updated_at
                   FROM ticket_config_email_routes
                   WHERE match_type = ? AND match_value = ?
                   LIMIT 1""",
                (normalized_type, normalized_value),
            ).fetchone()
        return _serialize_email_route_row(dict(row)) if row else {}
    finally:
        conn.close()

def delete_ticketera_routing_rule(rule_id: int) -> bool:
    conn = db.get_conn()
    try:
        cursor = conn.execute("DELETE FROM ticket_config_email_routes WHERE id = ?", (int(rule_id),))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_ticketera_admin_config() -> Dict[str, Any]:
    return {
        "templates": get_ticketera_templates(),
        "mail_templates": list_ticketera_mail_templates(),
        "routing_rules": list_ticketera_routing_rules(),
        "categories": sorted(CATEGORIAS_VALIDAS),
    }

def _resolve_routing_category_for_email(conn, origen_email: Optional[str]) -> Optional[str]:
    normalized_email = _normalize_email_address(origen_email)
    if not normalized_email:
        return None

    email_row = conn.execute(
        """SELECT categoria
           FROM ticket_config_email_routes
           WHERE match_type = 'email'
             AND match_value = ?
             AND is_active = true
           LIMIT 1""",
        (normalized_email,),
    ).fetchone()
    if email_row and str(email_row.get("categoria") or "").strip().lower() in CATEGORIAS_VALIDAS:
        return str(email_row.get("categoria") or "").strip().lower()

    domain = _extract_email_domain(normalized_email)
    if not domain:
        return None
    domain_row = conn.execute(
        """SELECT categoria
           FROM ticket_config_email_routes
           WHERE match_type = 'domain'
             AND match_value = ?
             AND is_active = true
           LIMIT 1""",
        (domain,),
    ).fetchone()
    if domain_row and str(domain_row.get("categoria") or "").strip().lower() in CATEGORIAS_VALIDAS:
        return str(domain_row.get("categoria") or "").strip().lower()

    return None

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

def _resolve_helpdesk_new_ticket_recipients() -> List[Dict[str, str]]:
    # Mantener email + telefono permite reutilizar esta audiencia en futuros canales.
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT username, role, secondary_roles, phone_number
               FROM users
               WHERE COALESCE(is_active, 1) = 1
               ORDER BY username ASC"""
        ).fetchall()
        recipients: List[Dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            username = _normalize_username(row.get("username"))
            if not username or username in seen:
                continue
            roles = []
            primary_role = _normalize_role(row.get("role"))
            if primary_role:
                roles.append(primary_role)
            roles.extend(_parse_secondary_roles_value(row.get("secondary_roles")))
            if HELPDESK_MANAGER_ROLE not in _normalize_roles(roles):
                continue
            seen.add(username)
            recipients.append(
                {
                    "username": username,
                    "email": _normalize_email_address(username),
                    "phone_number": str(row.get("phone_number") or "").strip(),
                }
            )
        return recipients
    finally:
        conn.close()

def notify_client_assignment(ticket: Dict[str, Any], assignee_name: str) -> None:
    """Envía un correo al cliente informando la asignación del especialista."""
    ticket_id = int(ticket["id"])
    # Recargar ticket para capturar metadatos de hilo actualizados (evitar carrera con auto-respuesta)
    ticket = get_ticket(ticket_id) or ticket
    to_email, cc_emails, bcc_emails, to_record = _compose_reply_recipients(ticket)

    if not to_email or "@" not in to_email:
        return

    conn = db.get_conn()
    try:
        subject, body_html = _render_ticketera_mail_template(
            conn,
            MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT,
            _ticketera_template_context(ticket=ticket, assignee_name=assignee_name),
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
            references=headers.get("References"),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"[AssignmentNotify] Client fail ticket={ticket_id}: {e}")
    finally:
        conn.close()

def notify_specialist_assignment(username: str, ticket: Dict[str, Any]) -> None:
    """Notifica al especialista por correo sobre su nueva asignación."""
    # Los usernames son correos en este sistema
    if not username or "@" not in username:
        return
    
    ticket_id = int(ticket["id"])
    template_conn = db.get_conn()
    try:
        subject, body_html = _render_ticketera_mail_template(
            template_conn,
            MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT,
            _ticketera_template_context(ticket=ticket, assignee_name=username),
        )
        body_html = _append_specialist_sla_note(body_html)
    finally:
        template_conn.close()
    
    try:
        email_sender.send_email_advanced(
            to_email=username,
            subject=subject,
            html_body=body_html
        )
    except Exception as e:
        logger.error(f"[AssignmentNotify] Specialist fail user={username}: {e}")

def notify_helpdesk_new_ticket(ticket: Dict[str, Any]) -> None:
    """Notifica por correo al encargado de mesa cuando entra un ticket."""
    ticket_id = int(ticket.get("id") or 0)
    recipients = _resolve_helpdesk_new_ticket_recipients()
    if not recipients:
        return

    template_conn = db.get_conn()
    try:
        subject, body_html = _render_ticketera_mail_template(
            template_conn,
            MAIL_TEMPLATE_KEY_HELPDESK_NEW_TICKET,
            _ticketera_template_context(ticket=ticket),
        )
    finally:
        template_conn.close()

    sent_any = False
    for recipient in recipients:
        email = str(recipient.get("email") or "").strip()
        if not email or "@" not in email:
            continue
        try:
            email_sender.send_email_advanced(
                to_email=email,
                subject=subject,
                html_body=body_html,
            )
            sent_any = True
        except Exception as e:
            logger.error(
                f"[TicketNotify] Helpdesk fail user={recipient.get('username') or email} ticket={ticket_id}: {e}"
            )

    if not sent_any:
        logger.warning(f"[TicketNotify] No encargado_mesa email recipient available for ticket {ticket_id}.")

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
    headers = _build_ticket_thread_headers(ticket)
    now = db.now_utc_iso()
    conn = db.get_conn()
    try:
        subject = f"Re: [{code}] {str(title).strip()}"
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
            headers=headers or None,
        )
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
        # Actualizar metadatos de hilo
        _update_ticket_thread_metadata(
            conn,
            ticket_id,
            message_id=send_meta.get("message_id"),
            in_reply_to=headers.get("In-Reply-To"),
            references=headers.get("References"),
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
    base = ticket.get("codigo") or f"Ticket #{int(ticket.get('id') or 0)}"
    title = (ticket.get("titulo") or "").strip()
    subject = f"[{base}] {title}" if title else str(base)
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
    minutes = int(TTR_MINUTOS.get(severidad, RESOLUTION_SLA_MINUTES))
    base_utc = _ensure_utc(now_dt)
    if SLA_MODE == "business_hours":
        return _add_business_minutes(base_utc, minutes).isoformat()
    return (base_utc + timedelta(minutes=minutes)).isoformat()

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
    """Genera código público simple TK-2154+."""
    normalized_id = max(1, int(ticket_id or 1))
    public_number = TICKET_PUBLIC_CODE_START + normalized_id - 1
    return f"TK-{public_number}"

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

def _validate_main_status_transition(current_estado: str, target_estado: str) -> None:
    current = str(current_estado or "").strip().lower()
    target = str(target_estado or "").strip().lower()
    if current not in MAIN_STATUS_SEQUENCE or target not in MAIN_STATUS_SEQUENCE:
        return
    if current == target:
        return
    current_idx = MAIN_STATUS_SEQUENCE.index(current)
    target_idx = MAIN_STATUS_SEQUENCE.index(target)
    if abs(target_idx - current_idx) > 1:
        raise ConflictError(
            "Transición de estado inválida: solo se permite avanzar o retroceder un estado a la vez "
            f"({current} -> {target})."
        )

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
    conn.execute(
        """INSERT INTO ticket_comments (ticket_id, user_id, content, is_internal, created_at)
           VALUES (?, ?, ?, 1, ?)""",
        (ticket_id, author_id, content, now_iso),
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
               WHERE COALESCE(is_trashed, FALSE) = FALSE
                 AND (
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
    t["is_trashed"] = _db_bool(t.get("is_trashed"))
    estado_norm = str(t.get("estado") or "").strip().lower()
    sub_norm = normalize_subestado(t.get("subestado"), "recibido")
    # Guard rail: normaliza combinaciones legacy incoherentes (estado/subestado)
    # para evitar flujos inválidos en UI/workflow.
    if estado_norm == "cerrado":
        sub_norm = "cerrado"
    elif estado_norm == "resuelto":
        sub_norm = "resuelto"
    t["subestado"] = sub_norm
    t["display_estado"] = _ticket_display_status(t)
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

        explicit_categoria = str(categoria or "").strip().lower()
        if explicit_categoria in CATEGORIAS_VALIDAS:
            categoria = explicit_categoria
        else:
            routed_categoria = _resolve_routing_category_for_email(conn, origen_email) if origen_email else None
            categoria = routed_categoria or clasificar_ticket(titulo, descripcion)

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
        if auto_assign:
            try:
                asignado_a = auto_asignar(categoria)
            except Exception as e:
                logger.warning(f"[create_ticket] auto_asignar falló para categoría '{categoria}': {e}")

        if explicit_subestado:
            subestado = normalize_subestado(explicit_subestado, "recibido")
        else:
            subestado = "asignado" if asignado_a else "sin_asignar"
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
        created_ticket = get_ticket(ticket_id)

        # Programar notificaciones escalonadas (no-crítico: si falla, ticket ya está creado)
        if created_ticket:
            threading.Thread(
                target=notify_helpdesk_new_ticket,
                args=(created_ticket,),
                daemon=True,
            ).start()

        if asignado_a:
            try:
                programar_notificaciones(ticket_id, asignado_a)
            except Exception as e:
                logger.warning(f"[create_ticket] programar_notificaciones falló para ticket {ticket_id}: {e}")

        return created_ticket
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
    estados: Optional[List[str]] = None,
    q: Optional[str] = None,
    categoria: Optional[str] = None,
    asignado_a: Optional[str] = None,
    severidad: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    include_full: bool = False,
    include_total: bool = True,
    ver_resueltos: bool = False,
    trashed_only: bool = False,
    customer_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Dict[str, Any]:
    """Listar tickets con filtros avanzados. Retorna {items, total}."""
    conn = db.get_conn()
    try:
        # Protección simple para evitar cargas excesivas en UI.
        limit = max(1, min(int(limit or 100), 500))
        offset = max(0, int(offset or 0))

        where_clauses = ["1=1"]
        params = []

        if trashed_only:
            where_clauses.append("COALESCE(is_trashed, FALSE) = TRUE")
        else:
            where_clauses.append("COALESCE(is_trashed, FALSE) = FALSE")

        if estados:
            placeholders = ", ".join(["?" for _ in estados])
            where_clauses.append(f"estado IN ({placeholders})")
            params.extend([e.lower() for e in estados])
        elif estado:
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

        if customer_id:
            where_clauses.append("LOWER(COALESCE(customer_id, '')) = ?")
            params.append(customer_id.strip().lower())

        if created_after:
            where_clauses.append("created_at >= ?")
            params.append(created_after)

        if created_before:
            where_clauses.append("created_at <= ?")
            params.append(created_before)

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
                retention_until, retention_days_snapshot, customer_id, contact_role, notify_emails,
                is_trashed, trashed_at, trashed_by, trash_reason,
                trash_prev_estado, trash_prev_subestado, trash_prev_asignado_a
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
    _ensure_ticket_not_trashed(ticket, "tomar el ticket")

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
    _ensure_ticket_not_trashed(current, "modificar el ticket")

    normalized_updates: Dict[str, Any] = {}
    for key, value in (updates or {}).items():
        if key not in allowed_keys:
            continue
        if key == "estado":
            estado = str(value or "").strip().lower()
            if estado in ESTADOS_VALIDOS:
                current_estado = str(current.get("estado") or "abierto").lower()
                _validate_main_status_transition(current_estado, estado)
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
        # Si tiene asignado y está en recibido, forzamos asignado.
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
                # Solo emitir nota de sistema si NO es una asignación (para no duplicar avisos)
                # Eliminada emisión de [TRANSICION] por ser redundante con la visual de estados
                # if "asignado_a" not in normalized_updates:
                #     _emit_system_comment(
                #         conn,
                #         ticket_id,
                #         f"[TRANSICION] Subestado cambiado de {from_sub or '-'} a {to_sub}",
                #         now,
                #         author_id="system",
                #     )

        if "estado" in normalized_updates:
            new_estado = normalized_updates["estado"]
            if "asignado_a" not in normalized_updates:
                clean_estado = str(new_estado).replace("_", " ")
                _emit_system_comment(conn, ticket_id, f"[CAMBIO_ESTADO] Estado cambiado a {clean_estado}", now, author_id="system")
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
                # Nota automática SOLO cuando pasa de sin asignar -> asignado.
                if not old_asignado_norm and new_asignado_norm:
                    # Usamos prefijo para el badge de la UI, pero autor system para ocultar nombre y centrar.
                    _emit_system_comment(conn, ticket_id, f"[ASIGNACION] Asignado a {new_asignado}", now, author_id="system")
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
                f"[ESCALAMIENTO] Severidad cambiada a {new_sev}. Nuevo SLA: {_format_sla_minutes_label(TTR_MINUTOS.get(new_sev, RESOLUTION_SLA_MINUTES))}",
                now,
                author_id="system",
            )

        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        updated_ticket = get_ticket(ticket_id)
    finally:
        conn.close()

    # --- Notificaciones post-commit de asignación ---
    if updated_ticket and "asignado_a" in normalized_updates:
        new_asignado = normalized_updates["asignado_a"]
        old_asignado_norm = _normalize_username(current.get("asignado_a"))
        new_asignado_norm = _normalize_username(new_asignado)
        
        # Disparar si es una nueva asignación real
        if new_asignado_norm and old_asignado_norm != new_asignado_norm:
            # Enviar notificaciones en segundo plano para no bloquear la API
            threading.Thread(
                target=notify_client_assignment, 
                args=(updated_ticket, new_asignado),
                daemon=True
            ).start()
            threading.Thread(
                target=notify_specialist_assignment, 
                args=(new_asignado_norm, updated_ticket),
                daemon=True
            ).start()

    if "estado" in normalized_updates and updated_ticket:
        new_estado = str(updated_ticket.get("estado") or "").strip().lower()
        if old_estado and new_estado and old_estado != new_estado:
            if new_estado == "resuelto":
                threading.Thread(target=notify_client_resolution, args=(updated_ticket,), daemon=True).start()

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

def move_ticket_to_trash(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_manage_ticket_trash(ticket, actor_id, actor_role, "enviar tickets a papelera")
    if _ticket_is_trashed(ticket):
        return {"ok": True, "already_trashed": True, "ticket": ticket}

    prev_estado = str(ticket.get("estado") or "abierto").strip().lower() or "abierto"
    prev_subestado = normalize_subestado(ticket.get("subestado"), "recibido")
    prev_assignee = str(ticket.get("asignado_a") or "").strip() or None
    trash_reason = str(reason or "").strip()

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """UPDATE tickets
               SET is_trashed = TRUE,
                   trashed_at = ?,
                   trashed_by = ?,
                   trash_reason = ?,
                   trash_prev_estado = ?,
                   trash_prev_subestado = ?,
                   trash_prev_asignado_a = ?,
                   estado = 'cerrado',
                   subestado = 'cerrado',
                   updated_at = ?,
                   resolved_at = COALESCE(resolved_at, ?)
               WHERE id = ?""",
            (
                now,
                actor_id,
                trash_reason,
                prev_estado,
                prev_subestado,
                prev_assignee,
                now,
                now,
                ticket_id,
            ),
        )
        reason_suffix = f" | Motivo: {trash_reason}" if trash_reason else ""
        _emit_system_comment(
            conn,
            ticket_id,
            f"[PAPELERA] Ticket enviado a papelera por {actor_id}{reason_suffix}",
            now,
            author_id=actor_id,
        )
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    if prev_assignee and prev_estado not in {"resuelto", "cerrado"}:
        try:
            decrementar_carga(prev_assignee, specialty=ticket.get("categoria"))
        except Exception as e:
            logger.warning(f"[move_ticket_to_trash] Falló decrementar_carga para {prev_assignee}: {e}")

    return {"ok": True, "ticket": get_ticket(ticket_id)}

def restore_ticket_from_trash(
    ticket_id: int,
    actor_id: str,
    actor_role: str = "",
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    _ensure_can_manage_ticket_trash(ticket, actor_id, actor_role, "restaurar tickets desde papelera")
    if not _ticket_is_trashed(ticket):
        return {"ok": True, "already_restored": True, "ticket": ticket}

    prev_estado = str(ticket.get("trash_prev_estado") or "abierto").strip().lower() or "abierto"
    prev_assignee = str(ticket.get("trash_prev_asignado_a") or "").strip() or None
    prev_subestado_raw = ticket.get("trash_prev_subestado")
    if prev_estado == "en_progreso":
        fallback_subestado = "en_progreso"
    elif prev_estado == "resuelto":
        fallback_subestado = "resuelto"
    elif prev_estado == "cerrado":
        fallback_subestado = "cerrado"
    else:
        fallback_subestado = "asignado" if prev_assignee else "recibido"
    prev_subestado = normalize_subestado(prev_subestado_raw, fallback_subestado)

    if prev_estado not in ESTADOS_VALIDOS:
        prev_estado = "abierto"
    if prev_estado == "abierto" and prev_subestado in {"resuelto", "cerrado", "en_progreso"}:
        prev_subestado = "asignado" if prev_assignee else "recibido"
    elif prev_estado == "en_progreso" and prev_subestado in {"resuelto", "cerrado", "recibido"}:
        prev_subestado = "en_progreso"
    elif prev_estado == "resuelto":
        prev_subestado = "resuelto"
    elif prev_estado == "cerrado":
        prev_subestado = "cerrado"

    restored_estado = estado_from_subestado(prev_subestado, prev_estado)
    should_clear_resolved_at = restored_estado in {"abierto", "en_progreso"}

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """UPDATE tickets
               SET is_trashed = FALSE,
                   trashed_at = NULL,
                   trashed_by = NULL,
                   trash_reason = '',
                   estado = ?,
                   subestado = ?,
                   asignado_a = ?,
                   updated_at = ?,
                   resolved_at = CASE WHEN ? THEN NULL ELSE resolved_at END,
                   trash_prev_estado = NULL,
                   trash_prev_subestado = NULL,
                   trash_prev_asignado_a = NULL
               WHERE id = ?""",
            (
                restored_estado,
                prev_subestado,
                prev_assignee,
                now,
                should_clear_resolved_at,
                ticket_id,
            ),
        )
        _emit_system_comment(
            conn,
            ticket_id,
            f"[PAPELERA] Ticket restaurado por {actor_id} a estado {restored_estado}",
            now,
            author_id=actor_id,
        )
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()

    if prev_assignee and restored_estado not in {"resuelto", "cerrado"}:
        try:
            incrementar_carga(prev_assignee, specialty=ticket.get("categoria"))
        except Exception as e:
            logger.warning(f"[restore_ticket_from_trash] Falló incrementar_carga para {prev_assignee}: {e}")

    return {"ok": True, "ticket": get_ticket(ticket_id)}

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
    _ensure_ticket_not_trashed(ticket, "agregar notas")
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
    _ensure_ticket_not_trashed(ticket, "descartar borradores")
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

def _build_ticket_reply_body_html(message_text: str) -> str:
    escaped_msg = html.escape(str(message_text or "").strip()).replace("\n", "<br>")
    return f"<p>{escaped_msg}</p>"

def _prepare_uploaded_reply_attachments(ticket_id: int, files: Optional[List[Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    email_attachments: List[Dict[str, Any]] = []
    stored_attachments: List[Dict[str, Any]] = []
    if not files:
        return email_attachments, stored_attachments

    base_root = str(getattr(app_settings, "TICKET_ATTACHMENTS_DIR", "") or _default_ticket_attachments_dir())
    base_path = Path(base_root) / str(ticket_id) / "attachments"
    base_path.mkdir(parents=True, exist_ok=True)

    for file in files:
        try:
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
            if size > app_settings.TICKET_MAX_FILE_SIZE:
                logger.warning(f"File {file.filename} exceeds max size")
                continue

            filename = getattr(file, "filename", "untitled")
            ext = Path(filename).suffix.lower()
            if ext not in app_settings.TICKET_ALLOWED_EXTENSIONS:
                logger.warning(f"File extension {ext} not allowed")
                continue

            file_content = file.file.read()
            file_path = base_path / _attachment_storage_name(filename)
            if not _is_safe_attachment_path(file_path):
                logger.warning(f"[reply_email] ruta de adjunto fuera de raíz permitida: {file_path}")
                continue

            with open(file_path, "wb") as fh:
                fh.write(file_content)

            sha256 = hashlib.sha256(file_content).hexdigest()
            content_type = getattr(file, "content_type", "application/octet-stream")
            email_attachments.append(
                {
                    "filename": filename,
                    "data": file_content,
                    "content_type": content_type,
                }
            )
            stored_attachments.append(
                {
                    "filename": filename,
                    "path": str(file_path),
                    "size": len(file_content),
                    "content_type": content_type,
                    "sha256": sha256,
                }
            )
        except Exception as e:
            logger.error(f"Error procesando adjunto {getattr(file, 'filename', '?')}: {e}")

    return email_attachments, stored_attachments

def _send_ticket_reply_email(
    *,
    ticket: Dict[str, Any],
    author_id: str,
    clean_msg: str,
    to_email: str,
    cc_emails: List[str],
    bcc_emails: List[str],
    to_addr_record: str,
    email_attachments: Optional[List[Dict[str, Any]]] = None,
    stored_attachments: Optional[List[Dict[str, Any]]] = None,
    idempotency_key: Optional[str] = None,
    artifact_ref: Optional[str] = None,
    evidence_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ticket_id = int(ticket.get("id") or 0)
    clean_msg = str(clean_msg or "").strip()
    if not clean_msg:
        raise ValueError("El mensaje de respuesta está vacío")
    if not to_email or "@" not in str(to_email):
        raise ValueError("Este ticket no tiene un correo de cliente válido")

    subject = _build_ticket_reply_subject(ticket)
    headers = _build_ticket_thread_headers(ticket)
    threaded = bool(headers.get("In-Reply-To") or headers.get("References"))
    body_html = _build_ticket_reply_body_html(clean_msg)
    now = db.now_utc_iso()
    preview = clean_msg if len(clean_msg) <= 300 else clean_msg[:300] + "..."
    normalized_idempotency_key = (idempotency_key or "").strip()[:128] or None
    email_attachments = list(email_attachments or [])
    stored_attachments = list(stored_attachments or [])

    dedupe_since = (
        datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(minutes=3)
    ).isoformat()
    marker_id = None

    lock_conn = db.get_conn()
    try:
        try:
            lock_conn.execute("SELECT pg_advisory_lock(?)", (ticket_id,))
        except Exception:
            pass

        if normalized_idempotency_key:
            idem_row = lock_conn.execute(
                """SELECT id, direction FROM ticket_emails
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
                    "sent_email_id": int(idem_row.get("id") or 0),
                    "email_direction": str(idem_row.get("direction") or ""),
                }

        dup_row = lock_conn.execute(
            """SELECT id, direction FROM ticket_emails
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
                "sent_email_id": int(dup_row.get("id") or 0),
                "email_direction": str(dup_row.get("direction") or ""),
            }

        marker_row = lock_conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
               VALUES (?, 'outgoing_pending', '', ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (
                ticket_id,
                to_addr_record or to_email,
                ", ".join(cc_emails),
                ", ".join(bcc_emails),
                subject,
                body_html,
                json.dumps(stored_attachments),
                normalized_idempotency_key,
                now,
            ),
        ).fetchone()
        marker_id = int((marker_row or {}).get("id") or 0)
        lock_conn.commit()
    finally:
        try:
            lock_conn.execute("SELECT pg_advisory_unlock(?)", (ticket_id,))
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
            attachments=email_attachments,
        )
    except Exception as e:
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
        email_id = marker_id
        if marker_id:
            conn.execute(
                """UPDATE ticket_emails
                   SET direction = 'outgoing', from_addr = ?, to_addr = ?, cc_addrs = ?, bcc_addrs = ?
                   WHERE id = ?""",
                (
                    send_meta.get("from_addr"),
                    to_addr_record or to_email,
                    ", ".join(cc_emails),
                    ", ".join(bcc_emails),
                    marker_id,
                ),
            )
        else:
            email_row = conn.execute(
                """INSERT INTO ticket_emails
                   (ticket_id, direction, from_addr, to_addr, cc_addrs, bcc_addrs, subject, body_html, attachments_json, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
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
            ).fetchone()
            email_id = int((email_row or {}).get("id") or 0)

        updated_stored_attachments = []
        for att in stored_attachments:
            inserted = conn.execute(
                """INSERT INTO ticket_attachments
                   (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   RETURNING id""",
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
            ).fetchone()
            att_id = int((inserted or {}).get("id") or 0)
            new_att = dict(att)
            new_att["id"] = att_id
            new_att["attachment_id"] = att_id
            updated_stored_attachments.append(new_att)

        if updated_stored_attachments:
            conn.execute(
                "UPDATE ticket_emails SET attachments_json = ? WHERE id = ?",
                (json.dumps(updated_stored_attachments), email_id)
            )

        has_attachments = " (con adjuntos)" if stored_attachments else ""
        cc_hint = f" + CC: {', '.join(cc_emails)}" if cc_emails else ""
        bcc_hint = f" + CCO: {', '.join(bcc_emails)}" if bcc_emails else ""
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                ticket_id,
                author_id,
                f"[CORREO] Respuesta enviada a {to_email}{cc_hint}{bcc_hint}{has_attachments}: {preview}",
                now,
            ),
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
            artifact_ref=artifact_ref or f"ticket:{ticket_id}:email_reply",
            owner=author_id,
            integrity_hash=send_meta.get("message_id") or "",
            metadata={
                "to": to_email,
                "cc": cc_emails,
                "bcc": bcc_emails,
                "threaded": threaded,
                "has_attachments": bool(stored_attachments),
                "idempotency_key": normalized_idempotency_key or "",
                **(evidence_metadata or {}),
            },
        )
    except Exception as e:
        logger.warning(f"[_send_ticket_reply_email] evidence_event no crítico falló para ticket {ticket_id}: {e}")

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
        "sent_email_id": int(email_id or 0),
        "body_html": body_html,
        "duplicate_skipped": False,
    }

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

    draft_id = 0
    current_version = 0
    to_email = ""
    cc_emails: List[str] = []
    bcc_emails: List[str] = []
    to_addr_record = ""
    clean_msg = ""
    email_attachments: List[Dict[str, Any]] = []
    stored_attachments: List[Dict[str, Any]] = []
    conn = db.get_conn()
    try:
        draft = _get_active_email_draft_row(conn, ticket_id)
        if not draft:
            raise ValueError("No existe borrador activo para este ticket.")
        _validate_draft_lock(draft, actor_id, lock_token)
        draft_id = int(draft.get("id") or 0)
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

        body_text = str(draft.get("body_text") or "")
        clean_msg = body_text.strip()
        if not clean_msg:
            raise ValueError("El borrador está vacío. Agrega un mensaje antes de enviar.")

        draft_attachments = _list_email_draft_attachments(conn, draft_id)
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
    finally:
        conn.close()

    send_result = _send_ticket_reply_email(
        ticket=ticket,
        author_id=actor_id,
        clean_msg=clean_msg,
        to_email=to_email,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        to_addr_record=to_addr_record,
        email_attachments=email_attachments,
        stored_attachments=stored_attachments,
        idempotency_key=f"draft:{draft_id}:v{current_version}",
        artifact_ref=f"ticket:{ticket_id}:email_reply_draft",
        evidence_metadata={
            "draft_id": draft_id,
            "version": current_version,
        },
    )
    email_id = int(send_result.get("sent_email_id") or 0)
    email_direction = str(send_result.get("email_direction") or "outgoing").strip().lower()
    should_mark_sent = (not send_result.get("duplicate_skipped")) or email_direction == "outgoing"
    draft_status = "active"

    if should_mark_sent and email_id > 0:
        now = db.now_utc_iso()
        conn = db.get_conn()
        try:
            conn.execute(
                """UPDATE ticket_email_draft_attachments
                   SET sent_email_id = ?
                   WHERE draft_id = ? AND sent_email_id IS NULL""",
                (email_id, draft_id),
            )
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
                (actor_id, email_id, now, actor_id, now, draft_id),
            )
            conn.commit()
            draft_status = "sent"
        finally:
            conn.close()

    return {
        "ok": True,
        "ticket_id": int(ticket_id),
        "to_email": to_email,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": send_result.get("subject"),
        "threaded": bool(send_result.get("threaded")),
        "message_id": send_result.get("message_id"),
        "sent_email_id": email_id,
        "draft_status": draft_status,
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
              AND COALESCE(is_trashed, FALSE) = FALSE
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
              AND COALESCE(is_trashed, FALSE) = FALSE
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
    _ensure_ticket_not_trashed(ticket, "cambiar estado")
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
            if new_estado == "resuelto":
                threading.Thread(target=notify_client_resolution, args=(result_ticket,), daemon=True).start()

            try:
                _send_ticket_status_update_to_notify_emails(
                    result_ticket,
                    from_estado=old_estado,
                    to_estado=new_estado,
                    actor_id=actor_id,
                    motivo=motivo,
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
    _ensure_ticket_not_trashed(ticket, "aprobar cambios")
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
    allowed_next: List[str] = []
    if not _ticket_is_trashed(ticket):
        allowed_next = _workflow_next(tipo, sub)
        allowed_next = _filter_waiting_subestados(allowed_next, ticket.get("estado"))
    if tipo == "cambio" and not _ticket_is_trashed(ticket):
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
    to_addr: Optional[str] = None,
    cc_addrs: Optional[Any] = None,
    bcc_addrs: Optional[Any] = None,
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
    _ensure_ticket_not_trashed(ticket, "responder correos")
    _ensure_can_participate_ticket(ticket, author_id, author_role, "responder correos")
    _ensure_reply_allowed_estado(ticket, "responder correos")

    clean_msg = (mensaje or "").strip()
    if not clean_msg:
        logger.error(f"Reply failed: Message empty for ticket {ticket_id}")
        raise ValueError("El mensaje de respuesta está vacío")

    to_email, cc_emails, bcc_emails, to_addr_record = _compose_reply_recipients(
        ticket,
        explicit_to=to_addr,
        explicit_cc=cc_addrs,
        explicit_bcc=bcc_addrs,
    )
    if not to_email or "@" not in to_email:
        logger.error(f"Reply failed: Invalid to_email '{to_email}' for ticket {ticket_id}")
        raise ValueError("Este ticket no tiene un correo de cliente válido")
    email_attachments, stored_attachments = _prepare_uploaded_reply_attachments(ticket_id, files)
    return _send_ticket_reply_email(
        ticket=ticket,
        author_id=author_id,
        clean_msg=clean_msg,
        to_email=to_email,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        to_addr_record=to_addr_record,
        email_attachments=email_attachments,
        stored_attachments=stored_attachments,
        idempotency_key=idempotency_key,
    )

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

def _normalize_incoming_email_content_id(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    if value.lower().startswith("cid:"):
        value = value[4:]
    return value.strip().strip("<>").strip().lower()

def _sanitize_incoming_email_numeric_attr(raw_value: Any, *, allow_percent: bool = False) -> Optional[str]:
    value = str(raw_value or "").strip()
    if not value:
        return None
    pattern = r"^\d{1,4}%?$" if allow_percent else r"^\d{1,4}$"
    if not re.match(pattern, value):
        return None
    if not allow_percent and value.endswith("%"):
        return None
    return value

def _sanitize_incoming_email_url(
    raw_value: Any,
    *,
    allow_cid: bool = False,
    allow_data_image: bool = False,
    allow_http: bool = False,
    allow_mailto: bool = False,
    allow_tel: bool = False,
) -> Optional[str]:
    value = html.unescape(str(raw_value or "").strip())
    if not value:
        return None
    lowered = value.lower()
    if allow_cid and lowered.startswith("cid:"):
        normalized_cid = _normalize_incoming_email_content_id(value)
        return f"cid:{normalized_cid}" if normalized_cid else None
    if allow_data_image and lowered.startswith("data:image/"):
        return value
    if lowered.startswith("//"):
        return None

    parsed = urlparse.urlsplit(value)
    scheme = parsed.scheme.lower()
    if not scheme:
        if value.startswith("#"):
            return value
        return value
    if scheme in {"http", "https"}:
        return value if allow_http else None
    if scheme == "mailto":
        return value if allow_mailto else None
    if scheme == "tel":
        return value if allow_tel else None
    return None

def _sanitize_incoming_email_attr(tag: str, name: str, raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    if name == "href":
        return _sanitize_incoming_email_url(
            value,
            allow_http=True,
            allow_mailto=True,
            allow_tel=True,
        )
    if name == "src":
        return _sanitize_incoming_email_url(
            value,
            allow_cid=True,
            allow_data_image=True,
            allow_http=False,
        )
    if name in {"width", "height"}:
        return _sanitize_incoming_email_numeric_attr(value, allow_percent=True)
    if name in {"border", "cellpadding", "cellspacing", "colspan", "rowspan"}:
        return _sanitize_incoming_email_numeric_attr(value, allow_percent=False)
    if name in {"align", "valign", "dir"}:
        normalized = value.lower()
        allowed_values = {
            "align": {"left", "center", "right", "justify"},
            "valign": {"top", "middle", "bottom"},
            "dir": {"ltr", "rtl", "auto"},
        }
        return normalized if normalized in allowed_values.get(name, set()) else None
    return value

def _sanitize_incoming_email_html(raw_html: Any) -> str:
    source = str(raw_html or "").strip()
    if not source:
        return ""
    parser = _IncomingEmailHtmlSanitizer()
    try:
        parser.feed(source)
        parser.close()
    except Exception as exc:
        logger.warning(f"[incoming_email_html] sanitizer fallback: {exc}")
        return ""
    return parser.get_html().strip()

def _plain_text_to_email_html(raw_text: Any) -> str:
    text = str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    escaped = html.escape(text)
    return escaped.replace("\n", "<br>")

def _incoming_email_attachment_inline_url(ticket_id: int, attachment_id: int) -> str:
    return f"api/tks/tickets/{int(ticket_id)}/attachments/{int(attachment_id)}/download?inline=1"

def _rewrite_incoming_email_inline_sources(
    body_html: str,
    ticket_id: int,
    attachments: Optional[List[Dict[str, Any]]],
) -> str:
    html_value = str(body_html or "").strip()
    if not html_value or not attachments:
        return html_value

    cid_map: Dict[str, int] = {}
    for item in attachments:
        if not isinstance(item, dict):
            continue
        attachment_id = int(item.get("attachment_id") or item.get("id") or 0)
        content_id = _normalize_incoming_email_content_id(item.get("content_id"))
        if attachment_id > 0 and content_id and content_id not in cid_map:
            cid_map[content_id] = attachment_id

    if not cid_map:
        return html_value

    def _replace(match: re.Match[str]) -> str:
        attr = match.group("attr")
        quote = match.group("quote")
        cid_value = _normalize_incoming_email_content_id(match.group("cid"))
        attachment_id = cid_map.get(cid_value)
        if not attachment_id:
            return match.group(0)
        return f'{attr}={quote}{_incoming_email_attachment_inline_url(ticket_id, attachment_id)}{quote}'

    return re.sub(
        r'(?P<attr>\bsrc)\s*=\s*(?P<quote>[\'"])\s*cid:(?P<cid>.*?)(?P=quote)',
        _replace,
        html_value,
        flags=re.IGNORECASE,
    )

def _build_incoming_email_body_html(
    *,
    ticket_id: int,
    body_text: Any,
    raw_html: Any = "",
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    sanitized_html = _sanitize_incoming_email_html(raw_html)
    if not sanitized_html:
        sanitized_html = _plain_text_to_email_html(body_text)
    if not sanitized_html:
        return ""
    return _rewrite_incoming_email_inline_sources(sanitized_html, ticket_id, attachments)

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
        content_id = _normalize_incoming_email_content_id(item.get("content_id"))
        disposition = str(item.get("disposition") or "").strip().lower()
        is_inline = bool(item.get("is_inline")) or bool(content_id) or "inline" in disposition
        inserted = conn.execute(
            """INSERT INTO ticket_attachments
               (ticket_id, filename, file_path, uploaded_by, created_at, size_bytes, content_type, sha256)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
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
        ).fetchone()
        attachment_id = int((inserted or {}).get("id") or 0)
        saved.append(
            {
                "id": attachment_id,
                "attachment_id": attachment_id,
                "filename": filename,
                "path": str(file_path),
                "size": len(data),
                "size_bytes": len(data),
                "content_type": content_type,
                "sha256": sha256,
                "content_id": content_id,
                "disposition": disposition,
                "is_inline": is_inline,
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
    _ensure_ticket_not_trashed(ticket, "subir adjuntos")
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
    item["content_type"] = (
        str(item.get("content_type") or "").strip()
        or mimetypes.guess_type(path.name)[0]
        or "application/octet-stream"
    )
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
            to_sub = str(row["to_subestado"] or "-")
            reason = str(row["reason"] or "").strip()
            detail = f"Estado: cambiado a {to_sub}"

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
        where_parts = ["1=1", "COALESCE(is_trashed, FALSE) = FALSE"]
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
                     AND COALESCE(is_trashed, FALSE) = FALSE
                   ORDER BY created_at ASC, id ASC
                   LIMIT ?""",
                (assignee_filter, ticket_limit),
            ).fetchall()
        else:
            ticket_rows = conn.execute(
                """SELECT id, codigo, titulo, estado, subestado, asignado_a, categoria, severidad,
                          created_at, updated_at, resolved_at
                   FROM tickets
                   WHERE COALESCE(is_trashed, FALSE) = FALSE
                     AND ((asignado_a IS NOT NULL)
                      OR (COALESCE(asignado_a, '') = '' AND estado = 'abierto')
                     )
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
        items = _list_specialties_with_role_fallback(conn)
        return [row for row in items if _normalize_username(row.get("username")) != "mesa_ayuda"]
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
            r"(TK-\d{4,})",
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

def _auto_reply_subject_default(ticket: Dict[str, Any]) -> str:
    code = str(ticket.get("codigo") or f"TK-{ticket.get('id', '')}").strip() or "Ticket"
    title = str(ticket.get("titulo") or "").strip()
    if title:
        return f"Re: [{code}] {title}"
    return f"Re: [{code}] Comprobante de Recepción"

def _auto_reply_subject(conn, ticket: Dict[str, Any], nombre: str = "", asignado_a: str = "") -> str:
    template = _get_system_setting(conn, AUTO_REPLY_SUBJECT_SETTING_KEY, "").strip()
    if not template:
        return _auto_reply_subject_default(ticket)
    rendered = _render_text_template(
        template,
        _ticketera_template_context(ticket=ticket, customer_name=nombre, assignee_name=asignado_a),
    ).strip()
    return rendered or _auto_reply_subject_default(ticket)

def _auto_reply_body(conn, ticket: Dict[str, Any], nombre: str, asignado_a: str) -> str:
    template = _get_system_setting(conn, AUTO_REPLY_BODY_SETTING_KEY, DEFAULT_AUTO_REPLY_BODY_TEMPLATE)
    rendered = _render_text_template(
        template,
        _ticketera_template_context(ticket=ticket, customer_name=nombre, assignee_name=asignado_a),
    ).strip() or DEFAULT_AUTO_REPLY_BODY_TEMPLATE
    return "<p>" + html.escape(rendered).replace("\n", "<br>") + "</p>"

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
    delay_minutes = _auto_reply_delay_minutes(conn)
    run_at = (datetime.utcnow() + timedelta(minutes=delay_minutes)).isoformat()
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
        "ticket_code": str(ticket.get("codigo") or generar_codigo(ticket_id)),
        "idempotency_key": idem_key,
        "in_reply_to": in_reply_to_norm or "",
        "references": merged_refs or "",
    }
    body_html = _auto_reply_body(conn, ticket, nombre, asignado_a or "")
    subject = _auto_reply_subject(conn, ticket, nombre, asignado_a or "")

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
    body_html = msg.get("body_html", "")
    msg_id = msg.get("message_id", "")
    in_reply_to = msg.get("in_reply_to", "")
    references = msg.get("references", "")
    attachments = msg.get("attachments") if isinstance(msg.get("attachments"), list) else []

    try:
        ticket_id = _find_ticket_by_thread_headers(in_reply_to, references)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id, in_reply_to, references, attachments, body_html=body_html)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by thread headers: {e}")

    try:
        ticket_id = _find_ticket_by_subject(subject)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id, in_reply_to, references, attachments, body_html=body_html)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by subject: {e}")

    _process_new_email_ticket(subject, sender, body, msg_id, in_reply_to, references, attachments, body_html=body_html)

def _process_reply_email(
    ticket_id: int,
    sender: str,
    subject: str,
    body: str,
    msg_id: str,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    body_html: Optional[str] = None,
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
        stored_body_html = _build_incoming_email_body_html(
            ticket_id=ticket_id,
            body_text=body,
            raw_html=body_html,
            attachments=saved_attachments,
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
                stored_body_html,
                json.dumps(saved_attachments, ensure_ascii=False),
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
    body_html: Optional[str] = None,
):
    print(f"[EMAIL] New Ticket from {sender}")
    
    # 1. Clasificación
    categoria = clasificar_ticket(subject, body)
    # 2. Triaje: por correo entrante se crea SIEMPRE sin asignación (cola manual)
    asignado_a = None

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
            auto_assign=False,
        )
        
        ticket_id = tk['id']
        codigo = tk['codigo']
        # Registrar correo entrante en historial de correos.
        conn = db.get_conn()
        saved_attachments = _persist_incoming_attachments(
            conn,
            ticket_id,
            attachments,
            uploaded_by=f"email:{sender}",
        )
        stored_body_html = _build_incoming_email_body_html(
            ticket_id=ticket_id,
            body_text=body,
            raw_html=body_html,
            attachments=saved_attachments,
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
                stored_body_html,
                json.dumps(saved_attachments, ensure_ascii=False),
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

        _emit_system_comment(
            conn,
            ticket_id,
            "[CREACIÓN] Ticket generado [Estado: Sin asignar]",
            now,
            author_id="system",
        )

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
        # Nota: Se eliminó la emisión de comentario [AUTO_RESPUESTA] programada
        # por petición del usuario para evitar ruido en la línea de tiempo.
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

def bulk_assign_customer_by_email(
    origen_email: str,
    customer_id: str,
    customer_name: str,
) -> Dict[str, Any]:
    """
    Asocia todos los tickets que tengan el mismo origen_email (o dominio)
    al cliente indicado. Retorna cuántos tickets fueron actualizados.
    """
    email = str(origen_email or "").strip().lower()
    if not email or not customer_id:
        raise ValueError("Email y customer_id son requeridos")

    conn = db.get_conn()
    try:
        # Tickets con mismo email exacto sin cliente asignado
        by_email = conn.execute(
            """UPDATE tks.tickets
               SET customer_id = ?, cliente_nombre = ?
               WHERE LOWER(COALESCE(origen_email, '')) = ?
                 AND (customer_id IS NULL OR customer_id = '')
               RETURNING id""",
            (customer_id, customer_name, email),
        ).fetchall()

        # Tickets con mismo dominio sin cliente asignado
        dominio = email.split("@")[1] if "@" in email else None
        by_domain = []
        if dominio:
            by_domain = conn.execute(
                """UPDATE tks.tickets
                   SET customer_id = ?, cliente_nombre = ?
                   WHERE LOWER(COALESCE(origen_email, '')) LIKE ?
                     AND (customer_id IS NULL OR customer_id = '')
                   RETURNING id""",
                (customer_id, customer_name, f"%@{dominio}"),
            ).fetchall()

        conn.commit()
        total = len(by_email) + len(by_domain)
        return {
            "ok": True,
            "updated": total,
            "by_email": len(by_email),
            "by_domain": len(by_domain),
            "dominio": dominio,
        }
    finally:
        conn.close()


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


# ==========================================================================
# DIRECTORIO DE CLIENTES
# ==========================================================================

def get_directorio_clientes(q: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna la lista de clientes que tienen tickets registrados,
    con conteos por estado para el panel lateral del Directorio.
    """
    conn = db.get_conn()
    try:
        # Clientes conocidos (con nombre) que tienen tickets
        rows = conn.execute(
            """
            SELECT
                t.customer_id,
                COALESCE(t.customer_id, 'sin_cliente') as id,
                COALESCE(
                    MAX(cce.customer_name),
                    MAX(t.cliente_nombre),
                    t.customer_id,
                    'Sin Cliente'
                ) as nombre,
                COUNT(*) as total,
                SUM(CASE WHEN t.estado IN ('abierto', 'en_progreso') AND COALESCE(t.is_trashed, FALSE) = FALSE THEN 1 ELSE 0 END) as activos,
                SUM(CASE WHEN t.estado IN ('resuelto', 'cerrado') THEN 1 ELSE 0 END) as resueltos
            FROM tickets t
            LEFT JOIN ticket_config_client_emails cce
                ON LOWER(t.origen_email) = LOWER(cce.email)
            WHERE t.customer_id IS NOT NULL AND t.customer_id != ''
            GROUP BY t.customer_id
            ORDER BY activos DESC, total DESC
            """
        ).fetchall()

        clientes = []
        for r in rows:
            nombre = str(r.get("nombre") or r.get("id") or "Sin Cliente")
            if q and q.strip():
                if q.strip().lower() not in nombre.lower():
                    continue
            clientes.append({
                "id": str(r.get("id") or ""),
                "nombre": nombre,
                "total": int(r.get("total") or 0),
                "activos": int(r.get("activos") or 0),
                "resueltos": int(r.get("resueltos") or 0),
            })

        return {"items": clientes, "total": len(clientes)}
    finally:
        conn.close()


def get_directorio_metricas(
    customer_id: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
) -> Dict[str, Any]:
    """
    KPIs de un cliente en un rango de fechas para el encabezado
    analítico del Directorio: volumen, SLA, tiempo de respuesta.
    """
    conn = db.get_conn()
    try:
        where = ["1=1"]
        params: List[Any] = []

        if customer_id:
            where.append("LOWER(COALESCE(customer_id, '')) = ?")
            params.append(customer_id.strip().lower())

        if created_after:
            where.append("created_at >= ?")
            params.append(created_after)

        if created_before:
            where.append("created_at <= ?")
            params.append(created_before)

        where_sql = " AND ".join(where)

        row = conn.execute(
            f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN estado IN ('resuelto', 'cerrado') THEN 1 ELSE 0 END) as resueltos,
                SUM(CASE WHEN estado IN ('abierto', 'en_progreso')
                         AND COALESCE(is_trashed, FALSE) = FALSE THEN 1 ELSE 0 END) as activos,
                SUM(CASE WHEN COALESCE(sla_frt_breached, FALSE) = TRUE THEN 1 ELSE 0 END) as sla_frt_incumplidos,
                SUM(CASE WHEN COALESCE(sla_ttr_breached, FALSE) = TRUE THEN 1 ELSE 0 END) as sla_ttr_incumplidos,
                AVG(
                    CASE
                        WHEN first_response_at IS NOT NULL AND created_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (first_response_at::timestamp - created_at::timestamp)) / 60.0
                    END
                ) as avg_frt_minutos,
                AVG(
                    CASE
                        WHEN resolved_at IS NOT NULL AND created_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (resolved_at::timestamp - created_at::timestamp)) / 60.0
                    END
                ) as avg_ttr_minutos
            FROM tickets
            WHERE {where_sql}
            """,
            params,
        ).fetchone()

        if not row:
            return {"total": 0, "resueltos": 0, "activos": 0}

        total = int(row.get("total") or 0)
        resueltos = int(row.get("resueltos") or 0)
        activos = int(row.get("activos") or 0)
        sla_frt = int(row.get("sla_frt_incumplidos") or 0)
        sla_ttr = int(row.get("sla_ttr_incumplidos") or 0)

        avg_frt = row.get("avg_frt_minutos")
        avg_ttr = row.get("avg_ttr_minutos")

        cumplimiento_pct = None
        if total > 0:
            cumplimiento_pct = round(100 * (1 - (sla_ttr / total)), 1)

        return {
            "total": total,
            "resueltos": resueltos,
            "activos": activos,
            "sla_frt_incumplidos": sla_frt,
            "sla_ttr_incumplidos": sla_ttr,
            "cumplimiento_sla_pct": cumplimiento_pct,
            "avg_frt_minutos": round(float(avg_frt), 1) if avg_frt else None,
            "avg_ttr_minutos": round(float(avg_ttr), 1) if avg_ttr else None,
        }
    except Exception as e:
        logger.error(f"[get_directorio_metricas] Error: {e}")
        return {"total": 0, "resueltos": 0, "activos": 0, "error": str(e)}
    finally:
        conn.close()
