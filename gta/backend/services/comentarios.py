"""Comentarios libres a nivel del flujo.

Modelo: gta.comentarios ya existe (tarea_id, autor, texto, created_at).
Aprovechamos esa tabla. Los comentarios se guardan asociados a la tarea
desde la cual se postean, pero al listar se devuelven TODOS los comentarios
de cualquier tarea del mismo flujo (visibilidad compartida).

Casos cubiertos:
- Comentarios libres de cualquier responsable mientras avanza el flujo
  (notas, contexto, "ojo con esto", etc.).
- Sigue funcionando el comentario de devolución que ya generaba el service
  de tareas (formato "[Devuelto desde paso X] motivo") — esos también se
  ven al listar comentarios del flujo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from plataforma.core import db


def listar_de_flujo(flujo_id: str) -> List[Dict[str, Any]]:
    """Comentarios de cualquier tarea del flujo, ordenados cronológicamente."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT c.id, c.tarea_id, c.autor, c.texto, c.created_at,
                      t.paso_orden, t.titulo AS tarea_titulo
               FROM gta.comentarios c
               JOIN gta.tareas t ON t.id = c.tarea_id
               WHERE t.flujo_id = %s
               ORDER BY c.created_at ASC""",
            (flujo_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_de_tarea(tarea_id: int) -> List[Dict[str, Any]]:
    """Comentarios del flujo al que pertenece la tarea (no solo de la tarea)."""
    conn = db.get_conn()
    try:
        flujo_row = conn.execute(
            "SELECT flujo_id FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not flujo_row:
            raise ValueError("tarea no encontrada")
        flujo_id = flujo_row.get("flujo_id")
        if not flujo_id:
            # Tarea suelta: solo los suyos
            rows = conn.execute(
                """SELECT id, tarea_id, autor, texto, created_at
                   FROM gta.comentarios
                   WHERE tarea_id = %s
                   ORDER BY created_at ASC""",
                (tarea_id,),
            ).fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()
    return listar_de_flujo(flujo_id)


def crear(
    *,
    tarea_id: int,
    autor: str,
    texto: str,
) -> Dict[str, Any]:
    texto_clean = (texto or "").strip()
    if not texto_clean:
        raise ValueError("El comentario no puede estar vacío")
    if len(texto_clean) > 5000:
        raise ValueError("El comentario es demasiado largo (máximo 5000 caracteres)")

    conn = db.get_conn()
    try:
        existe = conn.execute(
            "SELECT 1 FROM gta.tareas WHERE id = %s", (tarea_id,),
        ).fetchone()
        if not existe:
            raise ValueError("tarea no encontrada")

        row = conn.execute(
            """INSERT INTO gta.comentarios (tarea_id, autor, texto, created_at)
               VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
               RETURNING id, tarea_id, autor, texto, created_at""",
            (tarea_id, autor, texto_clean),
        ).fetchone()
        conn.commit()
        return dict(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def borrar(comentario_id: int, *, autor_actor: str, es_admin: bool = False) -> None:
    """Borra un comentario. Solo el autor o un admin."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id, autor FROM gta.comentarios WHERE id = %s",
            (comentario_id,),
        ).fetchone()
        if not row:
            raise ValueError("comentario no encontrado")
        if not es_admin and row.get("autor") != autor_actor:
            raise ValueError("solo el autor (o un admin) puede borrar el comentario")
        conn.execute("DELETE FROM gta.comentarios WHERE id = %s", (comentario_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
