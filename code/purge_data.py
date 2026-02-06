from app.core import db

conn = db.get_conn()
try:
    print("Purging all invoices to ensure clean state...")
    conn.execute("DELETE FROM invoices")
    conn.commit()
    print("✅ Invoices table truncated.")
finally:
    conn.close()
