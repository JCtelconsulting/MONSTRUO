import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# Config DB
DB_HOST = "localhost"
DB_NAME = "monstruo"
DB_USER = "monstruo"
DB_PASS = "monstruo"

def get_conn():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def migrate_structure():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("--- Iniciando Migración de Categorías ---")
        
        # 1. Definir IDs Raíz
        ROOTS = {
            'BODEGA': 6,
            'ARRIENDO': 98,
            'BAJAS': 99
        }
        
        # Verificar que existan
        for name, rid in ROOTS.items():
            cur.execute("SELECT id FROM cat_categorias WHERE id = %s", (rid,))
            if not cur.fetchone():
                print(f"Creating root {name}...")
                cur.execute("INSERT INTO cat_categorias (id, nombre, parent_id) VALUES (%s, %s, NULL) ON CONFLICT (id) DO NOTHING", (rid, name))
        
        # 2. Mover EQUIPOS (103) y MATERIALES (104) a BODEGA (6) si son root
        # Primero identificamos ramas huerfanas importantes
        TARGET_BRANCHES = ['EQUIPOS', 'MATERIALES', 'HERRAMIENTAS']
        
        for branch_name in TARGET_BRANCHES:
            # Buscar la rama huerfana (raiz actual)
            cur.execute("SELECT id FROM cat_categorias WHERE nombre = %s AND parent_id IS NULL AND id NOT IN (6, 98, 99)", (branch_name,))
            orphan_row = cur.fetchone()
            
            if orphan_row:
                orphan_id = orphan_row['id']
                print(f"Procesando rama huérfana '{branch_name}' (ID {orphan_id})...")
                
                # Check target collision under BODEGA
                cur.execute("SELECT id FROM cat_categorias WHERE nombre = %s AND parent_id = %s", (branch_name, ROOTS['BODEGA']))
                existing_target = cur.fetchone()
                
                if existing_target:
                    target_id = existing_target['id']
                    print(f"  Conflict: '{branch_name}' already exists in BODEGA (ID {target_id}). Merging...")
                    
                    # 1. Move children of orphan to target
                    try:
                        # Update parent_id of children, ignoring conflicts (if child name exists in target, strict unique constraint might fail again?)
                        # If strict unique constraint exists on (parent, name), we must recursive merge? 
                        # Let's hope first level merge is enough for now or use ON CONFLICT DO NOTHING trick not easy in UPDATE.
                        # Simple strategy: Update parent. If fail, log.
                        cur.execute("UPDATE cat_categorias SET parent_id = %s WHERE parent_id = %s", (target_id, orphan_id))
                        
                        # 2. Delete the empty orphan
                        cur.execute("DELETE FROM cat_categorias WHERE id = %s", (orphan_id,))
                        print(f"  Merged and deleted orphan {orphan_id}.")
                    except Exception as merge_err:
                        print(f"  Merge failed: {merge_err}. Skipping clean delete.")
                        conn.rollback() # Rollback logic is tricky inside transaction if not using savepoints. 
                        # Re-raise to restart script logic fix.
                        raise merge_err
                else:
                    # No collision, simple move
                    print(f"  Moving orphan {orphan_id} to BODEGA...")
                    cur.execute("UPDATE cat_categorias SET parent_id = %s WHERE id = %s", (ROOTS['BODEGA'], orphan_id))
            else:
                 # No existe rama huerfana, quizas ya esta movida o no existe.
                 # Check si existe en BODEGA, si no, crearla.
                 cur.execute("SELECT id FROM cat_categorias WHERE nombre = %s AND parent_id = %s", (branch_name, ROOTS['BODEGA']))
                 if not cur.fetchone():
                      print(f"Creando rama '{branch_name}' bajo BODEGA...")
                      cur.execute("INSERT INTO cat_categorias (nombre, parent_id) VALUES (%s, %s)", (branch_name, ROOTS['BODEGA']))

        # 3. Mirroring Recursivo y Creación de 'Sin Asignar'
        # Fuente de verdad: BODEGA (ID 6)
        # Destinos: ARRIENDO (98), BAJAS (99)
        
        print("Replicando estructura de BODEGA a ARRIENDO y BAJAS...")
        
        # Función recursiva para copiar
        def replicate_children(source_parent_id, target_parent_id):
            # Obtener hijos del source
            cur.execute("SELECT id, nombre FROM cat_categorias WHERE parent_id = %s", (source_parent_id,))
            children = cur.fetchall()
            
            # Asegurar 'Sin Asignar' si estamos en Nivel 2 (Equipos, Materiales, Herramientas)
            # Como saber si estamos en Nivel 2? Por el nombre del padre target? 
            # Mejor: Si el nombre del padre es EQUIPOS/MATERIALES/HERRAMIENTAS, creamos 'Sin Asignar'
            
            cur.execute("SELECT nombre FROM cat_categorias WHERE id = %s", (target_parent_id,))
            parent_row = cur.fetchone()
            if parent_row and parent_row['nombre'] in ['EQUIPOS', 'MATERIALES', 'HERRAMIENTAS']:
                 # Check/Create Sin Asignar
                 cur.execute("SELECT id FROM cat_categorias WHERE parent_id = %s AND nombre = 'Sin Asignar'", (target_parent_id,))
                 if not cur.fetchone():
                     print(f"  + Creando 'Sin Asignar' bajo {parent_row['nombre']} (ID {target_parent_id})...")
                     cur.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id) VALUES ('carpeta', 'Sin Asignar', %s)", (target_parent_id,))

            for child in children:
                # Skip 'Sin Asignar' logic in copy loop if handled above? 
                # Actually, if source has 'Sin Asignar', we copy it. 
                # If source DOESNT have it, we enforced it above.
                
                # Verificar si existe en target
                cur.execute("SELECT id FROM cat_categorias WHERE parent_id = %s AND nombre = %s", (target_parent_id, child['nombre']))
                target_child = cur.fetchone()
                
                target_child_id = None
                if target_child:
                    target_child_id = target_child['id']
                else:
                    # Crear
                    print(f"  + Replicando '{child['nombre']}' en nueva rama...")
                    cur.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id) VALUES ('carpeta', %s, %s) RETURNING id", (child['nombre'], target_parent_id))
                    target_child_id = cur.fetchone()['id']
                
                # Recursión
                replicate_children(child['id'], target_child_id)

        # Ejecutar replicación para Arriendo y Bajas
        replicate_children(ROOTS['BODEGA'], ROOTS['ARRIENDO'])
        replicate_children(ROOTS['BODEGA'], ROOTS['BAJAS'])
        
        # También asegurar 'Sin Asignar' en BODEGA misma (Source)
        for cat_name in ['EQUIPOS', 'MATERIALES', 'HERRAMIENTAS']:
             cur.execute("SELECT id FROM cat_categorias WHERE parent_id = %s AND nombre = %s", (ROOTS['BODEGA'], cat_name))
             cat = cur.fetchone()
             if cat:
                 cur.execute("SELECT id FROM cat_categorias WHERE parent_id = %s AND nombre = 'Sin Asignar'", (cat['id'],))
                 if not cur.fetchone():
                     print(f"Creando 'Sin Asignar' en BODEGA > {cat_name}...")
                     cur.execute("INSERT INTO cat_categorias (tipo, nombre, parent_id) VALUES ('carpeta', 'Sin Asignar', %s)", (cat['id'],))


        conn.commit()
        print("--- Migración Completada Exitosamente ---")
        
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_structure()
