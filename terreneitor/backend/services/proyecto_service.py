import os
import shutil
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from terreneitor.backend import modelos, nucleo
from terreneitor.backend.services.estructura_proyectos import STRUCTURE_TEMPLATES


def delete_project_filesystem(ruta_base: str) -> None:
    """Borra la carpeta de un proyecto y limpia hasta dos niveles padres
    si quedan vacios. Lanza ValueError si la ruta esta fuera de
    BASE_FILES_DIR o coincide con la base (proteccion).

    Lanza OSError con detalle si shutil.rmtree falla.
    """
    if not ruta_base:
        return
    base_dir = Path(os.path.abspath(nucleo.BASE_FILES_DIR))
    target = Path(os.path.abspath(ruta_base))
    if target == base_dir or base_dir not in target.parents:
        raise ValueError(f"Ruta fuera de base: {target}")
    if target.exists():
        shutil.rmtree(target)

    def _try_remove_empty(path: Path) -> bool:
        try:
            next(path.iterdir())
            return False
        except StopIteration:
            try:
                path.rmdir()
                return True
            except OSError:
                return False
        except FileNotFoundError:
            return True

    parent = target.parent
    if parent != base_dir and base_dir in parent.parents:
        if _try_remove_empty(parent):
            parent2 = parent.parent
            if parent2 != base_dir and base_dir in parent2.parents:
                _try_remove_empty(parent2)


def get_project_type_from_name(nombre_pmc: str) -> str:
    if not nombre_pmc:
        return ""
    prefix = nombre_pmc.split("_", 1)[0].strip().upper()
    if prefix in STRUCTURE_TEMPLATES:
        return prefix
    return ""


def build_category_order_map(tipo: str) -> dict:
    template = STRUCTURE_TEMPLATES.get(tipo) or []
    order = {}
    for idx, entry in enumerate(template):
        parts = [p.strip() for p in entry.split("/") if p.strip()]
        if len(parts) < 3:
            continue
        group = parts[0].upper()
        category = parts[1].upper()
        key = f"{group}/{category}"
        if key not in order:
            order[key] = idx
    return order


def build_group_order_map(tipo: str) -> dict:
    template = STRUCTURE_TEMPLATES.get(tipo) or []
    order = {}
    for idx, entry in enumerate(template):
        parts = [p.strip() for p in entry.split("/") if p.strip()]
        if len(parts) < 2:
            continue
        group = parts[0].upper()
        if group not in order:
            order[group] = idx
    return order


def get_planning_detail(db: Session, proyecto_id: int) -> dict:
    """Devuelve el detalle de planificacion de un proyecto: items agrupados
    por carpeta raiz (EDP/INFORME/OTROS) y ordenados segun el template.

    Si el proyecto no tiene categorias y su nombre matchea un template,
    se popula automaticamente desde el template.

    Lanza LookupError si el proyecto no existe.
    Lanza RuntimeError si falla la inicializacion desde template.
    """
    p = _load_with_categorias(db, proyecto_id)
    if not p:
        raise LookupError(f"Proyecto {proyecto_id} no encontrado")

    if not p.categorias:
        tipo = get_project_type_from_name(p.nombre_pmc)
        if tipo:
            try:
                populate_project_from_template(db, p, tipo)
                db.commit()
            except Exception as e:
                db.rollback()
                raise RuntimeError(f"Error inicializando tareas: {e}") from e
            p = _load_with_categorias(db, proyecto_id)
            if not p:
                raise LookupError(f"Proyecto {proyecto_id} no encontrado")

    tipo = get_project_type_from_name(p.nombre_pmc)
    order_map = build_category_order_map(tipo) if tipo else {}
    group_order_map = build_group_order_map(tipo) if tipo else {}
    base = Path(p.ruta_base) if p.ruta_base else None

    grupos: dict[str, dict[int, dict]] = {"EDP": {}, "INFORME": {}, "OTROS": {}}
    for c in p.categorias:
        if not c.items:
            continue
        g_name = _infer_group_name(c, base)
        if g_name not in grupos:
            grupos[g_name] = {}
        items_data = [
            modelos.ItemPlantillaSchema.model_validate(i).model_dump() for i in c.items
        ]
        items_data.sort(key=lambda x: nucleo.natural_sort_key(x["nombre"]))
        grupos[g_name][c.id] = {
            "id": c.id,
            "nombre": c.nombre.upper(),
            "proyecto": {"nombre_pmc": p.nombre_pmc},
            "items": items_data,
        }

    def _cat_sort_key(group_name: str, cat: dict):
        key = f"{group_name}/{cat['nombre'].upper()}"
        return (order_map.get(key, 9999), nucleo.natural_sort_key(cat["nombre"]))

    resp = {
        k: sorted(v.values(), key=lambda x, g=k: _cat_sort_key(g, x))
        for k, v in grupos.items()
    }
    grupos_orden = sorted(
        resp.keys(),
        key=lambda g: (group_order_map.get(g, 9999), nucleo.natural_sort_key(g)),
    )
    return {**p.__dict__, "grupos": resp, "grupos_orden": grupos_orden}


def _load_with_categorias(db: Session, proyecto_id: int):
    return (
        db.query(modelos.Proyecto)
        .options(
            selectinload(modelos.Proyecto.categorias).selectinload(
                modelos.Categoria.items
            )
        )
        .filter(modelos.Proyecto.id == proyecto_id)
        .first()
    )


def _infer_group_name(categoria: modelos.Categoria, base: Path | None) -> str:
    """Decide a que grupo pertenece una categoria (EDP/INFORME/OTROS)
    en base a la ruta de su primer item. Fallback heuristico por nombre."""
    if base:
        try:
            rel = Path(categoria.items[0].ruta_item).relative_to(base)
            root_folder = rel.parts[0].upper()
            if root_folder:
                return root_folder
        except Exception:
            pass
    if "INFORME" in categoria.nombre.upper():
        return "INFORME"
    if categoria.nombre and categoria.nombre[0].isdigit():
        return "EDP"
    return "OTROS"


def populate_project_from_template(db: Session, project: modelos.Proyecto, tipo: str):
    template = STRUCTURE_TEMPLATES.get(tipo) or []
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
