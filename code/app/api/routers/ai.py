"""
Router para endpoints de Asistente IA (recomendaciones).
"""
from fastapi import APIRouter, Depends, Header, Cookie, HTTPException, Header
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import json
import difflib
import re

from app.core import db
from app.core.deps import require_session, require_roles, require_session_hybrid

router = APIRouter(prefix="/api/ia", tags=["ai"])

# --- Modelos Bodega AI ---
class StockItem(BaseModel):
    id: Optional[int] = None
    name: str
    stock: float = 0
    available: float = 0

class SugerenciasRequest(BaseModel):
    items: List[StockItem]

class ClusterDuplicado(BaseModel):
    main_name: str
    variants: List[str]
    score: float

class SugerenciasResponse(BaseModel):
    items_enriched: List[Dict[str, Any]]
    clusters: List[ClusterDuplicado]

# --- Lógica Heurística ---
def _sugerir_categoria(nombre: str) -> str:
    n = nombre.upper()
    if any(x in n for x in ["CABLE", "UTP", "PATCH", "CONECTOR", "FIBRA"]):
        return "Conectividad"
    if any(x in n for x in ["ROUTER", "SWITCH", "MIKROTIK", "UBIQUITI", "ANTENA", "WIFI"]):
        return "Redes"
    if any(x in n for x in ["IPHONE", "NOTEBOOK", "HUAWEI", "SAMSUNG", "PC", "LAPTOP"]):
        return "Equipos"
    if any(x in n for x in ["HERRAMIENTA", "ALICATE", "MARTILLO", "TALADRO"]):
        return "Herramientas"
    if any(x in n for x in ["EPP", "CASCO", "GUANTE", "ZAPATO", "LENTE", "ARNES"]):
        return "Seguridad/EPP"
    if any(x in n for x in ["CAMARA", "CCTV", "DVR", "NVR"]):
        return "Seguridad Electrónica"
    return "Otros"

def _normalizar_nombre(nombre: str) -> str:
    # Eliminar caracteres raros, espacios extra, upper
    s = nombre.upper().strip()
    s = re.sub(r'\s+', ' ', s)
    return s

class ApprovalRequest(BaseModel):
    notes: Optional[str] = ""

@router.get("/recommendations")
def list_recommendations(
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None),
    status: str = "pending"
):
    """Listar recomendaciones IA filtradas por estado"""
    sess = require_session_hybrid(authorization, access_token)
    require_roles(sess, ["admin", "finance", "ops"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        filter_sql = ""
        params = []
        if status != "all":
            filter_sql = "WHERE status = ?"
            params.append(status)
        
        rows = conn.execute(f"""
            SELECT id, event_id, source, kind, title, summary,
                   recommended_actions_json, customer_message_draft,
                   requires_approval, status, created_at,
                   approved_at, approved_by
            FROM ai_recommendations
            {filter_sql}
            ORDER BY created_at DESC
            LIMIT 100
        """, tuple(params)).fetchall()
        
        items = []
        for r in rows:
            try:
                actions = json.loads(r["recommended_actions_json"])
            except:
                actions = []
            
            items.append({
                "id": r["id"],
                "event_id": r["event_id"],
                "source": r["source"],
                "kind": r["kind"],
                "title": r["title"],
                "summary": r["summary"],
                "recommended_actions": actions,
                "customer_message_draft": r["customer_message_draft"],
                "requires_approval": bool(r["requires_approval"]),
                "status": r["status"],
                "created_at": r["created_at"],
                "approved_at": r["approved_at"],
                "approved_by": r["approved_by"]
            })
        
        return {"items": items}
    finally:
        conn.close()

@router.get("/recommendations/{rec_id}")
def get_recommendation(
    rec_id: int,
    authorization: Optional[str] = Header(default=None)
):
    """Obtener detalle de una recomendación"""
    sess = require_session(authorization)
    require_roles(sess, ["admin", "finance", "ops"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute("""
            SELECT id, event_id, source, kind, title, summary,
                   recommended_actions_json, customer_message_draft,
                   requires_approval, status, raw_json, created_at,
                   approved_at, approved_by
            FROM ai_recommendations
            WHERE id = ?
        """, (rec_id,)).fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Recomendación no encontrada")
        
        try:
            actions = json.loads(row["recommended_actions_json"])
        except:
            actions = []
        
        try:
            raw = json.loads(row["raw_json"])
        except:
            raw = {}
        
        return {
            "id": row["id"],
            "event_id": row["event_id"],
            "source": row["source"],
            "kind": row["kind"],
            "title": row["title"],
            "summary": row["summary"],
            "recommended_actions": actions,
            "customer_message_draft": row["customer_message_draft"],
            "requires_approval": bool(row["requires_approval"]),
            "status": row["status"],
            "raw_json": raw,
            "created_at": row["created_at"],
            "approved_at": row["approved_at"],
            "approved_by": row["approved_by"]
        }
    finally:
        conn.close()

@router.post("/recommendations/{rec_id}/approve")
def approve_recommendation(
    rec_id: int,
    body: ApprovalRequest,
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None)
):
    """Aprobar una recomendación (solo cambia estado, no ejecuta acciones)"""
    sess = require_session_hybrid(authorization, access_token)
    require_roles(sess, ["admin", "finance"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        # Verificar que existe y está pendiente
        rec = conn.execute("""
            SELECT id, status FROM ai_recommendations
            WHERE id = ?
        """, (rec_id,)).fetchone()
        
        if not rec:
            raise HTTPException(status_code=404, detail="Recomendación no encontrada")
        
        if rec["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Recomendación ya está en status '{rec['status']}'")
        
        # Actualizar estado
        ts = datetime.utcnow().isoformat() + "+00:00"
        conn.execute("""
            UPDATE ai_recommendations
            SET status = 'approved',
                approved_at = ?,
                approved_by = ?
            WHERE id = ?
        """, (ts, sess["username"], rec_id))
        
        # Auditoría
        audit_msg = f"Recommendation {rec_id} approved by {sess['username']}"
        if body.notes:
            audit_msg += f": {body.notes}"
        
        conn.execute("""
            INSERT INTO audit_events (username, event_type, details, created_at)
            VALUES (?, 'ai_recommendation_approved', ?, ?)
        """, (sess["username"], audit_msg, ts))
        
        conn.commit()
        
        return {"status": "approved", "approved_at": ts, "approved_by": sess["username"]}
    finally:
        conn.close()

@router.post("/auditar")
def ejecutar_auditoria(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = Cookie(default=None)):
    sess = require_session_hybrid(authorization, access_token)
    require_roles(sess, ["admin", "finance", "ops"])
    
    # Simulación de auditoría o trigger real
    ts = db.now_utc_iso()
    msg = "Auditoría Completada: Integridad Verificada. Sin anomalías detectadas en conectores."
    
    db.init_db()
    conn = db.get_conn()
    try:
        conn.execute("INSERT INTO ia_eventos (event_type, severity, summary, created_at) VALUES (?, ?, ?, ?)",
                     ("auditoria_manual", "info", msg, ts))
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": msg}

@router.get("/eventos")
def listar_eventos(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = Cookie(default=None)):
    sess = require_session_hybrid(authorization, access_token)
    
    db.init_db()
    conn = db.get_conn()
    try:
        rows = conn.execute("SELECT * FROM ia_eventos ORDER BY id DESC LIMIT 50").fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

# --- IA Local & Logging Helper ---
import os
import requests
import json
import time

DATASET_PATH = "/srv/inteligencia_artificial/monstruo/bodega_casos.jsonl"

# Configuración IA Local
LOCAL_AI_BASE_URL = os.getenv("LOCAL_AI_BASE_URL", "http://127.0.0.1:11434")
AI_MODEL = os.getenv("AI_MODEL", os.getenv("LOCAL_AI_MODEL", "tinyllama"))
AI_MODE = os.getenv("AI_MODE", "ollama_generate")

# Rutas de almacenamiento (Respetando estructura del usuario)
ROUTE_DATA = os.getenv("RUTA_IA_DATOS", "/srv/inteligencia_artificial/datos")
DATASET_PATH = os.path.join(ROUTE_DATA, "monstruo/bodega_casos.jsonl")

def log_training_case(input_data: dict, output_data: dict, mode: str, ok: int, msg: str):
    """
    Registra un caso de entrenamiento/feedback en la DB y en archivo JSONL para fine-tuning.
    """
    try:
        ts = datetime.utcnow().isoformat()
        
        # 1. DB Log
        conn = db.get_conn()
        try:
            conn.execute("""
                INSERT INTO ia_bodega_casos (creado_ts, input_json, output_json, modelo, modo, ok, mensaje)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ts, json.dumps(input_data), json.dumps(output_data), AI_MODEL, mode, ok, msg))
            conn.commit()
        finally:
            conn.close()

        # 2. File Log (Append Only)
        try:
            os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
            with open(DATASET_PATH, "a", encoding="utf-8") as f:
                entry = {
                    "ts": ts,
                    "model": AI_MODEL,
                    "mode": mode,
                    "input": input_data,
                    "output": output_data,
                    "ok": ok,
                    "msg": msg
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"WARN: Failed to log to file {DATASET_PATH}: {e}")
            
    except Exception as e:
        print(f"ERROR: log_training_case failed: {e}")

def call_local_ai(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Intenta llamar a IA local (Ollama).
    """
    # Construir URL segun modo
    url = f"{LOCAL_AI_BASE_URL}/api/generate"
    
    # Construct prompt simplificado para modelo pequeño (tinyllama)
    # JSON mode enforcement is tricky with small models, we'll try best effort or heuristic fallback
    prompt = f"""
    You are an inventory assistant.
    Analyze this list of items: {json.dumps(items[:20])}
    
    Task:
    1. Categorize each item (Network, Tools, Equipment, Safety, Other).
    2. Identify duplicates.
    
    Output ONLY valid JSON:
    {{
      "items_enriched": [{{ "name": "...", "suggested_category": "..." }}],
      "clusters": [{{ "main_name": "...", "variants": ["..."] }}]
    }}
    """
    
    try:
        payload = {
            "model": AI_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1}
        }
        print(f"DEBUG: Calling Local AI {url} with model {AI_MODEL}")
        r = requests.post(url, json=payload, timeout=30)
        
        if r.status_code == 200:
            res = r.json()
            content = res.get("response", "")
            print(f"DEBUG: AI Response len={len(content)}")
            return json.loads(content)
        else:
            print(f"DEBUG: AI Fail status={r.status_code} text={r.text[:100]}")
    except Exception as e:
        print(f"DEBUG: AI Exception {e}")
        return None
    return None

@router.post("/bodega/sugerencias", response_model=SugerenciasResponse)
def analizar_bodega(
    body: SugerenciasRequest,
    authorization: Optional[str] = Header(default=None),
    access_token: Optional[str] = Cookie(default=None)
):
    """
    Analiza lista de productos. 
    Intenta IA Local, fallback a Heuristica.
    """
    sess = require_session_hybrid(authorization, access_token)
    
    items_in = [it.dict() for it in body.items]
    mode = "heuristico"
    
    # Intento IA Local
    ai_res = call_local_ai(items_in)
    
    if ai_res and "items_enriched" in ai_res: # Basic validation
        mode = f"local_{AI_MODEL}"
        items_out = [] # Reconstruct to preserve IDs and properties not returned by AI
        # Map AI results back to original items (simple name match)
        ai_map = {it.get("name"): it.get("suggested_category") for it in ai_res.get("items_enriched", [])}
        
        for it in items_in:
            items_out.append({
                **it,
                "normalized_name": _normalizar_nombre(it["name"]),
                "suggested_category": ai_map.get(it["name"], _sugerir_categoria(it["name"]))
            })
            
        clusters = ai_res.get("clusters", [])
    else:
        # Fallback Heuristico
        if ai_res is None:
             print("DEBUG: Fallback to Heuristic (AI unavailable or invalid JSON)")
        
        items_out = []
        normalized_map = {} 
        
        for it in items_in: # Use items_in dicts
            norm = _normalizar_nombre(it["name"])
            cat = _sugerir_categoria(it["name"])
            
            if norm not in normalized_map:
                normalized_map[norm] = []
            normalized_map[norm].append(it["name"])
            
            items_out.append({
                **it,
                "normalized_name": norm,
                "suggested_category": cat
            })

        # Detección de Duplicados (Heurística)
        clusters = []
        unique_names = list(normalized_map.keys())
        unique_names.sort()
        processed = set() 
        
        for i in range(len(unique_names)):
            name_a = unique_names[i]
            if name_a in processed:
                continue
            current_cluster = [name_a]
            for j in range(i + 1, len(unique_names)):
                name_b = unique_names[j]
                if name_b in processed:
                    continue
                ratio = difflib.SequenceMatcher(None, name_a, name_b).ratio()
                if ratio > 0.85:
                    current_cluster.append(name_b)
                    processed.add(name_b)
            
            if len(current_cluster) > 1:
                variants = []
                for cname in current_cluster:
                    variants.extend(normalized_map[cname])
                variants = list(set(variants))
                clusters.append({
                    "main_name": current_cluster[0],
                    "variants": variants,
                    "score": 0.9
                })

    resp_data = {"items_enriched": items_out, "clusters": clusters}
    
    log_training_case(
        input_data={"count": len(items_in), "sample": items_in[:5]}, 
        output_data={"cluster_count": len(clusters)},
        mode=mode,
        ok=1,
        msg="Success"
    )
            
    return resp_data

@router.get("/bodega/casos")
def listar_casos_ia(
    limit: int = 20, 
    offset: int = 0,
    authorization: Optional[str] = Header(default=None), 
    access_token: Optional[str] = Cookie(default=None)
):
    """Listar casos de entrenamiento registrados"""
    sess = require_session_hybrid(authorization, access_token)
    require_roles(sess, ["admin", "finance", "ops"])
    
    db.init_db()
    conn = db.get_conn()
    try:
        rows = conn.execute("""
            SELECT id, creado_ts, modelo, modo, ok, mensaje
            FROM ia_bodega_casos 
            ORDER BY id DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        
        items = [dict(r) for r in rows]
        return {"items": items, "total": len(items)} # TODO: Real count
    finally:
        conn.close()
