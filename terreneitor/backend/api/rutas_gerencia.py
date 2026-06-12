import math
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import piexif
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend import dependencias, modelos, nucleo
from backend.utils.logger import log

router = APIRouter(
    prefix="/api/gerencia",
    tags=["Gerencia"],
    dependencies=[Depends(dependencias.require_session)],
)


@router.get("/asignaciones/por-estado/{estado}")
def gerencia_asignaciones_por_estado(
    estado: modelos.EstadoItemEnum, db: Session = Depends(dependencias.get_db)
):
    """Lectura de asignaciones por estado para la sección de Evidencia de
    gerencia. El endpoint equivalente de supervisor exige rol SUPERVISOR y le
    daba 403 a GERENCIA (la sección mostraba 'Acceso denegado'). Reusa la misma
    lógica pero bajo el router de gerencia (require_session)."""
    from backend.api import rutas_supervisor

    return rutas_supervisor.get_asignaciones_estado(estado, db)


@router.get("/excepciones/fotos")
def gerencia_excepciones_fotos(db: Session = Depends(dependencias.get_db)):
    """Fotos en cuarentena (EXIF) para la sección de Evidencia de gerencia.
    Alias de lectura del endpoint de supervisor (que daba 403 a GERENCIA)."""
    from backend.api import rutas_supervisor

    return rutas_supervisor.get_exif_pending(db)


@router.get("/asignacion/{id}/archivos-por-validar")
def gerencia_archivos_por_validar(id: int, db: Session = Depends(dependencias.get_db)):
    """Lista de archivos de una asignación para la vista de Evidencia de
    gerencia. Alias de lectura del endpoint de supervisor (403 para GERENCIA)."""
    from backend.api import rutas_supervisor

    return rutas_supervisor.list_validar(id, db)


@router.get("/asignacion/{id}/archivos")
def gerencia_archivos_evidencia(id: int, db: Session = Depends(dependencias.get_db)):
    """Fotos de evidencia de una asignación para gerencia (solo lectura).

    Incluye las VALIDADAS (carpeta PLAN_{plan_id}_*) y las que están por validar
    (_POR_VALIDAR/_DEVUELTAS). Antes la vista 'Proyectos Listos' miraba solo
    _POR_VALIDAR (vacío tras validar) => 'Sin archivos visibles'.
    """
    a = db.query(modelos.AsignacionPlan).filter(modelos.AsignacionPlan.id == id).first()
    if not a or not a.item or not a.item.ruta_item:
        return []
    root = Path(a.item.ruta_item)
    if not root.exists():
        return []
    plan_tag = f"PLAN_{a.plan_id}_"
    incluir_dirs = {nucleo.VALIDATION_DIR_NAME, nucleo.RETURNED_DIR_NAME}
    exts = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}
    res = []
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix.lower() not in exts:
            continue
        rel = f.relative_to(root).parts
        carpeta = rel[0] if len(rel) > 1 else ""
        if not (carpeta.startswith(plan_tag) or carpeta in incluir_dirs):
            continue
        res.append(
            {
                "nombre_archivo": f.name,
                "ruta_archivo": str(f),
                "es_video": f.suffix.lower() in {".mp4", ".mov"},
            }
        )
    res.sort(key=lambda x: x["nombre_archivo"])
    return res


@router.get("/image-thumbnail/")
def gerencia_image_thumbnail(path: str):
    """Miniatura para la evidencia de gerencia (el endpoint de supervisor da
    403 a GERENCIA, dejando las imágenes rotas)."""
    from backend.api import rutas_supervisor

    return rutas_supervisor.thumb(path)


@router.get("/image-full/")
def gerencia_image_full(path: str):
    """Imagen completa para la evidencia de gerencia (alias del de supervisor)."""
    from backend.api import rutas_supervisor

    return rutas_supervisor.full(path)


REPORTS_DIR_NC = nucleo.get_reports_dir()


def _ensure_reports_dir() -> str:
    """Asegura y retorna el directorio de reportes para endpoints de gerencia."""
    global REPORTS_DIR_NC
    REPORTS_DIR_NC = nucleo.ensure_reports_dir()
    return REPORTS_DIR_NC


def _get_informes_del_disco():
    res = []
    try:
        reports_dir = _ensure_reports_dir()
    except Exception as e:
        log.error(f"[DISK_LIST_ERROR] No se pudo acceder a reportes: {e}")
        return res

    try:
        for f in os.listdir(reports_dir):
            if f.endswith(".docx"):
                path = os.path.join(reports_dir, f)
                stat = os.stat(path)

                # Intentar deducir cliente si el nombre sigue el patrón Reporte_CLIENTE_...
                cliente = "Varios"
                if f.startswith("Reporte_"):
                    parts = f.split("_")
                    if len(parts) > 1:
                        cliente = parts[1]

                res.append(
                    {
                        "id": -1,  # ID especial para indicar que es solo disco
                        "tipo": "Reporte Externo",
                        "rango": "N/A",
                        "fecha": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "cliente": cliente,
                        "proyecto": "Disco",
                        "plan": "N/A",
                        "archivo": f,
                        "url": f"/api/gerencia/informes/download-file?filename={f}",
                    }
                )
    except Exception as e:
        log.error(f"[DISK_LIST_ERROR] {e}")
    return sorted(res, key=lambda x: x["fecha"], reverse=True)


_DAY_NAMES = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
_MONTH_NAMES = [
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
]


def _parse_date_param(value: Optional[str]) -> Optional[datetime]:  # noqa: C901
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _normalize_range(
    desde: Optional[str], hasta: Optional[str]
) -> tuple[Optional[datetime], Optional[datetime]]:
    start = _parse_date_param(desde)
    end = _parse_date_param(hasta)
    if end and hasta and "T" not in hasta and len(hasta) <= 10:
        end = end + timedelta(days=1) - timedelta(seconds=1)
    return start, end


def _percentile(values: List[float], pct: float) -> float:  # noqa: C901
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = int(math.ceil((pct / 100.0) * len(values_sorted))) - 1
    idx = max(0, min(idx, len(values_sorted) - 1))
    return float(values_sorted[idx])


def _get_storage_usage() -> Dict[str, float]:  # noqa: C901
    usage = shutil.disk_usage(nucleo.BASE_FILES_DIR)
    total_gb = round(usage.total / (1024**3), 1)
    used_gb = round(usage.used / (1024**3), 1)
    free_gb = round(usage.free / (1024**3), 1)
    used_pct = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
    return {
        "total_gb": total_gb,
        "used_gb": used_gb,
        "free_gb": free_gb,
        "used_pct": used_pct,
    }


def _apply_project_filter(query, proyecto_id: Optional[int]):  # noqa: C901
    if not proyecto_id:
        return query
    return (
        query.join(modelos.AsignacionPlan.item)
        .join(modelos.Item.categoria)
        .join(modelos.Categoria.proyecto)
        .filter(modelos.Proyecto.id == proyecto_id)
    )


def _dir_has_files(path: Path) -> bool:  # noqa: C901
    try:
        return path.exists() and any(p.is_file() for p in path.iterdir())
    except Exception:
        return False


def _is_excluded_path(path_str: str) -> bool:  # noqa: C901
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
    for p in parts:
        if p in excluded:
            return True
    return False


def _rational_to_float(value) -> float:  # noqa: C901
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        num = getattr(value, "numerator", None)
        den = getattr(value, "denominator", None)
        if num is not None and den is not None:
            return float(num) / float(den) if den else 0.0
    except Exception:
        pass
    try:
        num, den = value
        return float(num) / float(den) if den else 0.0
    except Exception:
        return 0.0


def _convert_gps(coords, ref) -> Optional[float]:  # noqa: C901
    if not coords or not ref:
        return None
    try:
        if isinstance(ref, int):
            ref_val = chr(ref)
        else:
            ref_val = (
                ref.decode("utf-8", "ignore")
                if isinstance(ref, (bytes, bytearray))
                else str(ref)
            )
        ref_val = ref_val.strip().strip("\x00").upper()
        deg = _rational_to_float(coords[0])
        minutes = _rational_to_float(coords[1])
        seconds = _rational_to_float(coords[2])
        val = deg + (minutes / 60.0) + (seconds / 3600.0)
        if ref_val in ("S", "W"):
            val = -val
        return val
    except Exception:
        return None


def _extract_gps_and_date(file_path: str):  # noqa: C901
    try:
        exif = piexif.load(file_path)
    except Exception:
        return None, None, None
    gps = exif.get("GPS") or {}
    lat = _convert_gps(gps.get(2), gps.get(1))
    lon = _convert_gps(gps.get(4), gps.get(3))
    if lat is None or lon is None:
        return None, None, None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None, None, None
    if abs(lat) < 0.000001 and abs(lon) < 0.000001:
        return None, None, None
    dt = None
    try:
        exif_block = exif.get("Exif") or {}
        date_raw = exif_block.get(36867) or exif_block.get(36868)
        if not date_raw:
            date_raw = (exif.get("0th") or {}).get(306)
        if date_raw:
            date_txt = (
                date_raw.decode("utf-8")
                if isinstance(date_raw, (bytes, bytearray))
                else str(date_raw)
            )
            dt = datetime.strptime(date_txt, "%Y:%m:%d %H:%M:%S")
    except Exception:
        dt = None
    return lat, lon, dt


def _duration_seconds_expr(db):  # noqa: C901
    # Portable SQLite/Postgres: strftime('%s') solo existe en SQLite.
    if db.get_bind().dialect.name == "postgresql":
        return func.extract(
            "epoch",
            modelos.AsignacionPlan.fecha_validacion
            - modelos.AsignacionPlan.fecha_completado_terreno,
        )
    return func.strftime("%s", modelos.AsignacionPlan.fecha_validacion) - func.strftime(
        "%s", modelos.AsignacionPlan.fecha_completado_terreno
    )


@router.get("/dashboard/kpis")
def get_kpis(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    # 1. Proyectos Activos
    total_proyectos = (
        db.query(modelos.Proyecto)
        .filter(modelos.Proyecto.estado_proyecto == modelos.EstadoProyectoEnum.ACTIVO)
        .count()
    )

    # 2. Planes en Ejecución
    planes_activos = (
        db.query(modelos.PlanTrabajo)
        .filter(modelos.PlanTrabajo.estado_plan == modelos.EstadoPlanEnum.ABIERTO)
        .count()
    )

    # 3. Tasa de Rechazo (Global)
    total_tareas = db.query(modelos.AsignacionPlan).count()
    rechazadas = (
        db.query(modelos.AsignacionPlan)
        .filter(modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.RECHAZADA)
        .count()
    )
    tasa_rechazo = (
        round((rechazadas / total_tareas * 100), 1) if total_tareas > 0 else 0
    )

    # 4. Fotos en Cuarentena (Pendientes EXIF)
    cuarentena = (
        db.query(modelos.AsignacionPlan)
        .filter(modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.PENDIENTE_EXIF)
        .count()
    )

    return {
        "proyectos_activos": total_proyectos,
        "planes_en_curso": planes_activos,
        "tasa_rechazo": f"{tasa_rechazo}%",
        "fotos_cuarentena": cuarentena,
    }


@router.get("/dashboard/storage")
def get_storage():  # noqa: C901
    if not os.path.exists(nucleo.BASE_FILES_DIR):
        raise HTTPException(status_code=404, detail="Base de archivos no encontrada")
    return _get_storage_usage()


@router.get("/dashboard/sla")
def get_sla(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    proyecto_id: Optional[int] = None,
    db: Session = Depends(dependencias.get_db),
):
    start, end = _normalize_range(desde, hasta)
    duration_sec = _duration_seconds_expr(db)
    base = db.query(duration_sec).filter(
        modelos.AsignacionPlan.fecha_completado_terreno.isnot(None),
        modelos.AsignacionPlan.fecha_validacion.isnot(None),
        duration_sec.isnot(None),
        duration_sec >= 0,
    )
    base = _apply_project_filter(base, proyecto_id)
    if start:
        base = base.filter(modelos.AsignacionPlan.fecha_validacion >= start)
    if end:
        base = base.filter(modelos.AsignacionPlan.fecha_validacion <= end)

    count = base.count()
    breach_limit_h = 24.0
    breach_limit_sec = int(breach_limit_h * 3600)
    breach_count = base.filter(duration_sec > breach_limit_sec).count() if count else 0
    breach_pct = round((breach_count / count) * 100, 1) if count else 0.0

    avg_sec = base.with_entities(func.avg(duration_sec)).scalar()
    avg_h = round((float(avg_sec) / 3600.0), 1) if avg_sec is not None else 0.0

    p50_h = 0.0
    p90_h = 0.0
    if count:
        p50_idx = int(math.ceil(0.50 * count)) - 1
        p90_idx = int(math.ceil(0.90 * count)) - 1
        p50_idx = max(0, min(p50_idx, count - 1))
        p90_idx = max(0, min(p90_idx, count - 1))
        p50_sec = base.order_by(duration_sec.asc()).offset(p50_idx).limit(1).scalar()
        p90_sec = base.order_by(duration_sec.asc()).offset(p90_idx).limit(1).scalar()
        if p50_sec is not None:
            p50_h = round((float(p50_sec) / 3600.0), 1)
        if p90_sec is not None:
            p90_h = round((float(p90_sec) / 3600.0), 1)

    return {
        "count": count,
        "avg_h": avg_h,
        "p90_h": p90_h,
        "p50_h": p50_h,
        "breach_limit_h": breach_limit_h,
        "breach_pct": breach_pct,
        "desde": start.isoformat() if start else None,
        "hasta": end.isoformat() if end else None,
    }


@router.get("/dashboard/productividad")
def get_productividad(
    periodo: str = "semanal",
    proyecto_id: Optional[int] = None,
    db: Session = Depends(dependencias.get_db),
):
    periodo = (periodo or "semanal").lower()
    if periodo not in ("diario", "semanal", "mensual"):
        raise HTTPException(status_code=400, detail="Periodo invalido")

    now = datetime.now()
    base_query = db.query(modelos.AsignacionPlan.id).filter(
        modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.VALIDADA,
        modelos.AsignacionPlan.fecha_validacion.isnot(None),
    )
    base_query = _apply_project_filter(base_query, proyecto_id)

    if periodo == "diario":
        start_day = (now - timedelta(days=13)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_day = now
        date_key = func.date(modelos.AsignacionPlan.fecha_validacion)
        rows = (
            base_query.with_entities(date_key, func.count(modelos.AsignacionPlan.id))
            .filter(
                modelos.AsignacionPlan.fecha_validacion >= start_day,
                modelos.AsignacionPlan.fecha_validacion <= end_day,
            )
            .group_by(date_key)
            .all()
        )
        # str(): en SQLite date() devuelve 'YYYY-MM-DD'; en Postgres un objeto
        # date. Normalizar para que calce con las claves d_str de las labels.
        counts = {str(r[0])[:10]: r[1] for r in rows}
        labels = []
        data = []
        for i in range(14):
            d = start_day.date() + timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            labels.append(f"{_DAY_NAMES[d.weekday()]} {d.day:02d}")
            data.append(counts.get(d_str, 0))
        return {"periodo": periodo, "labels": labels, "data": data}

    if periodo == "semanal":
        week_start = now - timedelta(days=now.weekday())
        start_week = (week_start - timedelta(weeks=7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        # Agrupar en Python (portable SQLite/Postgres y claves identicas a las labels)
        fechas = (
            base_query.with_entities(modelos.AsignacionPlan.fecha_validacion)
            .filter(
                modelos.AsignacionPlan.fecha_validacion >= start_week,
                modelos.AsignacionPlan.fecha_validacion <= now,
            )
            .all()
        )
        counts = {}
        for (fv,) in fechas:
            if fv is None:
                continue
            k = fv.strftime("%Y-%W")
            counts[k] = counts.get(k, 0) + 1
        labels = []
        data = []
        for i in range(8):
            current = start_week + timedelta(weeks=i)
            week_num = int(current.strftime("%W"))
            label = f"S{week_num:02d} {_MONTH_NAMES[current.month - 1]}"
            labels.append(label)
            data.append(counts.get(current.strftime("%Y-%W"), 0))
        return {"periodo": periodo, "labels": labels, "data": data}

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_month = month_start
    for _ in range(11):
        if start_month.month == 1:
            start_month = start_month.replace(year=start_month.year - 1, month=12)
        else:
            start_month = start_month.replace(month=start_month.month - 1)
    # Agrupar en Python (portable SQLite/Postgres y claves identicas a las labels)
    fechas = (
        base_query.with_entities(modelos.AsignacionPlan.fecha_validacion)
        .filter(
            modelos.AsignacionPlan.fecha_validacion >= start_month,
            modelos.AsignacionPlan.fecha_validacion <= now,
        )
        .all()
    )
    counts = {}
    for (fv,) in fechas:
        if fv is None:
            continue
        k = fv.strftime("%Y-%m")
        counts[k] = counts.get(k, 0) + 1
    labels = []
    data = []
    current = start_month
    for _ in range(12):
        label = f"{_MONTH_NAMES[current.month - 1]} {current.year}"
        labels.append(label)
        data.append(counts.get(current.strftime("%Y-%m"), 0))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return {"periodo": periodo, "labels": labels, "data": data}


@router.get("/dashboard/riesgos")
def get_riesgos(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    now = datetime.now()
    riesgos: List[Dict[str, Any]] = []

    try:
        storage = _get_storage_usage()
        used_pct = storage.get("used_pct", 0.0)
        if used_pct >= 85:
            riesgos.append(
                {
                    "nivel": "ALTO",
                    "titulo": "Almacenamiento critico",
                    "detalle": f"{used_pct}% usado",
                }
            )
        elif used_pct >= 70:
            riesgos.append(
                {
                    "nivel": "MEDIO",
                    "titulo": "Almacenamiento alto",
                    "detalle": f"{used_pct}% usado",
                }
            )
    except Exception:
        riesgos.append(
            {
                "nivel": "MEDIO",
                "titulo": "Almacenamiento",
                "detalle": "No se pudo leer uso de disco",
            }
        )

    backlog_limit = now - timedelta(hours=48)
    backlog = (
        db.query(modelos.AsignacionPlan)
        .filter(
            modelos.AsignacionPlan.estado.in_(
                [
                    modelos.EstadoItemEnum.COMPLETADA_TERRENO,
                    modelos.EstadoItemEnum.PENDIENTE_EXIF,
                ]
            ),
            modelos.AsignacionPlan.fecha_completado_terreno.isnot(None),
            modelos.AsignacionPlan.fecha_completado_terreno < backlog_limit,
        )
        .count()
    )
    if backlog:
        nivel = "ALTO" if backlog >= 20 else "MEDIO"
        riesgos.append(
            {
                "nivel": nivel,
                "titulo": "Atraso en validacion",
                "detalle": f"{backlog} items >48h",
            }
        )

    cuarentena = (
        db.query(modelos.AsignacionPlan)
        .filter(modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.PENDIENTE_EXIF)
        .count()
    )
    if cuarentena >= 30:
        riesgos.append(
            {
                "nivel": "MEDIO",
                "titulo": "Cuarentena acumulada",
                "detalle": f"{cuarentena} items sin EXIF",
            }
        )

    fecha_corte = now - timedelta(days=30)
    total_rev = (
        db.query(modelos.AsignacionPlan)
        .filter(
            modelos.AsignacionPlan.estado.in_(
                [modelos.EstadoItemEnum.VALIDADA, modelos.EstadoItemEnum.RECHAZADA]
            ),
            modelos.AsignacionPlan.fecha_validacion.isnot(None),
            modelos.AsignacionPlan.fecha_validacion >= fecha_corte,
        )
        .count()
    )
    rechazadas = (
        db.query(modelos.AsignacionPlan)
        .filter(
            modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.RECHAZADA,
            modelos.AsignacionPlan.fecha_validacion.isnot(None),
            modelos.AsignacionPlan.fecha_validacion >= fecha_corte,
        )
        .count()
    )
    if total_rev:
        ratio = (rechazadas / total_rev) * 100
        if ratio >= 10:
            riesgos.append(
                {
                    "nivel": "ALTO",
                    "titulo": "Tasa de rechazo alta",
                    "detalle": f"{ratio:.1f}% en 30 dias",
                }
            )
        elif ratio >= 5:
            riesgos.append(
                {
                    "nivel": "MEDIO",
                    "titulo": "Tasa de rechazo en alza",
                    "detalle": f"{ratio:.1f}% en 30 dias",
                }
            )

    planes_antiguos = (
        db.query(modelos.PlanTrabajo)
        .filter(
            modelos.PlanTrabajo.estado_plan == modelos.EstadoPlanEnum.ABIERTO,
            modelos.PlanTrabajo.fecha_creacion < (now - timedelta(days=30)),
        )
        .count()
    )
    if planes_antiguos:
        nivel = "MEDIO" if planes_antiguos < 10 else "ALTO"
        riesgos.append(
            {
                "nivel": nivel,
                "titulo": "Planes abiertos antiguos",
                "detalle": f"{planes_antiguos} planes >30 dias",
            }
        )

    return riesgos


@router.get("/dashboard/mapa")
def get_mapa(
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    proyecto_id: Optional[int] = None,
    max_puntos: int = 5000,
    db: Session = Depends(dependencias.get_db),
):
    base_path = Path(nucleo.BASE_FILES_DIR)
    if proyecto_id:
        proyecto = (
            db.query(modelos.Proyecto)
            .filter(modelos.Proyecto.id == proyecto_id)
            .first()
        )
        if not proyecto or not proyecto.ruta_base:
            raise HTTPException(status_code=404, detail="Proyecto sin ruta valida")
        base_path = Path(proyecto.ruta_base)

    if not base_path.exists():
        raise HTTPException(status_code=404, detail="Ruta base no encontrada")

    start, end = _normalize_range(desde, hasta)
    excluded = {
        nucleo.QUARANTINE_DIR_NAME,
        nucleo.VALIDATION_DIR_NAME,
        nucleo.ARCHIVE_DIR_NAME,
        nucleo.RETURNED_DIR_NAME,
        nucleo.TRASH_DIR_NAME,
    }

    points: List[List[float]] = []
    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in excluded]
        if _is_excluded_path(root):
            continue
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".jpg", ".jpeg"):
                continue
            file_path = os.path.join(root, name)
            lat, lon, dt = _extract_gps_and_date(file_path)
            if lat is None or lon is None:
                continue
            if (start or end) and dt is None:
                continue
            if start and dt and dt < start:
                continue
            if end and dt and dt > end:
                continue
            points.append([lat, lon, 1.0])
            if len(points) >= max_puntos:
                break
        if len(points) >= max_puntos:
            break

    return {"points": points, "total": len(points), "limite": max_puntos}


@router.get("/dashboard/graficos/estados")
def get_grafico_estados(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    # Agrupar tareas por estado
    stats = (
        db.query(modelos.AsignacionPlan.estado, func.count(modelos.AsignacionPlan.id))
        .group_by(modelos.AsignacionPlan.estado)
        .all()
    )

    # Formatear para Chart.js
    labels = [s[0].value for s in stats]
    data = [s[1] for s in stats]

    # Colores Toxic (Manual mapping)
    colors = []
    for color_label in labels:
        if "VALIDADA" in color_label:
            colors.append("#00ff41")  # Neon Green
        elif "RECHAZADA" in color_label:
            colors.append("#ff3333")  # Red
        elif "PENDIENTE" in color_label:
            colors.append("#ffcc00")  # Yellow
        else:
            colors.append("#00f3ff")  # Cyan

    return {"labels": labels, "data": data, "colors": colors}


@router.get("/dashboard/graficos/avance-semanal")
def get_grafico_avance(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    # Tareas validadas ultimos 7 dias
    hoy = datetime.now()
    inicio = hoy - timedelta(days=6)

    res = (
        db.query(
            func.date(modelos.AsignacionPlan.fecha_validacion),
            func.count(modelos.AsignacionPlan.id),
        )
        .filter(
            modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.VALIDADA,
            modelos.AsignacionPlan.fecha_validacion >= inicio,
        )
        .group_by(func.date(modelos.AsignacionPlan.fecha_validacion))
        .all()
    )

    # Rellenar dias vacios. str(): SQLite devuelve 'YYYY-MM-DD', Postgres date.
    datos_map = {str(r[0])[:10]: r[1] for r in res}
    labels = []
    data = []

    for i in range(7):
        d = inicio + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        labels.append(d.strftime("%a %d"))  # Ej: Lun 24
        data.append(datos_map.get(d_str, 0))

    return {"labels": labels, "data": data}


@router.get("/informes/filtros")
def get_filtros_historial(db: Session = Depends(dependencias.get_db)):
    """
    Obtener filtros para el historial. Versión ultra-robusta.
    """
    fallback = {"clientes": [], "proyectos": [], "planes": []}
    try:
        # 1. Clientes (Directo de la tabla de historial)
        clientes_raw = db.query(modelos.ReporteHistorial.cliente).distinct().all()
        clientes = [c[0] for c in clientes_raw if c and c[0]]

        # 2. Proyectos (Join tradicional)
        proyectos_raw = (
            db.query(modelos.Proyecto)
            .join(
                modelos.ReporteHistorial,
                modelos.Proyecto.id == modelos.ReporteHistorial.proyecto_id,
            )
            .distinct()
            .all()
        )
        proyectos = [{"id": p.id, "nombre": p.nombre_pmc} for p in proyectos_raw]

        # 3. Planes (Join tradicional)
        planes_raw = (
            db.query(modelos.PlanTrabajo)
            .join(
                modelos.ReporteHistorial,
                modelos.PlanTrabajo.id == modelos.ReporteHistorial.plan_id,
            )
            .distinct()
            .all()
        )
        planes = [{"id": p.id, "descripcion": p.descripcion} for p in planes_raw]

        return {"clientes": clientes, "proyectos": proyectos, "planes": planes}
    except Exception as e:
        log.error(f"[HISTORY_FILTERS_ROBUST_FAIL] {e}")
        # En caso de error de DB (ej: tabla/columna faltante), devolvemos listas vacías
        # para que la UI al menos cargue.
        return fallback


@router.get("/informes/historial")
def get_historial_reportes(
    cliente: Optional[str] = None,
    proyecto_id: Optional[int] = None,
    plan_id: Optional[int] = None,
    tipo: Optional[str] = None,
    db: Session = Depends(dependencias.get_db),
):
    """
    Listar historial de informes. Combina DB y Disco con fallback total.
    """
    try:
        # Intento de búsqueda en DB
        query = db.query(modelos.ReporteHistorial)

        if cliente:
            query = query.filter(modelos.ReporteHistorial.cliente == cliente)
        if proyecto_id:
            query = query.filter(modelos.ReporteHistorial.proyecto_id == proyecto_id)
        if plan_id:
            query = query.filter(modelos.ReporteHistorial.plan_id == plan_id)
        if tipo:
            query = query.filter(modelos.ReporteHistorial.tipo_reporte == tipo)

        # Usamos try-except interno para la ejecución de la query por si fallan los JOINS o columnas
        try:
            reportes_db = query.order_by(
                modelos.ReporteHistorial.fecha_generacion.desc()
            ).all()

            db_results = []
            for r in reportes_db:
                # Acceso seguro a relaciones para evitar DetachedInstance o fallos de Join
                nombre_proy = "Varios"
                try:
                    if r.proyecto:
                        nombre_proy = r.proyecto.nombre_pmc
                except Exception:
                    pass

                desc_plan = "N/A"
                try:
                    if r.plan:
                        desc_plan = r.plan.descripcion
                except Exception:
                    pass

                fecha_str = datetime.now().isoformat()
                if r.fecha_generacion:
                    if isinstance(r.fecha_generacion, datetime):
                        fecha_str = r.fecha_generacion.isoformat()
                    else:
                        fecha_str = str(r.fecha_generacion)

                db_results.append(
                    {
                        "id": r.id,
                        "tipo": r.tipo_reporte or "Reporte",
                        "rango": r.rango_fechas or "N/A",
                        "fecha": fecha_str,
                        "cliente": r.cliente or "---",
                        "proyecto": nombre_proy,
                        "plan": desc_plan,
                        "archivo": r.nombre_archivo,
                        "url": f"/api/informes/download-direct/{r.id}",
                    }
                )
        except Exception as e_sql:
            log.warning(f"[HISTORY_SQL_FAIL] {e_sql}")
            db_results = []

        # SIEMPRE complementar con disco si no hay filtros o si la DB falló
        nombres_en_db = {r["archivo"] for r in db_results}
        disco = _get_informes_del_disco()
        solo_disco = [d for d in disco if d["archivo"] not in nombres_en_db]

        # Filtrar el disco manualmente si el usuario pidió filtros (fallback parcial)
        if cliente or proyecto_id or plan_id:
            # Si hay filtros pero la DB falló, intentamos filtrar el disco por nombre si es posible
            # pero por ahora devolvemos lo que hay para no dar Error 500
            pass

        final_results = sorted(
            db_results + solo_disco, key=lambda x: x["fecha"], reverse=True
        )
        return final_results

    except Exception as e_global:
        log.error(f"[HISTORY_GLOBAL_FAIL] {e_global}")
        # FALLBACK ABSOLUTO: Si todo falla, devolver al menos lo del disco
        try:
            return _get_informes_del_disco()
        except Exception:
            return []


@router.get("/informes/download-file")
def download_file_from_disk(filename: str):
    import os

    from fastapi.responses import FileResponse

    # Validación básica para evitar path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Nombre de archivo inválido")

    try:
        reports_dir = _ensure_reports_dir()
    except Exception as e:
        log.error(f"[DOWNLOAD_FILE_ERROR] No se pudo acceder a reportes: {e}")
        raise HTTPException(500, "Error interno accediendo al directorio de reportes")

    path = os.path.join(reports_dir, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(path, filename=filename)
