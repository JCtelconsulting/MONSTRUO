#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def expect_exists(rel_path: str, errors: list[str]) -> None:
    path = ROOT / rel_path
    if not path.exists():
        errors.append(f"Falta archivo requerido: {rel_path}")


def expect_missing(rel_path: str, errors: list[str]) -> None:
    path = ROOT / rel_path
    if path.exists():
        errors.append(f"No debe existir en raíz o ruta antigua: {rel_path}")


def main() -> int:
    errors: list[str] = []

    required_docs = [
        "README.md",
        "CLAUDE.md",
        "plataforma/docs/README.md",
        "plataforma/docs/AGENTS.md",
        "plataforma/docs/PROYECTO_CONTEXTO.md",
        "plataforma/docs/plan/GUIA_MAESTRA.md",
        "plataforma/docs/arquitectura/PROXY_INVERSO.md",
        "plataforma/docs/arquitectura/ARQUITECTURA.md",
        "plataforma/docs/arquitectura/CONTRATO_APPS.md",
        "plataforma/docs/changelog/CHANGELOG.md",
    ]
    for rel in required_docs:
        expect_exists(rel, errors)

    required_proxy = [
        "plataforma/ops/nginx/README.md",
        "plataforma/ops/nginx/monstruo.conf",
        "plataforma/ops/nginx/terreneitor.conf",
        "plataforma/ops/nginx/sapa.conf",
    ]
    for rel in required_proxy:
        expect_exists(rel, errors)

    old_root_docs = [
        "ARQUITECTURA.md",
        "CHANGELOG.md",
        "PLAN_DE_SANEAMIENTO.md",
        "AGENTS.md",
        "plataforma/docs/PLAN_MAESTRO_MONSTRUO.md",
        "plataforma/docs/DESIGN.md",
        "plataforma/docs/PROMPT_CHAT_UNIVERSAL.md",
        "plataforma/docs/PROGRAMA_REEMPLAZO_JIRA_ISO27001_12M.md",
        "plataforma/docs/playbooks/paralelo_jira_monstruo.md",
    ]
    for rel in old_root_docs:
        expect_missing(rel, errors)

    legacy_structure_paths = [
        ".env",
        "bodega/core",
        "crm/core",
        "erp/core",
        "fundacion/core",
        "gateway/frontend/fundacion",
    ]
    for rel in legacy_structure_paths:
        expect_missing(rel, errors)

    app_contract = {
        "bodega": ["README.md", "Dockerfile", "main.py", "router.py", "service.py"],
        "crm": ["README.md", "Dockerfile", "main.py", "router.py", "service.py"],
        "erp": ["README.md", "Dockerfile", "main.py", "router.py", "service.py"],
        "fundacion": ["README.md", "Dockerfile", "main.py", "router.py"],
        "gateway": ["README.md", "Dockerfile", "backend/main.py"],
        "ticketera": ["README.md", "Dockerfile", "backend/main.py", "backend/router.py", "backend/service.py"],
    }
    for app, files in app_contract.items():
        for rel in files:
            expect_exists(f"{app}/{rel}", errors)

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    for ref in (
        "plataforma/docs/README.md",
        "plataforma/docs/AGENTS.md",
        "plataforma/docs/PROYECTO_CONTEXTO.md",
        "plataforma/docs/plan/GUIA_MAESTRA.md",
        "plataforma/docs/arquitectura/ARQUITECTURA.md",
        "plataforma/docs/changelog/CHANGELOG.md",
    ):
        if ref not in readme_text:
            errors.append(f"README.md no referencia {ref}")

    # Guardas contrato canónico DEV/PROD (plataforma/docs/AGENTS.md §4) en docker-compose.yaml.
    compose_path = ROOT / "docker-compose.yaml"
    if not compose_path.exists():
        errors.append("Falta docker-compose.yaml en raíz")
    else:
        compose_text = compose_path.read_text(encoding="utf-8")

        # 1) Postgres NUNCA publica 5432 al host.
        for forbidden in ('"5432:5432"', "'5432:5432'", "- 5432:5432"):
            if forbidden in compose_text:
                errors.append(
                    f"docker-compose.yaml publica 5432 al host ({forbidden}); prohibido por contrato canónico"
                )

        # 2) Gateway debe publicar 9001 y ticketera 9005 (parametrizable con default).
        if "${GATEWAY_PORT:-9001}:9001" not in compose_text:
            errors.append(
                "docker-compose.yaml: gateway debe publicar ${GATEWAY_PORT:-9001}:9001"
            )
        if "${TICKETERA_PORT:-9005}:9005" not in compose_text:
            errors.append(
                "docker-compose.yaml: ticketera debe publicar ${TICKETERA_PORT:-9005}:9005"
            )

        # 3) Bind canónico de datos Postgres (idéntico DEV/PROD).
        if "./plataforma/data/postgres:/var/lib/postgresql/data" not in compose_text:
            errors.append(
                "docker-compose.yaml: db debe usar bind ./plataforma/data/postgres:/var/lib/postgresql/data"
            )

        # 4) Mounts críticos ticketera/data/{tickets,compliance} en gateway y ticketera.
        required_mounts = (
            "./ticketera/data/tickets:/app/ticketera/data/tickets",
            "./ticketera/data/compliance:/app/ticketera/data/compliance",
        )
        for mount in required_mounts:
            if compose_text.count(mount) < 2:
                errors.append(
                    f"docker-compose.yaml: mount requerido en gateway y ticketera: {mount}"
                )

        # 5) ENV_FILE parametrizable con default DEV.
        if "${ENV_FILE:-plataforma/ops/env/.env.server.dev}" not in compose_text:
            errors.append(
                "docker-compose.yaml: env_file debe ser ${ENV_FILE:-plataforma/ops/env/.env.server.dev}"
            )

        # 6) STACK_NAME parametrizable con default DEV en container_name.
        if "${STACK_NAME:-monstruo-dev}" not in compose_text:
            errors.append(
                "docker-compose.yaml: container_name debe usar ${STACK_NAME:-monstruo-dev}"
            )

    if errors:
        print("FAIL")
        for item in errors:
            print(f"- {item}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
