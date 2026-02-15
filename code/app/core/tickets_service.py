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
from email.utils import parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo
from app.core import email_integration, email as email_sender, jobs_engine
from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)

# ==========================================================================
# CONSTANTES
# ==========================================================================
CATEGORIAS_VALIDAS = {"redes", "sistemas", "ejecucion", "admin", "general"}
ESTADOS_VALIDOS = {"abierto", "en_progreso", "resuelto", "cerrado"}
SEVERIDADES_VALIDAS = {"baja", "media", "alta", "critica"}
ROLES_TECNICOS = ("redes", "sistemas", "implementaciones", "ops")
TICKET_SECURITY_CLASSES = {"public", "internal", "restricted"}
TIPOS_TICKET_VALIDOS = {"incidencia", "requerimiento", "cambio"}
SUBESTADOS_VALIDOS = {
    "nuevo",
    "triage",
    "en_analisis",
    "pendiente_cliente",
    "pendiente_aprobacion_1",
    "pendiente_aprobacion_2",
    "aprobado",
    "rechazado",
    "en_ejecucion",
    "en_validacion",
    "reabierto",
    "en_progreso",
    "resuelto",
    "cerrado",
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

WORKFLOW_RULES: Dict[str, Dict[str, List[str]]] = {
    "incidencia": {
        "nuevo": ["triage"],
        "triage": ["en_progreso"],
        "en_progreso": ["resuelto"],
        "resuelto": ["cerrado", "reabierto"],
        "cerrado": ["reabierto"],
        "reabierto": ["triage", "en_progreso"],
    },
    "requerimiento": {
        "nuevo": ["en_analisis"],
        "en_analisis": ["en_progreso"],
        "en_progreso": ["en_validacion"],
        "en_validacion": ["cerrado", "reabierto"],
        "cerrado": ["reabierto"],
        "reabierto": ["en_analisis", "en_progreso"],
    },
    "cambio": {
        "nuevo": ["en_analisis"],
        "en_analisis": ["pendiente_aprobacion_1"],
        "pendiente_aprobacion_1": ["pendiente_aprobacion_2", "rechazado"],
        "pendiente_aprobacion_2": ["aprobado", "rechazado"],
        "aprobado": ["en_ejecucion"],
        "en_ejecucion": ["en_validacion"],
        "en_validacion": ["cerrado", "reabierto"],
        "rechazado": ["en_analisis"],
        "cerrado": ["reabierto"],
        "reabierto": ["en_analisis", "en_ejecucion"],
    },
}

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


def normalize_ticket_security_class(value: Optional[str]) -> str:
    normalized = (value or "internal").strip().lower()
    if normalized not in TICKET_SECURITY_CLASSES:
        return "internal"
    return normalized


def normalize_ticket_type(value: Optional[str]) -> str:
    normalized = (value or "incidencia").strip().lower()
    if normalized not in TIPOS_TICKET_VALIDOS:
        return "incidencia"
    return normalized


def normalize_subestado(value: Optional[str], default_value: str = "nuevo") -> str:
    normalized = (value or default_value).strip().lower()
    if normalized not in SUBESTADOS_VALIDOS:
        return default_value
    return normalized


def estado_from_subestado(subestado: str, current_estado: str = "abierto") -> str:
    s = normalize_subestado(subestado, "nuevo")
    if s in {"resuelto"}:
        return "resuelto"
    if s in {"cerrado"}:
        return "cerrado"
    if s in {"en_progreso", "en_ejecucion", "en_validacion", "aprobado", "reabierto"}:
        return "en_progreso"
    if current_estado in ESTADOS_VALIDOS and current_estado in {"resuelto", "cerrado"} and s == "reabierto":
        return "en_progreso"
    return "abierto"


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
                (ticket_id, user_id, channel, status, escalation_level, scheduled_at, created_at)
                VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """, (ticket_id, user_id, channel, level, scheduled.isoformat(), now_iso))

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


async def process_pending_notifications(payload: Dict[str, Any] = None):
    """
    Busca notificaciones pendientes (scheduled_at <= now, status=pending)
    y encola los jobs correspondientes (WHATSAPP_NOTIFY, 3CX_CALL).
    Si payload['recurring'] is True, se re-agenda a si mismo.
    """
    payload = payload or {}
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        # Seleccionar pendientes vencidos
        rows = conn.execute("""
            SELECT tn.id, tn.channel, tn.user_id, u.phone_number, t.codigo, t.titulo
            FROM ticket_notifications tn
            JOIN tickets t ON t.id = tn.ticket_id
            JOIN users u ON u.username = tn.user_id
            WHERE tn.status = 'pending' 
              AND tn.channel IN ('whatsapp', '3cx')
              AND tn.scheduled_at <= ?
            LIMIT 50
        """, (now,)).fetchall()

        if rows:
            from app.core import jobs_engine
            
            for r in rows:
                notif_id = r["id"]
                channel = r["channel"]
                phone = r["phone_number"]
                
                if not phone:
                    logger.warning(f"User {r['user_id']} has no phone for {channel} notification")
                    conn.execute("UPDATE ticket_notifications SET status='failed', seen_at=? WHERE id=?", (now, notif_id))
                    continue

                try:
                    if channel == "whatsapp":
                        msg = f"Ticket {r['codigo']}: {r['titulo']} requiere tu atención."
                        asyncio.create_task(jobs_engine.enqueue_job(
                            "WHATSAPP_NOTIFY", 
                            {"phone": phone, "message": msg, "notification_id": notif_id}
                        ))
                    elif channel == "3cx":
                        asyncio.create_task(jobs_engine.enqueue_job(
                            "3CX_CALL", 
                            {"phone": phone, "notification_id": notif_id}
                        ))
                    
                    conn.execute("UPDATE ticket_notifications SET status='sent', seen_at=? WHERE id=?", (now, notif_id))
                    
                except Exception as e:
                    logger.error(f"Error enququeing notification {notif_id}: {e}")
            conn.commit()
                    


        # Reschedule if recurring
        if payload.get("recurring"):
            from app.core import jobs_engine
            # Re-enqueue process
            await jobs_engine.enqueue_job("PROCESS_NOTIFICATIONS", {"recurring": True}, max_retries=0)
            
            # Delay next run by 60 seconds
            delay_seconds = 60
            next_run = (db.datetime.utcnow() + db.timedelta(seconds=delay_seconds)).isoformat()
            
            # Update the job we just inserted (highest ID for this type) to set correct next_run_at
            # Note: This relies on no other concurrent inserts stealing the 'MAX(id)'. 
            # In single worker scenarios this is fine.
            conn.execute(
                "UPDATE sys_jobs SET next_run_at = ? WHERE id = (SELECT MAX(id) FROM sys_jobs WHERE job_type='PROCESS_NOTIFICATIONS')", 
                (next_run,)
            )
            conn.commit()

    finally:
        conn.close()

    # Re-schedule logic is now inside try block to ensure it happens if no critical DB error prevents commit.
    # If critical error happens, we might lose the chain, which is acceptable for now vs infinite error loop.


# ==========================================================================
# GENERADOR DE CÓDIGO DE TICKET
# ==========================================================================
def generar_codigo(ticket_id: int) -> str:
    """Genera código TK-DD-MM-YYYY-NNNN."""
    now = datetime.now()
    return f"TK-{now.strftime('%d-%m-%Y')}-{ticket_id:04d}"


def _workflow_next(tipo: str, subestado: str) -> List[str]:
    rules = WORKFLOW_RULES.get(normalize_ticket_type(tipo), WORKFLOW_RULES["incidencia"])
    return list(rules.get(normalize_subestado(subestado), []))


def _workflow_can_transition(tipo: str, from_subestado: str, to_subestado: str) -> bool:
    allowed = _workflow_next(tipo, from_subestado)
    return normalize_subestado(to_subestado) in allowed


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


def _emit_system_comment(conn, ticket_id: int, content: str, now_iso: str) -> None:
    conn.execute(
        """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
           VALUES (?, 'system', ?, ?)""",
        (ticket_id, content, now_iso),
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
        """SELECT id, estado, created_at, updated_at, first_response_at, frt_due_at, ttr_due_at,
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
    created_dt = _parse_dt(t.get("created_at"))
    frt_due_dt = _parse_dt(t.get("frt_due_at"))
    ttr_due_dt = _parse_dt(t.get("ttr_due_at")) or _parse_dt(t.get("vence_at"))
    first_response_dt = _parse_dt(t.get("first_response_at"))
    resolved_dt = _parse_dt(t.get("resolved_at")) or _parse_dt(t.get("updated_at"))
    estado = (t.get("estado") or "").lower()

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
    subestado: Optional[str] = None,
    ticket_security_class: Optional[str] = "internal",
) -> Dict[str, Any]:
    """Crear un nuevo ticket con auto-clasificación y auto-asignación."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        # Normalizar severidad
        severidad = severidad.lower() if severidad else "media"
        if severidad not in SEVERIDADES_VALIDAS:
            severidad = "media"

        # Auto-clasificar si no se especifica categoría
        if not categoria or categoria not in CATEGORIAS_VALIDAS:
            categoria = clasificar_ticket(titulo, descripcion)

        # Normalizar tipo
        tipo = normalize_ticket_type(tipo)

        # Calcular SLA
        now_dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        sla_horas = SLA_HORAS.get(severidad, 72)
        ttr_due_at = _ttr_due_iso(now_dt, severidad)
        frt_due_at = _frt_due_iso(now_dt, severidad)
        vence_at = ttr_due_at
        subestado = normalize_subestado(subestado, "nuevo")

        # Prioridad numérica
        prioridad = PRIORIDAD_MAP.get(severidad, 3)
        security_class = normalize_ticket_security_class(ticket_security_class)
        retention_days = _retention_days_for_class(security_class)

        # Auto-asignar (no-crítico: si falla, ticket se crea sin asignar)
        asignado_a = None
        try:
            asignado_a = auto_asignar(categoria)
        except Exception as e:
            logger.warning(f"[create_ticket] auto_asignar falló para categoría '{categoria}': {e}")

        cursor = conn.execute(
            """INSERT INTO tickets
               (titulo, descripcion, estado, severidad, tipo, creador_id,
                asignado_a, vence_at, created_at, updated_at,
                categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id,
                ticket_security_class, retention_days_snapshot, subestado, frt_due_at, ttr_due_at)
               VALUES (?, ?, 'abierto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (titulo, descripcion, severidad, tipo, creador_id,
             asignado_a, vence_at, now, now,
             categoria, origen_email, cliente_nombre, prioridad, sla_horas, email_thread_id,
             security_class, retention_days, subestado, frt_due_at, ttr_due_at)
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
               VALUES (?, 'system', ?, ?)""",
            (ticket_id, f"[CREACION] Ticket creado. Tipo: {tipo}. Categoría: {categoria}. Severidad: {severidad}.", now)
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
                   VALUES (?, 'system', ?, ?)""",
                (ticket_id, f"[ASIGNACION] Auto-asignado a {asignado_a} (especialidad: {categoria})", now)
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
        _evaluate_ticket_sla(conn, ticket_id, db.now_utc_iso())
        conn.commit()
        refreshed = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return _hydrate_ticket_runtime(dict(refreshed)) if refreshed else _hydrate_ticket_runtime(dict(row))
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
                prioridad, email_thread_id, resolucion, sla_horas_bak, sla_horas,
                subestado, frt_due_at, ttr_due_at, first_response_at, resolved_at,
                frt_breached_at, ttr_breached_at, ticket_security_class,
                retention_until, retention_days_snapshot
            """
        )

        # Obtener items
        items_params = params + [limit, offset]
        cursor = conn.execute(
            f"SELECT {select_fields} FROM tickets WHERE {where_sql} ORDER BY prioridad ASC, created_at DESC LIMIT ? OFFSET ?",
            items_params
        )
        raw_items = [dict(row) for row in cursor.fetchall()]
        now_iso = db.now_utc_iso()
        for item in raw_items:
            _evaluate_ticket_sla(conn, int(item["id"]), now_iso)
        conn.commit()

        cursor = conn.execute(
            f"SELECT {select_fields} FROM tickets WHERE {where_sql} ORDER BY prioridad ASC, created_at DESC LIMIT ? OFFSET ?",
            items_params,
        )
        now_dt = _parse_dt(now_iso) or _now_dt()
        items = [_hydrate_ticket_runtime(dict(row), now_dt=now_dt) for row in cursor.fetchall()]

        return {"items": items, "total": total if include_total else len(items)}
    finally:
        conn.close()


def update_ticket(ticket_id: int, updates: Dict[str, Any], actor_id: str = "system") -> Optional[Dict[str, Any]]:
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
                normalized_updates[key] = estado
            continue
        if key == "subestado":
            normalized_updates[key] = normalize_subestado(value, current.get("subestado") or "nuevo")
            continue
        if key == "severidad":
            sev = str(value or "").strip().lower()
            normalized_updates[key] = sev if sev in SEVERIDADES_VALIDAS else current.get("severidad", "media")
            continue
        if key == "ticket_security_class":
            normalized_updates[key] = normalize_ticket_security_class(value)
            continue
        normalized_updates[key] = value

    if "subestado" in normalized_updates and "estado" not in normalized_updates:
        normalized_updates["estado"] = estado_from_subestado(
            normalized_updates["subestado"],
            str(current.get("estado") or "abierto"),
        )

    keys_to_update = list(normalized_updates.keys())
    if not keys_to_update:
        return get_ticket(ticket_id)

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        now_dt = _parse_dt(now) or _now_dt()
        set_clause = ", ".join([f"{k} = ?" for k in keys_to_update]) + ", updated_at = ?"
        params = [normalized_updates[k] for k in keys_to_update] + [now, ticket_id]

        cursor = conn.execute(f"UPDATE tickets SET {set_clause} WHERE id = ?", params)
        if cursor.rowcount == 0:
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
                )

        if "estado" in normalized_updates:
            new_estado = normalized_updates["estado"]
            _emit_system_comment(conn, ticket_id, f"[CAMBIO_ESTADO] Estado cambiado a {new_estado}", now)
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
            _emit_system_comment(conn, ticket_id, f"[REASIGNACION] Reasignado a {new_asignado}", now)
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
            )

        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        return get_ticket(ticket_id)
    finally:
        conn.close()


def add_comment(ticket_id: int, user_id: str, content: str, event_type: str = "comentario") -> Dict[str, Any]:
    """Agregar un comentario/evento al ticket."""
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


def transition_ticket(
    ticket_id: int,
    to_subestado: str,
    actor_id: str,
    motivo: str = "",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")

    tipo = normalize_ticket_type(ticket.get("tipo"))
    from_sub = normalize_subestado(ticket.get("subestado"), "nuevo")
    target_sub = normalize_subestado(to_subestado, from_sub)
    normalized_idem = (idempotency_key or "").strip()[:128] or None

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
        conn.execute(
            """UPDATE tickets
               SET subestado = ?, estado = ?, updated_at = ?,
                   resolved_at = CASE
                       WHEN ? IN ('resuelto','cerrado') THEN COALESCE(resolved_at, ?)
                       WHEN ? = 'reabierto' THEN NULL
                       ELSE resolved_at
                   END
               WHERE id = ?""",
            (target_sub, new_estado, now, new_estado, now, target_sub, ticket_id),
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
        )
        if target_sub in {"resuelto", "cerrado"} and ticket.get("asignado_a"):
            decrementar_carga(str(ticket["asignado_a"]), specialty=ticket.get("categoria"))
        _recompute_ticket_retention(conn, ticket_id)
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
        return {
            "ok": True,
            "transition_id": int(transition_row["id"]) if transition_row else None,
            "ticket": get_ticket(ticket_id),
        }
    finally:
        conn.close()


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

    role_norm = (approver_role or "").strip().lower()
    step1_roles = {"admin", "implementaciones", "redes", "sistemas", "ops"}
    step2_roles = {"admin", "finance", "gerencia"}
    allowed_roles = step1_roles if step == 1 else step2_roles
    if role_norm not in allowed_roles:
        raise ValueError(f"El rol '{approver_role}' no está autorizado para aprobar paso {step}.")

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

        current_sub = normalize_subestado(ticket.get("subestado"), "nuevo")
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
    sub = normalize_subestado(ticket.get("subestado"), "nuevo")
    allowed_next = _workflow_next(tipo, sub)
    if tipo == "cambio":
        if latest_approvals.get(1) != "approved":
            allowed_next = [s for s in allowed_next if s not in {"pendiente_aprobacion_2", "aprobado", "en_ejecucion"}]
        if latest_approvals.get(2) != "approved":
            allowed_next = [s for s in allowed_next if s not in {"aprobado", "en_ejecucion"}]

    return {
        "ticket": ticket,
        "allowed_next": allowed_next,
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

    clean_msg = (mensaje or "").strip()
    if not clean_msg:
        logger.error(f"Reply failed: Message empty for ticket {ticket_id}")
        raise ValueError("El mensaje de respuesta está vacío")

    _, parsed_addr = parseaddr(ticket.get("origen_email") or "")
    to_email = parsed_addr.strip() if parsed_addr else (ticket.get("origen_email") or "").strip()
    if not to_email or "@" not in to_email:
        logger.error(f"Reply failed: Invalid to_email '{to_email}' for ticket {ticket_id}")
        raise ValueError("Este ticket no tiene un correo de cliente válido")

    if asunto and asunto.strip():
        subject = asunto.strip()
    else:
        base = ticket.get("codigo") or f"Ticket #{ticket_id}"
        title = (ticket.get("titulo") or "").strip()
        subject = f"{base} - {title}" if title else base
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    thread_id = (ticket.get("email_thread_id") or "").strip()
    headers = {}
    if thread_id:
        headers["In-Reply-To"] = thread_id
        headers["References"] = thread_id

    escaped_msg = html.escape(clean_msg).replace("\n", "<br>")
    body_html = f"""
    <p>Hola,</p>
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
        base_path = Path(app_settings.TICKET_ATTACHMENTS_DIR) / str(ticket_id) / "attachments"
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
                safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
                file_path = base_path / f"{int(datetime.utcnow().timestamp())}_{safe_filename}"
                
                with open(file_path, "wb") as f:
                    f.write(file_content)
                    
                email_attachments.append({
                    "filename": filename,
                    "data": file_content,
                    "content_type": getattr(file, "content_type", "application/octet-stream")
                })
                
                stored_attachments.append({
                    "filename": filename,
                    "path": str(file_path),
                    "size": len(file_content),
                    "content_type": getattr(file, "content_type", "application/octet-stream")
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
                    "subject": subject,
                    "threaded": bool(thread_id),
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
            (ticket_id, to_email, subject, body_html, dedupe_since),
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
                "subject": subject,
                "threaded": bool(thread_id),
                "duplicate_skipped": True,
                "message": "Se evitó un envío duplicado (correo ya enviado recientemente).",
            }

        marker_row = lock_conn.execute(
            """INSERT INTO ticket_emails
               (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, idempotency_key, created_at)
               VALUES (?, 'outgoing_pending', '', ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (ticket_id, to_email, subject, body_html, json.dumps(stored_attachments), normalized_idempotency_key, now),
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
        raise ValueError(str(e))

    conn = db.get_conn()
    try:
        if marker_id:
            conn.execute(
                """UPDATE ticket_emails
                   SET direction = 'outgoing', from_addr = ?
                   WHERE id = ?""",
                (send_meta.get("from_addr"), marker_id),
            )
        else:
            conn.execute(
                """INSERT INTO ticket_emails
                   (ticket_id, direction, from_addr, to_addr, subject, body_html, attachments_json, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    "outgoing",
                    send_meta.get("from_addr"),
                    to_email,
                    subject,
                    body_html,
                    json.dumps(stored_attachments),
                    normalized_idempotency_key,
                    now,
                ),
            )
        
        has_attachments = " (con adjuntos)" if stored_attachments else ""
        conn.execute(
            """INSERT INTO ticket_comments (ticket_id, user_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, author_id, f"[CORREO] Respuesta enviada a {to_email}{has_attachments}: {preview}", now),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        _maybe_mark_first_response(conn, ticket_id, author_id, now)

        # Si el envío salió con Message-ID, lo usamos como referencia para próximos replies.
        msg_id = send_meta.get("message_id")
        if msg_id:
            # EN PROD EL MESSAGE-ID DEBERIA SER "FIJO" POR TICKET O ASOCIADO AL HILO
            # Pero por ahora mantenemos la lógica de actualizar con el último msg_id
            conn.execute("UPDATE tickets SET email_thread_id = ? WHERE id = ?", (msg_id, ticket_id))

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
                "threaded": bool(thread_id),
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
        "subject": subject,
        "threaded": bool(thread_id),
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
                    "created_at": row.get("created_at"),
                    "body_text": body_text,
                    "preview": body_text[:280] + ("..." if len(body_text) > 280 else ""),
                    "attachments": attachments,
                }
            )
        return out
    finally:
        conn.close()


def upload_ticket_attachments(ticket_id: int, uploaded_by: str, files: Optional[List[Any]]) -> Dict[str, Any]:
    """Sube adjuntos manuales al ticket y devuelve metadata con hash/size."""
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError("Ticket no encontrado")
    if not files:
        return {"ok": True, "ticket_id": ticket_id, "uploaded": 0, "items": list_ticket_attachments(ticket_id)}

    base_path = Path(app_settings.TICKET_ATTACHMENTS_DIR) / str(ticket_id) / "manual"
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
            safe_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
            file_path = base_path / f"{int(datetime.utcnow().timestamp())}_{safe_filename}"
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


def get_timeline(ticket_id: int, limit: int = 120) -> List[Dict[str, Any]]:
    """Línea de tiempo unificada para la UI."""
    conn = db.get_conn()
    try:
        limit = max(1, min(int(limit or 120), 500))
        cursor = conn.execute(
            "SELECT * FROM ticket_comments WHERE ticket_id = ? ORDER BY created_at DESC LIMIT ?",
            (ticket_id, limit)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            content = r["content"]
            event_name = "Nota"
            detail = content
            
            if content.startswith("["):
                parts = content.split("]", 1)
                event_name = parts[0][1:].capitalize()
                detail = parts[1].strip()

            result.append({
                "creado_at": r["created_at"],
                "evento": event_name,
                "detalle": detail,
                "usuario": r["user_id"]
            })
        return result
    finally:
        conn.close()


def get_stats() -> Dict[str, Any]:
    """Obtener métricas para Dashboard."""
    conn = db.get_conn()
    try:
        stats = {
            "by_status": {},
            "by_prio": {},
            "by_category": {},
            "pivot_assignee": {},
            "sla_compliance": {"on_time": 0, "breached": 0},
            "total": 0,
        }

        # Por Estado
        rows = conn.execute("SELECT estado, COUNT(*) as c FROM tickets GROUP BY estado").fetchall()
        for r in rows:
            stats["by_status"][r["estado"]] = r["c"]
            stats["total"] += r["c"]

        # Por Severidad
        rows = conn.execute("SELECT severidad, COUNT(*) as c FROM tickets GROUP BY severidad").fetchall()
        for r in rows:
            stats["by_prio"][r["severidad"]] = r["c"]

        # Por Categoría
        rows = conn.execute("SELECT categoria, COUNT(*) as c FROM tickets GROUP BY categoria").fetchall()
        for r in rows:
            stats["by_category"][r["categoria"] or "general"] = r["c"]

        # Pivot: Assignee vs Status
        rows = conn.execute(
            "SELECT asignado_a, estado, COUNT(*) as c FROM tickets GROUP BY asignado_a, estado"
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
        row = conn.execute("""
            SELECT
                COUNT(CASE WHEN vence_at >= ? OR estado IN ('cerrado','resuelto') THEN 1 END) as on_time,
                COUNT(CASE WHEN vence_at < ? AND estado NOT IN ('cerrado','resuelto') THEN 1 END) as breached
            FROM tickets WHERE vence_at IS NOT NULL
        """, (now, now)).fetchone()
        if row:
            stats["sla_compliance"]["on_time"] = row["on_time"]
            stats["sla_compliance"]["breached"] = row["breached"]

        return stats
    finally:
        conn.close()


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

        # Snapshot de breaches para trazabilidad persistente.
        conn.execute(
            """UPDATE tickets
               SET frt_breached_at = COALESCE(frt_breached_at, ?)
               WHERE first_response_at IS NULL
                 AND frt_due_at IS NOT NULL
                 AND frt_due_at::timestamptz < ?::timestamptz""",
            (now_iso, now_iso),
        )
        conn.execute(
            """UPDATE tickets
               SET ttr_breached_at = COALESCE(ttr_breached_at, ?)
               WHERE estado NOT IN ('resuelto','cerrado')
                 AND ttr_due_at IS NOT NULL
                 AND ttr_due_at::timestamptz < ?::timestamptz""",
            (now_iso, now_iso),
        )
        conn.commit()

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
                out["duplicate_skipped"] = True
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
        "counts": counts,
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
        return {"items": [dict(r) for r in rows], "total": int(total["c"] or 0), "limit": limit, "offset": offset}
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
                out["duplicate_skipped"] = True
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


# ==========================================================================
# GESTIÓN DE ESPECIALIDADES
# ==========================================================================
def list_specialties() -> List[Dict[str, Any]]:
    """Lista todas las especialidades de usuarios."""
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT us.*, u.role
            FROM user_specialties us
            LEFT JOIN users u ON u.username = us.username
            ORDER BY us.specialty, us.username
        """).fetchall()
        return [dict(r) for r in rows]
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


def _find_ticket_by_thread_headers(in_reply_to: str, references: str) -> Optional[int]:
    conn = db.get_conn()
    try:
        candidates = []
        candidates.extend(_extract_message_ids(in_reply_to))
        candidates.extend(_extract_message_ids(references))
        for candidate in candidates:
            for token in _message_id_variants(candidate):
                row = conn.execute(
                    "SELECT id FROM tickets WHERE email_thread_id = ? ORDER BY id DESC LIMIT 1",
                    (token,),
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

    try:
        ticket_id = _find_ticket_by_thread_headers(in_reply_to, references)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by thread headers: {e}")

    try:
        ticket_id = _find_ticket_by_subject(subject)
        if ticket_id:
            _process_reply_email(ticket_id, sender, subject, body, msg_id)
            return
    except Exception as e:
        logger.error(f"[EMAIL] Error matching by subject: {e}")

    _process_new_email_ticket(subject, sender, body, msg_id)


def _process_reply_email(ticket_id: int, sender: str, subject: str, body: str, msg_id: str):
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
                "[]",
                now,
            ),
        )
        conn.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
        if msg_id:
            conn.execute("UPDATE tickets SET email_thread_id = ? WHERE id = ?", (msg_id, ticket_id))
        _evaluate_ticket_sla(conn, ticket_id, now)
        conn.commit()
    finally:
        conn.close()


def _process_new_email_ticket(subject: str, sender: str, body: str, msg_id: str):
    print(f"[EMAIL] New Ticket from {sender}")
    
    # 1. Clasificación
    categoria = clasificar_ticket(subject, body)
    
    # 2. Triaje (Mesa vs Especialista)
    asignado_a = None
    if categoria == "general":
        asignado_a = "mesa_ayuda" 
    else:
        asignado_a = auto_asignar(categoria)
        if not asignado_a:
            asignado_a = "mesa_ayuda"

    # 3. Datos del cliente
    cliente_nombre = sender
    origen_email = sender
    if "<" in sender:
        parts = sender.split("<")
        cliente_nombre = parts[0].strip().replace('"', '')
        origen_email = parts[1].strip().replace('>', '')

    conn = None
    now = db.now_utc_iso()

    # 4. Crear Ticket
    try:
        tk = create_ticket(
            titulo=subject,
            descripcion=body,
            creador_id="email_bot",
            categoria=categoria,
            origen_email=origen_email,
            cliente_nombre=cliente_nombre,
            email_thread_id=msg_id
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
                "[]",
                now,
            ),
        )
        conn.commit()

        print(f"[EMAIL] Created Ticket {codigo} (#{ticket_id})")

        # 5. Programar Auto-Respuesta (DESACTIVADO TEMPORALMENTE - CUENTA PERSONAL)
        # Cuando se migre a una cuenta dedicada (ej: soporte@...), descomentar esto.
        # 5. Programar Auto-Respuesta
        if app_settings.TICKET_AUTO_REPLY_ENABLED:
            payload = json.dumps({
                "ticket_id": ticket_id,
                "email": origen_email,
                "nombre": cliente_nombre,
                "asignado_a": asignado_a
            })
            run_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            
            conn.execute(
                "INSERT INTO sys_jobs (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at) VALUES (?, 'PENDING', ?, ?, 0, 3, ?, ?)",
                ("SEND_AUTO_RESPONSE", payload, run_at, now, now)
            )
            conn.commit()
            print(f"[EMAIL] Auto-response scheduled for TK-{ticket_id} in 15m")

    except Exception as e:
        logger.error(f"[EMAIL] Error creating ticket: {e}")
    finally:
        if conn:
            conn.close()
