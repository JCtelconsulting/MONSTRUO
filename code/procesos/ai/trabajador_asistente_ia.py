#!/usr/bin/env python3
"""
AI Assistant Worker - Procesa eventos y genera recomendaciones con Ollama.
"""
import sqlite3
import json
import os
import httpx
from datetime import datetime

DB_PATH = "../../data/db/monstruo.db"
PLAYBOOKS_DIR = "../../../docs/playbooks"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
AI_MODEL = os.getenv("AI_MODEL", "llama3.2:latest")

def now_utc_iso():
    return datetime.utcnow().isoformat() + "+00:00"

def load_playbook(playbook_name):
    """Cargar contenido de playbook"""
    playbook_path = os.path.join(os.path.dirname(__file__), PLAYBOOKS_DIR, f"{playbook_name}.md")
    if os.path.exists(playbook_path):
        with open(playbook_path, "r", encoding="utf-8") as f:
            return f.read()
    return None

def map_event_to_playbook(event_row):
    """Mapear evento a playbook apropiado"""
    payload_str = event_row.get("payload_json", "{}")
    kind = event_row.get("kind", "")
    
    try:
        payload = json.loads(payload_str)
    except:
        payload = {}
    
    # Detectar errores de integración
    if "integration_parrotfy_payments_api_500" in json.dumps(payload):
        return "integration_parrotfy_payments_api_500"
    
    # Detectar missing invoices
    if "missing_invoice" in kind.lower() or "missing_in_laudus" in json.dumps(payload):
        return "parrotfy_missing_invoice"
    
    # Fallback
    return "generic"

def build_prompt(playbook_content, event_data):
    """Construir prompt estructurado para Ollama"""
    prompt = f"""Eres un Asistente Operacional IA para Monstruo, sistema de gestión operativa.

Tu tarea: analizar evento y generar recomendación estructurada siguiendo el playbook.

PLAYBOOK:
{playbook_content}

EVENT DAT A:
```json
{json.dumps(event_data, indent=2, ensure_ascii=False)}
```

INSTRUCCIONES:
1. NO inventar datos no presentes en EVENT DATA
2. NO recomendar acciones externas (solo workflow interno)
3. Generar SOLO salida JSON con estos campos exactos:

{{
  "title": "Título conciso del problema",
  "summary": "Resumen ejecutivo 2-3 líneas",
  "recommended_actions_internal": [
    "Acción 1",
    "Acción 2",
    "Acción 3"
  ],
  "customer_message_draft": "Borrador de mensaje al cliente (NO ENVIAR, solo draft)"
}}

RESPUESTA (solo JSON, sin markdown):"""
    
    return prompt

def call_ollama(prompt):
    """Llamar a Ollama API"""
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(OLLAMA_URL, json={
                "model": AI_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            })
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
    except Exception as e:
        raise Exception(f"Ollama API error: {e}")

def process_event(conn, event_row):
    """Procesar un evento y generar recomendación"""
    event_id = event_row["id"]
    
    # Mapear a playbook
    playbook_name = map_event_to_playbook(event_row)
    playbook_content = load_playbook(playbook_name)
    
    if not playbook_content:
        playbook_content = load_playbook("generic")
    
    print(f"INFO: Procesando evento {event_id} con playbook '{playbook_name}'")
    
    # Construir prompt
    event_data = {
        "source": event_row.get("source"),
        "kind": event_row.get("kind"),
        "payload": json.loads(event_row.get("payload_json", "{}")),
        "created_at": event_row.get("created_at")
    }
    
    prompt = build_prompt(playbook_content, event_data)
    
    # Llamar Ollama
    try:
        response_text = call_ollama(prompt)
        recommendation = json.loads(response_text)
    except Exception as e:
        # Si falla, crear recomendación manual
        print(f"WARN: Ollama falló para evento {event_id}: {e}")
        recommendation = {
            "title": f"Evento {event_row.get('kind')} requiere revisión",
            "summary": f"Error procesando con IA: {str(e)[:100]}",
            "recommended_actions_internal": ["Revisar manualmente el evento"],
            "customer_message_draft": ""
        }
        response_text = json.dumps(recommendation)
    
    # Guardar recomendación
    ts = now_utc_iso()
    conn.execute("""
        INSERT INTO ai_recommendations (
            event_id, source, kind, title, summary,
            recommended_actions_json, customer_message_draft,
            requires_approval, status, raw_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'pending', ?, ?)
    """, (
        event_id,
        event_row.get("source"),
        event_row.get("kind"),
        recommendation.get("title", "Sin título"),
        recommendation.get("summary", ""),
        json.dumps(recommendation.get("recommended_actions_internal", [])),
        recommendation.get("customer_message_draft", ""),
        response_text,
        ts
    ))
    
    # Marcar evento como procesado
    conn.execute("""
        UPDATE ai_event_queue
        SET status = 'done', processed_at = ?
        WHERE id = ?
    """, (ts, event_id))
    
    # Publicar al Bridge
    rec_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.execute("""
        INSERT INTO bridge_messages (
            thread_id, from_agent, to_agent, kind, title, body, payload_json,
            requires_approval, approval_status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'na', ?)
    """, (
        "jarvis",
        "monstruo_ai",
        "all",
        "ai_recommendation",
        recommendation.get("title"),
        recommendation.get("summary"),
        json.dumps({"recommendation_id": rec_id, "event_id": event_id}),
        ts
    ))
    
    # Si el evento tiene case_id, agregar comentario en workflow
    try:
        payload = json.loads(event_row.get("payload_json", "{}"))
        case_id = payload.get("case_id")
        if case_id:
            comment = f"""🤖 **Recomendación IA** (ID: {rec_id})

{recommendation.get('summary')}

**Acciones sugeridas:**
{chr(10).join(f'- {a}' for a in recommendation.get('recommended_actions_internal', []))}

*Esta recomendación requiere aprobación manual.*
"""
            conn.execute("""
                INSERT INTO task_comments (task_id, author, comment, created_at)
                SELECT id, 'ai_assistant', ?, ?
                FROM tasks
                WHERE case_id = ?
                LIMIT 1
            """, (comment, ts, case_id))
    except:
        pass  # Si falla, no es crítico
    
    conn.commit()
    print(f"✅ Recomendación {rec_id} creada para evento {event_id}")

def main():
    db_path = os.path.join(os.path.dirname(__file__), DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        # Tomar eventos pendientes (máximo 10 por ejecución)
        events = conn.execute("""
            SELECT id, source, kind, bridge_message_id, payload_json, created_at
            FROM ai_event_queue
            WHERE status = 'new'
            ORDER BY created_at ASC
            LIMIT 10
        """).fetchall()
        
        print(f"INFO: Procesando {len(events)} eventos pendientes")
        
        for event in events:
            try:
                process_event(conn, event)
            except Exception as e:
                # Marcar como fallido
                ts = now_utc_iso()
                conn.execute("""
                    UPDATE ai_event_queue
                    SET status = 'failed', error = ?, processed_at = ?
                    WHERE id = ?
                """, (str(e)[:500], ts, event["id"]))
                conn.commit()
                print(f"❌ Error procesando evento {event['id']}: {e}")
        
        print(f"✅ Worker completado")
        return 0
        
    except Exception as e:
        print(f"❌ Error en worker: {e}")
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
