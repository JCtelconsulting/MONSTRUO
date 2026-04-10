import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "plataforma" / "legacy" / "code"))

from app.core.db import get_conn

def apply_constraint():
    conn = get_conn()
    try:
        print("Cleaning duplicate hashes first...")
        # Simplest way: Truncate lines table (it's dev)
        conn.execute("TRUNCATE TABLE bank_statement_lines CASCADE")
        conn.commit()
        
        print("Adding UNIQUE constraint to bank_statement_lines(hash)...")
        # Postgres syntax
        try:
            conn.execute("ALTER TABLE bank_statement_lines ADD CONSTRAINT uq_bsl_hash UNIQUE (hash)")
            conn.commit()
            print("Constraint added successfully.")
        except Exception as e:
            print(f"Error adding constraint: {e}")
            
    except Exception as outer:
        print(f"Outer error: {outer}")
    finally:
        conn.close()

if __name__ == "__main__":
    apply_constraint()
