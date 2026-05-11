"""Endpoints de reportes y dashboard para Fundación.

Toda la lógica pesada vive en vistas SQL (fundacion.v_alumno_kpi,
v_sede_kpi, v_asistencia_mensual). Estos endpoints solo filtran y
formatean.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from plataforma.core import db, deps
from fundacion.backend.services import sedes as sedes_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fundacion/reportes", tags=["fundacion-reportes"])


def _user_id(user: dict) -> Optional[int]:
    return sedes_service.usuario_id_de_username(user.get("username", ""))


def _scope_sede_ids(user: dict) -> Optional[set[int]]:
    """Devuelve el set de sede_ids accesibles, o None si el usuario tiene scope total."""
    uid = _user_id(user)
    if uid is None:
        return set()
    if sedes_service.es_super_scope(uid):
        return None
    codes = sedes_service.sede_codes_accesibles(uid)
    if not codes:
        return set()
    conn = db.get_conn()
    try:
        placeholders = ", ".join(["%s"] * len(codes))
        rows = conn.execute(
            f"SELECT id FROM fundacion.sedes WHERE code IN ({placeholders})",
            tuple(codes),
        ).fetchall()
        return {r["id"] for r in rows}
    finally:
        conn.close()


def _aplica_filtro_sede(sede_ids: Optional[set[int]], rows: list[dict]) -> list[dict]:
    if sede_ids is None:
        return rows
    return [r for r in rows if r.get("sede_id") in sede_ids]


@router.get("/dashboard")
async def get_dashboard(
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Resumen general: totales por sede, riesgos, último sync."""
    sede_ids = _scope_sede_ids(user)

    conn = db.get_conn()
    try:
        # KPIs por sede
        sedes = conn.execute(
            """
            SELECT sede_id, sede_code, sede_nombre, cupos,
                   alumnos_total, alumnos_activos, alumnos_visibles,
                   pct_asistencia_sede
            FROM fundacion.v_sede_kpi
            """
        ).fetchall()
        sedes_filtradas = _aplica_filtro_sede(sede_ids, [dict(r) for r in sedes])

        # Distribución de riesgo (sobre activos) — global
        riesgo_filtro_sql = ""
        params: tuple = ()
        if sede_ids is not None:
            if not sede_ids:
                riesgo_filtro_sql = "AND FALSE"
            else:
                ph = ", ".join(["%s"] * len(sede_ids))
                riesgo_filtro_sql = f"AND sede_id IN ({ph})"
                params = tuple(sede_ids)

        riesgo = conn.execute(
            f"""
            SELECT nivel_riesgo, COUNT(*) AS total
            FROM fundacion.v_alumno_kpi
            WHERE matricula_activa = TRUE {riesgo_filtro_sql}
            GROUP BY nivel_riesgo
            """,
            params,
        ).fetchall()
        riesgo_map = {"alto": 0, "medio": 0, "bajo": 0, "sin_datos": 0}
        for r in riesgo:
            key = r["nivel_riesgo"] or "sin_datos"
            riesgo_map[key] = r["total"]

        # Último sync exitoso (run padre)
        ultimo = conn.execute(
            """
            SELECT run_id::text, started_at, finished_at, status, trigger, actor,
                   alumnos_creados, alumnos_actualizados,
                   asistencias_insertadas, asistencias_actualizadas
            FROM fundacion.sync_logs
            WHERE sede_id IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()

        totales = {
            "alumnos_total": sum(s["alumnos_total"] for s in sedes_filtradas),
            "alumnos_activos": sum(s["alumnos_activos"] for s in sedes_filtradas),
            "alumnos_visibles": sum(s["alumnos_visibles"] for s in sedes_filtradas),
            "cupos": sum((s["cupos"] or 0) for s in sedes_filtradas),
        }
        return {
            "sedes": sedes_filtradas,
            "totales": totales,
            "riesgo": riesgo_map,
            "ultimo_sync": ultimo,
        }
    finally:
        conn.close()


@router.get("/alumnos")
async def get_alumnos(
    sede_id: Optional[int] = None,
    matricula_activa: Optional[bool] = None,
    nivel_riesgo: Optional[str] = None,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Lista alumnos con sus KPIs. Filtros opcionales."""
    sede_ids = _scope_sede_ids(user)

    conn = db.get_conn()
    try:
        clauses = ["TRUE"]
        params: list = []
        if sede_id is not None:
            if sede_ids is not None and sede_id not in sede_ids:
                raise HTTPException(status_code=403, detail="No tiene acceso a esa sede")
            clauses.append("sede_id = %s")
            params.append(sede_id)
        elif sede_ids is not None:
            if not sede_ids:
                return {"items": []}
            ph = ", ".join(["%s"] * len(sede_ids))
            clauses.append(f"sede_id IN ({ph})")
            params.extend(sede_ids)

        if matricula_activa is not None:
            clauses.append("matricula_activa = %s")
            params.append(matricula_activa)
        if nivel_riesgo:
            if nivel_riesgo == "sin_datos":
                clauses.append("nivel_riesgo IS NULL")
            else:
                clauses.append("nivel_riesgo = %s")
                params.append(nivel_riesgo)

        rows = conn.execute(
            f"""
            SELECT alumno_id, sede_id, correlativo, nombre_completo, rut,
                   curso_after, plan, gestora_a_cargo, estado_alumno,
                   estado_matricula, matricula_activa, riesgo_planilla,
                   dias_presente, dias_ausente, dias_justificado, dias_contables,
                   pct_asistencia, nivel_riesgo, presente_en_planilla
            FROM fundacion.v_alumno_kpi
            WHERE {" AND ".join(clauses)}
            ORDER BY sede_id, correlativo
            """,
            tuple(params),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/asistencia-mensual")
async def get_asistencia_mensual(
    sede_id: Optional[int] = None,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """% de asistencia por mes y por sede."""
    sede_ids = _scope_sede_ids(user)

    conn = db.get_conn()
    try:
        clauses = ["TRUE"]
        params: list = []
        if sede_id is not None:
            if sede_ids is not None and sede_id not in sede_ids:
                raise HTTPException(status_code=403, detail="No tiene acceso a esa sede")
            clauses.append("sede_id = %s")
            params.append(sede_id)
        elif sede_ids is not None:
            if not sede_ids:
                return {"items": []}
            ph = ", ".join(["%s"] * len(sede_ids))
            clauses.append(f"sede_id IN ({ph})")
            params.extend(sede_ids)

        rows = conn.execute(
            f"""
            SELECT sede_id, sede_code, sede_nombre, anio, mes_num, mes,
                   p_total, contables_total, pct_asistencia
            FROM fundacion.v_asistencia_mensual
            WHERE {" AND ".join(clauses)}
            ORDER BY anio, mes_num, sede_id
            """,
            tuple(params),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/asistencia-matriz")
async def get_asistencia_matriz(
    sede_id: int,
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Matriz alumnos × fechas de una sede en un rango.

    Devuelve fechas (lista), alumnos (lista con datos básicos) y celdas
    (dict {alumno_id: {fecha: codigo}}).
    """
    sede_ids = _scope_sede_ids(user)
    if sede_ids is not None and sede_id not in sede_ids:
        raise HTTPException(status_code=403, detail="No tiene acceso a esa sede")

    conn = db.get_conn()
    try:
        rango_clauses = ["ad.sede_id = %s"]
        params: list = [sede_id]
        if desde:
            rango_clauses.append("ad.fecha >= %s")
            params.append(desde)
        if hasta:
            rango_clauses.append("ad.fecha <= %s")
            params.append(hasta)

        fechas = conn.execute(
            f"""
            SELECT DISTINCT fecha FROM fundacion.asistencia_diaria ad
            WHERE {" AND ".join(rango_clauses)}
            ORDER BY fecha
            """,
            tuple(params),
        ).fetchall()

        alumnos = conn.execute(
            """
            SELECT id, correlativo, nombre_completo, rut, curso_after, plan, matricula_activa
            FROM fundacion.alumnos
            WHERE sede_id = %s AND presente_en_planilla = TRUE
            ORDER BY correlativo
            """,
            (sede_id,),
        ).fetchall()

        celdas = conn.execute(
            f"""
            SELECT ad.alumno_id, ad.fecha::text AS fecha, ad.codigo, ad.codigo_conocido
            FROM fundacion.asistencia_diaria ad
            WHERE {" AND ".join(rango_clauses)}
            """,
            tuple(params),
        ).fetchall()

        celdas_map: dict[int, dict[str, dict]] = {}
        for c in celdas:
            celdas_map.setdefault(c["alumno_id"], {})[c["fecha"]] = {
                "codigo": c["codigo"],
                "conocido": c["codigo_conocido"],
            }

        return {
            "sede_id": sede_id,
            "fechas": [f["fecha"].isoformat() for f in fechas],
            "alumnos": [dict(a) for a in alumnos],
            "celdas": celdas_map,
        }
    finally:
        conn.close()
