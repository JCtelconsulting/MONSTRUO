#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CODE_DIR = PROJECT_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import auth_service, db, security


def main() -> int:
    parser = argparse.ArgumentParser(description="Crea o actualiza un usuario manualmente")
    parser.add_argument("--username", default="admin_test")
    parser.add_argument("--password", default="test1234")
    parser.add_argument("--role", default="admin")
    parser.add_argument("--upsert", action="store_true", help="Si existe, actualiza password/role")
    args = parser.parse_args()

    conn = db.get_conn()
    try:
        existing = conn.execute(
            "SELECT username FROM users WHERE username=?", (args.username.strip(),)
        ).fetchone()

        if existing and not args.upsert:
            print(f"Usuario ya existe: {args.username}. Usa --upsert para actualizar.")
            return 0

        if existing and args.upsert:
            hashed = security.get_password_hash(args.password)
            conn.execute(
                "UPDATE users SET role=?, password_hash=? WHERE username=?",
                (args.role.strip(), hashed, args.username.strip()),
            )
            conn.commit()
            print(f"Usuario actualizado: {args.username}")
            return 0

        auth_service.create_user(args.username, args.password, args.role)
        print(f"Usuario creado: {args.username}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
