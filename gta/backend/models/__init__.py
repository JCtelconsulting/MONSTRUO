from pydantic import BaseModel
from typing import Any, Dict, List, Optional


# ── Procesos (catálogo) ────────────────────────────────────────────────────
class ProcesoCreate(BaseModel):
    nombre: str
    area: str
    descripcion: Optional[str] = None
    sla_horas: Optional[int] = None
    icono: Optional[str] = None
    pasos_definicion: Optional[str] = '[]'     # JSON: ["paso 1", "paso 2"]
    campos_formulario: Optional[str] = '[]'    # JSON: [{"key":"x","label":"X","type":"text"}]
    estado: Optional[str] = 'activo'


class ProcesoUpdate(BaseModel):
    nombre: Optional[str] = None
    area: Optional[str] = None
    subarea_code: Optional[str] = None
    descripcion: Optional[str] = None
    sla_horas: Optional[int] = None
    icono: Optional[str] = None
    pasos_definicion: Optional[str] = None
    campos_formulario: Optional[str] = None
    estado: Optional[str] = None


# ── Solicitudes ────────────────────────────────────────────────────────────
class SolicitudCreate(BaseModel):
    proceso_id: int
    titulo: str
    descripcion: Optional[str] = None
    area: str
    prioridad: Optional[str] = 'media'         # baja, media, alta
    campos_extra: Optional[str] = '{}'          # JSON con campos adicionales del proceso


class SolicitudUpdate(BaseModel):
    estado: Optional[str] = None               # pendiente, en_progreso, completado, bloqueado, cancelado
    prioridad: Optional[str] = None
    asignado_a: Optional[str] = None
    pasos_estado: Optional[str] = None         # JSON con estado de cada paso


# ── Quiebres ───────────────────────────────────────────────────────────────
class QuiebreCreate(BaseModel):
    descripcion: str
    area: str
    tipo: Optional[str] = 'sin_proceso'        # sin_proceso, paso_bloqueado, sla_vencido
    solicitud_id: Optional[int] = None


class QuiebreResolverBody(BaseModel):
    nota: Optional[str] = None


# ── Flujos cross-área ──────────────────────────────────────────────────────
class FlujoCrear(BaseModel):
    titulo: str
    descripcion: Optional[str] = ""
    proceso_id: Optional[int] = None
    datos_formulario: Optional[Dict[str, Any]] = None
    pasos_libres: Optional[List[Dict[str, Any]]] = None  # solo si proceso_id es None


class TareaCompletarBody(BaseModel):
    campos_completados: Optional[Dict[str, Any]] = None


class TareaValidarBody(BaseModel):
    aceptada: bool = True
    comentario: Optional[str] = ""


class AyudaCrear(BaseModel):
    pedido_a_area: str
    pedido_a_user: Optional[str] = ""
    mensaje: str
    bloquea_sla: bool = False


class AyudaResponder(BaseModel):
    respuesta: str


# ── Tareas (modelo área-céntrico) ──────────────────────────────────────
class TareaCreate(BaseModel):
    subarea_id: int
    titulo: str
    descripcion: Optional[str] = None
    proceso_id: Optional[int] = None
    flujo_tarea_id: Optional[int] = None
    tipo: Optional[str] = None
    prioridad: Optional[str] = "media"           # baja | media | alta | urgente
    sla_horas: Optional[int] = None
    tags: Optional[List[str]] = None


class TareaCerrarBody(BaseModel):
    reporte: Optional[str] = None
    datos_formulario: Optional[Dict[str, Any]] = None  # solo para tareas-paso-1 de flujo


class TareaDevolverBody(BaseModel):
    motivo: str         # qué no cumple, qué debe corregir el paso destino
    paso_destino: int   # paso_orden anterior al actual (cualquier paso del flujo, no solo validación)


class QuiebreReporteBody(BaseModel):
    """Reportar un quiebre desde una tarea hacia otra área del flujo."""
    area_destino: str
    descripcion: str
    tipo: Optional[str] = None


class TareaReasignarBody(BaseModel):
    nuevo_usuario_id: int
    motivo: Optional[str] = None


class TareaLiberarBody(BaseModel):
    motivo: Optional[str] = None


class ColaboradorAgregar(BaseModel):
    usuario_id: int
    rol: str                                      # co_responsable | ayuda
    motivo: Optional[str] = None


class ColaboradorQuitar(BaseModel):
    usuario_id: int
    rol: str


# ── Membresías área ↔ persona ──────────────────────────────────────────
class MembresiaAsignar(BaseModel):
    usuario_id: int
    subarea_id: int
    rol: str = "miembro"                          # miembro | lider
    es_principal: bool = False
    motivo: Optional[str] = None


class MembresiaCerrar(BaseModel):
    motivo: Optional[str] = None
