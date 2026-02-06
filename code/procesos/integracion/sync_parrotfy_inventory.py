#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict

from parrotfy_client import ParrotfyClient, pick_first, to_float
from db import get_conn, init_db

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def upsert_inventory(row: Dict[str, Any], ts: str) -> None:
    # Identify unique ID
    pid = pick_first(row, ["id", "movement_id", "inventory_movement_id"])
    pid_s = str(pid).strip() if pid is not None else ""
    if not pid_s:
        return

    # Extract fields
    prod_id = pick_first(row, ["product_id", "variant_id", "item_id"]) or ""
    qty = pick_first(row, ["quantity", "amount", "count"]) or 0
    mtype = pick_first(row, ["type", "movement_type", "reason"]) or ""
    date_val = pick_first(row, ["date", "created_at", "timestamp"]) or ""

    raw = json.dumps(row, ensure_ascii=True, sort_keys=True)

    conn = get_conn()
    try:
        conn.execute("""
        INSERT INTO parrotfy_inventory (parrotfy_move_id, product_id, quantity, move_type, date, raw_json, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(parrotfy_move_id) DO UPDATE SET
          product_id=excluded.product_id,
          quantity=excluded.quantity,
          move_type=excluded.move_type,
          date=excluded.date,
          raw_json=excluded.raw_json,
          synced_at=excluded.synced_at;
        """, (pid_s, str(prod_id), float(to_float(qty)), str(mtype), str(date_val), raw, ts))
        conn.commit()
    finally:
        conn.close()

def main() -> int:
    init_db()
    c = ParrotfyClient()
    ts = now_utc_iso()

    path = "/api/v1/inventory_movements"
    print(f"Syncing {path} ...")
    
    rows = []
    try:
        rows = c.list_all(path, page_size=200, hard_cap=20000)
    except Exception as e:
        print(f"ERROR: inventory_sync_failed reason={e}")
        return 1

    up = 0
    for r in rows:
        upsert_inventory(r, ts)
        up += 1

    conn = get_conn()
    try:
        n = conn.execute("SELECT count(*) AS n FROM parrotfy_inventory").fetchone()["n"]
    finally:
        conn.close()

    print(f"SYNC_PARROTFY_INVENTORY_OK upserts={up} received={len(rows)} db_count={n}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
