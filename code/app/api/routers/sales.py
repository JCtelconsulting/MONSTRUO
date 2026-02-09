from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timedelta
import io
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.core import sales_service, deps, db
from app.integraciones.laudus import LaudusClient
from app.core.audit_decorator import audit_action

router = APIRouter(prefix="/api/sales", tags=["sales"])


@router.get("/kpis", summary="Get ERP Financial KPIs")
async def get_kpis(sess: dict = Depends(deps.require_permission("dashboard:read"))):
    conn = db.get_conn()
    try:
        today = datetime.now()
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

        # 1. Facturado (Last 30 Days)
        row_sales = conn.execute(
            """
            SELECT SUM(total_final) as total 
            FROM invoices 
            WHERE status IN ('ISSUED', 'PAID') 
            AND issued_at >= ?
        """,
            (start_date,),
        ).fetchone()

        sales_month = 0
        if row_sales:
            val = row_sales["total"] if isinstance(row_sales, dict) else row_sales[0]
            sales_month = float(val or 0)
        if sales_month <= 0:
            row_sales_laudus = conn.execute(
                """
                SELECT SUM(total_amount) as total
                FROM laudus_invoices
                WHERE doc_date >= ?
            """,
                (start_date,),
            ).fetchone()
            if row_sales_laudus:
                val = (
                    row_sales_laudus["total"]
                    if isinstance(row_sales_laudus, dict)
                    else row_sales_laudus[0]
                )
                sales_month = float(val or 0)

        # 2. Deuda Vencida (Issued > 30 days ago and not PAID)
        # This remains the same logic (overdue)
        # But maybe we verify cutoff?
        cutoff_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        row_debt = conn.execute(
            """
            SELECT SUM(total_final) as total 
            FROM invoices 
            WHERE status='ISSUED' 
            AND issued_at < ?
        """,
            (cutoff_date,),
        ).fetchone()

        debt_overdue = 0
        if row_debt:
            val = row_debt["total"] if isinstance(row_debt, dict) else row_debt[0]
            debt_overdue = float(val or 0)
        if debt_overdue <= 0:
            row_debt_laudus = conn.execute(
                """
                SELECT SUM(
                    CASE 
                        WHEN balance > 0 THEN balance 
                        ELSE total_amount 
                    END
                ) as total
                FROM laudus_invoices
                WHERE is_paid = 0
                  AND COALESCE(NULLIF(due_date, ''), doc_date) < ?
            """,
                (cutoff_date,),
            ).fetchone()
            if row_debt_laudus:
                val = (
                    row_debt_laudus["total"]
                    if isinstance(row_debt_laudus, dict)
                    else row_debt_laudus[0]
                )
                debt_overdue = float(val or 0)

        # 3. Cobrado (Last 30 Days)
        # Assuming payment_date is ISO or YYYY-MM-DD
        row_paid = conn.execute(
            """
            SELECT SUM(amount) as total
            FROM laudus_payments
            WHERE payment_date >= ?
        """,
            (start_date,),
        ).fetchone()

        collected_month = 0
        if row_paid:
            val = row_paid["total"] if isinstance(row_paid, dict) else row_paid[0]
            collected_month = float(val or 0)
        if collected_month <= 0:
            row_paid_laudus = conn.execute(
                """
                SELECT SUM(
                    CASE 
                        WHEN total_amount > balance THEN (total_amount - balance)
                        ELSE 0
                    END
                ) as total
                FROM laudus_invoices
                WHERE doc_date >= ?
            """,
                (start_date,),
            ).fetchone()
            if row_paid_laudus:
                val = (
                    row_paid_laudus["total"]
                    if isinstance(row_paid_laudus, dict)
                    else row_paid_laudus[0]
                )
                collected_month = float(val or 0)

        return {
            "sales_month": sales_month,
            "debt_overdue": debt_overdue,
            "collected_month": collected_month,
        }
    finally:
        conn.close()


# Schemas
class InvoiceItemSchema(BaseModel):
    sku: str
    quantity: float
    unit_price: float


class InvoiceCreate(BaseModel):
    customer_id: str
    type: str = "FACTURA"
    items: List[InvoiceItemSchema]
    ref_id: Optional[int] = None


class VoidRequest(BaseModel):
    reason: str = "Voiding"


@router.get("/invoices", response_model=List[dict])
async def list_invoices(
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    limit: int = 100,
    sess: dict = Depends(deps.require_permission("invoice:read")),
):
    """List all local invoices."""
    return sales_service.list_invoices(status, customer_id, limit)


@router.post("/invoices", response_model=dict)
@audit_action("CREATE_INVOICE_DRAFT", severity="info")
async def create_draft(
    body: InvoiceCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    """Create a DRAFT invoice."""
    # Convert items to dict
    items_dict = [i.dict() for i in body.items]
    return sales_service.create_invoice_draft(
        body.customer_id, body.type, sess["username"], items_dict, body.ref_id
    )


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str, sess: dict = Depends(deps.require_permission("sales.read"))
):
    """Get single invoice details (head + items)."""
    inv = sales_service.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


@router.post("/invoices/{invoice_id}/issue", response_model=dict)
@audit_action("ISSUE_INVOICE", severity="info")
async def issue_invoice(
    invoice_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    sess: dict = Depends(deps.require_permission("invoice:write")),
):
    """Issue invoice (Deduct Stock)."""
    try:
        return sales_service.issue_invoice(invoice_id, sess["username"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/invoices/{invoice_id}/void", response_model=dict)
@audit_action("VOID_INVOICE", severity="warn")
async def void_invoice(
    invoice_id: int,
    body: VoidRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    sess: dict = Depends(deps.require_permission("invoice:void")),
):
    """Void invoice (Generate NC + Return Stock)."""
    try:
        return sales_service.void_invoice(invoice_id, sess["username"], body.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/laudus/invoices/{remote_id}/pdf")
async def get_invoice_pdf(
    remote_id: str, sess: dict = Depends(deps.require_permission("sales.read"))
):
    """
    Proxy to get PDF from Laudus.
    Auto-resolves local IDs to remote Laudus IDs if needed.
    """
    final_id = remote_id
    laudus_client = LaudusClient()  # Initialize client here

    # Heuristic: Resolve if ID is alphanumeric (like E00000697) or small local ID
    needs_resolution = not remote_id.isdigit() or int(remote_id) < 100000

    if needs_resolution:
        print(f"DEBUG PDF: Resolving ID {remote_id}...")
        try:
            conn = db.get_conn()
            try:
                local_inv = None

                # A) If it's a digit, look up by local ID first
                if remote_id.isdigit():
                    cur = conn.execute(
                        "SELECT external_id, customer_id, total_final, created_at FROM invoices WHERE id = %s",
                        (remote_id,),
                    )
                    local_inv = cur.fetchone()

                # B) If not found or alphanumeric, look up by external_id
                if not local_inv:
                    cur = conn.execute(
                        "SELECT external_id, customer_id, total_final, created_at FROM invoices WHERE external_id = %s",
                        (remote_id,),
                    )
                    local_inv = cur.fetchone()

                # 1. Check if we found a local record
                if local_inv:
                    print(f"DEBUG PDF: Found local record: {local_inv}")

                    # If the record itself has a valid numeric external_id that IS NOT the one we started with
                    if (
                        local_inv["external_id"]
                        and str(local_inv["external_id"]).isdigit()
                        and str(local_inv["external_id"]) != str(remote_id)
                    ):
                        final_id = local_inv["external_id"]
                        print(f"DEBUG PDF: Resolved to numeric external_id {final_id}")
                    else:
                        # 2. Fuzzy match in laudus_invoices
                        print(f"DEBUG PDF: No direct numeric ID, fuzzy matching...")
                        cust_id = local_inv["customer_id"]
                        total = local_inv["total_final"]
                        date_ts = local_inv["created_at"]

                        query = """
                            SELECT laudus_invoice_id 
                            FROM laudus_invoices 
                            WHERE TRIM(customer_id) = TRIM(%s)
                            AND ABS(total_amount - %s) < 1.0
                            AND doc_date::date >= (%s::date - INTERVAL '1 day')
                            AND doc_date::date <= (%s::date + INTERVAL '1 day')
                            LIMIT 1
                        """
                        cur = conn.execute(query, (cust_id, total, date_ts, date_ts))
                        match = cur.fetchone()
                        if match:
                            final_id = match["laudus_invoice_id"]
                            print(f"DEBUG PDF: Fuzzy match found remote ID {final_id}")
                        else:
                            print("DEBUG PDF: Fuzzy match failed.")
                else:
                    print("DEBUG PDF: ID not found in local invoices.")

            finally:
                conn.close()
        except Exception as e:
            print(f"DEBUG PDF: Resolution error: {e}")

    # Fallback to original behavior (try using the ID as-is if resolution failed)
    print(f"DEBUG PDF: Requesting Laudus PDF for ID: {final_id}")

    try:
        # Pass ID as is (string or int), do not force int() as some IDs are alphanumeric (e.g. E00000697)
        pdf_bytes = laudus_client.get_invoice_pdf(final_id)
        if not pdf_bytes:
            raise HTTPException(
                status_code=404, detail="Laudus PDF not found (empty bytes)"
            )

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=invoice_{final_id}.pdf"},
        )
    except Exception as e:
        print(f"Laudus PDF Error {final_id}: {e}")
        raise HTTPException(status_code=404, detail="Laudus PDF not found or error")


@router.get("/laudus/invoices/{remote_id}/payments")
async def get_laudus_payments(
    remote_id: str, sess: dict = Depends(deps.require_permission("invoice:read"))
):
    """Proxy to get Payments from Laudus."""
    client = LaudusClient()
    return client.get_invoice_payments(remote_id)
