#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
from pathlib import Path

def project_root() -> Path:
    return Path(__file__).resolve().parents[2]

def db_path(root: Path) -> Path:
    return root / "data" / "db" / "monstruo.db"

def main():
    dbfile = db_path(project_root())
    conn = sqlite3.connect(dbfile)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    try:
        # 1. Equipos
        c.execute("INSERT OR IGNORE INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES (?, ?, ?, ?)", ("equipo", "Equipos", None, 1))
        # 2. Materiales
        c.execute("INSERT OR IGNORE INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES (?, ?, ?, ?)", ("material", "Materiales", None, 1))
        
        # Get IDs
        cats = {r["nombre"]: r["id"] for r in c.execute("SELECT nombre, id FROM cat_categorias WHERE parent_id IS NULL")}
        
        mat_id = cats.get("Materiales")
        if mat_id:
             # 3. Tornillos (hijo de Materiales)
             c.execute("INSERT OR IGNORE INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES (?, ?, ?, ?)", ("material", "Tornillos", mat_id, 1))
             
             # Get Tornillos ID
             row_torn = c.execute("SELECT id FROM cat_categorias WHERE nombre='Tornillos' AND parent_id=?", (mat_id,)).fetchone()
             if row_torn:
                 torn_id = row_torn["id"]
                 # 4. Madera / Fierro (hijos de Tornillos)
                 c.execute("INSERT OR IGNORE INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES (?, ?, ?, ?)", ("material", "Madera", torn_id, 1))
                 c.execute("INSERT OR IGNORE INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES (?, ?, ?, ?)", ("material", "Fierro", torn_id, 1))
        
        conn.commit()
        print("[seed] Catalogo taxonomy seeded successfully.")
        
        # Verify
        print("[verify] Rows:")
        for r in c.execute("SELECT id, tipo, nombre, parent_id FROM cat_categorias ORDER BY tipo, parent_id, nombre"):
            print(dict(r))

    except Exception as e:
        print(f"[seed] Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
