from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fundacion.core import db

logger = logging.getLogger(__name__)

# Migraciones centrales del core. Clave en core.migration_log = filename a secas
# (retrocompatible con lo ya aplicado).
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
# Raíz del repo (…/plataforma/core/migrations.py -> parents[2]).
REPO_ROOT = Path(__file__).resolve().parents[2]


def _ensure_log_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS core.migration_log (
            id SERIAL PRIMARY KEY,
            filename TEXT UNIQUE NOT NULL,
            applied_at TEXT NOT NULL,
            success BOOLEAN DEFAULT TRUE,
            error_message TEXT
        );
    """)
    conn.commit()


def _apply_migration_dir(conn, migrations_dir: Path, key_prefix: str = "") -> None:
    """Aplica en orden las migraciones .sql de un directorio.

    La 'clave' que se guarda en core.migration_log es ``key_prefix + filename``,
    de modo que las migraciones de cada módulo (ticketera/, gta/, …) no
    colisionan con las del core ni entre sí aunque repitan el número (001, 002…).
    """
    if not migrations_dir.is_dir():
        return
    files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
    for filename in files:
        key = f"{key_prefix}{filename}"
        row = conn.execute(
            "SELECT success FROM core.migration_log WHERE filename = %s",
            (key,),
        ).fetchone()
        if row and row.get("success"):
            continue

        logger.info("[MIGRATIONS] Aplicando: %s", key)
        sql_content = (migrations_dir / filename).read_text(encoding="utf-8")
        try:
            # execute_script: trata el SQL como literal (no parsea `%` como
            # placeholder) y soporta múltiples statements por archivo.
            conn.execute_script(sql_content)
            now = datetime.now(timezone.utc).isoformat()
            if row:
                conn.execute(
                    "UPDATE core.migration_log SET success = TRUE, applied_at = %s, error_message = NULL WHERE filename = %s",
                    (now, key),
                )
            else:
                conn.execute(
                    "INSERT INTO core.migration_log (filename, applied_at, success) VALUES (%s, %s, TRUE)",
                    (key, now),
                )
            conn.commit()
            logger.info("[MIGRATIONS] Éxito: %s", key)
        except Exception as e:
            conn.rollback()
            now = datetime.now(timezone.utc).isoformat()
            error_msg = str(e)
            logger.error("[MIGRATIONS] ERROR en %s: %s", key, error_msg)
            if row:
                conn.execute(
                    "UPDATE core.migration_log SET success = FALSE, applied_at = %s, error_message = %s WHERE filename = %s",
                    (now, error_msg, key),
                )
            else:
                conn.execute(
                    "INSERT INTO core.migration_log (filename, applied_at, success, error_message) VALUES (%s, %s, FALSE, %s)",
                    (key, now, error_msg),
                )
            conn.commit()
            # No seguir con el resto de ESTE directorio (las siguientes pueden
            # depender de la que falló), pero sí continuar con los demás módulos.
            break


def _module_migration_dirs() -> list[tuple[Path, str]]:
    """Descubre ``<repo>/<modulo>/migrations/`` de cada módulo (excepto
    plataforma, que se maneja con clave a secas por retrocompatibilidad).

    Esto es lo que faltaba: antes el engine SOLO miraba plataforma/migrations,
    así que migraciones como ticketera/migrations/002 nunca se aplicaban en PROD
    y al promover dev→prod fallaba con 'relation ... does not exist'.
    """
    dirs: list[tuple[Path, str]] = []
    try:
        for mod in sorted(REPO_ROOT.iterdir()):
            if not mod.is_dir() or mod.name == "plataforma":
                continue
            mdir = mod / "migrations"
            if mdir.is_dir():
                dirs.append((mdir, f"{mod.name}/"))
    except Exception as e:
        logger.warning("[MIGRATIONS] No se pudieron listar módulos: %s", e)
    return dirs


def run_migrations() -> None:
    logger.info("[MIGRATIONS] Iniciando chequeo de migraciones...")

    if not MIGRATIONS_DIR.exists():
        os.makedirs(MIGRATIONS_DIR, exist_ok=True)
        logger.info("[MIGRATIONS] Directorio creado: %s", MIGRATIONS_DIR)

    conn = db.get_conn()
    try:
        _ensure_log_table(conn)
        # Separación: Fundación corre SOLO sus propias migraciones (fundacion/migrations).
        # No descubre otros módulos del repo — su DB es propia (fase 3) y su ciclo de
        # vida es independiente del de Monstruo.
        _apply_migration_dir(conn, MIGRATIONS_DIR, key_prefix="")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
