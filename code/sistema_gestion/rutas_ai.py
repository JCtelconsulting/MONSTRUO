"""
Router para endpoints de Asistente IA (recomendaciones).
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import json

import nucleo as db
from dependencias import require_session, require_roles

router = APIRouter(prefix="/ai", tags=["ai"])

class ApprovalRequest(BaseModel):
    notes: Optional[str] = ""

@router.get("/recommendations")
def list_recommendations(
    authorization: Optional[str] = Header(default=None),
    status: str = "pending"
):
    """Listar recomendaciones IA filtradas por estado"""
    sess = require_session(authorization)
    require_roles(sess, ["admin", "finance", "ops"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        filter_sql = ""
        params = []
        if status != "all":
            filter_sql = "WHERE status = ?"
            params.append(status)
        
        rows = conn.execute(f"""
            SELECT id, event_id, source, kind, title, summary,
                   recommended_actions_json, customer_message_draft,
                   requires_approval, status, created_at,
                   approved_at, approved_by
            FROM ai_recommendations
            {filter_sql}
            ORDER BY created_at DESC
            LIMIT 100
        """, tuple(params)).fetchall()
        
        items = []
        for r in rows:
            try:
                actions = json.loads(r["recommended_actions_json"])
            except:
                actions = []
            
            items.append({
                "id": r["id"],
                "event_id": r["event_id"],
                "source": r["source"],
                "kind": r["kind"],
                "title": r["title"],
                "summary": r["summary"],
                "recommended_actions": actions,
                "customer_message_draft": r["customer_message_draft"],
                "requires_approval": bool(r["requires_approval"]),
                "status": r["status"],
                "created_at": r["created_at"],
                "approved_at": r["approved_at"],
                "approved_by": r["approved_by"]
            })
        
        return {"items": items}
    finally:
        conn.close()

@router.get("/recommendations/{rec_id}")
def get_recommendation(
    rec_id: int,
    authorization: Optional[str] = Header(default=None)
):
    """Obtener detalle de una recomendación"""
    sess = require_session(authorization)
    require_roles(sess, ["admin", "finance", "ops"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute("""
            SELECT id, event_id, source, kind, title, summary,
                   recommended_actions_json, customer_message_draft,
                   requires_approval, status, raw_json, created_at,
                   approved_at, approved_by
            FROM ai_recommendations
            WHERE id = ?
        """, (rec_id,)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Recomendación no encontrada")
        
        try:
            actions = json.loads(row["recommended_actions_json"])
        except:
            actions = []
        
        try:
            raw = json.loads(row["raw_json"])
        except:
            raw = {}
        
        return {
            "id": row["id"],
            "event_id": row["event_id"],
            "source": row["source"],
            "kind": row["kind"],
            "title": row["title"],
            "summary": row["summary"],
            "recommended_actions": actions,
            "customer_message_draft": row["customer_message_draft"],
            "requires_approval": bool(row["requires_approval"]),
            "status": row["status"],
            "raw_json": raw,
            "created_at": row["created_at"],
            "approved_at": row["approved_at"],
            "approved_by": row["approved_by"]
        }
    finally:
        conn.close()

@router.post("/recommendations/{rec_id}/approve")
def approve_recommendation(
    rec_id: int,
    body: ApprovalRequest,
    authorization: Optional[str] = Header(default=None)
):
    """Aprobar una recomendación (solo cambia estado, no ejecuta acciones)"""
    sess = require_session(authorization)
    require_roles(sess, ["admin", "finance"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        # Verificar que existe y está pendiente
        rec = conn.execute("""
            SELECT id, status FROM ai_recommendations
            WHERE id = ?
        """, (rec_id,)).fetchone()
        
        if not rec:
            raise HTTPException(status_code=404, detail="Recomendación no encontrada")
        
        if rec["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Recomendación ya está en status '{rec['status']}'")
        
        # Actualizar estado
        ts = datetime.utcnow().isoformat() + "+00:00"
        conn.execute("""
            UPDATE ai_recommendations
            SET status = 'approved',
                approved_at = ?,
                approved_by = ?
            WHERE id = ?
        """, (ts, sess["username"], rec_id))
        
        # Auditoría
        audit_msg = f"Recommendation {rec_id} approved by {sess['username']}"
        if body.notes:
            audit_msg += f": {body.notes}"
        
        conn.execute("""
            INSERT INTO audit_events (username, event_type, details, created_at)
            VALUES (?, 'ai_recommendation_approved', ?, ?)
        """, (sess["username"], audit_msg, ts))
        
        conn.commit()
        
        return {"status": "approved", "approved_at": ts, "approved_by": sess["username"]}
    finally:
        conn.close()

@router.post("/recommendations/{rec_id}/reject")
def reject_recommendation(
    rec_id: int,
    body: ApprovalRequest,
    authorization: Optional[str] = Header(default=None)
):
    """Rechazar una recomendación"""
    sess = require_session(authorization)
    require_roles(sess, ["admin", "finance"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        # Verificar que existe y está pendiente
        rec = conn.execute("""
            SELECT id, status FROM ai_recommendations
            WHERE id = ?
        """, (rec_id,)).fetchone()
        
        if not rec:
            raise HTTPException(status_code=404, detail="Recomendación no encontrada")
        
        if rec["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Recomendación ya está en status '{rec['status']}'")
        
        # Actualizar estado
        ts = datetime.utcnow().isoformat() + "+00:00"
        conn.execute("""
            UPDATE ai_recommendations
            SET status = 'rejected',
                approved_at = ?,
                approved_by = ?
            WHERE id = ?
        """, (ts, sess["username"], rec_id))
        
        # Auditoría
        audit_msg = f"Recommendation {rec_id} rejected by {sess['username']}"
        if body.notes:
            audit_msg += f": {body.notes}"
        
        conn.execute("""
            INSERT INTO audit_events (username, event_type, details, created_at)
            VALUES (?, 'ai_recommendation_rejected', ?, ?)
        """, (sess["username"], audit_msg, ts))
        
        conn.commit()
        
        return {"status": "rejected", "rejected_at": ts, "rejected_by": sess["username"]}
    finally:
        conn.close()
