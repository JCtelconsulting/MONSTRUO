from app.core import db

conn = db.get_conn()
try:
    print("Fixing invoices table constraint...")
    
    # 1. Check if constraint exists (naive attempt or just try/except)
    try:
        conn.execute("ALTER TABLE invoices ADD CONSTRAINT uq_invoices_external_id UNIQUE (external_id);")
        conn.commit()
        print("✅ Added UNIQUE constraint to external_id")
    except Exception as e:
        print(f"info: {e}")
        # If it failed, maybe it exists or duplicates exist.
        conn.rollback()

finally:
    conn.close()
