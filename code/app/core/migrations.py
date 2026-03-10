import os
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
import json

from app.core import db

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

def run_migrations():
    """
    Motor de migraciones automáticas para MONSTRUO.
    Busca archivos .sql en code/migrations/ y los ejecuta en orden alfabético.
    """
    print("[MIGRATIONS] Iniciando chequeo de migraciones...")
    
    if not MIGRATIONS_DIR.exists():
        os.makedirs(MIGRATIONS_DIR, exist_ok=True)
        print(f"[MIGRATIONS] Directorio creado: {MIGRATIONS_DIR}")

    conn = db.get_conn()
    try:
        # 1. Asegurar tabla de logs
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

        # 2. Obtener lista de archivos
        files = sorted([f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")])
        if not files:
            print("[MIGRATIONS] No hay archivos de migración pendientes.")
            return

        # 3. Ejecutar pendientes
        for filename in files:
            # Verificar si ya se aplicó
            row = conn.execute(
                "SELECT success FROM core.migration_log WHERE filename = %s", 
                (filename,)
            ).fetchone()
            
            if row and row.get("success"):
                continue

            print(f"[MIGRATIONS] Aplicando: {filename}...")
            file_path = MIGRATIONS_DIR / filename
            with open(file_path, "r", encoding="utf-8") as f:
                sql_content = f.read()

            try:
                # Ejecutar el SQL (puede contener varias sentencias separadas por ;)
                # Nota: psycopg2 permite múltiples sentencias en un execute
                conn.execute(sql_content)
                
                # Registrar éxito
                now = datetime.now(timezone.utc).isoformat()
                if row: # Si existía pero falló, actualizamos
                    conn.execute(
                        "UPDATE core.migration_log SET success = TRUE, applied_at = %s, error_message = NULL WHERE filename = %s",
                        (now, filename)
                    )
                else:
                    conn.execute(
                        "INSERT INTO core.migration_log (filename, applied_at, success) VALUES (%s, %s, TRUE)",
                        (filename, now)
                    )
                conn.commit()
                print(f"[MIGRATIONS] Éxito: {filename}")
            except Exception as e:
                conn.rollback()
                now = datetime.now(timezone.utc).isoformat()
                error_msg = str(e)
                print(f"[MIGRATIONS] ERROR en {filename}: {error_msg}")
                
                if row:
                    conn.execute(
                        "UPDATE core.migration_log SET success = FALSE, applied_at = %s, error_message = %s WHERE filename = %s",
                        (now, error_msg, filename)
                    )
                else:
                    conn.execute(
                        "INSERT INTO core.migration_log (filename, applied_at, success, error_message) VALUES (%s, %s, FALSE, %s)",
                        (filename, now, error_msg)
                    )
                conn.commit()
                # Detenemos la cadena de migraciones si una falla por seguridad
                break

    finally:
        conn.close()

if __name__ == "__main__":
    run_migrations()
