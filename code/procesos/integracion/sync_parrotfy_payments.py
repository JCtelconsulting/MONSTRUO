#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from parrotfy_client import ParrotfyClient, pick_first, to_float, extract_list

DB_PATH = "monstruo.db"

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

from db import get_conn, init_db

def init_parrotfy_tables() -> None:
    init_db()

def upsert_payment(row: Dict[str, Any], ts: str) -> None:
    pid = pick_first(row, ["id", "payment_id", "sale_invoice_payment_id"])
    pid_s = str(pid).strip() if pid is not None else ""
    if not pid_s:
        return

    inv = pick_first(row, ["sale_invoice_id", "invoice_id", "saleInvoiceId", "invoiceId"]) or ""
    pdate = pick_first(row, ["payment_date", "date", "paid_at", "created_at"]) or ""
    amt = pick_first(row, ["amount", "paid_amount", "total", "value"]) or 0
    method = pick_first(row, ["method", "payment_method", "type"]) or ""

    raw = json.dumps(row, ensure_ascii=True, sort_keys=True)

    conn = get_conn()
    try:
        conn.execute("""
        INSERT INTO parrotfy_payments (parrotfy_payment_id, parrotfy_invoice_id, payment_date, amount, method, raw_json, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(parrotfy_payment_id) DO UPDATE SET
          parrotfy_invoice_id=excluded.parrotfy_invoice_id,
          payment_date=excluded.payment_date,
          amount=excluded.amount,
          method=excluded.method,
          raw_json=excluded.raw_json,
          synced_at=excluded.synced_at;
        """, (pid_s, str(inv), str(pdate), float(to_float(amt)), str(method), raw, ts))
        conn.commit()
    finally:
        conn.close()

def list_with_params(c: ParrotfyClient, path: str, params_base: Dict[str, Any], page_size: int = 200, hard_cap: int = 5000) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    page = 1
    while len(items) < hard_cap:
        params = dict(params_base)
        params.update({"page": page, "per_page": page_size})
        st, js, txt = c.get(path, params=params, timeout=45)
        if st == 500:
            raise RuntimeError(f"server_500 body={txt}")
        if st != 200:
            raise RuntimeError(f"status={st} body={txt}")
        rows = extract_list(js)
        if not rows:
            break
        items.extend(rows)
        if len(rows) < page_size:
            break
        page += 1
    return items[:hard_cap]

def create_integration_alert(source: str, kind: str, severity: str, title: str, details: Dict[str, Any]) -> None:
    """Create an alert for integration failures"""
    conn = get_conn()
    try:
        details_json = json.dumps(details, ensure_ascii=True, sort_keys=True)
        conn.execute("""
        INSERT INTO alerts (rule, severity, entity_type, entity_id, summary, details_json, status, first_seen_at, last_seen_at, occurrences)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, 1)
        ON CONFLICT(rule, entity_type, entity_id) DO UPDATE SET
          last_seen_at=excluded.last_seen_at,
          occurrences=occurrences + 1,
          details_json=excluded.details_json;
        """, (
            f"integration_{source}_{kind}",
            severity,
            "integration",
            source,
            title,
            details_json,
            now_utc_iso(),
            now_utc_iso()
        ))
        conn.commit()
    finally:
        conn.close()

def main() -> int:
    init_parrotfy_tables()
    c = ParrotfyClient()
    ts = now_utc_iso()

    path = "/api/v1/sale_invoice_payments"

    # Strategy A: try global list (may 500)
    rows: List[Dict[str, Any]] = []
    tried_global = True
    global_error = None
    
    try:
        rows = c.list_all(path, page_size=200, hard_cap=20000)
    except Exception as e:
        global_error = str(e)
        print(f"WARN: global_payments_failed reason={e}")
        
        # Check if it's a 500 error
        if "500" in global_error or "server_500" in global_error:
            print(f"ERROR: Parrotfy payments endpoint returning 500 - creating alert and skipping sync")
            create_integration_alert(
                source="parrotfy",
                kind="payments_api_500",
                severity="high",
                title="Parrotfy Payments API Error 500",
                details={
                    "endpoint": path,
                    "error": global_error,
                    "timestamp": ts,
                    "evidence_file": "/srv/inteligencia_artificial/documentacion/parrotfy_pagos_500_evidencia.txt",
                    "request_ids": [
                        "bc61b760-db5f-4f10-9c5c-a58f229ab2b6",
                        "9b122475-93b9-4342-a833-1a4410f76935",
                        "e90bc770-08a3-4ec2-8e88-4bb17bfb985c"
                    ],
                    "message": "Server-side error in Parrotfy API. All attempts (pagination, date range, no params) failed with 500. Escalate to Parrotfy support."
                }
            )
            print(f"SYNC_PARROTFY_PAYMENTS_SKIPPED reason=server_500 evidence=/srv/inteligencia_artificial/documentacion/parrotfy_pagos_500_evidencia.txt")
            return 0  # Not a failure, just skipped
        rows = []

    # Strategy B: fallback per invoice_id if global failed or returned empty
    if not rows and global_error and "500" not in global_error:
        tried_global = False
        conn = get_conn()
        try:
            inv_ids = [str(r["parrotfy_invoice_id"]) for r in conn.execute("SELECT parrotfy_invoice_id FROM parrotfy_invoices").fetchall()]
        finally:
            conn.close()

        ok_invoices = 0
        fail_invoices = 0

        for iid in inv_ids:
            # Common param name based on endpoint name
            params_candidates = [
                {"sale_invoice_id": iid},
                {"saleInvoiceId": iid},
                {"invoice_id": iid},
            ]
            got_any = False
            last_err = ""
            for params in params_candidates:
                try:
                    part = list_with_params(c, path, params, page_size=200, hard_cap=5000)
                    if part:
                        rows.extend(part)
                    got_any = True
                    break
                except Exception as e:
                    last_err = str(e)

            if got_any:
                ok_invoices += 1
            else:
                fail_invoices += 1
                try:
                    print(f"WARN: payments_for_invoice_failed invoice_id={iid} err={last_err}")
                except:
                    pass

        print(f"FALLBACK_PER_INVOICE_OK ok_invoices={ok_invoices} fail_invoices={fail_invoices} total_rows={len(rows)}")

    up = 0
    for r in rows:
        upsert_payment(r, ts)
        up += 1

    conn = get_conn()
    try:
        n = conn.execute("SELECT count(*) AS n FROM parrotfy_payments").fetchone()["n"]
        nz = conn.execute("SELECT count(*) AS n FROM parrotfy_payments WHERE amount > 0").fetchone()["n"]
    finally:
        conn.close()

    mode = "global" if tried_global else "per_invoice"
    print(f"SYNC_PARROTFY_PAYMENTS_OK mode={mode} upserts={up} received={len(rows)} db_count={n} nonzero_amount={nz}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
