import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

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
