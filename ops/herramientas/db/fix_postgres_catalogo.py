
import sys
import os
sys.path.append(os.path.join(os.getcwd(), "code"))
from app.core.db import get_conn

def main():
    print("Connecting to DB...")
    conn = get_conn()
    # Check if PgConn or sqlite3
    try:
        # 1. Add Column
        print("Adding column is_hidden...")
        try:
            # db.py's execute converts ? to %s for postgres automatically
            conn.execute("ALTER TABLE cat_categorias ADD COLUMN is_hidden BOOLEAN DEFAULT FALSE")
            conn.commit()
            print("  Column added.")
        except Exception as e:
            if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                print("  Column already exists.")
            else:
                # If we are in a transaction block from a failed command? 
                # PgConn commits explicitly.
                print(f"  Note: {e}")
                conn.rollback()

        # 2. Ensure Categories
        # Bodega
        bodega_id = None
        cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Bodega' AND parent_id IS NULL")
        row = cur.fetchone()
        if row:
            bodega_id = row['id']
        else:
            cur = conn.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES ('system', 'Bodega', NULL, 1) RETURNING id")
            bodega_id = cur.fetchone()['id']
            conn.commit()
            print(f"Created Bodega: {bodega_id}")

        # Sin Clasificar
        sin_clasif_id = None
        cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Sin Clasificar'")
        row = cur.fetchone()
        if row:
            sin_clasif_id = row['id']
            # Update parent
            conn.execute("UPDATE cat_categorias SET parent_id=? WHERE id=?", (bodega_id, sin_clasif_id))
            conn.commit()
        else:
            cur = conn.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id, activo) VALUES ('system', 'Sin Clasificar', ?, 1) RETURNING id", (bodega_id,))
            sin_clasif_id = cur.fetchone()['id']
            conn.commit()
            print(f"Created Sin Clasificar: {sin_clasif_id}")

        # Pendientes (Hidden)
        pendientes_id = None
        cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Pendientes'")
        row = cur.fetchone()
        if row:
            pendientes_id = row['id']
            conn.execute("UPDATE cat_categorias SET is_hidden=?, parent_id=? WHERE id=?", (True, sin_clasif_id, pendientes_id))
            conn.commit()
            print("Updated Pendientes (Hidden)")
        else:
            cur = conn.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id, activo, is_hidden) VALUES ('system', 'Pendientes', ?, 1, ?) RETURNING id", (sin_clasif_id, True))
            pendientes_id = cur.fetchone()['id']
            conn.commit()
            print(f"Created Pendientes (Hidden): {pendientes_id}")

        # 3. Migrate Items
        print(f"Migrating items to category {pendientes_id}...")
        cur = conn.execute("UPDATE cat_items SET categoria_id=? WHERE categoria_id IS NULL OR categoria_id=0", (pendientes_id,))
        # PgConn cursors might not have rowcount on select, but update should
        try:
            rc = cur.rowcount
            print(f"  Moved {rc} items.")
        except:
            print("  Items moved (rowcount unavailable).")
        
        conn.commit()
        print("Done.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
