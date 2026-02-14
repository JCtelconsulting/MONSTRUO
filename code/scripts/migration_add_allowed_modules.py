
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core import db

def migrate():
    print("--- Migrating Users Table (Add allowed_modules) ---")
    conn = db.get_conn()
    try:
        # Attempt to add column directly with IF NOT EXISTS (Postgres 9.6+)
        # This avoids the transaction aborted state from a failed SELECT
        print(" -> Attempting ADD COLUMN IF NOT EXISTS...")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_modules TEXT DEFAULT '[]'")
        conn.commit()
        print(" -> Success (or column already existed).")
            
    except Exception as e:
        print(f" -> ERROR: {e}")
        conn.rollback() # Ensure rollback on error
    finally:
        conn.close()
    print("--- Done ---")

if __name__ == "__main__":
    migrate()
