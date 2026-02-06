#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Tuple, Any, List, Set, Optional

import db

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def parse_iso_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    s = str(s).strip()
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None

def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule TEXT NOT NULL,
        severity TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        summary TEXT DEFAULT '',
        details_json TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open',  -- open|resolved
        first_seen_at TEXT DEFAULT '',
        last_seen_at TEXT DEFAULT '',
        resolved_at TEXT DEFAULT '',
        occurrences INTEGER DEFAULT 1,
        UNIQUE(rule, entity_type, entity_id)
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_rule ON alerts(rule);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_entity ON alerts(entity_type, entity_id);")
    conn.commit()

def load_existing(conn: sqlite3.Connection) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    rows = conn.execute("""
        SELECT rule, entity_type, entity_id, status, occurrences
        FROM alerts
    """).fetchall()
    out: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in rows:
        k = (r["rule"], r["entity_type"], r["entity_id"])
        out[k] = {"status": r["status"], "occurrences": int(r["occurrences"] or 0)}
    return out

def upsert_alert(conn: sqlite3.Connection, key: Tuple[str, str, str], severity: str, summary: str, details: Dict[str, Any], ts: str, existed: bool, prev_occ: int) -> None:
    rule, entity_type, entity_id = key
    details_json = json.dumps(details, ensure_ascii=True, sort_keys=True)
    if not existed:
        conn.execute("""
            INSERT INTO alerts (rule, severity, entity_type, entity_id, summary, details_json, status, first_seen_at, last_seen_at, occurrences)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, 1)
        """, (rule, severity, entity_type, entity_id, summary, details_json, ts, ts))
    else:
        conn.execute("""
            UPDATE alerts
            SET severity=?,
                summary=?,
                details_json=?,
                status='open',
                last_seen_at=?,
                resolved_at='',
                occurrences=?
            WHERE rule=? AND entity_type=? AND entity_id=?
        """, (severity, summary, details_json, ts, prev_occ + 1, rule, entity_type, entity_id))

def resolve_alert(conn: sqlite3.Connection, key: Tuple[str, str, str], ts: str) -> None:
    rule, entity_type, entity_id = key
    conn.execute("""
        UPDATE alerts
        SET status='resolved',
            resolved_at=?,
            last_seen_at=?
        WHERE rule=? AND entity_type=? AND entity_id=? AND status='open'
    """, (ts, ts, rule, entity_type, entity_id))

def main() -> int:
    db.init_db()
    conn = db.get_conn()
    try:
        ensure_table(conn)
        existing = load_existing(conn)

        invoices = conn.execute("""
            SELECT laudus_invoice_id, customer_id, doc_date, due_date, total_amount, balance, is_paid
            FROM laudus_invoices
        """).fetchall()

        invoice_ids: Set[str] = set(str(r["laudus_invoice_id"]) for r in invoices)

        payments = conn.execute("""
            SELECT laudus_payment_id, invoice_id, customer_id, payment_date, amount
            FROM laudus_payments
        """).fetchall()

        ts = now_utc_iso()
        new_keys: Set[Tuple[str, str, str]] = set()
        open_count = 0
        resolved_count = 0

        # ---- RULES ----

        # R1: payment unlinked to invoice
        for p in payments:
            pid = str(p["laudus_payment_id"])
            inv_id = str(p["invoice_id"] or "").strip()
            amt = float(p["amount"] or 0.0)
            if inv_id == "" or inv_id not in invoice_ids:
                key = ("payment_unlinked_invoice", "payment", pid)
                severity = "high"
                summary = "Payment not linked to a valid invoice"
                details = {"payment_id": pid, "invoice_id": inv_id, "amount": amt}
                existed = key in existing
                prev_occ = existing.get(key, {}).get("occurrences", 0)
                upsert_alert(conn, key, severity, summary, details, ts, existed, prev_occ)
                new_keys.add(key)

        # R2: invoice missing due_date (only if balance > 0)
        for inv in invoices:
            iid = str(inv["laudus_invoice_id"])
            due = str(inv["due_date"] or "").strip()
            bal = float(inv["balance"] or 0.0)
            if bal > 0.01 and due == "":
                key = ("invoice_missing_due_date", "invoice", iid)
                severity = "medium"
                summary = "Invoice has balance but no due_date"
                details = {"invoice_id": iid, "balance": bal, "customer_id": str(inv["customer_id"] or "")}
                existed = key in existing
                prev_occ = existing.get(key, {}).get("occurrences", 0)
                upsert_alert(conn, key, severity, summary, details, ts, existed, prev_occ)
                new_keys.add(key)

        # R3: invoice balance negative
        for inv in invoices:
            iid = str(inv["laudus_invoice_id"])
            bal = float(inv["balance"] or 0.0)
            if bal < -0.01:
                key = ("invoice_balance_negative", "invoice", iid)
                severity = "high"
                summary = "Invoice balance is negative"
                details = {"invoice_id": iid, "balance": bal, "total_amount": float(inv["total_amount"] or 0.0)}
                existed = key in existing
                prev_occ = existing.get(key, {}).get("occurrences", 0)
                upsert_alert(conn, key, severity, summary, details, ts, existed, prev_occ)
                new_keys.add(key)

        # R4: invoice balance > total
        for inv in invoices:
            iid = str(inv["laudus_invoice_id"])
            total = float(inv["total_amount"] or 0.0)
            bal = float(inv["balance"] or 0.0)
            if bal > total + 0.01:
                key = ("invoice_balance_gt_total", "invoice", iid)
                severity = "high"
                summary = "Invoice balance greater than total_amount"
                details = {"invoice_id": iid, "balance": bal, "total_amount": total}
                existed = key in existing
                prev_occ = existing.get(key, {}).get("occurrences", 0)
                upsert_alert(conn, key, severity, summary, details, ts, existed, prev_occ)
                new_keys.add(key)

        # R5: is_paid flag inconsistent
        for inv in invoices:
            iid = str(inv["laudus_invoice_id"])
            bal = float(inv["balance"] or 0.0)
            is_paid = int(inv["is_paid"] or 0)
            if is_paid == 1 and bal > 0.01:
                key = ("invoice_is_paid_inconsistent", "invoice", iid)
                severity = "medium"
                summary = "Invoice marked paid but balance > 0"
                details = {"invoice_id": iid, "balance": bal, "is_paid": is_paid}
                existed = key in existing
                prev_occ = existing.get(key, {}).get("occurrences", 0)
                upsert_alert(conn, key, severity, summary, details, ts, existed, prev_occ)
                new_keys.add(key)
            if is_paid == 0 and bal <= 0.01 and float(inv["total_amount"] or 0.0) > 0.01:
                key = ("invoice_unpaid_but_zero_balance", "invoice", iid)
                severity = "low"
                summary = "Invoice not paid flag but balance ~ 0"
                details = {"invoice_id": iid, "balance": bal, "is_paid": is_paid}
                existed = key in existing
                prev_occ = existing.get(key, {}).get("occurrences", 0)
                upsert_alert(conn, key, severity, summary, details, ts, existed, prev_occ)
                new_keys.add(key)

        # Resolve alerts not present anymore
        for key, meta in existing.items():
            if meta.get("status") == "open" and key not in new_keys:
                resolve_alert(conn, key, ts)

        conn.commit()

        open_count = conn.execute("SELECT count(*) AS n FROM alerts WHERE status='open'").fetchone()["n"]
        resolved_count = conn.execute("SELECT count(*) AS n FROM alerts WHERE status='resolved'").fetchone()["n"]
        total = conn.execute("SELECT count(*) AS n FROM alerts").fetchone()["n"]

        print(f"ALERTS_OK open={open_count} resolved={resolved_count} total={total}")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
