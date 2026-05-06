from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from plataforma.core import db, deps
from plataforma.core.config import settings

router = APIRouter(prefix="/api/config", tags=["config"])


ROLE_LABELS = {
    # Monstruo
    "admin": "Admin",
    "encargado_mesa": "Encargado Mesa Ayuda",
    "ops": "Operaciones",
    "redes": "Redes",
    "sistemas": "Sistemas",
    "implementaciones": "Implementaciones",
    "finance": "Finanzas",
    "warehouse": "Bodega",
    "gerencia": "Gerencia",
    # Fundación (organigrama 2026)
    "directora_social": "Directora Social",
    "jefa_pedagogica": "Jefa Pedagógica",
    "coordinadora_territorial": "Coordinadora Territorial",
    "lider_educativo": "Líder Educativo",
    "gestora_educativa": "Gestora Educativa",
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
    "directora_social": "Direccion estrategica de la Fundacion (super-scope a sedes).",
    "jefa_pedagogica": "Lidera la linea pedagogica de la Fundacion (super-scope a sedes).",
    "coordinadora_territorial": "Coordina territorialmente las sedes (super-scope a sedes).",
    "lider_educativo": "Responsable de una o mas sedes; el alcance lo define la membresia.",
    "gestora_educativa": "Operacion educativa dentro de su sede asignada.",
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
    "zabbix:read": "Zabbix: lectura",
    "ia:read": "IA: lectura",
    "gta:read": "GTA: lectura",
    "gta:write": "GTA: gestion",
}

ALL_PERMISSIONS = sorted(PERMISSION_LABELS.keys())


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


def _build_role_item(role: str, rows: list) -> dict:
    permissions = []
    seen: set = set()
    for row in rows:
        perm = str(row["permission"] or "").strip().lower()
        if not perm or perm in seen:
            continue
        seen.add(perm)
        permissions.append(perm)
    description = rows[0]["description"] if rows else ROLE_DESCRIPTIONS.get(role, "Rol operativo de plataforma.")
    return {
        "role": role,
        "label": ROLE_LABELS.get(role, role),
        "description": description,
        "permissions": permissions,
        "permissions_detail": [
            {"id": p, "label": _permission_label(p)} for p in permissions
        ],
    }


@router.get("/role-scopes", summary="Get role scopes from DB")
async def get_role_scopes(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT role, permission, label, description FROM core.sys_role_permissions ORDER BY role, id"
        ).fetchall()

        # Group by role
        grouped: dict[str, list] = {}
        for row in rows:
            role = str(row["role"])
            grouped.setdefault(role, []).append(row)

        # Ensure all config roles appear even if not in DB yet
        all_roles = set(settings.ROLE_PERMISSIONS.keys()) | set(grouped.keys())
        items = []
        for role in sorted(all_roles):
            if role in grouped:
                items.append(_build_role_item(role, grouped[role]))
            else:
                # Fallback from config for roles not yet seeded in DB
                fallback_perms = settings.ROLE_PERMISSIONS.get(role, [])
                items.append({
                    "role": role,
                    "label": ROLE_LABELS.get(role, role),
                    "description": ROLE_DESCRIPTIONS.get(role, "Rol operativo de plataforma."),
                    "permissions": list(fallback_perms),
                    "permissions_detail": [{"id": p, "label": _permission_label(p)} for p in fallback_perms],
                })
        return {"items": items, "all_permissions": [
            {"id": p, "label": _permission_label(p)} for p in ALL_PERMISSIONS
        ]}
    finally:
        conn.close()


class RoleScopeUpdate(BaseModel):
    description: str = ""
    permissions: List[str]


@router.put("/role-scopes/{role}", summary="Update permissions for a role")
async def update_role_scope(
    role: str,
    body: RoleScopeUpdate,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    role = str(role or "").strip().lower()
    if not role:
        raise HTTPException(status_code=400, detail="role requerido")

    # Protect admin from losing full access
    if role == "admin" and "*" not in body.permissions:
        raise HTTPException(status_code=400, detail="El rol admin siempre debe tener permiso '*'")

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        description = str(body.description or ROLE_DESCRIPTIONS.get(role, "Rol operativo de plataforma."))

        # Delete existing permissions for this role
        conn.execute("DELETE FROM core.sys_role_permissions WHERE role = %s", (role,))

        # Insert new set
        for perm in body.permissions:
            perm = str(perm or "").strip().lower()
            if not perm:
                continue
            label = _permission_label(perm)
            conn.execute(
                """INSERT INTO core.sys_role_permissions (role, permission, label, description, updated_at)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (role, permission) DO UPDATE SET
                       label = excluded.label,
                       description = excluded.description,
                       updated_at = excluded.updated_at""",
                (role, perm, label, description, now),
            )

        conn.commit()
        return {"ok": True, "role": role, "permissions": body.permissions}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error guardando permisos: {exc}") from exc
    finally:
        conn.close()


@router.get("/smtp", summary="Get SMTP config")
async def get_smtp_config(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        keys = [
            "smtp_host", "smtp_port", "smtp_user", "smtp_password", "smtp_from_name",
            "imap_host", "imap_port", "imap_user", "imap_password",
            "email_polling_interval", "ticket_auto_reply_enabled",
            "ticket_auto_reply_time", "ticket_auto_close_time",
        ]
        placeholders = ", ".join(["?" for _ in keys])
        rows = conn.execute(
            f"SELECT key, value, is_sensitive FROM system_settings WHERE key IN ({placeholders})",
            tuple(keys),
        ).fetchall()

        config: dict = {}
        found: set = set()
        for row in rows:
            key = row["key"]
            value = row["value"]
            is_sensitive = bool(row["is_sensitive"])
            found.add(key)
            config[key] = "********" if is_sensitive and value else value

        for key in keys:
            if key not in found:
                config[key] = ""
        config["mail_sandbox"] = settings.MAIL_SANDBOX
        config["env_type"] = settings.ENV_TYPE
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
            "smtp_host": False, "smtp_port": False, "smtp_user": False,
            "smtp_from_name": False, "smtp_password": True,
            "imap_host": False, "imap_port": False, "imap_user": False,
            "imap_password": True, "email_polling_interval": False,
            "ticket_auto_reply_enabled": False, "ticket_auto_reply_time": False,
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
