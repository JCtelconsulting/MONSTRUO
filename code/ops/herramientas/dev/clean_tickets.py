import sys
import os

# Ensure we are in dev
if os.getenv("ENV_TYPE") != "dev" and os.getenv("STACK_NAME") != "monstruo-dev":
    print("ERROR: This script must only be run in DEV environment.")
    print("Current ENV_TYPE:", os.getenv("ENV_TYPE"))
    sys.exit(1)

sys.path.append("/srv/monstruo_dev/code")
from app.core import db

def clean_tickets():
    if "--force" not in sys.argv:
        print("WARNING: This will delete ALL tickets, comments, and attachments in DEV.")
        confirm = input("Type 'DELETE' to confirm: ")
        if confirm != "DELETE":
            print("Aborted.")
            return

    conn = db.get_conn()
    try:
        tables = ["tickets", "ticket_comments", "ticket_attachments"]
        for t in tables:
            print(f"Truncating {t}...")
            # Use DELETE for SQLite compatibility if needed, but TRUNCATE is better for Postgres
            # Check if Postgres
            try:
                conn.execute(f"TRUNCATE TABLE {t} CASCADE")
            except Exception as e:
                print(f"TRUNCATE failed ({e}), trying DELETE...")
                conn.execute(f"DELETE FROM {t}")
        
        conn.commit()
        print("SUCCESS: Tickets cleared.")
    except Exception as e:
        print(f"ERROR: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    clean_tickets()
