#!/usr/bin/env python3
import requests
import sqlite3
import json
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
BASE_URL = os.getenv("VERIFY_BASE_URL", "http://127.0.0.1:9000")
DB_PATH = os.getenv("VERIFY_DB_PATH", str(PROJECT_ROOT / "data/db/monstruo.db"))

def get_db_conn():
    return sqlite3.connect(DB_PATH)

def login():
    url = f"{BASE_URL}/auth/login"
    # Default credentials from setup
    data = {"username": "admin_test", "password": "test1234"}
    try:
        r = requests.post(url, json=data)
        if r.status_code != 200:
            print(f"Login failed: {r.status_code} {r.text}")
            return None
        return r.json()["access_token"]
    except Exception as e:
        print(f"Login error: {e}")
        return None

def get_test_item_id():
    conn = get_db_conn()
    cursor = conn.cursor()
    # Try to find an item that is not categorized first, or just any item
    cursor.execute("SELECT id, nombre FROM cat_items ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

def main():
    print("--- Verificando Endpoint AI Duplicate ---")
    
    # 1. Login
    token = login()
    if not token:
        print("FAIL: Could not login")
        sys.exit(1)
    print(f"Login OK. Token: {token[:10]}...")

    # 2. Get Item
    item_id, name = get_test_item_id()
    if not item_id:
        print("FAIL: No items in DB")
        sys.exit(1)
    print(f"Testing with Item ID: {item_id} ({name})")

    # 3. Call Suggested Duplicates
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/api/catalogo/sugerir_duplicados"
    data = {"item_id": item_id}
    
    print(f"POST {url} with {data}")
    try:
        r = requests.post(url, json=data, headers=headers)
        if r.status_code == 200:
            res = r.json()
            print("Response OK:")
            print(json.dumps(res, indent=2, ensure_ascii=False))
            # Basic validation
            if "analysis" in res and "duplicates" in res["analysis"]:
                print("SUCCESS: Analysis structure found.")
            else:
                print("WARNING: Unexpected structure.")
        else:
            print(f"FAIL: Status {r.status_code}")
            print(r.text)
    except Exception as e:
        print(f"FAIL: Exception {e}")

if __name__ == "__main__":
    main()
