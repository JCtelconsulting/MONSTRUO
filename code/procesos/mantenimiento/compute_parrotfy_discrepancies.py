#!/usr/bin/env python3
import json
import sqlite3
import re
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple, Set

DB_PATH = "monstruo.db"

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_ticket_for_discrepancia(conn: sqlite3.Connection, origen: str, tipo: str, entidad_ref: str, titulo: str, descripcion: str) -> None:
    # Idempotencia: si existe ticket abierto/en_progreso para este origen+tipo+entidad_ref, no hacer nada
    cur = conn.execute(
        "SELECT id FROM tks_tickets WHERE origen=? AND tipo=? AND entidad_ref=? AND estado IN ('abierto', 'en_progreso')",
        (origen, tipo, entidad_ref)
    )
    if cur.fetchone():
        return # Ya existe

    # Crear ticket
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"TKS-{today_str}-"
    
    # Max seq
    row = conn.execute(
        "SELECT codigo FROM tks_tickets WHERE codigo LIKE ? ORDER BY codigo DESC LIMIT 1", 
        (f"{prefix}%",)
    ).fetchone()
    
    if row:
        last_seq = int(row["codigo"].split("-")[-1])
        new_seq = last_seq + 1
    else:
        new_seq = 1
        
    codigo = f"{prefix}{new_seq:04d}"
    now = now_utc_iso()
    
    conn.execute("""
        INSERT INTO tks_tickets (codigo, origen, tipo, severidad, estado, titulo, descripcion, entidad_ref, creado_at, actualizado_at)
        VALUES (?, ?, ?, 'media', 'abierto', ?, ?, ?, ?, ?)
    """, (codigo, origen, tipo, titulo, descripcion, entidad_ref, now, now))
    
    # Obtener ID para evento
    tid = conn.execute("SELECT id FROM tks_tickets WHERE codigo=?", (codigo,)).fetchone()["id"]
    
    conn.execute("""
        INSERT INTO tks_eventos (ticket_id, evento, detalle, creado_at)
        VALUES (?, 'created_from_discrepancy', 'Ticket creado automaticamente por discrepancia', ?)
    """, (tid, now))
    
    print(f"AUTO_TICKET_CREATED id={codigo}")

def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS parrotfy_discrepancies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        severity TEXT NOT NULL,
        laudus_ref TEXT DEFAULT '',
        parrotfy_ref TEXT DEFAULT '',
        summary TEXT DEFAULT '',
        details_json TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open',
        first_seen_at TEXT DEFAULT '',
        last_seen_at TEXT DEFAULT '',
        resolved_at TEXT DEFAULT '',
        occurrences INTEGER DEFAULT 1
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_disc_status ON parrotfy_discrepancies(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_disc_kind ON parrotfy_discrepancies(kind);")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule TEXT NOT NULL,
        severity TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        summary TEXT DEFAULT '',
        details_json TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open',
        first_seen_at TEXT DEFAULT '',
        last_seen_at TEXT DEFAULT '',
        resolved_at TEXT DEFAULT '',
        occurrences INTEGER DEFAULT 1,
        UNIQUE(rule, entity_type, entity_id)
    );
    """)
    conn.commit()

LIKELY_KEY_SUBSTRINGS = [
    "folio", "invoice", "number", "document", "doc", "nro", "num", "serie", "serial"
]

def deep_find_first(obj: Any, key_substrings: List[str], max_depth: int = 6) -> Optional[Tuple[str, str]]:
    def walk(x: Any, depth: int) -> Optional[Tuple[str, str]]:
        if depth > max_depth:
            return None
        if isinstance(x, dict):
            for k, v in x.items():
                kl = str(k).lower()
                if any(sub in kl for sub in key_substrings):
                    if v is None:
                        continue
                    if isinstance(v, (str, int)):
                        vv = str(v).strip()
                        if vv:
                            return (str(k), vv)
            for v in x.values():
                r = walk(v, depth + 1)
                if r:
                    return r
        elif isinstance(x, list):
            for it in x:
                r = walk(it, depth + 1)
                if r:
                    return r
        return None
    return walk(obj, 0)

def digits_only_normalized(s: str) -> str:
    """
    Normalize invoice-like identifiers to comparable numeric string.
    Example: E00000722 -> 722 ; 00048 -> 48 ; 687 -> 687
    Returns '' if no digits.
    """
    s = (s or "").strip()
    d = re.sub(r"\D+", "", s)
    if not d:
        return ""
    # remove leading zeros safely
    try:
        return str(int(d))
    except Exception:
        return d.lstrip("0") or "0"

def parse_date_prefix(s: str) -> str:
    s = (s or "").strip()
    return s[:10] if len(s) >= 10 else s

def to_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0

def upsert_disc(conn: sqlite3.Connection, key: str, kind: str, severity: str, laudus_ref: str, parrotfy_ref: str, summary: str, details: Dict[str, Any], ts: str) -> None:
    details_json = json.dumps(details, ensure_ascii=True, sort_keys=True)
    row = conn.execute("SELECT occurrences FROM parrotfy_discrepancies WHERE key=?", (key,)).fetchone()
    if not row:
        conn.execute("""
            INSERT INTO parrotfy_discrepancies (key, kind, severity, laudus_ref, parrotfy_ref, summary, details_json, status, first_seen_at, last_seen_at, occurrences)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, 1)
        """, (key, kind, severity, laudus_ref, parrotfy_ref, summary, details_json, ts, ts))
        
        # Auto-ticket on FIRST see
        ensure_ticket_for_discrepancia(conn, "discrepancia", kind, key, f"Discrepancia: {summary}", f"Ref P: {parrotfy_ref}, Ref L: {laudus_ref}, Key: {key}")
    else:
        occ = int(row["occurrences"] or 0)
        conn.execute("""
            UPDATE parrotfy_discrepancies
            SET kind=?,
                severity=?,
                laudus_ref=?,
                parrotfy_ref=?,
                summary=?,
                details_json=?,
                status='open',
                last_seen_at=?,
                resolved_at='',
                occurrences=?
            WHERE key=?
        """, (kind, severity, laudus_ref, parrotfy_ref, summary, details_json, ts, occ + 1, key))

def upsert_alert(conn: sqlite3.Connection, rule: str, severity: str, entity_type: str, entity_id: str, summary: str, details: Dict[str, Any], ts: str) -> None:
    details_json = json.dumps(details, ensure_ascii=True, sort_keys=True)
    row = conn.execute("""
        SELECT occurrences
        FROM alerts
        WHERE rule=? AND entity_type=? AND entity_id=?
    """, (rule, entity_type, entity_id)).fetchone()
    if not row:
        conn.execute("""
            INSERT INTO alerts (rule, severity, entity_type, entity_id, summary, details_json, status, first_seen_at, last_seen_at, occurrences)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, 1)
        """, (rule, severity, entity_type, entity_id, summary, details_json, ts, ts))
    else:
        occ = int(row["occurrences"] or 0)
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
        """, (severity, summary, details_json, ts, occ + 1, rule, entity_type, entity_id))

def resolve_disc(conn: sqlite3.Connection, key: str, ts: str) -> None:
    conn.execute("""
        UPDATE parrotfy_discrepancies
        SET status='resolved',
            resolved_at=?,
            last_seen_at=?
        WHERE key=? AND status='open'
    """, (ts, ts, key))

def main() -> int:
    conn = get_conn()
    try:
        ensure_tables(conn)
        ts = now_utc_iso()
        
        # Check env for severity adjustment
        is_staging = os.getenv("PARROTFY_ENV", "").lower() == "staging"
        missing_severity = "low" if is_staging else "high"
        if is_staging:
            print(f"INFO: Running in staging mode (PARROTFY_ENV=staging). Missing severity -> {missing_severity}")

        # Parrotfy invoices: build by normalized number
        pf_rows = conn.execute("""
            SELECT parrotfy_invoice_id, invoice_number, issued_date, total_amount, status, raw_json
            FROM parrotfy_invoices
        """).fetchall()

        pf_by_norm: Dict[str, Dict[str, Any]] = {}
        pf_norm_missing = 0
        for r in pf_rows:
            raw_no = str(r["invoice_number"] or "").strip()
            norm = digits_only_normalized(raw_no)
            if not norm:
                # fallback deep search in raw_json
                try:
                    jr = json.loads(str(r["raw_json"] or ""))
                    kv = deep_find_first(jr, LIKELY_KEY_SUBSTRINGS)
                    if kv:
                        norm = digits_only_normalized(kv[1])
                except Exception:
                    pass
            if not norm:
                pf_norm_missing += 1
                continue
            pf_by_norm[norm] = dict(r)

        # Laudus invoices: extract invoice-like id and normalize
        ld_rows = conn.execute("""
            SELECT laudus_invoice_id, doc_date, total_amount, raw_json
            FROM laudus_invoices
        """).fetchall()

        ld_by_norm: Dict[str, List[Dict[str, Any]]] = {}
        ld_norm_missing = 0
        for r in ld_rows:
            raw = str(r["raw_json"] or "")
            picked_key = ""
            picked_val = ""
            try:
                jr = json.loads(raw) if raw else {}
                kv = deep_find_first(jr, LIKELY_KEY_SUBSTRINGS)
                if kv:
                    picked_key, picked_val = kv
            except Exception:
                pass

            norm = digits_only_normalized(picked_val) if picked_val else ""
            if not norm:
                ld_norm_missing += 1
                continue

            d = dict(r)
            d["_picked_key"] = picked_key
            d["_picked_val"] = picked_val
            ld_by_norm.setdefault(norm, []).append(d)

        print(f"STATS pf_norm_keys={len(pf_by_norm)} pf_norm_missing={pf_norm_missing} ld_norm_keys={len(ld_by_norm)} ld_norm_missing={ld_norm_missing}")

        open_keys: Set[str] = set()

        # Compare
        for norm, pf in pf_by_norm.items():
            ld_list = ld_by_norm.get(norm, [])
            if not ld_list:
                key = f"inv_norm:{norm}"
                open_keys.add(key)
                upsert_disc(
                    conn, key,
                    kind="missing_in_laudus",
                    severity=missing_severity,
                    laudus_ref="",
                    parrotfy_ref=str(pf.get("parrotfy_invoice_id")),
                    summary="Parrotfy invoice number (normalized) not found in Laudus",
                    details={"norm": norm, "parrotfy_invoice_number": str(pf.get("invoice_number")), "parrotfy_invoice_id": str(pf.get("parrotfy_invoice_id"))},
                    ts=ts
                )
                upsert_alert(
                    conn,
                    rule="parrotfy_invoice_missing_in_laudus_norm",
                    severity=missing_severity,
                    entity_type="invoice_norm",
                    entity_id=norm,
                    summary="Parrotfy invoice not found in Laudus (normalized digits)",
                    details={"norm": norm, "parrotfy_invoice_id": str(pf.get("parrotfy_invoice_id"))},
                    ts=ts
                )
                continue

            if len(ld_list) > 1:
                # ambiguous match
                key = f"inv_norm:{norm}"
                open_keys.add(key)
                upsert_disc(
                    conn, key,
                    kind="ambiguous_in_laudus",
                    severity="medium",
                    laudus_ref=",".join(str(x.get("laudus_invoice_id")) for x in ld_list),
                    parrotfy_ref=str(pf.get("parrotfy_invoice_id")),
                    summary="Multiple Laudus invoices map to same normalized number; manual review needed",
                    details={"norm": norm, "laudus_candidates": [{"laudus_invoice_id": x.get("laudus_invoice_id"), "picked_key": x.get("_picked_key"), "picked_val": x.get("_picked_val")} for x in ld_list], "parrotfy_invoice_number": str(pf.get("invoice_number"))},
                    ts=ts
                )
                upsert_alert(
                    conn,
                    rule="parrotfy_invoice_ambiguous_in_laudus_norm",
                    severity="medium",
                    entity_type="invoice_norm",
                    entity_id=norm,
                    summary="Ambiguous match Laudus vs Parrotfy (normalized digits)",
                    details={"norm": norm, "laudus_candidates": [str(x.get("laudus_invoice_id")) for x in ld_list]},
                    ts=ts
                )
                continue

        # Resolve old discrepancies
        disc_open = conn.execute("SELECT key FROM parrotfy_discrepancies WHERE status='open'").fetchall()
        for r in disc_open:
            k = str(r["key"])
            if k not in open_keys:
                resolve_disc(conn, k, ts)

        conn.commit()

        total = conn.execute("SELECT count(*) AS n FROM parrotfy_discrepancies").fetchone()["n"]
        open_n = conn.execute("SELECT count(*) AS n FROM parrotfy_discrepancies WHERE status='open'").fetchone()["n"]
        print(f"PARROTFY_DISCREPANCIES_OK open={open_n} total={total}")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
