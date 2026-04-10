#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SKIP_DIRS = {"__pycache__", "venv", "node_modules", ".git"}


def parse_allowlist(readme_content: str) -> List[str]:
    patterns: List[str] = []
    for line in readme_content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        item = stripped[2:].split("#")[0].strip()
        if item.endswith("/"):
            item = item[:-1]
        if item:
            patterns.append(item)
    return patterns


def verify_structure(root_dir: str) -> List[str]:
    violations: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

        readme_path = os.path.join(dirpath, ".README.md")
        if not os.path.exists(readme_path):
            continue

        with open(readme_path, "r", encoding="utf-8") as f:
            allowed_patterns = parse_allowlist(f.read())

        current_items = set(filenames + dirnames)
        current_items = {i for i in current_items if i != ".README.md" and not i.startswith(".")}

        for item in current_items:
            matched = any(fnmatch.fnmatch(item, pattern) for pattern in allowed_patterns)
            if not matched:
                violations.append(f"[VIOLACION] {os.path.join(dirpath, item)} no esta en .README.md")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida estructura contra allowlists .README.md")
    parser.add_argument("--root", default=os.environ.get("PROJECT_ROOT", str(PROJECT_ROOT)))
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    print(f"Verificando estructura en {root}...")
    errors = verify_structure(root)

    if errors:
        print(f"Se encontraron {len(errors)} violaciones de estructura:")
        for err in errors:
            print(err)
        return 1

    print("Estructura OK. Coincide con manifiestos estrictos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
