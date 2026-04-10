from app.core import db

try:
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, external_id, customer_id, total_final, created_at FROM invoices ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    print("--- INVOICE DATA START ---")
    for r in rows:
        print(dict(r))
    print("--- INVOICE DATA END ---")
except Exception as e:
    print(f"Error: {e}")
finally:
    if "conn" in locals():
        conn.close()
