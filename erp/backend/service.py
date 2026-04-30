import json
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from plataforma.core import db
from erp.backend import sales_service
from plataforma.core import email as email_service
from erp.backend.laudus import LaudusClient
from erp.backend import indicators_service


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_template(template_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    conn = db.get_conn()
    try:
        tpl = conn.execute(
            "SELECT * FROM invoice_templates WHERE id = ? AND is_active = 1",
            (template_id,),
        ).fetchone()
        if not tpl:
            raise ValueError("Plantilla no encontrada o inactiva")

        items = conn.execute(
            """
            SELECT *
            FROM invoice_template_items
            WHERE template_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (template_id,),
        ).fetchall()

        # Compat: algunas BD antiguas usan columna `sku` en vez de `product_sku`.
        out_items: List[Dict[str, Any]] = []
        for r in items:
            d = dict(r)
            if "product_sku" not in d and "sku" in d:
                d["product_sku"] = d.get("sku")
            out_items.append(d)

        return dict(tpl), out_items
    finally:
        conn.close()


def _compute_uf_factor(uf_rule: str, uf_custom_value: float, issue_date: date) -> float:
    uf_rule = (uf_rule or "VALOR_DIA").upper().strip()
    if uf_rule == "VALOR_DIA":
        val = indicators_service.get_uf_value()
        if not val:
            raise ValueError("No se pudo obtener UF del día")
        return float(val)

    if uf_rule in ("VALOR_FIJO", "VALOR_CONTRATO"):
        if not uf_custom_value or float(uf_custom_value) <= 0:
            raise ValueError("UF custom inválida para regla fija/contrato")
        return float(uf_custom_value)

    if uf_rule in ("VALOR_FECHA_EMISION", "VALOR_FECHA"):
        val = indicators_service.get_uf_value_for_date(issue_date)
        if not val:
            raise ValueError(f"No se pudo obtener UF para {issue_date.isoformat()}")
        return float(val)

    raise ValueError(f"Regla UF no soportada: {uf_rule}")


def create_invoice_from_template(
    *,
    customer_id: str,
    template_id: int,
    issuer_id: str,
    profile_id: Optional[int] = None,
    currency_override: Optional[str] = None,
    uf_rule: str = "VALOR_DIA",
    uf_custom_value: float = 0.0,
    issue_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Crea una factura LOCAL en estado DRAFT desde una plantilla.
    Si la plantilla está en UF, convierte a CLP según uf_rule.
    """
    tpl, items = _load_template(template_id)

    issue_date = issue_date or date.today()
    currency = (currency_override or tpl.get("currency") or "CLP").upper().strip()
    if currency not in ("CLP", "UF"):
        raise ValueError("Moneda no soportada")

    uf_factor = 1.0
    if currency == "UF":
        uf_factor = _compute_uf_factor(uf_rule, uf_custom_value, issue_date)

    payload_items = []
    for it in items:
        sku = (it.get("product_sku") or "").strip()
        if not sku:
            raise ValueError("Item sin SKU en plantilla")
        qty = float(it.get("quantity") or 0)
        if qty <= 0:
            raise ValueError(f"Cantidad inválida para SKU {sku}")
        unit_price = float(it.get("unit_price") or 0)
        unit_price_clp = unit_price if currency == "CLP" else unit_price * uf_factor
        payload_items.append(
            {
                "sku": sku,
                "quantity": qty,
                "unit_price": float(unit_price_clp),
            }
        )

    inv = sales_service.create_invoice_draft(
        customer_id=customer_id,
        invoice_type="FACTURA",
        issuer_id=issuer_id,
        items=payload_items,
        ref_id=None,
    )

    # Event: created from template
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """
            INSERT INTO invoice_events (invoice_id, event_type, payload_json, created_by, created_at)
            VALUES (?, 'DRAFT_FROM_TEMPLATE', ?, ?, ?)
            """,
            (
                inv["id"],
                json.dumps(
                    {
                        "template_id": template_id,
                        "profile_id": profile_id,
                        "currency": currency,
                        "uf_rule": uf_rule,
                        "uf_custom_value": uf_custom_value,
                        "uf_factor": uf_factor if currency == "UF" else None,
                        "issue_date": issue_date.isoformat(),
                    }
                ),
                issuer_id,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return inv


def issue_invoice_via_laudus(
    *,
    invoice_id: int,
    customer_id: Optional[str] = None,
    doc_type_id: int,
    contact_external_id: Optional[str] = None,
    purchase_order_number: str = "",
    notes: str = "",
    user_id: str,
) -> Dict[str, Any]:
    """
    Emite (crea) la factura en Laudus y actualiza el registro LOCAL:
    - set external_id
    - transiciona a ISSUED (sin romper por stock de servicios)
    """
    inv = sales_service.get_invoice(invoice_id)
    if not inv:
        raise ValueError("Factura local no encontrada")
    if inv.get("status") != "DRAFT":
        raise ValueError("Solo se puede emitir desde DRAFT")
    if not inv.get("items"):
        raise ValueError("Factura sin items")

    customer_id = (customer_id or inv.get("customer_id") or "").strip()
    if not customer_id:
        raise ValueError("customer_id requerido")

    items_payload = []
    for it in inv["items"]:
        sku = (it.get("product_sku") or "").strip()
        if not sku:
            continue
        items_payload.append(
            {
                "product": {"sku": sku},
                "quantity": float(it.get("quantity") or 0),
                "unitPrice": float(it.get("unit_price") or 0),
            }
        )

    payload: Dict[str, Any] = {
        "docType": {"docTypeId": int(doc_type_id)},
        "customer": {"customerId": int(customer_id)},
        "issuedDate": datetime.now(timezone.utc).date().isoformat(),
        "purchaseOrderNumber": (purchase_order_number or "").strip() or None,
        "notes": (notes or "").strip() or None,
        "items": items_payload,
    }
    if contact_external_id:
        try:
            payload["contact"] = {"contactId": int(contact_external_id)}
        except Exception:
            # Keep as-is if non-numeric
            payload["contact"] = {"contactId": contact_external_id}

    # Remove null-like keys (Laudus sometimes is strict)
    payload = {k: v for k, v in payload.items() if v is not None}

    client = LaudusClient()
    res = client.create_sales_invoice(payload)
    if res.get("error"):
        raise ValueError(f"Laudus: {res.get('detail') or 'error'}")

    external_id = (
        res.get("salesInvoiceId")
        or res.get("id")
        or res.get("sales_invoice_id")
        or res.get("SalesInvoiceId")
    )
    if not external_id:
        # Some APIs return full dto
        external_id = res.get("external_id") or res.get("docNumber")
    if not external_id:
        raise ValueError("No se pudo obtener ID de factura en Laudus")

    # Update local invoice and mark issued
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            "UPDATE invoices SET external_id = ?, updated_at = ? WHERE id = ?",
            (str(external_id), now, invoice_id),
        )
        conn.execute(
            """
            INSERT INTO invoice_events (invoice_id, event_type, payload_json, created_by, created_at)
            VALUES (?, 'LAUDUS_CREATED', ?, ?, ?)
            """,
            (invoice_id, json.dumps({"external_id": str(external_id)}), user_id, now),
        )
        conn.commit()
    finally:
        conn.close()

    # Transition to ISSUED locally (skips stock for service items)
    issued = sales_service.issue_invoice(invoice_id, user_id=user_id)
    return {**issued, "laudus_external_id": str(external_id)}


def dispatch_invoice_email(
    *,
    invoice_id: int,
    profile_id: Optional[int],
    to_emails: List[str],
    cc_emails: Optional[List[str]] = None,
    subject: str,
    html_body: str,
    attach_pdf_from_laudus: bool = True,
) -> Dict[str, Any]:
    """
    Envía email (SMTP) y registra estado en invoice_dispatches.
    Si attach_pdf_from_laudus=True, intenta adjuntar PDF desde Laudus usando external_id.
    """
    cc_emails = cc_emails or []
    to_emails = [e for e in to_emails if e]
    cc_emails = [e for e in cc_emails if e]
    if not to_emails:
        raise ValueError("No hay destinatarios TO")

    inv = sales_service.get_invoice(invoice_id)
    if not inv:
        raise ValueError("Factura no encontrada")

    attachments = []
    if attach_pdf_from_laudus:
        external_id = (inv.get("external_id") or "").strip()
        if external_id:
            try:
                pdf = LaudusClient().get_invoice_pdf(external_id)
                if pdf:
                    attachments.append(
                        {
                            "filename": f"factura_{external_id}.pdf",
                            "content_type": "application/pdf",
                            "data": pdf,
                        }
                    )
            except Exception:
                pass

    conn = db.get_conn()
    dispatch_id = None
    try:
        now = db.now_utc_iso()
        cur = conn.execute(
            """
            INSERT INTO invoice_dispatches
            (invoice_id, profile_id, channel, status, to_emails, cc_emails, subject, attempts, last_error, created_at, updated_at)
            VALUES (?, ?, 'email', 'PENDING', ?, ?, ?, 0, '', ?, ?)
            RETURNING id
            """,
            (
                invoice_id,
                profile_id,
                ",".join(to_emails),
                ",".join(cc_emails),
                subject,
                now,
                now,
            ),
        )
        row = cur.fetchone()
        if row:
            dispatch_id = row["id"] if isinstance(row, dict) else row[0]
        conn.commit()
    finally:
        conn.close()

    try:
        email_service.send_email_with_attachments(
            to_emails=to_emails,
            cc_emails=cc_emails,
            subject=subject,
            html_body=html_body,
            attachments=attachments,
        )
        ok = True
        err = ""
    except Exception as e:
        ok = False
        err = str(e)

    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        if dispatch_id:
            conn.execute(
                """
                UPDATE invoice_dispatches
                SET status = ?, attempts = attempts + 1, last_error = ?, updated_at = ?, sent_at = CASE WHEN ? THEN ? ELSE sent_at END
                WHERE id = ?
                """,
                (
                    "SENT" if ok else "FAILED",
                    err[:2000],
                    now,
                    1 if ok else 0,
                    now,
                    dispatch_id,
                ),
            )
        conn.execute(
            """
            INSERT INTO invoice_events (invoice_id, event_type, payload_json, created_by, created_at)
            VALUES (?, ?, ?, '', ?)
            """,
            (
                invoice_id,
                "EMAIL_SENT" if ok else "EMAIL_FAILED",
                json.dumps(
                    {
                        "to": to_emails,
                        "cc": cc_emails,
                        "subject": subject,
                        "dispatch_id": dispatch_id,
                        "error": err if not ok else None,
                    }
                ),
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"ok": ok, "dispatch_id": dispatch_id, "error": err}
