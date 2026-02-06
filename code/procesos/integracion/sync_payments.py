#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Set

import requests
from dotenv import load_dotenv

import db

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def main() -> int:
    load_dotenv(dotenv_path=".env", override=False)

    base_url = (os.getenv("LAUDUS_BASE_URL") or "https://api.laudus.cl").rstrip("/")
    username = (os.getenv("LAUDUS_USERNAME") or "").strip()
    password = (os.getenv("LAUDUS_PASSWORD") or "").strip()
    vat_id = (os.getenv("LAUDUS_COMPANY_VAT_ID") or "").strip()

    if not username or not password or not vat_id:
        print("ERROR: missing env vars in .env")
        return 2

    s = requests.Session()
    s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    # Login
    login_url = f"{base_url}/security/login"
    payload = {"userName": username, "password": password, "companyVATId": vat_id}
    try:
        r = s.post(login_url, data=json.dumps(payload), timeout=30)
    except Exception as e:
        print(f"LOGIN_ERR: {e}")
        return 1

    if r.status_code != 200:
        print(f"LOGIN_FAIL status={r.status_code}")
        return 1
    
    token = (r.json() or {}).get("token", "")
    if not token:
        print("LOGIN_FAIL no_token")
        return 1
    s.headers["Authorization"] = f"Bearer {token}"

    db.init_db()

    # 1. Fetch all Receipt IDs
    print("Fetching receipt IDs...")
    list_url = f"{base_url}/sales/receipts/list"
    receipt_ids: List[int] = []
    offset = 0
    limit = 500
    while True:
        body = {
            "options": {"offset": offset, "limit": limit},
            "fields": ["receiptId"],
            "orderBy": [{"field": "receiptId", "direction": "DESC"}],
        }
        r2 = s.post(list_url, json=body, timeout=60)
        if r2.status_code != 200:
             print(f"LIST_FAIL status={r2.status_code} body={r2.text[:200]}")
             break
        
        data = r2.json()
        # Handle list or dict/items
        rows = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("items") or data.get("data") or []
        
        if not rows:
            break
            
        for row in rows:
            rid = row.get("receiptId")
            if rid:
                receipt_ids.append(rid)
        
        if len(rows) < limit:
            break
        offset += limit

    print(f"Found {len(receipt_ids)} receipts. Syncing details...")

    # 2. Fetch Detail for each Receipt
    total_upserts = 0
    processed = 0
    
    # Use existing payments to avoid re-fetching if strictly immutable (optional optimization)
    # For now, simplistic approach: sync all specified by limit in listing (or all found).
    # We fetch detail for ALL found IDs.

    for rid in receipt_ids:
        detail_url = f"{base_url}/sales/receipts/{rid}"
        r3 = s.get(detail_url, timeout=30)
        if r3.status_code != 200:
            print(f"DETAIL_FAIL id={rid} status={r3.status_code}")
            continue
        
        receipt = r3.json()
        # Structure: 
        # receiptId, issuedDate, salesInvoices: [{salesInvoiceId, amount, customer:{...}}]
        
        r_date = receipt.get("issuedDate") or ""
        allocations = receipt.get("salesInvoices") or []
        
        # If allocations is empty, maybe it's unallocated or different structure?
        # Just loop whatever we find.
        
        ts = now_utc_iso()
        
        for alloc in allocations:
            inv_id = alloc.get("salesInvoiceId")
            if not inv_id:
                continue
            
            amt = alloc.get("amount") or 0.0
            
            # Customer ID might be inside customer object or top level
            cust = alloc.get("customer") or {}
            cust_id = cust.get("customerId") or ""
            if not cust_id:
                 # fallback to top level if available?
                 pass
            
            # Upsert into laudus_payments
            # We construct a unique ID for the payment allocation: receiptId_invoiceId
            # Or use receiptId as base if 1:1. But 1 receipt can pay N invoices.
            # Table laudus_payments expects 'laudus_payment_id'. 
            # We will use "R{rid}_{inv_id}" as a composite key for allocation.
            
            comp_id = f"R{rid}_{inv_id}"
            
            db.upsert_payment(
                laudus_payment_id=comp_id, 
                invoice_id=str(inv_id),
                customer_id=str(cust_id),
                payment_date=str(r_date),
                amount=float(amt),
                raw_json=json.dumps(alloc),
                synced_at=ts
            )
            total_upserts += 1
            
        processed += 1
        if processed % 10 == 0:
            print(f"Processed {processed}/{len(receipt_ids)} receipts...")
            
    print(f"Sync details done. Total payment allocations upserted: {total_upserts}")

    # 3. Recalculate Balances in SQLite
    print("Recalculating invoice balances...")
    conn = db.get_conn()
    try:
        # Get all invoices with their totals
        invoices = conn.execute("SELECT laudus_invoice_id, total_amount FROM laudus_invoices").fetchall()
        
        # Get sum of payments per invoice
        pay_sums = conn.execute("""
            SELECT invoice_id, SUM(amount) as paid
            FROM laudus_payments
            GROUP BY invoice_id
        """).fetchall()
    finally:
        conn.close()
        
    paid_map = {row["invoice_id"]: row["paid"] for row in pay_sums}
    
    updated_count = 0
    for inv in invoices:
        iid = inv["laudus_invoice_id"]
        total = inv["total_amount"] or 0.0
        paid = paid_map.get(iid, 0.0)
        
        # Balance cannot be negative (unless overpaid, but we floor at 0 for aging clarity)
        balance = total - paid
        if balance < 0: 
            balance = 0.0
            
        db.update_invoice_balance(iid, balance)
        updated_count += 1

    print(f"SYNC_PAYMENTS_OK upserts={total_upserts} receipts_processed={processed} balances_updated={updated_count}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
