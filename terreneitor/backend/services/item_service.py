"""Servicios para operaciones sobre Item (tareas)."""

import glob
import os
import re
from pathlib import Path

from sqlalchemy.orm import Session, selectinload

from terreneitor.backend import modelos


def create_item_in_category(
    db: Session, categoria_id: int, nombre_raw: str
) -> tuple[str, modelos.Item]:
    """Crea un item nuevo en una categoria, incluyendo su carpeta fisica.

    Si ya existe un item con el mismo nombre normalizado, retorna el existente.

    Retorna ("ok"|"exists", Item).

    Excepciones:
        ValueError("Nombre invalido") si nombre_raw es vacio o solo
            caracteres invalidos.
        LookupError si la categoria no existe.
        ValueError("Proyecto sin ruta") si el proyecto no tiene ruta_base.
        ValueError("Categoria sin ruta base") si no se puede inferir el
            directorio padre del item.
        OSError si falla la creacion del directorio fisico.
    """
    nombre_raw = (nombre_raw or "").strip()
    if not nombre_raw:
        raise ValueError("Nombre invalido")

    cat = (
        db.query(modelos.Categoria)
        .options(
            selectinload(modelos.Categoria.items),
            selectinload(modelos.Categoria.proyecto),
        )
        .filter(modelos.Categoria.id == categoria_id)
        .first()
    )
    if not cat:
        raise LookupError("Categoria no encontrada")
    proyecto = cat.proyecto
    if not proyecto or not proyecto.ruta_base:
        raise ValueError("Proyecto sin ruta")

    safe_name = re.sub(r"[^A-Za-z0-9 _\-\.]", "", nombre_raw)
    safe_name = re.sub(r"\s+", " ", safe_name).strip()
    if not safe_name:
        raise ValueError("Nombre invalido")
    item_name = safe_name.upper()

    existing = (
        db.query(modelos.Item)
        .filter(modelos.Item.categoria_id == cat.id, modelos.Item.nombre == item_name)
        .first()
    )
    if existing:
        return "exists", existing

    base_dir = None
    if cat.items:
        base_dir = Path(cat.items[0].ruta_item).parent
    else:
        matches = glob.glob(os.path.join(proyecto.ruta_base, "*", cat.nombre))
        if matches:
            base_dir = Path(matches[0])
    if not base_dir:
        raise ValueError("Categoria sin ruta base")

    item_path = base_dir / item_name
    os.makedirs(item_path, exist_ok=True, mode=0o775)

    item = modelos.Item(nombre=item_name, ruta_item=str(item_path), categoria_id=cat.id)
    db.add(item)
    db.commit()
    db.refresh(item)
    return "ok", item
