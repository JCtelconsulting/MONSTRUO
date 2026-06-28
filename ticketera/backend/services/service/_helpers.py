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
from plataforma.core import email as email_sender, jobs_engine, google_chat
from plataforma.core.config import settings as app_settings
from ticketera.backend.services import roles as ticket_roles
from ticketera.backend.services import workflow as ticket_workflow

logger = logging.getLogger(__name__)

__all__ = [
    "ASSIGNMENT_SLA_MINUTES",
    "AUTO_REPLY_BODY_SETTING_KEY",
    "AUTO_REPLY_MAX_REFERENCES",
    "AUTO_REPLY_SLA_MINUTES",
    "AUTO_REPLY_SUBJECT_SETTING_KEY",
    "CATEGORIAS_VALIDAS",
    "CHAIN_ALGO",
    "CHAIN_VERSION",
    "CHANNELS_ENABLED",
    "CHANNELS_MAX_ATTEMPTS",
    "CHANNELS_RETRY_BASE_SECONDS",
    "CHANNELS_RETRY_MAX_SECONDS",
    "CHANNEL_ADAPTER_MODES",
    "CHANNEL_NOTIFICATION_STATUSES",
    "CLIENT_ASSIGNMENT_BODY_SETTING_KEY",
    "CLIENT_ASSIGNMENT_SUBJECT_SETTING_KEY",
    "COMPLIANCE_EXPORT_DIR",
    "COMPLIANCE_EXPORT_HOUR",
    "COMPLIANCE_EXPORT_MINUTE",
    "COMPLIANCE_PURGE_GRACE_DAYS",
    "COMPLIANCE_PURGE_HOUR",
    "COMPLIANCE_PURGE_MINUTE",
    "COMPLIANCE_TZ",
    "ConflictError",
    "DEFAULT_AUTO_REPLY_BODY_TEMPLATE",
    "DEFAULT_CLIENT_ASSIGNMENT_BODY_TEMPLATE",
    "DEFAULT_HELPDESK_NEW_TICKET_BODY_TEMPLATE",
    "DEFAULT_HELPDESK_NEW_TICKET_SUBJECT_TEMPLATE",
    "DEFAULT_REPLY_SUBJECT_TEMPLATE",
    "DEFAULT_RESOLUTION_BODY_TEMPLATE",
    "DEFAULT_SPECIALIST_ASSIGNMENT_BODY_TEMPLATE",
    "DEFAULT_SPECIALIST_ASSIGNMENT_SUBJECT_TEMPLATE",
    "EMAIL_DRAFT_LOCK_HEARTBEAT_SECONDS",
    "EMAIL_DRAFT_LOCK_MINUTES",
    "EMAIL_ROUTE_MATCH_TYPES",
    "ESTADOS_VALIDOS",
    "FRT_MINUTOS",
    "HELPDESK_MANAGER_ROLE",
    "HELPDESK_NEW_TICKET_BODY_SETTING_KEY",
    "HELPDESK_NEW_TICKET_SUBJECT_SETTING_KEY",
    "INCOMING_EMAIL_ALLOWED_ATTRS",
    "INCOMING_EMAIL_ALLOWED_TAGS",
    "INCOMING_EMAIL_DROP_TAGS",
    "INCOMING_EMAIL_VOID_TAGS",
    "KEYWORDS_CATEGORIAS",
    "MAIL_TEMPLATE_KEY_AUTO_REPLY",
    "MAIL_TEMPLATE_KEY_CLIENT_ASSIGNMENT",
    "MAIL_TEMPLATE_KEY_HELPDESK_NEW_TICKET",
    "MAIL_TEMPLATE_KEY_RESOLUTION",
    "MAIL_TEMPLATE_KEY_SPECIALIST_ASSIGNMENT",
    "MAIN_STATUS_SEQUENCE",
    "PRIORIDAD_MAP",
    "REPLY_BLOCKED_ESTADOS",
    "RESOLUTION_BODY_SETTING_KEY",
    "RESOLUTION_SLA_MINUTES",
    "RESOLUTION_SUBJECT_SETTING_KEY",
    "RESUELTO_AUTO_CLOSE_HOURS",
    "RETENTION_POLICY_DAYS",
    "ROLES_ADMIN_GESTION",
    "ROLES_DESPACHO_MESA",
    "ROLES_TECNICOS",
    "ROLES_TECNICOS_SET",
    "ROLE_SPECIALTY_FALLBACK",
    "SEVERIDADES_VALIDAS",
    "SLA_BUSINESS_DAYS",
    "SLA_BUSINESS_END_HOUR",
    "SLA_BUSINESS_START_HOUR",
    "SLA_BUSINESS_TZ",
    "SLA_ESCALATION_WINDOWS_PCT",
    "SLA_HORAS",
    "SLA_MODE",
    "SLA_STORAGE_HOURS",
    "SPECIALIST_ASSIGNMENT_BODY_SETTING_KEY",
    "SPECIALIST_ASSIGNMENT_SUBJECT_SETTING_KEY",
    "SUBESTADOS_ESPERA",
    "SUBESTADOS_LEGACY_MAP",
    "SUBESTADOS_VALIDOS",
    "TICKETERA_MAIL_TEMPLATE_DEFS",
    "TICKET_EMAIL_ALLOWED_ESTADOS",
    "TICKET_EMAIL_BLOCKED_ESTADOS",
    "TICKET_PUBLIC_CODE_START",
    "TICKET_READONLY_ESTADOS",
    "TICKET_SECURITY_CLASSES",
    "TIPOS_TICKET_VALIDOS",
    "TTR_MINUTOS",
    "WORKFLOW_RULES",
    "_IncomingEmailHtmlSanitizer",
    "_add_business_minutes",
    "_align_to_business_start",
    "_append_specialist_sla_note",
    "_attachment_roots",
    "_attachment_storage_name",
    "_auto_reply_allowlist_domains",
    "_auto_reply_allowlist_emails",
    "_auto_reply_blocked_localparts",
    "_auto_reply_delay_minutes",
    "_auto_reply_idempotency_key",
    "_auto_reply_require_allowlist",
    "_auto_reply_sender_allowed",
    "_build_chain_hash",
    "_build_ticket_reply_subject",
    "_business_bounds",
    "_can_dispatch_reassign",
    "_channel_adapter_mode",
    "_channel_provider_name",
    "_channel_retry_delay_seconds",
    "_channels_enabled",
    "_clamp_int",
    "_compose_reply_recipients",
    "_db_bool",
    "_default_compliance_export_dir",
    "_default_ticket_attachments_dir",
    "_draft_lock_info",
    "_drafts_base_path",
    "_enqueue_job_async_safe",
    "_ensure_can_manage_ticket",
    "_ensure_can_manage_ticket_trash",
    "_ensure_can_participate_ticket",
    "_ensure_reply_allowed_estado",
    "_ensure_ticket_not_trashed",
    "_ensure_utc",
    "_estado_label",
    "_extract_email_domain",
    "_extract_ticket_target_email",
    "_format_assignee_name",
    "_format_sla_minutes_label",
    "_frt_due_iso",
    "_get_system_setting",
    "_get_ticketera_mail_template_def",
    "_google_chat_assignment_text",
    "_hash_draft_lock_token",
    "_is_admin_management_role",
    "_is_business_day",
    "_is_dispatcher_role",
    "_is_draft_lock_active",
    "_is_readonly_blocked_by_estado",
    "_is_reply_blocked_by_estado",
    "_is_safe_attachment_path",
    "_is_tech_role",
    "_lock_expiry_iso",
    "_new_draft_lock_token",
    "_normalize_email_address",
    "_normalize_email_route_match_value",
    "_normalize_notify_emails",
    "_normalize_recipient_emails",
    "_normalize_role",
    "_normalize_roles",
    "_normalize_username",
    "_notify_emails_from_ticket",
    "_now_dt",
    "_parse_business_days",
    "_parse_csv_lower_set",
    "_parse_dt",
    "_parse_escalation_windows",
    "_parse_secondary_roles_value",
    "_parse_timezone_name",
    "_parse_tz_offset",
    "_recompute_ticket_retention",
    "_render_text_template",
    "_render_ticketera_mail_body_html",
    "_render_ticketera_mail_subject",
    "_render_ticketera_mail_template",
    "_resolve_helpdesk_new_ticket_recipients",
    "_resolve_routing_category_for_email",
    "_retention_days_for_class",
    "_retention_until_iso",
    "_scope_enforced",
    "_send_ticket_status_update_to_notify_emails",
    "_sender_identity",
    "_serialize_email_route_row",
    "_serialize_notify_emails",
    "_serialize_ticketera_mail_template",
    "_sha256_file",
    "_stable_json",
    "_ticket_assignee_username",
    "_ticket_display_status",
    "_ticket_is_trashed",
    "_ticket_sla_summary_label",
    "_ticketera_template_context",
    "_ticketera_template_text_to_html",
    "_tokenize_email_values",
    "_ttr_due_iso",
    "_upsert_system_setting",
    "delete_ticketera_routing_rule",
    "estado_from_subestado",
    "get_monthly_report_data",
    "get_ticketera_admin_config",
    "get_ticketera_mail_template",
    "get_ticketera_templates",
    "list_ticketera_mail_templates",
    "list_ticketera_routing_rules",
    "normalize_adapter_mode",
    "normalize_channel_name",
    "normalize_notification_status",
    "normalize_subestado",
    "normalize_ticket_security_class",
    "normalize_ticket_type",
    "notify_client_assignment",
    "notify_helpdesk_new_ticket",
    "notify_specialist_assignment",
    "update_ticketera_mail_template",
    "update_ticketera_templates",
    "upsert_ticketera_routing_rule",
]


# ==========================================================================
# CONSTANTES
# ==========================================================================
CATEGORIAS_VALIDAS = {"redes", "sistemas", "ejecucion", "admin", "general", "bodega", "gerencia"}
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
    # Bodega: seleccionable manualmente en los tickets (la UI lo muestra como "Bodega").
    # No es rol técnico, así que NO entra en la auto-asignación por categoría.
    "warehouse": "warehouse",
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
        # Sanitizer de atributos: definido en _crud (que hace 'from ._helpers import *').
        # Import perezoso para evitar el ciclo (mismo patrón que 'from ._crud import get_ticket').
        from ._crud import _sanitize_incoming_email_attr
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
    return str(Path(__file__).resolve().parent.parent / "data" / "compliance")

def _default_ticket_attachments_dir() -> str:
    return str(Path(__file__).resolve().parent.parent / "data" / "tickets")

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
    t = ticket or {}
    estado = str(t.get("estado") or "").strip().lower()
    # Si el ticket está esperando algo (subestado de espera: pendiente_cliente/compra/
    # tercero/gerencia), mostramos ESE subestado real y no el genérico 'en_progreso':
    # el ticket no está avanzando, está pendiente de algo. Aplica en lista y detalle.
    subestado = normalize_subestado(t.get("subestado"), estado)
    if subestado in SUBESTADOS_ESPERA:
        return subestado
    return estado

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
        "ticket_code": str(ticket.get("codigo") or (f"TK-{TICKET_PUBLIC_CODE_START + ticket_id - 1}" if ticket_id > 0 else "Ticket") or "Ticket").strip() or "Ticket",
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


def get_atendidos_report(period: str = "day", customer_id: str = None,
                         resolved_after: str = None, resolved_before: str = None) -> Dict[str, Any]:
    """Reporte de tickets ATENDIDOS (resuelto/cerrado) agrupados por período
    (day/week/month) según resolved_at, opcionalmente filtrado por cliente."""
    bucket = {"day": "day", "week": "week", "month": "month"}.get((period or "day").lower(), "day")
    where = ["estado IN ('resuelto', 'cerrado')", "resolved_at IS NOT NULL",
             "COALESCE(is_trashed, FALSE) = FALSE"]
    params = []
    if resolved_after:
        where.append("resolved_at >= ?"); params.append(resolved_after)
    if resolved_before:
        where.append("resolved_at < ?"); params.append(resolved_before)
    if customer_id:
        where.append("LOWER(COALESCE(customer_id, '')) = ?"); params.append(str(customer_id).strip().lower())
    wsql = " AND ".join(where)
    conn = db.get_conn()
    try:
        series = conn.execute(
            f"""SELECT date_trunc('{bucket}', resolved_at::timestamptz) AS bucket, COUNT(*) AS total
                FROM tickets WHERE {wsql} GROUP BY 1 ORDER BY 1""",
            tuple(params),
        ).fetchall()
        by_customer = conn.execute(
            f"""SELECT COALESCE(cliente_nombre, 'Sin Cliente / Directo') AS nombre, COUNT(*) AS total
                FROM tickets WHERE {wsql} GROUP BY cliente_nombre ORDER BY total DESC LIMIT 100""",
            tuple(params),
        ).fetchall()
        total_row = conn.execute(f"SELECT COUNT(*) AS total FROM tickets WHERE {wsql}", tuple(params)).fetchone()
        return {
            "period": bucket,
            "total": int(dict(total_row)["total"]) if total_row else 0,
            "series": [{"bucket": str(r["bucket"])[:10], "total": int(r["total"])} for r in series],
            "by_customer": [dict(r) for r in by_customer],
            "generated_at": db.now_utc_iso(),
        }
    finally:
        conn.close()

def get_clientes_resumen() -> Dict[str, Any]:
    """Resumen por cliente para la pestaña Reportes: una fila por cliente con
    tickets activos (no cerrados/resueltos), creados este mes y cerrados/resueltos."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(customer_id), ''), NULLIF(TRIM(cliente_nombre), ''), '') AS cliente_key,
                COALESCE(MAX(NULLIF(TRIM(cliente_nombre), '')), 'Sin Cliente / Directo') AS customer_name,
                COUNT(*) FILTER (WHERE estado NOT IN ('cerrado', 'resuelto')) AS activos,
                COUNT(*) FILTER (WHERE created_at::timestamptz >= ?::timestamptz) AS este_mes,
                COUNT(*) FILTER (WHERE estado IN ('cerrado', 'resuelto')) AS cerrados,
                COUNT(*) AS total
            FROM tickets
            WHERE COALESCE(is_trashed, FALSE) = FALSE
            GROUP BY COALESCE(NULLIF(TRIM(customer_id), ''), NULLIF(TRIM(cliente_nombre), ''), '')
            ORDER BY activos DESC, cerrados DESC, customer_name ASC
            """,
            (month_start,),
        ).fetchall()
        clientes = []
        for r in rows:
            d = dict(r)
            clientes.append({
                "customer_id": str(d.get("cliente_key") or "").strip(),
                "customer_name": str(d.get("customer_name") or "").strip() or "Sin Cliente / Directo",
                "activos": int(d.get("activos") or 0),
                "este_mes": int(d.get("este_mes") or 0),
                "cerrados": int(d.get("cerrados") or 0),
                "total": int(d.get("total") or 0),
            })
        return {"clientes": clientes, "generated_at": db.now_utc_iso()}
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
        "customer_id": str(row.get("customer_id") or "").strip(),
        "customer_name": str(row.get("customer_name") or "").strip(),
    }

def list_ticketera_routing_rules(*, only_active: bool = False) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        where = "WHERE is_active = true" if only_active else ""
        rows = conn.execute(
            f"""SELECT id, match_type, match_value, categoria, is_active, created_by, created_at, updated_at, customer_id, customer_name
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
    if normalized_categoria and normalized_categoria not in CATEGORIAS_VALIDAS:
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
                       customer_id = ?,
                       customer_name = ?,
                       updated_at = ?
                   WHERE id = ?""",
                (
                    normalized_type,
                    normalized_value,
                    normalized_categoria,
                    bool(is_active),
                    customer_id or None,
                    customer_name or None,
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
                """SELECT id, match_type, match_value, categoria, is_active, created_by, created_at, updated_at, customer_id, customer_name
                   FROM ticket_config_email_routes
                   WHERE id = ?
                   LIMIT 1""",
                (target_rule_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT id, match_type, match_value, categoria, is_active, created_by, created_at, updated_at, customer_id, customer_name
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
    from ._crud import get_ticket  # noqa: PLC0415 — lazy import to avoid circular
    from ._email import _build_ticket_thread_headers, _update_ticket_thread_metadata  # noqa: PLC0415
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

def _google_chat_assignment_text(username: str, ticket: Dict[str, Any]) -> str:
    codigo = ticket.get("codigo") or f"#{ticket.get('id', '?')}"
    titulo = ticket.get("titulo") or "Sin título"
    severidad = ticket.get("severidad") or "-"
    return f"🎫 *Nuevo ticket asignado* [{codigo}]\n*{titulo}*\nSeveridad: {severidad}\nAsignado a: {username}"


def notify_specialist_assignment(username: str, ticket: Dict[str, Any]) -> None:
    """Notifica al especialista por correo y Google Chat sobre su nueva asignación."""
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
        logger.error(f"[AssignmentNotify] Specialist email fail user={username}: {e}")

    # Google Chat DM al especialista
    bot_token = str(getattr(app_settings, "GOOGLE_CHAT_BOT_TOKEN", "") or "").strip()
    if bot_token:
        try:
            google_chat.send_dm(bot_token, username, _google_chat_assignment_text(username, ticket))
        except Exception as e:
            logger.error(f"[AssignmentNotify] Google Chat DM fail user={username}: {e}")

    # Google Chat al espacio compartido
    space_webhook = str(getattr(app_settings, "GOOGLE_CHAT_SPACE_WEBHOOK", "") or "").strip()
    if space_webhook:
        try:
            google_chat.send_space_message(space_webhook, _google_chat_assignment_text(username, ticket))
        except Exception as e:
            logger.error(f"[AssignmentNotify] Google Chat space fail ticket={ticket_id}: {e}")

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
    from ._email import _build_ticket_thread_headers, _update_ticket_thread_metadata  # noqa: PLC0415
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
    if s in {"en_progreso", "en_ejecucion", "en_validacion", "aprobado",
             "pendiente_cliente", "pendiente_compra", "pendiente_tercero",
             "pendiente_gerencia", "pendiente_aprobacion_1", "pendiente_aprobacion_2"}:
        # Subestados de espera/aprobación: el ticket sigue "en progreso", no rebota a abierto.
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
    if raw in {"app", "google_chat"}:
        return raw
    return ""

def normalize_notification_status(value: Optional[str], default_status: str = "pending") -> str:
    status = (value or default_status).strip().lower()
    if status not in CHANNEL_NOTIFICATION_STATUSES:
        return default_status
    return status

def _channel_adapter_mode(channel: str) -> str:
    normalized = normalize_channel_name(channel)
    if normalized == "google_chat":
        return normalize_adapter_mode(getattr(app_settings, "GOOGLE_CHAT_ADAPTER_MODE", "disabled"), "disabled")
    return "disabled"

def _channel_provider_name(channel: str) -> str:
    normalized = normalize_channel_name(channel)
    if normalized == "google_chat":
        return "google_chat_http"
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

