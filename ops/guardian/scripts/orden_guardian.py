#!/usr/bin/env python3
import json
import os
import sys
import fnmatch
import argparse
import re
from typing import List, Dict, Tuple

CANONICAL_RULES = "/srv/monstruo/docs/estructura_repo.json"

def load_rules():
    try:
        with open(CANONICAL_RULES, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"CRITICAL: No se pudo cargar reglas canónicas: {e}")
        sys.exit(1)

def validate_path(rel_path: str, rules_data: dict, is_dir: bool = False) -> List[str]:
    """Valida un path relativo contra las reglas. Retorna lista de violaciones."""
    violations = []
    
    # 1. Blocked Paths (Glob patterns)
    # Aplica tanto a archivos como directorios (ej: code/venv)
    for blocked in rules_data.get("blocked_paths", []):
        if fnmatch.fnmatch(rel_path, blocked):
            violations.append(f"BLOCKED: '{rel_path}' coincide con patrón prohibido '{blocked}'")
            return violations

    # 2. Root Checks
    parts = rel_path.split('/')
    if len(parts) == 1:
        # Es archivo/dir en raíz
        if rel_path not in rules_data.get("root_allowed", []):
            violations.append(f"ROOT: '{rel_path}' no permitido en la raíz")
        return violations

    # 3. Extension Checks (por carpeta)
    # SOLO para archivos. Directorios se saltan este check.
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
        _, ext = os.path.splitext(rel_path)
        if ext not in allowed_exts:
            violations.append(f"EXT: '{rel_path}' tiene extensión '{ext}' no permitida en '{matched_rule_key}' {allowed_exts}")

    return violations

def check_repo(rules):
    print("--- MODO SCANNER (REPO COMPLETO) ---")
    all_violations = []
    
    # Check raíz específicamente si os.walk no la cubre bien
    # (os.walk empieza en root, pero root mismo no es 'entry' en root... loop abajo cubre hijos)
    
    for root, dirs, files in os.walk("/srv/monstruo"):
        if ".git" in root or ".agent" in root:
            continue
            
        # Validar directorios
        for d in dirs:
            full_path = os.path.join(root, d)
            rel_path = os.path.relpath(full_path, "/srv/monstruo")
            v = validate_path(rel_path, rules, is_dir=True)
            all_violations.extend(v)

        # Validar archivos
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, "/srv/monstruo")
            v = validate_path(rel_path, rules, is_dir=False)
            all_violations.extend(v)

    report_and_exit(all_violations)

def check_patch(diff_content: str, rules):
    print("--- MODO GATEKEEPER (PATCH CHECK) ---")
    paths_to_check = []
    for line in diff_content.splitlines():
        match = re.search(r'^\+\+\+\s+b/(.*)', line)
        if match:
            path = match.group(1)
            paths_to_check.append(path)
            
    if not paths_to_check:
        print("WARN: No se detectaron rutas en el patch enviado.")
        sys.exit(0)

    print(f"Validando {len(paths_to_check)} archivos en el patch...")
    all_violations = []
    for p in paths_to_check:
        # Asumimos que patch toca archivos
        v = validate_path(p, rules, is_dir=False)
        all_violations.extend(v)

    report_and_exit(all_violations)

def report_and_exit(violations):
    if violations:
        print(f"FAIL: Se encontraron {len(violations)} violaciones a las reglas.")
        for i, v in enumerate(violations):
            if i >= 20: 
                print(f"... y {len(violations)-20} mas.")
                break
            print(v)
        sys.exit(1)
    else:
        print("PASS: Estructura conforme a reglas.")
        sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="Guardian del Orden - Validador de Estructura y Parches")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-repo", action="store_true", help="Escanear todo el repositorio (default)")
    group.add_argument("--check-patch", help="Validar archivo de patch/diff (usar '-' para stdin)")
    
    args = parser.parse_args()
    rules = load_rules()

    if args.check_patch:
        content = ""
        if args.check_patch == "-":
            content = sys.stdin.read()
        else:
            if os.path.exists(args.check_patch):
                with open(args.check_patch, 'r') as f:
                    content = f.read()
            else:
                print(f"ERROR: No existe archivo patch {args.check_patch}")
                sys.exit(2)
        check_patch(content, rules)
    else:
        check_repo(rules)

if __name__ == "__main__":
    main()
