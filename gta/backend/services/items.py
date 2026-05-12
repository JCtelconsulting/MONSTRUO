"""Items (checklist) dentro de un paso del proceso.

Modelo:
- En la plantilla del proceso (gta.procesos.pasos_definicion) cada paso
  puede tener un array opcional `items`:
    [
      { "id": "equipos_redes", "titulo": "...",
        "requerido_para_cerrar": true,
        "desbloquea_pasos": [9] },
      ...
    ]
- En runtime, cada gta.tareas trackea el tickeo en la columna items_estado:
    { "equipos_redes": { "tickeado": true, "tickeado_por_id": 25,
                         "tickeado_at": "2026-..." } }

Comportamiento:
- Tickear un item con desbloquea_pasos != []: para cada paso_orden ahí,
  buscar la tarea del mismo flujo y, si está 'bloqueada', pasarla a
  'pendiente' (desbloqueo directo, sin esperar al cierre completo).
- Destickear: NO re-bloquea los pasos ya desbloqueados (sería confuso si
  ya alguien los tomó). Solo se marca como no tickeado.
- Al cerrar la tarea (cerrar_tarea): si algún item con
  requerido_para_cerrar=true no está tickeado, rechazar el cierre.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from plataforma.core import db


def get_items_definicion_de_tarea(conn, tarea_id: int) -> List[Dict[str, Any]]:
    """Lee los items definidos en la plantilla del proceso para el paso de
    esta tarea. Devuelve [] si la tarea no tiene proceso/paso o si el paso
    no define items."""
    row = conn.execute(
        """SELECT t.paso_orden, p.pasos_definicion
           FROM gta.tareas t
           LEFT JOIN gta.procesos p ON p.id = t.proceso_id
           WHERE t.id = %s""",
        (tarea_id,),
    ).fetchone()
    if not row or not row.get("paso_orden"):
        return []
    try:
        pasos = json.loads(row.get("pasos_definicion") or "[]") or []
    except Exception:
        return []
    paso_def = next(
        (p for p in pasos if isinstance(p, dict) and p.get("orden") == row["paso_orden"]),
        None,
    )
    if not paso_def:
        return []
    items = paso_def.get("items") or []
    return [i for i in items if isinstance(i, dict) and i.get("id")]


def get_items_estado(conn, tarea_id: int) -> Dict[str, Any]:
    """Lee items_estado de la tarea como dict {item_id: {...}}."""
    row = conn.execute(
        "SELECT items_estado FROM gta.tareas WHERE id = %s",
        (tarea_id,),
    ).fetchone()
    if not row:
        return {}
    raw = row.get("items_estado")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw or "{}") or {}
        except Exception:
            return {}
    return {}


def items_pendientes_requeridos(conn, tarea_id: int) -> List[str]:
    """Devuelve los titulos de los items con requerido_para_cerrar=true que
    aún no están tickeados. Si la lista está vacía, el cierre del paso es
    válido respecto a items."""
    items_def = get_items_definicion_de_tarea(conn, tarea_id)
    if not items_def:
        return []
    estado = get_items_estado(conn, tarea_id)
    pendientes: List[str] = []
    for item in items_def:
        if item.get("requerido_para_cerrar") is False:
            continue  # explicitamente opcional
        est = estado.get(item["id"]) or {}
        if not est.get("tickeado"):
            pendientes.append(item.get("titulo") or item["id"])
    return pendientes


def tickear_item(
    *,
    tarea_id: int,
    item_id: str,
    tickeado: bool,
    actor_id: int,
) -> Dict[str, Any]:
    """Marca un item como tickeado o no tickeado. Si al tickear el item
    tiene desbloquea_pasos, esos pasos del flujo se desbloquean
    directamente (bloqueada → pendiente). Destickear NO re-bloquea."""
    conn = db.get_conn()
    try:
        # Tarea + paso + proceso, para validar y conocer items definición
        ctx = conn.execute(
            """SELECT t.id, t.flujo_id, t.paso_orden, t.estado, t.items_estado,
                      p.pasos_definicion
               FROM gta.tareas t
               LEFT JOIN gta.procesos p ON p.id = t.proceso_id
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not ctx:
            raise ValueError("tarea no encontrada")
        if ctx["estado"] in ("cerrada", "cancelada", "devuelta"):
            raise ValueError(f"no se puede modificar items en una tarea {ctx['estado']}")

        # Validar que el item exista en la definición del paso
        try:
            pasos = json.loads(ctx.get("pasos_definicion") or "[]") or []
        except Exception:
            pasos = []
        paso_def = next(
            (p for p in pasos if isinstance(p, dict) and p.get("orden") == ctx["paso_orden"]),
            None,
        )
        items_def = (paso_def or {}).get("items") or []
        item_def = next((i for i in items_def if isinstance(i, dict) and i.get("id") == item_id), None)
        if not item_def:
            raise ValueError(f"item '{item_id}' no existe en este paso")

        # Actualizar items_estado
        raw_estado = ctx.get("items_estado")
        if isinstance(raw_estado, dict):
            estado = dict(raw_estado)
        elif isinstance(raw_estado, str):
            try:
                estado = json.loads(raw_estado or "{}") or {}
            except Exception:
                estado = {}
        else:
            estado = {}
        if tickeado:
            estado[item_id] = {
                "tickeado": True,
                "tickeado_por_id": actor_id,
                "tickeado_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            # Destickear: mantener el registro pero marcar tickeado=false
            prev = estado.get(item_id) or {}
            estado[item_id] = {
                **prev,
                "tickeado": False,
                "tickeado_at": datetime.now(timezone.utc).isoformat(),
            }
        conn.execute(
            "UPDATE gta.tareas SET items_estado = %s::jsonb, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (json.dumps(estado, ensure_ascii=False), tarea_id),
        )

        # Desbloqueo directo de pasos del flujo si el item tiene desbloquea_pasos
        # (solo al tickear; destickear no re-bloquea pasos ya tomados).
        desbloqueadas_ids: List[int] = []
        if tickeado and ctx.get("flujo_id"):
            paso_objetivos = item_def.get("desbloquea_pasos") or []
            for paso_orden in paso_objetivos:
                try:
                    paso_orden_int = int(paso_orden)
                except (ValueError, TypeError):
                    continue
                fila = conn.execute(
                    """UPDATE gta.tareas
                       SET estado = 'pendiente',
                           sla_due_at = CASE
                               WHEN sla_horas IS NOT NULL AND sla_due_at IS NULL
                               THEN CURRENT_TIMESTAMP + (sla_horas || ' hours')::interval
                               ELSE sla_due_at
                           END,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE flujo_id = %s
                         AND paso_orden = %s
                         AND estado = 'bloqueada'
                       RETURNING id""",
                    (ctx["flujo_id"], paso_orden_int),
                ).fetchone()
                if fila:
                    desbloqueadas_ids.append(int(fila["id"]))

        # Evento en el timeline del flujo
        if ctx.get("flujo_id"):
            from gta.backend.services import flujo_eventos as evt
            actor_row = conn.execute(
                "SELECT username FROM auth.users WHERE id = %s", (actor_id,),
            ).fetchone()
            actor = (actor_row or {}).get("username") or "sistema"
            accion = "Tickeó" if tickeado else "Destickeó"
            mensaje = f"{accion} ítem «{item_def.get('titulo') or item_id}» del paso {ctx['paso_orden']}"
            if desbloqueadas_ids:
                mensaje += f" — desbloqueó {len(desbloqueadas_ids)} paso(s)"
            evt.registrar(
                conn, ctx["flujo_id"],
                tipo=evt.TAREA_CERRADA,  # reusamos tipo existente (no hay TICKEAR específico)
                actor=actor,
                tarea_id=tarea_id,
                mensaje=mensaje,
                metadata={
                    "item_id": item_id,
                    "tickeado": tickeado,
                    "desbloqueadas": desbloqueadas_ids,
                },
            )

        conn.commit()
        return {
            "tarea_id": tarea_id,
            "item_id": item_id,
            "tickeado": tickeado,
            "desbloqueadas": desbloqueadas_ids,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def listar_items_de_tarea(tarea_id: int) -> List[Dict[str, Any]]:
    """Combina definición de items (de la plantilla) con el estado actual
    (de items_estado). Útil para que la UI los renderice en orden y con
    su flag de tickeado."""
    conn = db.get_conn()
    try:
        items_def = get_items_definicion_de_tarea(conn, tarea_id)
        if not items_def:
            return []
        estado = get_items_estado(conn, tarea_id)
        out = []
        for item in items_def:
            est = estado.get(item["id"]) or {}
            out.append({
                "id": item["id"],
                "titulo": item.get("titulo") or item["id"],
                "requerido_para_cerrar": item.get("requerido_para_cerrar") is not False,
                "desbloquea_pasos": item.get("desbloquea_pasos") or [],
                "tickeado": bool(est.get("tickeado")),
                "tickeado_at": est.get("tickeado_at"),
                "tickeado_por_id": est.get("tickeado_por_id"),
            })
        return out
    finally:
        conn.close()
