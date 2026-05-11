"""Avisos de revisión para tareas cerradas cuando hubo cambios post-cierre.

Modelo:
- Cuando un paso reabierto (por devolución desde paso posterior) se cierra de
  nuevo, comparamos datos_flujo y adjuntos antes/después. Si hubo cambios,
  generamos avisos para los pasos cerrados intermedios + el paso que devolvió.
- El responsable de cada paso afectado ve un banner amarillo en su tarea.
- Puede "marcar como revisado" (cierra el aviso) o devolver nuevamente al
  paso modificado si necesita rehacer su trabajo.

NO confundir con:
- comentarios: notas libres del flujo (gta.comentarios)
- quiebres: deprecated, eliminado en el rediseño
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from plataforma.core import db


def crear_aviso(
    conn,
    *,
    tarea_id: int,
    flujo_id: str,
    por_tarea_id: Optional[int],
    motivo: str,
) -> Dict[str, Any]:
    """Inserta un aviso. Usa la conexión del caller (transaccional)."""
    row = conn.execute(
        """INSERT INTO gta.avisos_revision
               (tarea_id, flujo_id, por_tarea_id, motivo)
           VALUES (%s, %s, %s, %s)
           RETURNING id, tarea_id, flujo_id, por_tarea_id, motivo, created_at""",
        (tarea_id, flujo_id, por_tarea_id, (motivo or "").strip() or None),
    ).fetchone()
    return dict(row)


def listar_pendientes_de_tarea(tarea_id: int) -> List[Dict[str, Any]]:
    """Avisos pendientes (sin revisar) de una tarea específica."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT a.id, a.tarea_id, a.flujo_id, a.por_tarea_id, a.motivo,
                      a.created_at, a.revisado_at, a.revisado_por,
                      t.titulo AS por_tarea_titulo, t.paso_orden AS por_tarea_paso
               FROM gta.avisos_revision a
               LEFT JOIN gta.tareas t ON t.id = a.por_tarea_id
               WHERE a.tarea_id = %s
                 AND a.revisado_at IS NULL
               ORDER BY a.created_at DESC""",
            (tarea_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_de_flujo(flujo_id: str) -> List[Dict[str, Any]]:
    """Todos los avisos de un flujo (pendientes + revisados), con info del paso."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT a.id, a.tarea_id, a.flujo_id, a.por_tarea_id, a.motivo,
                      a.created_at, a.revisado_at,
                      ur.username AS revisado_por_username,
                      t.titulo AS tarea_titulo, t.paso_orden AS tarea_paso,
                      tp.titulo AS por_tarea_titulo, tp.paso_orden AS por_tarea_paso
               FROM gta.avisos_revision a
               LEFT JOIN auth.users ur ON ur.id = a.revisado_por
               LEFT JOIN gta.tareas t ON t.id = a.tarea_id
               LEFT JOIN gta.tareas tp ON tp.id = a.por_tarea_id
               WHERE a.flujo_id = %s
               ORDER BY a.created_at DESC""",
            (flujo_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def marcar_revisado(
    aviso_id: int,
    *,
    revisado_por_id: int,
) -> Dict[str, Any]:
    """Marca un aviso como revisado. Solo se puede marcar una vez."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT id, revisado_at FROM gta.avisos_revision WHERE id = %s""",
            (aviso_id,),
        ).fetchone()
        if not row:
            raise ValueError("aviso no encontrado")
        if row.get("revisado_at"):
            raise ValueError("el aviso ya está revisado")

        updated = conn.execute(
            """UPDATE gta.avisos_revision
               SET revisado_at = CURRENT_TIMESTAMP,
                   revisado_por = %s
               WHERE id = %s
               RETURNING id, tarea_id, revisado_at""",
            (revisado_por_id, aviso_id),
        ).fetchone()
        conn.commit()
        return dict(updated)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def hay_pendientes_en_tarea(conn, tarea_id: int) -> bool:
    """¿La tarea tiene al menos un aviso pendiente? Para badges del listado."""
    row = conn.execute(
        """SELECT 1 FROM gta.avisos_revision
           WHERE tarea_id = %s AND revisado_at IS NULL LIMIT 1""",
        (tarea_id,),
    ).fetchone()
    return bool(row)


def detectar_cambios_y_avisar(
    conn,
    *,
    tarea_cerrada_id: int,
    flujo_id: str,
    paso_orden_cerrado: int,
    paso_orden_origen: Optional[int],
    datos_flujo_antes: Dict[str, Any],
    datos_flujo_despues: Dict[str, Any],
    adjuntos_antes_count: int,
    adjuntos_despues_count: int,
) -> int:
    """Genera avisos solo para los pasos que estuvieron activos entre el
    paso destino (recién cerrado) y el paso origen (la tarea que disparó
    la devolución).

    Ejemplo: si paso 5 devolvió al paso 1, y al cerrar el 1 hay cambios,
    se avisa SOLO a pasos 2, 3, 4 y 5 (los que estuvieron cerrados o
    devueltos en algún momento). NO a 6, 7, 8 — esos están 'bloqueada' y
    nunca vieron datos del flujo.

    Si paso_orden_origen es None (no hubo devolución detectable), se cae
    al comportamiento legacy de avisar a todos los pasos posteriores
    cerrados/devueltos.

    Retorna cantidad de avisos creados. NO commitea (usa la conn del caller).
    """
    motivos = []
    if datos_flujo_antes != datos_flujo_despues:
        # Listar campos que cambiaron
        antes_keys = set(datos_flujo_antes.keys())
        despues_keys = set(datos_flujo_despues.keys())
        cambios = []
        for k in antes_keys | despues_keys:
            if datos_flujo_antes.get(k) != datos_flujo_despues.get(k):
                cambios.append(k)
        if cambios:
            motivos.append(f"cambió datos del flujo: {', '.join(cambios[:5])}")
    if adjuntos_despues_count != adjuntos_antes_count:
        delta = adjuntos_despues_count - adjuntos_antes_count
        if delta > 0:
            motivos.append(f"agregó {delta} adjunto(s)")
        else:
            motivos.append(f"borró {abs(delta)} adjunto(s)")

    if not motivos:
        return 0

    motivo = "; ".join(motivos)

    # Filtro: solo pasos entre destino y origen de la devolución, en estado
    # 'cerrada' o 'devuelta' (los que sí vieron datos en algún momento).
    # Excluye 'bloqueada' (nunca fueron tomadas, no tienen nada que revisar).
    if paso_orden_origen is not None:
        afectadas = conn.execute(
            """SELECT id FROM gta.tareas
               WHERE flujo_id = %s
                 AND paso_orden > %s
                 AND paso_orden <= %s
                 AND estado IN ('cerrada', 'devuelta')""",
            (flujo_id, paso_orden_cerrado, paso_orden_origen),
        ).fetchall()
    else:
        # Fallback legacy: paso_orden > destino, sin tope superior
        afectadas = conn.execute(
            """SELECT id FROM gta.tareas
               WHERE flujo_id = %s
                 AND paso_orden > %s
                 AND estado IN ('cerrada', 'devuelta')""",
            (flujo_id, paso_orden_cerrado),
        ).fetchall()
    count = 0
    for t in afectadas:
        crear_aviso(
            conn,
            tarea_id=t["id"],
            flujo_id=flujo_id,
            por_tarea_id=tarea_cerrada_id,
            motivo=motivo,
        )
        count += 1
    return count
