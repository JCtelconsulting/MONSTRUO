from app.core import db

def migrate():
    print("Migrating system_settings table...")
    conn = db.get_conn()
    try:
        # Create table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY, 
                value TEXT
            )
        """)
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
