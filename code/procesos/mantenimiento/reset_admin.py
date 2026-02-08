
import sys
import os
from pathlib import Path

# Adjust path to import nucleo
# script location: /srv/monstruo/code/procesos/mantenimiento/reset_admin.py
# nucleo location: /srv/monstruo/code/app/nucleo.py
# relative: ../../

current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parents[1]))

from app import nucleo

def reset_admin_password():
    username = "admin"
    new_pass = "monstruo" # Default secure-ish password for dev
    
    print(f"Resetting password for user '{username}'...")
    
    # Generate hash
    p_hash = nucleo.make_password_hash(new_pass)
    
    conn = nucleo.get_conn()
    try:
        # Check if user exists
        cursor = conn.execute("SELECT 1 FROM users WHERE username=?", (username,))
        if not cursor.fetchone():
            print(f"User '{username}' does not exist. Creating it...")
            nucleo.create_user(username, new_pass, "admin")
        else:
            conn.execute("UPDATE users SET password_hash=? WHERE username=?", (p_hash, username))
            conn.commit()
            print(f"Password updated successfully.")
            
        print(f"Credentials:\nUser: {username}\nPass: {new_pass}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_admin_password()
