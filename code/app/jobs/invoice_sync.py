"""
Invoice Sync Job.
Actualiza estado de facturas locales emitidas en Laudus:
- Marca PAID cuando los cobros (receipts) cubren el total.
"""

from datetime import datetime, timedelta
import json

from app.core import db
from app.integraciones.laudus import LaudusClient


async def sync_invoice_payments(payload: dict = None):
    client = LaudusClient()
    conn = db.get_conn()
    updated = 0
    checked = 0
    try:
        rows = conn.execute(
            """
            SELECT id, external_id, total_final
            FROM invoices
            WHERE status = 'ISSUED'
              AND external_id IS NOT NULL
              AND TRIM(external_id) != ''
            ORDER BY issued_at DESC NULLS LAST, id DESC
            LIMIT 50
            """
        ).fetchall()

        for r in rows:
            checked += 1
            inv_id = r["id"]
            ext_id = str(r["external_id"]).strip()
            total = float(r["total_final"] or 0)

            receipts = client.get_invoice_receipts(ext_id)
            paid = 0.0
            for rec in receipts or []:
                try:
                    paid += float(rec.get("amount") or 0)
                except Exception:
                    pass

            is_paid = total > 0 and paid >= (total - 1.0)
            if is_paid:
                now = db.now_utc_iso()
                conn.execute(
                    "UPDATE invoices SET status = 'PAID', updated_at = ? WHERE id = ?",
                    (now, inv_id),
                )
                conn.execute(
                    """
                    INSERT INTO invoice_events (invoice_id, event_type, payload_json, created_by, created_at)
                    VALUES (?, 'MARK_PAID', ?, 'laudus_sync', ?)
                    """,
                    (
                        inv_id,
                        json.dumps({"external_id": ext_id, "paid_amount": paid, "total": total}),
                        now,
                    ),
                )
                updated += 1

        conn.commit()
        print(f"[InvoiceSync] Checked {checked}, updated {updated}")
    finally:
        conn.close()

    # Re-encolar (cada 6 horas)
    if payload and payload.get("recurring"):
        next_run = (datetime.utcnow() + timedelta(hours=6)).isoformat()
        now_iso = db.now_utc_iso()
        conn2 = db.get_conn()
        try:
            exists = conn2.execute(
                "SELECT 1 FROM sys_jobs WHERE job_type='SYNC_INVOICE_PAYMENTS' AND status IN ('PENDING','RETRY')"
            ).fetchone()
            if not exists:
                conn2.execute(
                    """INSERT INTO sys_jobs
                       (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
                       VALUES ('SYNC_INVOICE_PAYMENTS', 'PENDING', '{"recurring": true}', ?, 0, 1, ?, ?)""",
                    (next_run, now_iso, now_iso),
                )
                conn2.commit()
                print(f"[InvoiceSync] Próximo sync programado para {next_run}")
            else:
                print("[InvoiceSync] Job recurrente ya pendiente, no se re-encola.")
        finally:
            conn2.close()

