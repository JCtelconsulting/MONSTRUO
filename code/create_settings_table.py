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
