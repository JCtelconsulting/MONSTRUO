import logging
import os
import hmac
import hashlib
import secrets
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import psycopg
    from psycopg.rows import dict_row
    _HAVE_PSYCOPG3 = True
except Exception:
    psycopg = None
    dict_row = None
    _HAVE_PSYCOPG3 = False

try:
    from psycopg_pool import ConnectionPool as _PsycopgPool
    _HAVE_POOL = True
except Exception:
    _PsycopgPool = None
    _HAVE_POOL = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    _HAVE_PSYCOPG2 = True
except Exception:
    psycopg2 = None
    RealDictCursor = None
    _HAVE_PSYCOPG2 = False

_pool: "object | None" = None  # ConnectionPool instance when available

from fundacion.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# DB_URL se resuelve dinámicamente en get_conn()
CHAIN_ALGO = "sha256"
CHAIN_VERSION = 1


def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


RETENTION_PUBLIC_DAYS = _env_int("TICKET_RETENTION_PUBLIC_DAYS", 365, 1, 36500)
RETENTION_INTERNAL_DAYS = _env_int("TICKET_RETENTION_INTERNAL_DAYS", 1095, 1, 36500)
RETENTION_RESTRICTED_DAYS = _env_int("TICKET_RETENTION_RESTRICTED_DAYS", 1825, 1, 36500)


def is_postgres() -> bool:
    url = os.getenv("DB_URL", "").strip()
    return url.startswith("postgres://") or url.startswith("postgresql://")


def _sqlite_path_from_url(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "", 1)
    return DEFAULT_DB_PATH


def _convert_sql_for_postgres(sql: str) -> str:
    sql = re.sub(
        r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
        "SERIAL PRIMARY KEY",
        sql,
        flags=re.I,
    )
    sql = re.sub(r"INTEGER\s+PRIMARY\s+KEY", "SERIAL PRIMARY KEY", sql, flags=re.I)
    sql = re.sub(r"BOOLEAN\s+DEFAULT\s+1", "BOOLEAN DEFAULT TRUE", sql, flags=re.I)
    sql = re.sub(r"BOOLEAN\s+DEFAULT\s+0", "BOOLEAN DEFAULT FALSE", sql, flags=re.I)
    if "?" in sql:
        sql = sql.replace("?", "%s")
    return sql


class PgConn:
    def __init__(self, conn, use_psycopg3: bool, pool=None):
        self._conn = conn
        self._use_psycopg3 = use_psycopg3
        self._pool = pool  # si viene del pool, close() lo devuelve en lugar de cerrarlo

    def execute(self, sql: str, params: Optional[Tuple[Any, ...]] = None):
        sql = _convert_sql_for_postgres(sql)
        if self._use_psycopg3:
            return self._conn.execute(sql, params or ())
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        return cur

    def execute_script(self, sql: str):
        """Ejecuta SQL literal sin parsear placeholders.

        Para archivos de migración con LIKE '%"x"%' o cualquier otro `%`
        que no sea un placeholder real. psycopg3 al recibir un argumento
        `params` (incluso `()`) parsea la query y aborta con `only '%s',
        '%b', '%t' are allowed as placeholders, got '%"'`. Llamando a
        `_conn.execute(sql)` SIN segundo argumento, psycopg3 trata el
        SQL como literal y no toca los `%`.
        """
        sql = _convert_sql_for_postgres(sql)
        if self._use_psycopg3:
            return self._conn.execute(sql)
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._pool is not None:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()


def init_pool() -> None:
    """
    Inicializa el connection pool global (psycopg3 + psycopg-pool).
    Llamar una vez en el startup de la app. Sin pool, get_conn() abre
    conexiones directas como antes — comportamiento degradado pero funcional.
    """
    global _pool
    if not _HAVE_PSYCOPG3 or not _HAVE_POOL:
        logger.warning("[DB] psycopg_pool no disponible — operando sin pool (conexiones directas)")
        return
    if _pool is not None:
        return

    db_url = os.getenv("DB_URL", "").strip()
    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        return

    min_size = int(os.getenv("DB_POOL_MIN", "2"))
    max_size = int(os.getenv("DB_POOL_MAX", "10"))
    try:
        _pool = _PsycopgPool(
            db_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        logger.info("[DB] Connection pool iniciado min=%d max=%d", min_size, max_size)
    except Exception as e:
        logger.error("[DB] No se pudo iniciar pool: %s — operando sin pool", e)
        _pool = None


def get_conn():
    db_url = os.getenv("DB_URL", "").strip()
    if not (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        raise RuntimeError(
            f"CRITICAL: PostgreSQL is required. Check DB_URL environment variable ({'empty' if not db_url else 'invalid'}). SQLite fallback has been disabled for safety."
        )

    # Usar pool si está disponible
    if _pool is not None:
        conn = _pool.getconn()
        pg_conn = PgConn(conn, use_psycopg3=True, pool=_pool)
        pg_conn.execute("SET search_path TO fundacion, public;")
        return pg_conn

    if _HAVE_PSYCOPG3:
        conn = psycopg.connect(db_url, row_factory=dict_row)
        pg_conn = PgConn(conn, use_psycopg3=True)
        pg_conn.execute("SET search_path TO fundacion, public;")
        return pg_conn
    if _HAVE_PSYCOPG2:
        conn = psycopg2.connect(db_url)
        pg_conn = PgConn(conn, use_psycopg3=False)
        pg_conn.execute("SET search_path TO fundacion, public;")
        return pg_conn

    raise RuntimeError("PostgreSQL driver not installed. Install psycopg or psycopg2.")


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_json_for_chain(payload: Dict[str, Any]) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_chain_hash(prev_hash: str, payload: Dict[str, Any]) -> str:
    raw = f"{prev_hash or ''}|{_stable_json_for_chain(payload)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _backfill_chain_table(conn, table_name: str, payload_fields: Tuple[str, ...]) -> None:
    select_fields = ", ".join(["id", *payload_fields, "chain_prev_hash", "chain_hash"])
    rows = conn.execute(
        f"SELECT {select_fields} FROM {table_name} ORDER BY id ASC"
    ).fetchall()
    prev_hash = ""
    for row in rows:
        record = dict(row)
        payload = {field: (record.get(field) if record.get(field) is not None else "") for field in payload_fields}
        expected_hash = _build_chain_hash(prev_hash, payload)
        current_prev = (record.get("chain_prev_hash") or "")
        current_hash = (record.get("chain_hash") or "")
        if current_prev != prev_hash or current_hash != expected_hash:
            conn.execute(
                f"""UPDATE {table_name}
                    SET chain_prev_hash = ?, chain_hash = ?, chain_algo = ?, chain_version = ?
                    WHERE id = ?""",
                (prev_hash, expected_hash, CHAIN_ALGO, CHAIN_VERSION, record["id"]),
            )
        prev_hash = expected_hash


def _create_append_only_triggers(conn, table_name: str) -> None:
    fn_name = f"{table_name}_append_only_guard"
    trg_upd = f"trg_{table_name}_no_update"
    trg_del = f"trg_{table_name}_no_delete"
    conn.execute(
        f"""
        CREATE OR REPLACE FUNCTION {fn_name}() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '{table_name} is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    conn.execute(f"DROP TRIGGER IF EXISTS {trg_upd} ON {table_name};")
    conn.execute(f"DROP TRIGGER IF EXISTS {trg_del} ON {table_name};")
    conn.execute(
        f"""CREATE TRIGGER {trg_upd}
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {fn_name}();"""
    )
    conn.execute(
        f"""CREATE TRIGGER {trg_del}
            BEFORE DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION {fn_name}();"""
    )


def _drop_append_only_triggers(conn, table_name: str) -> None:
    trg_upd = f"trg_{table_name}_no_update"
    trg_del = f"trg_{table_name}_no_delete"
    conn.execute(f"DROP TRIGGER IF EXISTS {trg_upd} ON {table_name};")
    conn.execute(f"DROP TRIGGER IF EXISTS {trg_del} ON {table_name};")


def _has_append_only_triggers(conn, table_name: str) -> bool:
    trg_upd = f"trg_{table_name}_no_update"
    trg_del = f"trg_{table_name}_no_delete"
    row = conn.execute(
        """SELECT 1
           FROM pg_trigger t
           JOIN pg_class c ON c.oid = t.tgrelid
           WHERE c.relname = ?
             AND NOT t.tgisinternal
             AND t.tgname IN (?, ?)
           LIMIT 1""",
        (table_name, trg_upd, trg_del),
    ).fetchone()
    return bool(row)


def _chain_table_is_consistent(conn, table_name: str, payload_fields: Tuple[str, ...]) -> bool:
    select_fields = ", ".join(["id", *payload_fields, "chain_prev_hash", "chain_hash"])
    rows = conn.execute(
        f"SELECT {select_fields} FROM {table_name} ORDER BY id ASC"
    ).fetchall()
    prev_hash = ""
    for row in rows:
        record = dict(row)
        payload = {field: (record.get(field) if record.get(field) is not None else "") for field in payload_fields}
        expected_hash = _build_chain_hash(prev_hash, payload)
        current_prev = (record.get("chain_prev_hash") or "")
        current_hash = (record.get("chain_hash") or "")
        if current_prev != prev_hash or current_hash != expected_hash:
            return False
        prev_hash = expected_hash
    return True


def _run_guarded_pg_section(conn, section_name: str, fn) -> None:
    sp_name = f"sp_{section_name}".replace("-", "_")
    conn.execute(f"SAVEPOINT {sp_name}")
    try:
        fn()
        conn.execute(f"RELEASE SAVEPOINT {sp_name}")
    except Exception as e:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
            conn.execute(f"RELEASE SAVEPOINT {sp_name}")
        except Exception:
            pass
        logger.warning("[DB-MIGRATION] WARN %s: %s", section_name, e)


def init_db() -> None:
    """Inicializa SOLO el schema de Fundación.

    Separación fase 3: ya no crea los schemas ni las tablas de toda la plataforma
    Monstruo. Crea el schema `fundacion` (idempotente) y corre las migraciones
    PROPIAS (fundacion/migrations), que crean users, sedes, sesiones, etc.
    """
    init_pool()
    conn = get_conn()
    try:
        conn.execute("CREATE SCHEMA IF NOT EXISTS fundacion;")
        conn.commit()
    finally:
        conn.close()

    # Automated Migrations Engine (solo migraciones de Fundación)
    try:
        from fundacion.core import migrations
        migrations.run_migrations()
    except Exception as e:
        logger.error("[DB] ERROR running automated migrations: %s", e)


def update_invoice_balance(laudus_invoice_id: str, new_balance: float) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
        UPDATE laudus_invoices
        SET balance = ?,
            is_paid = CASE WHEN ? <= 0.01 THEN 1 ELSE 0 END
        WHERE laudus_invoice_id = ?;
        """,
            (float(new_balance), float(new_balance), laudus_invoice_id),
        )
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
    synced_at: str,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
        INSERT INTO laudus_payments (laudus_payment_id, invoice_id, customer_id, payment_date, amount, raw_json, synced_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(laudus_payment_id) DO UPDATE SET
          invoice_id=excluded.invoice_id,
          customer_id=excluded.customer_id,
          payment_date=excluded.payment_date,
          amount=excluded.amount,
          raw_json=excluded.raw_json,
          synced_at=excluded.synced_at;
        """,
            (
                laudus_payment_id,
                invoice_id,
                customer_id,
                payment_date,
                float(amount or 0),
                raw_json,
                synced_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_invoice(
    laudus_invoice_id: str,
    customer_id: str,
    doc_date: str,
    due_date: str,
    total_amount: float,
    balance: float,
    is_paid: bool,
    raw_json: str,
    synced_at: str,
) -> None:
    conn = get_conn()
    try:
        # Map to unified 'invoices' table
        # We need to map laudus fields to invoices table columns
        # invoices(id, customer_id, type="FACTURA", status, total_final, issuer_id, issued_at, external_id)

        status = "PAID" if is_paid else "ISSUED"
        if balance <= 0.01:
            status = "PAID"

        conn.execute(
            """
        INSERT INTO invoices (
            customer_id, type, status, total_final, 
            issuer_id, issued_at, created_at, updated_at, external_id,
            ref_id
        ) VALUES (
            ?, 'FACTURA', ?, ?, 
            'laudus_sync', ?, ?, ?, ?,
            0
        )
        ON CONFLICT(external_id) DO UPDATE SET
            customer_id=excluded.customer_id,
            status=excluded.status,
            total_final=excluded.total_final,
            issued_at=excluded.issued_at,
            updated_at=excluded.updated_at;
        """,
            (
                customer_id,
                status,
                float(total_amount),
                doc_date,
                synced_at,
                synced_at,
                laudus_invoice_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


