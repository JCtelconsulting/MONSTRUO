import sys
import os

sys.path.append("/srv/monstruo/code")

# Mock environment if needed, or rely on .env loading within db
from app.core import db

conn = db.get_conn()
print("--- INVOICES (Local) ---")
try:
    cur = conn.execute(
        "SELECT id, customer_id, total_final, created_at, external_id FROM invoices WHERE id IN (64, 65)"
    )
    for row in cur.fetchall():
        print(dict(row))
except Exception as e:
    print(f"Error querying invoices: {e}")

print("\n--- LAUDUS INVOICES (Remote) ---")
try:
    cur = conn.execute(
        "SELECT laudus_invoice_id, customer_id, total_amount, doc_date FROM laudus_invoices ORDER BY doc_date DESC LIMIT 5"
    )
    for row in cur.fetchall():
        print(dict(row))
except Exception as e:
    print(f"Error querying laudus: {e}")

conn.close()
