#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path
from datetime import datetime

MIGRATION_ID = "2026-01-25_catalogo_v2"

DDL = """
-- Agregar columnas a match existente
ALTER TABLE cat_fuente_map ADD COLUMN last_seen_at TEXT;
ALTER TABLE cat_fuente_map ADD COLUMN meta_json TEXT DEFAULT '{}';
ALTER TABLE cat_fuente_map ADD COLUMN candidato_item_id INTEGER;
ALTER TABLE cat_fuente_map ADD COLUMN candidato_confianza REAL DEFAULT 0.0;

-- Tabla de Sugerencias Pendientes
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

CREATE INDEX IF NOT EXISTS idx_cat_mq_score ON cat_match_queue(score);
CREATE INDEX IF NOT EXISTS idx_cat_mq_estado ON cat_match_queue(estado);
"""

def project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def db_path(root: Path) -> Path:
    return root / "data" / "db" / "monstruo.db"

def migration_applied(conn: sqlite3.Connection) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS meta_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    cur = conn.execute("SELECT 1 FROM meta_migrations WHERE id = ?", (MIGRATION_ID,))
    return cur.fetchone() is not None

def apply_migration(conn: sqlite3.Connection) -> None:
    # Split DDL because sqlite executemany/script limitations with ALTER TABLE usually work but let's be safe
    # Actually executescript handles multiple statements fine.
    # However, ALTER TABLE ADD COLUMN might fail if column exists. 
    # We will handle individually wrapped in try/except for the columns.
    
    # 1. Add columns to cat_fuente_map
    cols = [
        ("last_seen_at", "TEXT"),
        ("meta_json", "TEXT DEFAULT '{}'"),
        ("candidato_item_id", "INTEGER"),
        ("candidato_confianza", "REAL DEFAULT 0.0")
    ]
    for col, type_def in cols:
        try:
            conn.execute(f"ALTER TABLE cat_fuente_map ADD COLUMN {col} {type_def}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                pass
            else:
                pass # Ignore if exists

    # 2. Create Match Queue
    conn.executescript("""
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
        CREATE INDEX IF NOT EXISTS idx_cat_mq_score ON cat_match_queue(score);
        CREATE INDEX IF NOT EXISTS idx_cat_mq_estado ON cat_match_queue(estado);
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
