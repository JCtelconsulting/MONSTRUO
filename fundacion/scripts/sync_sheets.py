"""CLI para correr el sync de planillas Google Sheets → DB.

Uso:
    docker exec monstruo-dev-fundacion python -m fundacion.scripts.sync_sheets
    docker exec monstruo-dev-fundacion python -m fundacion.scripts.sync_sheets --sede el-buen-camino

Pensado para correr por cron diario (3 AM) y a mano cuando haga falta.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Asegurar que el repo esté en sys.path al correr fuera del container
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from fundacion.core.env_loader import load_runtime_env

load_runtime_env(Path(__file__).resolve())

from fundacion.backend.services import drive_sync
from fundacion.core import db


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync de planillas Google Sheets → DB Fundación")
    parser.add_argument("--sede", help="Code de una sede específica (ej: el-buen-camino). "
                                       "Si no se pasa, se sincronizan todas las sedes activas.")
    parser.add_argument("--trigger", default="manual", choices=["cron", "manual", "api"])
    parser.add_argument("--actor", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if args.sede:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT id, code FROM fundacion.sedes WHERE code = %s", (args.sede,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            print(f"Sede '{args.sede}' no existe", file=sys.stderr)
            return 1
        result = drive_sync.sync_sede(row["id"])
        out = {
            "sede_id": result.sede_id,
            "sede_code": result.sede_code,
            "status": result.status,
            "alumnos_creados": result.alumnos_creados,
            "alumnos_actualizados": result.alumnos_actualizados,
            "alumnos_desaparecidos": result.alumnos_desaparecidos,
            "asistencias_insertadas": result.asistencias_insertadas,
            "asistencias_actualizadas": result.asistencias_actualizadas,
            "codigos_desconocidos": result.codigos_desconocidos,
            "error": result.error,
        }
    else:
        out = drive_sync.sync_todas(trigger=args.trigger, actor=args.actor)

    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    status = out.get("status") if "status" in out else "ok"
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
