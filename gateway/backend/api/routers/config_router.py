from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from plataforma.core import db, deps
from plataforma.core.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


ROLE_LABELS = {
    "admin": "Admin",
    "encargado_mesa": "Encargado Mesa Ayuda",
    "ops": "Operaciones",
    "redes": "Redes",
    "sistemas": "Sistemas",
    "implementaciones": "Implementaciones",
    "finance": "Finanzas",
    "warehouse": "Bodega",
    "gerencia": "Gerencia",
    "monitora": "Monitora Fundacion",
    "ejecutiva": "Ejecutiva Fundacion",
    "fundacion": "Fundacion",
    "encargado_la_pintana": "Encargado La Pintana",
    "encargado_maipu": "Encargado Maipu",
    "encargado_llay_llay": "Encargado Llay-Llay",
    "encargado_huechuraba": "Encargado Huechuraba",
    "encargado_renca": "Encargado Renca",
    "encargado_lo_espejo": "Encargado Lo Espejo",
    "encargado_cerro_navia": "Encargado Cerro Navia",
}

ROLE_DESCRIPTIONS = {
    "admin": "Control total de plataforma, seguridad y configuracion global.",
    "encargado_mesa": "Gestiona flujo de ticketera, asignacion, seguimiento y cumplimiento.",
    "ops": "Operacion tecnica transversal para atencion y despacho de tickets.",
    "redes": "Ejecucion tecnica en networking e incidencias de conectividad.",
    "sistemas": "Ejecucion tecnica en servidores, plataformas y sistemas.",
    "implementaciones": "Ejecucion de despliegues/proyectos con alcance tecnico.",
    "finance": "Gestion financiera y cobranza con foco contable.",
    "warehouse": "Gestion operativa de inventario y movimientos de bodega.",
    "gerencia": "Vision ejecutiva y lectura de indicadores/estado operacional.",
    "monitora": "Planificacion global y gestion de todas las tareas de la Fundacion.",
    "ejecutiva": "Acceso a planificacion propia y reporte de actividades.",
    "fundacion": "Gestion integral del modulo Fundacion.",
    "encargado_la_pintana": "Responsable operativo de la sede La Pintana.",
    "encargado_maipu": "Responsable operativo de la sede Maipu.",
    "encargado_llay_llay": "Responsable operativo de la sede Llay-Llay.",
    "encargado_huechuraba": "Responsable operativo de la sede Huechuraba.",
    "encargado_renca": "Responsable operativo de la sede Renca.",
    "encargado_lo_espejo": "Responsable operativo de la sede Lo Espejo.",
    "encargado_cerro_navia": "Responsable operativo de la sede Cerro Navia.",
}

PERMISSION_LABELS = {
    "*": "Acceso total del sistema",
    "dashboard:read": "Dashboard: lectura",
    "tickets:read": "Ticketera: lectura",
    "tickets:write": "Ticketera: gestion operativa",
    "tickets:compliance": "Ticketera: compliance y evidencias",
    "audit:read": "Auditoria: lectura",
    "audit:export": "Auditoria: exportacion",
    "invoice:read": "Facturacion: lectura",
    "invoice:sync": "Facturacion: sincronizacion",
    "invoice:write": "Facturacion: edicion",
    "invoice:void": "Facturacion: anulacion",
    "payment:write": "Pagos: gestion",
    "crm:read": "CRM: lectura",
    "crm:write": "CRM: edicion",
    "bodega:read": "Bodega: lectura",
    "bodega:write": "Bodega: edicion",
    "pmo:read": "PMO: lectura",
    "pmo:write": "PMO: edicion",
    "finanzas:read": "Finanzas: lectura",
    "reports:read": "Reportes: lectura",
    "fundacion:read": "Fundacion: lectura",
    "fundacion:write": "Fundacion: escritura",
    "admin.settings": "Configuracion administrativa",
}


def _permission_label(permission: str) -> str:
    normalized = str(permission or "").strip().lower()
    if not normalized:
        return "-"
    if normalized in PERMISSION_LABELS:
        return PERMISSION_LABELS[normalized]
    if ":" in normalized:
        module, action = normalized.split(":", 1)
        return f"{module.upper()}: {action}"
    return normalized


@router.get("/role-scopes", summary="Get role scopes")
async def get_role_scopes(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    items = []
    for role in sorted(settings.ROLE_PERMISSIONS.keys()):
        permissions = []
        seen = set()
        for raw_permission in settings.ROLE_PERMISSIONS.get(role, []) or []:
            permission = str(raw_permission or "").strip().lower()
            if not permission or permission in seen:
                continue
            seen.add(permission)
            permissions.append(permission)
        items.append(
            {
                "role": role,
                "label": ROLE_LABELS.get(role, role),
                "description": ROLE_DESCRIPTIONS.get(role, "Rol operativo de plataforma."),
                "permissions": permissions,
                "permissions_detail": [
                    {"id": permission, "label": _permission_label(permission)}
                    for permission in permissions
                ],
            }
        )
    return {"items": items}


@router.get("/smtp", summary="Get SMTP config")
async def get_smtp_config(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        keys = [
            "smtp_host",
            "smtp_port",
            "smtp_user",
            "smtp_password",
            "smtp_from_name",
            "imap_host",
            "imap_port",
            "imap_user",
            "imap_password",
            "email_polling_interval",
            "ticket_auto_reply_enabled",
            "ticket_auto_reply_time",
            "ticket_auto_close_time",
        ]
        placeholders = ", ".join(["?" for _ in keys])
        rows = conn.execute(
            f"SELECT key, value, is_sensitive FROM system_settings WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()

        config = {}
        found = set()
        for row in rows:
            key = row["key"]
            value = row["value"]
            is_sensitive = bool(row["is_sensitive"])
            found.add(key)
            config[key] = "********" if is_sensitive and value else value

        for key in keys:
            if key not in found:
                config[key] = ""
        return config
    finally:
        conn.close()


@router.post("/smtp", summary="Update SMTP config")
async def update_smtp_config(
    payload: dict,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        allowed = {
            "smtp_host": False,
            "smtp_port": False,
            "smtp_user": False,
            "smtp_from_name": False,
            "smtp_password": True,
            "imap_host": False,
            "imap_port": False,
            "imap_user": False,
            "imap_password": True,
            "email_polling_interval": False,
            "ticket_auto_reply_enabled": False,
            "ticket_auto_reply_time": False,
            "ticket_auto_close_time": False,
        }

        for key, value in (payload or {}).items():
            if key not in allowed:
                continue
            is_sensitive = allowed[key]
            if is_sensitive and value == "********":
                continue
            conn.execute(
                """INSERT INTO system_settings (key, value, group_name, is_sensitive, updated_at)
                   VALUES (?, ?, 'smtp', ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       group_name = excluded.group_name,
                       is_sensitive = excluded.is_sensitive,
                       updated_at = excluded.updated_at""",
                (key, str(value), bool(is_sensitive), now),
            )

        conn.commit()
        return {"ok": True}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando configuracion: {exc}") from exc
    finally:
        conn.close()
