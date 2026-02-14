#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from _helpers import as_json, build_session, env_str, guard_prod_target, require_credentials


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="E2E Ticketera: create -> reply -> dedupe -> emails")
    ap.add_argument(
        "--base-url",
        default=env_str("MONSTRUO_TEST_BASE_URL", "http://127.0.0.1:9001"),
        help="URL base del API, ejemplo: http://127.0.0.1:9001",
    )
    ap.add_argument("--user", default=env_str("MONSTRUO_TEST_USER"))
    ap.add_argument("--password", default=env_str("MONSTRUO_TEST_PASSWORD"))
    ap.add_argument("--timeout", type=int, default=int(env_str("MONSTRUO_TEST_TIMEOUT", "15") or "15"))
    ap.add_argument("--allow-prod", action="store_true", help="Permite ejecutar si la URL parece PROD")
    return ap.parse_args()


def fail(message: str) -> int:
    print(f"[FAIL] {message}")
    return 1


def ensure_200(label: str, status_code: int, body: str) -> None:
    if status_code != 200:
        raise RuntimeError(f"{label}: HTTP {status_code} -> {body}")


def iter_attachment_text(payload: object) -> Iterable[str]:
    if isinstance(payload, str):
        yield payload
        return
    if isinstance(payload, list):
        for item in payload:
            yield str(item)
        return
    if isinstance(payload, dict):
        for value in payload.values():
            yield str(value)


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        guard_prod_target(base_url, allow_prod=args.allow_prod)
        require_credentials(args.user, args.password)
        auth = build_session(base_url, args.user, args.password, timeout=args.timeout)
    except Exception as exc:
        return fail(str(exc))

    session = auth["session"]
    print(f"[OK] Login: {auth['login'].get('name', args.user)}")

    ticket_payload = {
        "titulo": f"E2E Ticketera {int(time.time())}",
        "descripcion": "Prueba E2E profesional Ticketera",
        "tipo": "incidencia",
        "severidad": "media",
        "categoria": "sistemas",
        "origen_email": "cliente.e2e@example.com",
        "cliente_nombre": "Cliente E2E",
    }
    try:
        create_resp = session.post(
            f"{base_url}/api/tks/tickets",
            json=ticket_payload,
            timeout=args.timeout,
        )
        ensure_200("Crear ticket", create_resp.status_code, create_resp.text)
        ticket = as_json(create_resp)
        ticket_id = ticket["id"]
        print(f"[OK] Ticket creado: {ticket.get('codigo')} (id={ticket_id})")
    except Exception as exc:
        return fail(str(exc))

    temp_path = None
    attachment_name = "ticketera_e2e.txt"
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
            tmp.write("Adjunto de prueba E2E Ticketera.")
            temp_path = tmp.name

        with open(temp_path, "rb") as handle:
            first_reply = session.post(
                f"{base_url}/api/tks/tickets/{ticket_id}/reply-email",
                files=[("files", (attachment_name, handle, "text/plain"))],
                data={"mensaje": "Respuesta E2E con adjunto", "asunto": "Re: E2E Ticketera"},
                timeout=args.timeout,
            )
        ensure_200("Primer reply", first_reply.status_code, first_reply.text)
        first_payload = as_json(first_reply)
        print("[OK] Primer reply enviado")

        with open(temp_path, "rb") as handle:
            second_reply = session.post(
                f"{base_url}/api/tks/tickets/{ticket_id}/reply-email",
                files=[("files", (attachment_name, handle, "text/plain"))],
                data={"mensaje": "Respuesta E2E con adjunto", "asunto": "Re: E2E Ticketera"},
                timeout=args.timeout,
            )
        ensure_200("Segundo reply (dedupe)", second_reply.status_code, second_reply.text)
        second_payload = as_json(second_reply)
        if second_payload.get("duplicate_skipped") is not True:
            return fail(f"Dedupe no activo: {second_payload}")
        print(f"[OK] Dedupe activo: {second_payload.get('message', 'sin mensaje')}")

        # --- 4. Incoming Thread Match (Simulado via Docker) ---
        # Capturamos el message_id del primer envío para simular una respuesta.
        last_msg_id = first_payload.get("message_id")
        if not last_msg_id:
            print("[WARN] No se capturó message_id en el reply saliente. Intentando obtenerlo del ticket...")
            # Fallback: consultar el ticket para ver si tiene email_thread_id
            t_resp = session.get(f"{base_url}/api/tks/tickets/{ticket_id}", timeout=args.timeout)
            if t_resp.status_code == 200:
                last_msg_id = t_resp.json().get("email_thread_id")

        if not last_msg_id:
            return fail("No se pudo obtener message_id para probar threading (incoming match).")

        print(f"[INFO] Thread ID capturado: {last_msg_id}")

        # Script python a ejecutar DENTRO del contenedor API
        # Nota: Usamos 'app.core.tickets_service' directamente
        inner_script = f"""
import sys
import logging
# Configurar logging basico para ver errores
logging.basicConfig(level=logging.INFO)
from app.core import tickets_service

payload = {{
    'subject': 'Re: E2E Ticketera Reply',
    'sender': 'cliente.e2e@example.com',
    'body': 'Esta es una respuesta simulada del cliente que DEBE agruparse.',
    'message_id': '<incoming-test-{int(time.time())}@example.com>',
    'in_reply_to': '{last_msg_id}',
    'references': '{last_msg_id}'
}}

print(f"Simulando incoming email para thread: {{payload['in_reply_to']}}")
try:
    tickets_service.handle_incoming_email(payload)
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {{e}}")
    sys.exit(1)
"""
        # Ejecutar docker exec
        # Asumimos que el contenedor se llama 'monstruo_dev-api-1' o similar, pero mejor usar docker compose si es posible.
        # Sin embargo, desde el host 'monstruo_dev' es el prefijo.
        # Intentaremos identificar el contenedor o usar docker compose exec.
        # El usuario pidió: docker compose --env-file .env.server.dev exec -T api python ...
        
        cmd = [
            "docker", "compose", "--env-file", ".env.server.dev", 
            "exec", "-T", "api", "python3", "-c", inner_script
        ]
        
        print("[INFO] Ejecutando simulación de correo entrante en contenedor API...")
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        
        if proc.returncode != 0:
            print(f"[FAIL] Falló ejecución docker: {proc.stderr}")
            return fail("Error simulando incoming email")
        
        if "SUCCESS" not in proc.stdout:
            print(f"[FAIL] Script interno falló: {proc.stdout} // {proc.stderr}")
            return fail("Simulación incoming email no reportó SUCCESS")

        print("[OK] Simulación incoming ejecutada.")

        # --- Verificación ---
        # Consultar historial nuevamente para ver si apareció el correo entrante
        time.sleep(2) # Breve espera extra
        emails_resp = session.get(f"{base_url}/api/tks/tickets/{ticket_id}/emails", timeout=args.timeout)
        ensure_200("Historial de correos (post-incoming)", emails_resp.status_code, emails_resp.text)
        items = as_json(emails_resp).get("items", [])
        
        incoming_found = False
        for email in items:
            # Case insensitive check or just match what we sent
            if email.get("direction") == "incoming" and "respuesta simulada" in str(email.get("body_html", "")).lower():
                incoming_found = True
                break
        
        if not incoming_found:
            return fail(f"No se encontró el correo entrante agrupado en el ticket {ticket_id}.")

        print("[OK] Incoming Thread Match VERIFICADO (Correo entrante apareció en el historial).")

        # --- Fin Verificación ---

        # Reset items variable for attachment check (which was original code)
        # We can re-use 'items' from the latest fetch which is more complete
        
        found_attachment = False
        for email in items:
            if str(email.get("direction", "")).lower() != "outgoing":
                continue
            for text in iter_attachment_text(email.get("attachments_json")):
                if attachment_name in text:
                    found_attachment = True
                    break
            if found_attachment:
                break

        if not found_attachment:
            return fail(f"No se encontro adjunto '{attachment_name}' en historial")

        print(f"[OK] Historial validado (Outgoing + Incoming). Correos totales: {len(items)}")
        print("[SUCCESS] E2E Ticketera PASS")
        return 0
    except Exception as exc:
        return fail(str(exc))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    raise SystemExit(main())
