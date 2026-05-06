"""Servicio de tareas.

Modelo: una tarea pertenece a una subárea (no a una persona). La asignación
se versiona en gta.tarea_participaciones — un único responsable vigente +
N co-responsables/ayudas vigentes.

Vistas principales:
- bandeja_subarea: tareas de una subárea sin responsable vigente (esperan
  ser tomadas).
- mis_tareas: tareas donde soy responsable vigente.
- donde_colaboro: tareas donde tengo participación vigente como
  co_responsable o ayuda (no responsable).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from plataforma.core import db
from gta.backend.services import membresias as membresias_service


# ── Helpers ─────────────────────────────────────────────────────────────

def usuario_id_de_username(username: str) -> int:
    """Resuelve username → id en auth.users. Lanza ValueError si no existe."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM auth.users WHERE username = %s",
            (username,),
        ).fetchone()
        if not row:
            raise ValueError(f"usuario no encontrado: {username}")
        return int(row["id"])
    finally:
        conn.close()


def _serialize_tarea(row: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(row)
    raw_tags = t.get("tags")
    if isinstance(raw_tags, str):
        try:
            t["tags"] = json.loads(raw_tags)
        except Exception:
            t["tags"] = []
    elif raw_tags is None:
        t["tags"] = []
    return t


def _attach_participaciones(conn, tarea: Dict[str, Any]) -> Dict[str, Any]:
    """Agrega responsable_actual + colaboradores_actuales + historial."""
    rows = conn.execute(
        """SELECT p.id, p.usuario_id, p.rol, p.desde, p.hasta, p.motivo,
                  u.username
           FROM gta.tarea_participaciones p
           JOIN auth.users u ON u.id = p.usuario_id
           WHERE p.tarea_id = %s
           ORDER BY p.desde DESC""",
        (tarea["id"],),
    ).fetchall()
    todas = [dict(r) for r in rows]
    vigentes = [p for p in todas if p["hasta"] is None]
    responsable = next((p for p in vigentes if p["rol"] == "responsable"), None)
    colaboradores = [p for p in vigentes if p["rol"] != "responsable"]
    tarea["responsable_actual"] = responsable
    tarea["colaboradores_actuales"] = colaboradores
    tarea["historial_participaciones"] = todas
    return tarea


# ── Crear / cerrar ──────────────────────────────────────────────────────

def crear_tarea(
    *,
    subarea_id: int,
    titulo: str,
    descripcion: Optional[str],
    creado_por: int,
    proceso_id: Optional[int] = None,
    flujo_tarea_id: Optional[int] = None,
    tipo: Optional[str] = None,
    prioridad: str = "media",
    sla_horas: Optional[int] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not titulo.strip():
        raise ValueError("titulo es requerido")
    if prioridad not in ("baja", "media", "alta", "urgente"):
        raise ValueError("prioridad inválida")

    conn = db.get_conn()
    try:
        sla_due = None
        if sla_horas and sla_horas > 0:
            row = conn.execute(
                "SELECT CURRENT_TIMESTAMP + (%s || ' hours')::interval AS due",
                (str(sla_horas),),
            ).fetchone()
            sla_due = row["due"]

        row = conn.execute(
            """INSERT INTO gta.tareas
               (subarea_id, proceso_id, flujo_tarea_id, titulo, descripcion,
                tipo, prioridad, sla_horas, sla_due_at, creado_por, tags)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                subarea_id, proceso_id, flujo_tarea_id, titulo.strip(),
                descripcion, tipo, prioridad, sla_horas, sla_due, creado_por,
                json.dumps(tags or [], ensure_ascii=False),
            ),
        ).fetchone()
        conn.commit()
        return get_tarea(int(row["id"]))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cerrar_tarea(tarea_id: int, *, cerrado_por: int, reporte: Optional[str] = None) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        # Cerrar todas las participaciones vigentes
        conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND hasta IS NULL""",
            (tarea_id,),
        )
        result = conn.execute(
            """UPDATE gta.tareas
               SET estado = 'cerrada',
                   cerrado_por = %s,
                   cerrado_at = CURRENT_TIMESTAMP,
                   reporte_cierre = %s,
                   fecha_fin = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s AND estado <> 'cerrada'
               RETURNING id""",
            (cerrado_por, reporte, tarea_id),
        ).fetchone()
        conn.commit()
        if not result:
            raise ValueError("tarea no encontrada o ya cerrada")
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Detalle ─────────────────────────────────────────────────────────────

def get_tarea(tarea_id: int) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT t.*,
                      s.code AS subarea_code, s.label AS subarea_label,
                      s.area_code,
                      a.label AS area_label,
                      uc.username AS creado_por_username
               FROM gta.tareas t
               JOIN gta.subareas s ON s.id = t.subarea_id
               JOIN gta.areas a ON a.code = s.area_code
               JOIN auth.users uc ON uc.id = t.creado_por
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not row:
            return {}
        tarea = _serialize_tarea(row)
        return _attach_participaciones(conn, tarea)
    finally:
        conn.close()


# ── Asignación / participaciones ────────────────────────────────────────

def tomar_tarea(tarea_id: int, *, usuario_id: int) -> Dict[str, Any]:
    """Auto-asignación: el usuario se vuelve responsable.

    Requiere que la tarea esté vigente, sin responsable activo, y que el
    usuario sea miembro vigente de la subárea de la tarea.
    """
    conn = db.get_conn()
    try:
        tarea_row = conn.execute(
            "SELECT id, subarea_id, estado FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea_row:
            raise ValueError("tarea no encontrada")
        if tarea_row["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")

        es_miembro = conn.execute(
            """SELECT 1 FROM gta.area_membresias
               WHERE usuario_id = %s AND subarea_id = %s AND hasta IS NULL""",
            (usuario_id, tarea_row["subarea_id"]),
        ).fetchone()
        if not es_miembro:
            raise ValueError("no sos miembro vigente de la subárea de esta tarea")

        ya_responsable = conn.execute(
            """SELECT usuario_id FROM gta.tarea_participaciones
               WHERE tarea_id = %s AND rol = 'responsable' AND hasta IS NULL""",
            (tarea_id,),
        ).fetchone()
        if ya_responsable:
            raise ValueError("la tarea ya tiene un responsable vigente")

        conn.execute(
            """INSERT INTO gta.tarea_participaciones
               (tarea_id, usuario_id, rol, asignado_por)
               VALUES (%s, %s, 'responsable', %s)""",
            (tarea_id, usuario_id, usuario_id),
        )
        conn.execute(
            """UPDATE gta.tareas
               SET estado = CASE WHEN estado = 'pendiente' THEN 'en_curso' ELSE estado END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def liberar_tarea(tarea_id: int, *, usuario_id: int, motivo: Optional[str] = None) -> Dict[str, Any]:
    """El responsable vigente libera la tarea — vuelve a la bandeja."""
    conn = db.get_conn()
    try:
        result = conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP,
                   motivo = COALESCE(%s, motivo)
               WHERE tarea_id = %s AND usuario_id = %s
                 AND rol = 'responsable' AND hasta IS NULL
               RETURNING id""",
            (motivo, tarea_id, usuario_id),
        ).fetchone()
        if not result:
            raise ValueError("no sos el responsable vigente de esta tarea")
        conn.execute(
            """UPDATE gta.tareas
               SET estado = CASE WHEN estado = 'en_curso' THEN 'pendiente' ELSE estado END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reasignar_responsable(
    tarea_id: int,
    *,
    nuevo_usuario_id: int,
    asignado_por: int,
    motivo: Optional[str] = None,
) -> Dict[str, Any]:
    """Cambia el responsable. Cierra el actual (si hay) y abre uno nuevo.

    No exige que asignado_por sea líder — el endpoint decide quién puede.
    """
    conn = db.get_conn()
    try:
        tarea_row = conn.execute(
            "SELECT id, subarea_id, estado FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea_row:
            raise ValueError("tarea no encontrada")
        if tarea_row["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")

        es_miembro = conn.execute(
            """SELECT 1 FROM gta.area_membresias
               WHERE usuario_id = %s AND subarea_id = %s AND hasta IS NULL""",
            (nuevo_usuario_id, tarea_row["subarea_id"]),
        ).fetchone()
        if not es_miembro:
            raise ValueError("el nuevo responsable no es miembro vigente de la subárea")

        conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND rol = 'responsable' AND hasta IS NULL""",
            (tarea_id,),
        )
        conn.execute(
            """INSERT INTO gta.tarea_participaciones
               (tarea_id, usuario_id, rol, asignado_por, motivo)
               VALUES (%s, %s, 'responsable', %s, %s)""",
            (tarea_id, nuevo_usuario_id, asignado_por, motivo),
        )
        conn.execute(
            """UPDATE gta.tareas
               SET estado = CASE WHEN estado = 'pendiente' THEN 'en_curso' ELSE estado END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def agregar_colaborador(
    tarea_id: int,
    *,
    usuario_id: int,
    rol: str,
    asignado_por: int,
    motivo: Optional[str] = None,
) -> Dict[str, Any]:
    """Agrega un co-responsable o ayuda. No toca al responsable vigente.

    rol: 'co_responsable' | 'ayuda'
    """
    if rol not in ("co_responsable", "ayuda"):
        raise ValueError("rol debe ser 'co_responsable' o 'ayuda'")

    conn = db.get_conn()
    try:
        tarea_row = conn.execute(
            "SELECT id, estado FROM gta.tareas WHERE id = %s", (tarea_id,),
        ).fetchone()
        if not tarea_row:
            raise ValueError("tarea no encontrada")
        if tarea_row["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")

        # Si ya tiene una participación vigente con ese rol, no duplicar
        ya = conn.execute(
            """SELECT 1 FROM gta.tarea_participaciones
               WHERE tarea_id = %s AND usuario_id = %s AND rol = %s AND hasta IS NULL""",
            (tarea_id, usuario_id, rol),
        ).fetchone()
        if ya:
            raise ValueError("ese usuario ya participa con ese rol")

        conn.execute(
            """INSERT INTO gta.tarea_participaciones
               (tarea_id, usuario_id, rol, asignado_por, motivo)
               VALUES (%s, %s, %s, %s, %s)""",
            (tarea_id, usuario_id, rol, asignado_por, motivo),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def quitar_colaborador(
    tarea_id: int, *, usuario_id: int, rol: str
) -> Dict[str, Any]:
    """Cierra una participación de co-responsable / ayuda vigente."""
    if rol not in ("co_responsable", "ayuda"):
        raise ValueError("rol inválido para quitar colaborador")
    conn = db.get_conn()
    try:
        result = conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND usuario_id = %s AND rol = %s
                 AND hasta IS NULL
               RETURNING id""",
            (tarea_id, usuario_id, rol),
        ).fetchone()
        conn.commit()
        if not result:
            raise ValueError("no se encontró participación vigente")
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Listados / vistas ──────────────────────────────────────────────────

_BASE_SELECT = """
    SELECT t.id, t.subarea_id, t.proceso_id, t.flujo_tarea_id,
           t.titulo, t.descripcion, t.tipo, t.prioridad, t.estado,
           t.sla_horas, t.sla_due_at, t.fecha_inicio, t.fecha_fin,
           t.creado_por, t.cerrado_por, t.cerrado_at, t.tags,
           t.created_at, t.updated_at,
           s.code AS subarea_code, s.label AS subarea_label,
           s.area_code,
           a.label AS area_label,
           gta.responsable_vigente(t.id) AS responsable_id,
           ur.username AS responsable_username
    FROM gta.tareas t
    JOIN gta.subareas s ON s.id = t.subarea_id
    JOIN gta.areas a ON a.code = s.area_code
    LEFT JOIN auth.users ur ON ur.id = gta.responsable_vigente(t.id)
"""


def listar_bandeja_subarea(subarea_id: int) -> List[Dict[str, Any]]:
    """Tareas de una subárea sin responsable vigente y no cerradas."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            _BASE_SELECT + """
            WHERE t.subarea_id = %s
              AND t.estado NOT IN ('cerrada', 'cancelada')
              AND gta.responsable_vigente(t.id) IS NULL
            ORDER BY
              CASE t.prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1
                               WHEN 'media' THEN 2 ELSE 3 END,
              t.created_at DESC
            """,
            (subarea_id,),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_bandeja_de_usuario(usuario_id: int) -> List[Dict[str, Any]]:
    """Bandejas combinadas de todas las subáreas del usuario."""
    sub_ids = membresias_service.subarea_ids_de_usuario(usuario_id)
    if not sub_ids:
        return []
    conn = db.get_conn()
    try:
        placeholders = ",".join(["%s"] * len(sub_ids))
        rows = conn.execute(
            _BASE_SELECT + f"""
            WHERE t.subarea_id IN ({placeholders})
              AND t.estado NOT IN ('cerrada', 'cancelada')
              AND gta.responsable_vigente(t.id) IS NULL
            ORDER BY
              CASE t.prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1
                               WHEN 'media' THEN 2 ELSE 3 END,
              t.created_at DESC
            """,
            tuple(sub_ids),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_mis_tareas(usuario_id: int, *, incluir_cerradas: bool = False) -> List[Dict[str, Any]]:
    """Tareas donde el usuario es responsable vigente."""
    conn = db.get_conn()
    try:
        where_estado = "" if incluir_cerradas else "AND t.estado NOT IN ('cerrada', 'cancelada')"
        rows = conn.execute(
            _BASE_SELECT + f"""
            JOIN gta.tarea_participaciones p
              ON p.tarea_id = t.id AND p.rol = 'responsable' AND p.hasta IS NULL
            WHERE p.usuario_id = %s
              {where_estado}
            ORDER BY
              CASE t.prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1
                               WHEN 'media' THEN 2 ELSE 3 END,
              t.sla_due_at NULLS LAST, t.created_at DESC
            """,
            (usuario_id,),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_donde_colaboro(usuario_id: int, *, incluir_cerradas: bool = False) -> List[Dict[str, Any]]:
    """Tareas donde el usuario es co-responsable o ayuda (vigente)."""
    conn = db.get_conn()
    try:
        where_estado = "" if incluir_cerradas else "AND t.estado NOT IN ('cerrada', 'cancelada')"
        rows = conn.execute(
            _BASE_SELECT + f"""
            JOIN gta.tarea_participaciones p
              ON p.tarea_id = t.id AND p.hasta IS NULL
            WHERE p.usuario_id = %s
              AND p.rol IN ('co_responsable', 'ayuda')
              {where_estado}
            ORDER BY t.created_at DESC
            """,
            (usuario_id,),
        ).fetchall()
        # Adjuntar el rol con el que participa
        out = []
        for r in rows:
            t = _serialize_tarea(r)
            out.append(t)
        return out
    finally:
        conn.close()


def listar_todas_subarea(subarea_id: int) -> List[Dict[str, Any]]:
    """Todas las tareas de una subárea (admin / vista de líder)."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            _BASE_SELECT + """
            WHERE t.subarea_id = %s
            ORDER BY
              CASE t.estado WHEN 'pendiente' THEN 0 WHEN 'en_curso' THEN 1
                            WHEN 'bloqueada' THEN 2 ELSE 3 END,
              t.created_at DESC
            """,
            (subarea_id,),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()
