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
        "AGENTS.md",
        "plataforma/docs/README.md",
        "plataforma/docs/PLAN_MAESTRO_MONSTRUO.md",
        "plataforma/docs/PROYECTO_CONTEXTO.md",
        "plataforma/docs/PROXY_INVERSO.md",
        "plataforma/docs/ARQUITECTURA.md",
        "plataforma/docs/CHANGELOG.md",
        "plataforma/docs/CONTRATO_APPS.md",
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
        "plataforma/docs/PLAN_MAESTRO_MONSTRUO.md",
        "plataforma/docs/PROYECTO_CONTEXTO.md",
        "plataforma/docs/PROXY_INVERSO.md",
        "plataforma/docs/ARQUITECTURA.md",
        "plataforma/docs/CHANGELOG.md",
    ):
        if ref not in readme_text:
            errors.append(f"README.md no referencia {ref}")

    if errors:
        print("FAIL")
        for item in errors:
            print(f"- {item}")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
