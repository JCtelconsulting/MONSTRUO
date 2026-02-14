import os
import hmac
import hashlib
import secrets
import re
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row

    _HAVE_PSYCOPG3 = True
except Exception:
    psycopg = None
    dict_row = None
    _HAVE_PSYCOPG3 = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    _HAVE_PSYCOPG2 = True
except Exception:
    psycopg2 = None
    RealDictCursor = None
    _HAVE_PSYCOPG2 = False

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_URL = os.getenv("DB_URL", "").strip()


def _is_postgres() -> bool:
    return DB_URL.startswith("postgres://") or DB_URL.startswith("postgresql://")


def is_postgres() -> bool:
    return _is_postgres()


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
    def __init__(self, conn, use_psycopg3: bool):
        self._conn = conn
        self._use_psycopg3 = use_psycopg3

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
        self._conn.close()


def get_conn():
    if not _is_postgres():
        raise RuntimeError(
            "CRITICAL: PostgreSQL is required. Check DB_URL environment variable. SQLite fallback has been disabled for safety."
        )

    if _HAVE_PSYCOPG3:
        conn = psycopg.connect(DB_URL, row_factory=dict_row)
        return PgConn(conn, use_psycopg3=True)
    if _HAVE_PSYCOPG2:
        conn = psycopg2.connect(DB_URL)
        return PgConn(conn, use_psycopg3=False)

    raise RuntimeError("PostgreSQL driver not installed. Install psycopg or psycopg2.")


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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_customers_vat ON laudus_customers(vat_id);"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_invoices_customer ON laudus_invoices(customer_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_invoices_due ON laudus_invoices(due_date);"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_payments_invoice ON laudus_payments(invoice_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_payments_customer ON laudus_payments(customer_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_laudus_payments_date ON laudus_payments(payment_date);"
        )

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
            allowed_modules TEXT DEFAULT '[]',
            phone_number TEXT,
            created_at TEXT DEFAULT ''
        );
        """)
        
        # MIGRATION: Ensure allowed_modules and phone_number exist (for existing DBs)
        try:
            if is_postgres():
                conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_modules TEXT DEFAULT '[]'")
                conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT")
            else:
                # SQLite fallback
                try:
                    conn.execute("ALTER TABLE users ADD COLUMN allowed_modules TEXT DEFAULT '[]'")
                except Exception:
                    pass
                try:
                    conn.execute("ALTER TABLE users ADD COLUMN phone_number TEXT")
                except Exception:
                    pass
        except Exception as e:
            print(f"Warning migrating users columns: {e}")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);")

        # System Settings (EPIC Config)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            group_name TEXT DEFAULT 'general',
            is_sensitive BOOLEAN DEFAULT 0,
            updated_at TEXT
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(username);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at);"
        )

        # Audit Logs (EPIC 02/03)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
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
            "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(timestamp);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor);")
        if is_postgres():
            conn.execute(
                "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'info'"
            )
        else:
            try:
                conn.execute(
                    "ALTER TABLE audit_logs ADD COLUMN severity TEXT DEFAULT 'info'"
                )
            except Exception:
                pass

        # Jobs Engine (EPIC 04)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS sys_jobs (
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON sys_jobs(status);")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_next_run ON sys_jobs(next_run_at);"
        )

        # Ticketera (EPIC 11)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
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
            "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(estado);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tickets_assignee ON tickets(asignado_a);"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_due ON tickets(vence_at);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_comments_ticket ON ticket_comments(ticket_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_attachments (
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
            "CREATE INDEX IF NOT EXISTS idx_attach_ticket ON ticket_attachments(ticket_id);"
        )

        # --- Ticketera V3: Columnas extras en tickets (migración individual) ---
        _v3_columns = [
            ("codigo",          "TEXT",                True),
            ("categoria",       "TEXT DEFAULT 'general'", True),
            ("origen_email",    "TEXT",                True),
            ("cliente_nombre",  "TEXT",                True),
            ("prioridad",       "INTEGER DEFAULT 3",   True),
            ("sla_horas",       "INTEGER DEFAULT 72",  True),
            ("email_thread_id", "TEXT",                False),
            ("resolucion",      "TEXT",                False),
        ]
        for col_name, col_def, is_critical in _v3_columns:
            try:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN IF NOT EXISTS {col_name} {col_def};")
            except Exception as _e:
                if is_critical:
                    # FAIL-FAST: Si es columna crítica para V3, no permitir arranque a medias
                    err_msg = f"[DB-MIGRATION] CRITICAL ERROR: No se pudo crear columna '{col_name}' necesaria para V3. Detalle: {_e}"
                    print(err_msg)
                    raise RuntimeError(err_msg) from _e
                else:
                    print(f"[DB-MIGRATION] WARN columna '{col_name}' ya existe o no se pudo crear: {_e}")

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
            "CREATE INDEX IF NOT EXISTS idx_tickets_codigo ON tickets(codigo);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_categoria ON tickets(categoria);",
            "CREATE INDEX IF NOT EXISTS idx_tickets_prioridad ON tickets(prioridad);",
        ]:
            try:
                conn.execute(idx_sql)
            except Exception as _e:
                print(f"[DB-MIGRATION] WARN índice: {_e}")

        # --- Ticketera V3: Especialidades de Usuarios ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_specialties (
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
            "CREATE INDEX IF NOT EXISTS idx_user_spec_user ON user_specialties(username);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_spec_specialty ON user_specialties(specialty);"
        )

        # --- Ticketera V3: Notificaciones Escalonadas ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_notifications (
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
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_ticket ON ticket_notifications(ticket_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_user ON ticket_notifications(user_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_status ON ticket_notifications(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_notif_sched ON ticket_notifications(scheduled_at);"
        )

        # --- Ticketera V3: Historial de Emails ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            from_addr TEXT,
            to_addr TEXT,
            subject TEXT,
            body_html TEXT,
            attachments_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        );
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tk_emails_ticket ON ticket_emails(ticket_id);"
        )

        # Sales ERP (EPIC 05)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
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
            "CREATE INDEX IF NOT EXISTS idx_invoices_cust ON invoices(customer_id);"
        )

        # CRM (EPIC 06)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
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
            "CREATE INDEX IF NOT EXISTS idx_customers_ext ON customers(external_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS crm_interactions (
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
            "CREATE INDEX IF NOT EXISTS idx_crm_interactions_cust ON crm_interactions(customer_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS collection_actions (
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
            "CREATE INDEX IF NOT EXISTS idx_coll_actions_cust ON collection_actions(customer_id);"
        )

        # Bodega (EPIC 09)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);")

        # Backfill columns if DB existed before (PostgreSQL)
        try:
            conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_currency TEXT DEFAULT 'CLP';")
            conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price_parity REAL DEFAULT 1.0;")
        except Exception:
            pass

        conn.execute("""
        CREATE TABLE IF NOT EXISTS invoice_items (
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
            "CREATE INDEX IF NOT EXISTS idx_inv_items_inv ON invoice_items(invoice_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movements (
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
            "CREATE INDEX IF NOT EXISTS idx_movements_prod ON inventory_movements(product_id);"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_number ON parrotfy_invoices(invoice_number);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_customer ON parrotfy_invoices(customer_id);"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_pay_invoice ON parrotfy_payments(parrotfy_invoice_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_pay_date ON parrotfy_payments(payment_date);"
        )

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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_prod ON parrotfy_inventory(product_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pf_inv_date ON parrotfy_inventory(date);"
        )

        # -----------------------------
        # Phase 3: Snapshots & Conciliation
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS parrotfy_stock_snapshot (
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
            "CREATE INDEX IF NOT EXISTS idx_pf_stock_snap ON parrotfy_stock_snapshot(snapshot_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS laudus_stock_snapshot (
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
            "CREATE INDEX IF NOT EXISTS idx_lau_stock_snap ON laudus_stock_snapshot(snapshot_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS conciliacion_bodega_runs (
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
        CREATE TABLE IF NOT EXISTS conciliacion_bodega_diffs (
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
            "CREATE INDEX IF NOT EXISTS idx_concil_diff_run ON conciliacion_bodega_diffs(run_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ia_eventos (
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
        CREATE TABLE IF NOT EXISTS stock_snapshots (
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
            "CREATE INDEX IF NOT EXISTS idx_stock_snap_prov ON stock_snapshots(proveedor);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stock_snap_ts ON stock_snapshots(creado_ts);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ia_bodega_casos (
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
            "CREATE INDEX IF NOT EXISTS idx_ia_casos_ts ON ia_bodega_casos(creado_ts);"
        )

        # -----------------------------
        # Bridge & AI
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bridge_messages (
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
            "CREATE INDEX IF NOT EXISTS idx_bridge_to ON bridge_messages(to_agent);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bridge_approval ON bridge_messages(approval_status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bridge_thread ON bridge_messages(thread_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_event_queue (
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
        CREATE TABLE IF NOT EXISTS ai_recommendations (
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
            "CREATE INDEX IF NOT EXISTS idx_ai_event_status ON ai_event_queue(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_event_kind ON ai_event_queue(kind);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_rec_status ON ai_recommendations(status);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_rec_event ON ai_recommendations(event_id);"
        )

        # -----------------------------
        # EPIC 07: Bank Reconciliation
        # -----------------------------
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bank_accounts (
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
            "CREATE INDEX IF NOT EXISTS idx_bank_acc_laudus ON bank_accounts(laudus_account_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bank_statements (
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
            "CREATE INDEX IF NOT EXISTS idx_bs_account ON bank_statements(bank_account_id);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bank_statement_lines (
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
            "CREATE INDEX IF NOT EXISTS idx_bsl_statement ON bank_statement_lines(statement_id);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bsl_hash ON bank_statement_lines(hash);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_bsl_date ON bank_statement_lines(date);"
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bank_reconciliations (
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
            "CREATE INDEX IF NOT EXISTS idx_br_line ON bank_reconciliations(statement_line_id);"
        )

        # Catalogo: multi-categoria (m:n)
        try:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat_categorias (
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
                "CREATE INDEX IF NOT EXISTS idx_cat_categorias_parent ON cat_categorias(parent_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_categorias_tipo ON cat_categorias(tipo);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat_items (
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
                "CREATE INDEX IF NOT EXISTS idx_cat_items_categoria ON cat_items(categoria_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_items_sku ON cat_items(sku_canonico);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat_match_queue (
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
                "CREATE INDEX IF NOT EXISTS idx_cat_mq_score ON cat_match_queue(score);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_mq_estado ON cat_match_queue(estado);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat_fuente_map (
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
                "CREATE INDEX IF NOT EXISTS idx_cat_fuente_map_fuente ON cat_fuente_map(fuente);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS cat_item_categories (
                item_id INTEGER NOT NULL,
                categoria_id INTEGER NOT NULL,
                created_at TEXT DEFAULT '',
                UNIQUE(item_id, categoria_id),
                FOREIGN KEY(item_id) REFERENCES cat_items(id),
                FOREIGN KEY(categoria_id) REFERENCES cat_categorias(id)
            );
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_item_categories_item ON cat_item_categories(item_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cat_item_categories_cat ON cat_item_categories(categoria_id);"
            )

            # -----------------------------
            # EPIC 21: Automatic Billing (Rules)
            # -----------------------------
            conn.execute("""
            CREATE TABLE IF NOT EXISTS billing_rules (
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
                "CREATE INDEX IF NOT EXISTS idx_billing_rules_cust ON billing_rules(customer_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_billing_rules_next ON billing_rules(next_billing_date);"
            )

            # -----------------------------
            # EPIC 22: Templates / Billing Profiles / Dispatch Tracking
            # -----------------------------
            conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_templates (
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
                "CREATE INDEX IF NOT EXISTS idx_invoice_templates_customer ON invoice_templates(customer_id);"
            )
            # Backfill columns if DB existed before (PostgreSQL)
            try:
                conn.execute("ALTER TABLE invoice_templates ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'CLP';")
                conn.execute("ALTER TABLE invoice_templates ADD COLUMN IF NOT EXISTS is_active INTEGER NOT NULL DEFAULT 1;")
                conn.execute("ALTER TABLE invoice_templates ADD COLUMN IF NOT EXISTS created_by TEXT DEFAULT '';")
                conn.execute("ALTER TABLE invoice_templates ADD COLUMN IF NOT EXISTS created_at TEXT DEFAULT '';")
                conn.execute("ALTER TABLE invoice_templates ADD COLUMN IF NOT EXISTS updated_at TEXT DEFAULT '';")
            except Exception:
                pass

            conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_template_items (
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
                "CREATE INDEX IF NOT EXISTS idx_template_items_template ON invoice_template_items(template_id);"
            )
            # Backfill columns if DB existed before (PostgreSQL)
            try:
                conn.execute("ALTER TABLE invoice_template_items ADD COLUMN IF NOT EXISTS sku TEXT;")
                conn.execute("ALTER TABLE invoice_template_items ADD COLUMN IF NOT EXISTS created_at TEXT DEFAULT '';")
            except Exception:
                pass

            conn.execute("""
            CREATE TABLE IF NOT EXISTS billing_profiles (
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
                "CREATE INDEX IF NOT EXISTS idx_billing_profiles_customer ON billing_profiles(customer_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_billing_profiles_next ON billing_profiles(next_billing_date);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS customer_contacts (
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
                "CREATE INDEX IF NOT EXISTS idx_customer_contacts_customer ON customer_contacts(customer_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS billing_profile_recipients (
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
                "CREATE INDEX IF NOT EXISTS idx_profile_recipients_profile ON billing_profile_recipients(profile_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_dispatches (
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
                "CREATE INDEX IF NOT EXISTS idx_invoice_dispatches_invoice ON invoice_dispatches(invoice_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_events (
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
                "CREATE INDEX IF NOT EXISTS idx_invoice_events_invoice ON invoice_events(invoice_id);"
            )

            conn.execute("""
            CREATE TABLE IF NOT EXISTS uf_rates (
                uf_date TEXT PRIMARY KEY, -- YYYY-MM-DD
                uf_value REAL NOT NULL,
                source TEXT DEFAULT 'mindicador',
                fetched_at TEXT NOT NULL
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_uf_rates_date ON uf_rates(uf_date);")

        except Exception as e:
            print(f"Error in init_db (cat/billing): {e}")
            pass

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


# Auth logic moved to app.core.security and app.core.auth_service
