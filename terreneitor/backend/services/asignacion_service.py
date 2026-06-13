import os
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from terreneitor.backend import modelos, nucleo


def dir_has_files(path: Path) -> bool:
    try:
        return path.exists() and any(p.is_file() for p in path.iterdir())
    except Exception:
        return False


def _load_asignacion(db: Session, asignacion_id: int) -> modelos.AsignacionPlan:
    """Carga una asignacion con item+plan eager. Lanza ValueError si no existe."""
    a = (
        db.query(modelos.AsignacionPlan)
        .options(
            selectinload(modelos.AsignacionPlan.item),
            selectinload(modelos.AsignacionPlan.plan),
        )
        .filter(modelos.AsignacionPlan.id == asignacion_id)
        .first()
    )
    if not a:
        raise ValueError("Asignacion no encontrada")
    return a


def _safe_dest_path(
    dest_dir: Path, source_name: str, source_stem: str, source_suffix: str
) -> Path:
    """Construye un path destino unico (con timestamp si ya existe)."""
    dest = dest_dir / source_name
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        dest = dest_dir / f"{source_stem}_{ts}{source_suffix}"
    return dest


def _move_file_safe(source_path: Path, dest: Path) -> None:
    """Mueve archivo y intenta chmod 0o664. Lanza OSError si shutil.move falla."""
    shutil.move(str(source_path), str(dest))
    try:
        os.chmod(str(dest), 0o664)
    except Exception:
        pass


def _validate_path_under_root(source_path: Path, root: Path) -> None:
    """Verifica que source_path este bajo root. Lanza ValueError si no."""
    try:
        if not source_path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid path")
    except ValueError:
        raise
    except Exception as e:
        raise ValueError("Invalid path") from e


def approve_file(db: Session, ruta_archivo: str, asignacion_id: int) -> dict:
    """Mueve un archivo individual desde _VALIDAR/_DEVUELTAS a la carpeta
    final del plan. Si era el ultimo archivo, marca la asignacion VALIDADA.

    Lanza FileNotFoundError si el archivo no existe.
    Lanza ValueError si la asignacion no existe o el path es invalido.
    """
    source_path = Path(ruta_archivo)
    if not source_path.exists():
        raise FileNotFoundError("File not found")

    a = _load_asignacion(db, asignacion_id)
    root = Path(a.item.ruta_item)
    _validate_path_under_root(source_path, root)

    safe_plan = "".join(
        [c for c in a.plan.descripcion if c.isalnum() or c in (" ", "-", "_")]
    ).strip()
    dest_dir = root / f"PLAN_{a.plan_id}_{safe_plan.replace(' ', '_')}"
    with nucleo.plan_lock(a.plan_id):
        os.makedirs(dest_dir, exist_ok=True, mode=0o775)
        dest = _safe_dest_path(
            dest_dir, source_path.name, source_path.stem, source_path.suffix
        )
        _move_file_safe(source_path, dest)

    if not (
        dir_has_files(root / nucleo.VALIDATION_DIR_NAME)
        or dir_has_files(root / nucleo.RETURNED_DIR_NAME)
    ):
        a.estado = modelos.EstadoItemEnum.VALIDADA
        a.fecha_validacion = datetime.now()
        db.commit()

    return {"status": "ok"}


def reject_file(db: Session, ruta_archivo: str, asignacion_id: int) -> dict:
    """Mueve un archivo individual a la papelera del plan. Si era el ultimo,
    marca la asignacion RECHAZADA y dispara revisar_estado_post_rechazo.

    Lanza FileNotFoundError / ValueError igual que approve_file.
    """
    source_path = Path(ruta_archivo)
    if not source_path.exists():
        raise FileNotFoundError("File not found")

    a = _load_asignacion(db, asignacion_id)
    root = Path(a.item.ruta_item)
    _validate_path_under_root(source_path, root)

    trash_dir = root / nucleo.TRASH_DIR_NAME / f"P{a.plan_id}"
    with nucleo.plan_lock(a.plan_id):
        os.makedirs(trash_dir, exist_ok=True, mode=0o775)
        dest = _safe_dest_path(
            trash_dir, source_path.name, source_path.stem, source_path.suffix
        )
        _move_file_safe(source_path, dest)

    if not (
        dir_has_files(root / nucleo.VALIDATION_DIR_NAME)
        or dir_has_files(root / nucleo.RETURNED_DIR_NAME)
    ):
        a.estado = modelos.EstadoItemEnum.RECHAZADA
        if not a.comentario_rechazo_supervisor:
            a.comentario_rechazo_supervisor = (
                "Rechazo automatico: ultima foto rechazada"
            )
        db.commit()

    item = db.query(modelos.Item).filter(modelos.Item.ruta_item == str(root)).first()
    if item:
        revisar_estado_post_rechazo(db, item.id)

    return {"status": "ok"}


def validate(db: Session, asignacion_id: int) -> dict:
    """Valida una asignacion: mueve archivos de _VALIDAR/_DEVUELTAS al directorio
    final del plan y marca la asignacion como VALIDADA.

    Lanza ValueError si la asignacion no existe.
    Retorna dict con {status, message?}.
    """
    a = (
        db.query(modelos.AsignacionPlan)
        .options(
            selectinload(modelos.AsignacionPlan.item),
            selectinload(modelos.AsignacionPlan.plan),
        )
        .filter(modelos.AsignacionPlan.id == asignacion_id)
        .first()
    )
    if not a:
        raise ValueError("Asignacion no encontrada")

    safe_plan = "".join(
        [c for c in a.plan.descripcion if c.isalnum() or c in (" ", "-", "_")]
    ).strip()
    root = Path(a.item.ruta_item)
    dest_dir = root / f"PLAN_{a.plan_id}_{safe_plan.replace(' ', '_')}"
    src_dirs = [root / nucleo.VALIDATION_DIR_NAME, root / nucleo.RETURNED_DIR_NAME]
    moved = 0

    with nucleo.plan_lock(a.plan_id):
        os.makedirs(dest_dir, exist_ok=True, mode=0o775)
        for src_dir in src_dirs:
            if not src_dir.exists():
                continue
            for f in list(src_dir.iterdir()):
                if not f.is_file():
                    continue
                dest = dest_dir / f.name
                if dest.exists():
                    ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    dest = dest_dir / f"{f.stem}_{ts}{f.suffix}"
                shutil.move(str(f), str(dest))
                try:
                    os.chmod(str(dest), 0o664)
                except Exception:
                    pass
                moved += 1

    if moved == 0 and any(dir_has_files(d) for d in src_dirs):
        return {"status": "ok", "message": "No files to validate"}

    a.estado = modelos.EstadoItemEnum.VALIDADA
    a.fecha_validacion = datetime.now()
    db.commit()

    if moved == 0:
        return {"status": "ok", "message": "Validated without files"}
    return {"status": "ok"}


def restart_validated(db: Session, asignacion_id: int) -> dict:
    """Revierte una asignacion VALIDADA: mueve archivos del PLAN_X_*
    de vuelta a _DEVUELTAS para que terreno los re-suba o el supervisor
    los re-valide. La asignacion vuelve a COMPLETADA_TERRENO y si el
    plan estaba CERRADO lo abre.

    Lanza ValueError si la asignacion no existe.
    Retorna {"status": "ok", "moved": N}.
    """
    a = _load_asignacion(db, asignacion_id)
    root = Path(a.item.ruta_item)
    plan_dirs = sorted(
        [p for p in root.glob(f"PLAN_{a.plan_id}_*") if p.is_dir()],
        key=lambda x: x.name,
    )
    dev_dir = root / nucleo.RETURNED_DIR_NAME

    moved = 0
    with nucleo.plan_lock(a.plan_id):
        os.makedirs(dev_dir, exist_ok=True, mode=0o775)
        if plan_dirs:
            plan_dir = plan_dirs[0]
            for f in plan_dir.iterdir():
                if not f.is_file():
                    continue
                dest = _safe_dest_path(dev_dir, f.name, f.stem, f.suffix)
                _move_file_safe(f, dest)
                moved += 1

    a.estado = modelos.EstadoItemEnum.COMPLETADA_TERRENO
    a.fecha_validacion = None
    if a.plan and a.plan.estado_plan == modelos.EstadoPlanEnum.CERRADO:
        a.plan.estado_plan = modelos.EstadoPlanEnum.ABIERTO
    db.commit()

    return {"status": "ok", "moved": moved}


def revisar_estado_post_rechazo(db: Session, item_id: int):
    item = db.query(modelos.Item).filter(modelos.Item.id == item_id).first()
    if not item or not item.ruta_item:
        return
    root = Path(item.ruta_item)
    cuarentena = root / nucleo.QUARANTINE_DIR_NAME
    validar = root / nucleo.VALIDATION_DIR_NAME
    devueltas = root / nucleo.RETURNED_DIR_NAME

    tiene_cuarentena = dir_has_files(cuarentena)
    tiene_validar = dir_has_files(validar) or dir_has_files(devueltas)

    if tiene_cuarentena:
        new_state = modelos.EstadoItemEnum.PENDIENTE_EXIF
    elif tiene_validar:
        new_state = modelos.EstadoItemEnum.COMPLETADA_TERRENO
    else:
        new_state = modelos.EstadoItemEnum.ASIGNADA

    asigs = (
        db.query(modelos.AsignacionPlan)
        .filter(
            modelos.AsignacionPlan.item_id == item_id,
            modelos.AsignacionPlan.estado.in_(
                [
                    modelos.EstadoItemEnum.PENDIENTE_EXIF,
                    modelos.EstadoItemEnum.COMPLETADA_TERRENO,
                ]
            ),
        )
        .all()
    )

    updated = False
    for a in asigs:
        if a.estado != new_state:
            a.estado = new_state
            updated = True
        if a.plan and a.plan.estado_plan == modelos.EstadoPlanEnum.CERRADO:
            a.plan.estado_plan = modelos.EstadoPlanEnum.ABIERTO
            updated = True

    if updated:
        db.commit()
