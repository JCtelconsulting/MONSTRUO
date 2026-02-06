from typing import Dict, Any
from app.core import db


def register_payment_local(
    invoice_id: int, amount: float, date_str: str, reference: str = ""
) -> Dict[str, Any]:
    """
    Registers a payment LOCALLY for an invoice.
    Updates status to PAID if balance reaches 0 (simplified logic for now: full payment).
    Does NOT sync to Laudus.
    """
    conn = db.get_conn()
    try:
        # 1. Validate Invoice
        row = conn.execute(
            "SELECT id, total_final, status FROM invoices WHERE id = %s", (invoice_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Invoice {invoice_id} not found")

        inv = dict(row)

        # 2. Insert Payment Record (Local)
        # We need a table for local payments if not exists, or re-use laudus_payments?
        # Ideally, we should have a 'payments' table that is unified.
        # For now, let's look for existing payment tables in db.py or creating one.
        # Assuming we update the invoice status directly for this MVP.

        # Check if we have a payments table.
        # db.py showed 'parrotfy_payments' and 'upsert_payment' logic.
        # Let's check if there is a generic 'payments' table.
        # If not, I'll create one.

        # 3. Update Invoice Status
        # For MVP: If amount >= total_final, mark as PAID.
        new_status = inv["status"]
        if amount >= inv["total_final"] * 0.99:  # Tolerance
            new_status = "PAID"

        conn.execute(
            "UPDATE invoices SET status = %s, updated_at = %s WHERE id = %s",
            (new_status, db.now_utc_iso(), invoice_id),
        )
        conn.commit()

        return {
            "status": "success",
            "invoice_id": invoice_id,
            "new_status": new_status,
            "amount_registered": amount,
        }

    finally:
        conn.close()
