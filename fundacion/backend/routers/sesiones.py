"""Endpoints para registrar sesiones pedagógicas diarias y consultar catálogos.

Modelo:
- Una sesión = (sede, fecha). Contiene clima, situaciones, estrategias y N bloques.
- La UI envía la sesión completa al guardar; el backend reemplaza los bloques
  en una transacción (delete + insert). Esto evita el problema de "qué cambió"
  y deja la BD siempre consistente.
"""
from __future__ import annotations

import logging
from datetime import date as date_type
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fundacion.core import db, deps
from fundacion.core.audit_decorator import audit_action

from fundacion.backend.services import sedes as sedes_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fundacion", tags=["fundacion-sesiones"])


def _user_id(user: dict) -> Optional[int]:
    return sedes_service.usuario_id_de_username(user.get("username", ""))


def _ensure_sede_access(user: dict, sede_id: int) -> int:
    uid = _user_id(user)
    if uid is None:
        raise HTTPException(status_code=401, detail="usuario no resoluble")
    if not sedes_service.es_super_scope(uid) and not sedes_service.tiene_acceso_sede(uid, sede_id):
        raise HTTPException(status_code=403, detail="No tiene acceso a esa sede")
    return uid


# ── Catálogos ───────────────────────────────────────────────────────────────

@router.get("/catalogos/niveles")
async def get_niveles(user: dict = Depends(deps.require_permission("fundacion:read"))):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, codigo, nombre, descripcion, color, orden FROM fundacion.niveles WHERE activo = TRUE ORDER BY orden"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/catalogos/actividades")
async def get_actividades(
    q: Optional[str] = None,
    bloque_tipo_id: Optional[int] = None,
    bloque_subtipo_id: Optional[int] = None,
    limit: int = 30,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Búsqueda de actividades (catálogo). Soporta autocomplete por nombre."""
    limit = max(1, min(limit, 100))
    conn = db.get_conn()
    try:
        clauses = ["a.activo = TRUE"]
        params: list = []
        if bloque_tipo_id is not None:
            clauses.append("a.bloque_tipo_id = %s")
            params.append(bloque_tipo_id)
        if bloque_subtipo_id is not None:
            clauses.append("a.bloque_subtipo_id = %s")
            params.append(bloque_subtipo_id)
        if q and q.strip():
            clauses.append("a.nombre_normalizado ILIKE %s")
            params.append(f"%{q.strip().lower()}%")
        sql = f"""
            SELECT a.id, a.nombre, a.bloque_tipo_id, a.bloque_subtipo_id,
                   a.resultado_aprendizaje, a.materiales_tipicos, a.veces_referenciada,
                   bt.codigo AS bloque_tipo_codigo, bt.nombre AS bloque_tipo_nombre,
                   bs.codigo AS bloque_subtipo_codigo, bs.nombre AS bloque_subtipo_nombre,
                   COALESCE((
                       SELECT array_agg(c.codigo ORDER BY c.codigo)
                       FROM fundacion.actividad_competencias ac
                       JOIN fundacion.competencias c ON c.id = ac.competencia_id
                       WHERE ac.actividad_id = a.id
                   ), ARRAY[]::text[]) AS competencias_codigos,
                   COALESCE((
                       SELECT array_agg(ac.competencia_id ORDER BY c.codigo)
                       FROM fundacion.actividad_competencias ac
                       JOIN fundacion.competencias c ON c.id = ac.competencia_id
                       WHERE ac.actividad_id = a.id
                   ), ARRAY[]::int[]) AS competencias_ids
            FROM fundacion.actividades a
            JOIN fundacion.bloque_tipos bt ON bt.id = a.bloque_tipo_id
            LEFT JOIN fundacion.bloque_subtipos bs ON bs.id = a.bloque_subtipo_id
            WHERE {" AND ".join(clauses)}
            ORDER BY a.veces_referenciada DESC, a.nombre
            LIMIT %s
        """
        rows = conn.execute(sql, tuple(params) + (limit,)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/calendario/bloques")
async def get_calendario_bloques(
    sede_id: int,
    nivel_id: int,
    desde: date_type,
    hasta: date_type,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Devuelve los bloques de cada día en el rango.

    Para cada día: si hay sesión guardada usa sus bloques (status='sesion'),
    si no usa los del plan oficial (status='plan'). Una sola request alcanza
    para pintar el calendario completo del mes.
    """
    _ensure_sede_access(user, sede_id)
    conn = db.get_conn()
    try:
        # 1) Bloques de sesiones guardadas
        sesion_rows = conn.execute(
            """
            SELECT sd.fecha::text AS fecha, sb.orden, sb.hora_inicio, sb.hora_fin,
                   sb.nombre_actividad, sb.se_ejecuto,
                   bt.codigo AS bloque_codigo, bt.nombre AS bloque_nombre, bt.color AS bloque_color,
                   bs.codigo AS subtipo_codigo, bs.nombre AS subtipo_nombre,
                   co.codigo AS clima_codigo, co.nombre AS clima_nombre, co.color AS clima_color
            FROM fundacion.sesion_dia sd
            JOIN fundacion.sesion_bloque sb ON sb.sesion_dia_id = sd.id
            JOIN fundacion.bloque_tipos bt ON bt.id = sb.bloque_tipo_id
            LEFT JOIN fundacion.bloque_subtipos bs ON bs.id = sb.bloque_subtipo_id
            LEFT JOIN fundacion.clima_opciones co ON co.id = sd.clima_opcion_id
            WHERE sd.sede_id = %s AND sd.nivel_id = %s
              AND sd.fecha BETWEEN %s AND %s
            ORDER BY sd.fecha, sb.orden
            """,
            (sede_id, nivel_id, desde, hasta),
        ).fetchall()

        sesion_por_fecha: dict[str, dict] = {}
        for r in sesion_rows:
            d = dict(r)
            if d.get("hora_inicio"): d["hora_inicio"] = str(d["hora_inicio"])
            if d.get("hora_fin"): d["hora_fin"] = str(d["hora_fin"])
            fecha = d["fecha"]
            if fecha not in sesion_por_fecha:
                sesion_por_fecha[fecha] = {
                    "fecha": fecha,
                    "status": "sesion",
                    "clima_codigo": d.pop("clima_codigo"),
                    "clima_nombre": d.pop("clima_nombre"),
                    "clima_color": d.pop("clima_color"),
                    "bloques": [],
                }
            else:
                # Limpiar clima fields que vienen repetidos en cada fila
                d.pop("clima_codigo", None); d.pop("clima_nombre", None); d.pop("clima_color", None)
            sesion_por_fecha[fecha]["bloques"].append(d)

        # 2) Bloques del plan oficial (solo para los días que no tienen sesión)
        plan_rows = conn.execute(
            """
            SELECT pd.fecha::text AS fecha, pb.orden, pb.hora_inicio, pb.hora_fin,
                   pb.nombre_actividad,
                   bt.codigo AS bloque_codigo, bt.nombre AS bloque_nombre, bt.color AS bloque_color,
                   bs.codigo AS subtipo_codigo, bs.nombre AS subtipo_nombre
            FROM fundacion.planificacion_dia pd
            JOIN fundacion.planificacion_bloque pb ON pb.planificacion_dia_id = pd.id
            JOIN fundacion.bloque_tipos bt ON bt.id = pb.bloque_tipo_id
            LEFT JOIN fundacion.bloque_subtipos bs ON bs.id = pb.bloque_subtipo_id
            WHERE pd.nivel_id = %s AND pd.fecha BETWEEN %s AND %s
            ORDER BY pd.fecha, pb.orden
            """,
            (nivel_id, desde, hasta),
        ).fetchall()

        plan_por_fecha: dict[str, dict] = {}
        for r in plan_rows:
            d = dict(r)
            if d.get("hora_inicio"): d["hora_inicio"] = str(d["hora_inicio"])
            if d.get("hora_fin"): d["hora_fin"] = str(d["hora_fin"])
            fecha = d["fecha"]
            if fecha in sesion_por_fecha:
                continue  # ya tiene sesión, ignoramos plan
            if fecha not in plan_por_fecha:
                plan_por_fecha[fecha] = {
                    "fecha": fecha,
                    "status": "plan",
                    "bloques": [],
                }
            plan_por_fecha[fecha]["bloques"].append(d)

        # 3) Combinar y devolver
        items = list(sesion_por_fecha.values()) + list(plan_por_fecha.values())
        items.sort(key=lambda x: x["fecha"])
        return {"items": items}
    finally:
        conn.close()


@router.get("/planificacion-oficial/listar")
async def listar_planificacion(
    nivel_id: int,
    desde: date_type,
    hasta: date_type,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Lista resumida de días planificados en un rango (para marcar en calendario)."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT pd.id, pd.fecha::text AS fecha, pd.numero_dia, pd.dia_semana,
                   COUNT(pb.id) AS bloques
            FROM fundacion.planificacion_dia pd
            LEFT JOIN fundacion.planificacion_bloque pb ON pb.planificacion_dia_id = pd.id
            WHERE pd.nivel_id = %s AND pd.fecha BETWEEN %s AND %s
            GROUP BY pd.id
            ORDER BY pd.fecha
            """,
            (nivel_id, desde, hasta),
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/planificacion-oficial")
async def get_planificacion_oficial(
    nivel_id: int,
    fecha: date_type,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Devuelve los bloques planificados oficialmente para un nivel y fecha
    según los docs de la fundación. Si no hay plan para ese día, 404."""
    conn = db.get_conn()
    try:
        dia = conn.execute(
            """
            SELECT id, nivel_id, fecha, numero_dia, dia_semana, fuente_doc
            FROM fundacion.planificacion_dia
            WHERE nivel_id = %s AND fecha = %s
            """,
            (nivel_id, fecha),
        ).fetchone()
        if not dia:
            raise HTTPException(status_code=404, detail="Sin planificación oficial para este día y nivel")

        bloques = conn.execute(
            """
            SELECT pb.*, bt.codigo AS bloque_tipo_codigo, bt.nombre AS bloque_tipo_nombre,
                   bs.codigo AS bloque_subtipo_codigo, bs.nombre AS bloque_subtipo_nombre,
                   COALESCE((
                       SELECT array_agg(c.id ORDER BY c.codigo)
                       FROM fundacion.planificacion_bloque_competencias pbc
                       JOIN fundacion.competencias c ON c.id = pbc.competencia_id
                       WHERE pbc.planificacion_bloque_id = pb.id
                   ), ARRAY[]::int[]) AS competencias_ids
            FROM fundacion.planificacion_bloque pb
            JOIN fundacion.bloque_tipos bt ON bt.id = pb.bloque_tipo_id
            LEFT JOIN fundacion.bloque_subtipos bs ON bs.id = pb.bloque_subtipo_id
            WHERE pb.planificacion_dia_id = %s
            ORDER BY pb.orden
            """,
            (dia["id"],),
        ).fetchall()

        out = dict(dia)
        if out.get("fecha"):
            out["fecha"] = out["fecha"].isoformat()
        out["bloques"] = [dict(b) for b in bloques]
        for b in out["bloques"]:
            if b.get("hora_inicio"):
                b["hora_inicio"] = str(b["hora_inicio"])
            if b.get("hora_fin"):
                b["hora_fin"] = str(b["hora_fin"])
        return out
    finally:
        conn.close()


@router.get("/catalogos/dominios")
async def get_dominios(user: dict = Depends(deps.require_permission("fundacion:read"))):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, codigo, nombre, color, orden FROM fundacion.competencia_dominios ORDER BY orden"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/catalogos/competencias")
async def get_competencias(user: dict = Depends(deps.require_permission("fundacion:read"))):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.codigo, c.descripcion, c.activo, c.orden,
                   d.id AS dominio_id, d.codigo AS dominio_codigo, d.nombre AS dominio_nombre, d.color AS dominio_color
            FROM fundacion.competencias c
            JOIN fundacion.competencia_dominios d ON d.id = c.dominio_id
            WHERE c.activo = TRUE
            ORDER BY d.orden, c.orden
            """
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/catalogos/bloque-tipos")
async def get_bloque_tipos(user: dict = Depends(deps.require_permission("fundacion:read"))):
    conn = db.get_conn()
    try:
        tipos = conn.execute(
            """
            SELECT id, codigo, nombre, descripcion, requiere_subtipo, permite_competencias,
                   color, icono, orden
            FROM fundacion.bloque_tipos WHERE activo = TRUE ORDER BY orden
            """
        ).fetchall()
        subtipos = conn.execute(
            """
            SELECT id, bloque_tipo_id, codigo, nombre, descripcion, orden
            FROM fundacion.bloque_subtipos WHERE activo = TRUE ORDER BY bloque_tipo_id, orden
            """
        ).fetchall()
        sub_por_tipo: dict[int, list] = {}
        for s in subtipos:
            sub_por_tipo.setdefault(s["bloque_tipo_id"], []).append(dict(s))
        items = []
        for t in tipos:
            d = dict(t)
            d["subtipos"] = sub_por_tipo.get(t["id"], [])
            items.append(d)
        return {"items": items}
    finally:
        conn.close()


@router.get("/catalogos/clima")
async def get_clima_opciones(user: dict = Depends(deps.require_permission("fundacion:read"))):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT id, codigo, nombre, descripcion, color, icono, orden FROM fundacion.clima_opciones WHERE activo = TRUE ORDER BY orden"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── Sesiones ────────────────────────────────────────────────────────────────

class MaterialIn(BaseModel):
    product_id: Optional[int] = None
    nombre_libre: Optional[str] = None
    cantidad_solicitada: Optional[float] = None
    cantidad_usada: Optional[float] = None
    notas: Optional[str] = None


class BloqueIn(BaseModel):
    orden: int
    bloque_tipo_id: int
    bloque_subtipo_id: Optional[int] = None
    actividad_id: Optional[int] = None     # FK al catálogo si la gestora eligió de ahí
    nombre_actividad: Optional[str] = None
    resultado_aprendizaje: Optional[str] = None
    hora_inicio: Optional[str] = None      # "HH:MM" o "HH:MM:SS"
    hora_fin: Optional[str] = None
    se_ejecuto: bool = True
    motivo_no_ejecucion: Optional[str] = None
    adaptacion: Optional[str] = None
    notas: Optional[str] = None
    competencias: List[int] = Field(default_factory=list)
    materiales: List[MaterialIn] = Field(default_factory=list)


class SesionIn(BaseModel):
    sede_id: int
    nivel_id: int
    fecha: date_type
    clima_opcion_id: Optional[int] = None
    situaciones_relevantes: Optional[str] = None
    estrategias_aplicadas: Optional[str] = None
    notas: Optional[str] = None
    cerrado: bool = False
    bloques: List[BloqueIn] = Field(default_factory=list)


def _sesion_to_dict(conn, sesion_id: int) -> dict:
    sd = conn.execute(
        """
        SELECT sd.*, co.codigo AS clima_codigo, co.nombre AS clima_nombre, co.color AS clima_color,
               n.codigo AS nivel_codigo, n.nombre AS nivel_nombre, n.color AS nivel_color
        FROM fundacion.sesion_dia sd
        LEFT JOIN fundacion.clima_opciones co ON co.id = sd.clima_opcion_id
        LEFT JOIN fundacion.niveles n ON n.id = sd.nivel_id
        WHERE sd.id = %s
        """,
        (sesion_id,),
    ).fetchone()
    if not sd:
        return None
    bloques = conn.execute(
        """
        SELECT sb.*, bt.codigo AS bloque_tipo_codigo, bt.nombre AS bloque_tipo_nombre,
               bs.codigo AS bloque_subtipo_codigo, bs.nombre AS bloque_subtipo_nombre
        FROM fundacion.sesion_bloque sb
        JOIN fundacion.bloque_tipos bt ON bt.id = sb.bloque_tipo_id
        LEFT JOIN fundacion.bloque_subtipos bs ON bs.id = sb.bloque_subtipo_id
        WHERE sb.sesion_dia_id = %s
        ORDER BY sb.orden
        """,
        (sesion_id,),
    ).fetchall()
    bloque_ids = [b["id"] for b in bloques]
    competencias_por_bloque: dict[int, list] = {bid: [] for bid in bloque_ids}
    materiales_por_bloque: dict[int, list] = {bid: [] for bid in bloque_ids}
    if bloque_ids:
        ph = ",".join(["%s"] * len(bloque_ids))
        comps = conn.execute(
            f"""
            SELECT sbc.sesion_bloque_id, c.id, c.codigo, c.descripcion,
                   d.codigo AS dominio_codigo, d.nombre AS dominio_nombre, d.color AS dominio_color
            FROM fundacion.sesion_bloque_competencias sbc
            JOIN fundacion.competencias c ON c.id = sbc.competencia_id
            JOIN fundacion.competencia_dominios d ON d.id = c.dominio_id
            WHERE sbc.sesion_bloque_id IN ({ph})
            ORDER BY d.orden, c.orden
            """,
            tuple(bloque_ids),
        ).fetchall()
        for c in comps:
            competencias_por_bloque[c["sesion_bloque_id"]].append({
                "id": c["id"], "codigo": c["codigo"], "descripcion": c["descripcion"],
                "dominio_codigo": c["dominio_codigo"], "dominio_nombre": c["dominio_nombre"],
                "dominio_color": c["dominio_color"],
            })
        mats = conn.execute(
            f"""
            SELECT sbm.id, sbm.sesion_bloque_id, sbm.product_id, sbm.nombre_libre,
                   sbm.cantidad_solicitada, sbm.cantidad_usada, sbm.notas,
                   p.name AS product_name, p.sku AS product_sku
            FROM fundacion.sesion_bloque_materiales sbm
            LEFT JOIN bodega.products p ON p.id = sbm.product_id
            WHERE sbm.sesion_bloque_id IN ({ph})
            """,
            tuple(bloque_ids),
        ).fetchall()
        for m in mats:
            materiales_por_bloque[m["sesion_bloque_id"]].append(dict(m))

    items = []
    for b in bloques:
        d = dict(b)
        # serializar time → str
        if d.get("hora_inicio"):
            d["hora_inicio"] = str(d["hora_inicio"])
        if d.get("hora_fin"):
            d["hora_fin"] = str(d["hora_fin"])
        d["competencias"] = competencias_por_bloque.get(b["id"], [])
        d["materiales"] = materiales_por_bloque.get(b["id"], [])
        items.append(d)
    out = dict(sd)
    if out.get("fecha"):
        out["fecha"] = out["fecha"].isoformat()
    out["bloques"] = items
    return out


@router.get("/sesiones")
async def list_sesiones(
    sede_id: int,
    nivel_id: Optional[int] = None,
    desde: Optional[date_type] = None,
    hasta: Optional[date_type] = None,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    _ensure_sede_access(user, sede_id)
    conn = db.get_conn()
    try:
        clauses = ["sd.sede_id = %s"]
        params: list = [sede_id]
        if nivel_id is not None:
            clauses.append("sd.nivel_id = %s")
            params.append(nivel_id)
        if desde:
            clauses.append("sd.fecha >= %s")
            params.append(desde)
        if hasta:
            clauses.append("sd.fecha <= %s")
            params.append(hasta)
        rows = conn.execute(
            f"""
            SELECT sd.id, sd.sede_id, sd.nivel_id, sd.fecha, sd.cerrado, sd.clima_opcion_id,
                   co.codigo AS clima_codigo, co.nombre AS clima_nombre,
                   n.codigo AS nivel_codigo, n.nombre AS nivel_nombre, n.color AS nivel_color,
                   COUNT(sb.id) AS bloques_total,
                   COUNT(sb.id) FILTER (WHERE sb.se_ejecuto) AS bloques_ejecutados
            FROM fundacion.sesion_dia sd
            LEFT JOIN fundacion.clima_opciones co ON co.id = sd.clima_opcion_id
            LEFT JOIN fundacion.niveles n ON n.id = sd.nivel_id
            LEFT JOIN fundacion.sesion_bloque sb ON sb.sesion_dia_id = sd.id
            WHERE {" AND ".join(clauses)}
            GROUP BY sd.id, co.codigo, co.nombre, n.codigo, n.nombre, n.color
            ORDER BY sd.fecha DESC
            """,
            tuple(params),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("fecha"):
                d["fecha"] = d["fecha"].isoformat()
            out.append(d)
        return {"items": out}
    finally:
        conn.close()


@router.get("/sesiones/by-fecha")
async def get_sesion_by_fecha(
    sede_id: int,
    fecha: date_type,
    nivel_id: int,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    """Devuelve la sesión de (sede, nivel, fecha) si existe; 404 si no."""
    _ensure_sede_access(user, sede_id)
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM fundacion.sesion_dia WHERE sede_id = %s AND nivel_id = %s AND fecha = %s",
            (sede_id, nivel_id, fecha),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sesión no existe")
        return _sesion_to_dict(conn, row["id"])
    finally:
        conn.close()


@router.get("/sesiones/{sesion_id}")
async def get_sesion(
    sesion_id: int,
    user: dict = Depends(deps.require_permission("fundacion:read")),
):
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT sede_id FROM fundacion.sesion_dia WHERE id = %s", (sesion_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sesión no existe")
        _ensure_sede_access(user, row["sede_id"])
        return _sesion_to_dict(conn, sesion_id)
    finally:
        conn.close()


@router.put("/sesiones")
@audit_action("UPSERT_FUNDACION_SESION", severity="info")
async def upsert_sesion(
    body: SesionIn,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    """Crea o actualiza una sesión completa (con todos sus bloques).

    Reemplaza los bloques existentes — el cliente debe mandar el estado final.
    """
    uid = _ensure_sede_access(user, body.sede_id)

    conn = db.get_conn()
    try:
        # Si la sesión existe y está cerrada → 409
        existing = conn.execute(
            """
            SELECT id, cerrado FROM fundacion.sesion_dia
            WHERE sede_id = %s AND nivel_id = %s AND fecha = %s
            """,
            (body.sede_id, body.nivel_id, body.fecha),
        ).fetchone()

        if existing and existing["cerrado"]:
            raise HTTPException(status_code=409, detail="Sesión cerrada, no se puede editar")

        if existing:
            sesion_id = existing["id"]
            conn.execute(
                """
                UPDATE fundacion.sesion_dia
                SET clima_opcion_id = %s,
                    situaciones_relevantes = %s,
                    estrategias_aplicadas = %s,
                    notas = %s,
                    cerrado = %s,
                    actualizado_por = %s,
                    actualizado_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (body.clima_opcion_id, body.situaciones_relevantes,
                 body.estrategias_aplicadas, body.notas, body.cerrado, uid, sesion_id),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO fundacion.sesion_dia (
                    sede_id, nivel_id, fecha, clima_opcion_id, situaciones_relevantes,
                    estrategias_aplicadas, notas, cerrado, creado_por, actualizado_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (body.sede_id, body.nivel_id, body.fecha, body.clima_opcion_id,
                 body.situaciones_relevantes, body.estrategias_aplicadas,
                 body.notas, body.cerrado, uid, uid),
            )
            sesion_id = cur.fetchone()["id"]

        # Reemplazar bloques: borrar todo (CASCADE limpia competencias y materiales)
        conn.execute("DELETE FROM fundacion.sesion_bloque WHERE sesion_dia_id = %s", (sesion_id,))

        for b in body.bloques:
            cur = conn.execute(
                """
                INSERT INTO fundacion.sesion_bloque (
                    sesion_dia_id, orden, bloque_tipo_id, bloque_subtipo_id, actividad_id,
                    nombre_actividad, resultado_aprendizaje, hora_inicio, hora_fin,
                    se_ejecuto, motivo_no_ejecucion, adaptacion, notas
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (sesion_id, b.orden, b.bloque_tipo_id, b.bloque_subtipo_id, b.actividad_id,
                 b.nombre_actividad, b.resultado_aprendizaje, b.hora_inicio, b.hora_fin,
                 b.se_ejecuto, b.motivo_no_ejecucion, b.adaptacion, b.notas),
            )
            bloque_id = cur.fetchone()["id"]

            for comp_id in b.competencias:
                conn.execute(
                    """
                    INSERT INTO fundacion.sesion_bloque_competencias (sesion_bloque_id, competencia_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                    """,
                    (bloque_id, comp_id),
                )

            for m in b.materiales:
                # Validar al menos uno: product_id o nombre_libre con contenido
                if m.product_id is None and (not m.nombre_libre or not m.nombre_libre.strip()):
                    continue
                conn.execute(
                    """
                    INSERT INTO fundacion.sesion_bloque_materiales (
                        sesion_bloque_id, product_id, nombre_libre,
                        cantidad_solicitada, cantidad_usada, notas
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (bloque_id, m.product_id,
                     m.nombre_libre.strip() if m.nombre_libre else None,
                     m.cantidad_solicitada, m.cantidad_usada, m.notas),
                )

        conn.commit()
        return _sesion_to_dict(conn, sesion_id)
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        logger.exception("Error guardando sesión")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.delete("/sesiones/{sesion_id}")
@audit_action("DELETE_FUNDACION_SESION", severity="warning")
async def delete_sesion(
    sesion_id: int,
    user: dict = Depends(deps.require_permission("fundacion:write")),
):
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT sede_id, cerrado FROM fundacion.sesion_dia WHERE id = %s", (sesion_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Sesión no existe")
        _ensure_sede_access(user, row["sede_id"])
        if row["cerrado"]:
            raise HTTPException(status_code=409, detail="Sesión cerrada, no se puede borrar")
        conn.execute("DELETE FROM fundacion.sesion_dia WHERE id = %s", (sesion_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()
