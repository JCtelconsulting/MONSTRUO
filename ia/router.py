from app.core import db
import re

import json
from fastapi import APIRouter, HTTPException, Body, Request
from app.core.ai import ai_local_openai_compat

router = APIRouter(prefix="/api/ultron", tags=["ultron"])

@router.post("/chat")
async def ultron_chat(request: Request):
    # Harden: Try to parse body manually to handle stringified JSON
    try:
        raw = await request.body()
        if not raw:
            msg = ""
        else:
            try:
                data = json.loads(raw)
                # Check for double stringify
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except:
                        pass # was just a string
                
                if isinstance(data, dict):
                    msg = data.get("message", "")
                else:
                    msg = str(data)
            except:
                msg = raw.decode("utf-8")
    except Exception as e:
        msg = ""

    msg = msg.lower().strip()
    
    # Default reply logic
    reply = "No entiendo esa orden específica. Comandos útiles: 'crear ticket', 'listar tickets', 'tablero', 'pendientes catalogo', 'estado sistema'."
    actions = []
    
    # Simple interactions
    if msg in ["hola", "buen dia", "inicio", "ayuda", "hello"]:
        reply = "Hola, soy ULTRON. Puedo ayudarte a gestionar la operación. Prueba diciendo 'estado sistema' o 'crear ticket'."
        return { "reply": reply, "actions": [] }

    # Intent: Crear Ticket
    # "crear ticket titulo X"
    if "crear ticket" in msg:
        # Extract title
        match = re.search(r"crear ticket (?P<title>.+)", msg)
        title = match.group("title") if match else "Sin titulo"
        
        # Action payload
        actions.append({
            "type": "create_ticket_modal", # UI should open modal pre-filled
            "payload": {
                "titulo": title.capitalize(),
                "tipo": "requerimiento",
                "descripcion": "Creado via ULTRON"
            }
        })
        reply = f"Entendido. Abriendo formulario para crear ticket: '{title}'."

    # Intent: Listar Tickets / Tablero
    elif "listar tickets" in msg or "ver tickets" in msg or "tablero" in msg:
        actions.append({
            "type": "navigate",
            "payload": { "module": "ticketera" }
        })
        reply = "Navegando a la Ticketera."

    # Intent: Catalogo Pendientes
    elif "pendientes" in msg and "catalogo" in msg:
        conn = db.get_conn()
        try:
            row = conn.execute("SELECT count(*) as n FROM cat_match_queue WHERE estado='pendiente'").fetchone()
            n = row['n']
            reply = f"Hay {n} items pendientes de revisión en el catálogo."
            if n > 0:
                actions.append({
                    "type": "navigate",
                    "payload": { "module": "bodega", "query": "?tab=pending" }
                })
        finally:
            conn.close()

    # Intent: Estado Sistema
    elif "estado" in msg and "sistema" in msg:
        # Check active tickets count
        conn = db.get_conn()
        try:
            n_open = conn.execute("SELECT count(*) as n FROM tks_tickets WHERE estado='abierto'").fetchone()['n']
            n_prog = conn.execute("SELECT count(*) as n FROM tks_tickets WHERE estado='en_progreso'").fetchone()['n']
            n_res = conn.execute("SELECT count(*) as n FROM tks_tickets WHERE estado='resuelto'").fetchone()['n']
            
            reply = f"Estado actual: {n_open} Tickets Abiertos, {n_prog} En Progreso, {n_res} Resueltos."
        finally:
            conn.close()
            
    # Intent: Sugerir Match (Demo)
    elif "sugerir" in msg and "match" in msg:
        actions.append({
            "type": "call_function",
            "payload": { "function": "demoSugerir" } # UI specific handler
        })
        reply = "Ejecutando simulación de sugerencia de match..."
    
    # LLM Fallback (Chat Real)
    else:
        if ai_local_openai_compat.is_enabled():
            # Build Context
            # TODO: Add more context based on user role or recent errors
            messages = [
                {"role": "system", "content": "Eres ULTRON, el IA de operaciones de Telconsulting. Responde breve, profesional y accionable. No inventes datos. Si no sabes, sugiere usar comandos exactos."},
                {"role": "user", "content": msg}
            ]
            llm_reply = ai_local_openai_compat.chat(messages)
            if llm_reply:
                reply = llm_reply
            else:
                reply += " (LLM no disponible momentáneamente)"
        else:
            # Deterministic fallback
            pass


    return {
        "reply": reply,
        "actions": actions
    }

@router.get("/status")
def ultron_status():
    return ai_local_openai_compat.check_status()
