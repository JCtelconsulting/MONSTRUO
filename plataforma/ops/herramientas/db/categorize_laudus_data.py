
import sys
import os
import re

sys.path.append(os.path.join(os.getcwd(), "code"))
from app.core.db import get_conn

# --- CONFIG ---
EQUIPOS_ID = 110
MATERIALES_ID = 106

# Map: Category Name -> ID (filled at runtime)
CAT_IDS = {
    # Equipos Subcats (Existing)
    'STARLINK': None,
    'MIKROTIK': None,
    'CELULARES': None,
    'COMPUTADORES': None,
    
    # Materiales Subcats (To Create)
    'CABLES': None,
    'CONECTORES': None,
    'FERRETERIA': None,
    'DUCTOS': None,
    
    # Buckets
    'EQUIPOS_SIN_ASIGNAR': None,
    'MATERIALES_SIN_ASIGNAR': None
}

# Regex Rules: (Pattern, Destination Key)
# Priority: Top to Bottom
RULES_EQUIPOS = [
    (r'(?i)(starlink|antena satelital)', 'STARLINK'),
    (r'(?i)(mikrotik|router|switch|ubiquiti|cisco)', 'MIKROTIK'),
    (r'(?i)(celular|smartphone|iphone|samsung|movil)', 'CELULARES'),
    (r'(?i)(computador|pc|notebook|laptop|macbook|monitor|cpu|teclado|mouse)', 'COMPUTADORES'),
]

RULES_MATERIALES = [
    (r'(?i)(cable|alambre|cordon|utp|fibra|patch|cord|bobina)', 'CABLES'),
    (r'(?i)(conector|rj45|jack|plug|modulare|faceplate)', 'CONECTORES'),
    (r'(?i)(canaleta|conduit|tubo|pvc|ducto|codo|copla)', 'DUCTOS'),
    (r'(?i)(tornillo|perno|tuerca|tarugo|fijacion|sopor|riel|perfil|abrazadera|clavo)', 'FERRETERIA'),
]

def ensure_cat(conn, name, parent_id, is_hidden=False):
    # Check exist (Case insensitive check better?)
    # Using specific names from map
    cur = conn.execute("SELECT id FROM cat_categorias WHERE parent_id=? AND LOWER(nombre)=?", (parent_id, name.lower()))
    row = cur.fetchone()
    if row:
        return row['id']
    else:
        print(f"Creating '{name}' under {parent_id}...")
        cur = conn.execute(
            "INSERT INTO cat_categorias (tipo, nombre, parent_id, activo, is_hidden) VALUES ('system', ?, ?, 1, ?) RETURNING id",
            (name, parent_id, is_hidden)
        )
        return cur.fetchone()['id']

def main():
    print("--- Categorizing Laudus Data (Postgres) ---")
    conn = get_conn()
    try:
        # 1. Setup EQUIPOS Subcats
        # We know they exist, but let's get IDs safely
        CAT_IDS['STARLINK'] = ensure_cat(conn, 'STARLINK', EQUIPOS_ID)
        CAT_IDS['MIKROTIK'] = ensure_cat(conn, 'MIKROTIK', EQUIPOS_ID)
        CAT_IDS['CELULARES'] = ensure_cat(conn, 'CELULARES', EQUIPOS_ID)
        CAT_IDS['COMPUTADORES'] = ensure_cat(conn, 'COMPUTADORES', EQUIPOS_ID)
        CAT_IDS['EQUIPOS_SIN_ASIGNAR'] = ensure_cat(conn, 'Sin Asignar', EQUIPOS_ID, is_hidden=True)

        # 2. Setup MATERIALES Subcats
        CAT_IDS['CABLES'] = ensure_cat(conn, 'Cables', MATERIALES_ID)
        CAT_IDS['CONECTORES'] = ensure_cat(conn, 'Conectores', MATERIALES_ID)
        CAT_IDS['FERRETERIA'] = ensure_cat(conn, 'Ferretería', MATERIALES_ID) # Accent check
        CAT_IDS['DUCTOS'] = ensure_cat(conn, 'Ductos', MATERIALES_ID)
        CAT_IDS['MATERIALES_SIN_ASIGNAR'] = ensure_cat(conn, 'Sin Asignar', MATERIALES_ID, is_hidden=True)

        conn.commit()
        print("Categories Ready.")

        # 3. Categorize EQUIPOS (110 + 14)
        print(f"Processing items in EQUIPOS ({EQUIPOS_ID}) and OLD ({14})...")
        cur = conn.execute("SELECT id, nombre, marca FROM cat_items WHERE categoria_id IN (?, ?)", (EQUIPOS_ID, 14))
        items = cur.fetchall()
        print(f"  Found {len(items)} items to sort.")
        
        for item in items:
            txt = f"{item['nombre']} {item['marca'] or ''}"
            target_id = CAT_IDS['EQUIPOS_SIN_ASIGNAR'] # Default
            
            for pat, key in RULES_EQUIPOS:
                if re.search(pat, txt):
                    target_id = CAT_IDS[key]
                    break
            
            conn.execute("UPDATE cat_items SET categoria_id=? WHERE id=?", (target_id, item['id']))
        
        print("  Equipos Sorted.")

        # 4. Categorize MATERIALES (106 + 19)
        print(f"Processing items in MATERIALES ({MATERIALES_ID}) and OLD ({19})...")
        cur = conn.execute("SELECT id, nombre, marca FROM cat_items WHERE categoria_id IN (?, ?)", (MATERIALES_ID, 19))
        items = cur.fetchall()
        print(f"  Found {len(items)} items to sort.")
        
        for item in items:
            txt = f"{item['nombre']} {item['marca'] or ''}"
            target_id = CAT_IDS['MATERIALES_SIN_ASIGNAR'] # Default
            
            for pat, key in RULES_MATERIALES:
                if re.search(pat, txt):
                    target_id = CAT_IDS[key]
                    break
            
            conn.execute("UPDATE cat_items SET categoria_id=? WHERE id=?", (target_id, item['id']))
            
        print("  Materiales Sorted.")
        
        # 5. Cleanup Old Cats (14, 19)
        for old_id in [14, 19]:
            # Verify no items in parent
            cur = conn.execute("SELECT count(*) as c FROM cat_items WHERE categoria_id=?", (old_id,))
            if cur.fetchone()['c'] > 0:
                print(f"Warning: Category {old_id} has items. Skipping delete.")
                continue

            # Check and delete children
            cur = conn.execute("SELECT id FROM cat_categorias WHERE parent_id=?", (old_id,))
            children = cur.fetchall()
            
            can_delete_parent = True
            for child in children:
                child_id = child['id']
                # Verify no items in child
                cur = conn.execute("SELECT count(*) as c FROM cat_items WHERE categoria_id=?", (child_id,))
                if cur.fetchone()['c'] > 0:
                    print(f"Warning: Child {child_id} of {old_id} has items. Cannot delete parent.")
                    can_delete_parent = False
                    break
                
                # Delete empty child
                print(f"  Deleting empty child {child_id}...")
                conn.execute("DELETE FROM cat_categorias WHERE id=?", (child_id,))
            
            if can_delete_parent:
                print(f"Deleting empty duplicate parent {old_id}...")
                conn.execute("DELETE FROM cat_categorias WHERE id=?", (old_id,))

        conn.commit()
        print("Done.")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
