"""Servicio de quiebres dirigidos desde una tarea de un flujo.

Modelo: cuando un responsable necesita info/acción de OTRA área para poder
seguir, abre un quiebre. El quiebre queda dirigido a un área específica del
flujo. La tarea origen pasa a estado 'esperando_quiebre' (bloqueada por
quiebre, distinto del 'bloqueada' por dependencias de pasos). Al resolverse
el quiebre, la tarea origen retoma su estado previo.

NO confundir con la 'devolución' del paso de validación: aquella REABRE el
paso destino y rebota el flujo; ésta solo PIDE algo a otra área sin romper
el camino normal.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from plataforma.core import db


def _areas_del_flujo(conn, flujo_id: str) -> List[Dict[str, Any]]:
    """Devuelve las áreas (con label) que participan en el flujo, leyendo
    pasos_definicion del proceso. Útil para limitar el dropdown de destinos.
    """
    proc = conn.execute(
        """SELECT p.pasos_definicion
           FROM gta.tareas t
           JOIN gta.procesos p ON p.id = t.proceso_id
           WHERE t.flujo_id = %s
           LIMIT 1""",
        (flujo_id,),
    ).fetchone()
    if not proc:
        return []
    try:
        pasos = json.loads(proc.get("pasos_definicion") or "[]") or []
    except Exception:
        pasos = []
    codes = sorted({p.get("area_code") for p in pasos if isinstance(p, dict) and p.get("area_code")})
    if not codes:
        return []
    placeholders = ",".join(["%s"] * len(codes))
    rows = conn.execute(
        f"SELECT code, label FROM gta.areas WHERE code IN ({placeholders}) ORDER BY orden, label",
        tuple(codes),
    ).fetchall()
    return [dict(r) for r in rows]


def areas_disponibles_para_quiebre(tarea_id: int) -> List[Dict[str, Any]]:
    """Áreas del flujo disponibles como destino de un quiebre desde esta tarea.
    Excluye el área de la propia tarea (no tiene sentido reportarse a uno mismo).
    """
    conn = db.get_conn()
    try:
        ctx = conn.execute(
            """SELECT t.flujo_id, s.area_code AS area_propia
               FROM gta.tareas t
               JOIN gta.subareas s ON s.id = t.subarea_id
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not ctx or not ctx.get("flujo_id"):
            return []
        areas = _areas_del_flujo(conn, ctx["flujo_id"])
        return [a for a in areas if a["code"] != ctx.get("area_propia")]
    finally:
        conn.close()


def reportar_desde_tarea(
    *,
    tarea_id: int,
    area_destino: str,
    descripcion: str,
    tipo: Optional[str] = None,
    reportado_por: str,
) -> Dict[str, Any]:
    """Crea un quiebre dirigido a `area_destino`, vinculado a la tarea, y
    bloquea la tarea origen guardando su estado previo en el quiebre."""
    desc_clean = (descripcion or "").strip()
    if not desc_clean:
        raise ValueError("La descripción es obligatoria")
    if not area_destino:
        raise ValueError("El área destino es obligatoria")

    conn = db.get_conn()
    try:
        ctx = conn.execute(
            """SELECT t.id, t.estado, t.flujo_id, t.proceso_id, s.area_code
               FROM gta.tareas t
               JOIN gta.subareas s ON s.id = t.subarea_id
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not ctx:
            raise ValueError("tarea no encontrada")
        if ctx["estado"] in ("cerrada", "cancelada", "devuelta", "esperando_quiebre"):
            raise ValueError(f"no se puede reportar quiebre en una tarea {ctx['estado']}")
        if not ctx.get("flujo_id"):
            raise ValueError("solo tareas de un flujo pueden reportar quiebres a otras áreas")
        if area_destino == ctx.get("area_code"):
            raise ValueError("no podés reportar un quiebre a tu propia área")

        # Validar que el área destino exista
        area_row = conn.execute(
            "SELECT 1 FROM gta.areas WHERE code = %s",
            (area_destino,),
        ).fetchone()
        if not area_row:
            raise ValueError(f"área destino no existe: {area_destino}")

        estado_previo = ctx["estado"]

        # Crear quiebre
        q = conn.execute(
            """INSERT INTO gta.quiebres
                   (descripcion, area, tipo, reportado_por,
                    tarea_id, tarea_estado_previo, proceso_id, estado)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'abierto')
               RETURNING id, descripcion, area, tipo, reportado_por,
                         tarea_id, tarea_estado_previo, estado, created_at""",
            (
                desc_clean, area_destino, tipo or "tarea",
                reportado_por, tarea_id, estado_previo, ctx.get("proceso_id"),
            ),
        ).fetchone()

        # Bloquear la tarea origen
        conn.execute(
            """UPDATE gta.tareas
               SET estado = 'esperando_quiebre',
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )

        conn.commit()
        return dict(q)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_de_flujo(flujo_id: str) -> List[Dict[str, Any]]:
    """Todos los quiebres de cualquier tarea de este flujo (abiertos y resueltos)."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT q.id, q.descripcion, q.area, q.tipo, q.estado,
                      q.reportado_por, q.created_at,
                      q.nota_resolucion, q.resuelto_por, q.resuelto_at,
                      q.tarea_id, q.tarea_estado_previo,
                      a.label AS area_label,
                      t.titulo AS tarea_titulo, t.paso_orden
               FROM gta.quiebres q
               LEFT JOIN gta.areas a ON a.code = q.area
               LEFT JOIN gta.tareas t ON t.id = q.tarea_id
               WHERE q.tarea_id IN (SELECT id FROM gta.tareas WHERE flujo_id = %s)
               ORDER BY q.created_at DESC""",
            (flujo_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_de_tarea(tarea_id: int) -> List[Dict[str, Any]]:
    """Quiebres del flujo al que pertenece la tarea (no solo de la tarea individual)."""
    conn = db.get_conn()
    try:
        flujo_row = conn.execute(
            "SELECT flujo_id FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not flujo_row or not flujo_row.get("flujo_id"):
            return []
        return listar_de_flujo(flujo_row["flujo_id"])
    finally:
        conn.close()


def listar_pendientes_para_areas(
    area_codes: List[str],
    *,
    todos: bool = False,
) -> List[Dict[str, Any]]:
    """Quiebres abiertos vinculados a una tarea.

    - Si todos=True: devuelve todos los abiertos (útil para admin).
    - Si todos=False: filtra por las áreas del usuario.

    Los quiebres del modelo viejo atados solo a solicitud_id quedan fuera.
    """
    if not todos and not area_codes:
        return []
    conn = db.get_conn()
    try:
        base_sql = """
            SELECT q.id, q.descripcion, q.area, q.tipo, q.estado,
                   q.reportado_por, q.created_at,
                   q.tarea_id, q.tarea_estado_previo, q.proceso_id,
                   a.label AS area_label,
                   t.titulo AS tarea_titulo, t.paso_orden, t.flujo_id,
                   t.flujo_titulo,
                   p.nombre AS proceso_nombre
            FROM gta.quiebres q
            LEFT JOIN gta.areas a ON a.code = q.area
            LEFT JOIN gta.tareas t ON t.id = q.tarea_id
            LEFT JOIN gta.procesos p ON p.id = q.proceso_id
            WHERE q.estado = 'abierto'
              AND q.tarea_id IS NOT NULL
        """
        if todos:
            rows = conn.execute(
                base_sql + " ORDER BY q.created_at ASC"
            ).fetchall()
        else:
            placeholders = ",".join(["%s"] * len(area_codes))
            rows = conn.execute(
                base_sql + f" AND q.area IN ({placeholders}) ORDER BY q.created_at ASC",
                tuple(area_codes),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resolver(
    quiebre_id: int,
    *,
    nota: Optional[str],
    resuelto_por: str,
) -> Dict[str, Any]:
    """Marca el quiebre como resuelto. Si está vinculado a una tarea, restaura
    el estado previo de la tarea (sale del 'esperando_quiebre')."""
    conn = db.get_conn()
    try:
        q = conn.execute(
            """SELECT id, estado, tarea_id, tarea_estado_previo
               FROM gta.quiebres WHERE id = %s""",
            (quiebre_id,),
        ).fetchone()
        if not q:
            raise ValueError("quiebre no encontrado")
        if q["estado"] != "abierto":
            raise ValueError(f"el quiebre ya está {q['estado']}")

        conn.execute(
            """UPDATE gta.quiebres
               SET estado = 'resuelto',
                   nota_resolucion = %s,
                   resuelto_por = %s,
                   resuelto_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            ((nota or "").strip() or None, resuelto_por, quiebre_id),
        )

        # Si está vinculado a una tarea, restaurar su estado previo
        # (a menos que ya esté en otro estado por algún motivo, en cuyo caso no tocamos)
        if q.get("tarea_id"):
            previo = q.get("tarea_estado_previo") or "en_curso"
            conn.execute(
                """UPDATE gta.tareas
                   SET estado = %s,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = %s AND estado = 'esperando_quiebre'""",
                (previo, q["tarea_id"]),
            )

        conn.commit()
        return {"ok": True, "id": quiebre_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get(quiebre_id: int) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT q.*, a.label AS area_label,
                      t.titulo AS tarea_titulo, t.paso_orden, t.flujo_id, t.flujo_titulo
               FROM gta.quiebres q
               LEFT JOIN gta.areas a ON a.code = q.area
               LEFT JOIN gta.tareas t ON t.id = q.tarea_id
               WHERE q.id = %s""",
            (quiebre_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
