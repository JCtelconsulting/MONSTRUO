from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Set
from pydantic import BaseModel, Field
import json
import unicodedata
from app.core import db, security, deps
from app.core.config import settings

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
            raise HTTPException(status_code=400, detail=f"Rol secundario inválido: '{raw}'")
        if role in out:
            continue
        out.append(role)
    return out

# --- Modelos ---
class UserOut(BaseModel):
    username: str
    role: str
    secondary_roles: List[str] = Field(default_factory=list)
    is_active: bool
    allowed_modules: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    secondary_roles: List[str] = Field(default_factory=list)
    allowed_modules: List[str] = Field(default_factory=list)

class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
    secondary_roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    allowed_modules: Optional[List[str]] = None

# --- Endpoints ---

@router.get("", response_model=dict)
async def list_users(
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Listar todos los usuarios del sistema."""
    conn = db.get_conn()
    try:
        cursor = conn.execute(
            "SELECT username, role, secondary_roles, is_active, allowed_modules, created_at FROM users ORDER BY username ASC"
        )
        users = []
        for row in cursor.fetchall():
            u = dict(row)
            u['is_active'] = bool(u['is_active'])
            try:
                u['allowed_modules'] = json.loads(u['allowed_modules']) if u['allowed_modules'] else []
            except:
                u['allowed_modules'] = []
            try:
                u['secondary_roles'] = json.loads(u.get('secondary_roles') or '[]')
                if not isinstance(u['secondary_roles'], list):
                    u['secondary_roles'] = []
            except:
                u['secondary_roles'] = []
            users.append(u)
        return {"items": users}
    finally:
        conn.close()

@router.post("", response_model=dict)
async def create_user_endpoint(
    body: UserCreate,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Crear nuevo usuario."""
    normalized_role = _normalize_role_input(body.role)
    if normalized_role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol inválido: '{body.role}'")
    normalized_secondary_roles = _normalize_secondary_roles_input(body.secondary_roles, normalized_role)

    conn = db.get_conn()
    try:
        # Check exists
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (body.username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Usuario ya existe")

        hashed = security.get_password_hash(body.password)
        allowed_json = json.dumps(body.allowed_modules)
        secondary_json = json.dumps(normalized_secondary_roles)
        
        conn.execute(
            "INSERT INTO users (username, password_hash, role, secondary_roles, is_active, allowed_modules, created_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
            (body.username, hashed, normalized_role, secondary_json, allowed_json, db.now_utc_iso())
        )
        conn.commit()
        return {"ok": True, "username": body.username}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print(f"[admin_users] create_user_endpoint error: {e}")
        raise HTTPException(status_code=500, detail="Error creando usuario")
    finally:
        conn.close()

@router.patch("/{username}", response_model=dict)
async def update_user(
    username: str,
    body: UserUpdate,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Actualizar usuario (password, rol, estado, modulos)."""
    conn = db.get_conn()
    try:
        # Check exist
        existing = conn.execute("SELECT role, secondary_roles FROM users WHERE username=?", (username,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        base_role = _normalize_role_input(existing.get("role"))
        target_role = _normalize_role_input(body.role) if body.role else base_role
        if target_role not in ALLOWED_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol inválido: '{body.role}'")

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

        if body.password:
             hashed = security.get_password_hash(body.password)
             updates.append("password_hash = ?")
             params.append(hashed)

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
    except Exception as e:
        conn.rollback()
        print(f"[admin_users] update_user error: {e}")
        raise HTTPException(status_code=500, detail="Error actualizando usuario")
    finally:
        conn.close()

@router.delete("/{username}", response_model=dict)
async def delete_user(
    username: str,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Eliminar usuario físicamente."""
    # Evitar auto-borrado?
    if username == sess["username"]:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")

    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
        return {"ok": True}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        print(f"[admin_users] delete_user error: {e}")
        raise HTTPException(status_code=500, detail="Error eliminando usuario")
    finally:
        conn.close()
