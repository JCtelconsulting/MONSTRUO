#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from parrotfy_client import ParrotfyClient, pick_first, to_float

DB_PATH = "monstruo.db"

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

from db import get_conn, init_db

def init_parrotfy_tables() -> None:
    # Deprecated: usage moved to db.init_db()
    init_db()

def choose_total(row: Dict[str, Any]) -> float:
    # Prefer real invoice amount first. pending_amount is usually outstanding, keep as fallback.
    v = pick_first(row, ["real_amount", "total_amount", "amount", "grand_total", "total"])
    if v is None:
        v = pick_first(row, ["pending_amount"])
    return float(to_float(v))

def upsert_invoice(row: Dict[str, Any], ts: str) -> None:
    pid = pick_first(row, ["id", "sale_invoice_id", "saleInvoiceId", "invoiceId"])
    pid_s = str(pid).strip() if pid is not None else ""
    if not pid_s:
        return

    inv_no = pick_first(row, ["number", "folio", "invoice_number", "document_number"]) or ""
    issued = pick_first(row, ["issued_date", "issue_date", "date", "created_at"]) or ""
    cust = pick_first(row, ["customer_id", "client_id", "customer_vat", "vat_id", "rut"]) or ""
    total = choose_total(row)
    status = pick_first(row, ["status", "state"]) or ""

    raw = json.dumps(row, ensure_ascii=True, sort_keys=True)

    conn = get_conn()
    try:
        conn.execute("""
        INSERT INTO parrotfy_invoices (parrotfy_invoice_id, invoice_number, issued_date, customer_id, total_amount, status, raw_json, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(parrotfy_invoice_id) DO UPDATE SET
          invoice_number=excluded.invoice_number,
          issued_date=excluded.issued_date,
          customer_id=excluded.customer_id,
          total_amount=excluded.total_amount,
          status=excluded.status,
          raw_json=excluded.raw_json,
          synced_at=excluded.synced_at;
        """, (pid_s, str(inv_no), str(issued), str(cust), float(total), str(status), raw, ts))
        conn.commit()
    finally:
        conn.close()

def main() -> int:
    init_parrotfy_tables()
    c = ParrotfyClient()
    ts = now_utc_iso()

    path = "/api/v1/sale_invoices"
    rows = c.list_all(path, page_size=200, hard_cap=20000)

    up = 0
    for r in rows:
        upsert_invoice(r, ts)
        up += 1

    conn = get_conn()
    try:
        n = conn.execute("SELECT count(*) AS n FROM parrotfy_invoices").fetchone()["n"]
        nz = conn.execute("SELECT count(*) AS n FROM parrotfy_invoices WHERE total_amount > 0").fetchone()["n"]
    finally:
        conn.close()

    print(f"SYNC_PARROTFY_INVOICES_OK upserts={up} received={len(rows)} db_count={n} nonzero_total={nz}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
