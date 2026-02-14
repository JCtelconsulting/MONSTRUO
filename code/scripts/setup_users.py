
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core import db, auth_service

def setup_users():
    print("--- Seeding Users ---")
    
    users_to_create = [
        # (username, password, role)
        ("fabian.correa@telconsulting.cl", "Telco2024!", "redes"),
        ("lukas.moyano@telconsulting.cl", "Telco2024!", "sistemas"),
        ("juan.hormazabal@telconsulting.cl", "Telco2024!", "implementaciones"),
        ("juan.lopez@telconsulting.cl", "Monstruo2024!", "admin"),
    ]

    conn = db.get_conn()
    try:
        for username, password, role in users_to_create:
            print(f"Processing {username} ({role})...")
            exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
            
            if exists:
                print(f" -> User {username} already exists. Updating role and password...")
                from app.core import security
                hashed = security.get_password_hash(password)
                conn.execute("UPDATE users SET role=?, password_hash=? WHERE username=?", (role, hashed, username))
                conn.commit()
            else:
                print(f" -> Creating user {username}...")
                try:
                    auth_service.create_user(username, password, role)
                    print(" -> OK")
                except Exception as e:
                    print(f" -> ERROR: {e}")
                    
    finally:
        conn.close()
    print("--- Done ---")

if __name__ == "__main__":
    setup_users()
