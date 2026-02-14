import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import db, auth_service

import os

def setup_users():
    print("--- Seeding Users ---")
    
    # Obtener contraseñas de variables de entorno (FAIL-FAST)
    pass_redes = os.getenv("SEED_PASS_REDES")
    pass_sistemas = os.getenv("SEED_PASS_SISTEMAS")
    pass_implementaciones = os.getenv("SEED_PASS_IMPLEMENTACIONES")
    pass_admin = os.getenv("SEED_PASS_ADMIN")
    
    if not all([pass_redes, pass_sistemas, pass_implementaciones, pass_admin]):
        print("ERROR: Faltan variables de entorno para contraseñas (SEED_PASS_*).")
        sys.exit(1)

    users_to_create = [
        # (username, password, role)
        ("fabian.correa@telconsulting.cl", pass_redes, "redes"),
        ("lukas.moyano@telconsulting.cl", pass_sistemas, "sistemas"),
        ("juan.hormazabal@telconsulting.cl", pass_implementaciones, "implementaciones"),
        ("juan.lopez@telconsulting.cl", pass_admin, "admin"),
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
