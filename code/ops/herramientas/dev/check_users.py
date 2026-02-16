import sys
sys.path.append("/srv/monstruo_dev/code")
from app.core import db

def list_users():
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT username, role, is_active FROM users LIMIT 10").fetchall()
        for r in rows:
            print(f"User: {r['username']}, Role: {r['role']}, Active: {r['is_active']}")
    except Exception as e:
        print(f"Error listing users: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    list_users()
