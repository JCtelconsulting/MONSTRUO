"""Servicio de flujos del GTA — modelo unificado en gta.tareas.

Después del refactor 011_gta_tareas_flujo_inline.sql, ya no existen las
tablas gta.flujos / gta.flujo_tareas / gta.flujo_eventos. Toda la info
del flujo vive directo en gta.tareas, identificada por la columna flujo_id.

Este servicio expone:
- crear_flujo(): inicia un nuevo flujo a partir de un proceso del catálogo,
  generando N filas en gta.tareas (una por paso).
- listar_flujos(), get_flujo(): vistas para el tablero.
- metricas_globales(): KPIs sobre los flujos activos.

Las funciones del sistema viejo (validar_tarea, pedir_ayuda, etc.) ya no
aplican y fueron removidas. Si un endpoint las invoca, devuelve 410.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from plataforma.core import db

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_pasos_definicion(raw: Any) -> List[Dict[str, Any]]:
    """Normaliza la definición de pasos del proceso a lista de dicts."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, list):
        return []
    pasos = []
    for i, p in enumerate(raw):
        if not isinstance(p, dict):
            continue
        pasos.append({
            "orden": int(p.get("orden") or (i + 1)),
            "titulo": str(p.get("titulo") or p.get("nombre") or "").strip(),
            "descripcion": str(p.get("descripcion") or "").strip(),
            "area_code": str(p.get("area_code") or p.get("area") or "").strip(),
            "subarea_code": p.get("subarea_code") or None,
            "sla_horas": int(p.get("sla_horas") or 24),
            "depende_de": list(p.get("depende_de") or []),
            "bloqueante": p.get("bloqueante", True) is not False,
        })
    return [p for p in pasos if p["titulo"] and p["area_code"]]


def _resolver_subarea_id(conn, area_code: str, subarea_code: Optional[str]) -> Optional[int]:
    """Resuelve (area, subarea) → subarea_id en gta.subareas.

    Si el área es plana (sin subárea explícita), tomamos cualquier subárea
    activa del área como bandeja default. Si no hay ninguna, devuelve None.
    """
    if subarea_code:
        row = conn.execute(
            "SELECT id FROM gta.subareas WHERE area_code = %s AND code = %s",
            (area_code, subarea_code),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM gta.subareas WHERE area_code = %s AND activo = TRUE "
            "ORDER BY orden, id LIMIT 1",
            (area_code,),
        ).fetchone()
    return int(row["id"]) if row else None


def crear_flujo(
    *,
    iniciado_por: str,
    titulo: str,
    descripcion: str = "",
    proceso_id: Optional[int] = None,
    datos_formulario: Optional[Dict[str, Any]] = None,
    pasos_libres: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Inicia un flujo y crea N tareas (una por paso) en gta.tareas.

    Reglas:
    - El flujo se identifica con un UUID guardado en gta.tareas.flujo_id.
    - Paso 1 nace 'pendiente' SIN responsable → cae a la bandeja del área
      correspondiente para que cualquier miembro lo tome.
    - Pasos siguientes nacen 'bloqueada' si dependen de algún predecesor
      bloqueante; 'pendiente' en otro caso.
    - sla_due_at se setea solo para pasos que arrancan en 'pendiente'.
    - datos_formulario inicial se guarda en cada tarea del flujo (datos_flujo)
      para que todos los pasos los vean. Se actualiza al cerrar el paso 1
      con los datos definitivos del proceso.
    """
    if not titulo.strip():
        raise ValueError("titulo es requerido")
    if proceso_id and pasos_libres:
        raise ValueError("usar proceso_id O pasos_libres, no ambos")
    if not proceso_id and not pasos_libres:
        raise ValueError("debe especificar proceso_id o pasos_libres")

    conn = db.get_conn()
    try:
        # Resolver pasos
        if proceso_id:
            proc = conn.execute(
                "SELECT id, nombre, pasos_definicion FROM gta.procesos WHERE id = %s",
                (proceso_id,),
            ).fetchone()
            if not proc:
                raise ValueError(f"proceso {proceso_id} no existe")
            pasos = _parse_pasos_definicion(proc.get("pasos_definicion"))
            if not pasos:
                raise ValueError("el proceso no tiene pasos definidos")
        else:
            pasos = _parse_pasos_definicion(pasos_libres)
            if not pasos:
                raise ValueError("debe especificar al menos un paso")

        # Resolver actor (FK a auth.users)
        actor_row = conn.execute(
            "SELECT id FROM auth.users WHERE username = %s",
            (iniciado_por,),
        ).fetchone()
        if not actor_row:
            raise ValueError(f"usuario no encontrado: {iniciado_por}")
        actor_id = int(actor_row["id"])

        # Identificador único del flujo
        flujo_id = str(uuid.uuid4())
        datos_inicial = json.dumps(datos_formulario or {}, ensure_ascii=False)

        # Calcular estado inicial por orden
        bloqueante_por_orden = {p["orden"]: p["bloqueante"] for p in pasos}
        estado_por_orden: Dict[int, str] = {}
        for p in pasos:
            deps = p["depende_de"]
            if not deps:
                estado_por_orden[p["orden"]] = "pendiente"
                continue
            traba = any(bloqueante_por_orden.get(d, True) for d in deps)
            estado_por_orden[p["orden"]] = "bloqueada" if traba else "pendiente"

        # Insertar cada paso como gta.tareas
        ids_creados = []
        pasos_skipeados = []
        for paso in pasos:
            sub_id = _resolver_subarea_id(conn, paso["area_code"], paso.get("subarea_code"))
            if not sub_id:
                pasos_skipeados.append(paso["orden"])
                logger.warning(
                    "[GTA-FLUJO] paso #%s '%s' (%s/%s) sin subárea resoluble — saltado",
                    paso["orden"], paso["titulo"], paso["area_code"], paso.get("subarea_code"),
                )
                continue

            estado = estado_por_orden[paso["orden"]]
            sla_h = paso["sla_horas"] or None

            # SLA solo para pasos que arrancan pendientes
            if sla_h and estado == "pendiente":
                sla_due_clause = "CURRENT_TIMESTAMP + (%s || ' hours')::interval"
                sla_due_param = [str(sla_h)]
            else:
                sla_due_clause = "NULL"
                sla_due_param = []

            params = [
                sub_id, proceso_id,
                paso["titulo"], paso["descripcion"],
                "proceso", "media", estado, sla_h,
            ] + sla_due_param + [
                actor_id,
                flujo_id, titulo.strip(), paso["orden"],
                json.dumps(paso["depende_de"]), paso["bloqueante"],
                datos_inicial, actor_id,
            ]

            row = conn.execute(
                f"""INSERT INTO gta.tareas
                    (subarea_id, proceso_id,
                     titulo, descripcion, tipo, prioridad, estado, sla_horas,
                     sla_due_at, creado_por,
                     flujo_id, flujo_titulo, paso_orden,
                     paso_depende_de, paso_bloqueante,
                     datos_flujo, iniciado_por_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, {sla_due_clause}, %s,
                            %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s)
                    RETURNING id""",
                tuple(params),
            ).fetchone()
            ids_creados.append(int(row["id"]))

        conn.commit()
        return {
            "flujo_id": flujo_id,
            "titulo": titulo.strip(),
            "proceso_id": proceso_id,
            "tareas_ids": ids_creados,
            "pasos_skipeados": pasos_skipeados,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Vista del tablero (jefe / admin) ───────────────────────────────────

def listar_flujos(
    *,
    estado: Optional[str] = None,
    area_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Devuelve flujos activos agrupados por flujo_id, con resumen de tareas.

    Para el tablero: cuántas tareas pendientes/bloqueadas/cerradas, % avance,
    SLA general, etc.
    """
    where = ["t.flujo_id IS NOT NULL"]
    params: List[Any] = []
    if area_code:
        where.append("t.id IN (SELECT t2.id FROM gta.tareas t2 "
                     "JOIN gta.subareas s2 ON s2.id = t2.subarea_id "
                     "WHERE t2.flujo_id = t.flujo_id AND s2.area_code = %s)")
        params.append(area_code)

    conn = db.get_conn()
    try:
        rows = conn.execute(
            f"""SELECT
                t.flujo_id,
                MAX(t.flujo_titulo) AS titulo,
                MAX(t.proceso_id) AS proceso_id,
                MAX(p.nombre) AS proceso_nombre,
                MIN(t.created_at) AS iniciado_at,
                MAX(u.username) AS iniciado_por,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE t.estado = 'pendiente')  AS pendientes,
                COUNT(*) FILTER (WHERE t.estado = 'en_curso')   AS en_curso,
                COUNT(*) FILTER (WHERE t.estado = 'bloqueada')  AS bloqueadas,
                COUNT(*) FILTER (WHERE t.estado = 'cerrada')    AS cerradas,
                COUNT(*) FILTER (WHERE t.estado = 'cancelada')  AS canceladas,
                MAX(CASE WHEN t.estado NOT IN ('cerrada','cancelada')
                         THEN t.sla_due_at END) AS proximo_vencimiento,
                MAX(t.datos_flujo::text) AS datos_flujo
            FROM gta.tareas t
            LEFT JOIN gta.procesos p ON p.id = t.proceso_id
            LEFT JOIN auth.users u ON u.id = t.iniciado_por_id
            WHERE {' AND '.join(where)}
            GROUP BY t.flujo_id
            ORDER BY iniciado_at DESC""",
            tuple(params) if params else (),
        ).fetchall()

        flujos = []
        for r in rows:
            total = int(r["total"] or 0)
            cerradas = int(r["cerradas"] or 0)
            canceladas = int(r["canceladas"] or 0)
            avance = round((cerradas / total * 100) if total else 0, 1)
            estado_flujo = (
                "completado" if cerradas == total
                else "cancelado" if canceladas == total
                else "activo"
            )
            if estado and estado != estado_flujo:
                continue
            try:
                datos = json.loads(r.get("datos_flujo") or "{}")
            except Exception:
                datos = {}
            flujos.append({
                "flujo_id": r["flujo_id"],
                "titulo": r.get("titulo") or "",
                "proceso_id": r.get("proceso_id"),
                "proceso_nombre": r.get("proceso_nombre"),
                "iniciado_at": r["iniciado_at"],
                "iniciado_por": r.get("iniciado_por"),
                "estado": estado_flujo,
                "avance_pct": avance,
                "total": total,
                "pendientes": int(r["pendientes"] or 0),
                "en_curso": int(r["en_curso"] or 0),
                "bloqueadas": int(r["bloqueadas"] or 0),
                "cerradas": cerradas,
                "canceladas": canceladas,
                "proximo_vencimiento": r.get("proximo_vencimiento"),
                "datos_flujo": datos,
            })
        return {"items": flujos}
    finally:
        conn.close()


def get_flujo(flujo_id: str) -> Dict[str, Any]:
    """Detalle del flujo: resumen + lista de tareas con su estado actual."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT t.id, t.titulo, t.descripcion, t.estado, t.prioridad,
                      t.sla_horas, t.sla_due_at, t.created_at, t.cerrado_at,
                      t.paso_orden, t.paso_depende_de, t.paso_bloqueante,
                      t.flujo_titulo, t.proceso_id,
                      s.code AS subarea_code, s.label AS subarea_label,
                      s.area_code,
                      a.label AS area_label,
                      gta.responsable_vigente(t.id) AS responsable_id,
                      ur.username AS responsable_username,
                      ui.username AS iniciado_por,
                      t.datos_flujo
               FROM gta.tareas t
               JOIN gta.subareas s ON s.id = t.subarea_id
               JOIN gta.areas a ON a.code = s.area_code
               LEFT JOIN auth.users ur ON ur.id = gta.responsable_vigente(t.id)
               LEFT JOIN auth.users ui ON ui.id = t.iniciado_por_id
               WHERE t.flujo_id = %s
               ORDER BY t.paso_orden""",
            (flujo_id,),
        ).fetchall()
        if not rows:
            return {}

        tareas = []
        for r in rows:
            try:
                deps = json.loads(r.get("paso_depende_de") or "[]")
            except Exception:
                deps = []
            tareas.append({
                "id": int(r["id"]),
                "titulo": r["titulo"],
                "descripcion": r["descripcion"],
                "estado": r["estado"],
                "prioridad": r["prioridad"],
                "sla_horas": r.get("sla_horas"),
                "sla_due_at": r.get("sla_due_at"),
                "created_at": r["created_at"],
                "cerrado_at": r.get("cerrado_at"),
                "paso_orden": r.get("paso_orden"),
                "paso_depende_de": deps,
                "paso_bloqueante": bool(r.get("paso_bloqueante")),
                "subarea_code": r["subarea_code"],
                "subarea_label": r["subarea_label"],
                "area_code": r["area_code"],
                "area_label": r["area_label"],
                "responsable_id": r.get("responsable_id"),
                "responsable_username": r.get("responsable_username"),
            })

        primera = rows[0]
        try:
            datos = json.loads(primera.get("datos_flujo") or "{}")
        except Exception:
            datos = {}

        return {
            "flujo_id": flujo_id,
            "titulo": primera.get("flujo_titulo") or "",
            "proceso_id": primera.get("proceso_id"),
            "iniciado_por": primera.get("iniciado_por"),
            "datos_flujo": datos,
            "tareas": tareas,
        }
    finally:
        conn.close()


def metricas_globales() -> Dict[str, Any]:
    """KPIs sobre flujos y tareas activas."""
    conn = db.get_conn()
    try:
        # Totales por estado
        rows = conn.execute(
            """SELECT
                  COUNT(*) AS total_tareas,
                  COUNT(*) FILTER (WHERE estado = 'pendiente') AS pendientes,
                  COUNT(*) FILTER (WHERE estado = 'en_curso')  AS en_curso,
                  COUNT(*) FILTER (WHERE estado = 'bloqueada') AS bloqueadas,
                  COUNT(*) FILTER (WHERE estado = 'cerrada')   AS cerradas,
                  COUNT(DISTINCT flujo_id) FILTER (WHERE flujo_id IS NOT NULL) AS flujos_total
               FROM gta.tareas"""
        ).fetchone()

        # Promedio horas para cerrar tareas (últimos 30 días)
        prom = conn.execute(
            """SELECT AVG(EXTRACT(EPOCH FROM (cerrado_at - created_at)) / 3600) AS horas
               FROM gta.tareas
               WHERE estado = 'cerrada'
                 AND cerrado_at IS NOT NULL
                 AND cerrado_at >= NOW() - INTERVAL '30 days'"""
        ).fetchone()

        # Tareas vencidas (SLA pasado y aún no cerradas)
        vencidas = conn.execute(
            """SELECT COUNT(*) AS n
               FROM gta.tareas
               WHERE estado NOT IN ('cerrada', 'cancelada')
                 AND sla_due_at IS NOT NULL
                 AND sla_due_at < NOW()"""
        ).fetchone()

        return {
            "total_tareas": int(rows["total_tareas"] or 0),
            "pendientes": int(rows["pendientes"] or 0),
            "en_curso": int(rows["en_curso"] or 0),
            "bloqueadas": int(rows["bloqueadas"] or 0),
            "cerradas": int(rows["cerradas"] or 0),
            "flujos_total": int(rows["flujos_total"] or 0),
            "promedio_horas_cierre": float(prom["horas"]) if prom and prom.get("horas") else None,
            "vencidas": int(vencidas["n"] or 0) if vencidas else 0,
        }
    finally:
        conn.close()
