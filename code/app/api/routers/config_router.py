from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core import db, deps

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/users", summary="List users for dropdowns")
async def list_users(
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Lista de usuarios para selects de asignación."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT username, role, is_active FROM users ORDER BY username"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/smtp", summary="Get SMTP Config")
async def get_smtp_config(
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    conn = db.get_conn()
    try:
        keys = ['smtp_host', 'smtp_port', 'smtp_user', 'smtp_password', 'smtp_from_name']
        
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
            'smtp_password': True 
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
