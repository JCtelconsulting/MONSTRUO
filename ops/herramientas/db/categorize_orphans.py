
import sys
import os
import re

# Ensure path to access app code
sys.path.append(os.path.join(os.getcwd(), "code"))
from app.core.db import get_conn

# Configuration: Parent Category IDs (based on previous investigation)
# EQUIPOS: 110
# MATERIALES: 19
# HERRAMIENTAS: 11
# FERRETERIA: 9
# SEGURIDAD: 25 (Using for Insumos/EPP if matches)
# OTROS: 27

CATEGORY_MAP = {
    'EQUIPOS': 110,
    'MATERIALES': 19,
    'HERRAMIENTAS': 11,
    'FERRETERIA': 9,
    'SEGURIDAD': 25,
    'OTROS': 27
}

# Regex Rules (Order matters)
RULES = [
    # EQUIPOS
    (r'(?i)(antena|router|switch|starlink|camara|camera|dvr|nvr|notebook|laptop|computador|pc|cpu|monitor|teclado|mouse|celular|smartphone|tablet|telefono|ubiquiti|mikrotik|cisco|huawei|epson|impresora)', 'EQUIPOS'),
    
    # MATERIALES (Cables, conectores)
    (r'(?i)(cable|alambre|cordon|utp|fibra|optica|patch|cord|conector|rj45|jack|plug|modulare|faceplate|canaleta|ducto|tubo|pvc|conduit)', 'MATERIALES'),
    
    # FERRETERIA (Tornillos, fijaciones)
    (r'(?i)(tornillo|perno|tuerca|golilla|tarugo|clavo|fijacion|sopor|abrazadera|riel|perfil|fierro|metal|soldadura|electrodo|disco|corte|lija)', 'FERRETERIA'),
    
    # HERRAMIENTAS
    (r'(?i)(taladro|martillo|alicate|destornillador|llave|sierra|esmeril|cautin|tester|multimetro|crimpeadora|pelacable|herramienta|broca|punta)', 'HERRAMIENTAS'),
    
    # SEGURIDAD/INSUMOS
    (r'(?i)(guante|lente|casco|zapato|chaleco|overol|respirador|mascarilla|filtro|arnes|cuerda|tinta|toner|papel|servilleta|limpiador|alcohol|jabon)', 'SEGURIDAD'),
]

# Source Category to migrate FROM (The orphans)
SOURCE_CAT_ID = 8

def ensure_hidden_subcat(conn, parent_id):
    """
    Finds or creates a 'Sin Asignar' child category under parent_id.
    Ensures it is hidden.
    """
    cur = conn.execute("SELECT id, is_hidden FROM cat_categorias WHERE nombre='Sin Asignar' AND parent_id=?", (parent_id,))
    row = cur.fetchone()
    
    if row:
        cat_id = row['id']
        if not row['is_hidden']:
             print(f"  Fixing visibility for 'Sin Asignar' (ID: {cat_id})...")
             conn.execute("UPDATE cat_categorias SET is_hidden=? WHERE id=?", (True, cat_id))
        return cat_id
    else:
        print(f"  Creating 'Sin Asignar' under Parent {parent_id}...")
        cur = conn.execute(
            "INSERT INTO cat_categorias (tipo, nombre, parent_id, activo, is_hidden) VALUES ('system', 'Sin Asignar', ?, 1, ?) RETURNING id",
            (parent_id, True)
        )
        return cur.fetchone()['id']

def main():
    print("--- Starting Orphan Categorization ---")
    conn = get_conn()
    try:
        # 1. Prepare Destination Map (Parent Name -> Sin Asignar ID)
        print("Preparing destinations...")
        dest_ids = {}
        for name, parent_id in CATEGORY_MAP.items():
            # Verify parent exists
            cur = conn.execute("SELECT id FROM cat_categorias WHERE id=?", (parent_id,))
            if cur.fetchone():
                dest_ids[name] = ensure_hidden_subcat(conn, parent_id)
            else:
                print(f"WARNING: Parent category {name} (ID {parent_id}) not found. Skipping.")

        # 2. Fetch Orphans
        print(f"Fetching items from category {SOURCE_CAT_ID}...")
        cur = conn.execute("SELECT id, nombre, marca FROM cat_items WHERE categoria_id=?", (SOURCE_CAT_ID,))
        items = cur.fetchall()
        print(f"Found {len(items)} orphans.")

        count_moved = 0
        
        for item in items:
            item_id = item['id']
            # Quick normalize
            text = f"{item['nombre']} {item['marca'] or ''}".strip()
            
            target_cat = None
            
            # Match Rules
            for pattern, cat_key in RULES:
                if re.search(pattern, text):
                    if cat_key in dest_ids:
                        target_cat = dest_ids[cat_key]
                        break
            
            # Fallback to OTROS > Sin Asignar if no match?
            # Or just leave them in source?
            # User said "Resto -> Bodega > Sin Asignar"
            # We don't have a specific "Bodega > Sin Asignar" distinct from the source ID 8?
            # Actually, ID 8 IS "Sin Clasificar" (orphaned). 
            # We should probably enable ID 8 to be the "General Sin Asignar"?
            # OR move them to Equipos > Sin Asignar as a default?
            # User said: "lo que no esten en las categorias ... aparescan sin asignar"
            # Let's move unmatched to OTROS > Sin Asignar (ID 27) for now so they are at least somewhere valid.
            
            if not target_cat:
                # Default to OTROS
                if 'OTROS' in dest_ids:
                    target_cat = dest_ids['OTROS']

            if target_cat:
                conn.execute("UPDATE cat_items SET categoria_id=? WHERE id=?", (target_cat, item_id))
                count_moved += 1
                if count_moved % 100 == 0:
                    print(f"  Processed {count_moved} items...")

        conn.commit()
        print(f"Map complete. Moved {count_moved} items.")
        
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
