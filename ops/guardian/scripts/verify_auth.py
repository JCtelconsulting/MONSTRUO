#!/usr/bin/env python3
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CODE_DIR = PROJECT_ROOT / "code"
sys.path.insert(0, str(CODE_DIR))

try:
    from app.core import auth_service, security, db
except ImportError as e:
    print(f"FAIL: Import error - {e}")
    sys.exit(1)

def run_test():
    print("--- 1. Init DB ---")
    db.init_db()
    
    USERNAME = "verify_admin"
    PASSWORD = "verify_password"
    
    print(f"--- 2. Create User '{USERNAME}' ---")
    try:
        auth_service.create_user(USERNAME, PASSWORD, "admin")
        print("User created successfully.")
    except RuntimeError:
        print("User already exists (OK).")
    except Exception as e:
        print(f"FAIL: Could not create user - {e}")
        return False

    print("--- 3. Authenticate ---")
    user = auth_service.authenticate_user(USERNAME, PASSWORD)
    if not user:
        print("FAIL: Auth returned None (Bad password?)")
        return False
    print(f"Auth OK: {user['username']} role={user['role']}")

    print("--- 4. Issue JWT ---")
    token = security.create_access_token(user['username'], user['role'])
    print(f"Token: {token[:30]}...")

    print("--- 5. Verify JWT ---")
    payload = security.verify_token(token)
    if not payload:
        print("FAIL: Token verification returned None")
        return False
    
    if payload['sub'] != USERNAME or payload['role'] != 'admin':
        print(f"FAIL: Payload mismatch: {payload}")
        return False

    print("SUCCESS: Full cycle verified.")
    return True

if __name__ == "__main__":
    if run_test():
        sys.exit(0)
    else:
        sys.exit(1)
