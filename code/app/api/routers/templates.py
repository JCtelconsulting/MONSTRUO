from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.core import db, deps
from app.integraciones.laudus import LaudusClient


router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateItemIn(BaseModel):
    sku: str
    description: str = ""
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(default=0, ge=0)
    sort_order: int = 0


class TemplateUpsertIn(BaseModel):
    name: str
    customer_id: Optional[str] = None  # Laudus customerId or None for global
    currency: str = "CLP"  # CLP | UF
    items: List[TemplateItemIn]
    is_active: bool = True


class ImportLastLaudusIn(BaseModel):
    customer_id: str
    name: str = "Última factura Laudus"
    doc_type_id: int = 33
    take: int = 200


def _get_template(conn, template_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM invoice_templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        return None
    tpl = dict(row)
    items = conn.execute(
        """
        SELECT sku AS product_sku, description, quantity, unit_price, sort_order
        FROM invoice_template_items
        WHERE template_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (template_id,),
    ).fetchall()
    tpl["items"] = [dict(r) for r in items]
    return tpl


@router.get("/", summary="Listar plantillas")
async def list_templates(
    customer_id: Optional[str] = None,
    include_global: bool = True,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM invoice_templates WHERE is_active = 1"
        params = []
        if customer_id:
            if include_global:
                sql += " AND (customer_id = ? OR customer_id IS NULL)"
                params.append(customer_id)
            else:
                sql += " AND customer_id = ?"
                params.append(customer_id)
        else:
            if not include_global:
                sql += " AND customer_id IS NOT NULL"
        sql += " ORDER BY id DESC LIMIT 200"
        rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{template_id}", summary="Obtener plantilla con items")
async def get_template(
    template_id: int,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    conn = db.get_conn()
    try:
        tpl = _get_template(conn, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Plantilla no encontrada")
        return tpl
    finally:
        conn.close()


@router.post("/", summary="Crear/actualizar plantilla")
async def upsert_template(
    body: TemplateUpsertIn,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    if not body.items:
        raise HTTPException(status_code=400, detail="La plantilla debe tener items")

    currency = (body.currency or "CLP").upper().strip()
    if currency not in ("CLP", "UF"):
        raise HTTPException(status_code=400, detail="currency debe ser CLP o UF")

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        # Match existing by (name, customer_id) to allow simple upsert from UI
        row = conn.execute(
            """
            SELECT id FROM invoice_templates
            WHERE name = ? AND (
                (customer_id IS NULL AND ? IS NULL) OR customer_id = ?
            )
            ORDER BY id DESC
            LIMIT 1
            """,
            (body.name, body.customer_id, body.customer_id),
        ).fetchone()

        template_id = None
        if row:
            template_id = int(row["id"] if isinstance(row, dict) else row[0])
            conn.execute(
                """
                UPDATE invoice_templates
                SET currency = ?, is_active = ?, updated_at = ?
                WHERE id = ?
                """,
                (currency, 1 if body.is_active else 0, now, template_id),
            )
            conn.execute("DELETE FROM invoice_template_items WHERE template_id = ?", (template_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO invoice_templates
                (name, customer_id, currency, is_active, created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (
                    body.name,
                    body.customer_id,
                    currency,
                    1 if body.is_active else 0,
                    sess.get("username", ""),
                    now,
                    now,
                ),
            )
            res = cur.fetchone()
            template_id = int(res["id"] if isinstance(res, dict) else res[0])

        for it in body.items:
            conn.execute(
                """
                INSERT INTO invoice_template_items
                (template_id, sku, description, quantity, unit_price, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id,
                    it.sku.strip(),
                    (it.description or "").strip(),
                    float(it.quantity),
                    float(it.unit_price),
                    int(it.sort_order or 0),
                    now,
                ),
            )

        conn.commit()
        tpl = _get_template(conn, template_id)
        return {"ok": True, "template": tpl}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.post("/import_last_laudus", summary="Importar última factura de Laudus como plantilla")
async def import_last_laudus(
    body: ImportLastLaudusIn,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    customer_id = (body.customer_id or "").strip()
    if not customer_id or not customer_id.isdigit():
        raise HTTPException(status_code=400, detail="customer_id debe ser un Laudus customerId numérico")

    client = LaudusClient()
    if not client.login():
        raise HTTPException(status_code=503, detail="Laudus no disponible (credenciales o conexión)")

    rows = client.list_sales_invoices(
        skip=0,
        take=max(10, min(int(body.take or 200), 500)),
        fields=[
            "salesInvoiceId",
            "customerId",
            "docTypeId",
            "issuedDate",
            "docNumber",
        ],
    )

    cust_id_int = int(customer_id)
    doc_type_id = int(body.doc_type_id or 33)

    candidates = []
    for r in rows or []:
        try:
            if int(r.get("customerId") or -1) != cust_id_int:
                continue
            if int(r.get("docTypeId") or -1) != doc_type_id:
                continue
            issued = r.get("issuedDate") or ""
            issued_dt = None
            try:
                issued_dt = datetime.fromisoformat(str(issued).replace("Z", "+00:00"))
            except Exception:
                issued_dt = None
            candidates.append({**r, "_issued_dt": issued_dt})
        except Exception:
            continue

    if not candidates:
        raise HTTPException(status_code=404, detail="No se encontraron facturas recientes para ese cliente (docTypeId)")

    candidates.sort(key=lambda x: x.get("_issued_dt") or datetime.min, reverse=True)
    last = candidates[0]
    sales_invoice_id = str(last.get("salesInvoiceId") or "").strip()
    if not sales_invoice_id:
        raise HTTPException(status_code=502, detail="Laudus: respuesta inválida (sin salesInvoiceId)")

    inv = client.get_invoice_details(sales_invoice_id)
    items = inv.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=404, detail="La factura no tiene items para importar")

    # Determine currency: si la mayoría de líneas vienen con currencyCode UF, guardamos la plantilla en UF.
    codes = [(it.get("currencyCode") or "").upper().strip() for it in items]
    uf_votes = sum(1 for c in codes if c == "UF")
    currency = "UF" if uf_votes >= max(1, len(items) // 2) else "CLP"

    template_items: List[TemplateItemIn] = []
    sort_order = 0
    for it in items:
        prod = it.get("product") or {}
        sku = ""
        desc = ""
        if isinstance(prod, dict):
            sku = (prod.get("sku") or "").strip()
            desc = (prod.get("description") or "").strip()
        if not sku:
            # fallback: algunos items vienen sin product.sku; intentar itemDescription
            sku = (it.get("sku") or it.get("productSKU") or "").strip()
        if not sku:
            continue

        qty = float(it.get("quantity") or 0) or 1.0
        curr_code = (it.get("currencyCode") or "").upper().strip()
        if currency == "UF" and curr_code == "UF":
            unit_price = float(it.get("originalUnitPrice") or 0)
        else:
            unit_price = float(it.get("unitPrice") or 0)

        template_items.append(
            TemplateItemIn(
                sku=sku,
                description=desc or (it.get("itemDescription") or "").strip(),
                quantity=qty,
                unit_price=unit_price,
                sort_order=sort_order,
            )
        )
        sort_order += 1

    if not template_items:
        raise HTTPException(status_code=404, detail="No se pudieron extraer SKUs válidos desde la factura")

    # Create template (append invoice ID to reduce accidental overwrites)
    name = (body.name or "").strip() or "Última factura Laudus"
    name = f"{name} ({sales_invoice_id})"

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        existing = conn.execute(
            """
            SELECT id FROM invoice_templates
            WHERE name = ? AND customer_id = ? AND is_active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (name, customer_id),
        ).fetchone()

        template_id = None
        if existing:
            template_id = int(existing["id"] if isinstance(existing, dict) else existing[0])
            conn.execute(
                """
                UPDATE invoice_templates
                SET currency = ?, is_active = 1, updated_at = ?
                WHERE id = ?
                """,
                (currency, now, template_id),
            )
            conn.execute("DELETE FROM invoice_template_items WHERE template_id = ?", (template_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO invoice_templates
                (name, customer_id, currency, is_active, created_by, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                RETURNING id
                """,
                (name, customer_id, currency, sess.get("username", ""), now, now),
            )
            res = cur.fetchone()
            template_id = int(res["id"] if isinstance(res, dict) else res[0])

        for it in template_items:
            conn.execute(
                """
                INSERT INTO invoice_template_items
                (template_id, sku, description, quantity, unit_price, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    template_id,
                    it.sku.strip(),
                    (it.description or "").strip(),
                    float(it.quantity),
                    float(it.unit_price),
                    int(it.sort_order or 0),
                    now,
                ),
            )

        conn.commit()
        tpl = _get_template(conn, template_id)
        return {"ok": True, "template": tpl, "source_invoice_id": sales_invoice_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@router.delete("/{template_id}", summary="Desactivar plantilla")
async def deactivate_template(
    template_id: int,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        cur = conn.execute(
            "UPDATE invoice_templates SET is_active = 0, updated_at = ? WHERE id = ?",
            (now, template_id),
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
