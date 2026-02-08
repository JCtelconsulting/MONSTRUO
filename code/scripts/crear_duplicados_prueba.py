import sys
import os
import json

# Add project root to path
sys.path.insert(0, "/srv/monstruo/code")

from app.core import db

def crear_datos_prueba():
    conn = db.get_conn()
    try:
        print("Conectado a DB. Verificando duplicados...")
        
        # 1. Check existing
        try:
            row = conn.execute("SELECT count(*) as cnt FROM cat_duplicados_detectados WHERE status='pendiente'").fetchone()
            cnt = row['cnt'] if row else 0
            print(f"Duplicados pendientes actuales: {cnt}")
            
            if cnt > 0:
                print("Ya existen duplicados. No se crearán nuevos.")
                return
        except Exception as e:
            print(f"Error consultando tabla duplicados (quizas no existe?): {e}")
            return

        # 2. Create Dummy Items if needed
        print("Creando items de prueba...")
        # Item A
        cur = conn.execute("""
            INSERT INTO cat_items (nombre, sku_canonico, marca, image_url, creado_at, actualizado_at, activo)
            VALUES ('Taladro Percutor Bosch GSB 13 RE', 'BOS-GSB13', 'BOSCH', 'https://m.media-amazon.com/images/I/71w+2-X+LCL._AC_SL1500_.jpg', ?, ?, 1)
            RETURNING id
        """, (db.now_utc_iso(), db.now_utc_iso()))
        id_a = cur.fetchone()['id']
        
        # Item B (Variant)
        cur = conn.execute("""
            INSERT INTO cat_items (nombre, sku_canonico, marca, image_url, creado_at, actualizado_at, activo)
            VALUES ('Taladro Percutor Bosch GSB 13 RE (Caja Carton)', 'BOS-GSB13-BOX', 'BOSCH', 'https://m.media-amazon.com/images/I/61bCWBj+7RL._AC_SL1000_.jpg', ?, ?, 1)
            RETURNING id
        """, (db.now_utc_iso(), db.now_utc_iso()))
        id_b = cur.fetchone()['id']
        
        print(f"Items creados: A={id_a}, B={id_b}")
        
        # 3. Create Duplicate Case
        conn.execute("""
            INSERT INTO cat_duplicados_detectados 
            (item_id_a, item_id_b, score, reason, status, creado_at, actualizado_at)
            VALUES (?, ?, 0.95, 'Caso de Prueba: Nombre y Marca idénticos', 'pendiente', ?, ?)
        """, (id_a, id_b, db.now_utc_iso(), db.now_utc_iso()))
        
        conn.commit()
        print("Caso de duplicado de prueba insertado correctamente.")
        
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    crear_datos_prueba()
