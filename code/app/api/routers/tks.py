from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, UploadFile, File, Query
from typing import List, Optional
import shutil
import os
import time
from pydantic import BaseModel
from app.core import tickets_service, deps
from app.core.audit_decorator import audit_action

router = APIRouter(prefix="/api/tks", tags=["tickets"])

# Modelos Pydantic en Español para match con UI
class TicketCreate(BaseModel):
    titulo: str
    descripcion: str = ""
    tipo: str = "incidencia"
    severidad: str = "media"
    origen: str = "manual"

class TicketUpdate(BaseModel):
    estado: Optional[str] = None
    severidad: Optional[str] = None
    asignado_a: Optional[str] = None
    descripcion: Optional[str] = None

class ComentarioCreate(BaseModel):
    evento: str
    detalle: str

# Endpoints
@router.get("/tickets", response_model=dict)
async def list_tickets(
    status: Optional[str] = None,
    q: Optional[str] = Query(None),
    limit: int = 100,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Listar tickets."""
    items = tickets_service.list_tickets(status, q, limit)
    return {"items": items}

@router.post("/tickets", response_model=dict)
@audit_action("CREATE_TICKET", severity="info")
async def create_ticket(
    body: TicketCreate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    return tickets_service.create_ticket(
        body.titulo,
        body.descripcion,
        sess["username"],
        body.severidad,
        body.tipo
    )

@router.get("/tickets/{ticket_id}", response_model=dict)
async def get_ticket(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    ticket = tickets_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return ticket

@router.get("/tickets/{ticket_id}/eventos", response_model=dict)
async def get_ticket_eventos(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    eventos = tickets_service.get_timeline(ticket_id)
    # UI expects {items: [...]}
    return {"items": eventos}

@router.post("/tickets/{ticket_id}/eventos", response_model=dict)
async def add_evento(
    ticket_id: int,
    body: ComentarioCreate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    return tickets_service.add_comment(ticket_id, sess["username"], body.detalle, body.evento)

@router.patch("/tickets/{ticket_id}", response_model=dict)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    return tickets_service.update_ticket(ticket_id, body.dict(exclude_unset=True))

@router.get("/tablero", response_model=dict)
async def get_tablero(sess: dict = Depends(deps.require_permission("tickets:read"))):
    """Agrupación por estados para el Kanban."""
    tickets = tickets_service.list_tickets(limit=200)
    kanban = {
        "abierto": [],
        "en_progreso": [],
        "resuelto": [],
        "cerrado": []
    }
    for t in tickets:
        estado = t.get("estado", "abierto")
        if estado in kanban:
            kanban[estado].append(t)
    return {"kanban": kanban}

@router.get("/stats", response_model=dict)
async def get_stats(sess: dict = Depends(deps.require_permission("tickets:read"))):
    """Métricas para el Dashboard."""
    return tickets_service.get_stats()
