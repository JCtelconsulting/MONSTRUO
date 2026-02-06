#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path
from datetime import datetime

MIGRATION_ID = "2026-01-25_tks_v2"

def project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def db_path(root: Path) -> Path:
    return root / "data" / "db" / "monstruo.db"

def migration_applied(conn: sqlite3.Connection) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS meta_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    cur = conn.execute("SELECT 1 FROM meta_migrations WHERE id = ?", (MIGRATION_ID,))
    return cur.fetchone() is not None

def apply_migration(conn: sqlite3.Connection) -> None:
    # Add columns to tks_tickets
    cols = [
        ("sla_horas", "INTEGER DEFAULT 72"),
        ("vence_at", "TEXT"),
        ("prioridad", "INTEGER DEFAULT 3"),
        ("tags", "TEXT DEFAULT ''")
    ]
    for col, type_def in cols:
        try:
            conn.execute(f"ALTER TABLE tks_tickets ADD COLUMN {col} {type_def}")
        except sqlite3.OperationalError:
            pass # Ignore if exists

    # Create indices
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_tks_vence ON tks_tickets(vence_at);
        CREATE INDEX IF NOT EXISTS idx_tks_prio ON tks_tickets(prioridad);
    """)

    conn.execute(
        "INSERT OR IGNORE INTO meta_migrations (id, applied_at) VALUES (?, ?)",
        (MIGRATION_ID, datetime.now().isoformat())
    )
    conn.commit()

def main():
    dbfile = db_path(project_root())
    conn = sqlite3.connect(dbfile)
    try:
        if migration_applied(conn):
            print(f"[migrate] already applied: {MIGRATION_ID}")
        else:
            print(f"[migrate] applying: {MIGRATION_ID}")
            apply_migration(conn)
            print("[migrate] done")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
