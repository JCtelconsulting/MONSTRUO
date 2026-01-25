import sqlite3
import os
import hmac
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple

DB_PATH = "../../data/db/monstruo.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def init_db() -> None:
    conn = get_conn()
    try:
        # Customers
        conn.execute("""
        CREATE TABLE IF NOT EXISTS laudus_customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laudus_customer_id TEXT NOT NULL UNIQUE,
            name TEXT DEFAULT '',
            legal_name TEXT DEFAULT '',
            vat_id TEXT DEFAULT '',
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_laudus_customers_vat ON laudus_customers(vat_id);")

        # Invoices
        conn.execute("""
        CREATE TABLE IF NOT EXISTS laudus_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laudus_invoice_id TEXT NOT NULL UNIQUE,
            customer_id TEXT DEFAULT '',
            doc_date TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            total_amount REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            is_paid INTEGER DEFAULT 0,
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_laudus_invoices_customer ON laudus_invoices(customer_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_laudus_invoices_due ON laudus_invoices(due_date);")

        # Payments
        conn.execute("""
        CREATE TABLE IF NOT EXISTS laudus_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laudus_payment_id TEXT NOT NULL UNIQUE,
            invoice_id TEXT DEFAULT '',
            customer_id TEXT DEFAULT '',
            payment_date TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_laudus_payments_invoice ON laudus_payments(invoice_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_laudus_payments_customer ON laudus_payments(customer_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_laudus_payments_date ON laudus_payments(payment_date);")

        # Alerts (created by compute_alerts.py, but ensure exists)
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);")

        # Auth: users + sessions
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'ops',  -- admin|finance|ops|warehouse
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(username);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at);")

        # -----------------------------
        # Parrotfy Staging (Raw Sync)
        # -----------------------------
        # Invoices
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parrotfy_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parrotfy_invoice_id TEXT NOT NULL UNIQUE,
            invoice_number TEXT DEFAULT '',
            issued_date TEXT DEFAULT '',
            customer_id TEXT DEFAULT '',
            total_amount REAL DEFAULT 0,
            status TEXT DEFAULT '',
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_inv_number ON parrotfy_invoices(invoice_number);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_inv_customer ON parrotfy_invoices(customer_id);")

        # Payments
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parrotfy_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parrotfy_payment_id TEXT NOT NULL UNIQUE,
            parrotfy_invoice_id TEXT DEFAULT '',
            payment_date TEXT DEFAULT '',
            amount REAL DEFAULT 0,
            method TEXT DEFAULT '',
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_pay_invoice ON parrotfy_payments(parrotfy_invoice_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_pay_date ON parrotfy_payments(payment_date);")

        # Inventory
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parrotfy_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parrotfy_move_id TEXT NOT NULL UNIQUE,
            product_id TEXT DEFAULT '',
            quantity REAL DEFAULT 0,
            move_type TEXT DEFAULT '',
            date TEXT DEFAULT '',
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_inv_prod ON parrotfy_inventory(product_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pf_inv_date ON parrotfy_inventory(date);")

        conn.commit()
    finally:
        conn.close()

def update_invoice_balance(laudus_invoice_id: str, new_balance: float) -> None:
    conn = get_conn()
    try:
        conn.execute("""
        UPDATE laudus_invoices
        SET balance = ?,
            is_paid = CASE WHEN ? <= 0.01 THEN 1 ELSE 0 END
        WHERE laudus_invoice_id = ?;
        """, (float(new_balance), float(new_balance), laudus_invoice_id))
        conn.commit()
    finally:
        conn.close()

def upsert_payment(
    laudus_payment_id: str,
    invoice_id: str,
    customer_id: str,
    payment_date: str,
    amount: float,
    raw_json: str,
    synced_at: str
) -> None:
    conn = get_conn()
    try:
        conn.execute("""
        INSERT INTO laudus_payments (laudus_payment_id, invoice_id, customer_id, payment_date, amount, raw_json, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(laudus_payment_id) DO UPDATE SET
          invoice_id=excluded.invoice_id,
          customer_id=excluded.customer_id,
          payment_date=excluded.payment_date,
          amount=excluded.amount,
          raw_json=excluded.raw_json,
          synced_at=excluded.synced_at;
        """, (laudus_payment_id, invoice_id, customer_id, payment_date, float(amount or 0), raw_json, synced_at))
        conn.commit()
    finally:
        conn.close()

# -----------------------------
# Auth helpers (PBKDF2)
# -----------------------------
def _pbkdf2_hash(password: str, salt: bytes, iterations: int = 200_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)

def make_password_hash(password: str, iterations: int = 200_000) -> str:
    salt = os.urandom(16)
    dk = _pbkdf2_hash(password, salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it_s, salt_hex, dk_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(it_s)
        salt = bytes.fromhex(salt_hex)
        dk = bytes.fromhex(dk_hex)
        calc = _pbkdf2_hash(password, salt, iterations)
        return hmac.compare_digest(calc, dk)
    except Exception:
        return False

def create_user(username: str, password: str, role: str) -> None:
    init_db()
    username = username.strip()
    role = role.strip()
    if role not in ("admin", "finance", "ops", "warehouse"):
        raise ValueError("invalid_role")

    conn = get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            raise RuntimeError("user_exists")
        ph = make_password_hash(password)
        conn.execute(
            "INSERT INTO users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            (username, ph, role, now_utc_iso())
        )
        conn.commit()
    finally:
        conn.close()

def verify_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT username, password_hash, role, is_active FROM users WHERE username=?",
            (username.strip(),)
        ).fetchone()
        if not row or int(row["is_active"] or 0) != 1:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return {"username": row["username"], "role": row["role"]}
    finally:
        conn.close()

def create_session(username: str, role: str, minutes: int = 720) -> Dict[str, Any]:
    init_db()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=minutes)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO sessions (token, username, role, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (token, username, role, exp.isoformat(), now.isoformat())
        )
        conn.commit()
    finally:
        conn.close()
    return {"token": token, "expires_at": exp.isoformat(), "username": username, "role": role}

def get_session(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    init_db()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT token, username, role, expires_at FROM sessions WHERE token=?",
            (token.strip(),)
        ).fetchone()
        if not row:
            return None
        exp = row["expires_at"]
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", ""))
        except Exception:
            return None
        if exp_dt < datetime.now(timezone.utc):
            return None
        return {"token": row["token"], "username": row["username"], "role": row["role"], "expires_at": row["expires_at"]}
    finally:
        conn.close()
