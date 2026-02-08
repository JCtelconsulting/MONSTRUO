from app.core import db

conn = db.get_conn()
try:
    print("Checking laudus_customers...")
    row = conn.execute("SELECT count(*) as n FROM laudus_customers").fetchone()
    if row:
        cnt = dict(row)["n"] if hasattr(row, "keys") else row[0]
        print(f"Count: {cnt}")
    else:
        print("Count: 0")

    print("\nSample:")
    res = conn.execute("SELECT laudus_customer_id, name FROM laudus_customers LIMIT 3").fetchall()
    for r in res:
        print(dict(r) if hasattr(r, "keys") else r)

finally:
    conn.close()
