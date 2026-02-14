import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import db

conn = db.get_conn()
try:
    print("Creating system_settings table...")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        group_name TEXT DEFAULT 'general',
        is_sensitive INTEGER DEFAULT 0,
        updated_at TEXT
    );
    """)
    conn.commit()
    print("Table created.")
finally:
    conn.close()
