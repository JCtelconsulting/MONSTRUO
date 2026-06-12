# ========================= rutas_admin.py (vPROD FINAL) =========================
import json
import os
import re
import shutil
import threading
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend import dependencias, modelos, nucleo

router = APIRouter(
    prefix="/api/admin",
    tags=["Admin"],
    dependencies=[Depends(dependencias.require_admin)],
)

from backend.services import gestion_proyectos, usuario_service
from backend.services.estructura_proyectos import STRUCTURE_TEMPLATES

PROJECT_MARKER_FILENAME = ".terreneitor.json"
SYNC_INTERVAL_SEC = int(os.environ.get("TERRENEITOR_SYNC_INTERVAL", "900"))
PHOTO_NAME_RE = re.compile(
    r"^(?P<prefix>PENDIENTE_)?(?P<project>[A-Za-z0-9_-]+)_P(?P<plan>\d+)_(?P<ts>\d{8}_\d{6})(?:_(?P<dup>\d+))?(?P<ext>\.[A-Za-z0-9]+)$",
    re.IGNORECASE,
)


def _is_test_env() -> bool:
    return (
        os.environ.get("ENV") == "test"
        or os.environ.get("TERRENEITOR_TEST_MODE") == "1"
        or "PYTEST_CURRENT_TEST" in os.environ
    )


class ProyectoAdminCreate(BaseModel):
    cliente: str
    zona: str
    tipo: str
    nombre: str


class ProyectoAdminUpdate(BaseModel):
    cliente: str
    zona: str
    nombre: str


def normalize_segment(value: str) -> str:  # noqa: C901
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text)
    return text.strip("_")


def sanitize_project_for_filename(value: str) -> str:  # noqa: C901
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    return "".join([c for c in text if c.isalnum() or c in ("_", "-")])


def build_project_name(tipo: str, nombre: str) -> str:  # noqa: C901
    tipo_norm = normalize_segment(tipo)
    nombre_norm = normalize_segment(nombre)
    if not tipo_norm or not nombre_norm:
        return ""
    # Si el nombre ya tiene el prefijo del tipo, no lo duplicamos
    prefix = f"{tipo_norm}_"
    if nombre_norm.startswith(prefix):
        return nombre_norm
    return f"{tipo_norm}_{nombre_norm}"


def get_project_type_from_name(nombre_pmc: str) -> str:  # noqa: C901
    if not nombre_pmc:
        return ""
    prefix = nombre_pmc.split("_", 1)[0].strip().upper()
    if prefix in STRUCTURE_TEMPLATES:
        return prefix
    return ""


def build_project_path(cliente: str, zona: str, nombre_pmc: str) -> str:  # noqa: C901
    cliente_norm = normalize_segment(cliente)
    zona_norm = normalize_segment(zona)
    nombre_norm = normalize_segment(nombre_pmc)
    if not cliente_norm or not zona_norm or not nombre_norm:
        return ""
    return os.path.join(nucleo.BASE_FILES_DIR, cliente_norm, zona_norm, nombre_norm)


def write_project_marker(
    project_path: str, project: modelos.Proyecto, tipo: str
):  # noqa: C901
    try:
        data = {
            "project_id": project.id,
            "nombre_pmc": project.nombre_pmc,
            "cliente": project.cliente,
            "zona": project.area,
            "tipo": tipo,
        }
        marker_path = os.path.join(project_path, PROJECT_MARKER_FILENAME)
        with open(marker_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=True, indent=2)
    except Exception:
        pass


def log_rename_summary(summary: dict, log_prefix: str):  # noqa: C901
    if summary.get("renamed"):
        print(f"{log_prefix} renamed={summary['renamed']}", flush=True)
    errors = summary.get("errors") or []
    for idx, err in enumerate(errors):
        if idx >= 50:
            print(f"{log_prefix} ... {len(errors) - 50} more", flush=True)
            break
        print(f"{log_prefix} {err}", flush=True)


def rename_project_files(
    project_path: str, expected_project_name: str
) -> dict:  # noqa: C901
    summary = {"renamed": 0, "errors": []}
    expected = sanitize_project_for_filename(expected_project_name)
    if not expected:
        summary["errors"].append("expected project name empty")
        return summary
    if not os.path.isdir(project_path):
        summary["errors"].append(f"path not found: {project_path}")
        return summary

    for root, _, files in os.walk(project_path):
        for fname in files:
            match = PHOTO_NAME_RE.match(fname)
            if not match:
                continue
            project_part = match.group("project")
            if project_part == expected:
                continue
            prefix = "PENDIENTE_" if match.group("prefix") else ""
            plan = match.group("plan")
            ts = match.group("ts")
            dup = match.group("dup")
            ext = match.group("ext").upper()
            new_name = f"{prefix}{expected}_P{plan}_{ts}"
            if dup:
                new_name = f"{new_name}_{dup}"
            new_name = f"{new_name}{ext}"
            if new_name == fname:
                continue
            src = os.path.join(root, fname)
            dest = os.path.join(root, new_name)
            if os.path.exists(dest):
                summary["errors"].append(f"dest exists: {dest}")
                continue
            try:
                os.replace(src, dest)
                summary["renamed"] += 1
            except Exception as e:  # noqa: B904
                summary["errors"].append(f"rename failed: {src} -> {dest}: {e}")
    return summary


def create_structure(project_path: str, tipo: str):  # noqa: C901
    template = STRUCTURE_TEMPLATES.get(tipo)
    if not template:
        raise RuntimeError(f"Template no disponible para tipo {tipo}")
    for subfolder in template:
        full_path = os.path.join(project_path, subfolder)
        os.makedirs(full_path, mode=0o775, exist_ok=True)
        try:
            os.chmod(full_path, 0o775)
        except Exception:
            pass


def populate_project_from_template(
    db: Session, project: modelos.Proyecto, tipo: str
):  # noqa: C901
    template = STRUCTURE_TEMPLATES.get(tipo)
    if not template:
        raise RuntimeError(f"Template no disponible para tipo {tipo}")
    categorias = {}
    for entry in template:
        parts = [p.strip() for p in entry.split("/") if p.strip()]
        if len(parts) < 3:
            continue
        group_dir, category_dir, item_dir = parts[0], parts[1], parts[2]
        cat_name = category_dir.upper()
        item_name = item_dir.upper()
        cat_key = f"{group_dir.upper()}|{cat_name}"
        cat = categorias.get(cat_key)
        if not cat:
            cat = modelos.Categoria(nombre=cat_name, proyecto_id=project.id)
            db.add(cat)
            db.flush()
            categorias[cat_key] = cat
        item_path = os.path.join(project.ruta_base, group_dir, category_dir, item_dir)
        db.add(modelos.Item(nombre=item_name, ruta_item=item_path, categoria_id=cat.id))


def update_item_paths(
    db: Session, project_id: int, old_base: str, new_base: str
):  # noqa: C901
    if not old_base or not new_base:
        return
    items = (
        db.query(modelos.Item)
        .join(modelos.Categoria)
        .filter(modelos.Categoria.proyecto_id == project_id)
        .all()
    )
    for item in items:
        ruta = item.ruta_item or ""
        if ruta.startswith(old_base):
            item.ruta_item = new_base + ruta[len(old_base) :]


# Local create_project_and_structure removed in favor of servicios.gestion_proyectos


def scan_project_markers(base_dir: str):  # noqa: C901
    markers = {}
    errors = []
    base_depth = len(Path(base_dir).parts)
    for root, dirs, files in os.walk(base_dir, topdown=True):
        # Ignorar papelera para evitar ruido de markers de proyectos eliminados
        dirs[:] = [d for d in dirs if d != nucleo.TRASH_DIR_NAME]
        depth = len(Path(root).parts) - base_depth
        if depth > 3:
            dirs[:] = []
            continue
        if PROJECT_MARKER_FILENAME in files:
            marker_path = os.path.join(root, PROJECT_MARKER_FILENAME)
            try:
                with open(marker_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pid = int(data.get("project_id", 0))
                if pid in markers:
                    # No generar ruido por duplicados en marker scan.
                    # Conservamos el primer path detectado para el project_id.
                    continue
                else:
                    markers[pid] = root
            except Exception as e:  # noqa: B904
                errors.append(f"Error leyendo marker {marker_path}: {e}")
        if depth >= 3:
            dirs[:] = []
    return markers, errors


def sync_projects_db(
    db: Session, apply_changes: bool = True, log_prefix: str = "[SYNC]"
):
    summary = {
        "updated": 0,
        "created_markers": 0,
        "missing_markers": [],
        "missing_paths": [],
        "orphan_markers": [],
        "errors": [],
        "renamed_photos": 0,
        "rename_errors": [],
    }
    if not os.path.isdir(nucleo.BASE_FILES_DIR):
        summary["errors"].append("BASE_FILES_DIR no disponible")
        return summary

    markers, scan_errors = scan_project_markers(nucleo.BASE_FILES_DIR)
    summary["errors"].extend(scan_errors)

    for pid, found_path in markers.items():
        project = db.query(modelos.Proyecto).filter(modelos.Proyecto.id == pid).first()
        if not project:
            summary["orphan_markers"].append(found_path)
            continue

        old_base = project.ruta_base or ""
        if os.path.normpath(old_base) != os.path.normpath(found_path):
            rel = None
            try:
                rel = Path(found_path).relative_to(nucleo.BASE_FILES_DIR)
            except Exception:
                summary["errors"].append(f"Ruta fuera de base: {found_path}")
            if rel and len(rel.parts) >= 3:
                new_cliente, new_zona, new_nombre = (
                    rel.parts[0],
                    rel.parts[1],
                    rel.parts[2],
                )
                dup = (
                    db.query(modelos.Proyecto)
                    .filter(
                        modelos.Proyecto.nombre_pmc == new_nombre,
                        modelos.Proyecto.id != project.id,
                    )
                    .first()
                )
                if dup:
                    summary["errors"].append(f"Nombre duplicado: {new_nombre}")
                    continue
                if apply_changes:
                    if new_nombre != project.nombre_pmc:
                        rename_summary = rename_project_files(found_path, new_nombre)
                        summary["renamed_photos"] += rename_summary.get("renamed", 0)
                        if rename_summary.get("errors"):
                            summary["rename_errors"].extend(rename_summary["errors"])
                            log_rename_summary(rename_summary, f"{log_prefix} RENAME")
                    update_item_paths(db, project.id, old_base, found_path)
                    project.cliente = new_cliente
                    project.area = new_zona
                    project.nombre_pmc = new_nombre
                    project.ruta_base = found_path
                    summary["updated"] += 1
                    write_project_marker(
                        found_path, project, get_project_type_from_name(new_nombre)
                    )
            else:
                summary["errors"].append(f"Ruta invalida para proyecto {project.id}")

    if apply_changes:
        db.commit()

    db_projects = db.query(modelos.Proyecto).all()
    for project in db_projects:
        ruta_base = project.ruta_base or ""
        if project.id in markers:
            continue
        if ruta_base and os.path.isdir(ruta_base):
            write_project_marker(
                ruta_base, project, get_project_type_from_name(project.nombre_pmc)
            )
            summary["created_markers"] += 1
        else:
            summary["missing_paths"].append(project.nombre_pmc or f"id:{project.id}")
            summary["missing_markers"].append(project.nombre_pmc or f"id:{project.id}")

    if summary["updated"] > 0 and apply_changes:
        db.commit()

    for msg in summary["errors"]:
        print(f"{log_prefix} {msg}", flush=True)
    return summary


def start_project_sync_timer():  # noqa: C901
    if (
        SYNC_INTERVAL_SEC <= 0
        or _is_test_env()
        or os.environ.get("TERRENEITOR_DISABLE_PROJECT_SYNC") == "1"
    ):
        return

    def _run():  # noqa: C901
        db = nucleo.SessionLocal()
        try:
            res = sync_projects_db(db, apply_changes=True)
            if res.get("updated"):
                print(f"[SYNC] actualizados={res['updated']}", flush=True)
        except Exception as e:  # noqa: B904
            print(f"[SYNC] error: {e}", flush=True)
        finally:
            db.close()
        t = threading.Timer(SYNC_INTERVAL_SEC, _run)
        t.daemon = True
        t.start()

    t = threading.Timer(SYNC_INTERVAL_SEC, _run)
    t.daemon = True
    t.start()


@router.get("/users", response_model=List[modelos.UserSchema])
def admin_get_users(db: Session = Depends(dependencias.get_db)):
    return usuario_service.list_users(db)


@router.post("/users", response_model=modelos.UserSchema)
def admin_create_user(
    req: modelos.UserCreate, db: Session = Depends(dependencias.get_db)
):
    try:
        return usuario_service.create_user(
            db, req.email, req.name, req.role, req.password
        )
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e


@router.put("/users/{user_id}", response_model=modelos.UserSchema)
def admin_update_user(
    user_id: int,
    req: modelos.UserUpdate,
    db: Session = Depends(dependencias.get_db),
):
    try:
        return usuario_service.update_user(
            db, user_id, email=req.email, name=req.name, role=req.role
        )
    except LookupError as e:
        raise HTTPException(404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(dependencias.get_db),
    current_user: modelos.User = Depends(dependencias.require_admin),
):
    try:
        usuario_service.delete_user(
            db, user_id, current_user.id if current_user else None
        )
    except ValueError as e:
        raise HTTPException(403, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(404, detail=str(e)) from e
    return {"status": "ok"}


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    req: modelos.AdminPasswordResetRequest,
    db: Session = Depends(dependencias.get_db),
):
    try:
        usuario_service.reset_user_password(db, user_id, req.new_password)
    except LookupError as e:
        raise HTTPException(404, detail=str(e)) from e
    return {"status": "ok"}


@router.post("/trigger/storage_scan")
async def trigger_storage_scan():  # noqa: C901
    nucleo.run_storage_index_refresh()
    return {"message": "Scanner iniciado"}


@router.get("/proyectos")
def admin_get_proyectos(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    # Remove SQL order_by strict to sort in Python
    proyectos = db.query(modelos.Proyecto).all()

    # Natural Sort Helper
    def natural_keys(text):  # noqa: C901
        import re

        return [
            int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text or "")
        ]

    # Sort in Python
    proyectos.sort(key=lambda p: natural_keys(p.nombre_pmc))

    res = []
    for p in proyectos:
        res.append(
            {
                "id": p.id,
                "nombre_pmc": p.nombre_pmc,
                "cliente": p.cliente,
                "zona": p.area,
                "ruta_base": p.ruta_base,
                "estado": p.estado_proyecto.value if p.estado_proyecto else None,
            }
        )
    return res


@router.post("/proyectos")
def admin_create_proyecto(
    req: ProyectoAdminCreate, db: Session = Depends(dependencias.get_db)
):
    project = gestion_proyectos.create_project_and_structure(
        db, req.cliente, req.zona, req.tipo, req.nombre
    )
    return {"status": "ok", "id": project.id, "nombre_pmc": project.nombre_pmc}


@router.put("/proyectos/{pid}/estado")
def admin_cambiar_estado(
    pid: int,
    estado: modelos.EstadoProyectoEnum = Body(..., embed=True),
    db: Session = Depends(dependencias.get_db),
):
    p = db.query(modelos.Proyecto).filter(modelos.Proyecto.id == pid).first()
    if not p:
        raise HTTPException(404, "No encontrado")
    p.estado_proyecto = estado
    db.commit()
    return {"status": "ok"}


@router.put("/proyectos/{project_id}")
def admin_update_proyecto(
    project_id: int,
    req: ProyectoAdminUpdate,
    db: Session = Depends(dependencias.get_db),
):
    project = (
        db.query(modelos.Proyecto).filter(modelos.Proyecto.id == project_id).first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    tipo = get_project_type_from_name(project.nombre_pmc) or "PMC"
    old_nombre_pmc = project.nombre_pmc
    new_nombre_pmc = build_project_name(tipo, req.nombre)
    if not new_nombre_pmc:
        raise HTTPException(status_code=400, detail="Nombre no valido")

    existing = (
        db.query(modelos.Proyecto)
        .filter(
            modelos.Proyecto.nombre_pmc == new_nombre_pmc,
            modelos.Proyecto.id != project_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Nombre ya existe")

    new_base = build_project_path(req.cliente, req.zona, new_nombre_pmc)
    if not new_base:
        raise HTTPException(status_code=400, detail="Cliente/Zona no validos")

    old_base = project.ruta_base or ""
    if old_base and os.path.normpath(old_base) != os.path.normpath(new_base):
        if os.path.exists(new_base):
            raise HTTPException(status_code=409, detail="Ruta destino ya existe")
        if os.path.exists(old_base):
            os.makedirs(os.path.dirname(new_base), mode=0o775, exist_ok=True)
            shutil.move(old_base, new_base)
        elif not os.path.exists(new_base):
            raise HTTPException(
                status_code=400, detail="Ruta actual no existe en disco"
            )

        update_item_paths(db, project.id, old_base, new_base)

    project.nombre_pmc = new_nombre_pmc
    project.cliente = normalize_segment(req.cliente)
    project.area = normalize_segment(req.zona)
    project.ruta_base = new_base
    db.commit()
    write_project_marker(new_base, project, tipo)

    warnings = []
    if old_nombre_pmc != new_nombre_pmc:
        rename_summary = rename_project_files(new_base, new_nombre_pmc)
        log_rename_summary(rename_summary, "[RENAME]")
        if rename_summary.get("renamed"):
            warnings.append(f"renamed={rename_summary['renamed']}")
        if rename_summary.get("errors"):
            warnings.append(f"errors={len(rename_summary['errors'])}")
            warnings.extend(rename_summary["errors"][:5])

    if warnings:
        return {"status": "ok", "warnings": warnings}
    return {"status": "ok"}


@router.post("/proyectos/sync")
def admin_sync_proyectos(db: Session = Depends(dependencias.get_db)):  # noqa: C901
    return sync_projects_db(db, apply_changes=True)


@router.post("/proyectos/crear-nuevo")
def crear_nuevo_proyecto(
    nombre_pmc: str = Body(..., embed=True),
    cliente: str = Body(..., embed=True),
    area: str = Body(..., embed=True),
    db: Session = Depends(dependencias.get_db),
):
    tipo = get_project_type_from_name(nombre_pmc) or "PMC"
    nombre = nombre_pmc
    if nombre_pmc.upper().startswith(f"{tipo}_"):
        nombre = nombre_pmc.split("_", 1)[1]
    project = gestion_proyectos.create_project_and_structure(
        db, cliente, area, tipo, nombre
    )
    return {"status": "ok", "id": project.id}


@router.delete("/proyectos/{pid}")
def admin_delete_proyecto(
    pid: int, db: Session = Depends(dependencias.get_db)
):  # noqa: C901
    project = db.query(modelos.Proyecto).filter(modelos.Proyecto.id == pid).first()
    if not project:
        raise HTTPException(404, "No encontrado")

    ruta_base = project.ruta_base
    project_name = project.nombre_pmc

    # 1. Eliminate from DB (Cascades should handle items/categories if configured, otherwise we rely on manual or foreign keys)
    # Assuming SQLAlchemy relationships cascade.
    try:
        db.delete(project)
        db.commit()
    except Exception as e:  # noqa: B904
        db.rollback()
        raise HTTPException(500, f"Error DB: {e}")

    # 2. Move to TRASH if exists
    if ruta_base and os.path.isdir(ruta_base):
        trash_dir = os.path.join(nucleo.BASE_FILES_DIR, nucleo.TRASH_DIR_NAME)
        os.makedirs(trash_dir, exist_ok=True)
        # Create a unique name for trash
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_name = f"{project_name}_DELETED_{timestamp}"
        dest_path = os.path.join(trash_dir, dest_name)
        try:
            shutil.move(ruta_base, dest_path)
        except Exception:
            pass  # Non-critical if move fails

    return {"status": "ok"}


@router.get("/proyectos/{pid}/structure")
def admin_get_structure(
    pid: int, db: Session = Depends(dependencias.get_db)
):  # noqa: C901
    return gestion_proyectos.get_project_structure(db, pid)


class ItemCreate(BaseModel):
    category: str
    item: str


@router.post("/proyectos/{pid}/items")
def admin_add_item(
    pid: int, req: ItemCreate, db: Session = Depends(dependencias.get_db)
):
    item = gestion_proyectos.add_project_item(db, pid, req.category, req.item)
    return {"status": "ok", "id": item.id}


@router.delete("/items/{item_id}")
def admin_delete_item(
    item_id: int, db: Session = Depends(dependencias.get_db)
):  # noqa: C901
    return gestion_proyectos.delete_project_item(db, item_id)


class MovePhotosRequest(BaseModel):
    src_item_id: int
    dest_item_id: int
    photos: List[str]


@router.post("/items/move-photos")
def admin_move_photos(
    req: MovePhotosRequest, db: Session = Depends(dependencias.get_db)
):
    return gestion_proyectos.move_photos(
        db, req.src_item_id, req.dest_item_id, req.photos
    )


@router.get("/system/stats")
def get_system_stats(
    user: modelos.User = Depends(dependencias.require_admin),
):  # noqa: C901
    # DEBUG LOGS
    print("--- DEBUG STATS START ---")

    # CPU Load (1 min avg)
    cpu_percent = 0
    try:
        load1, load5, load15 = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        cpu_percent = min(100, round((load1 / cpu_count) * 100, 1))
        print(f"DEBUG CPU: {load1} / {cpu_count} = {cpu_percent}%")
    except Exception as e:  # noqa: B904
        print(f"DEBUG CPU ERROR: {e}")

    # RAM
    ram_total = 0
    ram_avail = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if "MemTotal" in line:
                    ram_total = int(line.split()[1]) * 1024
                elif "MemAvailable" in line:
                    ram_avail = int(line.split()[1]) * 1024
        print(f"DEBUG RAM: Total={ram_total} Avail={ram_avail}")
    except Exception as e:  # noqa: B904
        print(f"DEBUG RAM ERROR: {e}")

    ram_used = ram_total - ram_avail
    ram_percent = 0
    if ram_total > 0:
        ram_percent = round((ram_used / ram_total) * 100, 1)

    # Disk
    disk_percent = 0
    disk_used = 0
    disk_total = 0
    try:
        path_to_check = (
            nucleo.BASE_FILES_DIR if os.path.exists(nucleo.BASE_FILES_DIR) else "/"
        )
        print(f"DEBUG DISK PATH: {path_to_check}")
        disk_usage = shutil.disk_usage(path_to_check)
        disk_total = disk_usage.total
        disk_used = disk_usage.used
        if disk_total > 0:
            disk_percent = round((disk_used / disk_total) * 100, 1)
        print(f"DEBUG DISK: {disk_used} / {disk_total}")
    except Exception as e:  # noqa: B904
        print(f"DEBUG DISK ERROR: {e}")

    # Uptime
    uptime_seconds = 0
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
        print(f"DEBUG UPTIME: {uptime_seconds}")
    except Exception as e:  # noqa: B904
        print(f"DEBUG UPTIME ERROR: {e}")

    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    uptime_str = f"{days}d {hours}h {minutes}m"

    print("--- DEBUG STATS END ---")

    return {
        "cpu": cpu_percent,
        "ram": ram_percent,
        "ram_gb": round(ram_used / (1024**3), 1),
        "ram_total_gb": round(ram_total / (1024**3), 1),
        "disk": disk_percent,
        "disk_gb": round(disk_used / (1024**3), 1),
        "disk_total_gb": round(disk_total / (1024**3), 1),
        "uptime": uptime_str,
        "service": "active",
    }


@router.get("/files/view")
def get_file_view(path: str):
    """Sirve un archivo desde el servidor (acepta rutas absolutas y relativas a BASE_FILES_DIR)."""
    path = (path or "").strip()
    if not path:
        raise HTTPException(400, "Path requerido")

    clean_path = os.path.normpath(path)

    if os.path.isabs(clean_path) and os.path.exists(clean_path):
        if os.path.isdir(clean_path):
            raise HTTPException(400, "Es un directorio")
        return _serve_file(clean_path)

    base_files = os.path.normpath(nucleo.BASE_FILES_DIR)
    final_path = os.path.join(base_files, clean_path)
    if not os.path.exists(final_path):
        raise HTTPException(404, "Archivo no encontrado")
    if os.path.isdir(final_path):
        raise HTTPException(400, "Es un directorio")
    return _serve_file(final_path)


def _serve_file(absolute_path: str) -> FileResponse:
    lower_path = absolute_path.lower()
    if lower_path.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif lower_path.endswith(".png"):
        media_type = "image/png"
    elif lower_path.endswith(".webp"):
        media_type = "image/webp"
    else:
        media_type = None

    headers = {
        "Content-Disposition": "inline",
        "Cache-Control": "no-cache, no-store, must-revalidate",
    }
    return FileResponse(absolute_path, media_type=media_type, headers=headers)
