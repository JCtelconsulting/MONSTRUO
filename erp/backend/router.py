from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from plataforma.core import deps, db
from datetime import datetime, date
import json
from erp.backend.services.laudus import LaudusClient
from erp.backend.services import service as facturacion_service
from plataforma.core import jobs_engine
from bodega.backend import service as bodega_service
from erp.backend.services import indicators_service

print("DEBUG: Loading facturacion.py module...")

router = APIRouter(prefix="/api/facturacion", tags=["facturacion"])


class BillingRuleSchema(BaseModel):
    customer_id: str
    description: str = ""
    currency: str = "CLP"
    uf_rule: str = "VALOR_DIA"
    uf_custom_value: float = 0.0
    base_amount: float = 0.0
    frequency_months: int = 1
    day_of_month: int = 5
    is_active: bool = True
    auto_issue: bool = False


@router.get("/uf", summary="Obtener valor UF actual")
async def get_uf():
    val = indicators_service.get_uf_value()
    if not val:
        raise HTTPException(
            status_code=503, detail="No se pudo obtener el valor de la UF"
        )
    return {"uf": val, "fecha": date.today().isoformat()}


@router.get("/ciclos", summary="Listar reglas de facturación")
async def list_rules(sess: dict = Depends(deps.require_permission("invoice:read"))):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                b.*,
                COALESCE(NULLIF(TRIM(c.fantasy_name), ''), NULLIF(TRIM(c.name), ''), TRIM(c.rut), TRIM(c.external_id), b.customer_id) AS customer_name
            FROM billing_rules b
            LEFT JOIN customers c
              ON TRIM(c.external_id) = TRIM(b.customer_id)
              OR CAST(c.id AS TEXT) = TRIM(b.customer_id)
            ORDER BY b.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/ciclos", summary="Crear o actualizar regla")
async def upsert_rule(
    rule: BillingRuleSchema,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    conn = db.get_conn()
    try:
        ts = db.now_utc_iso()
        # Verificar si ya existe para el cliente
        exist = conn.execute(
            "SELECT id FROM billing_rules WHERE customer_id = %s", (rule.customer_id,)
        ).fetchone()

        if exist:
            conn.execute(
                """
                UPDATE billing_rules SET
                    description = %s, currency = %s, uf_rule = %s, uf_custom_value = %s,
                    base_amount = %s, frequency_months = %s, day_of_month = %s,
                    is_active = %s, auto_issue = %s, updated_at = %s
                WHERE customer_id = %s
            """,
                (
                    rule.description,
                    rule.currency,
                    rule.uf_rule,
                    float(rule.uf_custom_value),
                    float(rule.base_amount),
                    rule.frequency_months,
                    rule.day_of_month,
                    1 if rule.is_active else 0,
                    1 if rule.auto_issue else 0,
                    ts,
                    rule.customer_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO billing_rules (
                    customer_id, description, currency, uf_rule, uf_custom_value,
                    base_amount, frequency_months, day_of_month, is_active, auto_issue,
                    created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    rule.customer_id,
                    rule.description,
                    rule.currency,
                    rule.uf_rule,
                    float(rule.uf_custom_value),
                    float(rule.base_amount),
                    rule.frequency_months,
                    rule.day_of_month,
                    1 if rule.is_active else 0,
                    1 if rule.auto_issue else 0,
                    ts,
                    ts,
                ),
            )

        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.post("/ciclos/preview", summary="Previsualizar cálculo de factura")
async def preview_billing(rule: BillingRuleSchema):
    uf_val = indicators_service.get_uf_value() or 37000.0  # Fallback

    factor = 1.0
    if rule.currency == "UF":
        if rule.uf_rule == "VALOR_DIA":
            factor = uf_val
        elif rule.uf_rule in ["VALOR_FIJO", "VALOR_CONTRATO"]:
            factor = rule.uf_custom_value
        # Manual o otros...

    total_neto = rule.base_amount * factor
    total_iva = total_neto * 0.19
    total_final = total_neto + total_iva

    return {
        "customer_id": rule.customer_id,
        "base_amount": rule.base_amount,
        "currency": rule.currency,
        "uf_used": factor if rule.currency == "UF" else None,
        "total_neto": round(total_neto),
        "total_final": round(total_final),
        "glosa": rule.description,
    }


@router.get("/laudus/doctypes", summary="Listar docTypes (Laudus)")
async def list_laudus_doctypes(sess: dict = Depends(deps.require_permission("invoice:read"))):
    client = LaudusClient()
    return client.list_doc_types()


class EmitSiiIn(BaseModel):
    doc_type_id: int
    contact_external_id: Optional[str] = None
    purchase_order_number: str = ""
    notes: str = ""


@router.post("/invoices/{invoice_id}/emitir_sii", summary="Emitir factura local en Laudus (SII)")
async def emitir_sii(
    invoice_id: int,
    body: EmitSiiIn,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    # customer_id se toma desde la factura local
    inv = facturacion_service.issue_invoice_via_laudus(
        invoice_id=invoice_id,
        customer_id="",  # placeholder; will override below
        doc_type_id=int(body.doc_type_id),
        contact_external_id=body.contact_external_id,
        purchase_order_number=body.purchase_order_number,
        notes=body.notes,
        user_id=sess.get("username", ""),
    )
    return {"ok": True, "invoice": inv}


# -----------------------------
# Servicios facturables (catálogo de facturación)
# -----------------------------


class ServiceUpsertIn(BaseModel):
    sku: str
    name: str
    price: float = 0.0


@router.get("/servicios", summary="Listar servicios facturables (productos is_service)")
async def list_services(
    q: Optional[str] = "",
    limit: int = 200,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        sql = "SELECT sku, name, category, price, price_currency, price_parity, is_service, external_id FROM products WHERE is_service IS TRUE"
        params = []
        qs = (q or "").strip()
        if qs:
            if db.is_postgres():
                sql += " AND (sku ILIKE ? OR name ILIKE ?)"
            else:
                sql += " AND (LOWER(sku) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?))"
            params.extend([f"%{qs}%", f"%{qs}%"])

        sql += " ORDER BY name ASC LIMIT ?"
        params.append(int(limit))

        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/servicios", summary="Crear/actualizar servicio facturable")
async def upsert_service(
    body: ServiceUpsertIn,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    sku = (body.sku or "").strip()
    name = (body.name or "").strip()
    if not sku:
        raise HTTPException(status_code=400, detail="sku requerido")
    if not name:
        raise HTTPException(status_code=400, detail="name requerido")

    prod = bodega_service.create_or_update_product(
        sku=sku,
        name=name,
        key_props={"price": float(body.price or 0), "is_service": True},
    )
    return {"ok": True, "product": prod}


@router.post("/servicios/sync_laudus", summary="Sincronizar servicios desde Laudus (catálogo)")
async def sync_services_laudus(
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    # Validación rápida: si faltan credenciales, no tiene sentido encolar
    health = LaudusClient().get_health()
    if health.get("status") != "ok":
        raise HTTPException(status_code=503, detail=f"Laudus no disponible: {health.get('msg')}")

    await jobs_engine.enqueue_job(
        "SYNC_SERVICES_LAUDUS",
        payload={"manual_trigger_by": sess.get("username", "")},
        max_retries=1,
    )
    return {"ok": True, "status": "enqueued"}


@router.get("/invoices/{invoice_id}/events", summary="Bitácora de eventos de la factura")
async def invoice_events(
    invoice_id: int,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM invoice_events WHERE invoice_id = ? ORDER BY id DESC LIMIT 200",
            (invoice_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/invoices/{invoice_id}/dispatches", summary="Historial de envíos de la factura")
async def invoice_dispatches(
    invoice_id: int,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM invoice_dispatches WHERE invoice_id = ? ORDER BY id DESC LIMIT 50",
            (invoice_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# -----------------------------
# Billing Profiles (multi factura por cliente)
# -----------------------------


class RecipientIn(BaseModel):
    contact_id: int
    role: str = "TO"  # TO | CC


class BillingProfileIn(BaseModel):
    id: Optional[int] = None
    customer_id: str
    name: str
    template_id: Optional[int] = None
    currency: str = "CLP"
    uf_rule: str = "VALOR_DIA"
    uf_custom_value: float = 0.0
    frequency_months: int = 1
    day_of_month: int = 5
    auto_issue: bool = False
    doc_type_id: Optional[int] = None
    term_id: Optional[int] = None
    purchase_order_required: bool = False
    purchase_order_number: str = ""
    notes: str = ""
    is_active: bool = True
    recipients: List[RecipientIn] = []


@router.get("/perfiles", summary="Listar perfiles de facturación")
async def list_profiles(
    customer_id: Optional[str] = None,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM billing_profiles WHERE 1=1"
        params = []
        if customer_id:
            sql += " AND customer_id = ?"
            params.append(customer_id)
        sql += " ORDER BY id DESC LIMIT 200"
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/perfiles", summary="Crear/actualizar perfil de facturación")
async def upsert_profile(
    body: BillingProfileIn,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    currency = (body.currency or "CLP").upper().strip()
    if currency not in ("CLP", "UF"):
        raise HTTPException(status_code=400, detail="currency debe ser CLP o UF")

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        if body.id:
            conn.execute(
                """
                UPDATE billing_profiles SET
                    customer_id = ?,
                    name = ?,
                    template_id = ?,
                    currency = ?,
                    uf_rule = ?,
                    uf_custom_value = ?,
                    frequency_months = ?,
                    day_of_month = ?,
                    auto_issue = ?,
                    doc_type_id = ?,
                    term_id = ?,
                    purchase_order_required = ?,
                    purchase_order_number = ?,
                    notes = ?,
                    is_active = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    body.customer_id,
                    body.name,
                    body.template_id,
                    currency,
                    body.uf_rule,
                    float(body.uf_custom_value or 0),
                    int(body.frequency_months or 1),
                    int(body.day_of_month or 5),
                    1 if body.auto_issue else 0,
                    body.doc_type_id,
                    body.term_id,
                    1 if body.purchase_order_required else 0,
                    body.purchase_order_number,
                    body.notes,
                    1 if body.is_active else 0,
                    now,
                    int(body.id),
                ),
            )
            profile_id = int(body.id)
            conn.execute("DELETE FROM billing_profile_recipients WHERE profile_id = ?", (profile_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO billing_profiles
                (customer_id, name, template_id, currency, uf_rule, uf_custom_value,
                 frequency_months, day_of_month, auto_issue, doc_type_id, term_id,
                 purchase_order_required, purchase_order_number, notes, is_active,
                 created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    body.customer_id,
                    body.name,
                    body.template_id,
                    currency,
                    body.uf_rule,
                    float(body.uf_custom_value or 0),
                    int(body.frequency_months or 1),
                    int(body.day_of_month or 5),
                    1 if body.auto_issue else 0,
                    body.doc_type_id,
                    body.term_id,
                    1 if body.purchase_order_required else 0,
                    body.purchase_order_number,
                    body.notes,
                    1 if body.is_active else 0,
                    sess.get("username", ""),
                    now,
                    now,
                ),
            )
            row = cur.fetchone()
            profile_id = int(row["id"] if isinstance(row, dict) else row[0])

        for r in body.recipients or []:
            role = (r.role or "TO").upper().strip()
            if role not in ("TO", "CC"):
                role = "TO"
            conn.execute(
                """
                INSERT INTO billing_profile_recipients (profile_id, contact_id, role, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (profile_id, int(r.contact_id), role, now),
            )

        conn.commit()
        return {"ok": True, "id": profile_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


# -----------------------------
# Contacts (routing por depto/proyecto)
# -----------------------------


@router.get("/clientes/{customer_id}/contactos", summary="Listar contactos de facturación del cliente")
async def list_contacts(
    customer_id: str,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM customer_contacts
            WHERE customer_id = ? AND is_active = 1
            ORDER BY department ASC, project ASC, last_name ASC, first_name ASC
            """,
            (customer_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/clientes/{customer_id}/contactos/sync", summary="Sincronizar contactos desde Laudus")
async def sync_contacts(
    customer_id: str,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    client = LaudusClient()
    contacts = client.list_customer_contacts(customer_id)

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        upserts = 0
        for c in contacts or []:
            ext_id = str(c.get("contactId") or "").strip() or None
            first = (c.get("firstName") or "").strip()
            last = (c.get("lastName") or "").strip()
            email = (c.get("email") or "").strip()

            conn.execute(
                """
                INSERT INTO customer_contacts
                (customer_id, external_contact_id, first_name, last_name, email, raw_json, synced_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id, external_contact_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    email = excluded.email,
                    raw_json = excluded.raw_json,
                    synced_at = excluded.synced_at,
                    updated_at = excluded.updated_at
                """,
                (
                    customer_id,
                    ext_id,
                    first,
                    last,
                    email,
                    json.dumps(c)[:8000],
                    now,
                    now,
                    now,
                ),
            )
            upserts += 1

        conn.commit()
        return {"ok": True, "count": upserts}
    finally:
        conn.close()


# -----------------------------
# Manual/Auto: generar + emitir (SII via Laudus)
# -----------------------------


@router.post("/perfiles/{profile_id}/generar", summary="Generar factura desde perfil (y opcionalmente emitir)")
async def generate_from_profile(
    profile_id: int,
    issue: bool = False,
    send: bool = False,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    conn = db.get_conn()
    try:
        prof = conn.execute(
            "SELECT * FROM billing_profiles WHERE id = ? AND is_active = 1",
            (profile_id,),
        ).fetchone()
        if not prof:
            raise HTTPException(status_code=404, detail="Perfil no encontrado")
        prof = dict(prof)
    finally:
        conn.close()

    if not prof.get("template_id"):
        raise HTTPException(status_code=400, detail="Perfil sin template_id")

    inv = facturacion_service.create_invoice_from_template(
        customer_id=prof["customer_id"],
        template_id=int(prof["template_id"]),
        issuer_id=sess.get("username", ""),
        profile_id=profile_id,
        currency_override=prof.get("currency"),
        uf_rule=prof.get("uf_rule") or "VALOR_DIA",
        uf_custom_value=float(prof.get("uf_custom_value") or 0),
    )

    if issue:
        if not prof.get("doc_type_id"):
            raise HTTPException(status_code=400, detail="Perfil sin doc_type_id (Laudus)")
        inv = facturacion_service.issue_invoice_via_laudus(
            invoice_id=int(inv["id"]),
            customer_id=str(prof["customer_id"]),
            doc_type_id=int(prof["doc_type_id"]),
            purchase_order_number=prof.get("purchase_order_number") or "",
            notes=prof.get("notes") or "",
            user_id=sess.get("username", ""),
        )

    if send:
        conn = db.get_conn()
        try:
            recs = conn.execute(
                """
                SELECT c.email, r.role
                FROM billing_profile_recipients r
                JOIN customer_contacts c ON c.id = r.contact_id
                WHERE r.profile_id = ?
                """,
                (profile_id,),
            ).fetchall()
            to_emails = [r["email"] for r in recs if (r.get("role") or "").upper() == "TO" and r.get("email")]
            cc_emails = [r["email"] for r in recs if (r.get("role") or "").upper() == "CC" and r.get("email")]
        finally:
            conn.close()

        subj = f"Factura {inv.get('external_id') or ('#' + str(inv.get('id')))}"
        body = f"<p>Adjuntamos factura.</p><p>Cliente: {prof.get('customer_id')}</p>"
        disp = facturacion_service.dispatch_invoice_email(
            invoice_id=int(inv["id"]),
            profile_id=profile_id,
            to_emails=to_emails,
            cc_emails=cc_emails,
            subject=subj,
            html_body=body,
            attach_pdf_from_laudus=True,
        )
        return {"ok": True, "invoice": inv, "dispatch": disp}

    return {"ok": True, "invoice": inv}
