import sqlite3
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = "monstruo.db"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_workflow_db() -> None:
    conn = get_conn()
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',   -- open|in_progress|blocked|done|canceled
            priority TEXT NOT NULL DEFAULT 'medium', -- low|medium|high|critical
            owner_role TEXT NOT NULL DEFAULT 'ops',  -- ops|finance|warehouse|admin
            created_by TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_owner ON cases(owner_role);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',     -- open|doing|blocked|done
            assignee_role TEXT NOT NULL DEFAULT 'ops',
            due_date TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            FOREIGN KEY(case_id) REFERENCES cases(id)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_case ON tasks(case_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            author TEXT DEFAULT '',
            comment TEXT NOT NULL,
            created_at TEXT DEFAULT '',
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_comments_task ON task_comments(task_id);")

        # generic links: tie discrepancies/alerts/anything to cases
        conn.execute("""
        CREATE TABLE IF NOT EXISTS task_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            link_type TEXT NOT NULL,      -- parrotfy_discrepancy|alert|laudus_invoice|etc
            link_key TEXT NOT NULL,       -- e.g. discrepancy.key or alert id
            created_at TEXT DEFAULT '',
            UNIQUE(case_id, link_type, link_key),
            FOREIGN KEY(case_id) REFERENCES cases(id)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_links_case ON task_links(case_id);")

        # Deduplication: persist fingerprints to avoid recreating tasks for same problem
        conn.execute("""
        CREATE TABLE IF NOT EXISTS workflow_dedup (
            fingerprint TEXT PRIMARY KEY,
            task_id INTEGER,
            case_id INTEGER,
            first_seen TEXT DEFAULT '',
            last_seen TEXT DEFAULT '',
            last_comment_at TEXT DEFAULT '',
            hit_count INTEGER DEFAULT 1,
            FOREIGN KEY(task_id) REFERENCES tasks(id),
            FOREIGN KEY(case_id) REFERENCES cases(id)
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_dedup_task ON workflow_dedup(task_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workflow_dedup_case ON workflow_dedup(case_id);")

        conn.commit()
    finally:
        conn.close()

def q(sql: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()

def exec1(sql: str, params: Tuple[Any, ...] = ()) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return int(cur.lastrowid or 0)
    finally:
        conn.close()
