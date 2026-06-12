"""Servicios para reportes globales (POST /api/reportes/generar)."""

import calendar
import collections
import glob
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from backend import modelos, nucleo


def compute_report_range(
    tipo: str, fecha_inicio: str, fecha_fin: str | None
) -> tuple[datetime, datetime]:
    """Convierte el (tipo, fecha_inicio, fecha_fin?) del request en un
    rango concreto (fi, ff) de datetimes con borders apropiados:
    - diario: fi a 00:00, ff a 23:59:59 del mismo dia.
    - semanal: lunes 00:00 al domingo 23:59:59 de la semana de fecha_inicio.
    - mensual: dia 1 a ultimo dia del mes de fecha_inicio.
    - personalizado: fi a 00:00, ff (requerido) a 23:59:59.

    Lanza ValueError si las fechas son invalidas o si tipo=personalizado y
    fecha_fin es None.
    """
    if not fecha_inicio:
        raise ValueError("fecha_inicio es requerida")

    fi = datetime.fromisoformat(fecha_inicio)
    ff = fi if not fecha_fin else datetime.fromisoformat(fecha_fin)

    if tipo == "diario":
        ff = fi.replace(hour=23, minute=59, second=59)
    elif tipo == "semanal":
        # Lunes a domingo de la semana de fi.
        lunes = fi - timedelta(days=fi.weekday())
        fi = lunes.replace(hour=0, minute=0, second=0)
        ff = lunes + timedelta(days=6, hours=23, minutes=59, seconds=59)
    elif tipo == "mensual":
        fi = fi.replace(day=1, hour=0, minute=0, second=0)
        ld = calendar.monthrange(fi.year, fi.month)[1]
        ff = fi.replace(day=ld, hour=23, minute=59, second=59)
    elif tipo == "personalizado":
        if not fecha_fin:
            raise ValueError("personalizado requiere fecha_fin")
        ff = ff.replace(hour=23, minute=59, second=59)
    else:
        raise ValueError(f"Tipo de reporte invalido: {tipo}")

    return fi, ff


def create_report_job(db: Session) -> str:
    """Crea un ReportJob en estado 'pending' y devuelve el job_id (uuid)."""
    job_id = str(uuid.uuid4())
    job = modelos.ReportJob(id=job_id, status="pending", progress=0)
    db.add(job)
    db.commit()
    return job_id


def _is_excluded_path(path_str: str) -> bool:
    """True si el path pertenece a un directorio operativo del sistema
    (cuarentena, validar, archivado, devueltas, papelera) y no debe
    listarse como evidencia disponible para informes."""
    try:
        parts = Path(path_str).parts
    except Exception:
        return False
    excluded = {
        nucleo.QUARANTINE_DIR_NAME,
        nucleo.VALIDATION_DIR_NAME,
        nucleo.ARCHIVE_DIR_NAME,
        nucleo.RETURNED_DIR_NAME,
        nucleo.TRASH_DIR_NAME,
    }
    return any(p in excluded for p in parts)


def list_plan_files_for_report(db: Session, plan_id: int) -> dict:
    """Lista los archivos de un plan elegibles para informe, agrupados por
    proyecto y tarea. Filtra por el token _P{plan_id}_ del nombre y excluye
    rutas operativas.

    Lanza LookupError si el plan no existe.
    Retorna {"plan_descripcion": str, "archivos": {proyecto: {tarea: [{nombre, ruta}, ...]}}}.
    """
    plan = (
        db.query(modelos.PlanTrabajo).filter(modelos.PlanTrabajo.id == plan_id).first()
    )
    if not plan:
        raise LookupError("No encontrado")

    asigs = (
        db.query(modelos.AsignacionPlan)
        .options(
            selectinload(modelos.AsignacionPlan.item)
            .selectinload(modelos.Item.categoria)
            .selectinload(modelos.Categoria.proyecto)
        )
        .filter(modelos.AsignacionPlan.plan_id == plan_id)
        .all()
    )

    tree: dict = collections.defaultdict(lambda: collections.defaultdict(list))
    token = f"_P{plan_id}_"
    for a in asigs:
        if not os.path.exists(a.item.ruta_item):
            continue
        pattern = os.path.join(a.item.ruta_item, "**", f"*{token}*")
        for f in glob.glob(pattern, recursive=True):
            if _is_excluded_path(f):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in (".jpg", ".jpeg", ".png"):
                tree[a.item.categoria.proyecto.nombre_pmc][a.item.nombre].append(
                    {"nombre": os.path.basename(f), "ruta": f}
                )
    return {"plan_descripcion": plan.descripcion, "archivos": tree}
