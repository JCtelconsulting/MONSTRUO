from __future__ import annotations
import json
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from app.core import db

try:
    # Prefer import de paquete (ejecución desde /srv/monstruo_dev/code)
    from sistema_gestion.dependencias import require_role, require_session
except Exception:
    try:
        # Compat: ejecución desde dentro de /srv/monstruo_dev/code/sistema_gestion
        from dependencias import require_role, require_session
    except Exception:
        def require_role(*roles):
            def dep(): return {"username": "sys", "role": "admin"}
            return dep
        def require_session(x): return {"username": "sys", "role": "admin"}

router = APIRouter(prefix="/bridge", tags=["bridge"])

def get_conn():
    return db.get_conn()

def now_utc_iso() -> str:
    return db.now_utc_iso()

class BridgeMsgIn(BaseModel):
    thread_id: str = "jarvis"
    from_agent: str
    to_agent: str
    kind: str # status|result|request|proposal
    title: str = ""
    body: str = ""
    # Compat: aceptar string JSON o un objeto (dict/list) directo
    payload_json: Any = "{}"
    requires_approval: bool = False

@router.post("/send")
def send_message(payload: BridgeMsgIn, user=Depends(require_role("admin", "system", "ops", "finance"))):
    conn = get_conn()
    try:
        ts = now_utc_iso()
        requires_approval = bool(payload.requires_approval) or (payload.kind == "proposal")
        approval_status = "pending" if requires_approval else "na"

        payload_json_str: str
        if payload.payload_json is None or payload.payload_json == "":
            payload_json_str = "{}"
        elif isinstance(payload.payload_json, (dict, list)):
            payload_json_str = json.dumps(payload.payload_json, ensure_ascii=False)
        elif isinstance(payload.payload_json, str):
            try:
                json.loads(payload.payload_json)
            except Exception:
                raise HTTPException(status_code=400, detail="payload_json_invalido")
            payload_json_str = payload.payload_json
        else:
            raise HTTPException(status_code=400, detail="payload_json_invalido")
        
        insert_sql = """
            INSERT INTO bridge_messages (
                thread_id, from_agent, to_agent, kind, title, body, payload_json, 
                requires_approval, approval_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if db.is_postgres():
            insert_sql = insert_sql.rstrip() + " RETURNING id"
        cur = conn.execute(insert_sql, (
            payload.thread_id, payload.from_agent, payload.to_agent, payload.kind, 
            payload.title, payload.body, payload_json_str, 
            1 if requires_approval else 0, approval_status, ts
        ))
        conn.commit()
        if hasattr(cur, "lastrowid") and cur.lastrowid:
            return {"ok": True, "id": cur.lastrowid}
        row = cur.fetchone() if db.is_postgres() else None
        return {"ok": True, "id": row["id"] if row else None}
    finally:
        conn.close()

@router.get("/inbox")
def get_inbox(
    to_agent: Optional[str] = None, 
    thread_id: Optional[str] = None, 
    since_id: int = 0,
    limit: int = 50,
    user=Depends(require_role("admin", "system", "ops", "finance"))
):
    conn = get_conn()
    try:
        sql = "SELECT * FROM bridge_messages WHERE id > ?"
        params = [since_id]
        if to_agent:
            sql += " AND to_agent=?"
            params.append(to_agent)
        if thread_id:
            sql += " AND thread_id=?"
            params.append(thread_id)
        
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/pending")
def get_pending(thread_id: Optional[str] = None, user=Depends(require_role("admin", "ops", "finance"))):
    conn = get_conn()
    try:
        sql = "SELECT * FROM bridge_messages WHERE requires_approval=1 AND approval_status='pending'"
        params = []
        if thread_id:
            sql += " AND thread_id=?"
            params.append(thread_id)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.post("/{msg_id}/approve")
def approve_msg(msg_id: int, user=Depends(require_role("admin", "finance"))):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM bridge_messages WHERE id=?", (msg_id,)).fetchone()
        if not row: raise HTTPException(404, "msg_not_found")
        if row["approval_status"] != "pending": raise HTTPException(400, "not_pending")
        
        ts = now_utc_iso()
        conn.execute("UPDATE bridge_messages SET approval_status='approved', decided_by=?, decided_at=? WHERE id=?",
                     (user["username"], ts, msg_id))
        conn.commit()
        return {"ok": True, "status": "approved"}
    finally:
        conn.close()

@router.post("/{msg_id}/reject")
def reject_msg(msg_id: int, user=Depends(require_role("admin", "finance"))):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM bridge_messages WHERE id=?", (msg_id,)).fetchone()
        if not row: raise HTTPException(404, "msg_not_found")
        if row["approval_status"] != "pending": raise HTTPException(400, "not_pending")
        
        ts = now_utc_iso()
        conn.execute("UPDATE bridge_messages SET approval_status='rejected', decided_by=?, decided_at=? WHERE id=?",
                     (user["username"], ts, msg_id))
        conn.commit()
        return {"ok": True, "status": "rejected"}
    finally:
        conn.close()
