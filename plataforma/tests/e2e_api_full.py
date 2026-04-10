#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from _helpers import as_json, build_session, env_str, guard_prod_target, require_credentials


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="E2E API full smoke")
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

    try:
        who = session.get(f"{base_url}/api/auth/whoami", timeout=args.timeout)
        ensure_200("whoami", who.status_code, who.text)
        who_data = as_json(who)
        if not who_data.get("logged"):
            return fail(f"Sesion no activa: {who_data}")
        print("[OK] whoami")

        ticket_payload = {
            "titulo": f"E2E API Full {int(time.time())}",
            "descripcion": "Smoke E2E API completa",
            "tipo": "incidencia",
            "severidad": "media",
            "categoria": "sistemas",
        }
        create = session.post(f"{base_url}/api/tks/tickets", json=ticket_payload, timeout=args.timeout)
        ensure_200("Crear ticket", create.status_code, create.text)
        ticket = as_json(create)
        ticket_id = ticket["id"]
        ticket_code = ticket.get("codigo")
        print(f"[OK] Ticket creado: {ticket_code} (id={ticket_id})")

        detail = session.get(f"{base_url}/api/tks/tickets/{ticket_id}", timeout=args.timeout)
        ensure_200("Detalle ticket", detail.status_code, detail.text)
        print("[OK] Detalle ticket")

        claim = session.patch(
            f"{base_url}/api/tks/tickets/{ticket_id}",
            json={"asignado_a": args.user, "estado": "en_progreso"},
            timeout=args.timeout,
        )
        ensure_200("Tomar ticket", claim.status_code, claim.text)
        print("[OK] Ticket tomado para acciones de ejecución")

        add_event = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/eventos",
            json={"evento": "comentario", "detalle": "Comentario E2E API full"},
            timeout=args.timeout,
        )
        ensure_200("Agregar evento", add_event.status_code, add_event.text)
        print("[OK] Evento agregado")

        timeline = session.get(f"{base_url}/api/tks/tickets/{ticket_id}/eventos", timeout=args.timeout)
        ensure_200("Timeline", timeline.status_code, timeline.text)
        timeline_items = as_json(timeline).get("items", [])
        if not timeline_items:
            return fail("Timeline vacio")
        print(f"[OK] Timeline con {len(timeline_items)} eventos")

        patch = session.patch(
            f"{base_url}/api/tks/tickets/{ticket_id}",
            json={"estado": "en_progreso"},
            timeout=args.timeout,
        )
        ensure_200("Actualizar ticket", patch.status_code, patch.text)
        print("[OK] Estado actualizado a en_progreso")

        stats = session.get(f"{base_url}/api/tks/stats", timeout=args.timeout)
        ensure_200("Stats", stats.status_code, stats.text)
        print("[OK] Stats")

        listing = session.get(
            f"{base_url}/api/tks/tickets",
            params={"q": ticket_code, "limit": 20},
            timeout=args.timeout,
        )
        ensure_200("Listado", listing.status_code, listing.text)
        items = as_json(listing).get("items", [])
        if not any(int(row.get("id", -1)) == int(ticket_id) for row in items):
            return fail(f"Ticket {ticket_id} no encontrado en listado filtrado")
        print("[OK] Listado filtrado")

        print("[SUCCESS] E2E API full PASS")
        return 0
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
