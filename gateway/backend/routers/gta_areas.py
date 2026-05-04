from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from plataforma.core import db, deps

router = APIRouter(prefix="/api/config/gta", tags=["config", "gta"])


class AreaUpdate(BaseModel):
    label: Optional[str] = None
    lider_username: Optional[str] = None
    lider_nombre: Optional[str] = None
    es_externa: Optional[bool] = None
    activo: Optional[bool] = None
    orden: Optional[int] = None


class SubareaIn(BaseModel):
    area_code: str
    code: str
    label: str
    lider_username: str = ""
    lider_nombre: str = ""
    activo: bool = True
    orden: int = 99


class SubareaUpdate(BaseModel):
    label: Optional[str] = None
    lider_username: Optional[str] = None
    lider_nombre: Optional[str] = None
    activo: Optional[bool] = None
    orden: Optional[int] = None


def _serialize_area(row) -> dict:
    return {
        "code": row["code"],
        "label": row["label"],
        "lider_username": row.get("lider_username") or "",
        "lider_nombre": row.get("lider_nombre") or "",
        "es_externa": bool(row.get("es_externa")),
        "activo": bool(row.get("activo")),
        "orden": int(row.get("orden") or 99),
    }


def _serialize_subarea(row) -> dict:
    return {
        "id": int(row["id"]),
        "area_code": row["area_code"],
        "code": row["code"],
        "label": row["label"],
        "lider_username": row.get("lider_username") or "",
        "lider_nombre": row.get("lider_nombre") or "",
        "activo": bool(row.get("activo")),
        "orden": int(row.get("orden") or 99),
    }


@router.get("/areas", summary="Lista de áreas GTA con sus subáreas")
async def list_areas(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        areas = conn.execute(
            "SELECT code, label, lider_username, lider_nombre, es_externa, activo, orden "
            "FROM gta.areas ORDER BY orden, code"
        ).fetchall()
        subs = conn.execute(
            "SELECT id, area_code, code, label, lider_username, lider_nombre, activo, orden "
            "FROM gta.subareas ORDER BY area_code, orden, code"
        ).fetchall()

        sub_by_area: dict = {}
        for s in subs:
            sub_by_area.setdefault(s["area_code"], []).append(_serialize_subarea(s))

        items = []
        for a in areas:
            item = _serialize_area(a)
            item["subareas"] = sub_by_area.get(a["code"], [])
            items.append(item)
        return {"items": items}
    finally:
        conn.close()


@router.put("/areas/{code}", summary="Actualizar área GTA")
async def update_area(
    code: str,
    body: AreaUpdate,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    code = str(code or "").strip().lower()
    if not code:
        raise HTTPException(status_code=400, detail="code requerido")

    fields = []
    params: list = []
    for col, val in (
        ("label", body.label),
        ("lider_username", body.lider_username),
        ("lider_nombre", body.lider_nombre),
        ("es_externa", body.es_externa),
        ("activo", body.activo),
        ("orden", body.orden),
    ):
        if val is not None:
            fields.append(f"{col} = %s")
            params.append(val)

    if not fields:
        raise HTTPException(status_code=400, detail="sin cambios")

    params.append(code)
    conn = db.get_conn()
    try:
        conn.execute(
            f"UPDATE gta.areas SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE code = %s",
            tuple(params),
        )
        conn.commit()
        row = conn.execute(
            "SELECT code, label, lider_username, lider_nombre, es_externa, activo, orden FROM gta.areas WHERE code = %s",
            (code,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="area no encontrada")
        return _serialize_area(row)
    finally:
        conn.close()


@router.post("/subareas", summary="Crear subárea GTA")
async def create_subarea(
    body: SubareaIn,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    area_code = str(body.area_code or "").strip().lower()
    code = str(body.code or "").strip().lower()
    label = str(body.label or "").strip()
    if not area_code or not code or not label:
        raise HTTPException(status_code=400, detail="area_code, code y label son obligatorios")

    conn = db.get_conn()
    try:
        parent = conn.execute(
            "SELECT 1 FROM gta.areas WHERE code = %s",
            (area_code,),
        ).fetchone()
        if not parent:
            raise HTTPException(status_code=400, detail=f"area '{area_code}' no existe")

        try:
            conn.execute(
                """INSERT INTO gta.subareas
                   (area_code, code, label, lider_username, lider_nombre, activo, orden)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (area_code, code, label, body.lider_username, body.lider_nombre, body.activo, body.orden),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(status_code=400, detail=f"no se pudo crear subarea: {exc}")

        row = conn.execute(
            "SELECT id, area_code, code, label, lider_username, lider_nombre, activo, orden "
            "FROM gta.subareas WHERE area_code = %s AND code = %s",
            (area_code, code),
        ).fetchone()
        return _serialize_subarea(row)
    finally:
        conn.close()


@router.put("/subareas/{sub_id}", summary="Actualizar subárea")
async def update_subarea(
    sub_id: int,
    body: SubareaUpdate,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    fields = []
    params: list = []
    for col, val in (
        ("label", body.label),
        ("lider_username", body.lider_username),
        ("lider_nombre", body.lider_nombre),
        ("activo", body.activo),
        ("orden", body.orden),
    ):
        if val is not None:
            fields.append(f"{col} = %s")
            params.append(val)

    if not fields:
        raise HTTPException(status_code=400, detail="sin cambios")

    params.append(int(sub_id))
    conn = db.get_conn()
    try:
        conn.execute(
            f"UPDATE gta.subareas SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            tuple(params),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, area_code, code, label, lider_username, lider_nombre, activo, orden "
            "FROM gta.subareas WHERE id = %s",
            (int(sub_id),),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="subarea no encontrada")
        return _serialize_subarea(row)
    finally:
        conn.close()


@router.delete("/subareas/{sub_id}", summary="Eliminar subárea")
async def delete_subarea(
    sub_id: int,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        conn.execute("DELETE FROM gta.subareas WHERE id = %s", (int(sub_id),))
        conn.commit()
        return {"ok": True, "id": int(sub_id)}
    finally:
        conn.close()


@router.get("/users", summary="Lista de usuarios disponibles para asignar como líder")
async def list_users(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT username, role, secondary_roles, is_active "
            "FROM auth.users WHERE COALESCE(is_active, 1) IN (1, TRUE) ORDER BY username"
        ).fetchall()
        items = [
            {
                "username": r["username"],
                "email": r["username"],
                "role": r.get("role") or "",
                "secondary_roles": r.get("secondary_roles") or "[]",
            }
            for r in rows
        ]
        return {"items": items}
    finally:
        conn.close()
