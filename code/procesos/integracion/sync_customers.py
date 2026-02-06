#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

import db

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def extract_list(data: Any) -> List[Dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ("items", "results", "data", "rows"):
            v = data.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []

def main() -> int:
    load_dotenv(dotenv_path=".env", override=False)

    base_url = (os.getenv("LAUDUS_BASE_URL") or "https://api.laudus.cl").rstrip("/")
    username = (os.getenv("LAUDUS_USERNAME") or "").strip()
    password = (os.getenv("LAUDUS_PASSWORD") or "").strip()
    vat_id = (os.getenv("LAUDUS_COMPANY_VAT_ID") or "").strip()

    if not username or not password or not vat_id:
        print("ERROR: missing env vars in .env (LAUDUS_USERNAME/LAUDUS_PASSWORD/LAUDUS_COMPANY_VAT_ID)")
        return 2

    s = requests.Session()
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    # Login
    login_url = f"{base_url}/security/login"
    payload = {"userName": username, "password": password, "companyVATId": vat_id}
    r = s.post(login_url, data=json.dumps(payload), timeout=30)
    if r.status_code != 200:
        print(f"LOGIN_FAIL status={r.status_code} body={(r.text or '')[:300]}")
        return 1

    token = r.json().get("token", "")
    if not token:
        print("LOGIN_FAIL no_token")
        return 1
    s.headers["Authorization"] = f"Bearer {token}"

    # Init DB
    db.init_db()

    # Fetch customers (page 0..N) up to hard cap to be safe
    total_upserts = 0
    total_received = 0
    offset = 0
    limit = 200
    hard_cap = 2000  # adjust later

    while total_received < hard_cap:
        list_url = f"{base_url}/sales/customers/list"
        body = {
            "options": {"offset": offset, "limit": limit},
            "fields": ["customerId", "name", "legalName", "VATId"],
            "filterBy": [],
             "orderBy": [{"field": "name", "direction": "ASC"}],
        }
        r2 = s.post(list_url, data=json.dumps(body), timeout=60)
        if r2.status_code != 200:
            print(f"CUSTOMERS_FAIL status={r2.status_code} body={(r2.text or '')[:300]}")
            return 1

        rows = extract_list(r2.json())
        got = len(rows)
        total_received += got

        if got == 0:
            break

        ts = now_utc_iso()
        for it in rows:
            cid = str(it.get("customerId", "")).strip()
            if not cid:
                continue
            name = str(it.get("name", "") or "")
            legal = str(it.get("legalName", "") or "")
            vat = str(it.get("VATId", "") or "")
            raw = json.dumps(it, ensure_ascii=True, sort_keys=True)
            db.upsert_customer(cid, name, legal, vat, raw, ts)
            total_upserts += 1

        offset += limit

    print(f"SYNC_OK upserts={total_upserts} received={total_received}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
