import sys
import os
from pathlib import Path

# Script location: /srv/monstruo_dev/code/scripts/fix_pmo_db.py
# We need to add /srv/monstruo_dev/code to path to import 'app'
# This is parent directory of 'scripts'
CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(CODE_DIR))

from app.core import db

def migrate():
    print(f"Added {CODE_DIR} to path.")
    print("Connecting to DB...")
    conn = db.get_conn()
    try:
        print("Executing ALTER TABLE on PostgreSQL...")
        # Postgres syntax
        conn.execute("ALTER TABLE pmo_proyectos ADD COLUMN IF NOT EXISTS estado VARCHAR(50) DEFAULT 'borrador'")
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
