#!/usr/bin/env python3
"""
Enqueue Bridge Events para procesamiento IA.
Lee bridge_messages recientes y encola eventos relevantes.
"""
import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = "../../data/db/monstruo.db"
STATE_FILE = "../../data/.enqueue_state"

def now_utc_iso():
    return datetime.utcnow().isoformat() + "+00:00"

def get_last_run():
    """Leer timestamp de última ejecución"""
    state_path = os.path.join(os.path.dirname(__file__), STATE_FILE)
    if os.path.exists(state_path):
        with open(state_path, "r") as f:
            return f.read().strip()
    # Primera ejecución: últimas 24 horas
    return (datetime.utcnow() - timedelta(hours=24)).isoformat() + "+00:00"

def save_last_run(timestamp):
    """Guardar timestamp de ejecución"""
    state_path = os.path.join(os.path.dirname(__file__), STATE_FILE)
    with open(state_path, "w") as f:
        f.write(timestamp)

def is_relevant_event(msg_row):
    """Determinar si evento es relevante para IA"""
    kind = msg_row.get("kind", "")
    source = msg_row.get("source", "")
    title = msg_row.get("title", "")
    body = msg_row.get("body", "")
    
    # Kinds relevantes
    if kind in ["workflow_dedupe_result", "proposal", "status"]:
        return True
    
    # Detectar errores
    if "error" in kind.lower() or "error" in title.lower():
        return True
    
    if "integration_" in title.lower() or "500" in body:
        return True
    
    return False

def main():
    db_path = os.path.join(os.path.dirname(__file__), DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        last_run = get_last_run()
        ts = now_utc_iso()
        
        print(f"INFO: Encolando eventos desde {last_run}")
        
        # Leer bridge_messages recientes
        messages = conn.execute("""
            SELECT id, thread_id, from_agent, to_agent, kind, title, body, payload_json, created_at
            FROM bridge_messages
            WHERE created_at > ?
            ORDER BY created_at ASC
            LIMIT 200
        """, (last_run,)).fetchall()
        
        print(f"INFO: Encontrados {len(messages)} mensajes bridge nuevos")
        
        enqueued = 0
        skipped = 0
        
        for msg in messages:
            msg_dict = dict(msg)
            
            # Filtrar relevantes
            if not is_relevant_event(msg_dict):
                skipped += 1
                continue
            
            # Verificar si ya está encolado (idempotencia)
            exists = conn.execute("""
                SELECT 1 FROM ai_event_queue
                WHERE bridge_message_id = ?
            """, (msg["id"],)).fetchone()
            
            if exists:
                skipped += 1
                continue
            
            # Encolar
            source = msg_dict.get("from_agent", "bridge")
            kind = msg_dict.get("kind", "unknown")
            payload = msg_dict.get("payload_json", "{}")
            
            conn.execute("""
                INSERT INTO ai_event_queue (
                    source, kind, bridge_message_id, payload_json, status, created_at
                )
                VALUES (?, ?, ?, ?, 'new', ?)
            """, (source, kind, msg["id"], payload, ts))
            
            enqueued += 1
        
        conn.commit()
        save_last_run(ts)
        
        print(f"✅ Encolados: {enqueued} eventos")
        print(f"   Ignorados: {skipped} (no relevantes o duplicados)")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error encolando eventos: {e}")
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
