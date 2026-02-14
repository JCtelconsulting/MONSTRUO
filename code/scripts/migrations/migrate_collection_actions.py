import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import db

conn = db.get_conn()
try:
    print("Creating collection_actions table...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS collection_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id TEXT NOT NULL, -- Link to invoices.customer_id (Laudus ID)
        action_type TEXT NOT NULL, -- CALL, EMAIL, WHATSAPP, NOTE
        notes TEXT DEFAULT '',
        committed_amount REAL DEFAULT 0,
        commitment_date TEXT, -- ISO Date
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_coll_actions_cust ON collection_actions(customer_id);")
    conn.commit()
    print("✅ Table created.")
finally:
    conn.close()
