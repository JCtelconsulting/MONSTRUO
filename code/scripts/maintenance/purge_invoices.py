import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import db

conn = db.get_conn()
try:
    print("Purging all invoices to ensure clean state...")
    conn.execute("DELETE FROM invoices")
    conn.commit()
    print("✅ Invoices table truncated.")
finally:
    conn.close()
