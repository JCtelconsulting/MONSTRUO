from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from app.core import db, deps
from app.core.audit_decorator import audit_action

router = APIRouter(prefix="/api/fundacion", tags=["fundacion"])

class TareaFundacion(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    asignado_a: Optional[str] = None
    curso: Optional[str] = None
    categoria: Optional[str] = None
    categoria_madre: Optional[str] = None
    subcategoria: Optional[str] = None
    color: Optional[str] = "#4facfe"
    estado: Optional[str] = "pendiente"
    reporte: Optional[str] = None
    imprevistos: Optional[str] = None

@router.get("/tareas")
async def list_tareas(
    request: Request, 
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    user: dict = Depends(deps.require_permission("fundacion:read"))
):
    """
    Lista tareas del calendario. Soporta filtrado opcional por rango de fechas.
    Sin parámetros devuelve todas las tareas (carga inicial rápida para cache del cliente).
    """
    conn = db.get_conn()
    try:
        if start or end:
            query = "SELECT * FROM fundacion_tareas"
            params = []
            clauses = []
            if start:
                clauses.append("fecha_inicio >= %s")
                params.append(start)
            if end:
                clauses.append("fecha_inicio <= %s")
                params.append(end)
            query += " WHERE " + " AND ".join(clauses) + " ORDER BY fecha_inicio ASC"
            rows = conn.execute(query, tuple(params)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM fundacion_tareas ORDER BY fecha_inicio ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@router.post("/tareas")
@audit_action("CREATE_FUNDACION_TASK", severity="info")
async def create_tarea(tarea: TareaFundacion, user: dict = Depends(deps.require_permission("fundacion:write"))):
    """
    Crea una nueva tarea.
    """
    conn = db.get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO fundacion_tareas (titulo, descripcion, fecha_inicio, fecha_fin, asignado_a, creado_by, color, estado, categoria, categoria_madre, subcategoria, curso)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (tarea.titulo, tarea.descripcion, tarea.fecha_inicio, tarea.fecha_fin, tarea.asignado_a, user["username"], tarea.color, tarea.estado, tarea.categoria, tarea.categoria_madre, tarea.subcategoria, tarea.curso))
        new_id = cur.fetchone()['id']
        conn.commit()
        return {"ok": True, "id": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.patch("/tareas/{tid}")
async def update_tarea(tid: int, update: Dict[str, Any], user: dict = Depends(deps.require_permission("fundacion:read"))):
    """
    Actualiza una tarea.
    """
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM fundacion_tareas WHERE id = %s", (tid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
        roles = user.get("roles", [])
        is_monitora = any(r in ["admin", "monitora", "gerencia", "ejecutiva"] for r in roles)
        is_owner = row["asignado_a"] == user["username"]
        
        if not is_monitora and not is_owner:
            raise HTTPException(status_code=403, detail="No tiene permisos sobre esta tarea")
            
        fields = []
        values = []
        
        # Campos que requieren marcar reportado_at
        reporting_fields = ["reporte", "imprevistos"]
        should_set_report_time = False

        # Filtrar campos permitidos
        allowed_fields = [
            "titulo", "descripcion", "fecha_inicio", "fecha_fin", 
            "asignado_a", "color", "estado", "reporte", "imprevistos", 
            "categoria", "categoria_madre", "subcategoria", "curso"
        ]
        
        if not is_monitora:
            allowed_fields = ["estado", "reporte", "imprevistos"]
            
        for k, v in update.items():
            if k in allowed_fields:
                fields.append(f"{k} = %s")
                values.append(v)
                if k in reporting_fields:
                    should_set_report_time = True
        
        if should_set_report_time:
            fields.append("reportado_at = CURRENT_TIMESTAMP")

        if not fields:
            return {"ok": True, "message": "No changes applied"}
            
        values.append(tid)
        query = f"UPDATE fundacion_tareas SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s"
        
        conn.execute(query, tuple(values))
        conn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/tareas/{tid}")
@audit_action("DELETE_FUNDACION_TASK", severity="warning")
async def delete_tarea(tid: int, user: dict = Depends(deps.require_permission("fundacion:write"))):
    """
    Elimina una tarea. Solo monitoras/admin.
    """
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM fundacion_tareas WHERE id = %s", (tid,))
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
