
import sys
import os
import argparse
from pathlib import Path

# Adjust path to import nucleo
# script location: /srv/monstruo_dev/code/procesos/mantenimiento/upsert_user.py
# nucleo location: /srv/monstruo_dev/code/app/nucleo.py
# relative: ../../

current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parents[1]))

from app import nucleo

def upsert_user(username, password, role="admin"):
    print(f"Upserting user '{username}' with role '{role}'...")
    
    # Generate hash
    p_hash = nucleo.make_password_hash(password)
    
    conn = nucleo.get_conn()
    try:
        # Check if user exists
        cursor = conn.execute("SELECT 1 FROM users WHERE username=?", (username,))
        if not cursor.fetchone():
            print(f"User '{username}' does not exist. Creating it...")
            # create_user handles hashing internally usually, but let's see nucleo.py
            # nucleo.create_user hashes it. Let's use nucleo.create_user if possible, 
            # or manual insert if we want to be sure about upsert logic.
            # nucleo.create_user raises error if exists.
            try:
                nucleo.create_user(username, password, role)
                print("User created successfully via nucleo.create_user.")
            except Exception as e:
                print(f"Error creating user: {e}")
        else:
            print(f"User '{username}' exists. Updating password...")
            conn.execute("UPDATE users SET password_hash=?, role=?, is_active=1 WHERE username=?", (p_hash, role, username))
            conn.commit()
            print(f"User updated successfully.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--role", default="admin")
    args = parser.parse_args()
    
    upsert_user(args.username, args.password, args.role)
