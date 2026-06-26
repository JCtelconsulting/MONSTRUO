# ========================= modelos.py (PROD MASTER v36.0) =========================
import enum
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# --- ENUMS ---
class UserRoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"
    TERRENO = "TERRENO"
    GERENCIA = "GERENCIA"


class EstadoItemEnum(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    ASIGNADA = "ASIGNADA"
    EN_PROGRESO = "EN_PROGRESO"
    COMPLETADA_TERRENO = "COMPLETADA_TERRENO"
    PENDIENTE_EXIF = "PENDIENTE_EXIF"
    VALIDADA = "VALIDADA"
    RECHAZADA = "RECHAZADA"
    ARCHIVADO = "ARCHIVADO"


class EstadoProyectoEnum(str, enum.Enum):
    ACTIVO = "ACTIVO"
    PAUSADO = "PAUSADO"
    CERRADO = "CERRADO"


class EstadoPlanEnum(str, enum.Enum):
    ABIERTO = "ABIERTO"
    CERRADO = "CERRADO"


# --- TABLAS ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    hashed_password = Column(String)
    role = Column(SqlEnum(UserRoleEnum))
    created_at = Column(DateTime, default=datetime.now)


class Proyecto(Base):
    __tablename__ = "proyectos"
    id = Column(Integer, primary_key=True, index=True)
    nombre_pmc = Column(String, unique=True, index=True)
    cliente = Column(String, index=True)
    area = Column(String)
    ruta_base = Column(String)
    estado_proyecto = Column(
        SqlEnum(EstadoProyectoEnum), default=EstadoProyectoEnum.ACTIVO
    )
    descripcion_interna = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    categorias = relationship(
        "Categoria", back_populates="proyecto", cascade="all,delete-orphan"
    )


class Categoria(Base):
    __tablename__ = "categorias"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    proyecto_id = Column(Integer, ForeignKey("proyectos.id"))
    proyecto = relationship("Proyecto", back_populates="categorias")
    items = relationship(
        "Item", back_populates="categoria", cascade="all,delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String)
    ruta_item = Column(String)
    categoria_id = Column(Integer, ForeignKey("categorias.id"))
    categoria = relationship("Categoria", back_populates="items")
    asignaciones = relationship(
        "AsignacionPlan", back_populates="item", cascade="all,delete-orphan"
    )


class Cliente(Base):
    """Catálogo de clientes (vocabulario controlado) para que los nombres
    queden siempre bien escritos al crear planes."""

    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, nullable=False)


class PlantillaTarea(Base):
    """Plantilla editable de tareas por tipo de trabajo (PMC, OBRA, INTERPOSTE...).
    Cada fila es una entrada con formato 'GRUPO/CATEGORIA/ITEM'. Si un tipo NO tiene
    filas aquí, el sistema cae a STRUCTURE_TEMPLATES (código) como red de seguridad,
    así editar plantillas desde el panel nunca rompe la creación de proyectos."""

    __tablename__ = "plantillas_tareas"
    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(String, nullable=False, index=True)
    ruta = Column(String, nullable=False)  # "GRUPO/CATEGORIA/ITEM"
    orden = Column(Integer, default=0)


class PlanTrabajo(Base):
    __tablename__ = "planes_trabajo"
    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String)
    # Datos estructurados (además del nombre compuesto en `descripcion`):
    cliente = Column(String, nullable=True)
    numero = Column(Integer, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.now)
    estado_plan = Column(SqlEnum(EstadoPlanEnum), default=EstadoPlanEnum.ABIERTO)
    asignaciones = relationship(
        "AsignacionPlan", back_populates="plan", cascade="all,delete-orphan"
    )


class AsignacionUsuario(Base):
    __tablename__ = "asignacion_usuarios"
    asignacion_id = Column(
        Integer, ForeignKey("asignaciones_plan.id"), primary_key=True
    )
    usuario_id = Column(Integer, ForeignKey("users.id"), primary_key=True)


class AsignacionPlan(Base):
    __tablename__ = "asignaciones_plan"
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("planes_trabajo.id"))
    item_id = Column(Integer, ForeignKey("items.id"))
    # Mantenemos usuario_id por compatibilidad legacy/simple,
    # pero las cuadrillas usarán asignacion_usuarios.
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    estado = Column(SqlEnum(EstadoItemEnum), default=EstadoItemEnum.ASIGNADA)
    fecha_asignacion = Column(DateTime, default=datetime.now)
    fecha_completado_terreno = Column(DateTime, nullable=True)
    fecha_validacion = Column(DateTime, nullable=True)
    comentario_terreno = Column(String, nullable=True)
    comentario_rechazo_supervisor = Column(String, nullable=True)
    es_complementaria = Column(Boolean, default=False)

    plan = relationship("PlanTrabajo", back_populates="asignaciones")
    item = relationship("Item", back_populates="asignaciones")
    usuario = relationship("User")
    # Nueva relación para cuadrilla
    colaboradores = relationship(
        "User", secondary="asignacion_usuarios", backref="asignaciones_compartidas"
    )


class ReporteHistorial(Base):
    __tablename__ = "reportes_historial"
    id = Column(Integer, primary_key=True, index=True)
    tipo_reporte = Column(String)  # diario, semanal, mensual, plan, etc.
    rango_fechas = Column(String, nullable=True)
    cliente = Column(String, nullable=True)
    proyecto_id = Column(Integer, ForeignKey("proyectos.id"), nullable=True)
    plan_id = Column(Integer, ForeignKey("planes_trabajo.id"), nullable=True)
    fecha_generacion = Column(DateTime, default=datetime.now)
    nombre_archivo = Column(String)
    ruta_fisica = Column(String)

    proyecto = relationship("Proyecto")
    plan = relationship("PlanTrabajo")


class ReportJob(Base):
    __tablename__ = "report_jobs"
    id = Column(String, primary_key=True, index=True)
    status = Column(String, default="pending")  # pending, processing, completed, failed
    progress = Column(Integer, default=0)
    download_url = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# --- SCHEMAS ---
class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: UserRoleEnum


class UserSchema(BaseModel):
    id: int
    email: str
    name: str
    role: UserRoleEnum
    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[UserRoleEnum] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


class AdminPasswordResetRequest(BaseModel):
    new_password: str


class ProyectoCreate(BaseModel):
    nombre_pmc: str
    cliente: Optional[str] = None
    area: Optional[str] = None
    ruta_base: Optional[str] = None


class ProyectoNombreSchema(BaseModel):
    id: int
    nombre_pmc: str
    estado_proyecto: str
    cliente: Optional[str] = None
    area: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class CategoriaCreate(BaseModel):
    nombre: str
    proyecto_id: int


class ItemCreate(BaseModel):
    nombre: str
    ruta_item: str
    categoria_id: int


class ItemCreateSupervisor(BaseModel):
    nombre: str
    categoria_id: int


class ProyectoInfoSchema(BaseModel):
    nombre_pmc: str
    cliente: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class CategoriaInfoSchema(BaseModel):
    nombre: str
    proyecto: ProyectoInfoSchema
    model_config = ConfigDict(from_attributes=True)


class ItemInfoSchema(BaseModel):
    id: int
    nombre: str
    ruta_item: str
    categoria: CategoriaInfoSchema
    model_config = ConfigDict(from_attributes=True)


class PlanTrabajoSchema(BaseModel):
    id: int
    descripcion: str
    estado_plan: str
    model_config = ConfigDict(from_attributes=True)


class AsignacionTerrenoSchema(BaseModel):
    id: int
    estado: EstadoItemEnum
    es_complementaria: bool
    plan: PlanTrabajoSchema
    item: ItemInfoSchema
    usuario: Optional[UserSchema] = None
    comentario_rechazo_supervisor: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class CompletarItemRequest(BaseModel):
    comentario: Optional[str] = None


class RechazoRequest(BaseModel):
    comentario: str


class ArchivoRequest(BaseModel):
    ruta_archivo: str


class ExifManualRequest(BaseModel):
    ruta_foto_mala: str
    fecha_hora_manual: str


class FotoRechazoRequest(BaseModel):
    ruta_foto_mala: str


class ItemPlantillaSchema(BaseModel):
    id: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class CategoriaConItemsSchema(BaseModel):
    id: int
    nombre: str
    proyecto: ProyectoInfoSchema
    items: List[ItemPlantillaSchema] = []
    model_config = ConfigDict(from_attributes=True)


class ProyectoDetallePlanificacionSchema(BaseModel):
    id: int
    nombre_pmc: str
    cliente: Optional[str] = None
    area: Optional[str] = None
    estado_proyecto: EstadoProyectoEnum
    grupos: Dict[str, List[CategoriaConItemsSchema]] = {
        "EDP": [],
        "INFORME": [],
        "OTROS": [],
    }
    grupos_orden: List[str] = []
    model_config = ConfigDict(from_attributes=True)


class CrearTareaExtraRequest(BaseModel):
    plan_id: int
    nombre_tarea: str
    proyecto_id: int


class BridgeMessageSchema(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    from_agent: str
    to_agent: str
    status: str
    payload: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class CreateBridgeMessageRequest(BaseModel):
    kind: str
    title: str
    body: str
    from_agent: str
    to_agent: str
    payload: Optional[str] = None
