#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from _helpers import as_json, build_session, env_str, guard_prod_target, require_credentials


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="E2E Ticketera: workflow + approvals + reply + dedupe + incoming thread")
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


def ensure_status(label: str, status_code: int, body: str, expected: Iterable[int]) -> None:
    if status_code not in set(expected):
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


def make_idem(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def create_ticket(session, base_url: str, timeout: int, payload: Dict[str, object]) -> Dict[str, object]:
    resp = session.post(f"{base_url}/api/tks/tickets", json=payload, timeout=timeout)
    ensure_status("Crear ticket", resp.status_code, resp.text, {200})
    tk = as_json(resp)
    if not tk.get("id"):
        raise RuntimeError(f"Crear ticket sin id: {tk}")
    if not tk.get("subestado"):
        raise RuntimeError(f"Crear ticket sin subestado: {tk}")
    return tk


def transition_ticket(session, base_url: str, timeout: int, ticket_id: int, to_subestado: str, motivo: str, idem: Optional[str] = None, expected: Iterable[int] = (200,)):
    headers = {"Idempotency-Key": idem} if idem else {}
    resp = session.post(
        f"{base_url}/api/tks/tickets/{ticket_id}/transitions",
        json={"to_subestado": to_subestado, "motivo": motivo},
        headers=headers,
        timeout=timeout,
    )
    ensure_status(f"Transition {to_subestado}", resp.status_code, resp.text, expected)
    return as_json(resp) if resp.status_code == 200 else {"raw": resp.text}


def approve_change(session, base_url: str, timeout: int, ticket_id: int, step: int, decision: str, note: str = "", idem: Optional[str] = None, expected: Iterable[int] = (200,)):
    headers = {"Idempotency-Key": idem} if idem else {}
    resp = session.post(
        f"{base_url}/api/tks/tickets/{ticket_id}/approvals",
        json={"step": step, "decision": decision, "decision_note": note},
        headers=headers,
        timeout=timeout,
    )
    ensure_status(f"Approval step {step} ({decision})", resp.status_code, resp.text, expected)
    return as_json(resp) if resp.status_code == 200 else {"raw": resp.text}


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

    # ------------------------------------------------------------
    # 1) Workflow por tipo + aprobaciones + idempotencia
    # ------------------------------------------------------------
    try:
        inc = create_ticket(session, base_url, args.timeout, {
            "titulo": f"E2E Incidencia {int(time.time())}",
            "descripcion": "Flujo incidencia",
            "tipo": "incidencia",
            "severidad": "alta",
            "categoria": "sistemas",
        })
        req = create_ticket(session, base_url, args.timeout, {
            "titulo": f"E2E Requerimiento {int(time.time())}",
            "descripcion": "Flujo requerimiento",
            "tipo": "requerimiento",
            "severidad": "media",
            "categoria": "admin",
        })
        chg = create_ticket(session, base_url, args.timeout, {
            "titulo": f"E2E Cambio {int(time.time())}",
            "descripcion": "Flujo cambio con doble aprobación",
            "tipo": "cambio",
            "severidad": "critica",
            "categoria": "sistemas",
        })
        print(f"[OK] Tickets creados: inc={inc['id']} req={req['id']} chg={chg['id']}")

        # Incidencia
        transition_ticket(session, base_url, args.timeout, inc["id"], "triage", "triage inicial", idem=make_idem("inc-triage"))
        transition_ticket(session, base_url, args.timeout, inc["id"], "en_progreso", "tomado", idem=make_idem("inc-work"))
        transition_ticket(session, base_url, args.timeout, inc["id"], "resuelto", "resuelto", idem=make_idem("inc-res"))
        transition_ticket(session, base_url, args.timeout, inc["id"], "cerrado", "cerrado", idem=make_idem("inc-close"))

        # Idempotencia de transición
        idem_reopen = make_idem("inc-reopen")
        first_reopen = transition_ticket(session, base_url, args.timeout, inc["id"], "reabierto", "reapertura", idem=idem_reopen)
        second_reopen = transition_ticket(session, base_url, args.timeout, inc["id"], "reabierto", "reapertura", idem=idem_reopen)
        if not second_reopen.get("duplicate_skipped"):
            return fail(f"Idempotencia transición no activa: {second_reopen}")
        print("[OK] Idempotencia transición activa")

        # Requerimiento
        transition_ticket(session, base_url, args.timeout, req["id"], "en_analisis", "analisis", idem=make_idem("req-ana"))
        transition_ticket(session, base_url, args.timeout, req["id"], "en_progreso", "en curso", idem=make_idem("req-work"))
        transition_ticket(session, base_url, args.timeout, req["id"], "en_validacion", "validacion", idem=make_idem("req-val"))
        transition_ticket(session, base_url, args.timeout, req["id"], "cerrado", "cerrado", idem=make_idem("req-close"))

        # Cambio + doble aprobación
        transition_ticket(session, base_url, args.timeout, chg["id"], "en_analisis", "analisis de cambio", idem=make_idem("chg-ana"))
        transition_ticket(session, base_url, args.timeout, chg["id"], "pendiente_aprobacion_1", "solicita paso 1", idem=make_idem("chg-p1"))

        blocked = session.post(
            f"{base_url}/api/tks/tickets/{chg['id']}/transitions",
            json={"to_subestado": "en_ejecucion", "motivo": "debería bloquear"},
            timeout=args.timeout,
        )
        ensure_status("Bloqueo cambio sin aprobaciones", blocked.status_code, blocked.text, {400})
        print("[OK] Bloqueo de ejecución sin doble aprobación")

        idem_ap1 = make_idem("chg-ap1")
        approve_change(session, base_url, args.timeout, chg["id"], 1, "approved", note="ok paso 1", idem=idem_ap1)
        dup_ap1 = approve_change(session, base_url, args.timeout, chg["id"], 1, "approved", note="dup", idem=idem_ap1)
        if not dup_ap1.get("duplicate_skipped"):
            return fail(f"Idempotencia aprobación paso1 no activa: {dup_ap1}")

        approve_change(session, base_url, args.timeout, chg["id"], 2, "approved", note="ok paso 2", idem=make_idem("chg-ap2"))
        transition_ticket(session, base_url, args.timeout, chg["id"], "en_ejecucion", "ejecutando", idem=make_idem("chg-exec"))
        transition_ticket(session, base_url, args.timeout, chg["id"], "en_validacion", "validando", idem=make_idem("chg-val"))
        transition_ticket(session, base_url, args.timeout, chg["id"], "cerrado", "cerrado", idem=make_idem("chg-close"))
        print("[OK] Workflow + doble aprobación validado")
    except Exception as exc:
        return fail(str(exc))

    # ------------------------------------------------------------
    # 2) Reply + dedupe + incoming thread match
    # ------------------------------------------------------------
    temp_path = None
    attachment_name = "ticketera_e2e.txt"
    try:
        email_ticket = create_ticket(session, base_url, args.timeout, {
            "titulo": f"E2E Ticketera Correo {int(time.time())}",
            "descripcion": "Prueba E2E profesional Ticketera",
            "tipo": "incidencia",
            "severidad": "media",
            "categoria": "sistemas",
            "origen_email": "cliente.e2e@example.com",
            "cliente_nombre": "Cliente E2E",
        })
        ticket_id = email_ticket["id"]

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
        ensure_status("Primer reply", first_reply.status_code, first_reply.text, {200})
        first_payload = as_json(first_reply)

        with open(temp_path, "rb") as handle:
            second_reply = session.post(
                f"{base_url}/api/tks/tickets/{ticket_id}/reply-email",
                files=[("files", (attachment_name, handle, "text/plain"))],
                data={"mensaje": "Respuesta E2E con adjunto", "asunto": "Re: E2E Ticketera"},
                timeout=args.timeout,
            )
        ensure_status("Segundo reply dedupe", second_reply.status_code, second_reply.text, {200})
        second_payload = as_json(second_reply)
        if second_payload.get("duplicate_skipped") is not True:
            return fail(f"Dedupe correo no activo: {second_payload}")
        print("[OK] Dedupe de correo activo")

        last_msg_id = first_payload.get("message_id")
        if not last_msg_id:
            t_resp = session.get(f"{base_url}/api/tks/tickets/{ticket_id}", timeout=args.timeout)
            if t_resp.status_code == 200:
                last_msg_id = t_resp.json().get("email_thread_id")
        if not last_msg_id:
            return fail("No se pudo obtener message_id para incoming thread match")

        inner_script = f"""
import sys
import logging
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

try:
    tickets_service.handle_incoming_email(payload)
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {{e}}')
    sys.exit(1)
"""
        cmd = [
            "docker", "compose", "--env-file", ".env.server.dev",
            "exec", "-T", "api", "python3", "-c", inner_script
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if proc.returncode != 0 or "SUCCESS" not in proc.stdout:
            return fail(f"Error simulando incoming email: {proc.stdout} // {proc.stderr}")

        time.sleep(2)
        emails_resp = session.get(f"{base_url}/api/tks/tickets/{ticket_id}/emails?format=human", timeout=args.timeout)
        ensure_status("Historial de correos", emails_resp.status_code, emails_resp.text, {200})
        items = as_json(emails_resp).get("items", [])

        incoming_found = any(
            (em.get("direction") == "incoming" and "respuesta simulada" in str(em.get("body_text", "")).lower())
            for em in items
        )
        if not incoming_found:
            return fail("No se encontró correo entrante agrupado")

        found_attachment = False
        for email in items:
            if str(email.get("direction", "")).lower() != "outgoing":
                continue
            for text in iter_attachment_text(email.get("attachments") or email.get("attachments_json")):
                if attachment_name in text:
                    found_attachment = True
                    break
            if found_attachment:
                break

        if not found_attachment:
            return fail(f"No se encontró adjunto '{attachment_name}' en historial")

        print("[OK] Reply + dedupe + incoming thread match validados")
    except Exception as exc:
        return fail(str(exc))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    # ------------------------------------------------------------
    # 3) SLA metrics/breaches API contract
    # ------------------------------------------------------------
    try:
        metrics = session.get(f"{base_url}/api/tks/sla/metrics", timeout=args.timeout)
        ensure_status("SLA metrics", metrics.status_code, metrics.text, {200})
        metrics_body = as_json(metrics)
        required_keys = {
            "frt_on_time",
            "frt_breached",
            "ttr_on_time",
            "ttr_breached",
            "aging_buckets",
            "sla_mode",
            "escalation_windows_pct",
            "business_hours",
        }
        missing = sorted([k for k in required_keys if k not in metrics_body])
        if missing:
            return fail(f"SLA metrics sin llaves esperadas: {missing}")

        frt_breaches = session.get(f"{base_url}/api/tks/sla/breaches?breach_type=frt&limit=20", timeout=args.timeout)
        ensure_status("SLA breaches FRT", frt_breaches.status_code, frt_breaches.text, {200})
        ttr_breaches = session.get(f"{base_url}/api/tks/sla/breaches?breach_type=ttr&limit=20", timeout=args.timeout)
        ensure_status("SLA breaches TTR", ttr_breaches.status_code, ttr_breaches.text, {200})
        print("[OK] Contrato SLA metrics/breaches validado")
    except Exception as exc:
        return fail(str(exc))

    # ------------------------------------------------------------
    # 4) Compliance core (retención + legal hold + export + hash-chain)
    # ------------------------------------------------------------
    try:
        cmp_ticket = create_ticket(session, base_url, args.timeout, {
            "titulo": f"E2E Compliance {int(time.time())}",
            "descripcion": "Validación de compliance core",
            "tipo": "incidencia",
            "severidad": "media",
            "categoria": "sistemas",
            "ticket_security_class": "public",
        })
        cmp_ticket_id = int(cmp_ticket["id"])

        transition_ticket(session, base_url, args.timeout, cmp_ticket_id, "triage", "triage compliance", idem=make_idem("cmp-triage"))
        transition_ticket(session, base_url, args.timeout, cmp_ticket_id, "en_progreso", "trabajo compliance", idem=make_idem("cmp-work"))
        transition_ticket(session, base_url, args.timeout, cmp_ticket_id, "resuelto", "resuelto compliance", idem=make_idem("cmp-res"))
        transition_ticket(session, base_url, args.timeout, cmp_ticket_id, "cerrado", "cerrado compliance", idem=make_idem("cmp-close"))

        cmp_detail = session.get(f"{base_url}/api/tks/tickets/{cmp_ticket_id}", timeout=args.timeout)
        ensure_status("Detalle ticket compliance", cmp_detail.status_code, cmp_detail.text, {200})
        cmp_body = as_json(cmp_detail)
        if not cmp_body.get("retention_until"):
            return fail(f"Ticket compliance sin retention_until: {cmp_body}")
        if int(cmp_body.get("retention_days_snapshot") or 0) <= 0:
            return fail(f"Ticket compliance sin retention_days_snapshot válido: {cmp_body}")

        hold_resp = session.post(
            f"{base_url}/api/tks/compliance/legal-holds",
            json={"ticket_id": cmp_ticket_id, "reason": "Investigación e2e", "case_ref": "E2E-CASE-001"},
            timeout=args.timeout,
        )
        ensure_status("Crear legal hold", hold_resp.status_code, hold_resp.text, {200})
        hold_item = as_json(hold_resp).get("item", {})
        hold_id = hold_item.get("id")
        if not hold_id:
            return fail(f"Legal hold sin id: {hold_item}")

        holds_list = session.get(
            f"{base_url}/api/tks/compliance/legal-holds?ticket_id={cmp_ticket_id}&active=true",
            timeout=args.timeout,
        )
        ensure_status("Listar legal holds activos", holds_list.status_code, holds_list.text, {200})
        active_items = as_json(holds_list).get("items", [])
        if not any(int(i.get("id") or 0) == int(hold_id) for i in active_items):
            return fail(f"Legal hold creado no aparece activo: {active_items}")

        release_resp = session.post(
            f"{base_url}/api/tks/compliance/legal-holds/{hold_id}/release",
            json={"release_note": "Cierre de investigación e2e"},
            timeout=args.timeout,
        )
        ensure_status("Liberar legal hold", release_resp.status_code, release_resp.text, {200})

        export_key = make_idem("cmp-export")
        from_ts = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        to_ts = datetime.now(timezone.utc).isoformat()
        export_resp = session.post(
            f"{base_url}/api/tks/compliance/exports/run",
            json={"from_ts": from_ts, "to_ts": to_ts, "scope": "both"},
            headers={"Idempotency-Key": export_key},
            timeout=max(args.timeout, 30),
        )
        ensure_status("Run compliance export", export_resp.status_code, export_resp.text, {200})
        export_dup = session.post(
            f"{base_url}/api/tks/compliance/exports/run",
            json={"from_ts": from_ts, "to_ts": to_ts, "scope": "both"},
            headers={"Idempotency-Key": export_key},
            timeout=max(args.timeout, 30),
        )
        ensure_status("Run compliance export duplicate", export_dup.status_code, export_dup.text, {200})
        if not as_json(export_dup).get("duplicate_skipped"):
            return fail(f"Export compliance idempotente no deduplicó: {export_dup.text}")

        verify_audit = session.get(
            f"{base_url}/api/tks/compliance/hash-chain/verify?stream=audit",
            timeout=args.timeout,
        )
        ensure_status("Verify hash-chain audit", verify_audit.status_code, verify_audit.text, {200})
        if as_json(verify_audit).get("ok") is not True:
            return fail(f"Hash-chain audit inválida: {verify_audit.text}")

        verify_evidence = session.get(
            f"{base_url}/api/tks/compliance/hash-chain/verify?stream=evidence",
            timeout=args.timeout,
        )
        ensure_status("Verify hash-chain evidence", verify_evidence.status_code, verify_evidence.text, {200})
        if as_json(verify_evidence).get("ok") is not True:
            return fail(f"Hash-chain evidence inválida: {verify_evidence.text}")

        purge_dry = session.post(
            f"{base_url}/api/tks/compliance/purge/dry-run",
            json={"as_of": datetime.now(timezone.utc).isoformat(), "max_tickets": 100},
            timeout=max(args.timeout, 30),
        )
        ensure_status("Purge dry-run", purge_dry.status_code, purge_dry.text, {200})

        purge_run = session.post(
            f"{base_url}/api/tks/compliance/purge/run",
            json={"as_of": "1970-01-01T00:00:00+00:00", "max_tickets": 10},
            headers={"Idempotency-Key": make_idem("cmp-purge-run")},
            timeout=max(args.timeout, 30),
        )
        ensure_status("Purge run", purge_run.status_code, purge_run.text, {200})
        print("[OK] Compliance core validado")
    except Exception as exc:
        return fail(str(exc))

    print("[SUCCESS] E2E Ticketera PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
