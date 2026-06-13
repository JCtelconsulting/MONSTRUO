# ========================= rutas_supervisor.py (MASTER v50.1 - ULTRON PATCH: Rechazo Metadata Fix) =========================
import glob
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session, selectinload

from terreneitor.backend import dependencias, modelos, nucleo
from terreneitor.backend.services import (
    asignacion_service,
    foto_service,
    item_service,
    plan_service,
    proyecto_service,
)

router = APIRouter(
    prefix="/api",
    tags=["Supervisor"],
    dependencies=[Depends(dependencias.require_supervisor)],
)

# Reusamos el helper del service para no duplicar.
_dir_has_files = asignacion_service.dir_has_files


def _safe_media_path(raw: str) -> str:
    """Anti path traversal: exige que la ruta quede dentro de BASE_FILES_DIR.

    Los endpoints de visualizacion/borrado reciben la ruta como parametro; sin
    esto cualquier supervisor podria leer/borrar archivos arbitrarios del server
    (la BD, el .env con la SECRET_KEY, etc.).
    """
    if not raw or not str(raw).strip():
        raise HTTPException(status_code=400, detail="Ruta requerida")
    base = Path(nucleo.BASE_FILES_DIR).resolve()
    p = Path(str(raw).strip()).resolve()
    try:
        p.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return str(p)


# --- PROYECTOS ---
@router.get("/proyectos/", response_model=List[modelos.ProyectoNombreSchema])
def get_proyectos(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    query = db.query(modelos.Proyecto).filter(
        ~modelos.Proyecto.nombre_pmc.ilike("%dupe%"),
        ~modelos.Proyecto.nombre_pmc.ilike("%1.4.%"),
        modelos.Proyecto.estado_proyecto == modelos.EstadoProyectoEnum.ACTIVO,
    )
    proyectos = query.order_by(modelos.Proyecto.nombre_pmc).all()
    print(f"[DEBUG-SUPER] Proyectos activos en DB: {len(proyectos)}")
    res = [
        p
        for p in proyectos
        if p.ruta_base
        and os.path.exists(p.ruta_base)
        and "_PAPELERA" not in p.ruta_base
    ]
    print(f"[DEBUG-SUPER] Proyectos visibles tras filtro OS: {len(res)}")
    return res


@router.post("/proyectos/{id}/toggle-pause")
def toggle_pause_proyecto(
    id: int, db: Session = Depends(dependencias.get_db)
):  # noqa: C901
    p = db.query(modelos.Proyecto).filter(modelos.Proyecto.id == id).first()
    if not p:
        raise HTTPException(404)
    p.estado_proyecto = (
        modelos.EstadoProyectoEnum.PAUSADO
        if p.estado_proyecto == modelos.EstadoProyectoEnum.ACTIVO
        else modelos.EstadoProyectoEnum.ACTIVO
    )
    db.commit()
    return {"status": "ok", "estado": p.estado_proyecto}


@router.delete("/proyectos/{id}/delete")
def delete_proyecto(id: int, db: Session = Depends(dependencias.get_db)):
    p = db.query(modelos.Proyecto).filter(modelos.Proyecto.id == id).first()
    if not p:
        raise HTTPException(404)
    try:
        proyecto_service.delete_project_filesystem(p.ruta_base or "")
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(500, detail=f"No se pudo borrar carpeta: {e}") from e
    db.delete(p)
    db.commit()
    return {"status": "ok"}


@router.get(
    "/proyectos/{proyecto_id}/detalle-planificacion/",
    response_model=modelos.ProyectoDetallePlanificacionSchema,
)
def get_proyecto_detalle_planificacion(
    proyecto_id: int, db: Session = Depends(dependencias.get_db)
):
    try:
        return proyecto_service.get_planning_detail(db, proyecto_id)
    except LookupError as e:
        raise HTTPException(404, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e)) from e


@router.get("/especialistas/", response_model=List[modelos.UserSchema])
def get_especialistas(db: Session = Depends(dependencias.get_db)):
    return (
        db.query(modelos.User)
        .filter(modelos.User.role == modelos.UserRoleEnum.TERRENO)
        .order_by(modelos.User.name)
        .all()
    )


@router.post("/items/crear")
def crear_item_supervisor(
    req: modelos.ItemCreateSupervisor, db: Session = Depends(dependencias.get_db)
):
    try:
        status, item = item_service.create_item_in_category(
            db, req.categoria_id, req.nombre
        )
    except LookupError as e:
        raise HTTPException(404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(500, detail=f"Error creando carpeta: {e}") from e
    return {
        "status": status,
        "item_id": item.id,
        "nombre": item.nombre,
        "categoria_id": item.categoria_id,
    }


# --- PLANES ---
@router.post("/planes-trabajo/")
def create_plan(
    descripcion: str = Body(..., embed=True),
    item_ids: List[int] = Body(..., embed=True),
    usuario_ids: List[int] = Body(None, embed=True),
    cliente: str = Body(None, embed=True),
    numero: int = Body(None, embed=True),
    db: Session = Depends(dependencias.get_db),
):
    plan = modelos.PlanTrabajo(descripcion=descripcion, cliente=cliente, numero=numero)
    db.add(plan)
    db.commit()
    db.refresh(plan)

    # Cuadrilla: Una sola tarea compartida por varios usuarios
    effective_users = usuario_ids if usuario_ids and len(usuario_ids) > 0 else []

    for i_id in item_ids:
        # Creamos la asignación (una sola vez por item)
        # usuario_id queda como el 'primero' o null para compatibilidad,
        # pero la verdad está en la tabla intermedia.
        principal_id = effective_users[0] if effective_users else None
        asig = modelos.AsignacionPlan(
            plan_id=plan.id, item_id=i_id, usuario_id=principal_id
        )
        db.add(asig)
        db.flush()  # Para obtener asig.id

        # Vinculamos a todos los miembros de la cuadrilla
        for u_id in effective_users:
            db.add(modelos.AsignacionUsuario(asignacion_id=asig.id, usuario_id=u_id))

    db.commit()
    return {"status": "ok", "plan_id": plan.id}


@router.get("/planes-trabajo/activos-detalle/")
def get_planes_activos(db: Session = Depends(dependencias.get_db)):
    return plan_service.list_active_plans(db)


@router.post("/planes-trabajo/{plan_id}/add-items")
def add_items_plan(
    plan_id: int,
    item_ids: List[int] = Body(..., embed=True),
    db: Session = Depends(dependencias.get_db),
):
    existentes = {
        x[0]
        for x in db.query(modelos.AsignacionPlan.item_id)
        .filter(modelos.AsignacionPlan.plan_id == plan_id)
        .all()
    }
    c = 0
    for i in item_ids:
        if i not in existentes:
            db.add(modelos.AsignacionPlan(plan_id=plan_id, item_id=i))
            c += 1
    db.commit()
    return {"status": "ok", "added": c}


@router.delete("/planes-trabajo/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(dependencias.get_db)):
    plan_service.delete_plan_cascade(db, plan_id)
    return {"status": "ok"}


@router.post("/planes-trabajo/{plan_id}/archivar-mover")
def archivar_plan(
    plan_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(dependencias.get_db),
):
    try:
        result = plan_service.archive_plan(db, plan_id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e)) from e

    if result["trash_deleted"] > 0:
        background_tasks.add_task(nucleo.run_storage_index_refresh)
    return result


# --- ASIGNACIONES & VALIDACION ---
@router.get("/asignaciones/por-estado/{estado}")
def get_asignaciones_estado(
    estado: modelos.EstadoItemEnum, db: Session = Depends(dependencias.get_db)
):
    asigs = (
        db.query(modelos.AsignacionPlan)
        .options(
            selectinload(modelos.AsignacionPlan.item)
            .selectinload(modelos.Item.categoria)
            .selectinload(modelos.Categoria.proyecto),
            selectinload(modelos.AsignacionPlan.plan),
        )
        .filter(modelos.AsignacionPlan.estado == estado)
        .all()
    )
    updated = False
    res = []
    for a in asigs:
        if estado == modelos.EstadoItemEnum.COMPLETADA_TERRENO:
            root = Path(a.item.ruta_item)
            pending = asignacion_service.dir_has_files(
                root / nucleo.VALIDATION_DIR_NAME
            ) or asignacion_service.dir_has_files(root / nucleo.RETURNED_DIR_NAME)
            if not pending:
                a.estado = modelos.EstadoItemEnum.VALIDADA
                a.fecha_validacion = datetime.now()
                updated = True
                continue
        res.append(
            {
                "id": a.id,
                "nombre": a.item.nombre.upper(),
                "estado": a.estado.value,
                "categoria": {
                    "proyecto": {"nombre_pmc": a.item.categoria.proyecto.nombre_pmc}
                },
                "plan": {"id": a.plan.id, "descripcion": a.plan.descripcion},
            }
        )
    if updated:
        db.commit()
    return res


@router.post("/asignaciones/{id}/validar/")
def validar_tarea(
    id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(dependencias.get_db),
):
    try:
        result = asignacion_service.validate(db, id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e)) from e

    # Si no era el caso "no files to validate", refrescar el indice de storage.
    if result.get("message") != "No files to validate":
        background_tasks.add_task(nucleo.run_storage_index_refresh)
    return result


@router.post("/asignaciones/{id}/rechazar/")
def rechazar_tarea(
    id: int, req: modelos.RechazoRequest, db: Session = Depends(dependencias.get_db)
):
    a = db.query(modelos.AsignacionPlan).filter(modelos.AsignacionPlan.id == id).first()
    a.estado = modelos.EstadoItemEnum.RECHAZADA
    a.comentario_rechazo_supervisor = req.comentario
    db.commit()
    return {"status": "ok"}


@router.delete("/asignaciones/{id}")
def delete_tarea(id: int, db: Session = Depends(dependencias.get_db)):  # noqa: C901
    db.query(modelos.AsignacionUsuario).filter(
        modelos.AsignacionUsuario.asignacion_id == id
    ).delete()
    db.query(modelos.AsignacionPlan).filter(modelos.AsignacionPlan.id == id).delete()
    db.commit()
    return {"status": "ok"}


@router.post("/asignaciones/{id}/reiniciar-validada")
def reiniciar_tarea_validada(id: int, db: Session = Depends(dependencias.get_db)):
    try:
        return asignacion_service.restart_validated(db, id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e)) from e


@router.post("/asignaciones/{id}/reasignar-validada")
def reasignar_tarea_validada(
    id: int, db: Session = Depends(dependencias.get_db)
):  # noqa: C901
    a = (
        db.query(modelos.AsignacionPlan)
        .options(
            selectinload(modelos.AsignacionPlan.item),
            selectinload(modelos.AsignacionPlan.plan),
        )
        .filter(modelos.AsignacionPlan.id == id)
        .first()
    )
    if not a:
        raise HTTPException(404, "Asignacion no encontrada")
    if a.estado != modelos.EstadoItemEnum.VALIDADA:
        raise HTTPException(400, "Asignacion no validada")

    a.estado = modelos.EstadoItemEnum.ASIGNADA
    a.fecha_validacion = None
    a.fecha_completado_terreno = None
    a.fecha_asignacion = datetime.now()
    a.comentario_rechazo_supervisor = None

    if a.plan and a.plan.estado_plan == modelos.EstadoPlanEnum.CERRADO:
        a.plan.estado_plan = modelos.EstadoPlanEnum.ABIERTO

    db.commit()
    return {"status": "ok"}


@router.get(
    "/asignacion/{id}/archivos-por-validar",
)
def list_validar(id: int, db: Session = Depends(dependencias.get_db)):  # noqa: C901
    try:
        a = (
            db.query(modelos.AsignacionPlan)
            .filter(modelos.AsignacionPlan.id == id)
            .first()
        )
        if not a:
            return []
        root = Path(a.item.ruta_item)
        dirs = [root / nucleo.VALIDATION_DIR_NAME, root / nucleo.RETURNED_DIR_NAME]
        for d in dirs:
            try:
                foto_service.normalize_duplicate_names(d)
            except Exception:
                pass
        files = []
        for d in dirs:
            if d.exists():
                for f in d.iterdir():
                    if f.is_file():
                        files.append(f)
        res = []
        for f in files:
            res.append(
                {
                    "nombre_archivo": f.name,
                    "ruta_archivo": str(f),
                    "es_video": f.suffix.lower() in [".mp4", ".mov"],
                }
            )
        return res
    except Exception as e:
        import traceback

        with open("/srv/terreneitor/logs/error_super_debug.log", "a") as f_err:
            f_err.write(f"\n[ERROR] list_validar ID={id}: {str(e)}\n")
            f_err.write(traceback.format_exc())
        raise HTTPException(500, detail=f"Internal Server Error: {str(e)}")


@router.get("/image-thumbnail/")
def thumb(path: str):  # noqa: C901
    safe = _safe_media_path(path)
    if not os.path.exists(safe):
        raise HTTPException(404)
    buf = foto_service.generate_thumbnail(safe)
    if buf:
        return Response(content=buf.read(), media_type="image/jpeg")
    else:
        return FileResponse(safe)


@router.get("/image-full/")
def full(path: str):  # noqa: C901
    safe = _safe_media_path(path)
    if not os.path.exists(safe):
        raise HTTPException(404)
    # Formatos que el navegador no renderiza (HEIC de iPhone, TIFF, BMP):
    # convertir a JPEG al vuelo para que se vean.
    ext = os.path.splitext(safe)[1].lower()
    if ext in foto_service.NAVEGADOR_NO_SOPORTA:
        buf = foto_service.to_browser_jpeg(safe)
        if buf:
            return Response(content=buf.read(), media_type="image/jpeg")
    return FileResponse(safe)


@router.get("/video-stream/")
def vid(path: str):  # noqa: C901
    safe = _safe_media_path(path)
    if os.path.exists(safe):
        return FileResponse(
            safe, media_type="video/mp4", headers={"Accept-Ranges": "bytes"}
        )
    else:
        raise HTTPException(404)


@router.post("/archivos/aprobar-archivo")
def aprobar_file(
    ruta_archivo: str = Body(...),
    asignacion_id: int = Body(...),
    db: Session = Depends(dependencias.get_db),
):
    try:
        return asignacion_service.approve_file(db, ruta_archivo, asignacion_id)
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e)) from e
    except ValueError as e:
        msg = str(e)
        status = 400 if "Invalid path" in msg else 404
        raise HTTPException(status, detail=msg) from e
    except OSError as e:
        raise HTTPException(500, detail=f"Error moving file: {e}") from e


@router.post("/archivos/rechazar-archivo")
def rechazar_file(
    ruta_archivo: str = Body(...),
    asignacion_id: int = Body(...),
    db: Session = Depends(dependencias.get_db),
):
    try:
        return asignacion_service.reject_file(db, ruta_archivo, asignacion_id)
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e)) from e
    except ValueError as e:
        msg = str(e)
        status = 400 if "Invalid path" in msg else 404
        raise HTTPException(status, detail=msg) from e
    except OSError as e:
        raise HTTPException(500, detail=f"Error moving file: {e}") from e


# --- CUARENTENA INTELIGENTE ---
@router.get("/excepciones/fotos")
def get_exif_pending(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    patron = os.path.join(nucleo.BASE_FILES_DIR, "**", nucleo.QUARANTINE_DIR_NAME, "*")
    rutas = glob.glob(patron, recursive=True)
    res = []
    for r in rutas:
        try:
            p = Path(r)
            if not p.is_file():
                continue
            item_path = str(p.parent.parent)
            item = (
                db.query(modelos.Item)
                .filter(modelos.Item.ruta_item == item_path)
                .first()
            )
            plan_name = "Sin Plan"
            match = re.search(r"_P(\d+)_", p.name)
            if match:
                pid = int(match.group(1))
                plan = (
                    db.query(modelos.PlanTrabajo)
                    .filter(modelos.PlanTrabajo.id == pid)
                    .first()
                )
                if plan:
                    plan_name = plan.descripcion

            if item:
                item_nombre = item.nombre
                proyecto_nombre = item.categoria.proyecto.nombre_pmc
            else:
                item_nombre = p.parent.parent.name
                proyecto_nombre = p.parent.parent.parent.name

            res.append(
                {
                    "item_nombre": item_nombre,
                    "proyecto_nombre": proyecto_nombre,
                    "ruta_foto_mala": r,
                    "plan_descripcion": plan_name,
                }
            )
        except Exception:
            pass
    return res


@router.post("/excepciones/rechazar-permanente")
def rechazar_exif_permanente(
    req: modelos.FotoRechazoRequest, db: Session = Depends(dependencias.get_db)
):
    safe = _safe_media_path(req.ruta_foto_mala)
    if os.path.exists(safe):
        os.remove(safe)
    item_path = str(Path(safe).parent.parent)
    print(f"DEBUG: Rechazo permanente. Ruta: {safe}. ParentItem: {item_path}")
    item = db.query(modelos.Item).filter(modelos.Item.ruta_item == item_path).first()
    if item:
        print(f"DEBUG: Item encontrado id={item.id}. Revisando estado...")
        asignacion_service.revisar_estado_post_rechazo(db, item.id)
    else:
        print(f"DEBUG: Item NO encontrado para ruta: {item_path}")
    return {"status": "ok"}


@router.post("/excepciones/aplicar-exif-manual")
def aplicar_exif_manual(
    req: modelos.ExifManualRequest, db: Session = Depends(dependencias.get_db)
):
    try:
        safe = _safe_media_path(req.ruta_foto_mala)
        return foto_service.apply_manual_exif(db, safe, req.fecha_hora_manual)
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    except Exception as e:  # noqa: B904
        raise HTTPException(500, str(e))
