"""Servicio de adjuntos del flujo.

Los adjuntos son DEL FLUJO (no de una tarea individual): cualquier responsable
de cualquier paso puede subir/ver/borrar (con permisos) los archivos. La PTE
que cargó comercial en el paso 1 la ve el validador del paso 2, y compras ve
la cotización del paso 3 sin tener que pedirla.

Almacenamiento físico: gta/data/flujos/<flujo_id>/<filename>
Tabla:                 gta.flujo_adjuntos
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from plataforma.core import db


ALLOWED_UPLOAD_EXT = {
    ".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls",
    ".txt", ".md", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".zip", ".7z",
    ".eml", ".msg",
}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def _data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.\- ]", "_", name)
    return safe.strip()[:200] or "archivo"


def _flujo_id_de_tarea(tarea_id: int) -> Optional[str]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT flujo_id FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not row:
            raise ValueError("tarea no encontrada")
        return row.get("flujo_id")
    finally:
        conn.close()


def listar_adjuntos_flujo(flujo_id: str) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT a.id, a.flujo_id, a.filename, a.ruta, a.mime, a.size_bytes,
                      a.subido_por, a.created_at,
                      u.username AS subido_por_username
               FROM gta.flujo_adjuntos a
               LEFT JOIN auth.users u ON u.id = a.subido_por
               WHERE a.flujo_id = %s
               ORDER BY a.created_at DESC""",
            (flujo_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_adjuntos_tarea(tarea_id: int) -> List[Dict[str, Any]]:
    """Lista adjuntos del flujo al que pertenece la tarea. Si la tarea no
    pertenece a un flujo (tarea suelta), devuelve vacío por ahora."""
    flujo_id = _flujo_id_de_tarea(tarea_id)
    if not flujo_id:
        return []
    return listar_adjuntos_flujo(flujo_id)


def subir_adjunto(
    *,
    tarea_id: int,
    filename: str,
    contenido: bytes,
    mime: Optional[str],
    subido_por: int,
) -> Dict[str, Any]:
    """Guarda el archivo en gta/data/flujos/<flujo_id>/ y registra en DB."""
    if not contenido:
        raise ValueError("archivo vacío")
    if len(contenido) > MAX_UPLOAD_BYTES:
        raise ValueError(f"archivo supera el máximo permitido ({MAX_UPLOAD_BYTES // (1024*1024)} MB)")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise ValueError(f"extensión no permitida: {ext}")

    flujo_id = _flujo_id_de_tarea(tarea_id)
    if not flujo_id:
        raise ValueError("la tarea no pertenece a un flujo, no admite adjuntos compartidos")

    safe_name = _sanitize_filename(filename)
    target_dir = _data_root() / "flujos" / str(flujo_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / safe_name
    if target.exists():
        stem = target.stem
        idx = 1
        while target.exists():
            target = target_dir / f"{stem}_{idx}{ext}"
            idx += 1

    target.write_bytes(contenido)
    rel_path = target.relative_to(_data_root()).as_posix()

    conn = db.get_conn()
    try:
        row = conn.execute(
            """INSERT INTO gta.flujo_adjuntos
                   (flujo_id, filename, ruta, mime, size_bytes, subido_por)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, flujo_id, filename, ruta, mime, size_bytes,
                         subido_por, created_at""",
            (flujo_id, target.name, rel_path, mime, len(contenido), subido_por),
        ).fetchone()
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        # Si falla la DB, también borramos el archivo recién escrito
        try:
            target.unlink()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def eliminar_adjunto(
    adjunto_id: int,
    *,
    actor_id: int,
    es_admin: bool = False,
) -> None:
    """Borra el registro y el archivo físico. Solo el que subió o un admin."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id, ruta, subido_por FROM gta.flujo_adjuntos WHERE id = %s",
            (adjunto_id,),
        ).fetchone()
        if not row:
            raise ValueError("adjunto no encontrado")
        if not es_admin and row.get("subido_por") != actor_id:
            raise ValueError("solo el que subió el adjunto (o un admin) puede borrarlo")

        conn.execute("DELETE FROM gta.flujo_adjuntos WHERE id = %s", (adjunto_id,))
        conn.commit()

        # Borrar archivo físico (si falla, el commit ya está hecho — se loggea pero no rompe)
        try:
            full = _data_root() / row["ruta"]
            if full.exists():
                full.unlink()
        except Exception:
            pass
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_adjunto(adjunto_id: int) -> Optional[Dict[str, Any]]:
    """Devuelve metadata de un adjunto (para descarga)."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id, flujo_id, filename, ruta, mime, size_bytes FROM gta.flujo_adjuntos WHERE id = %s",
            (adjunto_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def ruta_absoluta(ruta_relativa: str) -> Path:
    """Convierte la ruta relativa de DB en absoluta del filesystem."""
    return _data_root() / ruta_relativa
