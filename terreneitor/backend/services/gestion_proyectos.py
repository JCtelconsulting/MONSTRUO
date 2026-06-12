import json
import os
import re
import shutil
import unicodedata

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend import modelos, nucleo


# --- CONFIGURACION ---
def _is_test_env() -> bool:
    return (
        os.environ.get("ENV") == "test"
        or os.environ.get("TERRENEITOR_TEST_MODE") == "1"
        or "PYTEST_CURRENT_TEST" in os.environ
    )


from backend.services.estructura_proyectos import STRUCTURE_TEMPLATES

if not STRUCTURE_TEMPLATES and _is_test_env():
    STRUCTURE_TEMPLATES = {
        "PMC": ["GENERAL/GENERAL/ITEM"],
        "OBRA": ["GENERAL/GENERAL/ITEM"],
        "SATLINK": ["GENERAL/GENERAL/ITEM"],
        "DOMICILIO": ["GENERAL/GENERAL/ITEM"],
        "LEVANTAMIENTO": ["GENERAL/GENERAL/ITEM"],
    }

PROJECT_MARKER_FILENAME = ".terreneitor.json"
PHOTO_NAME_RE = re.compile(
    r"^(?P<prefix>PENDIENTE_)?(?P<project>[A-Za-z0-9_-]+)_P(?P<plan>\d+)_(?P<ts>\d{8}_\d{6})(?:_(?P<dup>\d+))?(?P<ext>\.[A-Za-z0-9]+)$",
    re.IGNORECASE,
)


def normalize_segment(value: str) -> str:
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


def sanitize_project_for_filename(value: str) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    return "".join([c for c in text if c.isalnum() or c in ("_", "-")])


def build_project_name(tipo: str, nombre: str) -> str:
    tipo_norm = normalize_segment(tipo)
    nombre_norm = normalize_segment(nombre)
    if not tipo_norm or not nombre_norm:
        return ""

    # Si el nombre ya empieza por el tipo, no lo repetimos
    prefix = f"{tipo_norm}_"
    if nombre_norm.startswith(prefix):
        return nombre_norm

    return f"{tipo_norm}_{nombre_norm}"


def get_project_type_from_name(nombre_pmc: str) -> str:
    if not nombre_pmc:
        return ""
    prefix = nombre_pmc.split("_", 1)[0].strip().upper()
    if prefix in STRUCTURE_TEMPLATES:
        return prefix
    return ""


def build_project_path(cliente: str, zona: str, nombre_pmc: str) -> str:
    cliente_norm = normalize_segment(cliente)
    zona_norm = normalize_segment(zona)
    nombre_norm = normalize_segment(nombre_pmc)
    if not cliente_norm or not zona_norm or not nombre_norm:
        return ""
    return os.path.join(nucleo.BASE_FILES_DIR, cliente_norm, zona_norm, nombre_norm)


def write_project_marker(project_path: str, project: modelos.Proyecto, tipo: str):
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


def create_structure(project_path: str, tipo: str):
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


def populate_project_from_template(db: Session, project: modelos.Proyecto, tipo: str):
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


def create_project_and_structure(
    db: Session, cliente: str, zona: str, tipo: str, nombre: str
):
    tipo_norm = normalize_segment(tipo)
    if tipo_norm not in STRUCTURE_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail="Tipo no valido (Templates: PMC, OBRA, SATLINK, DOMICILIO, LEVANTAMIENTO)",
        )
    nombre_pmc = build_project_name(tipo_norm, nombre)
    if not nombre_pmc:
        raise HTTPException(status_code=400, detail="Nombre no valido")
    if (
        db.query(modelos.Proyecto)
        .filter(modelos.Proyecto.nombre_pmc == nombre_pmc)
        .first()
    ):
        raise HTTPException(status_code=400, detail="Proyecto ya existe")

    ruta_base = build_project_path(cliente, zona, nombre_pmc)
    if not ruta_base:
        raise HTTPException(status_code=400, detail="Cliente/Zona no validos")
    if not os.path.isdir(nucleo.BASE_FILES_DIR):
        raise HTTPException(status_code=500, detail="BASE_FILES_DIR no disponible")
    if os.path.exists(ruta_base):
        raise HTTPException(status_code=409, detail="Ruta ya existe en disco")

    os.makedirs(ruta_base, mode=0o775, exist_ok=False)
    try:
        os.chmod(ruta_base, 0o775)
    except Exception:
        pass

    create_structure(ruta_base, tipo_norm)

    project = modelos.Proyecto(
        nombre_pmc=nombre_pmc,
        cliente=normalize_segment(cliente),
        area=normalize_segment(zona),
        ruta_base=ruta_base,
    )
    db.add(project)
    try:
        db.flush()
        populate_project_from_template(db, project, tipo_norm)
        db.commit()
        db.refresh(project)
    except Exception as e:
        db.rollback()
        # shutil.rmtree(ruta_base) # Opcional: limpiar si falla DB
        raise HTTPException(status_code=500, detail=f"Error creando items: {e}")
    write_project_marker(ruta_base, project, tipo_norm)
    return project


def update_item_paths(db: Session, project_id: int, old_base: str, new_base: str):
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


def rename_project_files(project_path: str, expected_project_name: str) -> dict:
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
            except Exception as e:
                summary["errors"].append(f"rename failed: {src} -> {dest}: {e}")
    return summary


def get_project_structure(db: Session, project_id: int):
    project = (
        db.query(modelos.Proyecto).filter(modelos.Proyecto.id == project_id).first()
    )
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    # Get all categories and items
    categories = (
        db.query(modelos.Categoria)
        .filter(modelos.Categoria.proyecto_id == project_id)
        .order_by(modelos.Categoria.nombre)
        .all()
    )

    tree = []
    # base_path unused removed

    for cat in categories:
        cat_node = {"id": cat.id, "name": cat.nombre, "items": []}
        for item in cat.items:
            photos = []
            if item.ruta_item and os.path.isdir(item.ruta_item):
                try:
                    for root, _, files in os.walk(item.ruta_item):
                        for f in files:
                            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                                full_path = os.path.join(root, f)
                                if os.path.exists(full_path):
                                    rel_path = os.path.relpath(
                                        full_path, item.ruta_item
                                    )
                                    photos.append(rel_path)
                    photos.sort()
                except Exception:
                    pass

            cat_node["items"].append(
                {
                    "id": item.id,
                    "name": item.nombre,
                    "path": item.ruta_item,
                    "photos": len(photos),
                    "files": photos,  # Return list
                }
            )

        tree.append(cat_node)

    # Helper for Natural Sort
    def natural_keys(text):
        import re

        return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", text)]

    # Sort Items in each Category
    for node in tree:
        node["items"].sort(key=lambda x: natural_keys(x["name"]))

    # Sort Categories
    tree.sort(key=lambda x: natural_keys(x["name"]))

    return {"project_id": project.id, "name": project.nombre_pmc, "tree": tree}


def add_project_item(db: Session, project_id: int, category_name: str, item_name: str):
    project = (
        db.query(modelos.Proyecto).filter(modelos.Proyecto.id == project_id).first()
    )
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    cat_norm = normalize_segment(category_name)
    item_norm = normalize_segment(item_name)

    if not cat_norm or not item_norm:
        raise HTTPException(400, "Nombres invalidos")

    # Find or Create Category
    category = (
        db.query(modelos.Categoria)
        .filter(
            modelos.Categoria.proyecto_id == project_id,
            modelos.Categoria.nombre == cat_norm,
        )
        .first()
    )
    if not category:
        category = modelos.Categoria(nombre=cat_norm, proyecto_id=project_id)
        db.add(category)
        db.flush()

    # Check existence
    existing = (
        db.query(modelos.Item)
        .filter(
            modelos.Item.categoria_id == category.id, modelos.Item.nombre == item_norm
        )
        .first()
    )
    if existing:
        raise HTTPException(409, "El item ya existe")

    # Create Directory
    # Assuming Standard PMC Structure: BASE / TIPO / CATEGORIA / ITEM
    # We need to guess the "Group dir" (TIPO) if it's not provided.
    # For now, we'll try to deduce it from existing items in the category, or default to "DOCS" if new.
    # Inference Strategy: Look at sibling items in the same category.
    parent_dir = None
    if category.items:
        sibling = category.items[0]
        if sibling.ruta_item:
            parent_dir = os.path.dirname(sibling.ruta_item)

    if not parent_dir:
        # Fallback: Try to use project base + "GENERAL" + category
        if not project.ruta_base:
            raise HTTPException(500, "Proyecto sin ruta base")
        parent_dir = os.path.join(project.ruta_base, "GENERAL", cat_norm)

    new_path = os.path.join(parent_dir, item_norm)

    # Create FS
    try:
        os.makedirs(new_path, mode=0o775, exist_ok=True)
    except Exception as e:
        raise HTTPException(500, f"Error creando directorio: {e}")

    # Create DB Record
    new_item = modelos.Item(
        nombre=item_norm, ruta_item=new_path, categoria_id=category.id
    )
    db.add(new_item)
    db.commit()
    return new_item


def delete_project_item(db: Session, item_id: int):
    item = db.query(modelos.Item).filter(modelos.Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "Item no encontrado")

    # Move to trash
    if item.ruta_item and os.path.isdir(item.ruta_item):
        trash_dir = os.path.join(nucleo.BASE_FILES_DIR, nucleo.TRASH_DIR_NAME)
        os.makedirs(trash_dir, exist_ok=True)
        timestamp = nucleo.time.strftime("%Y%m%d_%H%M%S")
        dest_name = f"DEL_{item.id}_{timestamp}_{os.path.basename(item.ruta_item)}"
        try:
            shutil.move(item.ruta_item, os.path.join(trash_dir, dest_name))
        except Exception:
            pass  # Continue to delete from DB

    # DB Delete
    db.delete(item)
    db.commit()
    return {"status": "ok"}


def move_photos(db: Session, src_item_id: int, dest_item_id: int, photos: list[str]):
    src = db.query(modelos.Item).filter(modelos.Item.id == src_item_id).first()
    dest = db.query(modelos.Item).filter(modelos.Item.id == dest_item_id).first()

    if not src or not dest:
        raise HTTPException(404, "Item origen o destino no encontrado")

    if not src.ruta_item or not os.path.isdir(src.ruta_item):
        raise HTTPException(400, "Directorio origen invalido")
    if not dest.ruta_item or not os.path.isdir(dest.ruta_item):
        raise HTTPException(400, "Directorio destino invalido")

    # Determine Project Name for renaming
    # We assume dest item belongs to a project with a consistent naming convention
    # Photo regex: PREFIX_PROJECT_P{Plan}_{Timestamp}_{Dup}.ext
    # We need to extract the project part from destination project name
    project = dest.categoria.proyecto
    project_clean = sanitize_project_for_filename(project.nombre_pmc)

    moved_count = 0
    errors = []

    for photo in photos:
        src_path = os.path.join(src.ruta_item, photo)
        if not os.path.exists(src_path):
            errors.append(f"{photo}: no existe")
            continue

        # Rename logic
        # 1. Parse original
        rel_dir = os.path.dirname(photo)
        filename = os.path.basename(photo)
        match = PHOTO_NAME_RE.match(filename)
        new_name = filename

        if match:
            # Reconstruct with new project name if valid match
            prefix = "PENDIENTE_" if match.group("prefix") else ""
            plan = match.group("plan")
            ts = match.group("ts")
            dup = match.group("dup")
            ext = match.group("ext").upper()

            new_name = f"{prefix}{project_clean}_P{plan}_{ts}"
            if dup:
                new_name += f"_{dup}"
            new_name += ext

        # Determine destination folder (PRESERVE STRUCTURE)
        dest_dir = dest.ruta_item
        if rel_dir:
            dest_dir = os.path.join(dest.ruta_item, rel_dir)
            if not os.path.exists(dest_dir):
                try:
                    # Force 777 to avoid permission issues in nested folders
                    old_mask = os.umask(0)
                    os.makedirs(dest_dir, mode=0o777, exist_ok=True)
                    os.umask(old_mask)
                except Exception:
                    pass

        dest_path = os.path.join(dest_dir, new_name)

        # Avoid overwrite
        if os.path.exists(dest_path):
            name, ext = os.path.splitext(new_name)
            new_name = f"{name}_{int(nucleo.time.time())}{ext}"
            dest_path = os.path.join(dest_dir, new_name)

        try:
            shutil.move(src_path, dest_path)
            moved_count += 1
        except Exception as e:
            errors.append(f"{photo}: error moviendo {e}")

    return {"moved": moved_count, "errors": errors}
