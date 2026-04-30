from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from plataforma.core import db

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def run_migrations() -> None:
    logger.info("[MIGRATIONS] Iniciando chequeo de migraciones...")

    if not MIGRATIONS_DIR.exists():
        os.makedirs(MIGRATIONS_DIR, exist_ok=True)
        logger.info("[MIGRATIONS] Directorio creado: %s", MIGRATIONS_DIR)

    conn = db.get_conn()
    try:
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

        files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")])
        if not files:
            logger.info("[MIGRATIONS] No hay archivos de migración pendientes.")
            return

        for filename in files:
            row = conn.execute(
                "SELECT success FROM core.migration_log WHERE filename = %s",
                (filename,),
            ).fetchone()

            if row and row.get("success"):
                continue

            logger.info("[MIGRATIONS] Aplicando: %s", filename)
            file_path = MIGRATIONS_DIR / filename
            sql_content = file_path.read_text(encoding="utf-8")

            try:
                conn.execute(sql_content)
                now = datetime.now(timezone.utc).isoformat()
                if row:
                    conn.execute(
                        "UPDATE core.migration_log SET success = TRUE, applied_at = %s, error_message = NULL WHERE filename = %s",
                        (now, filename),
                    )
                else:
                    conn.execute(
                        "INSERT INTO core.migration_log (filename, applied_at, success) VALUES (%s, %s, TRUE)",
                        (filename, now),
                    )
                conn.commit()
                logger.info("[MIGRATIONS] Éxito: %s", filename)
            except Exception as e:
                conn.rollback()
                now = datetime.now(timezone.utc).isoformat()
                error_msg = str(e)
                logger.error("[MIGRATIONS] ERROR en %s: %s", filename, error_msg)
                if row:
                    conn.execute(
                        "UPDATE core.migration_log SET success = FALSE, applied_at = %s, error_message = %s WHERE filename = %s",
                        (now, error_msg, filename),
                    )
                else:
                    conn.execute(
                        "INSERT INTO core.migration_log (filename, applied_at, success, error_message) VALUES (%s, %s, FALSE, %s)",
                        (filename, now, error_msg),
                    )
                conn.commit()
                break
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
