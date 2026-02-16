#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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

        attachments_list = session.get(f"{base_url}/api/tks/tickets/{ticket_id}/attachments", timeout=args.timeout)
        ensure_status("Lista de adjuntos ticket", attachments_list.status_code, attachments_list.text, {200})
        att_items = as_json(attachments_list).get("items", [])
        if not att_items:
            return fail("No se encontraron adjuntos persistidos en ticket_attachments")
        att = att_items[0]
        att_id = int(att.get("id") or 0)
        if att_id <= 0:
            return fail(f"Adjunto sin id válido: {att}")

        download = session.get(
            f"{base_url}/api/tks/tickets/{ticket_id}/attachments/{att_id}/download",
            timeout=max(args.timeout, 30),
        )
        ensure_status("Descarga de adjunto", download.status_code, download.text if hasattr(download, "text") else "", {200})
        content = download.content or b""
        if len(content) == 0:
            return fail("Descarga de adjunto devolvió contenido vacío")
        expected_sha = str(att.get("sha256") or "").strip().lower()
        if expected_sha:
            got_sha = hashlib.sha256(content).hexdigest().lower()
            if got_sha != expected_sha:
                return fail(f"Hash inconsistente en descarga de adjunto: esperado={expected_sha} obtenido={got_sha}")

        print("[OK] Reply + dedupe + incoming thread match + download adjuntos validados")
    except Exception as exc:
        return fail(str(exc))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    # ------------------------------------------------------------
    # 3) Auto-Respuesta segura (allowlist + antiloop + one-shot)
    # ------------------------------------------------------------
    try:
        inner_auto_reply = f"""
import asyncio
from app.core import db, tickets_service, jobs_engine, email
from app.core.config import settings

backup = {{
    "enabled": settings.TICKET_AUTO_REPLY_ENABLED,
    "delay": settings.TICKET_AUTO_REPLY_DELAY_MINUTES,
    "allow_emails": settings.TICKET_AUTO_REPLY_ALLOWLIST_EMAILS,
    "allow_domains": settings.TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS,
    "require_allowlist": settings.TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST,
    "blocked_localparts": settings.TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS,
}}

try:
    settings.TICKET_AUTO_REPLY_ENABLED = False
    settings.TICKET_AUTO_REPLY_DELAY_MINUTES = 15
    settings.TICKET_AUTO_REPLY_ALLOWLIST_EMAILS = ""
    settings.TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS = ""
    settings.TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST = True
    settings.TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS = "noreply,no-reply,mailer-daemon,postmaster"

    ticket = tickets_service.create_ticket(
        titulo="E2E AutoReply",
        descripcion="Validación allowlist y dedupe",
        creador_id="e2e_bot",
        categoria="sistemas",
        severidad="media",
        tipo="incidencia",
        origen_email="cliente.autoreply@example.com",
        cliente_nombre="Cliente Auto",
        email_thread_id="<incoming-autoreply@example.com>",
        email_references="<incoming-autoreply@example.com>",
    )
    ticket_id = int(ticket["id"])
    to_email = "cliente.autoreply@example.com"

    conn = db.get_conn()
    try:
        ok, reason, _ = tickets_service.should_schedule_auto_reply(conn, ticket_id, to_email)
        if ok or reason != "auto_reply_disabled":
            print("FAIL_DISABLED", ok, reason)
            raise SystemExit(1)
    finally:
        conn.close()

    settings.TICKET_AUTO_REPLY_ENABLED = True

    conn = db.get_conn()
    try:
        ok, reason, _ = tickets_service.should_schedule_auto_reply(conn, ticket_id, to_email)
        if ok or reason != "allowlist_empty":
            print("FAIL_ALLOWLIST_EMPTY", ok, reason)
            raise SystemExit(1)
    finally:
        conn.close()

    settings.TICKET_AUTO_REPLY_ALLOWLIST_EMAILS = "cliente.autoreply@example.com"
    settings.TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS = ""

    conn = db.get_conn()
    try:
        ok, reason, _ = tickets_service.should_schedule_auto_reply(conn, ticket_id, to_email)
        if not ok:
            print("FAIL_ALLOW_EMAIL", reason)
            raise SystemExit(1)

        ok_blocked, reason_blocked, _ = tickets_service.should_schedule_auto_reply(conn, ticket_id, "no-reply@example.com")
        if ok_blocked or reason_blocked != "blocked_localpart":
            print("FAIL_BLOCKLIST", ok_blocked, reason_blocked)
            raise SystemExit(1)

        result_schedule = tickets_service.schedule_auto_reply_for_ticket(
            conn,
            ticket,
            to_email,
            "Cliente Auto",
            "mesa_ayuda",
            "<incoming-autoreply@example.com>",
            "<incoming-autoreply@example.com>",
        )
        if not result_schedule.get("scheduled"):
            print("FAIL_SCHEDULE", result_schedule)
            raise SystemExit(1)
        conn.commit()

        result_schedule_2 = tickets_service.schedule_auto_reply_for_ticket(
            conn,
            ticket,
            to_email,
            "Cliente Auto",
            "mesa_ayuda",
            "<incoming-autoreply@example.com>",
            "<incoming-autoreply@example.com>",
        )
        if result_schedule_2.get("scheduled"):
            print("FAIL_DUP_SCHEDULE", result_schedule_2)
            raise SystemExit(1)
        conn.commit()
    finally:
        conn.close()

    idem = tickets_service._auto_reply_idempotency_key(ticket_id, to_email)

    def _fake_send_email_advanced(to_email: str, subject: str, html_body: str, headers=None, attachments=None):
        return {{
            "ok": True,
            "from_addr": "soporte@example.com",
            "message_id": "<auto-reply-test@example.com>",
        }}

    email.send_email_advanced = _fake_send_email_advanced

    payload = {{
        "ticket_id": ticket_id,
        "email": to_email,
        "nombre": "Cliente Auto",
        "asignado_a": "mesa_ayuda",
        "idempotency_key": idem,
        "in_reply_to": "<incoming-autoreply@example.com>",
        "references": "<incoming-autoreply@example.com>",
    }}
    asyncio.run(jobs_engine.send_auto_response_job(payload))
    asyncio.run(jobs_engine.send_auto_response_job(payload))

    conn = db.get_conn()
    try:
        sent = conn.execute(
            '''SELECT COUNT(*) AS c
               FROM ticket_emails
               WHERE ticket_id = ?
                 AND direction = 'auto_reply'
                 AND idempotency_key = ?''',
            (ticket_id, idem),
        ).fetchone()
        if int((sent or {{}}).get("c") or 0) != 1:
            print("FAIL_AUTO_REPLY_DUP", dict(sent) if sent else None)
            raise SystemExit(1)

        ticket_after = conn.execute(
            "SELECT email_thread_id, email_references FROM tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        refs = str((ticket_after or {{}}).get("email_references") or "")
        if "<auto-reply-test@example.com>" not in refs:
            print("FAIL_THREAD_CHAIN", dict(ticket_after) if ticket_after else None)
            raise SystemExit(1)
    finally:
        conn.close()

    print("SUCCESS")
finally:
    settings.TICKET_AUTO_REPLY_ENABLED = backup["enabled"]
    settings.TICKET_AUTO_REPLY_DELAY_MINUTES = backup["delay"]
    settings.TICKET_AUTO_REPLY_ALLOWLIST_EMAILS = backup["allow_emails"]
    settings.TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS = backup["allow_domains"]
    settings.TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST = backup["require_allowlist"]
    settings.TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS = backup["blocked_localparts"]
"""
        cmd_auto_reply = [
            "docker", "compose", "--env-file", ".env.server.dev",
            "exec", "-T", "api", "python3", "-c", inner_auto_reply
        ]
        proc_auto_reply = subprocess.run(cmd_auto_reply, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if proc_auto_reply.returncode != 0 or "SUCCESS" not in proc_auto_reply.stdout:
            return fail(f"Error validando auto-reply seguro: {proc_auto_reply.stdout} // {proc_auto_reply.stderr}")
        print("[OK] Auto-reply seguro validado (allowlist + antiloop + one-shot)")
    except Exception as exc:
        return fail(str(exc))

    # ------------------------------------------------------------
    # 4) SLA metrics/breaches API contract
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
    # 5) Compliance core (retención + legal hold + export + hash-chain)
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
        export_body = as_json(export_resp)
        export_dup = session.post(
            f"{base_url}/api/tks/compliance/exports/run",
            json={"from_ts": from_ts, "to_ts": to_ts, "scope": "both"},
            headers={"Idempotency-Key": export_key},
            timeout=max(args.timeout, 30),
        )
        ensure_status("Run compliance export duplicate", export_dup.status_code, export_dup.text, {200})
        if not as_json(export_dup).get("duplicate_skipped"):
            return fail(f"Export compliance idempotente no deduplicó: {export_dup.text}")

        manifest_path = str(export_body.get("manifest_path") or "").strip()
        first_run_id = int(export_body.get("run_id") or 0)
        if not manifest_path or first_run_id <= 0:
            return fail(f"Run export sin manifest_path/run_id válido: {export_body}")

        delete_manifest_script = f"""
from pathlib import Path
p = Path({manifest_path!r})
if p.exists():
    p.unlink()
print("SUCCESS")
"""
        delete_cmd = [
            "docker", "compose", "--env-file", ".env.server.dev",
            "exec", "-T", "api", "python3", "-c", delete_manifest_script
        ]
        delete_proc = subprocess.run(delete_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if delete_proc.returncode != 0 or "SUCCESS" not in delete_proc.stdout:
            return fail(f"No se pudo borrar manifest para prueba de rerun: {delete_proc.stdout} // {delete_proc.stderr}")

        export_rerun = session.post(
            f"{base_url}/api/tks/compliance/exports/run",
            json={"from_ts": from_ts, "to_ts": to_ts, "scope": "both"},
            headers={"Idempotency-Key": export_key},
            timeout=max(args.timeout, 30),
        )
        ensure_status("Run compliance export rerun sin artefacto", export_rerun.status_code, export_rerun.text, {200})
        export_rerun_body = as_json(export_rerun)
        if export_rerun_body.get("duplicate_skipped"):
            return fail(f"Rerun de export no se ejecutó pese a artefacto faltante: {export_rerun_body}")
        rerun_id = int(export_rerun_body.get("run_id") or 0)
        if rerun_id <= 0 or rerun_id == first_run_id:
            return fail(f"Rerun de export no generó run nuevo: first={first_run_id} rerun={rerun_id}")
        if export_rerun_body.get("artifact_exists") is not True:
            return fail(f"Rerun de export sin artefacto verificado: {export_rerun_body}")

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
        print("[OK] Compliance core validado (incluye rerun cuando falta artefacto)")
    except Exception as exc:
        return fail(str(exc))

    # ------------------------------------------------------------
    # 6) Worker real de canales (dry_run + retry controlado)
    # ------------------------------------------------------------
    try:
        channels_status = session.get(f"{base_url}/api/tks/channels/status", timeout=args.timeout)
        ensure_status("Channels status", channels_status.status_code, channels_status.text, {200})

        channels_list = session.get(f"{base_url}/api/tks/channels/notifications?limit=10", timeout=args.timeout)
        ensure_status("Channels notifications list", channels_list.status_code, channels_list.text, {200})

        inner_channels = f"""
import asyncio
import logging
from app.core import db, tickets_service
from app.workers import integrations_worker
from app.core.config import settings

logging.basicConfig(level=logging.INFO)

conn = db.get_conn()
try:
    user = conn.execute(
        "SELECT username, phone_number FROM users WHERE COALESCE(phone_number, '') <> '' ORDER BY id ASC LIMIT 1"
    ).fetchone()
finally:
    conn.close()

if not user:
    print("SKIP_NO_PHONE")
    raise SystemExit(0)

username = str(user["username"])

ticket = tickets_service.create_ticket(
    titulo="E2E Channels DryRun",
    descripcion="Validación worker real de canales",
    creador_id=username,
    categoria="sistemas",
    severidad="alta",
    tipo="incidencia",
)
ticket_id = int(ticket["id"])
now = db.now_utc_iso()

def insert_notif(max_attempts: int) -> int:
    conn_i = db.get_conn()
    try:
        row = conn_i.execute(
            '''INSERT INTO ticket_notifications
               (ticket_id, user_id, channel, status, escalation_level, scheduled_at, next_retry_at,
                attempt_count, max_attempts, provider, provider_ref, last_error, error, created_at, updated_at)
               VALUES (?, ?, 'whatsapp', 'pending', 2, ?, ?, 0, ?, '', '', '', '', ?, ?)
               RETURNING id''',
            (ticket_id, username, now, now, max_attempts, now, now),
        ).fetchone()
        conn_i.commit()
        return int(row["id"])
    finally:
        conn_i.close()

notif_ok = insert_notif(2)
settings.CHANNELS_ENABLED = True
settings.WHATSAPP_ADAPTER_MODE = "dry_run"
settings.THREECX_ADAPTER_MODE = "disabled"
settings.WHATSAPP_BASE_URL = ""
settings.WHATSAPP_AUTH_TOKEN = ""

async def run_dry():
    await tickets_service.process_pending_notifications({{"recurring": False}})
    await integrations_worker.send_whatsapp_notification({{"notification_id": notif_ok}})

asyncio.run(run_dry())

conn_ok = db.get_conn()
try:
    row_ok = conn_ok.execute(
        "SELECT status, attempt_count, provider_ref FROM ticket_notifications WHERE id = ?",
        (notif_ok,),
    ).fetchone()
finally:
    conn_ok.close()

if not row_ok or str(row_ok["status"]).lower() != "sent":
    print("FAIL_DRY_RUN", dict(row_ok) if row_ok else None)
    raise SystemExit(1)

notif_live = insert_notif(3)
settings.WHATSAPP_ADAPTER_MODE = "live"

async def run_live_missing_creds():
    await tickets_service.process_pending_notifications({{"recurring": False}})
    await integrations_worker.send_whatsapp_notification({{"notification_id": notif_live}})

asyncio.run(run_live_missing_creds())

conn_live = db.get_conn()
try:
    row_live = conn_live.execute(
        "SELECT status, attempt_count, next_retry_at, last_error FROM ticket_notifications WHERE id = ?",
        (notif_live,),
    ).fetchone()
finally:
    conn_live.close()

if not row_live:
    print("FAIL_LIVE_ROW")
    raise SystemExit(1)

status_live = str(row_live["status"]).lower()
attempt_live = int(row_live["attempt_count"] or 0)
if status_live not in ("pending", "failed"):
    print("FAIL_LIVE_STATUS", dict(row_live))
    raise SystemExit(1)
if attempt_live < 1:
    print("FAIL_LIVE_ATTEMPT", dict(row_live))
    raise SystemExit(1)

idem = "e2e-channels-retry-001"
first_retry = tickets_service.retry_channel_notification(notif_live, actor="e2e_ticketera", idempotency_key=idem)
second_retry = tickets_service.retry_channel_notification(notif_live, actor="e2e_ticketera", idempotency_key=idem)
if not second_retry.get("duplicate_skipped"):
    print("FAIL_RETRY_IDEMPOTENCY", first_retry, second_retry)
    raise SystemExit(1)

print("SUCCESS")
"""
        cmd_channels = [
            "docker", "compose", "--env-file", ".env.server.dev",
            "exec", "-T", "api", "python3", "-c", inner_channels
        ]
        proc_channels = subprocess.run(cmd_channels, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if proc_channels.returncode != 0:
            return fail(f"Error validando worker canales: {proc_channels.stdout} // {proc_channels.stderr}")
        if "SKIP_NO_PHONE" in proc_channels.stdout:
            print("[OK] Worker canales: sin usuario con phone_number, test de dispatch omitido en este entorno")
        elif "SUCCESS" not in proc_channels.stdout:
            return fail(f"Salida inesperada worker canales: {proc_channels.stdout} // {proc_channels.stderr}")
        else:
            print("[OK] Worker canales validado (dry_run + retry + idempotencia)")
    except Exception as exc:
        return fail(str(exc))

    # ------------------------------------------------------------
    # 7) Cola jobs: queue-health + recover stale + dedupe recurrentes
    # ------------------------------------------------------------
    try:
        inner_queue_seed = f"""
import asyncio
from datetime import datetime, timedelta, timezone
from app.core import db, jobs_engine

conn = db.get_conn()
try:
    now = db.now_utc_iso()
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    conn.execute("DELETE FROM sys_jobs WHERE job_type = 'E2E_RECURRENCE_TEST'")
    row = conn.execute(
        '''INSERT INTO sys_jobs
           (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
           VALUES ('PROCESS_NOTIFICATIONS', 'RUNNING', '{{}}', ?, 0, 0, ?, ?)
           RETURNING id''',
        (old, now, old),
    ).fetchone()
    stale_id = int(row["id"]) if row else 0
    conn.commit()
finally:
    conn.close()

async def _run():
    first = await jobs_engine.enqueue_unique_job("E2E_RECURRENCE_TEST", {{"recurring": True}}, max_retries=0)
    second = await jobs_engine.enqueue_unique_job("E2E_RECURRENCE_TEST", {{"recurring": True}}, max_retries=0)
    return first, second

f, s = asyncio.run(_run())
if not f.get("enqueued") or not s.get("duplicate"):
    print("FAIL_DEDUPE", f, s)
    raise SystemExit(1)
print(f"SUCCESS STALE_ID={{stale_id}}")
"""
        seed_cmd = [
            "docker", "compose", "--env-file", ".env.server.dev",
            "exec", "-T", "api", "python3", "-c", inner_queue_seed
        ]
        seed_proc = subprocess.run(seed_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if seed_proc.returncode != 0 or "SUCCESS" not in seed_proc.stdout:
            return fail(f"Error preparando prueba de cola/recurrentes: {seed_proc.stdout} // {seed_proc.stderr}")

        stale_job_id = 0
        for token in seed_proc.stdout.split():
            if token.startswith("STALE_ID="):
                try:
                    stale_job_id = int(token.split("=", 1)[1])
                except Exception:
                    stale_job_id = 0
        if stale_job_id <= 0:
            return fail(f"No se pudo obtener stale_job_id desde seed script: {seed_proc.stdout}")

        queue_health = session.get(f"{base_url}/api/tks/ops/queue-health", timeout=max(args.timeout, 30))
        ensure_status("Queue health", queue_health.status_code, queue_health.text, {200})
        q_body = as_json(queue_health)
        for k in ("generated_at", "by_job_type", "totals"):
            if k not in q_body:
                return fail(f"Queue health sin campo requerido '{k}': {q_body}")

        recover = session.post(f"{base_url}/api/jobs/recover-stale?stale_minutes=20", timeout=max(args.timeout, 30))
        ensure_status("Recover stale jobs", recover.status_code, recover.text, {200})
        recovered = as_json(recover)
        if recovered.get("ok") is not True:
            return fail(f"Recover stale respondió sin ok=true: {recovered}")

        inner_check_stale = f"""
from app.core import db
conn = db.get_conn()
try:
    row = conn.execute("SELECT status FROM sys_jobs WHERE id = ?", ({stale_job_id},)).fetchone()
finally:
    conn.close()
if not row:
    print("FAIL_NOT_FOUND")
    raise SystemExit(1)
status = str(row.get("status") or "").upper()
if status not in ("RETRY", "FAILED"):
    print("FAIL_STATUS", status)
    raise SystemExit(1)
print("SUCCESS")
"""
        check_cmd = [
            "docker", "compose", "--env-file", ".env.server.dev",
            "exec", "-T", "api", "python3", "-c", inner_check_stale
        ]
        check_proc = subprocess.run(check_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if check_proc.returncode != 0 or "SUCCESS" not in check_proc.stdout:
            return fail(f"Recover stale no movió job a RETRY: {check_proc.stdout} // {check_proc.stderr}")

        print("[OK] Cola jobs validada (queue-health + recover stale + dedupe recurrentes)")
    except Exception as exc:
        return fail(str(exc))

    # ------------------------------------------------------------
    # 8) Paralelo Jira + MONSTRUO (bootstrap/delta/runs/kpi/go-no-go)
    # ------------------------------------------------------------
    try:
        jira_key = f"E2E-JIRA-{int(time.time())}"
        jira_issue = {
            "key": jira_key,
            "summary": f"E2E Jira Parallel {jira_key}",
            "description": "Validación técnica del paralelo Jira+MONSTRUO",
            "status": "open",
            "priority": "medium",
            "issue_type": "incidencia",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "comments": [{"author": "jira", "body": "comentario e2e paralelo"}],
        }

        bootstrap = session.post(
            f"{base_url}/api/tks/migration/jira/bootstrap-open",
            json={
                "dry_run": True,
                "issues": [jira_issue],
                "limit": 100,
            },
            timeout=max(args.timeout, 30),
        )
        ensure_status("Jira bootstrap-open dry_run", bootstrap.status_code, bootstrap.text, {200})

        delta_1 = session.post(
            f"{base_url}/api/tks/migration/jira/delta-sync/run",
            json={
                "dry_run": False,
                "issues": [jira_issue],
                "limit": 100,
            },
            timeout=max(args.timeout, 30),
        )
        ensure_status("Jira delta-sync run 1", delta_1.status_code, delta_1.text, {200})

        delta_2 = session.post(
            f"{base_url}/api/tks/migration/jira/delta-sync/run",
            json={
                "dry_run": False,
                "issues": [jira_issue],
                "limit": 100,
            },
            timeout=max(args.timeout, 30),
        )
        ensure_status("Jira delta-sync run 2", delta_2.status_code, delta_2.text, {200})
        if int(as_json(delta_2).get("skipped") or 0) < 1:
            return fail(f"Delta idempotente no reflejó skipped esperado: {delta_2.text}")

        runs = session.get(f"{base_url}/api/tks/migration/jira/runs?limit=10", timeout=args.timeout)
        ensure_status("Jira runs", runs.status_code, runs.text, {200})
        if int(as_json(runs).get("total") or 0) < 1:
            return fail(f"Sin historial de runs Jira: {runs.text}")

        reconciliation = session.get(
            f"{base_url}/api/tks/migration/jira/reconciliation/daily",
            timeout=max(args.timeout, 30),
        )
        ensure_status("Jira reconciliation daily", reconciliation.status_code, reconciliation.text, {200})
        rec_body = as_json(reconciliation)
        if "snapshot_date" not in rec_body:
            return fail(f"Reconciliation sin snapshot_date: {rec_body}")

        kpi = session.get(
            f"{base_url}/api/tks/parallel/kpi/daily?from=2026-01-01&to=2030-01-01",
            timeout=max(args.timeout, 30),
        )
        ensure_status("Parallel KPI daily", kpi.status_code, kpi.text, {200})
        if "items" not in as_json(kpi):
            return fail(f"KPI daily sin items: {kpi.text}")

        go_no_go = session.post(
            f"{base_url}/api/tks/parallel/go-no-go",
            json={
                "decision": "no_go",
                "signers": [args.user],
                "rationale": "E2E técnico - pendiente ejecución real 8 semanas",
                "evidence_refs": ["tests/e2e_ticketera.py"],
            },
            timeout=max(args.timeout, 30),
        )
        ensure_status("Parallel go-no-go", go_no_go.status_code, go_no_go.text, {200})
        if not as_json(go_no_go).get("item", {}).get("id"):
            return fail(f"Go/No-Go sin id: {go_no_go.text}")

        print("[OK] Paralelo Jira+MONSTRUO técnico validado (bootstrap/delta/runs/kpi/go-no-go)")
    except Exception as exc:
        return fail(str(exc))

    print("[SUCCESS] E2E Ticketera PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
