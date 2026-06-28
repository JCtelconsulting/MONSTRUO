"""Endpoints para operar el sync de planillas Google Sheets."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from fundacion.core import db, deps
from fundacion.core.audit_decorator import audit_action

from fundacion.backend.services import drive_sync, sedes as sedes_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fundacion/sync", tags=["fundacion-sync"])


def _is_admin(user: dict) -> bool:
    role = (user.get("role") or "").lower()
    roles = [r.lower() for r in (user.get("roles") or [])]
    admin_roles = {"admin", "directora_social", "jefa_pedagogica", "coordinadora_territorial"}
    return role in admin_roles or any(r in admin_roles for r in roles)


@router.post("/sheets")
@audit_action("FUNDACION_SYNC_SHEETS", severity="info")
async def post_sync_sheets(
    sede_code: Optional[str] = None,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    """Dispara el sync de Google Sheets → DB. Solo admin/jefatura.

    Si se pasa sede_code, solo sincroniza esa sede. Si no, las 7.
    """
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Solo admin/jefatura pueden sincronizar")

    actor = user.get("username")

    if sede_code:
        conn = db.get_conn()
        try:
            row = conn.execute(
                "SELECT id, code FROM fundacion.sedes WHERE code = %s", (sede_code,)
            ).fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(status_code=404, detail=f"Sede '{sede_code}' no existe")
        result = drive_sync.sync_sede(row["id"])
        return {
            "sede_id": result.sede_id,
            "sede_code": result.sede_code,
            "status": result.status,
            "alumnos_creados": result.alumnos_creados,
            "alumnos_actualizados": result.alumnos_actualizados,
            "alumnos_desaparecidos": result.alumnos_desaparecidos,
            "asistencias_insertadas": result.asistencias_insertadas,
            "asistencias_actualizadas": result.asistencias_actualizadas,
            "codigos_desconocidos": result.codigos_desconocidos,
            "error": result.error,
        }

    return drive_sync.sync_todas(trigger="manual", actor=actor)


@router.get("/logs")
async def get_sync_logs(
    limit: int = 20,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Devuelve los últimos N runs del sync con sus filas hijas por sede."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Solo admin/jefatura pueden ver el log")

    limit = max(1, min(limit, 100))

    conn = db.get_conn()
    try:
        # Padre por run
        padres = conn.execute(
            """
            SELECT run_id::text, started_at, finished_at, status, trigger, actor,
                   alumnos_creados, alumnos_actualizados, alumnos_desaparecidos,
                   asistencias_insertadas, asistencias_actualizadas, codigos_desconocidos
            FROM fundacion.sync_logs
            WHERE sede_id IS NULL
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

        if not padres:
            return {"items": []}

        run_ids = tuple(p["run_id"] for p in padres)
        placeholders = ", ".join(["%s"] * len(run_ids))
        hijos = conn.execute(
            f"""
            SELECT sl.run_id::text, sl.sede_id, s.code AS sede_code, s.nombre AS sede_nombre,
                   sl.started_at, sl.finished_at, sl.status,
                   sl.alumnos_creados, sl.alumnos_actualizados, sl.alumnos_desaparecidos,
                   sl.asistencias_insertadas, sl.asistencias_actualizadas,
                   sl.codigos_desconocidos, sl.mensaje
            FROM fundacion.sync_logs sl
            LEFT JOIN fundacion.sedes s ON s.id = sl.sede_id
            WHERE sl.sede_id IS NOT NULL AND sl.run_id::text IN ({placeholders})
            ORDER BY sl.run_id, s.orden NULLS LAST
            """,
            run_ids,
        ).fetchall()

        # Indexar hijos por run_id
        hijos_por_run: dict[str, list] = {}
        for h in hijos:
            hijos_por_run.setdefault(h["run_id"], []).append(h)

        items = []
        for p in padres:
            items.append({
                **p,
                "sedes": hijos_por_run.get(p["run_id"], []),
            })
        return {"items": items}
    finally:
        conn.close()
