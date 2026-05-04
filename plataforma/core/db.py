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

from core.env_loader import load_runtime_env

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
        pg_conn.execute("SET search_path TO auth, tks, erp, crm, bodega, core, cat, pmo, ia, ops, fundacion, public;")
        return pg_conn

    if _HAVE_PSYCOPG3:
        conn = psycopg.connect(db_url, row_factory=dict_row)
        pg_conn = PgConn(conn, use_psycopg3=True)
        pg_conn.execute("SET search_path TO auth, tks, erp, crm, bodega, core, cat, pmo, ia, ops, fundacion, public;")
        return pg_conn
    if _HAVE_PSYCOPG2:
        conn = psycopg2.connect(db_url)
        pg_conn = PgConn(conn, use_psycopg3=False)
        pg_conn.execute("SET search_path TO auth, tks, erp, crm, bodega, core, cat, pmo, ia, ops, fundacion, public;")
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
        logger.warning("[DB-MIGRATION] WARN {section_name}: {e}")


def init_db() -> None:
    init_pool()
    conn = get_conn()
    try:
        for schema_name in (
            "auth",
            "tks",
            "erp",
            "crm",
            "bodega",
            "core",
            "cat",
            "pmo",
            "ia",
            "ops",
            "fundacion",
            "gta",
        ):
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name};")

        # Customers
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.laudus_customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            laudus_customer_id TEXT NOT NULL UNIQUE,
            name TEXT DEFAULT '',
            legal_name TEXT DEFAULT '',
            vat_id TEXT DEFAULT '',
            raw_json TEXT DEFAULT '',
            synced_at TEXT DEFAULT ''
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_customers_vat ON erp.laudus_customers(vat_id);"
        )

        # Invoices
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.laudus_invoices (
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_invoices_customer ON erp.laudus_invoices(customer_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_invoices_due ON erp.laudus_invoices(due_date);"
        )

        # Payments
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.laudus_payments (
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_payments_invoice ON erp.laudus_payments(invoice_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_payments_customer ON erp.laudus_payments(customer_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_payments_date ON erp.laudus_payments(payment_date);"
        )

        # Alerts (created by compute_alerts.py, but ensure exists)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS core.alerts (
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON core.alerts(status);")

        # Auth: users + sessions
        conn.execute("""
        CREATE TABLE IF NOT EXISTS auth.users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'ops',  -- admin|finance|ops|warehouse
            is_active INTEGER NOT NULL DEFAULT 1,
            allowed_modules TEXT DEFAULT '[]',
            secondary_roles TEXT DEFAULT '[]',
            fundacion_scope TEXT DEFAULT '{}',
            phone_number TEXT,
            created_at TEXT DEFAULT ''
        );
        """)
        
        def _migrate_users_section() -> None:
            if is_postgres():
                conn.execute("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS allowed_modules TEXT DEFAULT '[]'")
                conn.execute("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS secondary_roles TEXT DEFAULT '[]'")
                conn.execute("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS fundacion_scope TEXT DEFAULT '{}'")
                conn.execute("ALTER TABLE auth.users ADD COLUMN IF NOT EXISTS phone_number TEXT")
            else:
                # SQLite fallback
                try:
                    conn.execute("ALTER TABLE auth.users ADD COLUMN allowed_modules TEXT DEFAULT '[]'")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE auth.users ADD COLUMN secondary_roles TEXT DEFAULT '[]'")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE auth.users ADD COLUMN fundacion_scope TEXT DEFAULT '{}'")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE auth.users ADD COLUMN phone_number TEXT")
                except Exception:
                    pass

        _run_guarded_pg_section(conn, "migrate_users", _migrate_users_section)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON auth.users(role);")

        # System Settings (EPIC Config)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS core.system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            group_name TEXT DEFAULT 'general',
            is_sensitive BOOLEAN DEFAULT 0,
            updated_at TEXT
        );
        """)

        def _migrate_system_settings_section() -> None:
            for col_name, col_def in [
                ("group_name", "TEXT DEFAULT 'general'"),
                ("is_sensitive", "BOOLEAN DEFAULT FALSE"),
                ("updated_at", "TEXT"),
            ]:
                conn.execute(f"ALTER TABLE core.system_settings ADD COLUMN IF NOT EXISTS {col_name} {col_def}")

        _run_guarded_pg_section(conn, "migrate_system_settings", _migrate_system_settings_section)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS auth.sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON auth.sessions(username);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_exp ON auth.sessions(expires_at);"
        )

        # Audit Logs (EPIC 02/03)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS core.audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,      -- Username or 'anonymous'
            action TEXT NOT NULL,     -- LOGIN_SUCCESS, LOGIN_FAILED, INVOICE_SYNC, etc.
            target TEXT DEFAULT '',   -- Entity affected
            ip_address TEXT DEFAULT '',
            metadata_json TEXT DEFAULT ''
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_ts ON core.audit_logs(timestamp);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON core.audit_logs(actor);")
        def _migrate_audit_logs_section() -> None:
            conn.execute(
                "ALTER TABLE core.audit_logs ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'info'"
            )
            conn.execute(
                "ALTER TABLE core.audit_logs ADD COLUMN IF NOT EXISTS chain_prev_hash TEXT DEFAULT ''"
            )
            conn.execute(
                "ALTER TABLE core.audit_logs ADD COLUMN IF NOT EXISTS chain_hash TEXT DEFAULT ''"
            )
            conn.execute(
                f"ALTER TABLE core.audit_logs ADD COLUMN IF NOT EXISTS chain_algo TEXT DEFAULT '{CHAIN_ALGO}'"
            )
            conn.execute(
                f"ALTER TABLE core.audit_logs ADD COLUMN IF NOT EXISTS chain_version INTEGER DEFAULT {CHAIN_VERSION}"
            )

        _run_guarded_pg_section(conn, "migrate_audit_logs", _migrate_audit_logs_section)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_chain_hash ON core.audit_logs(chain_hash);")

        # Jobs Engine (EPIC 04)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS core.sys_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_type TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',  -- PENDING, RUNNING, COMPLETED, FAILED, RETRY
            payload TEXT DEFAULT '{}',
            next_run_at TEXT NOT NULL,
            retries_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            last_error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON core.sys_jobs(status);")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON core.sys_jobs(next_run_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_type_status_next ON core.sys_jobs(job_type, status, next_run_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_status_updated ON core.sys_jobs(status, updated_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON core.sys_jobs(created_at);"
        )
        # Limpiar duplicados históricos antes de crear índices únicos parciales.
        try:
            now_jobs = now_utc_iso()
            conn.execute(
                """WITH ranked AS (
                       SELECT id,
                              ROW_NUMBER() OVER (
                                  PARTITION BY job_type
                                  ORDER BY next_run_at::timestamptz ASC, id ASC
                              ) AS rn
                       FROM sys_jobs
                       WHERE job_type = 'EMAIL_POLLING'
                         AND status IN ('PENDING', 'RETRY')
                   )
                   UPDATE sys_jobs j
                   SET status = 'FAILED',
                       updated_at = ?,
                       last_error = CASE
                           WHEN COALESCE(last_error, '') = '' THEN '[DB-MIGRATION] duplicate recurring job pruned'
                           ELSE (last_error || E'\n[DB-MIGRATION] duplicate recurring job pruned')
                       END
                   FROM ranked r
                   WHERE j.id = r.id
                     AND r.rn > 1""",
                (now_jobs,),
            )
            conn.execute(
                """WITH ranked AS (
                       SELECT id,
                              ROW_NUMBER() OVER (
                                  PARTITION BY job_type
                                  ORDER BY next_run_at::timestamptz ASC, id ASC
                              ) AS rn
                       FROM sys_jobs
                       WHERE job_type = 'PROCESS_NOTIFICATIONS'
                         AND status IN ('PENDING', 'RETRY')
                   )
                   UPDATE sys_jobs j
                   SET status = 'FAILED',
                       updated_at = ?,
                       last_error = CASE
                           WHEN COALESCE(last_error, '') = '' THEN '[DB-MIGRATION] duplicate recurring job pruned'
                           ELSE (last_error || E'\n[DB-MIGRATION] duplicate recurring job pruned')
                       END
                   FROM ranked r
                   WHERE j.id = r.id
                     AND r.rn > 1""",
                (now_jobs,),
            )
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN prune duplicados sys_jobs: {_e}")
        # Dedupe fuerte para recurrentes de alta frecuencia.
        try:
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_jobs_unique_pending_email
                   ON core.sys_jobs(job_type)
                   WHERE job_type = 'EMAIL_POLLING'
                     AND status IN ('PENDING', 'RETRY')"""
            )
            conn.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_sys_jobs_unique_pending_notifications
                   ON core.sys_jobs(job_type)
                   WHERE job_type = 'PROCESS_NOTIFICATIONS'
                     AND status IN ('PENDING', 'RETRY')"""
            )
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN índices únicos recurrentes sys_jobs: {_e}")

        # Ticketera (EPIC 11)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            descripcion TEXT DEFAULT '',
            estado TEXT DEFAULT 'abierto',  -- abierto, en_progreso, resuelto, cerrado
            tipo TEXT DEFAULT 'incidencia',
            severidad TEXT DEFAULT 'media', -- baja, media, alta, critica
            creador_id TEXT NOT NULL,
            asignado_a TEXT,
            vence_at TEXT,                  -- ISO format, nullable
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tks.tickets(estado);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_assignee ON tks.tickets(asignado_a);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_due ON tks.tickets(vence_at);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            is_internal INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_comments_ticket ON tks.ticket_comments(ticket_id);"
        )

        # Migración is_internal
        def _migrate_ticket_comments_section() -> None:
            conn.execute("ALTER TABLE tks.ticket_comments ADD COLUMN IF NOT EXISTS is_internal INTEGER DEFAULT 0")

        _run_guarded_pg_section(conn, "migrate_ticket_comments", _migrate_ticket_comments_section)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_attach_ticket ON tks.ticket_attachments(ticket_id);"
        )

        # --- Ticketera: metadata adicional de adjuntos ---
        def _migrate_ticket_attachments_section() -> None:
            for col_name, col_def in [
                ("size_bytes", "INTEGER"),
                ("content_type", "TEXT"),
                ("sha256", "TEXT"),
            ]:
                conn.execute(f"ALTER TABLE tks.ticket_attachments ADD COLUMN IF NOT EXISTS {col_name} {col_def};")

        _run_guarded_pg_section(conn, "migrate_ticket_attachments", _migrate_ticket_attachments_section)
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attach_sha256 ON tks.ticket_attachments(sha256);")
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN índice idx_attach_sha256: {_e}")

        # --- Ticketera V3: Columnas extras en tickets (migración individual) ---
        _v3_columns = [
            ("codigo",          "TEXT",                True),
            ("categoria",       "TEXT DEFAULT 'general'", True),
            ("origen_email",    "TEXT",                True),
            ("cliente_nombre",  "TEXT",                True),
            ("notify_emails",   "TEXT DEFAULT ''",     False),
            ("prioridad",       "INTEGER DEFAULT 3",   True),
            ("sla_horas",       "INTEGER DEFAULT 72",  True),
            ("email_thread_id", "TEXT",                False),
            ("email_references", "TEXT DEFAULT ''",    False),
            ("resolucion",      "TEXT",                False),
            ("ticket_security_class", "TEXT DEFAULT 'internal'", False),
            ("retention_until", "TEXT",                False),
            ("retention_days_snapshot", "INTEGER DEFAULT 1095", False),
            ("subestado", "TEXT DEFAULT 'recibido'", False),
            ("first_response_at", "TEXT", False),
            ("frt_due_at", "TEXT", False),
            ("ttr_due_at", "TEXT", False),
            ("resolved_at", "TEXT", False),
            ("frt_breached_at", "TEXT", False),
            ("ttr_breached_at", "TEXT", False),
            # --- Ticketera 2.0 (Cliente 360) ---
            ("customer_id", "TEXT", False),       # Link a Laudus/CRM
            ("contact_role", "TEXT", False),      # Gerente, Tecnico, etc.
            # --- Ticketera 2.1 (Papelera blanda) ---
            ("is_trashed", "BOOLEAN DEFAULT FALSE", False),
            ("trashed_at", "TEXT", False),
            ("trashed_by", "TEXT", False),
            ("trash_reason", "TEXT DEFAULT ''", False),
            ("trash_prev_estado", "TEXT", False),
            ("trash_prev_subestado", "TEXT", False),
            ("trash_prev_asignado_a", "TEXT", False),
        ]
        def _migrate_tickets_v3_section() -> None:
            for col_name, col_def, is_critical in _v3_columns:
                try:
                    conn.execute(f"ALTER TABLE tks.tickets ADD COLUMN IF NOT EXISTS {col_name} {col_def};")
                except Exception as _e:
                    if is_critical:
                        # FAIL-FAST: Si es columna crítica para V3, no permitir arranque a medias
                        err_msg = f"[DB-MIGRATION] CRITICAL ERROR: No se pudo crear columna '{col_name}' necesaria para V3. Detalle: {_e}"
                        logger.error("%s", err_msg)
                        raise RuntimeError(err_msg) from _e
                    else:
                        logger.warning("[DB-MIGRATION] WARN columna '{col_name}' ya existe o no se pudo crear: {_e}")

        _run_guarded_pg_section(conn, "migrate_tickets_v3", _migrate_tickets_v3_section)

        # Validar existencia de columnas críticas (Safety Check final)
        # Esto cubre el caso donde "ADD COLUMN IF NOT EXISTS" no falla pero la columna igual no está accesible por alguna razón rara
        try:
            # Intentar leer un ticket dummy o solo verificar schema
            # En SQLite pragma table_info, en PG information_schema. 
            # Para ser agnóstico, hacemos un SELECT dummy
            conn.execute("SELECT codigo, categoria, prioridad, origen_email, cliente_nombre, sla_horas FROM tickets LIMIT 0")
        except Exception as _e:
             raise RuntimeError(f"[DB-MIGRATION] FATAL: Las columnas críticas de V3 no son accesibles tras migración. {_e}")

        for idx_sql in [
            "CREATE INDEX IF NOT EXISTS idx_tickets_codigo ON tks.tickets(codigo);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_categoria ON tks.tickets(categoria);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_prioridad ON tks.tickets(prioridad);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_security_class ON tks.tickets(ticket_security_class);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_trashed ON tks.tickets(is_trashed);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_subestado ON tks.tickets(subestado);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_frt_due ON tks.tickets(frt_due_at);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_ttr_due ON tks.tickets(ttr_due_at);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_list_status_prio_created ON tks.tickets(estado, prioridad, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_list_cat_status_prio_created ON tks.tickets(categoria, estado, prioridad, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_list_assignee_status_prio_created ON tks.tickets(asignado_a, estado, prioridad, created_at DESC);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_list_sev_status_prio_created ON tks.tickets(severidad, estado, prioridad, created_at DESC);",
        ]:
            try:
                conn.execute(idx_sql)
            except Exception as _e:
                logger.warning("[DB-MIGRATION] WARN índice: {_e}")

        # --- Backfill de columnas Workflow/SLA para registros existentes ---
        try:
            conn.execute(
                """UPDATE tickets
                   SET subestado = CASE
                       WHEN estado = 'en_progreso' THEN 'en_progreso'
                       WHEN estado = 'resuelto' THEN 'resuelto'
                       WHEN estado = 'cerrado' THEN 'cerrado'
                       WHEN COALESCE(asignado_a, '') <> '' THEN 'asignado'
                       ELSE 'recibido'
                   END
                   WHERE LOWER(COALESCE(subestado, '')) IN ('nuevo', 'triage')"""
            )
            conn.execute(
                """UPDATE tickets
                   SET subestado = 'cerrado'
                   WHERE estado = 'cerrado'
                     AND LOWER(COALESCE(subestado, '')) <> 'cerrado'"""
            )
            conn.execute(
                """UPDATE tickets
                   SET subestado = 'resuelto'
                   WHERE estado = 'resuelto'
                     AND LOWER(COALESCE(subestado, '')) <> 'resuelto'"""
            )
            conn.execute(
                """UPDATE tickets
                   SET subestado = CASE
                       WHEN estado = 'en_progreso' THEN 'en_progreso'
                       WHEN estado = 'resuelto' THEN 'resuelto'
                       WHEN estado = 'cerrado' THEN 'cerrado'
                       WHEN COALESCE(asignado_a, '') <> '' THEN 'asignado'
                       ELSE 'recibido'
                   END
                   WHERE COALESCE(subestado, '') = ''"""
            )
            conn.execute(
                "UPDATE tickets SET ttr_due_at = COALESCE(ttr_due_at, vence_at) WHERE ttr_due_at IS NULL"
            )
            conn.execute(
                "UPDATE tickets SET resolved_at = COALESCE(resolved_at, updated_at) WHERE estado IN ('resuelto', 'cerrado') AND resolved_at IS NULL"
            )
            conn.execute(
                """UPDATE tickets
                   SET frt_due_at = CASE
                       WHEN severidad = 'critica' THEN (created_at::timestamptz + INTERVAL '15 minutes')::text
                       WHEN severidad = 'alta' THEN (created_at::timestamptz + INTERVAL '30 minutes')::text
                       WHEN severidad = 'media' THEN (created_at::timestamptz + INTERVAL '2 hours')::text
                       ELSE (created_at::timestamptz + INTERVAL '8 hours')::text
                   END
                   WHERE frt_due_at IS NULL"""
            )
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN backfill workflow/sla: {_e}")

        # --- Backfill papelera ---
        try:
            conn.execute(
                "UPDATE tickets SET is_trashed = FALSE WHERE is_trashed IS NULL"
            )
            conn.execute(
                "UPDATE tickets SET trash_reason = '' WHERE trash_reason IS NULL"
            )
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN backfill papelera: {_e}")

        # --- Backfill retención por clase de seguridad ---
        try:
            conn.execute(
                f"""UPDATE tickets
                    SET retention_days_snapshot = CASE
                        WHEN COALESCE(ticket_security_class, 'internal') = 'public' THEN {RETENTION_PUBLIC_DAYS}
                        WHEN COALESCE(ticket_security_class, 'internal') = 'restricted' THEN {RETENTION_RESTRICTED_DAYS}
                        ELSE {RETENTION_INTERNAL_DAYS}
                    END
                    WHERE retention_days_snapshot IS NULL OR retention_days_snapshot <= 0"""
            )
            conn.execute(
                f"""UPDATE tickets
                    SET retention_until = (
                        COALESCE(resolved_at, updated_at)::timestamptz +
                        make_interval(days => CASE
                            WHEN COALESCE(ticket_security_class, 'internal') = 'public' THEN {RETENTION_PUBLIC_DAYS}
                            WHEN COALESCE(ticket_security_class, 'internal') = 'restricted' THEN {RETENTION_RESTRICTED_DAYS}
                            ELSE {RETENTION_INTERNAL_DAYS}
                        END)
                    )::text
                    WHERE estado IN ('resuelto', 'cerrado')
                      AND retention_until IS NULL"""
            )
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN backfill retention: {_e}")

        # --- Ticketera V3: Especialidades de Usuarios ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.user_specialties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            specialty TEXT NOT NULL,
            is_available INTEGER DEFAULT 1,
            current_load INTEGER DEFAULT 0,
            max_load INTEGER DEFAULT 10,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(username, specialty)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_spec_user ON tks.user_specialties(username);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_spec_specialty ON tks.user_specialties(specialty);"
        )

        # --- Ticketera V3: Notificaciones Escalonadas ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'app',
            status TEXT NOT NULL DEFAULT 'pending',
            escalation_level INTEGER DEFAULT 1,
            scheduled_at TEXT NOT NULL,
            sent_at TEXT,
            seen_at TEXT,
            error TEXT DEFAULT '',
            provider TEXT DEFAULT '',
            provider_ref TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            attempt_count INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            next_retry_at TEXT,
            locked_at TEXT,
            updated_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        def _migrate_ticket_notifications_section() -> None:
            for col_name, col_def in [
                ("provider", "TEXT DEFAULT ''"),
                ("provider_ref", "TEXT DEFAULT ''"),
                ("last_error", "TEXT DEFAULT ''"),
                ("attempt_count", "INTEGER DEFAULT 0"),
                ("max_attempts", "INTEGER DEFAULT 3"),
                ("next_retry_at", "TEXT"),
                ("locked_at", "TEXT"),
                ("updated_at", "TEXT"),
            ]:
                conn.execute(f"ALTER TABLE tks.ticket_notifications ADD COLUMN IF NOT EXISTS {col_name} {col_def};")

        _run_guarded_pg_section(conn, "migrate_ticket_notifications", _migrate_ticket_notifications_section)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_ticket ON tks.ticket_notifications(ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_user ON tks.ticket_notifications(user_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_status ON tks.ticket_notifications(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_sched ON tks.ticket_notifications(scheduled_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_status_sched ON tks.ticket_notifications(status, scheduled_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_status_retry ON tks.ticket_notifications(status, next_retry_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_channel_status ON tks.ticket_notifications(channel, status);"
        )

        try:
            conn.execute(
                f"""UPDATE ticket_notifications
                    SET attempt_count = COALESCE(attempt_count, 0),
                        max_attempts = CASE
                            WHEN COALESCE(max_attempts, 0) <= 0 THEN {_env_int('CHANNELS_MAX_ATTEMPTS', 3, 1, 20)}
                            ELSE max_attempts
                        END,
                        next_retry_at = COALESCE(next_retry_at, scheduled_at),
                        updated_at = COALESCE(updated_at, created_at),
                        last_error = COALESCE(NULLIF(last_error, ''), COALESCE(error, '')),
                        provider = COALESCE(provider, '')
                    WHERE provider IS NULL OR attempt_count IS NULL"""
            )
        except Exception as _e:
            logger.warning("[DB-MIGRATION] WARN backfill ticket_notifications: {_e}")

        # --- PMO (Proyectos y Bitacora) ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pmo.pmo_proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cliente_nombre TEXT,
            presupuesto_venta REAL DEFAULT 0,
            fecha_inicio TEXT,
            fecha_fin_estimada TEXT,
            estado TEXT DEFAULT 'borrador',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP::text,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP::text
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pmo_proyectos_estado ON pmo.pmo_proyectos(estado);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS pmo.pmo_bitacora_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER NOT NULL,
            origen TEXT DEFAULT 'manual',
            contenido_raw TEXT,
            estado_procesamiento TEXT DEFAULT 'pendiente',
            resumen_ia TEXT,
            acciones_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP::text,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP::text,
            FOREIGN KEY(proyecto_id) REFERENCES pmo_proyectos(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pmo_bitacora_proyecto ON pmo.pmo_bitacora_ia(proyecto_id);"
        )


        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_notification_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL DEFAULT 0,
            attempt_type TEXT NOT NULL DEFAULT 'dispatch',
            channel TEXT NOT NULL,
            provider TEXT DEFAULT '',
            adapter_mode TEXT DEFAULT '',
            status TEXT NOT NULL,
            provider_ref TEXT DEFAULT '',
            http_status INTEGER,
            latency_ms INTEGER,
            error TEXT DEFAULT '',
            idempotency_key TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(notification_id) REFERENCES ticket_notifications(id) ON DELETE CASCADE
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_attempts_notif ON tks.ticket_notification_attempts(notification_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_attempts_created ON tks.ticket_notification_attempts(created_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_attempts_status ON tks.ticket_notification_attempts(status);"
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_tk_notif_attempts_idem
               ON tks.ticket_notification_attempts(notification_id, attempt_type, idempotency_key)
               WHERE idempotency_key <> ''"""
        )

        # --- Ticketera V3: Historial de Emails ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            from_addr TEXT,
            to_addr TEXT,
            cc_addrs TEXT DEFAULT '',
            bcc_addrs TEXT DEFAULT '',
            subject TEXT,
            body_html TEXT,
            attachments_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_emails_ticket ON tks.ticket_emails(ticket_id);"
        )
        def _migrate_ticket_emails_section() -> None:
            conn.execute("ALTER TABLE tks.ticket_emails ADD COLUMN IF NOT EXISTS idempotency_key TEXT;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tk_emails_idempotency ON tks.ticket_emails(idempotency_key);")
            conn.execute("ALTER TABLE tks.ticket_emails ADD COLUMN IF NOT EXISTS cc_addrs TEXT DEFAULT '';")
            conn.execute("ALTER TABLE tks.ticket_emails ADD COLUMN IF NOT EXISTS bcc_addrs TEXT DEFAULT '';")

        _run_guarded_pg_section(conn, "migrate_ticket_emails", _migrate_ticket_emails_section)

        # --- Ticketera V3: Borradores de respuesta por correo ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_email_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            to_addr TEXT DEFAULT '',
            cc_addrs TEXT DEFAULT '',
            bcc_addrs TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            body_text TEXT DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            lock_owner TEXT,
            lock_token_hash TEXT,
            lock_expires_at TEXT,
            created_by TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            sent_by TEXT,
            sent_email_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            sent_at TEXT,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(sent_email_id) REFERENCES ticket_emails(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_drafts_ticket ON tks.ticket_email_drafts(ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_drafts_status ON tks.ticket_email_drafts(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_drafts_lock_expires ON tks.ticket_email_drafts(lock_expires_at);"
        )
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_tk_email_drafts_active
               ON tks.ticket_email_drafts(ticket_id)
               WHERE status = 'active'"""
        )
        def _migrate_ticket_email_drafts_section() -> None:
            conn.execute("ALTER TABLE tks.ticket_email_drafts ADD COLUMN IF NOT EXISTS cc_addrs TEXT DEFAULT '';")
            conn.execute("ALTER TABLE tks.ticket_email_drafts ADD COLUMN IF NOT EXISTS bcc_addrs TEXT DEFAULT '';")

        _run_guarded_pg_section(conn, "migrate_ticket_email_drafts", _migrate_ticket_email_drafts_section)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_email_draft_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            content_type TEXT DEFAULT 'application/octet-stream',
            sha256 TEXT DEFAULT '',
            uploaded_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_email_id INTEGER,
            FOREIGN KEY(draft_id) REFERENCES ticket_email_drafts(id) ON DELETE CASCADE,
            FOREIGN KEY(sent_email_id) REFERENCES ticket_emails(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_draft_att_draft ON tks.ticket_email_draft_attachments(draft_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_draft_att_sent_email ON tks.ticket_email_draft_attachments(sent_email_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_draft_att_sha256 ON tks.ticket_email_draft_attachments(sha256);"
        )

        # --- Workflow de transiciones por ticket ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            from_subestado TEXT,
            to_subestado TEXT NOT NULL,
            actor TEXT NOT NULL,
            reason TEXT DEFAULT '',
            idempotency_key TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_transitions_ticket ON tks.ticket_transitions(ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_transitions_created ON tks.ticket_transitions(created_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_transitions_idem ON tks.ticket_transitions(idempotency_key);"
        )

        # --- Asociacion explicita email -> cliente para Ticketera ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_config_client_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_tk_client_emails_email
               ON tks.ticket_config_client_emails(email);"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_client_emails_customer_id ON tks.ticket_config_client_emails(customer_id);"
        )

        # --- Routing por correo/dominio para Ticketera ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_config_email_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_type TEXT NOT NULL,
            match_value TEXT NOT NULL,
            categoria TEXT NOT NULL,
            customer_id TEXT,
            customer_name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_tk_email_routes_match
               ON tks.ticket_config_email_routes(match_type, match_value);"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_routes_active ON tks.ticket_config_email_routes(is_active);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_email_routes_categoria ON tks.ticket_config_email_routes(categoria);"
        )

        def _migrate_email_routes_section() -> None:
            conn.execute("ALTER TABLE tks.ticket_config_email_routes ADD COLUMN IF NOT EXISTS customer_id TEXT")
            conn.execute("ALTER TABLE tks.ticket_config_email_routes ADD COLUMN IF NOT EXISTS customer_name TEXT")

        _run_guarded_pg_section(conn, "migrate_email_routes", _migrate_email_routes_section)

        # --- Aprobaciones de cambios ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            step INTEGER NOT NULL,
            approver TEXT NOT NULL,
            decision TEXT NOT NULL,
            decision_note TEXT DEFAULT '',
            idempotency_key TEXT,
            decided_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_approvals_ticket ON tks.ticket_approvals(ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_approvals_step ON tks.ticket_approvals(step);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_approvals_decided ON tks.ticket_approvals(decided_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_approvals_idem ON tks.ticket_approvals(idempotency_key);"
        )

        # --- Reglas de automatización Ticketera ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_automation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            is_active INTEGER DEFAULT 1,
            match_json TEXT NOT NULL DEFAULT '{}',
            action_json TEXT NOT NULL DEFAULT '{}',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_auto_rules_active ON tks.ticket_automation_rules(is_active);"
        )

        # --- Evidencias para trazabilidad ISO ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS core.evidence_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_id TEXT NOT NULL,
            artifact_ref TEXT NOT NULL,
            owner TEXT NOT NULL,
            integrity_hash TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_evidence_control ON core.evidence_events(control_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_evidence_created ON core.evidence_events(created_at);"
        )
        conn.execute(
            "ALTER TABLE core.evidence_events ADD COLUMN IF NOT EXISTS chain_prev_hash TEXT DEFAULT ''"
        )
        conn.execute(
            "ALTER TABLE core.evidence_events ADD COLUMN IF NOT EXISTS chain_hash TEXT DEFAULT ''"
        )
        conn.execute(
            f"ALTER TABLE core.evidence_events ADD COLUMN IF NOT EXISTS chain_algo TEXT DEFAULT '{CHAIN_ALGO}'"
        )
        conn.execute(
            f"ALTER TABLE core.evidence_events ADD COLUMN IF NOT EXISTS chain_version INTEGER DEFAULT {CHAIN_VERSION}"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_evidence_chain_hash ON core.evidence_events(chain_hash);"
        )

        # --- Compliance Core ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tks.ticket_legal_holds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            case_ref TEXT DEFAULT '',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            released_by TEXT DEFAULT '',
            released_at TEXT,
            release_note TEXT DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_legal_holds_ticket ON tks.ticket_legal_holds(ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_legal_holds_active ON tks.ticket_legal_holds(is_active);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.compliance_export_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL DEFAULT 'both',
            from_ts TEXT,
            to_ts TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            actor TEXT NOT NULL,
            idempotency_key TEXT DEFAULT '',
            artifact_dir TEXT DEFAULT '',
            manifest_path TEXT DEFAULT '',
            artifact_hash TEXT DEFAULT '',
            counts_json TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compliance_export_status ON ops.compliance_export_runs(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compliance_export_created ON ops.compliance_export_runs(created_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compliance_export_idem ON ops.compliance_export_runs(idempotency_key);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.compliance_purge_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dry_run INTEGER NOT NULL DEFAULT 0,
            as_of TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            actor TEXT NOT NULL,
            idempotency_key TEXT DEFAULT '',
            summary_json TEXT DEFAULT '{}',
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compliance_purge_status ON ops.compliance_purge_runs(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compliance_purge_created ON ops.compliance_purge_runs(created_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compliance_purge_idem ON ops.compliance_purge_runs(idempotency_key);"
        )

        # Backfill hash-chain previo a activar triggers append-only.
        def _chain_backfill_section() -> None:
            audit_payload_fields = (
                "timestamp",
                "actor",
                "action",
                "target",
                "ip_address",
                "severity",
                "metadata_json",
            )
            evidence_payload_fields = (
                "control_id",
                "artifact_ref",
                "owner",
                "integrity_hash",
                "metadata_json",
                "created_at",
            )

            audit_has_triggers = _has_append_only_triggers(conn, "audit_logs")
            audit_consistent = _chain_table_is_consistent(conn, "audit_logs", audit_payload_fields)
            if not audit_consistent:
                logger.warning("[DB-MIGRATION] WARN audit_logs chain inconsistente; se forzará re-backfill.")
                if audit_has_triggers:
                    _drop_append_only_triggers(conn, "audit_logs")
                _backfill_chain_table(
                    conn,
                    "audit_logs",
                    audit_payload_fields,
                )
            elif audit_has_triggers:
                logger.info("[DB-MIGRATION] INFO skip hash-chain backfill audit_logs (append-only activo y consistente)")
            else:
                _backfill_chain_table(
                    conn,
                    "audit_logs",
                    audit_payload_fields,
                )

            evidence_has_triggers = _has_append_only_triggers(conn, "evidence_events")
            evidence_consistent = _chain_table_is_consistent(conn, "evidence_events", evidence_payload_fields)
            if not evidence_consistent:
                logger.warning("[DB-MIGRATION] WARN evidence_events chain inconsistente; se forzará re-backfill.")
                if evidence_has_triggers:
                    _drop_append_only_triggers(conn, "evidence_events")
                _backfill_chain_table(
                    conn,
                    "evidence_events",
                    evidence_payload_fields,
                )
            elif evidence_has_triggers:
                logger.info("[DB-MIGRATION] INFO skip hash-chain backfill evidence_events (append-only activo y consistente)")
            else:
                _backfill_chain_table(
                    conn,
                    "evidence_events",
                    evidence_payload_fields,
                )

        _run_guarded_pg_section(conn, "hash_chain_backfill", _chain_backfill_section)

        # Inmutabilidad en PostgreSQL: bloquear UPDATE/DELETE.
        _run_guarded_pg_section(
            conn,
            "append_only_triggers",
            lambda: (
                _create_append_only_triggers(conn, "audit_logs"),
                _create_append_only_triggers(conn, "evidence_events"),
            ),
        )

        # --- Importaciones Jira para trazabilidad de migración ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.jira_import_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_by TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_import_runs_created ON ops.jira_import_runs(created_at);"
        )

        # --- Paralelo Jira + MONSTRUO ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.jira_issue_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jira_issue_key TEXT NOT NULL UNIQUE,
            jira_updated_at TEXT NOT NULL,
            monstruo_ticket_id INTEGER NOT NULL,
            sync_status TEXT NOT NULL DEFAULT 'synced',
            last_sync_at TEXT NOT NULL,
            last_error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(monstruo_ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_issue_map_ticket ON ops.jira_issue_map(monstruo_ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_issue_map_status ON ops.jira_issue_map(sync_status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_issue_map_key_updated ON ops.jira_issue_map(jira_issue_key, jira_updated_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_issue_map_sync_at ON ops.jira_issue_map(last_sync_at);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.jira_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL, -- bootstrap | delta
            actor TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running', -- running | completed | failed | completed_with_errors
            context_json TEXT NOT NULL DEFAULT '{}',
            counts_json TEXT NOT NULL DEFAULT '{}',
            error_summary TEXT DEFAULT '',
            cursor_before TEXT DEFAULT '',
            cursor_after TEXT DEFAULT '',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_sync_runs_type_started ON ops.jira_sync_runs(run_type, started_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_sync_runs_status ON ops.jira_sync_runs(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_sync_runs_created ON ops.jira_sync_runs(created_at);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.jira_sync_cursor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cursor_name TEXT NOT NULL UNIQUE,
            cursor_value TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jira_sync_cursor_name ON ops.jira_sync_cursor(cursor_name);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.parallel_kpi_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL DEFAULT 'parallel_daily',
            total_jira_open INTEGER NOT NULL DEFAULT 0,
            total_monstruo_open INTEGER NOT NULL DEFAULT 0,
            sev1_open INTEGER NOT NULL DEFAULT 0,
            sla_compliance_pct REAL NOT NULL DEFAULT 0,
            mismatch_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            failed_sync_runs INTEGER NOT NULL DEFAULT 0,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parallel_kpi_date ON ops.parallel_kpi_daily(snapshot_date);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.parallel_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision TEXT NOT NULL, -- go | no_go
            decided_at TEXT NOT NULL,
            decided_by TEXT NOT NULL,
            signers_json TEXT NOT NULL DEFAULT '[]',
            rationale TEXT NOT NULL DEFAULT '',
            evidence_refs_json TEXT NOT NULL DEFAULT '[]',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parallel_decisions_at ON ops.parallel_decisions(decided_at);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_parallel_decisions_decision ON ops.parallel_decisions(decision);"
        )

        # Sales ERP (EPIC 05)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL,
            type TEXT NOT NULL,         -- FACTURA, BOLETA, NC, ND
            status TEXT DEFAULT 'DRAFT', -- DRAFT, ISSUED, PAID, VOID
            total_net REAL DEFAULT 0.0,
            total_tax REAL DEFAULT 0.0,
            total_final REAL DEFAULT 0.0,
            ref_id INTEGER,             -- FK to invoices (for NC/ND)
            external_id TEXT,           -- ID en Laudus
            issuer_id TEXT NOT NULL,
            issued_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_invoices_cust ON erp.invoices(customer_id);"
        )

        # CRM (EPIC 06)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            fantasy_name TEXT,
            address TEXT,
            city TEXT,
            category TEXT,
            email TEXT,
            phone TEXT,
            external_id TEXT UNIQUE,
            is_active BOOLEAN DEFAULT 1,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_customers_ext ON erp.customers(external_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_customers_name ON erp.customers(name);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS crm.crm_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            type TEXT DEFAULT 'nota', -- nota, llamada, correo
            content TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_crm_interactions_cust ON crm.crm_interactions(customer_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.collection_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT NOT NULL, -- Link to invoices.customer_id (Laudus ID)
            action_type TEXT NOT NULL, -- CALL, EMAIL, WHATSAPP, NOTE
            notes TEXT DEFAULT '',
            committed_amount REAL DEFAULT 0,
            commitment_date TEXT, -- ISO Date
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_coll_actions_cust ON erp.collection_actions(customer_id);"
        )

        # Bodega (EPIC 09)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            price REAL DEFAULT 0.0,
            price_currency TEXT DEFAULT 'CLP', -- CLP | UF
            price_parity REAL DEFAULT 1.0,     -- Paridad a moneda principal si aplica (Laudus)
            cost REAL DEFAULT 0.0,
            stock_current INTEGER DEFAULT 0,
            is_service BOOLEAN DEFAULT 0,
            external_id TEXT, -- ID en Parrotfy/Laudus
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON bodega.products(sku);")

        def _migrate_products_section() -> None:
            conn.execute("ALTER TABLE bodega.products ADD COLUMN IF NOT EXISTS price_currency TEXT DEFAULT 'CLP';")
            conn.execute("ALTER TABLE bodega.products ADD COLUMN IF NOT EXISTS price_parity REAL DEFAULT 1.0;")

        _run_guarded_pg_section(conn, "migrate_products", _migrate_products_section)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            product_sku TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY(invoice_id) REFERENCES invoices(id),
            FOREIGN KEY(product_sku) REFERENCES products(sku)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inv_items_inv ON erp.invoice_items(invoice_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL, -- Positivo (entrada) o Negativo (salida)
            type TEXT NOT NULL,        -- PURCHASE, SALE, ADJUSTMENT, SYNC
            reference TEXT DEFAULT '', -- Nro Factura, Ticket ID, etc.
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_movements_prod ON bodega.inventory_movements(product_id);"
        )

        # -----------------------------
        # Parrotfy Staging (Raw Sync)
        # -----------------------------
        # Invoices
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.parrotfy_invoices (
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_number ON erp.parrotfy_invoices(invoice_number);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_customer ON erp.parrotfy_invoices(customer_id);"
        )

        # Payments
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.parrotfy_payments (
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_pay_invoice ON erp.parrotfy_payments(parrotfy_invoice_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_pay_date ON erp.parrotfy_payments(payment_date);"
        )

        # Inventory
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.parrotfy_inventory (
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_prod ON bodega.parrotfy_inventory(product_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_date ON bodega.parrotfy_inventory(date);"
        )

        # -----------------------------
        # Phase 3: Snapshots & Conciliation
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.parrotfy_stock_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            product_id TEXT,
            sku TEXT,
            quantity REAL,
            raw_json TEXT,
            created_at TEXT
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_stock_snap ON bodega.parrotfy_stock_snapshot(snapshot_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.laudus_stock_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id TEXT NOT NULL,
            product_id TEXT,
            sku TEXT,
            quantity REAL,
            raw_json TEXT,
            created_at TEXT
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_lau_stock_snap ON bodega.laudus_stock_snapshot(snapshot_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.conciliacion_bodega_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            status TEXT,
            total_items INTEGER DEFAULT 0,
            diff_count INTEGER DEFAULT 0,
            details_json TEXT,
            started_at TEXT,
            completed_at TEXT
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.conciliacion_bodega_diffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            sku TEXT,
            laudus_qty REAL,
            parrotfy_qty REAL,
            diff REAL,
            diff_type TEXT,
            created_at TEXT
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_concil_diff_run ON bodega.conciliacion_bodega_diffs(run_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ia.ia_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            severity TEXT,
            summary TEXT,
            payload_json TEXT,
            created_at TEXT
        );
        """)

        # -----------------------------
        # Phase 4 (Hito Cache): Snapshots Headers & Training
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bodega.stock_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proveedor TEXT NOT NULL,      -- 'parrotfy' | 'laudus'
            creado_ts TEXT NOT NULL,      -- ISO
            total_items INTEGER DEFAULT 0,
            ok INTEGER DEFAULT 0,         -- 1=Exito, 0=Fallo
            mensaje TEXT DEFAULT '',
            payload_json TEXT DEFAULT '', -- Cache completo para UI
            hash TEXT DEFAULT ''
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_snap_prov ON bodega.stock_snapshots(proveedor);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_snap_ts ON bodega.stock_snapshots(creado_ts);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ia.ia_bodega_casos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creado_ts TEXT NOT NULL,
            proveedor_stock TEXT DEFAULT '',
            snapshot_id INTEGER,
            input_json TEXT DEFAULT '',
            output_json TEXT DEFAULT '',
            modelo TEXT DEFAULT '',
            modo TEXT DEFAULT '', -- 'local'|'heuristico'
            ok INTEGER DEFAULT 0,
            mensaje TEXT DEFAULT ''
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ia_casos_ts ON ia.ia_bodega_casos(creado_ts);"
        )

        # -----------------------------
        # Bridge & AI
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ops.bridge_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT DEFAULT 'jarvis',
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            kind TEXT NOT NULL, -- status|result|request|proposal
            title TEXT DEFAULT '',
            body TEXT DEFAULT '',
            payload_json TEXT DEFAULT '{}',
            requires_approval INTEGER DEFAULT 0, -- boolean 0/1
            approval_status TEXT DEFAULT 'na', -- pending|approved|rejected|na
            created_at TEXT DEFAULT '',
            decided_at TEXT DEFAULT '',
            decided_by TEXT DEFAULT ''
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bridge_to ON ops.bridge_messages(to_agent);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bridge_approval ON ops.bridge_messages(approval_status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bridge_thread ON ops.bridge_messages(thread_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ia.ai_event_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            bridge_message_id INTEGER,
            payload_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL,
            processed_at TEXT DEFAULT '',
            error TEXT DEFAULT ''
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ia.ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            recommended_actions_json TEXT DEFAULT '[]',
            customer_message_draft TEXT DEFAULT '',
            requires_approval INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            raw_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            approved_at TEXT DEFAULT '',
            approved_by TEXT DEFAULT '',
            FOREIGN KEY (event_id) REFERENCES ai_event_queue(id)
        );
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_event_status ON ia.ai_event_queue(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_event_kind ON ia.ai_event_queue(kind);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_rec_status ON ia.ai_recommendations(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_rec_event ON ia.ai_recommendations(event_id);"
        )

        # -----------------------------
        # EPIC 07: Bank Reconciliation
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            laudus_account_id INTEGER UNIQUE NOT NULL, -- ID contable en Laudus (ej: 8)
            account_number TEXT DEFAULT '',            -- Nro Cuenta Real
            bank_name TEXT DEFAULT '',                 -- Banco Santander, Chile, etc.
            currency TEXT DEFAULT 'CLP',
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT ''
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bank_acc_laudus ON erp.bank_accounts(laudus_account_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.bank_statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_account_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            period_start TEXT DEFAULT '',
            period_end TEXT DEFAULT '',
            total_deposit REAL DEFAULT 0,
            total_withdrawal REAL DEFAULT 0,
            status TEXT DEFAULT 'pending', -- pending, processed, reconciled
            FOREIGN KEY(bank_account_id) REFERENCES bank_accounts(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bs_account ON erp.bank_statements(bank_account_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.bank_statement_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id INTEGER NOT NULL,
            date TEXT NOT NULL,          -- Fecha movimiento
            description TEXT DEFAULT '', -- Glosa
            document_number TEXT DEFAULT '',
            amount REAL NOT NULL,        -- Positivo (abono) / Negativo (cargo)
            balance REAL DEFAULT 0,      -- Saldo parcial (si viene)
            hash TEXT NOT NULL,          -- Dedup: sha256(date+amount+desc+doc)
            reconciled_at TEXT,          -- Null = Pendiente
            FOREIGN KEY(statement_id) REFERENCES bank_statements(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bsl_statement ON erp.bank_statement_lines(statement_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bsl_hash ON erp.bank_statement_lines(hash);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bsl_date ON erp.bank_statement_lines(date);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS erp.bank_reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_line_id INTEGER NOT NULL,
            match_type TEXT NOT NULL,    -- 'payment', 'ledger', 'manual'
            match_id TEXT NOT NULL,      -- ID en tabla destino (laudus_payment_id, etc.)
            confidence REAL DEFAULT 1.0, -- 1.0 = Manual, <1.0 = Auto
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL,    -- User or 'system'
            notes TEXT DEFAULT '',
            FOREIGN KEY(statement_line_id) REFERENCES bank_statement_lines(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_br_line ON erp.bank_reconciliations(statement_line_id);"
        )

        # -----------------------------
        # EPIC 21: Automatic Billing (Rules)
        # -----------------------------
        def _migrate_cat_billing_section() -> None:
            # Catalogo: multi-categoria (m:n)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat.cat_categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL,
                nombre TEXT NOT NULL,
                parent_id INTEGER,
                activo INTEGER NOT NULL DEFAULT 1,
                is_hidden INTEGER DEFAULT 0,
                UNIQUE(tipo, nombre, parent_id),
                FOREIGN KEY(parent_id) REFERENCES cat_categorias(id) ON DELETE SET NULL
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_categorias_parent ON cat.cat_categorias(parent_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_categorias_tipo ON cat.cat_categorias(tipo);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat.cat_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria_id INTEGER,
                unidad TEXT DEFAULT '',
                sku_canonico TEXT DEFAULT '',
                ean TEXT DEFAULT '',
                marca TEXT DEFAULT '',
                image_url TEXT DEFAULT '',
                atributos_json TEXT DEFAULT '{}',
                activo INTEGER NOT NULL DEFAULT 1,
                creado_at TEXT NOT NULL,
                actualizado_at TEXT NOT NULL,
                FOREIGN KEY(categoria_id) REFERENCES cat_categorias(id) ON DELETE SET NULL
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_items_categoria ON cat.cat_items(categoria_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_items_sku ON cat.cat_items(sku_canonico);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat.cat_match_queue (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fuente TEXT NOT NULL,
              fuente_item_id TEXT NOT NULL,
              raw_nombre TEXT,
              raw_sku TEXT,
              raw_ean TEXT,
              raw_marca TEXT,
              suggested_item_id INTEGER,
              score REAL DEFAULT 0.0,
              estado TEXT DEFAULT 'pendiente', -- pendiente, aprobado, rechazado
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(fuente, fuente_item_id)
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_mq_score ON cat.cat_match_queue(score);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_mq_estado ON cat.cat_match_queue(estado);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat.cat_fuente_map (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fuente TEXT NOT NULL,
              fuente_item_id TEXT NOT NULL,
              item_id INTEGER NOT NULL,
              confianza REAL NOT NULL DEFAULT 1.0,
              metodo_match TEXT NOT NULL DEFAULT 'manual',
              last_seen_at TEXT,
              meta_json TEXT DEFAULT '{}',
              candidato_item_id INTEGER,
              candidato_confianza REAL DEFAULT 0.0,
              UNIQUE(fuente, fuente_item_id),
              FOREIGN KEY(item_id) REFERENCES cat_items(id) ON DELETE CASCADE
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_fuente_map_fuente ON cat.cat_fuente_map(fuente);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat.cat_item_categories (
                item_id INTEGER NOT NULL,
                categoria_id INTEGER NOT NULL,
                created_at TEXT DEFAULT '',
                UNIQUE(item_id, categoria_id),
                FOREIGN KEY(item_id) REFERENCES cat_items(id),
                FOREIGN KEY(categoria_id) REFERENCES cat_categorias(id)
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_item_categories_item ON cat.cat_item_categories(item_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_item_categories_cat ON cat.cat_item_categories(categoria_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.billing_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                description TEXT DEFAULT '',
                currency TEXT DEFAULT 'CLP',
                uf_rule TEXT DEFAULT 'VALOR_DIA',
                uf_custom_value REAL DEFAULT 0,
                base_amount REAL DEFAULT 0,
                frequency_months INTEGER DEFAULT 1,
                day_of_month INTEGER DEFAULT 5,
                next_billing_date TEXT,
                last_billed_at TEXT,
                is_active INTEGER DEFAULT 1,
                auto_issue INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_billing_rules_cust ON erp.billing_rules(customer_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_billing_rules_next ON erp.billing_rules(next_billing_date);"
            )

            # -----------------------------
            # EPIC 22: Templates / Billing Profiles / Dispatch Tracking
            # -----------------------------
            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.invoice_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                customer_id TEXT, -- Laudus customerId (optional, NULL = global)
                currency TEXT NOT NULL DEFAULT 'CLP', -- CLP | UF
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoice_templates_customer ON erp.invoice_templates(customer_id);"
            )
            # Backfill columns if DB existed before
            conn.execute("ALTER TABLE erp.invoice_templates ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'CLP';")
            conn.execute("ALTER TABLE erp.invoice_templates ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1;")
            conn.execute("ALTER TABLE erp.invoice_templates ADD COLUMN IF NOT EXISTS created_by TEXT DEFAULT '';")
            conn.execute("ALTER TABLE erp.invoice_templates ADD COLUMN IF NOT EXISTS created_at TEXT DEFAULT '';")
            conn.execute("ALTER TABLE erp.invoice_templates ADD COLUMN IF NOT EXISTS updated_at TEXT DEFAULT '';")

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.invoice_template_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                description TEXT DEFAULT '',
                quantity REAL NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(template_id) REFERENCES invoice_templates(id) ON DELETE CASCADE
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_template_items_template ON erp.invoice_template_items(template_id);"
            )
            # Backfill columns if DB existed before
            conn.execute("ALTER TABLE erp.invoice_template_items ADD COLUMN IF NOT EXISTS sku TEXT;")
            conn.execute("ALTER TABLE erp.invoice_template_items ADD COLUMN IF NOT EXISTS created_at TEXT DEFAULT '';")

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.billing_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,          -- Laudus customerId
                name TEXT NOT NULL,                 -- Ej: 'Soporte TI - Proyecto X'
                template_id INTEGER,                -- invoice_templates.id
                currency TEXT NOT NULL DEFAULT 'CLP', -- CLP | UF (override)
                uf_rule TEXT DEFAULT 'VALOR_DIA',    -- VALOR_DIA | VALOR_FIJO | VALOR_CONTRATO | ...
                uf_custom_value REAL DEFAULT 0,
                frequency_months INTEGER DEFAULT 1,
                day_of_month INTEGER DEFAULT 5,
                next_billing_date TEXT,
                last_billed_at TEXT,
                auto_issue INTEGER DEFAULT 0,
                doc_type_id INTEGER,                -- Laudus docTypeId
                term_id INTEGER,                    -- Laudus termId (optional)
                purchase_order_required INTEGER DEFAULT 0,
                purchase_order_number TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_by TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(template_id) REFERENCES invoice_templates(id)
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_billing_profiles_customer ON erp.billing_profiles(customer_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_billing_profiles_next ON erp.billing_profiles(next_billing_date);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS crm.customer_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,              -- Laudus customerId
                external_contact_id TEXT,               -- Laudus contactId (optional)
                first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '',
                email TEXT DEFAULT '',
                department TEXT DEFAULT '',
                project TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                raw_json TEXT DEFAULT '',
                synced_at TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(customer_id, external_contact_id)
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_customer_contacts_customer ON crm.customer_contacts(customer_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.billing_profile_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'TO', -- TO | CC
                created_at TEXT NOT NULL,
                UNIQUE(profile_id, contact_id, role),
                FOREIGN KEY(profile_id) REFERENCES billing_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY(contact_id) REFERENCES customer_contacts(id) ON DELETE CASCADE
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_profile_recipients_profile ON erp.billing_profile_recipients(profile_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.invoice_dispatches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                profile_id INTEGER,
                channel TEXT NOT NULL DEFAULT 'email',
                status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING | SENT | FAILED | DELIVERED
                to_emails TEXT DEFAULT '',
                cc_emails TEXT DEFAULT '',
                subject TEXT DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sent_at TEXT,
                delivered_at TEXT,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
                FOREIGN KEY(profile_id) REFERENCES billing_profiles(id)
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoice_dispatches_invoice ON erp.invoice_dispatches(invoice_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.invoice_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT DEFAULT '{}',
                created_by TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoice_events_invoice ON erp.invoice_events(invoice_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS erp.uf_rates (
                uf_date TEXT PRIMARY KEY, -- YYYY-MM-DD
                uf_value REAL NOT NULL,
                source TEXT DEFAULT 'mindicador',
                fetched_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uf_rates_date ON erp.uf_rates(uf_date);")

        _run_guarded_pg_section(conn, "migrate_cat_billing", _migrate_cat_billing_section)

        # -----------------------------
        # EPIC: Fundación (Planificación)
        # -----------------------------
        def _migrate_fundacion_section() -> None:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS fundacion.fundacion_tareas (
                id SERIAL PRIMARY KEY,
                titulo TEXT NOT NULL,
                descripcion TEXT,
                fecha_inicio TIMESTAMP NOT NULL,
                fecha_fin TIMESTAMP,
                asignado_a TEXT, -- username del ejecutivo
                creado_by TEXT,
                sede TEXT,
                estado TEXT DEFAULT 'pendiente', -- pendiente, en_progreso, completado, cancelado
                color TEXT DEFAULT '#4facfe', -- Para visualización en calendario
                reporte TEXT, -- Feedback de la monitora
                imprevistos TEXT, -- Problemas surgidos
                reportado_at TIMESTAMP, -- Momento del reporte
                curso TEXT,
                categoria TEXT,
                categoria_madre TEXT,
                subcategoria TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Migraciones incrementales para tablas existentes
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS sede TEXT;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS reporte TEXT;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS imprevistos TEXT;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS reportado_at TIMESTAMP;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS curso TEXT;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS categoria TEXT;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS categoria_madre TEXT;")
            conn.execute("ALTER TABLE fundacion.fundacion_tareas ADD COLUMN IF NOT EXISTS subcategoria TEXT;")
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_asignado ON fundacion.fundacion_tareas(asignado_a);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_fecha ON fundacion.fundacion_tareas(fecha_inicio);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_sede ON fundacion.fundacion_tareas(sede);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fundacion_tareas_curso ON fundacion.fundacion_tareas(curso);")

        _run_guarded_pg_section(conn, "migrate_fundacion", _migrate_fundacion_section)

        def _migrate_gta_section() -> None:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.tareas (
                id          SERIAL PRIMARY KEY,
                titulo      TEXT NOT NULL,
                descripcion TEXT,
                fecha_inicio TIMESTAMP NOT NULL,
                fecha_fin    TIMESTAMP,
                asignado_a   TEXT,
                creado_by    TEXT,
                prioridad    TEXT DEFAULT 'media',   -- baja, media, alta
                tipo         TEXT,
                estado       TEXT DEFAULT 'pendiente', -- pendiente, en_progreso, completado, bloqueado, cancelado
                tags         TEXT DEFAULT '[]',
                reporte      TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.comentarios (
                id        SERIAL PRIMARY KEY,
                tarea_id  INTEGER NOT NULL REFERENCES gta.tareas(id) ON DELETE CASCADE,
                autor     TEXT NOT NULL,
                texto     TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_tareas_estado    ON gta.tareas(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_tareas_asignado  ON gta.tareas(asignado_a);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_tareas_fecha     ON gta.tareas(fecha_inicio);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_comentarios_tarea ON gta.comentarios(tarea_id);")

        _run_guarded_pg_section(conn, "migrate_gta", _migrate_gta_section)

        def _migrate_gta_v2_section() -> None:
            # Catálogo de procesos
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.procesos (
                id                SERIAL PRIMARY KEY,
                nombre            TEXT NOT NULL,
                area              TEXT NOT NULL,
                descripcion       TEXT,
                sla_horas         INTEGER,
                icono             TEXT,
                pasos_definicion  TEXT DEFAULT '[]',   -- JSON: ["paso 1", "paso 2"]
                campos_formulario TEXT DEFAULT '[]',   -- JSON: [{"key":"x","label":"X","type":"text"}]
                estado            TEXT DEFAULT 'activo',
                creado_por        TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Solicitudes enlazadas a procesos
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.solicitudes (
                id           SERIAL PRIMARY KEY,
                proceso_id   INTEGER REFERENCES gta.procesos(id) ON DELETE SET NULL,
                titulo       TEXT NOT NULL,
                descripcion  TEXT,
                area         TEXT NOT NULL,
                prioridad    TEXT DEFAULT 'media',      -- baja, media, alta
                estado       TEXT DEFAULT 'pendiente',  -- pendiente, en_progreso, completado, bloqueado, cancelado
                creado_por   TEXT,
                asignado_a   TEXT,
                pasos_estado TEXT DEFAULT '[]',         -- JSON: [{"completado":false,"bloqueado":false}]
                campos_extra TEXT DEFAULT '{}',         -- JSON con valores de campos_formulario
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Quiebres de proceso
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.quiebres (
                id               SERIAL PRIMARY KEY,
                descripcion      TEXT NOT NULL,
                area             TEXT NOT NULL,
                tipo             TEXT DEFAULT 'sin_proceso',  -- sin_proceso, paso_bloqueado, sla_vencido
                solicitud_id     INTEGER REFERENCES gta.solicitudes(id) ON DELETE SET NULL,
                reportado_por    TEXT,
                estado           TEXT DEFAULT 'abierto',      -- abierto, resuelto
                nota_resolucion  TEXT,
                resuelto_por     TEXT,
                resuelto_at      TIMESTAMP,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Comentarios de solicitudes
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.comentarios_solicitudes (
                id           SERIAL PRIMARY KEY,
                solicitud_id INTEGER NOT NULL REFERENCES gta.solicitudes(id) ON DELETE CASCADE,
                autor        TEXT NOT NULL,
                texto        TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_procesos_area      ON gta.procesos(area);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_procesos_estado    ON gta.procesos(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_solicitudes_estado ON gta.solicitudes(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_solicitudes_area   ON gta.solicitudes(area);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_solicitudes_proc   ON gta.solicitudes(proceso_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_quiebres_estado    ON gta.quiebres(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_comentarios_sol    ON gta.comentarios_solicitudes(solicitud_id);")

        _run_guarded_pg_section(conn, "migrate_gta_v2", _migrate_gta_v2_section)

        def _migrate_gta_areas_section() -> None:
            # Áreas (12 áreas operativas + contabilidad externa)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.areas (
                id           SERIAL PRIMARY KEY,
                code         TEXT NOT NULL UNIQUE,
                label        TEXT NOT NULL,
                lider_username TEXT DEFAULT '',
                lider_nombre   TEXT DEFAULT '',
                es_externa     BOOLEAN NOT NULL DEFAULT FALSE,
                activo         BOOLEAN NOT NULL DEFAULT TRUE,
                orden          INTEGER NOT NULL DEFAULT 99,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Subáreas: una subárea apunta a un área padre. Mismo líder por defecto.
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.subareas (
                id              SERIAL PRIMARY KEY,
                area_code       TEXT NOT NULL REFERENCES gta.areas(code) ON UPDATE CASCADE ON DELETE CASCADE,
                code            TEXT NOT NULL,
                label           TEXT NOT NULL,
                lider_username  TEXT DEFAULT '',
                lider_nombre    TEXT DEFAULT '',
                activo          BOOLEAN NOT NULL DEFAULT TRUE,
                orden           INTEGER NOT NULL DEFAULT 99,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(area_code, code)
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_areas_activo    ON gta.areas(activo);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_subareas_area   ON gta.subareas(area_code);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_subareas_activo ON gta.subareas(activo);")

            # Seed de las 12 áreas si la tabla está vacía
            existing = conn.execute("SELECT COUNT(*) AS c FROM gta.areas").fetchone()
            if int((existing or {}).get("c") or 0) == 0:
                seed_areas = [
                    ("comercial",         "Comercial",         "brayan.fuentes",   "Brayan Fuentes",   False, 10),
                    ("preventa",          "Preventa",          "",                 "Elso",             False, 20),
                    ("redes",             "Redes",             "fabian.correa",    "Fabián Correa",    False, 30),
                    ("sistemas",          "Sistemas",          "lukas.moyano",     "Lukas Moyano",     False, 40),
                    ("proveedores",       "Proveedores",       "",                 "Jonhson",          False, 50),
                    ("finanzas",          "Finanzas",          "",                 "Tania",            False, 60),
                    ("bodega",            "Bodega",            "",                 "",                 False, 70),
                    ("capital_humano",    "Capital Humano",    "",                 "Cristian Peña",    False, 80),
                    ("pmo",               "PMO",               "francisco.cea",    "Francisco Cea",    False, 90),
                    ("prevencion_riesgos","Prevención de Riesgos", "",             "(externa)",        True,  100),
                    ("contabilidad",      "Contabilidad",      "",                 "(externa)",        True,  110),
                    ("ia",                "IA",                "",                 "",                 False, 120),
                ]
                for code, label, lider_user, lider_nombre, externa, orden in seed_areas:
                    conn.execute(
                        """INSERT INTO gta.areas
                           (code, label, lider_username, lider_nombre, es_externa, activo, orden)
                           VALUES (%s, %s, %s, %s, %s, TRUE, %s)
                           ON CONFLICT (code) DO NOTHING""",
                        (code, label, lider_user, lider_nombre, externa, orden),
                    )

                seed_subareas = [
                    ("comercial",      "ventas",              "Ventas",                  10),
                    ("comercial",      "postventa",           "Postventa",               20),
                    ("redes",          "infraestructura",     "Infraestructura",         10),
                    ("redes",          "acceso",              "Redes de Acceso",         20),
                    ("redes",          "mesa_ayuda",          "Mesa de Ayuda",           30),
                    ("redes",          "soporte",             "Soporte",                 40),
                    ("redes",          "ciberseguridad",      "Ciberseguridad",          50),
                    ("proveedores",    "compras",             "Compras",                 10),
                    ("finanzas",       "facturacion",         "Facturación",             10),
                    ("finanzas",       "cobranzas",           "Cobranzas",               20),
                    ("capital_humano", "contratacion",        "Contratación",            10),
                    ("capital_humano", "desvinculacion",      "Desvinculación",          20),
                    ("pmo",            "proyectos",           "Gestión de Proyectos",    10),
                    ("pmo",            "instalaciones",       "Instalaciones",           20),
                    ("pmo",            "gestion_documental",  "Gestión Documental",      30),
                ]
                for area_code, code, label, orden in seed_subareas:
                    conn.execute(
                        """INSERT INTO gta.subareas
                           (area_code, code, label, activo, orden)
                           VALUES (%s, %s, %s, TRUE, %s)
                           ON CONFLICT (area_code, code) DO NOTHING""",
                        (area_code, code, label, orden),
                    )

        _run_guarded_pg_section(conn, "migrate_gta_areas", _migrate_gta_areas_section)

        def _migrate_gta_procesos_fix_section() -> None:
            # Asegura columnas faltantes en gta.procesos cuando la tabla
            # se creó parcial en una migración anterior (CREATE IF NOT EXISTS
            # no agrega columnas nuevas a una tabla preexistente).
            for col_def in (
                "descripcion       TEXT",
                "sla_horas         INTEGER",
                "icono             TEXT",
                "pasos_definicion  TEXT DEFAULT '[]'",
                "campos_formulario TEXT DEFAULT '[]'",
                "creado_por        TEXT",
                "updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            ):
                conn.execute(
                    f"ALTER TABLE gta.procesos ADD COLUMN IF NOT EXISTS {col_def}"
                )

        _run_guarded_pg_section(conn, "migrate_gta_procesos_fix", _migrate_gta_procesos_fix_section)

        def _migrate_gta_flujos_section() -> None:
            # Settings globales del GTA (jefe que recibe escalamientos, umbrales SLA, etc.)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # Seed básico
            for k, v in (
                ("jefe_username", "diego@telconsulting.cl"),
                ("sla_warn_pct", "70"),
                ("sla_critical_pct", "85"),
                ("sla_check_interval_min", "10"),
            ):
                conn.execute(
                    "INSERT INTO gta.settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                    (k, v),
                )

            # Instancia de flujo (un cierre de negocio puntual, una solicitud activa)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.flujos (
                id                 SERIAL PRIMARY KEY,
                proceso_id         INTEGER REFERENCES gta.procesos(id) ON DELETE SET NULL,
                titulo             TEXT NOT NULL,
                descripcion        TEXT,
                iniciado_por       TEXT NOT NULL,
                estado             TEXT NOT NULL DEFAULT 'borrador',
                datos_formulario   TEXT NOT NULL DEFAULT '{}',
                sla_horas_total    INTEGER,
                iniciado_at        TIMESTAMP,
                completado_at      TIMESTAMP,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # estados válidos: borrador, activo, completado, cancelado, vencido

            # Tareas dentro del flujo (una por área que participa)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.flujo_tareas (
                id                       SERIAL PRIMARY KEY,
                flujo_id                 INTEGER NOT NULL REFERENCES gta.flujos(id) ON DELETE CASCADE,
                orden                    INTEGER NOT NULL DEFAULT 1,
                area_code                TEXT NOT NULL,
                subarea_code             TEXT,
                asignado_a               TEXT,
                titulo                   TEXT NOT NULL,
                descripcion              TEXT,
                campos_requeridos        TEXT NOT NULL DEFAULT '[]',
                campos_completados       TEXT NOT NULL DEFAULT '{}',
                depende_de               TEXT NOT NULL DEFAULT '[]',
                sla_horas                INTEGER NOT NULL DEFAULT 24,
                estado                   TEXT NOT NULL DEFAULT 'pendiente',
                inicio_at                TIMESTAMP,
                ejecutor_completo_at     TIMESTAMP,
                ejecutor_completo_por    TEXT,
                validado_at              TIMESTAMP,
                validado_por             TEXT,
                sla_paused_minutes       INTEGER NOT NULL DEFAULT 0,
                sla_pause_started_at     TIMESTAMP,
                last_sla_warn_pct        INTEGER NOT NULL DEFAULT 0,
                created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # estados válidos: pendiente, lista, en_progreso, por_validar, completada,
            # ayuda_pedida, vencida, cancelada

            # Pedidos de ayuda entre áreas
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.flujo_ayudas (
                id                 SERIAL PRIMARY KEY,
                tarea_id           INTEGER NOT NULL REFERENCES gta.flujo_tareas(id) ON DELETE CASCADE,
                pedido_por         TEXT NOT NULL,
                pedido_a_area      TEXT NOT NULL,
                pedido_a_user      TEXT,
                mensaje            TEXT NOT NULL,
                bloquea_sla        BOOLEAN NOT NULL DEFAULT FALSE,
                estado             TEXT NOT NULL DEFAULT 'abierto',
                respondido_por     TEXT,
                respuesta          TEXT,
                respondido_at      TIMESTAMP,
                created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Timeline auditable de eventos del flujo
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.flujo_eventos (
                id           SERIAL PRIMARY KEY,
                flujo_id     INTEGER NOT NULL REFERENCES gta.flujos(id) ON DELETE CASCADE,
                tarea_id     INTEGER REFERENCES gta.flujo_tareas(id) ON DELETE SET NULL,
                tipo         TEXT NOT NULL,
                actor        TEXT,
                mensaje      TEXT,
                metadata     TEXT NOT NULL DEFAULT '{}',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Índices
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_flujos_estado       ON gta.flujos(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_flujos_iniciado_por ON gta.flujos(iniciado_por);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_flujos_proceso      ON gta.flujos(proceso_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_ftareas_flujo       ON gta.flujo_tareas(flujo_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_ftareas_estado      ON gta.flujo_tareas(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_ftareas_area        ON gta.flujo_tareas(area_code);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_ftareas_asignado    ON gta.flujo_tareas(asignado_a);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_fayudas_tarea       ON gta.flujo_ayudas(tarea_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_fayudas_estado      ON gta.flujo_ayudas(estado);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_feventos_flujo      ON gta.flujo_eventos(flujo_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_feventos_tarea      ON gta.flujo_eventos(tarea_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_feventos_tipo       ON gta.flujo_eventos(tipo);")

        _run_guarded_pg_section(conn, "migrate_gta_flujos", _migrate_gta_flujos_section)

        def _migrate_gta_procesos_unificacion_section() -> None:
            # Columnas adicionales en gta.procesos para unificar con archivos descargados
            for col_def in (
                "archivo_path  TEXT",
                "subarea_code  TEXT",
                "version       INTEGER NOT NULL DEFAULT 1",
            ):
                conn.execute(f"ALTER TABLE gta.procesos ADD COLUMN IF NOT EXISTS {col_def}")

            # Vincular quiebres a procesos (no solo a solicitudes/flujos)
            conn.execute("ALTER TABLE gta.quiebres ADD COLUMN IF NOT EXISTS proceso_id INTEGER")

            # Comentarios / decisiones / cambios sobre el proceso (audit trail)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS gta.proceso_comentarios (
                id          SERIAL PRIMARY KEY,
                proceso_id  INTEGER NOT NULL REFERENCES gta.procesos(id) ON DELETE CASCADE,
                autor       TEXT NOT NULL,
                texto       TEXT NOT NULL,
                tipo        TEXT NOT NULL DEFAULT 'nota',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            # tipo: nota | cambio | decision

            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_procesos_archivo  ON gta.procesos(archivo_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_quiebres_proceso  ON gta.quiebres(proceso_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gta_pcomentarios_proc ON gta.proceso_comentarios(proceso_id);")

        _run_guarded_pg_section(conn, "migrate_gta_procesos_unif", _migrate_gta_procesos_unificacion_section)

        def _migrate_sys_notifications_section() -> None:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS core.sys_notifications (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                message    TEXT NOT NULL,
                severity   TEXT NOT NULL DEFAULT 'INFO',
                read       BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL DEFAULT ''
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sys_notif_user   ON core.sys_notifications(user_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sys_notif_read   ON core.sys_notifications(read);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sys_notif_ts     ON core.sys_notifications(created_at DESC);")

        _run_guarded_pg_section(conn, "migrate_sys_notifications", _migrate_sys_notifications_section)

        def _migrate_sys_role_permissions_section() -> None:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS core.sys_role_permissions (
                id          SERIAL PRIMARY KEY,
                role        TEXT NOT NULL,
                permission  TEXT NOT NULL,
                label       TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                updated_at  TEXT NOT NULL DEFAULT '',
                UNIQUE(role, permission)
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_role_perms_role ON core.sys_role_permissions(role);")
            # Seed from config.py defaults if table is empty
            count = conn.execute("SELECT COUNT(*) AS n FROM core.sys_role_permissions").fetchone()
            if count and int(count["n"]) == 0:
                try:
                    from plataforma.core.config import settings as _s
                    now = now_utc_iso()
                    _PERM_LABELS = {
                        "*": "Acceso total del sistema",
                        "dashboard:read": "Dashboard: lectura",
                        "tickets:read": "Ticketera: lectura",
                        "tickets:write": "Ticketera: gestión operativa",
                        "tickets:compliance": "Ticketera: compliance y evidencias",
                        "audit:read": "Auditoría: lectura",
                        "audit:export": "Auditoría: exportación",
                        "invoice:read": "Facturación: lectura",
                        "invoice:sync": "Facturación: sincronización",
                        "invoice:write": "Facturación: edición",
                        "invoice:void": "Facturación: anulación",
                        "payment:write": "Pagos: gestión",
                        "crm:read": "CRM: lectura",
                        "crm:write": "CRM: edición",
                        "bodega:read": "Bodega: lectura",
                        "bodega:write": "Bodega: edición",
                        "pmo:read": "PMO: lectura",
                        "pmo:write": "PMO: edición",
                        "finanzas:read": "Finanzas: lectura",
                        "reports:read": "Reportes: lectura",
                        "fundacion:read": "Fundación: lectura",
                        "fundacion:write": "Fundación: escritura",
                        "admin.settings": "Configuración administrativa",
                        "zabbix:read": "Zabbix: lectura",
                        "ia:read": "IA: lectura",
                        "gta:read": "GTA: lectura",
                        "gta:write": "GTA: gestión",
                    }
                    _ROLE_DESCS = {
                        "admin": "Control total de plataforma, seguridad y configuración global.",
                        "encargado_mesa": "Gestiona flujo de ticketera, asignación, seguimiento y cumplimiento.",
                        "ops": "Operación técnica transversal para atención y despacho de tickets.",
                        "redes": "Ejecución técnica en networking e incidencias de conectividad.",
                        "sistemas": "Ejecución técnica en servidores, plataformas y sistemas.",
                        "implementaciones": "Ejecución de despliegues/proyectos con alcance técnico.",
                        "finance": "Gestión financiera y cobranza con foco contable.",
                        "warehouse": "Gestión operativa de inventario y movimientos de bodega.",
                        "gerencia": "Visión ejecutiva y lectura de indicadores/estado operacional.",
                        "monitora": "Planificación global y gestión de todas las tareas de la Fundación.",
                        "ejecutiva": "Acceso a planificación propia y reporte de actividades.",
                        "fundacion": "Gestión integral del módulo Fundación.",
                    }
                    for role, perms in _s.ROLE_PERMISSIONS.items():
                        desc = _ROLE_DESCS.get(role, "Rol operativo de plataforma.")
                        for perm in (perms or []):
                            label = _PERM_LABELS.get(perm, perm)
                            conn.execute(
                                """INSERT INTO core.sys_role_permissions (role, permission, label, description, updated_at)
                                   VALUES (%s, %s, %s, %s, %s)
                                   ON CONFLICT (role, permission) DO NOTHING""",
                                (role, perm, label, desc, now),
                            )
                except Exception as seed_err:
                    logger.warning("[DB] Could not seed sys_role_permissions: %s", seed_err)

        _run_guarded_pg_section(conn, "migrate_sys_role_permissions", _migrate_sys_role_permissions_section)

        # Automated Migrations Engine
        try:
            from core import migrations
            migrations.run_migrations()
        except Exception as e:
            logger.error("[DB] ERROR running automated migrations: %s", e)

        conn.commit()
    finally:
        conn.close()


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


