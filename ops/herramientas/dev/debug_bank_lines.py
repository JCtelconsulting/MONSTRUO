from app.core import db

try:
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT document_number, description, amount FROM bank_statement_lines LIMIT 20"
    ).fetchall()
    print("--- DATA START ---")
    for r in rows:
        print(dict(r))
    print("--- DATA END ---")
except Exception as e:
    print(f"Error: {e}")
finally:
    if "conn" in locals():
        conn.close()
