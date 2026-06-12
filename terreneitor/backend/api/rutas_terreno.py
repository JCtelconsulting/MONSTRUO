# ========================= rutas_terreno.py (vPROD MASTER FINAL) =========================
import os
import shutil
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from backend import dependencias, modelos, nucleo

router = APIRouter(
    prefix="/api",
    tags=["Terreno"],
    dependencies=[Depends(dependencias.require_session)],
)


def _verificar_acceso_asignacion(asignacion, current_user):
    """Evita IDOR: un usuario de terreno solo opera sus propias asignaciones.

    ADMIN y SUPERVISOR pueden gestionar cualquiera. Para TERRENO se exige ser el
    usuario_id (legacy) o estar en la cuadrilla (colaboradores).
    """
    rol = getattr(current_user, "role", None)
    rol_val = getattr(rol, "value", rol)
    if rol_val in ("ADMIN", "SUPERVISOR"):
        return
    uid = current_user.id
    if asignacion.usuario_id == uid:
        return
    if any(c.id == uid for c in (asignacion.colaboradores or [])):
        return
    raise HTTPException(status_code=403, detail="No tienes acceso a esta asignación")


# --- HELPER: OBTENER FECHA REAL (MODO ESTRICTO) ---
def get_real_date(file_path):
    """
    Intenta extraer la fecha original de captura.
    Retorna: Objeto datetime si existe.
    Retorna: None si NO tiene fecha EXIF (para enviar a cuarentena).
    """
    try:
        img = Image.open(file_path)
        exif = img._getexif()
        if exif:
            # 36867 = DateTimeOriginal (Fecha de la toma)
            # 306 = DateTime (Fecha de digitalización)
            date_str = exif.get(36867) or exif.get(306)

            if date_str and isinstance(date_str, str):
                # Formato estándar EXIF: YYYY:MM:DD HH:MM:SS
                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    return None  # <--- CLAVE: Si falla, no inventamos fecha.


def _timestamp_conflict(
    dest_folder: str, base_prefix: str, timestamp_str: str, extension: str
) -> bool:
    try:
        base = f"{base_prefix}{timestamp_str}".upper()
        ext_upper = extension.upper()
        for f in Path(dest_folder).iterdir():
            if not f.is_file():
                continue
            name_upper = f.name.upper()
            if name_upper.startswith(base) and f.suffix.upper() == ext_upper:
                return True
    except Exception:
        return False
    return False


def _procesar_archivo(
    file: UploadFile, item: modelos.Item, proyecto_nombre: str, plan_id: int
) -> Tuple[bool, str]:
    tmp_path = None
    try:
        # 1. Guardar temporalmente para análisis
        fd, tmp_path = tempfile.mkstemp(suffix=f"_{file.filename}")
        with os.fdopen(fd, "wb") as tmp_file:
            shutil.copyfileobj(file.file, tmp_file)
    except Exception as e:
        print(f"ERROR TMP: {e}")  # Debug
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return (False, f"ERROR_TMP_{file.filename}")
    finally:
        file.file.close()

    # 2. Análisis EXIF (Fecha Real)
    es_video = (file.content_type or "").startswith("video/")
    tiene_exif = False
    fecha_foto = datetime.now()  # Fecha por defecto (hoy)

    if es_video:
        tiene_exif = True  # Los videos pasan directo
    else:
        # Usamos el helper que definimos antes
        fecha_detectada = get_real_date(tmp_path)

        if fecha_detectada:
            fecha_foto = fecha_detectada
            tiene_exif = True  # Tiene fecha real -> Valida
        else:
            tiene_exif = False  # No tiene fecha -> Cuarentena
            # Dejamos fecha_foto como hoy para el nombre del archivo, pero marcamos false

    try:
        # 3. Determinar Carpeta de Destino
        # Si tiene EXIF o es Video -> _POR_VALIDAR
        # Si NO tiene EXIF -> _CUARENTENA
        es_valido = tiene_exif or es_video

        nombre_carpeta = (
            nucleo.VALIDATION_DIR_NAME if es_valido else nucleo.QUARANTINE_DIR_NAME
        )
        dest_folder = os.path.join(item.ruta_item, nombre_carpeta)

        # Prefijo visual para el archivo
        prefijo = "" if es_valido else "PENDIENTE_"

        os.makedirs(dest_folder, exist_ok=True, mode=0o775)

        # 4. Generar Nombre con Fecha REAL
        timestamp_str = fecha_foto.strftime("%Y%m%d_%H%M%S")
        _, extension = os.path.splitext(file.filename)
        if extension.lower() in [".jpg", ".jpeg"]:
            extension = ".JPG"
        else:
            extension = extension.upper()

        # Nombre: PENDIENTE_Proyecto_Plan_FechaReal.jpg
        clean_proj = "".join(
            [c for c in proyecto_nombre if c.isalnum() or c in ("_", "-")]
        )
        base_prefix = f"{prefijo}{clean_proj}_P{plan_id}_"
        # Evitar duplicados (si sacaron 2 fotos en el mismo segundo)
        offset_seconds = 0
        while _timestamp_conflict(dest_folder, base_prefix, timestamp_str, extension):
            offset_seconds += 1
            ts_dt = fecha_foto + timedelta(seconds=offset_seconds)
            timestamp_str = ts_dt.strftime("%Y%m%d_%H%M%S")
        nuevo_nombre = f"{base_prefix}{timestamp_str}{extension}"
        dest_path = os.path.join(dest_folder, nuevo_nombre)

        # 5. Mover archivo final
        shutil.move(tmp_path, dest_path)
        try:
            os.chmod(dest_path, 0o664)
        except Exception:
            pass

        return (tiene_exif, nuevo_nombre)

    except Exception as e:
        print(f"!!! ERROR PROCESANDO {file.filename}: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        return (False, f"ERROR_MOVE_{file.filename}")


def _procesar_archivo_path(
    tmp_path: str,
    original_name: str,
    content_type: str,
    item: modelos.Item,
    proyecto_nombre: str,
    plan_id: int,
) -> Tuple[bool, str]:
    try:
        es_video = (content_type or "").startswith("video/")
        tiene_exif = False
        fecha_foto = datetime.now()

        if es_video:
            tiene_exif = True
        else:
            fecha_detectada = get_real_date(tmp_path)
            if fecha_detectada:
                fecha_foto = fecha_detectada
                tiene_exif = True
            else:
                tiene_exif = False

        es_valido = tiene_exif or es_video
        nombre_carpeta = (
            nucleo.VALIDATION_DIR_NAME if es_valido else nucleo.QUARANTINE_DIR_NAME
        )
        dest_folder = os.path.join(item.ruta_item, nombre_carpeta)
        prefijo = "" if es_valido else "PENDIENTE_"

        os.makedirs(dest_folder, exist_ok=True, mode=0o775)

        timestamp_str = fecha_foto.strftime("%Y%m%d_%H%M%S")
        _, extension = os.path.splitext(original_name or tmp_path)
        if extension.lower() in [".jpg", ".jpeg"]:
            extension = ".JPG"
        else:
            extension = extension.upper()

        clean_proj = "".join(
            [c for c in proyecto_nombre if c.isalnum() or c in ("_", "-")]
        )
        base_prefix = f"{prefijo}{clean_proj}_P{plan_id}_"
        offset_seconds = 0
        while _timestamp_conflict(dest_folder, base_prefix, timestamp_str, extension):
            offset_seconds += 1
            ts_dt = fecha_foto + timedelta(seconds=offset_seconds)
            timestamp_str = ts_dt.strftime("%Y%m%d_%H%M%S")
        nuevo_nombre = f"{base_prefix}{timestamp_str}{extension}"
        dest_path = os.path.join(dest_folder, nuevo_nombre)

        os.replace(tmp_path, dest_path)
        try:
            os.chmod(dest_path, 0o664)
        except Exception:
            pass

        return (tiene_exif, nuevo_nombre)
    except Exception as e:
        print(f"!!! ERROR PROCESANDO {original_name}: {e}")
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        return (False, f"ERROR_MOVE_{original_name}")


def _procesar_lote_staged(asignacion_id: int, staged_files: List[dict]):
    db = nucleo.SessionLocal()
    try:
        asignacion = (
            db.query(modelos.AsignacionPlan)
            .options(
                selectinload(modelos.AsignacionPlan.item)
                .selectinload(modelos.Item.categoria)
                .selectinload(modelos.Categoria.proyecto)
            )
            .filter(modelos.AsignacionPlan.id == asignacion_id)
            .first()
        )
        if not asignacion:
            for f in staged_files:
                try:
                    if os.path.exists(f["path"]):
                        os.remove(f["path"])
                except Exception:
                    pass
            return

        req_exif = False
        resultados_ok = 0
        for f in staged_files:
            ok, nom = _procesar_archivo_path(
                f["path"],
                f.get("name", ""),
                f.get("content_type", ""),
                asignacion.item,
                asignacion.item.categoria.proyecto.nombre_pmc,
                asignacion.plan_id,
            )
            if "ERROR_" not in nom:
                resultados_ok += 1
                if not ok and not (f.get("content_type") or "").startswith("video/"):
                    req_exif = True

        if resultados_ok:
            novo_estado = (
                modelos.EstadoItemEnum.PENDIENTE_EXIF
                if req_exif
                else modelos.EstadoItemEnum.COMPLETADA_TERRENO
            )
            if asignacion.estado != modelos.EstadoItemEnum.PENDIENTE_EXIF:
                asignacion.estado = novo_estado
                asignacion.fecha_completado_terreno = datetime.now()
            db.commit()
    except Exception as e:
        print(f"!!! ERROR PROCESANDO LOTE {asignacion_id}: {e}")
        db.rollback()
    finally:
        db.close()


# --- ENDPOINTS ---


@router.get(
    "/planes-trabajo/activos/", response_model=List[modelos.AsignacionTerrenoSchema]
)
def get_tareas_asignadas(
    db: Session = Depends(dependencias.get_db),
    user: modelos.User = Depends(dependencias.require_session),
):
    # Un usuario de terreno solo ve:
    # 1. Tareas asignadas directamente (usuario_id legacy)
    # 2. Tareas donde es colaborador (Cuadrilla)
    query = (
        db.query(modelos.AsignacionPlan)
        .join(modelos.PlanTrabajo)
        .options(
            selectinload(modelos.AsignacionPlan.item)
            .selectinload(modelos.Item.categoria)
            .selectinload(modelos.Categoria.proyecto),
            selectinload(modelos.AsignacionPlan.plan),
        )
        .filter(modelos.PlanTrabajo.estado_plan == modelos.EstadoPlanEnum.ABIERTO)
        .filter(
            modelos.AsignacionPlan.estado.in_(
                [
                    modelos.EstadoItemEnum.ASIGNADA,
                    modelos.EstadoItemEnum.RECHAZADA,
                    modelos.EstadoItemEnum.EN_PROGRESO,
                    modelos.EstadoItemEnum.COMPLETADA_TERRENO,
                    modelos.EstadoItemEnum.PENDIENTE_EXIF,
                    modelos.EstadoItemEnum.VALIDADA,
                ]
            )
        )
    )

    # Filtro para Terreno: Solo lo que le pertenece
    if user.role == modelos.UserRoleEnum.TERRENO:
        query = query.filter(
            (modelos.AsignacionPlan.usuario_id == user.id)
            | (modelos.AsignacionPlan.colaboradores.any(id=user.id))
        )

    return query.all()


@router.get(
    "/asignaciones/disponibles/",
    response_model=List[modelos.AsignacionTerrenoSchema],
)
def get_tareas_disponibles(
    db: Session = Depends(dependencias.get_db),
    user: modelos.User = Depends(dependencias.require_session),
):
    """Tareas de planes ABIERTOS que NO tienen a nadie asignado (pool abierto).
    El técnico puede 'tomarlas' sin esperar a que el supervisor lo asigne."""
    return (
        db.query(modelos.AsignacionPlan)
        .join(modelos.PlanTrabajo)
        .options(
            selectinload(modelos.AsignacionPlan.item)
            .selectinload(modelos.Item.categoria)
            .selectinload(modelos.Categoria.proyecto),
            selectinload(modelos.AsignacionPlan.plan),
        )
        .filter(modelos.PlanTrabajo.estado_plan == modelos.EstadoPlanEnum.ABIERTO)
        .filter(modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.ASIGNADA)
        .filter(modelos.AsignacionPlan.usuario_id.is_(None))
        .filter(~modelos.AsignacionPlan.colaboradores.any())
        .all()
    )


@router.post("/asignaciones/{asignacion_id}/tomar")
def tomar_tarea(
    asignacion_id: int,
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_session),
):
    """El técnico se auto-asigna (toma) una tarea: se agrega a la cuadrilla."""
    a = (
        db.query(modelos.AsignacionPlan)
        .options(selectinload(modelos.AsignacionPlan.colaboradores))
        .filter(modelos.AsignacionPlan.id == asignacion_id)
        .first()
    )
    if not a:
        raise HTTPException(404, "Tarea no encontrada")
    if not a.plan or a.plan.estado_plan != modelos.EstadoPlanEnum.ABIERTO:
        raise HTTPException(400, "El plan no está abierto")
    if all(c.id != current_user.id for c in (a.colaboradores or [])):
        a.colaboradores.append(current_user)
    if a.usuario_id is None:
        a.usuario_id = current_user.id
    db.commit()
    return {"status": "ok", "asignacion_id": asignacion_id}


@router.post("/asignaciones/{asignacion_id}/soltar")
def soltar_tarea(
    asignacion_id: int,
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_session),
):
    """El técnico suelta una tarea que había tomado (vuelve al pool si queda sin nadie)."""
    a = (
        db.query(modelos.AsignacionPlan)
        .options(selectinload(modelos.AsignacionPlan.colaboradores))
        .filter(modelos.AsignacionPlan.id == asignacion_id)
        .first()
    )
    if not a:
        raise HTTPException(404, "Tarea no encontrada")
    a.colaboradores = [c for c in (a.colaboradores or []) if c.id != current_user.id]
    if a.usuario_id == current_user.id:
        a.usuario_id = a.colaboradores[0].id if a.colaboradores else None
    db.commit()
    return {"status": "ok", "asignacion_id": asignacion_id}


@router.post("/planes-trabajo/{plan_id}/tomar")
def tomar_plan(
    plan_id: int,
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_session),
):
    """El técnico toma un PLAN completo: se asigna todas las tareas abiertas
    (sin nadie) de ese plan. Pensado para 'tomar un trabajo' de los 7 casos."""
    plan = (
        db.query(modelos.PlanTrabajo).filter(modelos.PlanTrabajo.id == plan_id).first()
    )
    if not plan or plan.estado_plan != modelos.EstadoPlanEnum.ABIERTO:
        raise HTTPException(400, "El plan no está abierto")
    asigs = (
        db.query(modelos.AsignacionPlan)
        .options(selectinload(modelos.AsignacionPlan.colaboradores))
        .filter(modelos.AsignacionPlan.plan_id == plan_id)
        .filter(modelos.AsignacionPlan.estado == modelos.EstadoItemEnum.ASIGNADA)
        .filter(modelos.AsignacionPlan.usuario_id.is_(None))
        .all()
    )
    n = 0
    for a in asigs:
        if a.colaboradores:
            continue
        a.colaboradores.append(current_user)
        if a.usuario_id is None:
            a.usuario_id = current_user.id
        n += 1
    db.commit()
    return {"status": "ok", "plan_id": plan_id, "tomadas": n}


@router.get("/clientes")
def listar_clientes(db: Session = Depends(dependencias.get_db)):
    """Catálogo de clientes (para los dropdowns de creación de plan)."""
    return [
        {"id": c.id, "nombre": c.nombre}
        for c in db.query(modelos.Cliente).order_by(modelos.Cliente.nombre).all()
    ]


@router.post("/clientes")
def crear_cliente(
    payload: dict,
    db: Session = Depends(dependencias.get_db),
):
    """Agrega un cliente al catálogo (normaliza espacios). Reusa si ya existe
    (case-insensitive) para no duplicar."""
    nombre = " ".join((payload.get("nombre") or "").split()).strip()
    if not nombre:
        raise HTTPException(400, "Nombre requerido")
    existente = (
        db.query(modelos.Cliente)
        .filter(func.lower(modelos.Cliente.nombre) == nombre.lower())
        .first()
    )
    if existente:
        return {"id": existente.id, "nombre": existente.nombre, "creado": False}
    c = modelos.Cliente(nombre=nombre)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "nombre": c.nombre, "creado": True}


@router.get("/planes-trabajo/siguiente-numero")
def siguiente_numero(cliente: str, db: Session = Depends(dependencias.get_db)):
    """Próximo número correlativo para ese cliente (evita numeración a mano)."""
    cli = " ".join((cliente or "").split()).strip()
    maxn = (
        db.query(func.max(modelos.PlanTrabajo.numero))
        .filter(modelos.PlanTrabajo.cliente == cli)
        .scalar()
    )
    return {"cliente": cli, "siguiente": (maxn or 0) + 1}


# Tareas por defecto al crear un trabajo desde terreno (según el caso de Diego).
_TAREAS_POR_TIPO = {
    "Instalación": ["Antes", "Durante", "Después", "Etiqueta/Serie"],
    "Retiro": ["Antes del retiro", "Durante", "Equipo retirado"],
    "Traslado": ["Origen", "Traslado", "Destino instalado"],
    "Despacho": ["Equipo", "Etiqueta/Serie", "Guía/Documento"],
    "Reportabilidad EPP": ["EPP puesto", "Área de trabajo", "Checklist"],
    "Avance del día": ["Avance general", "Detalle"],
    "Visita / Preventa": ["Lugar", "Detalle técnico", "Mediciones"],
}
_TAREAS_GENERICAS = ["Foto general", "Foto detalle", "Foto de cierre"]


def _slug_path(s: str) -> str:
    return (
        "".join(c for c in s if c.isalnum() or c in (" ", "_", "-"))
        .strip()
        .replace(" ", "_")
    )


@router.post("/terreno/crear-trabajo")
def crear_trabajo_terreno(
    payload: dict,
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_session),
):
    """El técnico crea su propio trabajo (mismo formulario que el supervisor:
    tipo/cliente/N°/fecha) y queda auto-asignado, con tareas por defecto según
    el tipo. Para cuando hace algo que nadie le planificó."""
    tipo = (payload.get("tipo") or "").strip()
    cliente = " ".join((payload.get("cliente") or "").split()).strip()
    numero = payload.get("numero")
    descripcion = (payload.get("descripcion") or "").strip() or (
        " · ".join([p for p in [tipo, cliente] if p]) or "Trabajo de terreno"
    )

    # Proyecto genérico contenedor de los trabajos creados desde terreno.
    nombre_pmc = "TERRENO_DIRECTO"
    proy = (
        db.query(modelos.Proyecto)
        .filter(modelos.Proyecto.nombre_pmc == nombre_pmc)
        .first()
    )
    if not proy:
        proy = modelos.Proyecto(
            nombre_pmc=nombre_pmc,
            cliente="Varios",
            area="Terreno",
            ruta_base=os.path.join(nucleo.BASE_FILES_DIR, nombre_pmc),
            estado_proyecto=modelos.EstadoProyectoEnum.ACTIVO,
        )
        db.add(proy)
        db.commit()
        db.refresh(proy)

    cat_nombre = tipo or "General"
    cat = (
        db.query(modelos.Categoria)
        .filter(
            modelos.Categoria.proyecto_id == proy.id,
            modelos.Categoria.nombre == cat_nombre,
        )
        .first()
    )
    if not cat:
        cat = modelos.Categoria(nombre=cat_nombre, proyecto_id=proy.id)
        db.add(cat)
        db.commit()
        db.refresh(cat)

    plan = modelos.PlanTrabajo(
        descripcion=descripcion,
        cliente=cliente or None,
        numero=numero,
        estado_plan=modelos.EstadoPlanEnum.ABIERTO,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    nombres = _TAREAS_POR_TIPO.get(tipo, _TAREAS_GENERICAS)
    for nom in nombres:
        item = (
            db.query(modelos.Item)
            .filter(modelos.Item.categoria_id == cat.id, modelos.Item.nombre == nom)
            .first()
        )
        if not item:
            ruta = os.path.join(proy.ruta_base, _slug_path(cat_nombre), _slug_path(nom))
            item = modelos.Item(nombre=nom, ruta_item=ruta, categoria_id=cat.id)
            db.add(item)
            db.commit()
            db.refresh(item)
        asig = modelos.AsignacionPlan(
            plan_id=plan.id,
            item_id=item.id,
            usuario_id=current_user.id,
            estado=modelos.EstadoItemEnum.ASIGNADA,
        )
        db.add(asig)
        db.flush()
        asig.colaboradores.append(current_user)
    db.commit()
    return {"status": "ok", "plan_id": plan.id, "tareas": len(nombres)}


@router.post("/tareas/crear-complemento")
def crear_tarea_complementaria(
    req: modelos.CrearTareaExtraRequest, db: Session = Depends(dependencias.get_db)
):
    plan = (
        db.query(modelos.PlanTrabajo)
        .filter(modelos.PlanTrabajo.id == req.plan_id)
        .first()
    )
    if not plan or plan.estado_plan != modelos.EstadoPlanEnum.ABIERTO:
        raise HTTPException(400, "Plan no válido o cerrado")

    proyecto = (
        db.query(modelos.Proyecto)
        .filter(modelos.Proyecto.id == req.proyecto_id)
        .first()
    )
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    # Buscar/Crear categoría ADICIONALES
    cat = (
        db.query(modelos.Categoria)
        .filter(
            modelos.Categoria.proyecto_id == proyecto.id,
            modelos.Categoria.nombre == "ADICIONALES",
        )
        .first()
    )

    if not cat:
        cat = modelos.Categoria(nombre="ADICIONALES", proyecto_id=proyecto.id)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        try:
            os.makedirs(
                os.path.join(proyecto.ruta_base, "ADICIONALES"),
                exist_ok=True,
                mode=0o775,
            )
        except Exception:
            pass

    # Crear Item
    safe_name = "".join(
        [c for c in req.nombre_tarea if c.isalnum() or c in (" ", "-", "_")]
    ).strip()
    path_item = os.path.join(proyecto.ruta_base, "ADICIONALES", safe_name)
    try:
        os.makedirs(path_item, exist_ok=True, mode=0o775)
    except Exception:
        pass

    item = modelos.Item(
        nombre=req.nombre_tarea, ruta_item=path_item, categoria_id=cat.id
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Asignar
    asig = modelos.AsignacionPlan(
        plan_id=plan.id,
        item_id=item.id,
        estado=modelos.EstadoItemEnum.ASIGNADA,
        es_complementaria=True,
    )
    db.add(asig)
    db.commit()

    return {"status": "ok", "message": "Tarea adicional creada"}


@router.post("/asignaciones/{asignacion_id}/upload-multiple/")
def upload_multiple_archivos(
    asignacion_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_session),
):
    asignacion = (
        db.query(modelos.AsignacionPlan)
        .options(
            selectinload(modelos.AsignacionPlan.item)
            .selectinload(modelos.Item.categoria)
            .selectinload(modelos.Categoria.proyecto)
        )
        .filter(modelos.AsignacionPlan.id == asignacion_id)
        .first()
    )

    if not asignacion:
        raise HTTPException(404, "Tarea no encontrada")
    _verificar_acceso_asignacion(asignacion, current_user)
    if not os.path.exists(asignacion.item.ruta_item):
        try:
            os.makedirs(asignacion.item.ruta_item, exist_ok=True, mode=0o775)
        except Exception:
            pass

    staged_files = []
    staging_dir = os.path.join(
        asignacion.item.ruta_item, "_UPLOADS", f"P{asignacion.plan_id}"
    )
    try:
        os.makedirs(staging_dir, exist_ok=True, mode=0o775)
    except Exception:
        pass

    for file in files:
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(dir=staging_dir, suffix=f"_{file.filename}")
            with os.fdopen(fd, "wb") as tmp_file:
                shutil.copyfileobj(file.file, tmp_file)
            staged_files.append(
                {
                    "path": tmp_path,
                    "name": file.filename,
                    "content_type": file.content_type or "",
                }
            )
        except Exception as e:
            print(f"ERROR TMP: {e}")
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        finally:
            try:
                file.file.close()
            except Exception:
                pass

    if not staged_files:
        raise HTTPException(500, "Fallo total en subida")

    if asignacion.estado not in [modelos.EstadoItemEnum.PENDIENTE_EXIF]:
        asignacion.estado = modelos.EstadoItemEnum.EN_PROGRESO
        db.commit()

    threading.Thread(
        target=_procesar_lote_staged, args=(asignacion.id, staged_files), daemon=True
    ).start()

    background_tasks.add_task(nucleo.run_storage_index_refresh)
    return {"status": "ok", "message": f"En cola {len(staged_files)} archivos."}


@router.post("/asignaciones/{asignacion_id}/completar/")
def completar_asignacion(
    asignacion_id: int,
    request: modelos.CompletarItemRequest,
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_session),
):
    asignacion = (
        db.query(modelos.AsignacionPlan)
        .filter(modelos.AsignacionPlan.id == asignacion_id)
        .first()
    )
    if not asignacion:
        raise HTTPException(404, "No encontrado")
    _verificar_acceso_asignacion(asignacion, current_user)
    if asignacion.estado == modelos.EstadoItemEnum.PENDIENTE_EXIF:
        raise HTTPException(400, "Pendiente revisión EXIF")
    asignacion.estado = modelos.EstadoItemEnum.COMPLETADA_TERRENO
    if request.comentario:
        asignacion.comentario_terreno = request.comentario
    db.commit()
    return {"status": "ok"}
