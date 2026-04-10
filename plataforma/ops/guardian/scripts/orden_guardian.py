#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RULES_PATH = PROJECT_ROOT / "plataforma" / "docs" / "estructura_repo.json"
SKIP_DIRS = {".git", ".agent", "__pycache__", "venv", "node_modules"}


def load_rules(rules_path: Path) -> dict:
    try:
        with rules_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"CRITICAL: no se pudo cargar reglas canonicas desde {rules_path}: {e}")
        sys.exit(1)


def validate_path(rel_path: str, rules_data: dict, is_dir: bool = False) -> List[str]:
    violations: List[str] = []

    for blocked in rules_data.get("blocked_paths", []):
        if fnmatch.fnmatch(rel_path, blocked):
            violations.append(f"BLOCKED: '{rel_path}' coincide con patron prohibido '{blocked}'")
            return violations

    parts = rel_path.split("/")
    if len(parts) == 1:
        if rel_path not in rules_data.get("root_allowed", []):
            violations.append(f"ROOT: '{rel_path}' no permitido en la raiz")
        return violations

    if is_dir:
        return violations

    matched_rule_key = None
    longest_prefix = -1
    folder_rules = rules_data.get("rules", {})

    for rule_path in folder_rules:
        if rel_path.startswith(rule_path + "/") or rel_path == rule_path:
            if len(rule_path) > longest_prefix:
                longest_prefix = len(rule_path)
                matched_rule_key = rule_path

    if matched_rule_key:
        allowed_exts = folder_rules[matched_rule_key].get("allowed_extensions", [])
        ext = Path(rel_path).suffix
        if ext not in allowed_exts:
            violations.append(
                f"EXT: '{rel_path}' tiene extension '{ext}' no permitida en '{matched_rule_key}' {allowed_exts}"
            )

    return violations


def check_repo(root_dir: Path, rules: dict) -> None:
    print(f"--- MODO SCANNER (REPO COMPLETO): {root_dir} ---")
    all_violations: List[str] = []

    for current_root, dirs, files in root_dir.walk(top_down=True):
        dirs[:] = [d for d in dirs if d.name not in SKIP_DIRS]

        for d in dirs:
            rel_path = str((current_root / d.name).relative_to(root_dir))
            all_violations.extend(validate_path(rel_path, rules, is_dir=True))

        for f in files:
            if f.name.startswith("."):
                continue
            rel_path = str((current_root / f.name).relative_to(root_dir))
            all_violations.extend(validate_path(rel_path, rules, is_dir=False))

    report_and_exit(all_violations)


def check_patch(diff_content: str, rules: dict) -> None:
    print("--- MODO GATEKEEPER (PATCH CHECK) ---")
    paths_to_check = []
    for line in diff_content.splitlines():
        match = re.search(r"^\+\+\+\s+b/(.*)", line)
        if match:
            path = match.group(1)
            if path != "/dev/null":
                paths_to_check.append(path)

    if not paths_to_check:
        print("WARN: no se detectaron rutas en el patch enviado")
        sys.exit(0)

    all_violations: List[str] = []
    for p in paths_to_check:
        all_violations.extend(validate_path(p, rules, is_dir=False))

    report_and_exit(all_violations)


def report_and_exit(violations: List[str]) -> None:
    if violations:
        print(f"FAIL: se encontraron {len(violations)} violaciones")
        for i, v in enumerate(violations):
            if i >= 20:
                print(f"... y {len(violations) - 20} mas")
                break
            print(v)
        sys.exit(1)

    print("PASS: estructura conforme a reglas")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Guardian del Orden - validador de estructura y patches")
    parser.add_argument("--rules", default=str(DEFAULT_RULES_PATH), help="Ruta a estructura_repo.json")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="Raiz del repo a validar")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-repo", action="store_true", help="Escanear todo el repositorio (default)")
    group.add_argument("--check-patch", help="Validar archivo patch/diff (usar '-' para stdin)")
    args = parser.parse_args()

    rules = load_rules(Path(args.rules).resolve())

    if args.check_patch:
        if args.check_patch == "-":
            content = sys.stdin.read()
        else:
            patch_path = Path(args.check_patch)
            if not patch_path.exists():
                print(f"ERROR: no existe archivo patch {patch_path}")
                sys.exit(2)
            content = patch_path.read_text(encoding="utf-8", errors="replace")
        check_patch(content, rules)
    else:
        check_repo(Path(args.root).resolve(), rules)


if __name__ == "__main__":
    main()
