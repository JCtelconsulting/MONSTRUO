from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from plataforma.core import db, deps
from plataforma.core.audit_decorator import audit_action

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
            "SELECT id, username, role, secondary_roles, is_active "
            "FROM auth.users WHERE COALESCE(is_active, 1) <> 0 ORDER BY username"
        ).fetchall()
        items = [
            {
                "id": int(r["id"]),
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


# ── Membresías (líderes y miembros vigentes por subárea) ──────────────

class MembresiaIn(BaseModel):
    usuario_id: int
    subarea_id: int
    rol: str = "miembro"          # miembro | lider
    es_principal: bool = False
    motivo: Optional[str] = None


@router.get("/membresias", summary="Membresías vigentes por subárea (líder + miembros)")
async def list_membresias(
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT m.id, m.usuario_id, m.subarea_id, m.rol, m.es_principal,
                      m.desde, m.motivo,
                      u.username,
                      s.code AS subarea_code, s.label AS subarea_label,
                      s.area_code,
                      a.label AS area_label
               FROM gta.area_membresias m
               JOIN auth.users u ON u.id = m.usuario_id
               JOIN gta.subareas s ON s.id = m.subarea_id
               JOIN gta.areas a ON a.code = s.area_code
               WHERE m.hasta IS NULL
               ORDER BY a.orden, s.orden, (m.rol = 'lider') DESC, m.es_principal DESC, u.username"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("/membresias", summary="Asignar usuario a subárea (miembro o líder)")
@audit_action("GTA_MEMBRESIA_ASIGNAR", severity="warning")
async def create_membresia(
    body: MembresiaIn,
    request: Request,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    if body.rol not in ("miembro", "lider"):
        raise HTTPException(status_code=400, detail="rol debe ser 'miembro' o 'lider'")

    actor_id = _resolver_actor_id(sess)

    conn = db.get_conn()
    try:
        # Validar referencias
        u = conn.execute("SELECT id FROM auth.users WHERE id = %s", (body.usuario_id,)).fetchone()
        if not u:
            raise HTTPException(status_code=400, detail="usuario no encontrado")
        s = conn.execute("SELECT id FROM gta.subareas WHERE id = %s", (body.subarea_id,)).fetchone()
        if not s:
            raise HTTPException(status_code=400, detail="subárea no encontrada")

        # Cerrar membresía vigente del mismo (usuario, subárea), si existe
        conn.execute(
            """UPDATE gta.area_membresias
               SET hasta = CURRENT_TIMESTAMP
               WHERE usuario_id = %s AND subarea_id = %s AND hasta IS NULL""",
            (body.usuario_id, body.subarea_id),
        )
        # Si es líder, cerrar al líder vigente actual de la subárea
        if body.rol == "lider":
            conn.execute(
                """UPDATE gta.area_membresias
                   SET hasta = CURRENT_TIMESTAMP
                   WHERE subarea_id = %s AND rol = 'lider'
                     AND usuario_id <> %s AND hasta IS NULL""",
                (body.subarea_id, body.usuario_id),
            )
        # Si es principal, cerrar la principal vigente del usuario en otra subárea
        if body.es_principal:
            conn.execute(
                """UPDATE gta.area_membresias
                   SET hasta = CURRENT_TIMESTAMP
                   WHERE usuario_id = %s AND es_principal = TRUE
                     AND subarea_id <> %s AND hasta IS NULL""",
                (body.usuario_id, body.subarea_id),
            )

        row = conn.execute(
            """INSERT INTO gta.area_membresias
               (usuario_id, subarea_id, rol, es_principal, asignado_por, motivo)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, desde""",
            (body.usuario_id, body.subarea_id, body.rol, body.es_principal, actor_id, body.motivo),
        ).fetchone()
        conn.commit()
        return {"id": int(row["id"]), "desde": row["desde"]}
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()


@router.delete("/membresias/{membresia_id}", summary="Cerrar membresía vigente")
@audit_action("GTA_MEMBRESIA_CERRAR", severity="warning")
async def close_membresia(
    membresia_id: int,
    request: Request,
    sess: dict = Depends(deps.require_permission("admin.settings")),
):
    conn = db.get_conn()
    try:
        row = conn.execute(
            """UPDATE gta.area_membresias
               SET hasta = CURRENT_TIMESTAMP
               WHERE id = %s AND hasta IS NULL
               RETURNING id""",
            (int(membresia_id),),
        ).fetchone()
        conn.commit()
        if not row:
            raise HTTPException(status_code=404, detail="membresía no encontrada o ya cerrada")
        return {"ok": True, "id": int(row["id"])}
    finally:
        conn.close()


def _resolver_actor_id(sess: dict) -> Optional[int]:
    username = sess.get("username") if isinstance(sess, dict) else None
    if not username:
        return None
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM auth.users WHERE username = %s", (username,),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()
