#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path
from datetime import datetime

MIGRATION_ID = "2026-01-29_hidden_categories_v1"

def project_root() -> Path:
    return Path(__file__).resolve().parents[3]

def db_path(root: Path) -> Path:
    return root / "data" / "db" / "monstruo.db"

def migration_applied(conn: sqlite3.Connection) -> bool:
    conn.execute("CREATE TABLE IF NOT EXISTS meta_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    cur = conn.execute("SELECT 1 FROM meta_migrations WHERE id = ?", (MIGRATION_ID,))
    return cur.fetchone() is not None

def ensure_category_structure(conn: sqlite3.Connection):
    """
    Ensure structure: Bodega (root) -> Sin Clasificar -> Pendientes
    Returns the id of 'Pendientes' category.
    """
    # 1. Bodega (Root)
    print("  Checking 'Bodega'...")
    cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Bodega' AND parent_id IS NULL")
    row = cur.fetchone()
    if row:
        bodega_id = row[0]
    else:
        cur = conn.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES ('system', 'Bodega', NULL, 1) RETURNING id")
        bodega_id = cur.fetchone()[0]
        print(f"    Created 'Bodega' (id={bodega_id})")

    # 2. Sin Clasificar (Child of Bodega)
    print("  Checking 'Sin Clasificar'...")
    cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Sin Clasificar'")
    row = cur.fetchone()
    if row:
        sin_clasif_id = row[0]
        # Fix parent if wrong
        conn.execute("UPDATE cat_categorias SET parent_id=? WHERE id=?", (bodega_id, sin_clasif_id))
    else:
        cur = conn.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES ('system', 'Sin Clasificar', ?, 1) RETURNING id", (bodega_id,))
        sin_clasif_id = cur.fetchone()[0]
        print(f"    Created 'Sin Clasificar' (id={sin_clasif_id})")
    
    # Ensure it is hidden? Plan says 'Pendientes' is hidden. User asked for unassigned to be IN category.
    # Usually "Sin Clasificar" acts as a bucket. Let's make sure 'Sin Clasificar' is visible but its children might be?
    # Or maybe 'Sin Clasificar' ITSELF should be hidden?
    # The requirement is: "hacer una categoria del tercer y cuarto nivel que se ocultable que tenga a las sin asignar"
    # So: Bodega (1) -> Sin Clasificar (2) -> Pendientes (3/Hidden).
    # Items go into Pendientes.
    
    # 3. Pendientes (Child of Sin Clasificar) - HIDDEN
    print("  Checking 'Pendientes'...")
    cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Pendientes' AND parent_id=?", (sin_clasif_id,))
    row = cur.fetchone()
    if row:
        pendientes_id = row[0]
        conn.execute("UPDATE cat_categorias SET is_hidden=1 WHERE id=?", (pendientes_id,))
        print(f"    Updated 'Pendientes' (id={pendientes_id}) to hidden")
    else:
        cur = conn.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id, activo, is_hidden) VALUES ('system', 'Pendientes', ?, 1, 1) RETURNING id", (sin_clasif_id,))
        pendientes_id = cur.fetchone()[0]
        print(f"    Created 'Pendientes' (id={pendientes_id}) as HIDDEN")
        
    return pendientes_id

def apply_migration(conn: sqlite3.Connection) -> None:
    # 1. Add column is_hidden
    try:
        print("Adding column is_hidden...")
        conn.execute("ALTER TABLE cat_categorias ADD COLUMN is_hidden INTEGER DEFAULT 0")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("  Column is_hidden already exists.")
        else:
            print(f"  Warning: {e}")

    # 2. Create Structure
    pendientes_id = ensure_category_structure(conn)
    
    # 3. Migrate Items
    print(f"Migrating unassigned items to category {pendientes_id}...")
    # Items with NULL category or 0
    cur = conn.execute("UPDATE cat_items SET categoria_id=? WHERE categoria_id IS NULL OR categoria_id=0", (pendientes_id,))
    print(f"  Moved {cur.rowcount} items.")

    # 4. Mark migration
    conn.execute(
        "INSERT OR IGNORE INTO meta_migrations (id, applied_at) VALUES (?, ?)",
        (MIGRATION_ID, datetime.now().isoformat())
    )
    conn.commit()

def main():
    root = project_root()
    dbfile = db_path(root)
    print(f"[migrate] path={dbfile}")
    
    if not dbfile.exists():
        print("DB not found!")
        return

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
