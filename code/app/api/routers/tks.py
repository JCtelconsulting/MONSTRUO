from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Header
from fastapi.responses import FileResponse
from typing import List, Optional
from pydantic import BaseModel, Field
from app.core import tickets_service, deps
from app.core.audit_decorator import audit_action
from app.core.tickets import roles as ticket_roles

router = APIRouter(prefix="/api/tks", tags=["tickets"])

ROLES_TECNICOS = set(ticket_roles.ROLES_TECNICOS)
ROLES_GESTION_GLOBAL = set(ticket_roles.ROLES_ADMIN_GESTION)


def _normalize_session_roles(sess: dict) -> List[str]:
    out: List[str] = []
    raw_roles = (sess or {}).get("roles")
    if isinstance(raw_roles, list):
        for item in raw_roles:
            role = str(item or "").strip().lower()
            if role and role not in out:
                out.append(role)
    primary = str((sess or {}).get("role") or "").strip().lower()
    if primary and primary not in out:
        out.insert(0, primary)
    return out


def _normalize_session_role(sess: dict) -> str:
    roles = _normalize_session_roles(sess)
    return roles[0] if roles else ""


def _normalize_session_user(sess: dict) -> str:
    return str((sess or {}).get("username") or "").strip().lower()


def _is_tech_session(sess: dict) -> bool:
    roles = _normalize_session_roles(sess)
    has_management_scope = any(role in ROLES_GESTION_GLOBAL for role in roles)
    has_tech_scope = any(role in ROLES_TECNICOS for role in roles)
    return has_tech_scope and not has_management_scope


def _session_actor_roles(sess: dict):
    roles = _normalize_session_roles(sess)
    if not roles:
        return str((sess or {}).get("role") or "").strip().lower()
    return roles


def _scoped_assignee(sess: dict, requested_assignee: Optional[str]) -> Optional[str]:
    if _is_tech_session(sess):
        return _normalize_session_user(sess) or "__no_user__"
    return requested_assignee


def _ensure_ticket_read_scope(
    ticket_id: int,
    sess: dict,
    *,
    ticket: Optional[dict] = None,
) -> dict:
    current = ticket or tickets_service.get_ticket(ticket_id)
    if not current:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if not _is_tech_session(sess):
        return current

    user = _normalize_session_user(sess)
    assignee = str(current.get("asignado_a") or "").strip().lower()
    if not user or assignee != user:
        raise HTTPException(
            status_code=403,
            detail="Los técnicos solo pueden ver tickets asignados a su usuario.",
        )
    return current


def _require_ticketera_message_editor(
    sess: dict = Depends(deps.require_session_hybrid),
) -> dict:
    roles = _normalize_session_roles(sess)
    if any(role in ROLES_GESTION_GLOBAL for role in roles):
        return sess
    raise HTTPException(
        status_code=403,
        detail="Solo admin o encargado_mesa pueden gestionar mensajes de Ticketera.",
    )


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
    notify_emails: List[str] = Field(default_factory=list)
    subestado: Optional[str] = None
    ticket_security_class: Optional[str] = "internal"


class TicketUpdate(BaseModel):
    estado: Optional[str] = None
    subestado: Optional[str] = None
    severidad: Optional[str] = None
    asignado_a: Optional[str] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    resolucion: Optional[str] = None
    ticket_security_class: Optional[str] = None
    notify_emails: Optional[List[str]] = None


class ComentarioCreate(BaseModel):
    evento: str
    detalle: str


class TicketEmailReply(BaseModel):
    mensaje: str
    asunto: Optional[str] = None


class TicketeraTemplatesIn(BaseModel):
    subject_template: str = ""
    body_template: str = ""


class TicketeraRoutingRuleIn(BaseModel):
    id: int | None = None
    match_type: str
    match_value: str
    categoria: str
    is_active: bool = True


class SpecialtyUpsert(BaseModel):
    username: str
    specialty: str
    max_load: int = 10


class AutomationRuleIn(BaseModel):
    name: str
    is_active: bool = True
    match_json: dict = Field(default_factory=dict)
    action_json: dict = Field(default_factory=dict)


class JiraCommentIn(BaseModel):
    author: Optional[str] = "jira"
    body: str


class JiraIssueIn(BaseModel):
    key: Optional[str] = None
    summary: str
    description: Optional[str] = ""
    status: Optional[str] = "open"
    updated_at: Optional[str] = None
    updated: Optional[str] = None
    priority: Optional[str] = "medium"
    issue_type: Optional[str] = "incidencia"
    categoria: Optional[str] = "general"
    assignee: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_name: Optional[str] = None
    ticket_security_class: Optional[str] = "internal"
    comments: List[JiraCommentIn] = Field(default_factory=list)


class JiraImportRequest(BaseModel):
    dry_run: bool = False
    issues: List[JiraIssueIn]


class JiraBootstrapRunIn(BaseModel):
    dry_run: bool = False
    issues: List[JiraIssueIn] = Field(default_factory=list)
    project_keys: List[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=500)


class JiraDeltaRunIn(BaseModel):
    dry_run: bool = False
    issues: List[JiraIssueIn] = Field(default_factory=list)
    project_keys: List[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=500)
    since: Optional[str] = None


class ParallelGoNoGoIn(BaseModel):
    decision: str = Field(pattern="^(go|no_go)$")
    signers: List[str] = Field(default_factory=list, min_length=1)
    rationale: str
    evidence_refs: List[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    decided_at: Optional[str] = None


class EvidenceEventCreate(BaseModel):
    control_id: str
    artifact_ref: str
    owner: str
    integrity_hash: Optional[str] = ""
    metadata: dict = Field(default_factory=dict)


class TicketTransitionIn(BaseModel):
    to_subestado: str
    motivo: Optional[str] = ""


class TicketApprovalIn(BaseModel):
    step: int
    decision: str
    decision_note: Optional[str] = ""


class LegalHoldCreate(BaseModel):
    ticket_id: int
    reason: str
    case_ref: Optional[str] = ""


class LegalHoldRelease(BaseModel):
    release_note: Optional[str] = ""


class ComplianceExportRunIn(BaseModel):
    from_ts: Optional[str] = None
    to_ts: Optional[str] = None
    scope: Optional[str] = "both"


class CompliancePurgeIn(BaseModel):
    as_of: Optional[str] = None
    max_tickets: Optional[int] = 500


class CustomerAssociateIn(BaseModel):
    email: str
    customer_id: str
    customer_name: str


class EmailDraftLockIn(BaseModel):
    force: bool = False


class EmailDraftHeartbeatIn(BaseModel):
    lock_token: str


class EmailDraftUpdateIn(BaseModel):
    lock_token: str
    version: int = Field(ge=1)
    to_addr: Optional[str] = None
    cc_addrs: Optional[str] = None
    bcc_addrs: Optional[str] = None
    subject: Optional[str] = None
    body_text: Optional[str] = None


class EmailDraftAttachmentDeleteIn(BaseModel):
    lock_token: str


class EmailDraftSendIn(BaseModel):
    lock_token: str
    version: int = Field(ge=1)


class EmailDraftDiscardIn(BaseModel):
    lock_token: str


# ==========================================================================
# AJUSTES DE TICKETS
# ==========================================================================
@router.get("/settings/domain-templates", response_model=dict)
async def get_ticketera_domain_templates_settings(
    sess: dict = Depends(_require_ticketera_message_editor),
):
    return tickets_service.get_ticketera_admin_config()


@router.get("/settings/message-templates", response_model=dict)
async def get_ticketera_message_templates(
    sess: dict = Depends(_require_ticketera_message_editor),
):
    return {"templates": tickets_service.get_ticketera_templates()}


@router.put("/settings/message-templates", response_model=dict)
async def update_ticketera_message_templates(
    payload: TicketeraTemplatesIn,
    sess: dict = Depends(_require_ticketera_message_editor),
):
    try:
        return {
            "ok": True,
            "templates": tickets_service.update_ticketera_templates(
                payload.subject_template,
                payload.body_template,
                sess.get("username", ""),
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/settings/mail-templates/{template_key}", response_model=dict)
async def get_ticketera_mail_template(
    template_key: str,
    sess: dict = Depends(_require_ticketera_message_editor),
):
    try:
        return {
            "ok": True,
            "template": tickets_service.get_ticketera_mail_template(template_key),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/settings/mail-templates/{template_key}", response_model=dict)
async def update_ticketera_mail_template(
    template_key: str,
    payload: TicketeraTemplatesIn,
    sess: dict = Depends(_require_ticketera_message_editor),
):
    try:
        return {
            "ok": True,
            "template": tickets_service.update_ticketera_mail_template(
                template_key,
                payload.subject_template,
                payload.body_template,
                sess.get("username", ""),
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/settings/routing-rules", response_model=dict)
async def upsert_ticketera_routing_rule(
    payload: TicketeraRoutingRuleIn,
    sess: dict = Depends(_require_ticketera_message_editor),
):
    try:
        rule = tickets_service.upsert_ticketera_routing_rule(
            rule_id=payload.id,
            match_type=payload.match_type,
            match_value=payload.match_value,
            categoria=payload.categoria,
            is_active=payload.is_active,
            actor_id=sess.get("username", ""),
        )
        return {"ok": True, "rule": rule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/settings/routing-rules/{rule_id}", response_model=dict)
async def delete_ticketera_routing_rule(
    rule_id: int,
    sess: dict = Depends(_require_ticketera_message_editor),
):
    deleted = tickets_service.delete_ticketera_routing_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Regla de routing no encontrada")
    return {"ok": True, "deleted": True, "rule_id": int(rule_id)}


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
    tech_scope = _is_tech_session(sess)
    scoped_asignado = _scoped_assignee(sess, asignado_a)
    return tickets_service.list_tickets(
        estado=None if tech_scope else status,
        q=None if tech_scope else q,
        categoria=None if tech_scope else categoria,
        asignado_a=scoped_asignado,
        severidad=None if tech_scope else severidad,
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
        notify_emails=body.notify_emails,
        subestado=body.subestado,
        ticket_security_class=body.ticket_security_class,
    )


@router.get("/tickets/{ticket_id}", response_model=dict)
async def get_ticket(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    return _ensure_ticket_read_scope(ticket_id, sess)


@router.get("/tickets/{ticket_id}/email-draft", response_model=dict)
async def get_ticket_email_draft(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    try:
        return tickets_service.get_ticket_email_draft(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/email-draft/lock", response_model=dict)
async def lock_ticket_email_draft(
    ticket_id: int,
    body: EmailDraftLockIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.acquire_ticket_email_draft_lock(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            force=body.force,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/email-draft/lock/heartbeat", response_model=dict)
async def heartbeat_ticket_email_draft(
    ticket_id: int,
    body: EmailDraftHeartbeatIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.heartbeat_ticket_email_draft_lock(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            lock_token=body.lock_token,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/tickets/{ticket_id}/email-draft", response_model=dict)
async def save_ticket_email_draft(
    ticket_id: int,
    body: EmailDraftUpdateIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.save_ticket_email_draft(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            lock_token=body.lock_token,
            version=body.version,
            to_addr=body.to_addr,
            cc_addrs=body.cc_addrs,
            bcc_addrs=body.bcc_addrs,
            subject=body.subject,
            body_text=body.body_text,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/email-draft/attachments", response_model=dict)
async def upload_ticket_email_draft_attachments(
    ticket_id: int,
    lock_token: str = Form(...),
    files: List[UploadFile] = File(default=[]),
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.upload_ticket_email_draft_attachments(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            lock_token=lock_token,
            files=files,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tickets/{ticket_id}/email-draft/attachments/{attachment_id}", response_model=dict)
async def delete_ticket_email_draft_attachment(
    ticket_id: int,
    attachment_id: int,
    body: EmailDraftAttachmentDeleteIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.delete_ticket_email_draft_attachment(
            ticket_id=ticket_id,
            attachment_id=attachment_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            lock_token=body.lock_token,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/email-draft/send", response_model=dict)
async def send_ticket_email_draft(
    ticket_id: int,
    body: EmailDraftSendIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.send_ticket_email_draft(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            lock_token=body.lock_token,
            version=body.version,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/email-draft/discard", response_model=dict)
async def discard_ticket_email_draft(
    ticket_id: int,
    body: EmailDraftDiscardIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.discard_ticket_email_draft(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            lock_token=body.lock_token,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tickets/{ticket_id}/eventos", response_model=dict)
async def get_ticket_eventos(
    ticket_id: int,
    limit: int = Query(120, ge=1, le=500),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    eventos = tickets_service.get_timeline(ticket_id, limit=limit)
    return {"items": eventos}


@router.get("/tickets/{ticket_id}/emails", response_model=dict)
async def get_ticket_emails(
    ticket_id: int,
    format: Optional[str] = Query(None, pattern="^(human)?$"),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    emails = tickets_service.get_ticket_emails(ticket_id, format_human=(format == "human"))
    return {"items": emails}


@router.post("/tickets/{ticket_id}/eventos", response_model=dict)
async def add_evento(
    ticket_id: int,
    body: ComentarioCreate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.add_comment(
            ticket_id,
            sess["username"],
            body.detalle,
            body.evento,
            actor_role=_session_actor_roles(sess),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tickets/{ticket_id}/workflow", response_model=dict)
async def get_ticket_workflow(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    try:
        return tickets_service.get_ticket_workflow(ticket_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/tickets/{ticket_id}/transitions", response_model=dict)
async def transition_ticket(
    ticket_id: int,
    body: TicketTransitionIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.transition_ticket(
            ticket_id=ticket_id,
            to_subestado=body.to_subestado,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
            motivo=body.motivo or "",
            idempotency_key=idempotency_key,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/approvals", response_model=dict)
async def approve_ticket_change(
    ticket_id: int,
    body: TicketApprovalIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.approve_ticket_change(
            ticket_id=ticket_id,
            step=body.step,
            decision=body.decision,
            approver=sess["username"],
            approver_role=_session_actor_roles(sess),
            decision_note=body.decision_note or "",
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tickets/{ticket_id}/approvals", response_model=dict)
async def list_ticket_approvals(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    return {"items": tickets_service.list_ticket_approvals(ticket_id)}


@router.post("/tickets/{ticket_id}/reply-email", response_model=dict)
async def reply_ticket_email(
    ticket_id: int,
    mensaje: str = Form(...),
    asunto: Optional[str] = Form(None),
    to_addr: Optional[str] = Form(None),
    cc_addrs: Optional[str] = Form(None),
    bcc_addrs: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.reply_ticket_email(
            ticket_id=ticket_id,
            author_id=sess["username"],
            mensaje=mensaje,
            author_role=_session_actor_roles(sess),
            asunto=asunto,
            to_addr=to_addr,
            cc_addrs=cc_addrs,
            bcc_addrs=bcc_addrs,
            files=files,
            idempotency_key=idempotency_key,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tickets/{ticket_id}/attachments", response_model=dict)
async def post_ticket_attachments(
    ticket_id: int,
    files: List[UploadFile] = File(default=[]),
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.upload_ticket_attachments(
            ticket_id,
            sess["username"],
            files,
            uploaded_role=_session_actor_roles(sess),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tickets/{ticket_id}/attachments", response_model=dict)
async def get_ticket_attachments(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    return {"items": tickets_service.list_ticket_attachments(ticket_id)}


@router.get("/tickets/{ticket_id}/attachments/{attachment_id}/download")
async def download_ticket_attachment(
    ticket_id: int,
    attachment_id: int,
    inline: bool = Query(False),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    _ensure_ticket_read_scope(ticket_id, sess)
    try:
        item = tickets_service.get_ticket_attachment_for_download(ticket_id, attachment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FileResponse(
        path=item["resolved_path"],
        filename=item.get("filename") or f"ticket-{ticket_id}-attachment-{attachment_id}",
        media_type=item.get("content_type") or "application/octet-stream",
        content_disposition_type="inline" if inline else "attachment",
    )


@router.patch("/tickets/{ticket_id}", response_model=dict)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        result = tickets_service.update_ticket(
            ticket_id,
            body.model_dump(exclude_unset=True),
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except tickets_service.ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    return result


@router.post("/tickets/{ticket_id}/claim", response_model=dict)
async def claim_ticket(
    ticket_id: int,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    try:
        return tickets_service.claim_ticket(
            ticket_id=ticket_id,
            actor_id=sess["username"],
            actor_role=_session_actor_roles(sess),
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tablero", response_model=dict)
async def get_tablero(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Agrupación por estados para el Kanban."""
    scoped_asignado = _scoped_assignee(sess, None) if _is_tech_session(sess) else None

    data = tickets_service.list_tickets(
        limit=120,
        include_total=False,
        asignado_a=scoped_asignado,
    )
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
    return tickets_service.get_stats(
        asignado_a=_scoped_assignee(sess, None) if _is_tech_session(sess) else None
    )


@router.get("/asignacion/timeline", response_model=dict)
async def get_assignment_timeline(
    window_h: int = Query(72, ge=1, le=720),
    limit: int = Query(400, ge=50, le=2000),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Timeline de asignación por técnico + cola de tickets sin asignar."""
    return tickets_service.get_assignment_timeline(
        window_hours=window_h,
        ticket_limit=limit,
        assignee=_scoped_assignee(sess, None) if _is_tech_session(sess) else None,
    )


@router.get("/dashboard/kpi", response_model=dict)
async def get_dashboard_kpi(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """
    KPIs específicos para el Dashboard v3:
    1. Tickets por Cliente (Top 5 + Otros)
    2. Correos pendientes de respuesta (Auto-reply candidate)
    """
    return tickets_service.get_dashboard_kpi()


@router.get("/sla/metrics", response_model=dict)
async def get_sla_metrics(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    return tickets_service.get_sla_metrics(
        date_from=date_from,
        date_to=date_to,
        severity=severity,
        assignee=assignee,
    )


@router.get("/sla/breaches", response_model=dict)
async def get_sla_breaches(
    severity: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    breach_type: Optional[str] = Query(None, pattern="^(frt|ttr)?$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    return tickets_service.list_sla_breaches(
        severity=severity,
        assignee=assignee,
        breach_type=breach_type,
        limit=limit,
        offset=offset,
    )


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
# ENDPOINTS DE AUTOMATIZACIÓN / MIGRACIÓN / EVIDENCIAS
# ==========================================================================
@router.post("/automations/rules", response_model=dict)
async def upsert_automation_rule(
    body: AutomationRuleIn,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    row = tickets_service.upsert_automation_rule(
        name=body.name,
        is_active=body.is_active,
        match_json=body.match_json,
        action_json=body.action_json,
        created_by=sess["username"],
    )
    return {"item": row}


@router.get("/automations/rules", response_model=dict)
async def list_automation_rules(
    only_active: bool = Query(False),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    return {"items": tickets_service.list_automation_rules(only_active=only_active)}


@router.post("/migration/jira/import", response_model=dict)
async def import_jira_tickets(
    body: JiraImportRequest,
    sess: dict = Depends(deps.require_permission("admin.settings"))
):
    issues = [i.model_dump() for i in body.issues]
    return tickets_service.import_jira_issues(
        issues=issues,
        imported_by=sess["username"],
        dry_run=body.dry_run,
    )


@router.post("/migration/jira/bootstrap-open", response_model=dict)
async def run_jira_bootstrap_open(
    body: JiraBootstrapRunIn,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.run_jira_bootstrap_open(
            actor=sess["username"],
            dry_run=body.dry_run,
            issues=[i.model_dump() for i in (body.issues or [])],
            project_keys=body.project_keys or None,
            limit=body.limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/migration/jira/delta-sync/run", response_model=dict)
async def run_jira_delta_sync(
    body: JiraDeltaRunIn,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.run_jira_delta_sync(
            actor=sess["username"],
            dry_run=body.dry_run,
            issues=[i.model_dump() for i in (body.issues or [])],
            project_keys=body.project_keys or None,
            limit=body.limit,
            since=body.since,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/migration/jira/runs", response_model=dict)
async def list_jira_runs(
    run_type: Optional[str] = Query(None, pattern="^(bootstrap|delta)?$"),
    status: Optional[str] = Query(None, pattern="^(running|completed|failed|completed_with_errors)?$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.list_jira_sync_runs(
        run_type=run_type,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/migration/jira/reconciliation/daily", response_model=dict)
async def get_jira_reconciliation_daily(
    snapshot_date: Optional[str] = Query(None),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.get_jira_reconciliation_daily(snapshot_date=snapshot_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/parallel/kpi/daily", response_model=dict)
async def list_parallel_kpi_daily(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.list_parallel_kpi_daily(
            date_from=from_date,
            date_to=to_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/parallel/go-no-go", response_model=dict)
async def register_parallel_go_no_go(
    body: ParallelGoNoGoIn,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        item = tickets_service.record_parallel_go_no_go_decision(
            decision=body.decision,
            decided_by=sess["username"],
            signers=body.signers,
            rationale=body.rationale,
            evidence_refs=body.evidence_refs or [],
            metrics=body.metrics or {},
            decided_at=body.decided_at,
        )
        return {"item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/evidence/events", response_model=dict)
async def create_evidence_event(
    body: EvidenceEventCreate,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    item = tickets_service.create_evidence_event(
        control_id=body.control_id,
        artifact_ref=body.artifact_ref,
        owner=body.owner,
        integrity_hash=body.integrity_hash or "",
        metadata=body.metadata or {},
    )
    return {"item": item}


@router.get("/evidence/events", response_model=dict)
async def list_evidence_events(
    control_id: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.list_evidence_events(
        control_id=control_id,
        owner=owner,
        limit=limit,
        offset=offset,
    )


# ==========================================================================
# ENDPOINTS DE COMPLIANCE CORE
# ==========================================================================
@router.post("/compliance/legal-holds", response_model=dict)
async def create_legal_hold(
    body: LegalHoldCreate,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        item = tickets_service.create_ticket_legal_hold(
            ticket_id=body.ticket_id,
            reason=body.reason,
            actor=sess["username"],
            case_ref=body.case_ref,
        )
        return {"item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compliance/legal-holds/{hold_id}/release", response_model=dict)
async def release_legal_hold(
    hold_id: int,
    body: LegalHoldRelease,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        item = tickets_service.release_ticket_legal_hold(
            hold_id=hold_id,
            release_note=body.release_note or "",
            actor=sess["username"],
        )
        return {"item": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/compliance/legal-holds", response_model=dict)
async def list_legal_holds(
    ticket_id: Optional[int] = Query(None),
    active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.list_ticket_legal_holds(
        ticket_id=ticket_id,
        active=active,
        limit=limit,
        offset=offset,
    )


@router.post("/compliance/exports/run", response_model=dict)
async def run_compliance_export(
    body: ComplianceExportRunIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        if not (idempotency_key or "").strip():
            raise HTTPException(status_code=400, detail="Idempotency-Key requerido")
        return tickets_service.run_compliance_export(
            actor=sess["username"],
            from_ts=body.from_ts,
            to_ts=body.to_ts,
            scope=body.scope,
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/compliance/exports/runs", response_model=dict)
async def list_compliance_export_runs(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.list_compliance_export_runs(
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/compliance/purge/dry-run", response_model=dict)
async def run_compliance_purge_dry(
    body: CompliancePurgeIn,
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.run_compliance_purge(
            actor=sess["username"],
            dry_run=True,
            as_of=body.as_of,
            max_tickets=body.max_tickets,
            idempotency_key=None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/compliance/purge/run", response_model=dict)
async def run_compliance_purge(
    body: CompliancePurgeIn,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        if not (idempotency_key or "").strip():
            raise HTTPException(status_code=400, detail="Idempotency-Key requerido")
        return tickets_service.run_compliance_purge(
            actor=sess["username"],
            dry_run=False,
            as_of=body.as_of,
            max_tickets=body.max_tickets,
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/compliance/purge/runs", response_model=dict)
async def list_compliance_purge_runs(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.list_compliance_purge_runs(
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/compliance/hash-chain/verify", response_model=dict)
async def verify_compliance_hash_chain(
    stream: str = Query(..., pattern="^(audit|evidence)$"),
    from_id: Optional[int] = Query(None, ge=1),
    to_id: Optional[int] = Query(None, ge=1),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.verify_hash_chain(
            stream=stream,
            from_id=from_id,
            to_id=to_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# ENDPOINTS DE OPERACIÓN DE CANALES
# ==========================================================================
@router.get("/channels/status", response_model=dict)
async def get_channels_status(
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.get_channels_status()


@router.get("/ops/queue-health", response_model=dict)
async def get_queue_health(
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.get_jobs_queue_health()


@router.get("/channels/notifications", response_model=dict)
async def list_channel_notifications(
    status: Optional[str] = Query(None, pattern="^(pending|dispatching|sent|failed|cancelled)?$"),
    channel: Optional[str] = Query(None, pattern="^(whatsapp|3cx)?$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    return tickets_service.list_channel_notifications(
        status=status,
        channel=channel,
        limit=limit,
        offset=offset,
    )


@router.post("/channels/notifications/{notification_id}/retry", response_model=dict)
async def retry_channel_notification(
    notification_id: int,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    sess: dict = Depends(deps.require_permission("tickets:compliance"))
):
    try:
        return tickets_service.retry_channel_notification(
            notification_id=notification_id,
            actor=sess["username"],
            idempotency_key=idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==========================================================================
# ENDPOINT: MIS TICKETS
# ==========================================================================
@router.get("/mis-tickets", response_model=dict)
async def get_mis_tickets(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Mis tickets asignados."""
    return tickets_service.list_tickets(asignado_a=sess["username"], limit=50)


# ==========================================================================
# ENDPOINTS DE CLIENTES
# ==========================================================================
@router.post("/customers/associate-email", response_model=dict)
async def associate_email(
    body: CustomerAssociateIn,
    sess: dict = Depends(deps.require_permission("tickets:write"))
):
    """Asocia un email a un cliente."""
    try:
        tickets_service.associate_email_to_client(body.email, body.customer_id, body.customer_name, sess["username"])
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/customers/search", response_model=dict)
async def search_customers(
    q: Optional[str] = Query(""),
    limit: int = Query(0, ge=0, le=5000),
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Busca clientes para asociar."""
    items = tickets_service.search_customers(q or "", limit=limit)
    return {"items": items}
async def get_my_tickets(
    sess: dict = Depends(deps.require_permission("tickets:read"))
):
    """Tickets asignados al usuario logueado."""
    return tickets_service.list_tickets(asignado_a=sess["username"], limit=50)
