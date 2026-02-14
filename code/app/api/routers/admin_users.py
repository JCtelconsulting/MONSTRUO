from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Set
from pydantic import BaseModel, Field
import json
from app.core import db, security, deps
from app.core.config import settings

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])
ALLOWED_ROLES: Set[str] = set(settings.ROLE_PERMISSIONS.keys())

# --- Modelos ---
class UserOut(BaseModel):
    username: str
    role: str
    is_active: bool
    allowed_modules: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    allowed_modules: List[str] = Field(default_factory=list)

class UserUpdate(BaseModel):
    password: Optional[str] = None
    role: Optional[str] = None
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
        cursor = conn.execute("SELECT username, role, is_active, allowed_modules, created_at FROM users ORDER BY username ASC")
        users = []
        for row in cursor.fetchall():
            u = dict(row)
            u['is_active'] = bool(u['is_active'])
            try:
                u['allowed_modules'] = json.loads(u['allowed_modules']) if u['allowed_modules'] else []
            except:
                u['allowed_modules'] = []
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
    if body.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Rol inválido")

    conn = db.get_conn()
    try:
        # Check exists
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (body.username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Usuario ya existe")

        hashed = security.get_password_hash(body.password)
        allowed_json = json.dumps(body.allowed_modules)
        
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active, allowed_modules, created_at) VALUES (?, ?, ?, 1, ?, ?)",
            (body.username, hashed, body.role, allowed_json, db.now_utc_iso())
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
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        updates = []
        params = []

        if body.role:
            # Validar rol
            if body.role not in ALLOWED_ROLES:
                raise HTTPException(status_code=400, detail="Rol inválido")
            updates.append("role = ?")
            params.append(body.role)

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
