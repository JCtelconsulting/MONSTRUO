#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path
from datetime import datetime

MIGRATION_ID = "2026-01-25_ticketera_catalogo_v1"

DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta_migrations (
  id TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

-- Ticketera
CREATE TABLE IF NOT EXISTS tks_tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL,
  origen TEXT NOT NULL,
  tipo TEXT NOT NULL,
  severidad TEXT NOT NULL DEFAULT 'media',
  estado TEXT NOT NULL DEFAULT 'abierto',
  titulo TEXT NOT NULL,
  descripcion TEXT DEFAULT '',
  entidad_ref TEXT DEFAULT '',
  asignado_a TEXT DEFAULT '',
  creado_por TEXT DEFAULT 'system',
  creado_at TEXT NOT NULL,
  actualizado_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tks_tickets_estado ON tks_tickets(estado);
CREATE INDEX IF NOT EXISTS idx_tks_tickets_origen ON tks_tickets(origen);
CREATE INDEX IF NOT EXISTS idx_tks_tickets_tipo ON tks_tickets(tipo);

CREATE TABLE IF NOT EXISTS tks_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL,
  evento TEXT NOT NULL,
  detalle TEXT DEFAULT '',
  creado_por TEXT DEFAULT 'system',
  creado_at TEXT NOT NULL,
  FOREIGN KEY(ticket_id) REFERENCES tks_tickets(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tks_eventos_ticket ON tks_eventos(ticket_id);

-- Catalogo jerarquico (equipos/materiales + subcategorias)
CREATE TABLE IF NOT EXISTS cat_categorias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL,
  nombre TEXT NOT NULL,
  parent_id INTEGER,
  activo INTEGER NOT NULL DEFAULT 1,
  UNIQUE(tipo, nombre, parent_id),
  FOREIGN KEY(parent_id) REFERENCES cat_categorias(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_cat_categorias_parent ON cat_categorias(parent_id);
CREATE INDEX IF NOT EXISTS idx_cat_categorias_tipo ON cat_categorias(tipo);

CREATE TABLE IF NOT EXISTS cat_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL,
  categoria_id INTEGER,
  unidad TEXT DEFAULT '',
  sku_canonico TEXT DEFAULT '',
  ean TEXT DEFAULT '',
  marca TEXT DEFAULT '',
  atributos_json TEXT DEFAULT '{}',
  activo INTEGER NOT NULL DEFAULT 1,
  creado_at TEXT NOT NULL,
  actualizado_at TEXT NOT NULL,
  FOREIGN KEY(categoria_id) REFERENCES cat_categorias(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_cat_items_categoria ON cat_items(categoria_id);
CREATE INDEX IF NOT EXISTS idx_cat_items_sku ON cat_items(sku_canonico);
CREATE INDEX IF NOT EXISTS idx_cat_items_ean ON cat_items(ean);

CREATE TABLE IF NOT EXISTS cat_fuente_map (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fuente TEXT NOT NULL,
  fuente_item_id TEXT NOT NULL,
  item_id INTEGER NOT NULL,
  confianza REAL NOT NULL DEFAULT 1.0,
  metodo_match TEXT NOT NULL DEFAULT 'manual',
  UNIQUE(fuente, fuente_item_id),
  FOREIGN KEY(item_id) REFERENCES cat_items(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cat_fuente_map_fuente ON cat_fuente_map(fuente);
"""

def project_root() -> Path:
  return Path(__file__).resolve().parents[2]

def db_path(root: Path) -> Path:
  return root / "data" / "db" / "monstruo.db"

def backup_db(dbfile: Path) -> Path:
  ts = datetime.now().strftime("%Y%m%d_%H%M%S")
  backup_dir = dbfile.parent / "backups"
  backup_dir.mkdir(parents=True, exist_ok=True)
  backup_file = backup_dir / f"{dbfile.name}.{ts}.bak"
  if dbfile.exists():
    backup_file.write_bytes(dbfile.read_bytes())
  return backup_file

def migration_applied(conn: sqlite3.Connection) -> bool:
  conn.execute("CREATE TABLE IF NOT EXISTS meta_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
  cur = conn.execute("SELECT 1 FROM meta_migrations WHERE id = ?", (MIGRATION_ID,))
  return cur.fetchone() is not None

def apply_migration(conn: sqlite3.Connection) -> None:
  conn.executescript(DDL)
  conn.execute(
    "INSERT OR IGNORE INTO meta_migrations (id, applied_at) VALUES (?, ?)",
    (MIGRATION_ID, datetime.now().isoformat(timespec="seconds"))
  )
  conn.commit()

def list_tables(conn: sqlite3.Connection):
  cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
  return [r[0] for r in cur.fetchall()]

def main():
  root = project_root()
  dbfile = db_path(root)

  print(f"[db] root={root}")
  print(f"[db] path={dbfile}")

  bkp = backup_db(dbfile)
  print(f"[db] backup={bkp}")

  conn = sqlite3.connect(dbfile)
  try:
    conn.execute("PRAGMA foreign_keys = ON")
    if migration_applied(conn):
      print(f"[migrate] already applied: {MIGRATION_ID}")
    else:
      print(f"[migrate] applying: {MIGRATION_ID}")
      apply_migration(conn)
      print("[migrate] done")

    tables = list_tables(conn)
    must_have = [
      "tks_tickets", "tks_eventos",
      "cat_categorias", "cat_items", "cat_fuente_map",
      "meta_migrations"
    ]
    missing = [t for t in must_have if t not in tables]
    print(f"[verify] tables={len(tables)}")
    print(f"[verify] missing={missing}" if missing else "[verify] ok")
  finally:
    conn.close()

if __name__ == "__main__":
  main()
