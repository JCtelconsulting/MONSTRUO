from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from plataforma.core import auth_service, db, deps
from plataforma.core.audit_decorator import audit_action
from fundacion.backend.services import sedes as sedes_service
from fundacion.backend.services import membresias as memb_service

router = APIRouter(prefix="/api/fundacion", tags=["fundacion"])


def _user_id(user: dict) -> int:
    uid = sedes_service.usuario_id_de_username(user.get("username", ""))
    if not uid:
        raise HTTPException(status_code=401, detail="usuario no resoluble")
    return uid


def _is_admin(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    roles = [r.lower() for r in (user.get("roles") or [])]
    admin_roles = {"admin", "directora_social", "jefa_pedagogica", "coordinadora_territorial"}
    return role in admin_roles or any(r in admin_roles for r in roles)


def _normalize_sede_value(raw_value: Any) -> str:
    resolved = auth_service.resolve_fundacion_sede(raw_value)
    if resolved:
        return resolved

    normalized_scope = auth_service.normalize_fundacion_scope(
        {"is_global": False, "sedes": [raw_value], "cursos": []}
    )
    sedes = normalized_scope.get("sedes") or []
    return sedes[0] if sedes else ""


def _normalize_curso_value(raw_value: Any) -> str:
    return auth_service.resolve_fundacion_curso(raw_value)


def _is_target_in_scope(scope: Dict[str, Any], sede_value: str, curso_value: str) -> bool:
    if scope.get("is_global"):
        return True

    allowed_sedes = set(scope.get("sedes") or [])
    allowed_cursos = set(scope.get("cursos") or [])

    if allowed_sedes and sede_value not in allowed_sedes:
        return False
    if allowed_cursos and curso_value not in allowed_cursos:
        return False
    return True


def _is_task_in_scope(scope: Dict[str, Any], task_row: Dict[str, Any]) -> bool:
    sede_value = _normalize_sede_value(task_row.get("sede"))
    curso_value = _normalize_curso_value(task_row.get("curso"))
    return _is_target_in_scope(scope, sede_value, curso_value)


def _ensure_sede_access(user: dict, sede_id: Optional[int] = None, sede_code: Optional[str] = None):
    """Doble candado: backend rechaza si el usuario no tiene acceso a la sede.

    Admins/jefatura pasan siempre (super_scope vía función SQL). Otros roles
    solo pasan si tienen membresía vigente en la sede solicitada.
    """
    uid = _user_id(user)
    target_id = sede_id
    if target_id is None and sede_code:
        sede = sedes_service.get_sede_por_code(sede_code)
        target_id = sede["id"] if sede else None
    if target_id is None:
        # Sin sede target → libre (ej: listar sedes accesibles).
        return uid
    if not sedes_service.tiene_acceso_sede(uid, int(target_id)):
        raise HTTPException(status_code=403, detail="no tenés acceso a esta sede")
    return uid

class TareaFundacion(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    asignado_a: Optional[str] = None
    sede: Optional[str] = None
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
    scope = auth_service.get_user_fundacion_scope(user.get("username", ""))
    uid = _user_id(user)
    sedes_codes = sedes_service.sede_codes_accesibles(uid)
    is_admin = sedes_service.es_super_scope(uid) or _is_admin(user)

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

        items = [dict(r) for r in rows]

        # Capa 1: filtrar por sedes accesibles según membresías nuevas.
        if not is_admin:
            allowed = set(sedes_codes)
            items = [i for i in items if (i.get("sede") or "") in allowed or not i.get("sede")]

        # Capa 2 (fallback compat): scope viejo basado en fundacion_scope JSON.
        if scope.get("is_global") or is_admin:
            return items
        return [item for item in items if _is_task_in_scope(scope, item)]
    finally:
        conn.close()

@router.post("/tareas")
@audit_action("CREATE_FUNDACION_TASK", severity="info")
async def create_tarea(tarea: TareaFundacion, user: dict = Depends(deps.require_permission("fundacion:write"))):
    """
    Crea una nueva tarea.
    """
    scope = auth_service.get_user_fundacion_scope(user.get("username", ""))
    normalized_sede = _normalize_sede_value(tarea.sede)
    normalized_curso = _normalize_curso_value(tarea.curso)

    if not _is_target_in_scope(scope, normalized_sede, normalized_curso):
        raise HTTPException(status_code=403, detail="No tiene permisos para crear tareas fuera de su alcance Fundación")

    conn = db.get_conn()
    try:
        cur = conn.execute("""
            INSERT INTO fundacion_tareas (titulo, descripcion, fecha_inicio, fecha_fin, asignado_a, creado_by, sede, color, estado, categoria, categoria_madre, subcategoria, curso)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            tarea.titulo,
            tarea.descripcion,
            tarea.fecha_inicio,
            tarea.fecha_fin,
            tarea.asignado_a,
            user["username"],
            normalized_sede or None,
            tarea.color,
            tarea.estado,
            tarea.categoria,
            tarea.categoria_madre,
            tarea.subcategoria,
            normalized_curso or None,
        ))
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

        scope = auth_service.get_user_fundacion_scope(user.get("username", ""))
        if not _is_task_in_scope(scope, dict(row)):
            raise HTTPException(status_code=403, detail="No tiene permisos sobre esta tarea")

        target_sede = _normalize_sede_value(update.get("sede", row.get("sede")))
        target_curso = _normalize_curso_value(update.get("curso", row.get("curso")))
        if not _is_target_in_scope(scope, target_sede, target_curso):
            raise HTTPException(status_code=403, detail="No puede mover esta tarea fuera de su alcance Fundación")
        
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
            "asignado_a", "sede", "color", "estado", "reporte", "imprevistos", 
            "categoria", "categoria_madre", "subcategoria", "curso"
        ]
        
        if not is_monitora:
            allowed_fields = ["estado", "reporte", "imprevistos"]
            
        for k, v in update.items():
            if k in allowed_fields:
                value = v
                if k == "sede":
                    value = _normalize_sede_value(v) or None
                elif k == "curso":
                    value = _normalize_curso_value(v) or None

                fields.append(f"{k} = %s")
                values.append(value)
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
    scope = auth_service.get_user_fundacion_scope(user.get("username", ""))

    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id, sede, curso FROM fundacion_tareas WHERE id = %s", (tid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Tarea no encontrada")
        if not _is_task_in_scope(scope, dict(row)):
            raise HTTPException(status_code=403, detail="No tiene permisos para eliminar esta tarea")

        conn.execute("DELETE FROM fundacion_tareas WHERE id = %s", (tid,))
        conn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── Sedes ──────────────────────────────────────────────────────────────

class SedeIn(BaseModel):
    code: str
    nombre: str
    region: Optional[str] = None
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    orden: Optional[int] = 99


class SedeUpdate(BaseModel):
    nombre: Optional[str] = None
    region: Optional[str] = None
    descripcion: Optional[str] = None
    icono: Optional[str] = None
    color: Optional[str] = None
    activo: Optional[bool] = None
    orden: Optional[int] = None


@router.get("/sedes")
async def list_sedes_accesibles(
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Lista de sedes que el usuario puede ver. Doble candado: el filtro
    se hace en SQL via fundacion.sedes_accesibles(usuario_id)."""
    uid = _user_id(user)
    items = sedes_service.sedes_accesibles(uid)
    is_admin = sedes_service.es_super_scope(uid) or _is_admin(user)
    return {"items": items, "es_admin": is_admin}


@router.get("/sedes/all")
async def list_todas_sedes(
    incluir_inactivas: bool = False,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Vista admin: todas las sedes existentes (para configuración)."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="solo admin")
    return {"items": sedes_service.listar_todas_sedes(incluir_inactivas=incluir_inactivas)}


@router.post("/sedes")
@audit_action("CREATE_FUNDACION_SEDE", severity="info")
async def crear_sede(
    body: SedeIn,
    request: Request,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="solo admin")
    try:
        return sedes_service.crear_sede(
            code=body.code, nombre=body.nombre, region=body.region,
            descripcion=body.descripcion, icono=body.icono, color=body.color,
            orden=body.orden or 99,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/sedes/{sede_id}")
@audit_action("UPDATE_FUNDACION_SEDE", severity="info")
async def actualizar_sede(
    sede_id: int,
    body: SedeUpdate,
    request: Request,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="solo admin")
    try:
        return sedes_service.actualizar_sede(
            sede_id,
            nombre=body.nombre, region=body.region, descripcion=body.descripcion,
            icono=body.icono, color=body.color, activo=body.activo, orden=body.orden,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Membresías persona ↔ sede ─────────────────────────────────────────

class MembresiaIn(BaseModel):
    usuario_id: int
    sede_id: int
    rol: str  # 'lider_educativo' | 'gestora_educativa' | 'ejecutiva'
    motivo: Optional[str] = None


@router.get("/membresias")
async def list_membresias(
    sede_id: Optional[int] = None,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Lista membresías. Sin sede_id devuelve todas las vigentes (admin) o
    solo las del usuario (no-admin)."""
    uid = _user_id(user)
    if sede_id is not None:
        # Doble candado: si no es admin, debe tener acceso a la sede para verlas.
        _ensure_sede_access(user, sede_id=sede_id)
        return {"items": memb_service.listar_membresias_sede(sede_id)}
    if _is_admin(user) or sedes_service.es_super_scope(uid):
        return {"items": memb_service.listar_todas_membresias_vigentes()}
    return {"items": memb_service.listar_membresias_usuario(uid)}


@router.get("/membresias/mias")
async def list_mis_membresias(
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    uid = _user_id(user)
    return {"items": memb_service.listar_membresias_usuario(uid)}


@router.post("/membresias")
@audit_action("ASSIGN_FUNDACION_SEDE_MEMBERSHIP", severity="info")
async def crear_membresia(
    body: MembresiaIn,
    request: Request,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="solo admin puede asignar")
    actor_id = _user_id(user)
    try:
        return memb_service.asignar_membresia(
            usuario_id=body.usuario_id, sede_id=body.sede_id, rol=body.rol,
            asignado_por=actor_id, motivo=body.motivo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/membresias/{membresia_id}")
@audit_action("CLOSE_FUNDACION_SEDE_MEMBERSHIP", severity="warning")
async def cerrar_membresia(
    membresia_id: int,
    request: Request,
    motivo: Optional[str] = None,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="solo admin puede cerrar")
    ok = memb_service.cerrar_membresia(membresia_id, motivo=motivo)
    if not ok:
        raise HTTPException(status_code=404, detail="membresía no encontrada o ya cerrada")
    return {"ok": True}
