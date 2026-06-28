"""Administración de usuarios PROPIA de Fundación (separación fase 2).

Adaptado de gateway/backend/routers/admin_users.py, pero SIN el scoping por
`organizacion` (en Fundación todos los usuarios son de Fundación) y apuntando a
fundacion.users en vez de auth.users.

CRUD sobre /api/admin/users. Requiere permiso 'admin.settings' (lo tienen las
jefaturas del organigrama: directora_social, jefa_pedagogica, coordinadora_territorial).
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fundacion.core import auth_service, db, deps, security
from fundacion.core.config import settings

router = APIRouter(prefix="/api/admin/users", tags=["fundacion-admin-users"])
ALLOWED_ROLES: Set[str] = set(settings.ROLE_PERMISSIONS.keys())


def _normalize_role_input(raw_role: Optional[str]) -> str:
    role = unicodedata.normalize("NFKD", str(raw_role or ""))
    role = role.encode("ascii", "ignore").decode("ascii")
    role = role.strip().lower().replace("-", "_").replace(" ", "_")
    return role


def _normalize_secondary_roles_input(raw_roles: Optional[List[str]], primary_role: str) -> List[str]:
    out: List[str] = []
    primary = _normalize_role_input(primary_role)
    for raw in raw_roles or []:
        role = _normalize_role_input(raw)
        if not role or role == primary:
            continue
        if role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol secundario inválido: '{raw}'")
        if role in out:
            continue
        out.append(role)
    return out


class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    secondary_roles: List[str] = Field(default_factory=list)
    allowed_modules: List[str] = Field(default_factory=list)
    fundacion_scope: Dict[str, Any] = Field(default_factory=dict)
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    secondary_roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    allowed_modules: Optional[List[str]] = None
    fundacion_scope: Optional[Dict[str, Any]] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


@router.get("", response_model=dict)
async def list_users(sess: dict = Depends(deps.require_permission("admin.settings"))):
    sql = (
        "SELECT id, username, role, secondary_roles, is_active, allowed_modules, "
        "fundacion_scope, first_name, last_name, created_at "
        "FROM fundacion.users ORDER BY username ASC"
    )
    conn = db.get_conn()
    try:
        users = []
        for row in conn.execute(sql).fetchall():
            item = dict(row)
            item["is_active"] = bool(item.get("is_active"))
            try:
                item["allowed_modules"] = json.loads(item.get("allowed_modules") or "[]")
            except Exception:
                item["allowed_modules"] = []
            try:
                item["secondary_roles"] = json.loads(item.get("secondary_roles") or "[]")
                if not isinstance(item["secondary_roles"], list):
                    item["secondary_roles"] = []
            except Exception:
                item["secondary_roles"] = []
            item["display_name"] = f"{(item.get('first_name') or '').strip()} {(item.get('last_name') or '').strip()}".strip()
            item["fundacion_scope"] = auth_service.normalize_fundacion_scope(item.get("fundacion_scope"))
            users.append(item)
        return {"items": users, "actor_organizacion": "fundacion"}
    finally:
        conn.close()


@router.post("", response_model=dict)
async def create_user_endpoint(
    body: UserCreate,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    normalized_role = _normalize_role_input(body.role)
    if normalized_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol inválido: '{body.role}'")
    normalized_secondary = _normalize_secondary_roles_input(body.secondary_roles, normalized_role)
    normalized_scope = auth_service.normalize_fundacion_scope(body.fundacion_scope)

    conn = db.get_conn()
    try:
        if conn.execute("SELECT 1 FROM fundacion.users WHERE username = ?", (body.username,)).fetchone():
            raise HTTPException(status_code=409, detail="Usuario ya existe")
        conn.execute(
            """INSERT INTO fundacion.users (username, password_hash, role, secondary_roles, is_active,
                                  allowed_modules, fundacion_scope, first_name, last_name, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (
                body.username,
                security.get_password_hash(body.password),
                normalized_role,
                json.dumps(normalized_secondary),
                json.dumps(body.allowed_modules or []),
                json.dumps(normalized_scope),
                (body.first_name or "").strip(),
                (body.last_name or "").strip(),
                db.now_utc_iso(),
            ),
        )
        conn.commit()
        return {"ok": True, "username": body.username}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error creando usuario: {exc}") from exc
    finally:
        conn.close()


@router.patch("/{username}", response_model=dict)
async def update_user(
    username: str,
    body: UserUpdate,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        existing = conn.execute(
            "SELECT role, secondary_roles FROM fundacion.users WHERE username = ?",
            (username,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        base_role = _normalize_role_input(existing.get("role"))
        target_role = _normalize_role_input(body.role) if body.role else base_role
        if target_role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol inválido: '{body.role}'")

        updates: list = []
        params: list = []
        if body.role:
            updates.append("role = ?")
            params.append(target_role)
        if body.secondary_roles is not None:
            updates.append("secondary_roles = ?")
            params.append(json.dumps(_normalize_secondary_roles_input(body.secondary_roles, target_role)))
        elif body.role:
            try:
                existing_secondary = json.loads(existing.get("secondary_roles") or "[]")
            except Exception:
                existing_secondary = []
            updates.append("secondary_roles = ?")
            params.append(json.dumps(_normalize_secondary_roles_input(existing_secondary, target_role)))
        if body.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if body.is_active else 0)
        if body.allowed_modules is not None:
            updates.append("allowed_modules = ?")
            params.append(json.dumps(body.allowed_modules))
        if body.fundacion_scope is not None:
            updates.append("fundacion_scope = ?")
            params.append(json.dumps(auth_service.normalize_fundacion_scope(body.fundacion_scope)))
        if body.password:
            updates.append("password_hash = ?")
            params.append(security.get_password_hash(body.password))
        if body.first_name is not None:
            updates.append("first_name = ?")
            params.append(body.first_name.strip())
        if body.last_name is not None:
            updates.append("last_name = ?")
            params.append(body.last_name.strip())

        if not updates:
            return {"ok": True, "msg": "No changes"}

        params.append(username)
        conn.execute(f"UPDATE fundacion.users SET {', '.join(updates)} WHERE username = ?", tuple(params))
        conn.commit()
        return {"ok": True}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error actualizando usuario: {exc}") from exc
    finally:
        conn.close()


@router.delete("/{username}", response_model=dict)
async def delete_user(
    username: str,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    if username == sess["username"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    conn = db.get_conn()
    try:
        if not conn.execute("SELECT 1 FROM fundacion.users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        conn.execute("DELETE FROM fundacion.users WHERE username = ?", (username,))
        conn.commit()
        return {"ok": True}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando usuario: {exc}") from exc
    finally:
        conn.close()
