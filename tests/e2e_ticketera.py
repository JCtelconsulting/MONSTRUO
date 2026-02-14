
import requests
import json
import os
import sys

# BASE_URL = "http://localhost:8000/api/tks"
# HEADERS = {"x-token": "..."} # Necesitaríamos un token válido o mockear auth
# Para este E2E, asumiremos que se corre localmente y quizás necesitemos un token de admin o similar.
# O mejor, usamos validación directa contra los servicios si es script interno, 
# pero idealmente debe probar la API.

# SUposiciones:
# - Servidor corriendo en puerto default (verificar .env o main.py)
# - User 'juan.lopez' existe (o usar uno valido)

API_URL = "http://localhost:8081/api/tks" # Asumiendo puerto 8081 por configs previas o default
USERNAME = "juan.lopez" # Mock user header for dev/testing if auth allows
# En main.py, deps.get_current_user valida token. 
# Para testear sin auth real, necesitamos un token válido o modificar main.py temporalmente, 
# O (mejor) usar una función de login si existe.

# Dado que no tengo pass de juan.lopez a mano (se reseteó en otra task), 
# voy a usar un enfoque de "Test Unitario de Integración" importando los servicios directamente 
# para probar la lógica sin depender de levantar el servidor HTTP completo en este script.
# Esto es más robusto para verificar la lógica implementada rápidamente.

import sys
from pathlib import Path
import os

# Adjust path for container vs host
if os.path.exists("/app/code"):
    sys.path.append("/app/code")
elif os.path.exists("/srv/monstruo_dev/code"):
    sys.path.append("/srv/monstruo_dev/code")

# Fix for DB_URL inside container
if os.getenv("DB_URL") is None:
    # Fallback to internal docker name if not set
    # Try typical docker service names
    os.environ["DB_URL"] = "postgresql://monstruo:monstruo@monstruo-dev-postgres:5432/monstruo" 
    # Or just 'db' if that is the service name, but 'monstruo-dev-postgres' is the container name which usually resolves in custom networks too.
    # But better to rely on what's set in the container or passed.

from app.core import tickets_service, db
from app.core import config
# Mock UploadFile is needed if we are running the script as standalone
from fastapi import UploadFile

def run_e2e():
    print("=== INICIANDO E2E TICKETERA EPIC 11 ===")
    
    # 1. Verificar Config
    print(f"[CHECK] ENV_TYPE: {config.settings.ENV_TYPE}")
    if config.settings.ENV_TYPE == 'prod':
        print("[WARN] Corriendo en PROD? Cuidado con los correos reales.")
    else:
        print("[OK] Corriendo en DEV/TEST.")

    # 2. Crear Ticket
    print("\n[STEP 1] Creando Ticket...")
    tk_data = tickets_service.create_ticket(
        titulo="Test E2E Attachments",
        descripcion="Prueba de concepto para adjuntos y respuesta",
        creador_id="test_script",
        categoria="sistemas",
        origen_email="cliente.test@example.com",
        cliente_nombre="Cliente Test"
    )
    ticket_id = tk_data['id']
    print(f"[OK] Ticket creado: #{ticket_id} (Código: {tk_data['codigo']})")

    # 3. Simular Respuesta con Adjunto
    print("\n[STEP 2] Respondiendo con Adjunto...")
    
    # Crear archivo dummy
    dummy_path = "/tmp/e2e_test.txt"
    with open(dummy_path, "w") as f:
        f.write("Este es un archivo de prueba adjunto.")
    
    # Mock UploadFile
    class MockUploadFile:
        def __init__(self, path, filename):
            self.file = open(path, "rb")
            self.filename = filename
            self.content_type = "text/plain"

    files = [MockUploadFile(dummy_path, "prueba.txt")]
    
    try:
        reply_res = tickets_service.reply_ticket_email(
            ticket_id=ticket_id,
            author_id="juan.lopez",
            mensaje="Hola cliente, te adjunto el archivo.",
            asunto=None,
            files=files
        )
        print(f"[OK] Respuesta enviada. Meta: {reply_res}")
    except Exception as e:
        print(f"[FAIL] Error respondiendo: {e}")
        return

    # 4. Verificar Historial de Correos
    print("\n[STEP 3] Verificando Historial...")
    emails = tickets_service.get_ticket_emails(ticket_id)
    if not emails:
        print("[FAIL] No se encontraron correos en historial.")
    else:
        last_email = emails[0]
        print(f"[OK] {len(emails)} correos encontrados.")
        print(f"      Último subject: {last_email['subject']}")
        print(f"      Adjuntos JSON: {last_email['attachments_json']}")
        
        if "prueba.txt" in last_email['attachments_json']:
             print("[OK] Adjunto encontrado en metadata.")
        else:
             print("[FAIL] Adjunto NO encontrado en metadata.")

    # 5. Simulando Incoming Reply (Threading)
    print("\n[STEP 4] Simulando Respuesta Cliente (Threading)...")
    msg_id = reply_res.get('message_id') or f"<test-e2e-{ticket_id}@monstruo.local>"
    
    incoming_data = {
        "sender": "cliente.test@example.com",
        "subject": f"Re: {reply_res['subject']}",
        "body": "Gracias, recibido.",
        "in_reply_to": msg_id,
        "references": msg_id,
        "message_id": f"<reply-{ticket_id}@client.com>"
    }
    
    # Llamamos a handle_incoming_email (necesitamos importar)
    # Nota: handle_incoming_email está en tickets_service o jobs? Está en tickets_service.
    
    try:
        tickets_service.handle_incoming_email(incoming_data)
        print("[OK] Email entrante procesado.")
    except Exception as e:
         print(f"[FAIL] Error procesando entrante: {e}")

    # Verificar que se agregó al mismo ticket
    print("\n[STEP 5] Verificando Threading...")
    updated_emails = tickets_service.get_ticket_emails(ticket_id)
    if len(updated_emails) > len(emails):
        print(f"[OK] Nuevo correo detectado en ticket #{ticket_id}.")
        print(f"      Total correos: {len(updated_emails)}")
    else:
        print(f"[FAIL] El correo entrante no se asoció al ticket #{ticket_id}.")

    print("\n=== E2E FINALIZADO ===")

if __name__ == "__main__":
    run_e2e()
