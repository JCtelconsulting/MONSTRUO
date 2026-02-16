import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

# Override host for local execution if needed
import os
db_url = os.environ.get("DB_URL", "")
if "db" in db_url and "localhost" not in db_url:
    print("Patching DB_URL for local execution (db -> localhost)")
    os.environ["DB_URL"] = db_url.replace("@db:", "@localhost:")

from app.core import db

def migrate():
    print(f"Added {CODE_DIR} to path.")
    print("Connecting to DB...")
    
    conn = db.get_conn()
    try:
        print("Creating PMO tables if not exist...")
        
        # pmo_proyectos
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pmo_proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            cliente_nombre TEXT,
            presupuesto_venta REAL DEFAULT 0,
            fecha_inicio TEXT,
            fecha_fin_estimada TEXT,
            estado TEXT DEFAULT 'borrador',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """)
        # Index pmo_proyectos
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pmo_proyectos_estado ON pmo_proyectos(estado);"
        )

        # pmo_bitacora_ia
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pmo_bitacora_ia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER NOT NULL,
            origen TEXT DEFAULT 'manual',
            contenido_raw TEXT,
            estado_procesamiento TEXT DEFAULT 'pendiente',
            resumen_ia TEXT,
            acciones_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(proyecto_id) REFERENCES pmo_proyectos(id)
        );
        """)
        # Index pmo_bitacora_ia
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pmo_bitacora_proyecto ON pmo_bitacora_ia(proyecto_id);"
        )

        conn.commit()
        print("Migration successful: PMO tables created.")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
