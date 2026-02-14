from typing import Optional, Dict, Any
from app.core import db, security

def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username=?",
            (username.strip(),)
        ).fetchone()
        
        if not row or int(row["is_active"] or 0) != 1:
            return None
            
        if not security.verify_password(password, row["password_hash"]):
            return None
            
        return {"username": row["username"], "role": row["role"]}
    finally:
        conn.close()

def create_user(username: str, password: str, role: str) -> None:
    # Validacion basica
    username = username.strip()
    role = role.strip()
    if role not in ("admin", "finance", "ops", "warehouse", "redes", "sistemas", "implementaciones", "gerencia"):
        raise ValueError("Role invalido")

    hashed_pw = security.get_password_hash(password)
    
    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            # Silent fail or raise? Raise allows API to handle 409
            raise RuntimeError("Usuario ya existe")
            
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (username, hashed_pw, role, db.now_utc_iso())
        )
        conn.commit()
    finally:
        conn.close()
