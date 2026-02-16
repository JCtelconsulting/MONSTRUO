#!/usr/bin/env python3
import sys
import os
import sqlite3
import datetime

# Setup path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
sys.path.append(BASE_DIR)

from app.core import db, tickets_service

def verify_customer_linking():
    print("[TEST] Iniciando verificación de vinculación de cliente...")
    
    print("[TEST] Ejecutando migraciones (init_db)...")
    db.init_db()
    
    conn = db.get_conn()
    now_ts = datetime.datetime.now().isoformat()
    
    # 1. Crear cliente ficticio
    fake_rut = "99.999.999-K"
    fake_email = "gerente@empresa-cliente.cl"
    fake_external_id = "TEST-CLIENT-123"
    
    # Limpieza previa
    conn.execute("DELETE FROM customers WHERE rut = ?", (fake_rut,))
    conn.commit()
    
    print(f"[TEST] Creando cliente RUT {fake_rut} Email {fake_email} ID {fake_external_id}")
    try:
        conn.execute(
            """INSERT INTO customers (rut, name, email, external_id, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (fake_rut, "Empresa Cliente SpA", fake_email, fake_external_id, now_ts)
        )
        conn.commit()
    except Exception as e:
        print(f"[TEST] Error al insertar cliente: {e}")
        conn.close()
        sys.exit(1)
        
    conn.close()
    
    # 2. Crear ticket usando el email del cliente en 'origen_email'
    print("[TEST] Creando ticket con origen_email coincidente...")
    try:
        sender = f"Juan Perez <{fake_email}>"
        ticket = tickets_service.create_ticket(
            titulo="Ticket de Prueba Cliente 360",
            descripcion="Esto es un test de vinculación automática.",
            creador_id="system",
            origen_email=sender,
            severidad="media"
        )
        
        # 3. Verificar customer_id
        t_id = ticket["id"]
        customer_id = ticket.get("customer_id")
        contact_role = ticket.get("contact_role")
        
        print(f"[TEST] Ticket creado ID: {t_id}")
        print(f"[TEST] Customer ID vinculado: {customer_id}")
        
        if customer_id == fake_external_id:
            print("[TEST] SUCCESS: El ticket se vinculó correctamente al cliente.")
        else:
            print(f"[TEST] FAILURE: Se esperaba '{fake_external_id}', se obtuvo '{customer_id}'")
            sys.exit(1)
            
        # 4. Validar actualización manual de rol
        print("[TEST] Actualizando rol de contacto...")
        updated = tickets_service.update_ticket(t_id, {"contact_role": "Gerente TI"})
        if updated.get("contact_role") == "Gerente TI":
             print("[TEST] SUCCESS: Rol de contacto actualizado correctamente.")
        else:
             print("[TEST] FAILURE: No se actualizó el rol.")
             sys.exit(1)

    except Exception as e:
        print(f"[TEST] Excepción durante prueba: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
if __name__ == "__main__":
    verify_customer_linking()
