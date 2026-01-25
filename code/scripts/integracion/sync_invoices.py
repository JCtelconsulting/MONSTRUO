#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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

def pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None

def to_float(x: Any) -> float:
    if x is None or x == "":
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(".", "").replace(",", ".")  # rough fix if thousands sep
    try:
        return float(s)
    except Exception:
        return 0.0

def to_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return x != 0
    s = str(x).strip().lower()
    return s in ("true", "1", "yes", "y", "si", "sí")

def parse_iso_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    try:
        # API docs say ISO8601 without tz; assume local but we treat as naive
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None

def call_list(session: requests.Session, base_url: str, path: str, body: Dict[str, Any]) -> Tuple[int, Any, str]:
    url = f"{base_url}{path}"
    r = session.post(url, data=json.dumps(body), timeout=60)
    txt = (r.text or "")[:400]
    try:
        return r.status_code, r.json(), txt
    except Exception:
        return r.status_code, None, txt

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
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    # Login
    login_url = f"{base_url}/security/login"
    payload = {"userName": username, "password": password, "companyVATId": vat_id}
    r = s.post(login_url, data=json.dumps(payload), timeout=30)
    if r.status_code != 200:
        print(f"LOGIN_FAIL status={r.status_code} body={(r.text or '')[:300]}")
        return 1

    token = (r.json() or {}).get("token", "")
    if not token:
        print("LOGIN_FAIL no_token")
        return 1

    s.headers["Authorization"] = f"Bearer {token}"

    db.init_db()

    # Candidate endpoints (in case tenant differs)
    endpoints = [
        "/sales/invoices/list",
        "/sales/salesInvoices/list",
        "/sales/customerInvoices/list",
    ]

    total_upserts = 0
    total_received = 0
    offset = 0
    limit = 200
    hard_cap = 5000

    chosen_endpoint: Optional[str] = None

    while total_received < hard_cap:
        body_with_fields = {
            "options": {"offset": offset, "limit": limit},
            "fields": [
                "salesInvoiceId", "issuedDate", "dueDate", "total",
                "customerId" # "isPaid" removed
            ],
            "filterBy": [],
            "orderBy": [{"field": "issuedDate", "direction": "DESC"}],
        }

        body_without_fields = {
            "options": {"offset": offset, "limit": limit},
            "filterBy": [],
            "orderBy": [{"field": "issuedDate", "direction": "DESC"}],
        }

        last_err = ""
        data = None

        # pick endpoint once
        if chosen_endpoint is None:
            for ep in endpoints:
                st, js, txt = call_list(s, base_url, ep, body_with_fields)
                if st in (200, 204):
                    chosen_endpoint = ep
                    data = js if st == 200 else {}
                    break
                # retry without fields if 400
                if st in (400, 422):
                    st2, js2, txt2 = call_list(s, base_url, ep, body_without_fields)
                    if st2 in (200, 204):
                        chosen_endpoint = ep
                        data = js2 if st2 == 200 else {}
                        break
                    last_err = f"{ep} status={st2} body={txt2}"
                else:
                    last_err = f"{ep} status={st} body={txt}"
                print(f"Tried {ep}: status={st} body={(txt or '')[:100]}")
            if chosen_endpoint is None:
                print("INVOICES_FAIL no_working_endpoint")
                print(last_err[:350])
                return 1
        else:
            st, js, txt = call_list(s, base_url, chosen_endpoint, body_with_fields)
            if st not in (200, 204):
                if st in (400, 422):
                    st2, js2, txt2 = call_list(s, base_url, chosen_endpoint, body_without_fields)
                    if st2 not in (200, 204):
                        print(f"INVOICES_FAIL status={st2} body={txt2}")
                        return 1
                    data = js2 if st2 == 200 else {}
                else:
                    print(f"INVOICES_FAIL status={st} body={txt}")
                    return 1
            else:
                data = js if st == 200 else {}

        rows = extract_list(data)
        got = len(rows)
        total_received += got
        if got == 0:
            break

        ts = now_utc_iso()

        for it in rows:
            # Field mapping (best-effort)
            iid = pick_first(it, ["invoiceId", "salesInvoiceId", "docId", "documentId", "id"])
            cid = pick_first(it, ["customerId", "relatedToId", "clientId"])
            doc_date = pick_first(it, ["date", "issuedDate", "docDate"])
            due_date = pick_first(it, ["dueDate", "expirationDate", "paymentDueDate"])
            total = to_float(pick_first(it, ["total", "totalAmount", "amount"]))
            # balance = pick_first(it, ["balance", "pendingAmount", "remaining"]) # FIELD MISSING IN LAUDUS?
            is_paid = to_bool(pick_first(it, ["isPaid", "paid"]))
            
            # Approx balance logic if field missing
            balance = 0.0 if is_paid else total

            iid_s = str(iid).strip() if iid is not None else ""
            if not iid_s:
                continue

            db.upsert_invoice(
                laudus_invoice_id=iid_s,
                customer_id=str(cid).strip() if cid is not None else "",
                doc_date=str(doc_date or ""),
                due_date=str(due_date or ""),
                total_amount=total,
                balance=balance,
                is_paid=is_paid,
                raw_json=json.dumps(it, ensure_ascii=True, sort_keys=True),
                synced_at=ts
            )
            total_upserts += 1

        offset += limit

    print(f"SYNC_INVOICES_OK endpoint={chosen_endpoint} upserts={total_upserts} received={total_received}")

    # ---- Aging report (by customer) ----
    conn = db.get_conn()
    try:
        inv = conn.execute("""
            SELECT i.customer_id, i.due_date, i.balance, c.name
            FROM laudus_invoices i
            LEFT JOIN laudus_customers c ON c.laudus_customer_id = i.customer_id
            WHERE i.balance > 0
        """).fetchall()
    finally:
        conn.close()

    today = datetime.now().date()
    buckets = {
        "not_due_or_no_due_date": 0.0,
        "1_30": 0.0,
        "31_60": 0.0,
        "61_90": 0.0,
        "91_plus": 0.0,
    }
    by_customer: Dict[str, float] = {}

    for row in inv:
        name = (row["name"] or row["customer_id"] or "UNKNOWN")
        bal = float(row["balance"] or 0.0)
        due = parse_iso_date(row["due_date"] or "")
        if not due:
            buckets["not_due_or_no_due_date"] += bal
            by_customer[name] = by_customer.get(name, 0.0) + bal
            continue

        days = (today - due.date()).days
        if days <= 0:
            buckets["not_due_or_no_due_date"] += bal
        elif days <= 30:
            buckets["1_30"] += bal
        elif days <= 60:
            buckets["31_60"] += bal
        elif days <= 90:
            buckets["61_90"] += bal
        else:
            buckets["91_plus"] += bal

        by_customer[name] = by_customer.get(name, 0.0) + bal

    top = sorted(by_customer.items(), key=lambda x: x[1], reverse=True)[:8]

    print("\n--- AGING RESUMEN (saldo > 0) ---")
    print(f"Total invoices with balance>0: {len(inv)}")
    print("Buckets (sum balance):")
    for k in ["not_due_or_no_due_date", "1_30", "31_60", "61_90", "91_plus"]:
        print(f"  {k}: {buckets[k]:.2f}")

    print("\nTop clientes por deuda:")
    for name, debt in top:
        print(f"  {name}: {debt:.2f}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
