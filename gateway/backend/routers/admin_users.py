from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from plataforma.core import auth_service, db, deps, security
from plataforma.core.config import settings

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
ALLOWED_ROLES: Set[str] = set(settings.ROLE_PERMISSIONS.keys())


def _normalize_role_input(raw_role: Optional[str]) -> str:
    role = unicodedata.normalize("NFKD", str(raw_role or ""))
    role = role.encode("ascii", "ignore").decode("ascii")
    role = role.strip().lower().replace("-", "_").replace(" ", "_")
    if "encargado" in role and "mesa" in role:
        return "encargado_mesa"
    aliases = {
        "encargado_de_mesa_de_ayuda": "encargado_mesa",
        "encargado_mesa_de_ayuda": "encargado_mesa",
        "encargado_mesa_ayuda": "encargado_mesa",
        "encargado_de_mesa_ayuda": "encargado_mesa",
        "encargado_de_mesa": "encargado_mesa",
        "encargado_mesa": "encargado_mesa",
        "mesa_de_ayuda": "encargado_mesa",
        "operaciones": "ops",
    }
    return aliases.get(role, role)


def _normalize_secondary_roles_input(raw_roles: Optional[List[str]], primary_role: str) -> List[str]:
    out: List[str] = []
    primary = _normalize_role_input(primary_role)
    for raw in raw_roles or []:
        role = _normalize_role_input(raw)
        if not role or role == primary:
            continue
        if role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol secundario invalido: '{raw}'")
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
    organizacion: Optional[str] = None  # 'monstruo' | 'fundacion'


class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    secondary_roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    allowed_modules: Optional[List[str]] = None
    fundacion_scope: Optional[Dict[str, Any]] = None
    organizacion: Optional[str] = None


_VALID_ORGS = {"monstruo", "fundacion"}


def _scope_from_session(sess: dict) -> str:
    """Devuelve la organización a la que el actor está limitado.

    - admin de Monstruo (sistemas/admin global) ve todo: 'monstruo' (sin filtro extra
      en list, pero al crear/editar puede tocar a quien quiera dentro de Monstruo).
    - admin de Fundación solo ve y edita usuarios de Fundación.

    Implementación simple: el actor mismo tiene un valor en auth.users.organizacion;
    los actores de Fundación quedan limitados a su organización.
    """
    username = sess.get("username") if isinstance(sess, dict) else None
    if not username:
        return "monstruo"
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT organizacion FROM auth.users WHERE username = %s",
            (username,),
        ).fetchone()
        org = (row.get("organizacion") if row else "monstruo") or "monstruo"
        return org if org in _VALID_ORGS else "monstruo"
    finally:
        conn.close()


def _scope_filter_clause(actor_org: str, alias: str = "") -> tuple[str, tuple]:
    """Cláusula WHERE para limitar la query al scope del actor.

    - actor 'fundacion' → SOLO usuarios de fundacion
    - actor 'monstruo'  → ve todos (no filtra) — el admin global gestiona ambos lados
                          pero la UI de configuración global por convención muestra
                          solo monstruo (filtrado en el frontend o via parámetro).
    """
    prefix = f"{alias}." if alias else ""
    if actor_org == "fundacion":
        return f"{prefix}organizacion = %s", ("fundacion",)
    return "1=1", ()


@router.get("", response_model=dict)
async def list_users(
    organizacion: Optional[str] = None,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    """Lista usuarios.

    - Admin de Fundación (organizacion='fundacion' en su propia fila): SOLO ve
      usuarios de Fundación, ignorando el query param.
    - Admin global (organizacion='monstruo'): por default ve solo Monstruo. Puede
      pedir explícitamente ?organizacion=fundacion o ?organizacion=all.
    """
    actor_org = _scope_from_session(sess)
    where_clauses = ["1=1"]
    params: list = []

    if actor_org == "fundacion":
        where_clauses.append("organizacion = %s")
        params.append("fundacion")
    else:
        # Admin de Monstruo: respetar filtro explícito o default 'monstruo'.
        wanted = (organizacion or "monstruo").strip().lower()
        if wanted in _VALID_ORGS:
            where_clauses.append("organizacion = %s")
            params.append(wanted)
        elif wanted == "all":
            pass  # sin filtro
        else:
            where_clauses.append("organizacion = %s")
            params.append("monstruo")

    sql = (
        "SELECT id, username, role, secondary_roles, is_active, allowed_modules, "
        "fundacion_scope, organizacion, created_at "
        f"FROM users WHERE {' AND '.join(where_clauses)} ORDER BY username ASC"
    )

    conn = db.get_conn()
    try:
        cursor = conn.execute(sql, tuple(params))
        users = []
        for row in cursor.fetchall():
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

            item["fundacion_scope"] = auth_service.normalize_fundacion_scope(item.get("fundacion_scope"))
            users.append(item)
        return {"items": users, "actor_organizacion": actor_org}
    finally:
        conn.close()


@router.post("", response_model=dict)
async def create_user_endpoint(
    body: UserCreate,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    normalized_role = _normalize_role_input(body.role)
    if normalized_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol invalido: '{body.role}'")
    normalized_secondary_roles = _normalize_secondary_roles_input(body.secondary_roles, normalized_role)
    normalized_fundacion_scope = auth_service.normalize_fundacion_scope(body.fundacion_scope)

    # Resolver organización del usuario nuevo según el scope del actor
    actor_org = _scope_from_session(sess)
    requested = (body.organizacion or "").strip().lower() or None
    if actor_org == "fundacion":
        # Admin de Fundación SOLO puede crear usuarios de Fundación
        if requested and requested != "fundacion":
            raise HTTPException(status_code=403, detail="Solo podés crear usuarios de Fundación")
        target_org = "fundacion"
    else:
        # Admin de Monstruo elige (default 'monstruo')
        target_org = requested if requested in _VALID_ORGS else "monstruo"

    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE username = ?", (body.username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Usuario ya existe")

        conn.execute(
            """INSERT INTO users (username, password_hash, role, secondary_roles, is_active,
                                  allowed_modules, fundacion_scope, organizacion, created_at)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (
                body.username,
                security.get_password_hash(body.password),
                normalized_role,
                json.dumps(normalized_secondary_roles),
                json.dumps(body.allowed_modules or []),
                json.dumps(normalized_fundacion_scope),
                target_org,
                db.now_utc_iso(),
            ),
        )
        conn.commit()
        return {"ok": True, "username": body.username, "organizacion": target_org}
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
    actor_org = _scope_from_session(sess)
    conn = db.get_conn()
    try:
        existing = conn.execute(
            "SELECT role, secondary_roles, organizacion FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        target_org = (existing.get("organizacion") or "monstruo")
        if actor_org == "fundacion" and target_org != "fundacion":
            raise HTTPException(status_code=403, detail="Solo podés editar usuarios de Fundación")

        base_role = _normalize_role_input(existing.get("role"))
        target_role = _normalize_role_input(body.role) if body.role else base_role
        if target_role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol invalido: '{body.role}'")

        updates = []
        params = []

        if body.role:
            updates.append("role = ?")
            params.append(target_role)

        if body.secondary_roles is not None:
            normalized_secondary_roles = _normalize_secondary_roles_input(body.secondary_roles, target_role)
            updates.append("secondary_roles = ?")
            params.append(json.dumps(normalized_secondary_roles))
        elif body.role:
            try:
                existing_secondary = json.loads(existing.get("secondary_roles") or "[]")
            except Exception:
                existing_secondary = []
            normalized_secondary_roles = _normalize_secondary_roles_input(existing_secondary, target_role)
            updates.append("secondary_roles = ?")
            params.append(json.dumps(normalized_secondary_roles))

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

        if body.organizacion is not None:
            new_org = body.organizacion.strip().lower()
            if new_org not in _VALID_ORGS:
                raise HTTPException(status_code=400, detail="organización inválida")
            if actor_org == "fundacion" and new_org != "fundacion":
                raise HTTPException(status_code=403, detail="No podés mover usuarios fuera de Fundación")
            updates.append("organizacion = ?")
            params.append(new_org)

        if not updates:
            return {"ok": True, "msg": "No changes"}

        params.append(username)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE username = ?"
        conn.execute(sql, tuple(params))
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

    actor_org = _scope_from_session(sess)
    conn = db.get_conn()
    try:
        existing = conn.execute(
            "SELECT organizacion FROM users WHERE username = ?", (username,),
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        target_org = (existing.get("organizacion") or "monstruo")
        if actor_org == "fundacion" and target_org != "fundacion":
            raise HTTPException(status_code=403, detail="Solo podés eliminar usuarios de Fundación")

        conn.execute("DELETE FROM users WHERE username = ?", (username,))
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
