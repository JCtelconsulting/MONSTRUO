
import sys
import os
sys.path.append(os.path.join(os.getcwd(), "code"))
from app.core.db import get_conn

def main():
    print("Correction: Moving 'Sin Asignar' to BODEGA > EQUIPOS")
    conn = get_conn()
    try:
        # 1. Identify Target Parent: BODEGA (6) -> EQUIPOS (110)
        # Verify 110 is indeed EQUIPOS and parent is 6
        cur = conn.execute("SELECT id, nombre, parent_id FROM cat_categorias WHERE id=110")
        equipos = cur.fetchone()
        if not equipos:
            print("CRITICAL: Category EQUIPOS (110) not found. Aborting.")
            return
        
        print(f"Target Parent: {equipos['nombre']} (ID: {equipos['id']}, Parent: {equipos['parent_id']})")
        
        # 2. Check if 'Sin Asignar' already exists under EQUIPOS (110)
        sin_asignar_id = None
        cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Sin Asignar' AND parent_id=110")
        row = cur.fetchone()
        
        if row:
            sin_asignar_id = row['id']
            print(f"  'Sin Asignar' already exists (ID: {sin_asignar_id}). Ensuring hidden...")
            conn.execute("UPDATE cat_categorias SET is_hidden=? WHERE id=?", (True, sin_asignar_id))
        else:
            print("  Creating 'Sin Asignar' under EQUIPOS...")
            cur = conn.execute(
                "INSERT INTO cat_categorias (tipo, nombre, parent_id, activo, is_hidden) VALUES ('system', 'Sin Asignar', ?, 1, ?) RETURNING id",
                (110, True)
            )
            sin_asignar_id = cur.fetchone()['id']
            print(f"  Created 'Sin Asignar' (ID: {sin_asignar_id})")
        
        # 3. Migrate items from 'Pendientes' (Old hidden cat)
        # Find 'Pendientes' (we made it hidden previously, likely ID 139 or 101 depending on DB state)
        # Or just find ANY category named 'Pendientes' that is hidden
        cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Pendientes'")
        pendientes_rows = cur.fetchall()
        
        for p in pendientes_rows:
            p_id = p['id']
            if p_id == sin_asignar_id: continue # Just in case
            
            print(f"  Migrating items from Pendientes (ID: {p_id}) -> Sin Asignar (ID: {sin_asignar_id})")
            cur = conn.execute("UPDATE cat_items SET categoria_id=? WHERE categoria_id=?", (sin_asignar_id, p_id))
            print(f"    Moved {cur.rowcount} items.")
            
            # Delete the old category
            print(f"    Deleting old category {p_id}...")
            conn.execute("DELETE FROM cat_categorias WHERE id=?", (p_id,))

        # 4. Cleanup 'Bodega' duplicate (ID 138)
        # Also check 'Sin Clasificar' (ID 8) if it was under 138
        # We need to be careful not to delete items if any exist there.
        
        # Find 'Bodega' (duplicate) - We know ID 138 from inspection, but let's be safe
        cur = conn.execute("SELECT id FROM cat_categorias WHERE nombre='Bodega' AND id != 6")
        dups = cur.fetchall()
        for d in dups:
            d_id = d['id']
            print(f"  Cleaning up duplicate 'Bodega' (ID: {d_id})...")
            
            # Move children to Root or valid Bodega? Or just fail if children?
            # Check children
            cur = conn.execute("SELECT id, nombre FROM cat_categorias WHERE parent_id=?", (d_id,))
            children = cur.fetchall()
            for child in children:
                print(f"    Found child '{child['nombre']}' (ID: {child['id']}). Deleting...")
                conn.execute("DELETE FROM cat_categorias WHERE id=?", (child['id'],))
            
            conn.execute("DELETE FROM cat_categorias WHERE id=?", (d_id,))
            print("    Deleted.")

        conn.commit()
        print("Done.")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
