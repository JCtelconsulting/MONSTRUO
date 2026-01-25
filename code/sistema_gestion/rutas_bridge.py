from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

try:
    from dependencias import require_role, require_session
except Exception:
    def require_role(*roles):
        def dep(): return {"username": "sys", "role": "admin"}
        return dep
    def require_session(x): return {"username": "sys", "role": "admin"}

DB_PATH = "monstruo.db"
router = APIRouter(prefix="/bridge", tags=["bridge"])

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class BridgeMsgIn(BaseModel):
    thread_id: str = "jarvis"
    from_agent: str
    to_agent: str
    kind: str # status|result|request|proposal
    title: str = ""
    body: str = ""
    payload_json: str = "{}"
    requires_approval: bool = False

@router.post("/send")
def send_message(payload: BridgeMsgIn, user=Depends(require_role("admin", "system", "ops", "finance"))):
    conn = get_conn()
    try:
        ts = now_utc_iso()
        approval_status = "pending" if payload.requires_approval else "na"
        
        cur = conn.execute("""
            INSERT INTO bridge_messages (
                thread_id, from_agent, to_agent, kind, title, body, payload_json, 
                requires_approval, approval_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.thread_id, payload.from_agent, payload.to_agent, payload.kind, 
            payload.title, payload.body, payload.payload_json, 
            1 if payload.requires_approval else 0, approval_status, ts
        ))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
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
