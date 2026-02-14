from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from app.core import tickets_service, deps
from app.core.audit_decorator import audit_action

router = APIRouter(prefix="/api/tks", tags=["tickets"])


# ==========================================================================
# MODELOS PYDANTIC
# ==========================================================================
class TicketCreate(BaseModel):
    titulo: str
    descripcion: str = ""
    tipo: str = "incidencia"
    severidad: str = "media"
    origen: str = "manual"
    categoria: Optional[str] = None
    origen_email: Optional[str] = None
    cliente_nombre: Optional[str] = None


class TicketUpdate(BaseModel):
    estado: Optional[str] = None
    severidad: Optional[str] = None
    asignado_a: Optional[str] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    resolucion: Optional[str] = None


class ComentarioCreate(BaseModel):
    evento: str
    detalle: str


class TicketEmailReply(BaseModel):
    mensaje: str
    asunto: Optional[str] = None


class SpecialtyUpsert(BaseModel):
    username: str
    specialty: str
    max_load: int = 10


# ==========================================================================
# ENDPOINTS DE TICKETS
# ==========================================================================
@router.get("/tickets", response_model=dict)
async def list_tickets(
    status: Optional[str] = None,
    q: Optional[str] = Query(None),
    categoria: Optional[str] = None,
    asignado_a: Optional[str] = None,
    severidad: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = 0,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Listar tickets con filtros avanzados."""
    return tickets_service.list_tickets(
        estado=status, q=q, categoria=categoria,
        asignado_a=asignado_a, severidad=severidad,
        limit=limit, offset=offset
    )


@router.post("/tickets", response_model=dict)
@audit_action("CREATE_TICKET", severity="info")
async def create_ticket(
    body: TicketCreate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    """Crear ticket con auto-clasificación y auto-asignación."""
    return tickets_service.create_ticket(
        titulo=body.titulo,
        descripcion=body.descripcion,
        creador_id=sess["username"],
        severidad=body.severidad,
        tipo=body.tipo,
        categoria=body.categoria,
        origen_email=body.origen_email,
        cliente_nombre=body.cliente_nombre,
    )


@router.get("/tickets/{ticket_id}", response_model=dict)
async def get_ticket(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    ticket = tickets_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")

    # Marcar notificaciones como vistas cuando el técnico abre el ticket
    tickets_service.marcar_notificacion_vista(ticket_id, sess["username"])
    return ticket


@router.get("/tickets/{ticket_id}/eventos", response_model=dict)
async def get_ticket_eventos(
    ticket_id: int,
    limit: int = Query(120, ge=1, le=500),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    eventos = tickets_service.get_timeline(ticket_id, limit=limit)
    return {"items": eventos}


@router.get("/tickets/{ticket_id}/emails", response_model=dict)
async def get_ticket_emails(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    emails = tickets_service.get_ticket_emails(ticket_id)
    return {"items": emails}


@router.post("/tickets/{ticket_id}/eventos", response_model=dict)
async def add_evento(
    ticket_id: int,
    body: ComentarioCreate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    return tickets_service.add_comment(ticket_id, sess["username"], body.detalle, body.evento)


from fastapi import UploadFile, File, Form

@router.post("/tickets/{ticket_id}/reply-email", response_model=dict)
async def reply_ticket_email(
    ticket_id: int,
    mensaje: str = Form(...),
    asunto: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.reply_ticket_email(
            ticket_id=ticket_id,
            author_id=sess["username"],
            mensaje=mensaje,
            asunto=asunto,
            files=files
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/tickets/{ticket_id}", response_model=dict)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    result = tickets_service.update_ticket(ticket_id, body.dict(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return result


@router.get("/tablero", response_model=dict)
async def get_tablero(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Agrupación por estados para el Kanban."""
    data = tickets_service.list_tickets(limit=120, include_total=False)
    kanban = {
        "abierto": [],
        "en_progreso": [],
        "resuelto": [],
        "cerrado": []
    }
    for t in data["items"]:
        estado = t.get("estado", "abierto")
        if estado in kanban:
            kanban[estado].append(t)
    return {"kanban": kanban}


@router.get("/stats", response_model=dict)
async def get_stats(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Métricas para el Dashboard."""
    return tickets_service.get_stats()


# ==========================================================================
# ENDPOINTS DE NOTIFICACIONES
# ==========================================================================
@router.get("/notificaciones", response_model=dict)
async def get_my_notifications(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Notificaciones in-app del usuario logueado."""
    items = tickets_service.get_notificaciones_pendientes(sess["username"])
    return {"items": items, "total": len(items)}


# ==========================================================================
# ENDPOINTS DE ESPECIALIDADES
# ==========================================================================
@router.get("/especialidades", response_model=dict)
async def list_specialties(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Listar especialidades de técnicos."""
    items = tickets_service.list_specialties()
    return {"items": items}


@router.post("/especialidades", response_model=dict)
async def upsert_specialty(
    body: SpecialtyUpsert,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Crear o actualizar especialidad."""
    return tickets_service.upsert_specialty(body.username, body.specialty, body.max_load)


@router.patch("/especialidades/{username}/disponibilidad", response_model=dict)
async def toggle_availability(
    username: str,
    available: bool = True,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Activar/desactivar disponibilidad."""
    tickets_service.toggle_availability(username, available)
    return {"ok": True, "username": username, "is_available": available}


@router.delete("/especialidades/{username}/{specialty}", response_model=dict)
async def delete_specialty(
    username: str,
    specialty: str,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    """Eliminar especialidad."""
    tickets_service.delete_specialty(username, specialty)
    return {"ok": True}


# ==========================================================================
# ENDPOINT: MIS TICKETS
# ==========================================================================
@router.get("/mis-tickets", response_model=dict)
async def get_my_tickets(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Tickets asignados al usuario logueado."""
    return tickets_service.list_tickets(asignado_a=sess["username"], limit=50)
