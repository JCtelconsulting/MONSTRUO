#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Tuple

import requests

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from _helpers import as_json, build_session, env_str, guard_prod_target, require_credentials

PROJECT_ROOT = THIS_DIR.parents[1]


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validacion hardening repo + API opcional")
    ap.add_argument("--check-api", action="store_true", help="Ejecuta validacion API ademas de chequeos repo")
    ap.add_argument(
        "--base-url",
        default=env_str("MONSTRUO_TEST_BASE_URL", "http://127.0.0.1:9001"),
        help="URL base del API",
    )
    ap.add_argument("--user", default=env_str("MONSTRUO_TEST_USER"))
    ap.add_argument("--password", default=env_str("MONSTRUO_TEST_PASSWORD"))
    ap.add_argument("--timeout", type=int, default=int(env_str("MONSTRUO_TEST_TIMEOUT", "15") or "15"))
    ap.add_argument("--allow-prod", action="store_true")
    return ap.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_env_like(path: Path) -> dict:
    data = {}
    for raw in read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.split(None, 1)[1].strip()
        data[key] = value.strip()
    return data


def list_repo_files() -> List[Path]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
        files = []
        for rel in proc.stdout.splitlines():
            rel = rel.strip()
            if not rel:
                continue
            files.append(PROJECT_ROOT / rel)
        return files
    except Exception:
        return [p for p in PROJECT_ROOT.rglob("*") if p.is_file()]


def repo_checks() -> List[str]:
    errors: List[str] = []

    required_files = [
        PROJECT_ROOT / "plataforma/ops/herramientas/deploy/deploy.sh",
        PROJECT_ROOT / "plataforma/ops/control/control_monstruo.sh",
        PROJECT_ROOT / "plataforma/ops/control/limpiar_ram.sh",
        PROJECT_ROOT / "plataforma/tests/e2e_ticketera.py",
        PROJECT_ROOT / "plataforma/tests/e2e_api_full.py",
        PROJECT_ROOT / "plataforma/tests/.README.md",
    ]
    for path in required_files:
        if not path.exists():
            errors.append(f"Falta archivo requerido: {path}")

    deploy_text = read_text(PROJECT_ROOT / "plataforma/ops/herramientas/deploy/deploy.sh")
    if 'BRANCH="${DEPLOY_BRANCH:-dev}"' not in deploy_text:
        errors.append("deploy.sh no tiene branch default en dev")
    if 'APP_DIR="${DEPLOY_PATH:-$PROJECT_ROOT}"' not in deploy_text:
        errors.append("deploy.sh no usa APP_DIR dinamico por PROJECT_ROOT")
    for required in (
        'plataforma/ops/env/.env.server.dev',
        'plataforma/ops/env/.env.server',
    ):
        if required not in deploy_text:
            errors.append(f"deploy.sh no referencia env canónico requerido: {required}")

    syntax = subprocess.run(
        ["bash", "-n", str(PROJECT_ROOT / "plataforma/ops/herramientas/deploy/deploy.sh")],
        capture_output=True,
        text=True,
    )
    if syntax.returncode != 0:
        detail = (syntax.stderr or syntax.stdout).strip()
        errors.append(f"deploy.sh con error de sintaxis: {detail}")

    compose_text = read_text(PROJECT_ROOT / "docker-compose.yaml")
    if "plataforma/ops/env/.env.server.dev" not in compose_text:
        errors.append("docker-compose.yaml debe usar ENV_FILE canónico oculto")
    if re.search(r"^\s*-\s*\.env\s*$", compose_text, flags=re.M):
        errors.append("docker-compose.yaml no debe fijar env_file a .env")

    gitignore_text = read_text(PROJECT_ROOT / ".gitignore")
    if "ticketera/data/compliance/" not in gitignore_text:
        errors.append(".gitignore debe excluir ticketera/data/compliance/")

    config_text = read_text(PROJECT_ROOT / "plataforma/core/config.py")
    if "tickets:compliance" not in config_text:
        errors.append("RBAC sin permiso tickets:compliance")
    for required in (
        "TICKET_AUTO_REPLY_ENABLED",
        "TICKET_AUTO_REPLY_DELAY_MINUTES",
        "TICKET_AUTO_REPLY_ALLOWLIST_EMAILS",
        "TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS",
        "TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST",
        "TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS",
        "TICKET_ATTACHMENTS_DIR",
        "COMPLIANCE_EXPORT_DIR",
        "JOBS_STALE_RUNNING_MINUTES",
        "SYS_JOBS_RETENTION_DAYS",
        "TKS_SLA_EVAL_LIMIT",
        "CHANNELS_ENABLED",
        "WHATSAPP_ADAPTER_MODE",
        "THREECX_ADAPTER_MODE",
        "CHANNELS_MAX_ATTEMPTS",
    ):
        if required not in config_text:
            errors.append(f"config.py sin variable requerida de ticketera: {required}")

    for env_file in (
        PROJECT_ROOT / "plataforma/docs/operacion/deploy/plantillas_env/env.server.dev.example",
        PROJECT_ROOT / "plataforma/docs/operacion/deploy/plantillas_env/env.server.example",
    ):
        env_text = read_text(env_file)
        for required in (
            "TICKET_AUTO_REPLY_ENABLED",
            "TICKET_AUTO_REPLY_DELAY_MINUTES",
            "TICKET_AUTO_REPLY_ALLOWLIST_EMAILS",
            "TICKET_AUTO_REPLY_ALLOWLIST_DOMAINS",
            "TICKET_AUTO_REPLY_REQUIRE_ALLOWLIST",
            "TICKET_AUTO_REPLY_BLOCKED_LOCALPARTS",
            "TICKET_ATTACHMENTS_DIR",
            "COMPLIANCE_EXPORT_DIR",
            "JOBS_STALE_RUNNING_MINUTES",
            "SYS_JOBS_RETENTION_DAYS",
            "TKS_SLA_EVAL_LIMIT",
            "CHANNELS_ENABLED",
            "WHATSAPP_ADAPTER_MODE",
            "THREECX_ADAPTER_MODE",
            "WHATSAPP_BASE_URL",
            "THREECX_BASE_URL",
            "CHANNELS_MAX_ATTEMPTS",
            "CHANNELS_RETRY_BASE_SECONDS",
            "CHANNELS_RETRY_MAX_SECONDS",
        ):
            if required not in env_text:
                errors.append(f"{env_file} sin variable requerida: {required}")

    banned_checks: List[Tuple[str, re.Pattern[str], List[Path]]] = [
        (
            "password hardcodeada conocida",
            re.compile(r"Apstref\.8"),
            [],
        ),
        (
            "sudo por pipe inseguro",
            re.compile(r'echo\s+"\$SUDO_PASS"\s+\|\s+sudo'),
            [],
        ),
        (
            "password hardcodeada en tests",
            re.compile(r'PASSWORD\s*=\s*["\']'),
            [
                PROJECT_ROOT / "plataforma/tests/e2e_api_full.py",
                PROJECT_ROOT / "plataforma/tests/e2e_ticketera.py",
                PROJECT_ROOT / "plataforma/tests/verify_hardening.py",
            ],
        ),
    ]
    ignore_files = {
        PROJECT_ROOT / "plataforma/ops/herramientas/dev/proxy_vm.env.example",
        PROJECT_ROOT / "plataforma/ops/herramientas/dev/proxy_vm_env.sh",
    }

    repo_files = list_repo_files()
    for pattern_name, pattern, scoped_files in banned_checks:
        targets: List[Path] = []
        if scoped_files:
            targets = scoped_files
        else:
            targets = repo_files
        for path in targets:
            if path in ignore_files:
                continue
            if ".git/" in str(path) or "__pycache__" in str(path):
                continue
            try:
                text = read_text(path)
            except Exception:
                continue
            if pattern.search(text):
                errors.append(f"{pattern_name}: {path}")

    for path in [
        PROJECT_ROOT / "plataforma/tests/e2e_api_full.py",
        PROJECT_ROOT / "plataforma/tests/e2e_ticketera.py",
        PROJECT_ROOT / "plataforma/tests/verify_hardening.py",
    ]:
        text = read_text(path)
        if "MONSTRUO_TEST_USER" not in text:
            errors.append(f"{path} no usa MONSTRUO_TEST_USER")
        if "MONSTRUO_TEST_PASSWORD" not in text:
            errors.append(f"{path} no usa MONSTRUO_TEST_PASSWORD")

    return errors


def api_checks(args: argparse.Namespace) -> List[str]:
    errors: List[str] = []
    base_url = args.base_url.rstrip("/")
    try:
        guard_prod_target(base_url, allow_prod=args.allow_prod)
        require_credentials(args.user, args.password)
    except Exception as exc:
        return [str(exc)]

    try:
        auth = build_session(base_url, args.user, args.password, timeout=args.timeout)
        session = auth["session"]
    except Exception as exc:
        return [f"Login API fallo: {exc}"]

    try:
        resp = session.get(f"{base_url}/api/tks/stats", timeout=args.timeout)
        if resp.status_code != 200:
            errors.append(f"/api/tks/stats con sesion -> {resp.status_code} {resp.text}")
    except Exception as exc:
        errors.append(f"Error consultando stats autenticado: {exc}")

    try:
        noauth = requests.get(f"{base_url}/api/tks/stats", timeout=args.timeout)
        if noauth.status_code not in (401, 403):
            errors.append(f"/api/tks/stats sin sesion deberia bloquear (401/403), obtuvo {noauth.status_code}")
    except Exception as exc:
        errors.append(f"Error consultando stats sin sesion: {exc}")

    try:
        whoami = session.get(f"{base_url}/api/auth/whoami", timeout=args.timeout)
        if whoami.status_code != 200:
            errors.append(f"/api/auth/whoami -> {whoami.status_code}")
        else:
            payload = as_json(whoami)
            if not payload.get("logged"):
                errors.append(f"/api/auth/whoami sin sesion valida: {payload}")
    except Exception as exc:
        errors.append(f"Error consultando whoami: {exc}")

    try:
        sla_metrics = session.get(f"{base_url}/api/tks/sla/metrics", timeout=args.timeout)
        if sla_metrics.status_code != 200:
            errors.append(f"/api/tks/sla/metrics -> {sla_metrics.status_code} {sla_metrics.text}")
        else:
            payload = as_json(sla_metrics)
            for key in ("sla_mode", "escalation_windows_pct", "business_hours"):
                if key not in payload:
                    errors.append(f"/api/tks/sla/metrics no contiene '{key}'")
    except Exception as exc:
        errors.append(f"Error consultando /api/tks/sla/metrics: {exc}")

    try:
        chain_verify = session.get(
            f"{base_url}/api/tks/compliance/hash-chain/verify?stream=evidence",
            timeout=args.timeout,
        )
        if chain_verify.status_code != 200:
            errors.append(f"/api/tks/compliance/hash-chain/verify -> {chain_verify.status_code} {chain_verify.text}")
    except Exception as exc:
        errors.append(f"Error consultando hash-chain verify: {exc}")

    try:
        channels_status = session.get(f"{base_url}/api/tks/channels/status", timeout=args.timeout)
        if channels_status.status_code != 200:
            errors.append(f"/api/tks/channels/status -> {channels_status.status_code} {channels_status.text}")
        else:
            payload = as_json(channels_status)
            for key in ("channels_enabled", "adapters", "queue", "retry_policy"):
                if key not in payload:
                    errors.append(f"/api/tks/channels/status no contiene '{key}'")
    except Exception as exc:
        errors.append(f"Error consultando /api/tks/channels/status: {exc}")

    try:
        channels_list = session.get(f"{base_url}/api/tks/channels/notifications?limit=5", timeout=args.timeout)
        if channels_list.status_code != 200:
            errors.append(f"/api/tks/channels/notifications -> {channels_list.status_code} {channels_list.text}")
    except Exception as exc:
        errors.append(f"Error consultando /api/tks/channels/notifications: {exc}")

    try:
        queue_health = session.get(f"{base_url}/api/tks/ops/queue-health", timeout=args.timeout)
        if queue_health.status_code != 200:
            errors.append(f"/api/tks/ops/queue-health -> {queue_health.status_code} {queue_health.text}")
        else:
            payload = as_json(queue_health)
            for key in ("generated_at", "by_job_type", "totals"):
                if key not in payload:
                    errors.append(f"/api/tks/ops/queue-health no contiene '{key}'")
    except Exception as exc:
        errors.append(f"Error consultando /api/tks/ops/queue-health: {exc}")

    try:
        recover = session.post(f"{base_url}/api/jobs/recover-stale?stale_minutes=20", timeout=max(args.timeout, 30))
        if recover.status_code != 200:
            errors.append(f"/api/jobs/recover-stale -> {recover.status_code} {recover.text}")
    except Exception as exc:
        errors.append(f"Error ejecutando /api/jobs/recover-stale: {exc}")

    protected_cases = [
        ("GET", f"{base_url}/api/tks/tickets/1/workflow", None),
        ("POST", f"{base_url}/api/tks/tickets/1/transitions", {"to_subestado": "en_analisis", "motivo": "hardening"}),
        ("POST", f"{base_url}/api/tks/tickets/1/approvals", {"step": 1, "decision": "approved", "decision_note": "hardening"}),
        ("GET", f"{base_url}/api/tks/tickets/1/approvals", None),
        ("GET", f"{base_url}/api/tks/compliance/hash-chain/verify?stream=audit", None),
        ("GET", f"{base_url}/api/tks/compliance/exports/runs", None),
        ("GET", f"{base_url}/api/tks/compliance/purge/runs", None),
        ("GET", f"{base_url}/api/tks/compliance/legal-holds", None),
        ("GET", f"{base_url}/api/tks/channels/status", None),
        ("GET", f"{base_url}/api/tks/ops/queue-health", None),
        ("GET", f"{base_url}/api/tks/channels/notifications?limit=5", None),
        ("POST", f"{base_url}/api/tks/channels/notifications/1/retry", None),
        ("POST", f"{base_url}/api/jobs/recover-stale?stale_minutes=20", None),
    ]
    for method, url, body in protected_cases:
        try:
            if method == "GET":
                resp = requests.get(url, timeout=args.timeout)
            else:
                resp = requests.post(url, json=body, timeout=args.timeout)
            if resp.status_code not in (401, 403):
                errors.append(f"Ruta protegida sin bloqueo ({method} {url}) -> {resp.status_code}")
        except Exception as exc:
            errors.append(f"Error validando protección de ruta ({method} {url}): {exc}")

    # Validación mínima de idempotencia para endpoints nuevos de workflow/aprobaciones
    try:
        create_resp = session.post(
            f"{base_url}/api/tks/tickets",
            json={
                "titulo": f"Hardening Workflow {int(time.time())}",
                "descripcion": "Validación de idempotencia",
                "tipo": "cambio",
                "severidad": "media",
                "categoria": "sistemas",
            },
            timeout=args.timeout,
        )
        if create_resp.status_code != 200:
            errors.append(f"No se pudo crear ticket de hardening ({create_resp.status_code}): {create_resp.text}")
            return errors

        ticket_id = as_json(create_resp).get("id")
        if not ticket_id:
            errors.append(f"Ticket de hardening sin ID: {create_resp.text}")
            return errors

        transition_idem = f"hardening-transition-{ticket_id}-{int(time.time() * 1000)}"
        t1 = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/transitions",
            json={"to_subestado": "asignado", "motivo": "idempotencia"},
            headers={"Idempotency-Key": transition_idem},
            timeout=args.timeout,
        )
        if t1.status_code != 200:
            errors.append(f"Transition idempotente (primera) falló: {t1.status_code} {t1.text}")
            return errors

        t2 = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/transitions",
            json={"to_subestado": "asignado", "motivo": "idempotencia"},
            headers={"Idempotency-Key": transition_idem},
            timeout=args.timeout,
        )
        if t2.status_code != 200 or not as_json(t2).get("duplicate_skipped"):
            errors.append(f"Transition idempotente (duplicada) no deduplicó: {t2.status_code} {t2.text}")
            return errors

        analysis_transition = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/transitions",
            json={"to_subestado": "en_analisis", "motivo": "pasa a analisis"},
            headers={"Idempotency-Key": f"{transition_idem}-analysis"},
            timeout=args.timeout,
        )
        if analysis_transition.status_code != 200:
            errors.append(f"Transition a en_analisis falló: {analysis_transition.status_code} {analysis_transition.text}")
            return errors

        p1 = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/transitions",
            json={"to_subestado": "pendiente_aprobacion_1", "motivo": "paso a aprobación"},
            headers={"Idempotency-Key": f"{transition_idem}-p1"},
            timeout=args.timeout,
        )
        if p1.status_code != 200:
            errors.append(f"Transition a pendiente_aprobacion_1 falló: {p1.status_code} {p1.text}")
            return errors

        approval_idem = f"hardening-approval-{ticket_id}-{int(time.time() * 1000)}"
        a1 = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/approvals",
            json={"step": 1, "decision": "approved", "decision_note": "hardening"},
            headers={"Idempotency-Key": approval_idem},
            timeout=args.timeout,
        )
        if a1.status_code != 200:
            errors.append(f"Approval idempotente (primera) falló: {a1.status_code} {a1.text}")
            return errors

        a2 = session.post(
            f"{base_url}/api/tks/tickets/{ticket_id}/approvals",
            json={"step": 1, "decision": "approved", "decision_note": "hardening-dup"},
            headers={"Idempotency-Key": approval_idem},
            timeout=args.timeout,
        )
        if a2.status_code != 200 or not as_json(a2).get("duplicate_skipped"):
            errors.append(f"Approval idempotente (duplicada) no deduplicó: {a2.status_code} {a2.text}")
    except Exception as exc:
        errors.append(f"Error validando idempotencia workflow/aprobaciones: {exc}")

    return errors


def check_deploy_workflow() -> List[str]:
    """Valida que .github/workflows/deploy.yml tenga la configuración correcta para DEV/PROD."""
    errors = []
    deploy_yml = PROJECT_ROOT / ".github/workflows/deploy.yml"
    if not deploy_yml.exists():
        return [f"No existe {deploy_yml}"]

    content = read_text(deploy_yml)
    
    # Validaciones específicas para rama DEV
    checks = [
        (r'echo\s+"env_file=/srv/monstruo/\plataforma/ops/env/\.env\.server"', "PROD debe usar plataforma/ops/env/.env.server"),
        (r'echo\s+"env_file=/srv/monstruo_dev/\plataforma/ops/env/\.env\.server\.dev"', "DEV debe usar plataforma/ops/env/.env.server.dev"),
        (r'echo\s+"project=monstruo_dev"', "DEV debe usar project=monstruo_dev"),
        (r'echo\s+"project=monstruo"', "PROD debe usar project=monstruo"),
        (r'echo\s+"health=http://127\.0\.0\.1:9001/health"', "DEV debe chequear health en puerto 9001"),
        (r'echo\s+"health=http://127\.0\.0\.1:9000/health"', "PROD debe chequear health en puerto 9000"),
        (r'echo\s+"deploy_path=/srv/monstruo_dev"', "DEV debe deployar en /srv/monstruo_dev"),
        (r'echo\s+"deploy_path=/srv/monstruo"', "PROD debe deployar en /srv/monstruo"),
    ]

    for pattern, msg in checks:
        if not re.search(pattern, content):
            errors.append(f"Deploy workflow FAIL: {msg}")

    return errors


def main() -> int:
    args = parse_args()
    repo_errors = repo_checks()
    deploy_errors = check_deploy_workflow()
    
    api_errors: List[str] = []
    if args.check_api:
        api_errors = api_checks(args)

    all_errors = repo_errors + deploy_errors + api_errors
    if all_errors:
        print("[FAIL] Hardening check")
        for err in all_errors:
            print(f"- {err}")
        return 1

    print("[OK] Hardening repo PASS")
    if args.check_api:
        print("[OK] Hardening API PASS")
    print("[SUCCESS] verify_hardening PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
