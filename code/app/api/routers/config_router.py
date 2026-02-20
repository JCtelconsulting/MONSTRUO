from fastapi import APIRouter, Depends, HTTPException
from app.core import db, deps
from app.core.config import settings
import json

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
}

ROLE_DESCRIPTIONS = {
    "admin": "Control total de plataforma, seguridad y configuración global.",
    "encargado_mesa": "Gestiona flujo de ticketera, asignación, seguimiento y cumplimiento.",
    "ops": "Operación técnica transversal para atención y despacho de tickets.",
    "redes": "Ejecución técnica en networking e incidencias de conectividad.",
    "sistemas": "Ejecución técnica en servidores, plataformas y sistemas.",
    "implementaciones": "Ejecución de despliegues/proyectos con alcance técnico.",
    "finance": "Gestión financiera y cobranza con foco contable.",
    "warehouse": "Gestión operativa de inventario y movimientos de bodega.",
    "gerencia": "Visión ejecutiva y lectura de indicadores/estado operacional.",
}

PERMISSION_LABELS = {
    "*": "Acceso total del sistema",
    "dashboard:read": "Dashboard: lectura",
    "tickets:read": "Ticketera: lectura",
    "tickets:write": "Ticketera: gestión operativa",
    "tickets:compliance": "Ticketera: compliance y evidencias",
    "audit:read": "Auditoría: lectura",
    "audit:export": "Auditoría: exportación",
    "invoice:read": "Facturación: lectura",
    "invoice:sync": "Facturación: sincronización",
    "invoice:write": "Facturación: edición",
    "invoice:void": "Facturación: anulación",
    "payment:write": "Pagos: gestión",
    "crm:read": "CRM: lectura",
    "crm:write": "CRM: edición",
    "bodega:read": "Bodega: lectura",
    "bodega:write": "Bodega: edición",
    "pmo:read": "PMO: lectura",
    "pmo:write": "PMO: edición",
    "finanzas:read": "Finanzas: lectura",
    "reports:read": "Reportes: lectura",
    "admin.settings": "Configuración administrativa",
}


def _permission_label(permission: str) -> str:
    normalized = str(permission or "").strip().lower()
    if not normalized:
        return "-"
    if normalized in PERMISSION_LABELS:
        return PERMISSION_LABELS[normalized]
    prefix_map = {
        "dashboard": "Dashboard",
        "tickets": "Ticketera",
        "invoice": "Facturación",
        "payment": "Pagos",
        "crm": "CRM",
        "bodega": "Bodega",
        "pmo": "PMO",
        "audit": "Auditoría",
        "reports": "Reportes",
        "finanzas": "Finanzas",
        "admin": "Administración",
    }
    if ":" in normalized:
        module, action = normalized.split(":", 1)
        module_label = prefix_map.get(module, module.upper())
        return f"{module_label}: {action}"
    return normalized


@router.get("/users", summary="List users for dropdowns")
async def list_users(
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Lista de usuarios para selects de asignación."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT username, role, secondary_roles, is_active FROM users ORDER BY username"
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            try:
                parsed = json.loads(item.get("secondary_roles") or "[]")
                item["secondary_roles"] = parsed if isinstance(parsed, list) else []
            except Exception:
                item["secondary_roles"] = []
            items.append(item)
        return {"items": items}
    finally:
        conn.close()


@router.get("/role-scopes", summary="Get role scopes")
async def get_role_scopes(
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    items = []
    for role in sorted(settings.ROLE_PERMISSIONS.keys()):
        raw_permissions = settings.ROLE_PERMISSIONS.get(role, []) or []
        permissions = []
        seen = set()
        for item in raw_permissions:
            perm = str(item or "").strip().lower()
            if not perm or perm in seen:
                continue
            seen.add(perm)
            permissions.append(perm)
        items.append(
            {
                "role": role,
                "label": ROLE_LABELS.get(role, role),
                "description": ROLE_DESCRIPTIONS.get(role, "Rol operativo de plataforma."),
                "permissions": permissions,
                "permissions_detail": [
                    {"id": perm, "label": _permission_label(perm)}
                    for perm in permissions
                ],
            }
        )
    return {"items": items}

@router.get("/smtp", summary="Get SMTP Config")
async def get_smtp_config(
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    conn = db.get_conn()
    try:
        keys = [
            'smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from_name',
            'imap_host', 'imap_port', 'imap_user', 'imap_password',
            'email_polling_interval', 'ticket_auto_reply_enabled', 
            'ticket_auto_reply_time', 'ticket_auto_close_time'
        ]
        
        # Simple fetch
        placeholders = ', '.join(['%s' for _ in keys])
        query = f"SELECT key, value, is_sensitive FROM system_settings WHERE key IN ({placeholders})"
        
        cursor = conn.execute(query, tuple(keys))
        rows = cursor.fetchall()
        
        config = {}
        found_keys = set()
        for r in rows:
            if isinstance(r, dict):
                k, v, s = r['key'], r['value'], r['is_sensitive']
            else:
                k, v, s = r[0], r[1], r[2]
            
            found_keys.add(k)
            if s and v:
                config[k] = "********" 
            else:
                config[k] = v
        
        # Fill missing with empty
        for k in keys:
            if k not in found_keys:
                config[k] = ""
                
        return config
    finally:
        conn.close()

@router.post("/smtp", summary="Update SMTP Config")
async def update_smtp_config(
    payload: dict,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        
        allowed = {
            'smtp_host': False, 
            'smtp_port': False, 
            'smtp_user': False, 
            'smtp_from_name': False,
            'smtp_password': True,
            'imap_host': False,
            'imap_port': False,
            'imap_user': False,
            'imap_password': True,
            'email_polling_interval': False,
            'ticket_auto_reply_enabled': False,
            'ticket_auto_reply_time': False,
            'ticket_auto_close_time': False
        }
        
        for k, v in payload.items():
            if k in allowed:
                is_sensitive = allowed[k]
                
                # If sensitive and value is mask, SKIP update
                if is_sensitive and v == "********":
                    continue
                    
                # Upsert query
                sql = """
                    INSERT INTO system_settings (key, value, group_name, is_sensitive, updated_at)
                    VALUES (?, ?, 'smtp', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                """
                conn.execute(sql, (k, str(v), int(is_sensitive), now))
                
        conn.commit()
        return {"ok": True}
    except Exception as e:
        print(f"Error saving settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
