from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import bus
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

# Reuse existing auth deps if present in project
try:
    from dependencias import require_role  # type: ignore
except Exception:
    def require_role(*roles):
        def dep(): return {"username": "system", "role": "admin"}
        return dep

DB_PATH = "monstruo.db"
router = APIRouter(prefix="/crm", tags=["crm"])

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def audit(conn: sqlite3.Connection, actor: str, action: str, entity_type: str, entity_id: str, details: Dict[str, Any]) -> None:
    conn.execute("""
      INSERT INTO crm_audit_events (actor, action, entity_type, entity_id, details, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    """, (actor, action, entity_type, entity_id, json.dumps(details, ensure_ascii=True, sort_keys=True), now_utc_iso()))

# --- Models ---
class ConsentUpsertIn(BaseModel):
    purpose: str = Field(..., pattern="^(marketing|sales|ops|support)$")
    channel: str = Field(..., pattern="^(email|phone|sms|whatsapp)$")
    status: str = Field(..., pattern="^(granted|denied|unknown)$")
    legal_basis: str = Field(..., pattern="^(consent|contract|legitimate_interest|public_source|other)$")
    evidence: str = ""
    notice_version: str = ""

class OptOutIn(BaseModel):
    channel: str = Field(..., pattern="^(email|phone|sms|whatsapp)$")
    reason: str = Field(..., pattern="^(no_molestar|opt_out|legal|complaint|other)$")
    source: str = "manual"

class InteractionIn(BaseModel):
    kind: str = Field(..., pattern="^(call|email|meeting|note)$")
    direction: str = Field(..., pattern="^(inbound|outbound|internal)$")
    purpose: str = Field(..., pattern="^(marketing|sales|ops|support)$")
    channel: str = Field(..., pattern="^(email|phone|sms|whatsapp)$")
    occurred_at: str = ""
    outcome: str = ""
    notes: str = ""

class CompanyIn(BaseModel):
    name: str
    vat_id: str = ""
    domain: str = ""

class OppIn(BaseModel):
    company_id: int
    title: str
    stage: str = Field(..., pattern="^(lead|qualified|proposal|won|lost)$")
    value_estimated: float = 0
    owner_role: str = "sales"
    next_action: str = ""
    next_action_due: str = ""

class OppUpdateIn(BaseModel):
    stage: str = Field(..., pattern="^(lead|qualified|proposal|won|lost)$")
    next_action: str
    next_action_due: str = ""
    value_estimated: float = 0

# --- Contacts Endpoints ---

@router.get("/contacts")
def list_contacts(q: str = "", limit: int = 50, offset: int = 0, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    q = (q or "").strip()
    if limit > 200: limit = 200
    conn = get_conn()
    try:
        sql = """
          SELECT c.id, c.full_name, c.email, c.phone, c.title, c.is_active, co.name as company
          FROM crm_contacts c
          LEFT JOIN crm_companies co ON c.company_id = co.id
        """
        params = []
        if q:
            sql += " WHERE c.full_name LIKE ? OR c.email LIKE ? OR c.phone LIKE ? OR co.name LIKE ?"
            lk = f"%{q}%"
            params = [lk, lk, lk, lk]
        
        sql += " ORDER BY c.updated_at DESC, c.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset}
    finally:
        conn.close()

@router.get("/contacts/{contact_id}")
def get_contact(contact_id: int, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        c = conn.execute("""
          SELECT c.*, co.name as company_name
          FROM crm_contacts c
          LEFT JOIN crm_companies co ON c.company_id = co.id
          WHERE c.id=?
        """, (contact_id,)).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="contact_not_found")

        cons = conn.execute("SELECT * FROM crm_consents WHERE contact_id=? ORDER BY purpose, channel", (contact_id,)).fetchall()
        
        # simplified suppression lookup logic for brevity
        sup_email = (c["email"] or "").strip().lower()
        sup_phone = "".join(ch for ch in (c["phone"] or "") if ch.isdigit())
        sup = conn.execute("""
          SELECT channel, value, reason, source, created_at
          FROM crm_suppression
          WHERE (channel='email' AND value=?) OR (channel IN ('phone','sms','whatsapp') AND value=?)
        """, (sup_email, sup_phone)).fetchall()

        inter = conn.execute("SELECT * FROM crm_interactions WHERE contact_id=? ORDER BY created_at DESC LIMIT 100", (contact_id,)).fetchall()

        return {
            "contact": dict(c),
            "consents": [dict(r) for r in cons],
            "suppression": [dict(r) for r in sup],
            "interactions": [dict(r) for r in inter],
        }
    finally:
        conn.close()

def _contact_value_for_channel(contact_row: sqlite3.Row, channel: str) -> str:
    if channel == "email":
        return (contact_row["email"] or "").strip().lower()
    return "".join(ch for ch in (contact_row["phone"] or "") if ch.isdigit())

@router.post("/contacts/{contact_id}/opt-out")
def opt_out(contact_id: int, payload: OptOutIn, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        c = conn.execute("SELECT * FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
        if not c: raise HTTPException(404, "contact_not_found")

        value = _contact_value_for_channel(c, payload.channel)
        if not value: raise HTTPException(400, "missing_value")
        
        ts = now_utc_iso()
        conn.execute("INSERT OR IGNORE INTO crm_suppression (channel, value, reason, source, created_at) VALUES (?,?,?,?,?)",
                     (payload.channel, value, payload.reason, payload.source, ts))
        
        # Deny marketing
        conn.execute("""
          INSERT INTO crm_consents (contact_id, purpose, channel, status, legal_basis, evidence, notice_version, granted_at, revoked_at, created_at, updated_at)
          VALUES (?, 'marketing', ?, 'denied', 'other', ?, '', '', ?, ?, ?)
          ON CONFLICT(contact_id, purpose, channel) DO UPDATE SET status='denied', revoked_at=?, updated_at=?
        """, (contact_id, payload.channel, f"opt_out {payload.reason}", ts, ts, ts, ts, ts, ts)) # simplistic params
        
        audit(conn, user.get("username","sys"), "opt_out", "contact", str(contact_id), payload.model_dump())
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

@router.post("/contacts/{contact_id}/consent")
def upsert_consent(contact_id: int, payload: ConsentUpsertIn, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        c = conn.execute("SELECT id FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
        if not c: raise HTTPException(404, "contact_not_found")
        ts = now_utc_iso()
        g_at = ts if payload.status == "granted" else ""
        r_at = ts if payload.status == "denied" else ""
        
        conn.execute("""
          INSERT INTO crm_consents (contact_id, purpose, channel, status, legal_basis, evidence, notice_version, granted_at, revoked_at, created_at, updated_at)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(contact_id, purpose, channel) DO UPDATE SET
            status=excluded.status, legal_basis=excluded.legal_basis, evidence=excluded.evidence,
            granted_at=CASE WHEN excluded.status='granted' THEN excluded.granted_at ELSE crm_consents.granted_at END,
            revoked_at=CASE WHEN excluded.status='denied' THEN excluded.revoked_at ELSE crm_consents.revoked_at END,
            updated_at=excluded.updated_at
        """, (contact_id, payload.purpose, payload.channel, payload.status, payload.legal_basis, payload.evidence, payload.notice_version, g_at, r_at, ts, ts))
        
        audit(conn, user.get("username","sys"), "consent_change", "consent", f"{contact_id}:{payload.purpose}", payload.model_dump())
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

@router.post("/contacts/{contact_id}/interaction")
def add_interaction(contact_id: int, payload: InteractionIn, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        c = conn.execute("SELECT id FROM crm_contacts WHERE id=?", (contact_id,)).fetchone()
        if not c: raise HTTPException(404)
        ts = now_utc_iso()
        occurred = payload.occurred_at.strip() or ts
        conn.execute("INSERT INTO crm_interactions (contact_id, kind, direction, purpose, channel, occurred_at, outcome, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (contact_id, payload.kind, payload.direction, payload.purpose, payload.channel, occurred, payload.outcome, payload.notes, ts))
        audit(conn, user.get("username","sys"), "create", "interaction", str(contact_id), payload.model_dump())
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

@router.get("/suppression")
def list_suppression(q: str = "", limit: int = 50, offset: int = 0, user=Depends(require_role("admin", "finance", "ops"))):
    conn = get_conn()
    try:
        sql = "SELECT * FROM crm_suppression"
        params = []
        if q:
            sql += " WHERE value LIKE ?"
            params.append(f"%{q}%")
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset}
    finally:
        conn.close()

# --- Companies Endpoints ---

@router.get("/companies")
def list_companies(q: str = "", limit: int = 50, offset: int = 0, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        sql = "SELECT * FROM crm_companies"
        params = []
        if q:
            sql += " WHERE name LIKE ?"
            params.append(f"%{q}%")
        sql += " ORDER BY name ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.get("/companies/{company_id}")
def get_company(company_id: int, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        comp = conn.execute("SELECT * FROM crm_companies WHERE id=?", (company_id,)).fetchone()
        if not comp: raise HTTPException(404, "company_not_found")
        
        contacts = conn.execute("SELECT id, full_name, email, phone, title FROM crm_contacts WHERE company_id=? ORDER BY full_name", (company_id,)).fetchall()
        opps = conn.execute("SELECT * FROM crm_opportunities WHERE company_id=? ORDER BY updated_at DESC", (company_id,)).fetchall()
        
        return {
            "company": dict(comp),
            "contacts": [dict(r) for r in contacts],
            "opportunities": [dict(r) for r in opps]
        }
    finally:
        conn.close()

@router.post("/companies")
def create_company(payload: CompanyIn, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        ts = now_utc_iso()
        cur = conn.execute("INSERT INTO crm_companies (name, vat_id, domain, source_system, created_at, updated_at) VALUES (?,?,?, 'manual', ?, ?)",
                           (payload.name, payload.vat_id, payload.domain, ts, ts))
        cid = cur.lastrowid
        audit(conn, user.get("username","sys"), "create", "company", str(cid), payload.model_dump())
        conn.commit()
        return {"ok": True, "id": cid}
    except sqlite3.IntegrityError:
        raise HTTPException(400, "duplicate_company")
    finally:
        conn.close()

# --- Opportunities Endpoints ---

@router.post("/opportunities")
def create_opportunity(payload: OppIn, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        ts = now_utc_iso()
        cur = conn.execute("""
            INSERT INTO crm_opportunities (company_id, title, stage, value_estimated, owner_role, next_action, next_action_due, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (payload.company_id, payload.title, payload.stage, payload.value_estimated, payload.owner_role, payload.next_action, payload.next_action_due, ts, ts))
        oid = cur.lastrowid
        audit(conn, user.get("username","sys"), "create", "opportunity", str(oid), payload.model_dump())
        conn.commit()
        return {"ok": True, "id": oid}
    finally:
        conn.close()

@router.post("/opportunities/{opp_id}")
def update_opportunity(opp_id: int, payload: OppUpdateIn, user=Depends(require_role("admin", "ops", "finance", "sales"))):
    conn = get_conn()
    try:
        o = conn.execute("SELECT * FROM crm_opportunities WHERE id=?", (opp_id,)).fetchone()
        if not o: raise HTTPException(404, "opp_not_found")
        ts = now_utc_iso()
        
        # Check for deal_won event
        if payload.stage == "won" and o["stage"] != "won":
            bus.emit_event(conn, "deal_won", "crm", "opportunity", str(opp_id), 
                           {"value": payload.value_estimated, "title": o["title"], "owner": o["owner_role"]})
            
        conn.execute("""
            UPDATE crm_opportunities SET stage=?, next_action=?, next_action_due=?, value_estimated=?, updated_at=?
            WHERE id=?
        """, (payload.stage, payload.next_action, payload.next_action_due, payload.value_estimated, ts, opp_id))
        
        audit(conn, user.get("username","sys"), "update", "opportunity", str(opp_id), payload.model_dump())
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
