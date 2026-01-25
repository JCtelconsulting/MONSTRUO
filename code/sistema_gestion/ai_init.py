#!/usr/bin/env python3
"""
Inicialización de tablas para Asistente Operaciones IA.
Crea ai_event_queue y ai_recommendations.
"""
import sqlite3
import os

# DB path relativo a la ubicación del script
DB_PATH = "../../data/db/monstruo.db"

def init_ai_tables():
    """Crear tablas para sistema de asistente IA"""
    db_abs = os.path.join(os.path.dirname(__file__), DB_PATH)
    conn = sqlite3.connect(db_abs)
    conn.row_factory = sqlite3.Row
    
    try:
        # Tabla: Cola de eventos para procesar
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_event_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            bridge_message_id INTEGER,
            payload_json TEXT DEFAULT '{}',
            status TEXT DEFAULT 'new',
            created_at TEXT NOT NULL,
            processed_at TEXT DEFAULT '',
            error TEXT DEFAULT ''
        )
        """)
        
        # Tabla: Recomendaciones generadas por IA
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            source TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            recommended_actions_json TEXT DEFAULT '[]',
            customer_message_draft TEXT DEFAULT '',
            requires_approval INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            raw_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            approved_at TEXT DEFAULT '',
            approved_by TEXT DEFAULT '',
            FOREIGN KEY (event_id) REFERENCES ai_event_queue(id)
        )
        """)
        
        # Índices
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_event_status ON ai_event_queue(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_event_kind ON ai_event_queue(kind)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_rec_status ON ai_recommendations(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_rec_event ON ai_recommendations(event_id)")
        
        conn.commit()
        print("✅ Tablas AI creadas: ai_event_queue, ai_recommendations")
        
        # Verificar
        count_events = conn.execute("SELECT COUNT(*) as n FROM ai_event_queue").fetchone()["n"]
        count_recs = conn.execute("SELECT COUNT(*) as n FROM ai_recommendations").fetchone()["n"]
        print(f"   - ai_event_queue: {count_events} eventos")
        print(f"   - ai_recommendations: {count_recs} recomendaciones")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error creando tablas AI: {e}")
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(init_ai_tables())
