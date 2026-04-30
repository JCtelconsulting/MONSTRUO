from pydantic import BaseModel
from typing import Optional


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
