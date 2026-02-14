
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core import db

def debug():
    print("--- Debugging User Modules ---")
    conn = db.get_conn()
    try:
        # Search for users matching fabian
        cursor = conn.execute("SELECT username, role, allowed_modules FROM users WHERE username LIKE %s", ('%fabian%',))
        rows = cursor.fetchall()
        for row in rows:
            print(f"User: {row['username']}")
            print(f"Role: {row['role']}")
            print(f"Allowed Modules (Raw): {row['allowed_modules']}")
            print("-" * 20)
            
    except Exception as e:
        print(f" -> ERROR: {e}")
    finally:
        conn.close()
    print("--- Done ---")

if __name__ == "__main__":
    debug()
