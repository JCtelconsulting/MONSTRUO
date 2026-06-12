from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from plataforma.core import db, deps
from crm.backend.services import service as crm_service

router = APIRouter(prefix="/api/crm", tags=["crm"])

@router.get("/customers", response_model=List[dict])
async def search_customers(
    q: Optional[str] = Query(None, description="Search by name or RUT"),
    limit: int = 50,
    sess: dict = Depends(deps.require_permission("crm:read"))
):
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM customers"
        params = []
        if q:
            sql += " WHERE name LIKE ? OR rut LIKE ? OR fantasy_name LIKE ?"
            params = [f"%{q}%", f"%{q}%", f"%{q}%"]
        sql += " ORDER BY name ASC LIMIT ?"
        params.append(limit)
        cursor = conn.execute(sql, tuple(params))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.get("/customers/{customer_id}", response_model=dict)
async def get_customer(
    customer_id: int,
    sess: dict = Depends(deps.require_permission("crm:read"))
):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Customer not found")
        return dict(row)
    finally:
        conn.close()

class InteractionIn(BaseModel):
    type: str
    content: str

@router.get("/customers/{customer_id}/account", response_model=dict)
async def get_account(customer_id: str, sess: dict = Depends(deps.require_permission("crm:read"))):
    return crm_service.get_account_status(customer_id)

@router.get("/customers/{customer_id}/timeline", response_model=List[dict])
async def get_timeline(customer_id: int, sess: dict = Depends(deps.require_permission("crm:read"))):
    return crm_service.get_timeline(customer_id)

@router.post("/customers/{customer_id}/interactions", response_model=dict)
async def add_interaction(customer_id: int, payload: InteractionIn, sess: dict = Depends(deps.require_permission("crm:write"))):
    try:
        return crm_service.add_interaction(customer_id, payload.type, payload.content, sess["username"])
    except ValueError:
        raise HTTPException(status_code=404, detail="Customer not found")
