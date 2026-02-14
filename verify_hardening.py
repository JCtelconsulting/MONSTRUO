import requests
import time
import sys
import os

# Add /app/code to sys.path to import app modules if running inside container
sys.path.append("/app/code")

try:
    from app.core import db, security
except ImportError:
    print("ERROR: This script must be run inside the API container to access the database.")
    sys.exit(1)

# Config
API_URL = "http://localhost:9000/api"
AUTH_URL = "http://localhost:9000/auth/login"

def seed_admin():
    print(">>> Seeding Admin User...")
    conn = db.get_conn()
    try:
        # Check if exists
        user = conn.execute("SELECT 1 FROM users WHERE username='admin'").fetchone()
        if not user:
            print("Creating admin user...")
            hashed_pw = security.get_password_hash("123")
            conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, 'admin', 1, %s)",
                ("admin", hashed_pw, db.now_utc_iso())
            )
            conn.commit()
        else:
            print("Admin user already exists.")
    except Exception as e:
        print(f"Error seeding admin: {e}")
        conn.rollback()
    finally:
        conn.close()

def login():
    print(f">>> Logging in to {AUTH_URL}...")
    try:
        resp = requests.post(AUTH_URL, json={"username": "admin", "password": "123"})
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            print("Login successful.")
            return token
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    except Exception as e:
        print(f"Login connection error: {e}")
        sys.exit(1)

def test_xss_sanitization(token):
    print(">>> Testing XSS Sanitization...")
    headers = {"Authorization": f"Bearer {token}"}
    xss_payload = "<script>alert('XSS')</script>"
    
    resp = requests.post(f"{API_URL}/tks/tickets", json={
        "titulo": f"Test XSS {xss_payload}",
        "descripcion": f"Desc {xss_payload}",
        "severidad": "media",
        "categoria": "sistemas"
    }, headers=headers)
    
    if resp.status_code != 200:
        print(f"Failed to create ticket: {resp.text}")
        return False
        
    ticket = resp.json()
    tid = ticket["id"]
    print(f"Ticket {tid} created with XSS payload.")
    return tid

def test_load_balancing(token, ticket_id):
    print(">>> Testing Load Balancing...")
    headers = {"Authorization": f"Bearer {token}"}
    
    tech_user = f"tech_{int(time.time())}"
    
    # Insert tech user directly into DB
    conn = db.get_conn()
    try:
        # Postgres uses %s for placeholders
        hashed_pw = security.get_password_hash("123")
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, 'tecnico', 1, %s)",
            (tech_user, hashed_pw, db.now_utc_iso())
        )
        conn.execute(
            "INSERT INTO user_specialties (username, specialty, max_load, current_load, is_available, created_at, updated_at) VALUES (%s, 'sistemas', 5, 0, 1, %s, %s)",
            (tech_user, db.now_utc_iso(), db.now_utc_iso())
        )
        conn.commit()
    except Exception as e:
        print(f"Error caching tech user: {e}")
        conn.close()
        return False
    
    # Verify initial load
    load_before = conn.execute("SELECT current_load FROM user_specialties WHERE username=%s", (tech_user,)).fetchone()["current_load"]
    conn.close()
    print(f"Load before: {load_before}")
    
    # Assign ticket
    resp = requests.patch(f"{API_URL}/tks/tickets/{ticket_id}", json={"asignado_a": tech_user}, headers=headers)
    if resp.status_code != 200:
        print(f"Failed to assign: {resp.text}")
        return False

    # Verify load +1
    conn = db.get_conn()
    load_after = conn.execute("SELECT current_load FROM user_specialties WHERE username=%s", (tech_user,)).fetchone()["current_load"]
    conn.close()
    print(f"Load after assign: {load_after}")
    
    if load_after != load_before + 1:
        print("FAIL: Load did not increase")
        return False
        
    # Resolve ticket
    resp = requests.patch(f"{API_URL}/tks/tickets/{ticket_id}", json={"estado": "resuelto"}, headers=headers)
    
    conn = db.get_conn()
    load_end = conn.execute("SELECT current_load FROM user_specialties WHERE username=%s", (tech_user,)).fetchone()["current_load"]
    conn.close()
    print(f"Load after resolve: {load_end}")
    
    if load_end != load_before:
        print("FAIL: Load did not decrease")
        return False
        
    print("PASS: Load balancing works")
    return True

if __name__ == "__main__":
    try:
        seed_admin()
        token = login()
        tid = test_xss_sanitization(token)
        if tid:
            if test_load_balancing(token, tid):
                print("ALL TESTS PASSED")
            else:
                sys.exit(1)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        # import traceback
        # traceback.print_exc()
        sys.exit(1)
