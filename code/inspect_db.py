from app.core import db
import datetime

conn = db.get_conn()
try:
    print("--- TOTAL INVOICES ---")
    rows = conn.execute("SELECT count(*) as n FROM invoices").fetchall()
    print(rows)

    print("\n--- INVOICES BY STATUS ---")
    rows = conn.execute("SELECT status, count(*) as n FROM invoices GROUP BY status").fetchall()
    print(rows)

    print("\n--- SAMPLE ISSUED INVOICES ---")
    # Postgres specific casting if needed, but let's try generic first or just *
    rows = conn.execute("SELECT id, customer_id, total_final, status, issued_at FROM invoices WHERE status='ISSUED' LIMIT 5").fetchall()
    for r in rows:
        print(r)

finally:
    conn.close()
