from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel
from datetime import date, datetime
import json
from app.core import db
from app.core.ai import ai_local_openai_compat as ai_local
from app.core.audit_decorator import audit_action

router = APIRouter(prefix="/api/pmo", tags=["pmo"])

# --- Models ---

class ProyectoCreate(BaseModel):
    nombre: str
    cliente_nombre: Optional[str] = None
    presupuesto_venta: float = 0
    fecha_inicio: Optional[date] = None
    fecha_fin_estimada: Optional[date] = None

class ProyectoUpdate(BaseModel):
    nombre: Optional[str] = None
    cliente_nombre: Optional[str] = None
    presupuesto_venta: Optional[float] = None
    fecha_inicio: Optional[date] = None
    fecha_fin_estimada: Optional[date] = None
    estado: Optional[str] = None # activo, pendiente_cliente, pendiente_pago, pendiente_interno, cerrado
    cuadrilla_info: Optional[str] = None # Placeholder for crew info

class ProyectoOut(BaseModel):
    id: int
    nombre: str
    estado: str
    presupuesto_venta: float
    created_at: datetime
    # Add other fields if needed for typed response

class BitacoraCreate(BaseModel):
    origen: str = "manual"
    contenido_raw: str
    proyecto_id: Optional[int] = None

# --- Endpoints ---

@router.post("/proyectos", response_model=Dict[str, Any])
def create_proyecto(proyecto: ProyectoCreate):
    conn = db.get_conn()
    try:
        # Default state logic handled by DB default call or explicit insert if needed
        # We'll stick to basic insert and let DB default 'borrador' or update later
        cur = conn.execute(
            """
            INSERT INTO pmo_proyectos (nombre, cliente_nombre, presupuesto_venta, fecha_inicio, fecha_fin_estimada, estado)
            VALUES (%s, %s, %s, %s, %s, 'borrador')
            RETURNING id
            """,
            (proyecto.nombre, proyecto.cliente_nombre, proyecto.presupuesto_venta, proyecto.fecha_inicio, proyecto.fecha_fin_estimada)
        )
        new_id = cur.fetchone()['id']
        conn.commit()
        return {"ok": True, "id": new_id, "message": "Proyecto creado exitosamente"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.get("/proyectos", response_model=List[Dict[str, Any]])
def list_proyectos():
    conn = db.get_conn()
    try:
        # Simple list for now
        rows = conn.execute("SELECT * FROM pmo_proyectos ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@router.patch("/proyectos/{pid}")
@audit_action("UPDATE_PROJECT_PMO", severity="info")
async def update_proyecto(pid: int, update: ProyectoUpdate, request: Request, background_tasks: BackgroundTasks):
    conn = db.get_conn()
    try:
        # Build dynamic query
        fields = []
        values = []
        if update.nombre is not None:
            fields.append("nombre = %s")
            values.append(update.nombre)
        if update.cliente_nombre is not None:
            fields.append("cliente_nombre = %s")
            values.append(update.cliente_nombre)
        if update.presupuesto_venta is not None:
            fields.append("presupuesto_venta = %s")
            values.append(update.presupuesto_venta)
        if update.fecha_inicio is not None:
            fields.append("fecha_inicio = %s")
            values.append(update.fecha_inicio)
        if update.fecha_fin_estimada is not None:
            fields.append("fecha_fin_estimada = %s")
            values.append(update.fecha_fin_estimada)
        if update.estado is not None:
            fields.append("estado = %s")
            values.append(update.estado)
        
        # Note: cuadrilla_info not in DB yet, ignoring for now or assumed planned for json field
        # For strict compliance, we should add the column first. 
        # Skipping cuadrilla persistence for this step to adhere to 'max 3 files' rule strictness 
        # unless necessary. User asked for "editable pero con logs".
        
        if not fields:
             return {"ok": True, "message": "No changes"}
        
        values.append(pid)
        query = f"UPDATE pmo_proyectos SET {', '.join(fields)} WHERE id = %s"
        
        conn.execute(query, tuple(values))
        conn.commit()
        return {"ok": True, "message": "Proyecto actualizado"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/bitacora/ingesta")
def ingesta_bitacora_ia(item: BitacoraCreate):
    """
    Endpoint para recibir texto libre (email/meet).
    Conecta con IA local para procesar 'resumen_ia' y 'acciones_json'.
    """
    
    # 1. Guardar RAW primero
    conn = db.get_conn()
    bitacora_id = None
    try:
        cur = conn.execute(
            """
            INSERT INTO pmo_bitacora_ia (proyecto_id, origen, contenido_raw, estado_procesamiento)
            VALUES (%s, %s, %s, 'pendiente')
            RETURNING id
            """,
            (item.proyecto_id, item.origen, item.contenido_raw)
        )
        bitacora_id = cur.fetchone()['id']
        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error DB Raw: {str(e)}")
    
    # 2. Procesar con IA (si está habilitada)
    resumen = "IA Deshabilitada"
    acciones = {}
    
    if ai_local.is_enabled():
        try:
            prompt_system = """
            Eres un Asistente PMO Experto. Analiza el siguiente texto (email o minuta) y extrae:
            1. 'resumen': Un resumen ejecutivo en 2 lineas.
            2. 'costos': Lista de posibles costos detectados (tipo: personal, vehiculo, material, otros) y monto estimado si aparece.
            3. 'tareas': Lista de tareas accionables y responsables sugeridos.
            
            Retorna SOLO JSON válido con estructura:
            {
              "resumen": "...",
              "acciones": {
                "costos": [{"tipo": "...", "descripcion": "...", "monto": 0}],
                "tareas": [{"descripcion": "...", "responsable": "..."}]
              }
            }
            """
            
            payload_ai = [
                {"role": "system", "content": prompt_system},
                {"role": "user", "content": item.contenido_raw}
            ]
            
            raw_response = ai_local.chat_completion(
                model="llama3:8b", # Or default model
                messages=payload_ai,
                temperature=0.2
            )
            
            # Intentar parsear JSON
            content = raw_response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            # Extraer JSON si hay markdown
            if "```json" in content:
                import re
                match = re.search(r"```json(.*?)```", content, re.DOTALL)
                if match:
                    content = match.group(1)
            
            try:
                data_ia = json.loads(content)
                resumen = data_ia.get("resumen", "Sin resumen")
                acciones = data_ia.get("acciones", {})
            except:
                resumen = f"Error parseando IA: {content[:100]}"
                
        except Exception as e:
             resumen = f"Error IA: {str(e)}"

    # 3. Actualizar DB con resultado
    try:
        conn = db.get_conn() # Reconnect if needed or reuse logic (db.get_conn returns new usually)
        conn.execute(
            """
            UPDATE pmo_bitacora_ia 
            SET resumen_ia = %s, acciones_json = %s, estado_procesamiento = 'procesado'
            WHERE id = %s
            """,
            (resumen, json.dumps(acciones), bitacora_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error guardando resultado IA: {e}")
    finally:
        conn.close()
        
    return {
        "ok": True,
        "bitacora_id": bitacora_id,
        "ia_result": {
            "resumen": resumen,
            "acciones": acciones
        }
    }
