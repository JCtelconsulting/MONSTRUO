#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from getpass import getpass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from plataforma.core import auth_service, db, security


def main() -> int:
    parser = argparse.ArgumentParser(description="Crea o actualiza un usuario manualmente")
    parser.add_argument("--username", default="admin_test")
    parser.add_argument(
        "--password",
        default=None,
        help="Si no se entrega, se pedirá por consola (evita exponer en history).",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lee la contraseña desde stdin (ej: `printf 'x' | ... --password-stdin`).",
    )
    parser.add_argument("--role", default="admin")
    parser.add_argument("--upsert", action="store_true", help="Si existe, actualiza password/role")
    args = parser.parse_args()

    username = str(args.username or "").strip()
    if not username:
        print("ERROR: --username es requerido.")
        return 2

    role = str(args.role or "").strip()
    if not role:
        print("ERROR: --role es requerido.")
        return 2

    password = args.password
    if args.password_stdin:
        password = sys.stdin.read().rstrip("\n")
    if password is None:
        try:
            password = getpass("Password: ")
        except (EOFError, KeyboardInterrupt):
            print("ERROR: Password requerido (usa --password o ejecuta en un TTY).")
            return 2

    # Asegurar schemas/tablas antes de operar
    db.init_db()

    conn = db.get_conn()
    try:
        existing = conn.execute(
            "SELECT username FROM users WHERE username=?", (username,)
        ).fetchone()

        if existing and not args.upsert:
            print(f"Usuario ya existe: {username}. Usa --upsert para actualizar.")
            return 0

        if existing and args.upsert:
            hashed = security.get_password_hash(password)
            conn.execute(
                "UPDATE users SET role=?, password_hash=? WHERE username=?",
                (role, hashed, username),
            )
            conn.commit()
            print(f"Usuario actualizado: {username}")
            return 0

        auth_service.create_user(username, password, role)
        print(f"Usuario creado: {username}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
