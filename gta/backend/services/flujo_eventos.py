"""Log cronológico de eventos de un flujo (para timeline del tablero).

Cada acción significativa registra una entry en gta.flujo_eventos. El
tablero arma con esto un timeline visual.

Uso desde otros services:
    from gta.backend.services import flujo_eventos as evt
    evt.registrar(conn, flujo_id, tarea_id=t_id, tipo=evt.TAREA_CERRADA,
                  mensaje="Cerrada por juan", actor="juan")

Pasamos `conn` para que el evento viaje en la misma transacción del
service que lo dispara (si rolleas la transacción, no queda evento).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from plataforma.core import db


# Tipos de evento
FLUJO_INICIADO    = "flujo_iniciado"
TAREA_CERRADA     = "tarea_cerrada"
TAREA_DEVUELTA    = "tarea_devuelta"
TAREA_REABIERTA   = "tarea_reabierta"      # paso destino reabierto tras devolución
QUIEBRE_REPORTADO = "quiebre_reportado"
QUIEBRE_RESUELTO  = "quiebre_resuelto"
FLUJO_COMPLETADO  = "flujo_completado"


def registrar(
    conn,
    flujo_id: str,
    *,
    tipo: str,
    actor: Optional[str] = None,
    tarea_id: Optional[int] = None,
    mensaje: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Inserta un evento en el timeline del flujo. Usa la conexión recibida
    (no abre una nueva) para que viaje en la transacción del caller."""
    conn.execute(
        """INSERT INTO gta.flujo_eventos
               (flujo_id, tarea_id, tipo, mensaje, actor, metadata)
           VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
        (
            flujo_id,
            tarea_id,
            tipo,
            (mensaje or "").strip() or None,
            actor,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def listar_de_flujo(flujo_id: str, *, limit: int = 200) -> list:
    """Devuelve eventos del flujo en orden cronológico ASC (viejos primero)."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT e.id, e.flujo_id, e.tarea_id, e.tipo, e.mensaje,
                      e.actor, e.metadata, e.created_at,
                      t.titulo AS tarea_titulo, t.paso_orden
               FROM gta.flujo_eventos e
               LEFT JOIN gta.tareas t ON t.id = e.tarea_id
               WHERE e.flujo_id = %s
               ORDER BY e.created_at ASC, e.id ASC
               LIMIT %s""",
            (flujo_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
