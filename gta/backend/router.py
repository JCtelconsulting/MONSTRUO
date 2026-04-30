from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, Dict, Any
from plataforma.core import db, deps
from plataforma.core.audit_decorator import audit_action
from gta.backend.models import (
    ProcesoCreate, ProcesoUpdate,
    SolicitudCreate, SolicitudUpdate,
    QuiebreCreate, QuiebreResolverBody,
)

router = APIRouter(prefix="/api/gta", tags=["gta"])


# ── Catálogo de procesos ───────────────────────────────────────────────────

@router.get("/procesos")
async def list_procesos(
    estado: Optional[str] = None,
    area: Optional[str] = None,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    conn = db.get_conn()
    try:
        q = """SELECT p.*,
                      (SELECT COUNT(*) FROM gta.solicitudes s WHERE s.proceso_id = p.id) AS solicitudes_count,
                      COALESCE(json_array_length(p.pasos_definicion::json), 0) AS pasos_count
               FROM gta.procesos p WHERE 1=1"""
        params: list = []
        if estado:
            q += " AND p.estado = %s"
            params.append(estado)
        if area:
            q += " AND p.area = %s"
            params.append(area)
        q += " ORDER BY p.area, p.nombre"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/procesos/{pid}")
async def get_proceso(pid: int, user: dict = Depends(deps.require_permission("gta:read"))):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM gta.procesos WHERE id = %s", [pid]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")
        return dict(row)
    finally:
        conn.close()


@router.post("/procesos")
@audit_action("GTA_CREATE_PROCESO", severity="info")
async def create_proceso(
    proceso: ProcesoCreate,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    conn = db.get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO gta.procesos
               (nombre, area, descripcion, sla_horas, icono, pasos_definicion, campos_formulario, estado, creado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (proceso.nombre, proceso.area, proceso.descripcion, proceso.sla_horas,
             proceso.icono, proceso.pasos_definicion or '[]', proceso.campos_formulario or '[]',
             proceso.estado or 'activo', user.get("username")),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return {"ok": True, "id": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.put("/procesos/{pid}")
@audit_action("GTA_UPDATE_PROCESO", severity="info")
async def update_proceso(
    pid: int,
    update: ProcesoUpdate,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM gta.procesos WHERE id = %s", [pid]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")
        fields = {k: v for k, v in update.model_dump().items() if v is not None}
        if not fields:
            raise HTTPException(status_code=400, detail="Sin campos para actualizar")
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        conn.execute(
            f"UPDATE gta.procesos SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            list(fields.values()) + [pid],
        )
        conn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── Solicitudes ────────────────────────────────────────────────────────────

@router.get("/solicitudes")
async def list_solicitudes(
    estado: Optional[str] = None,
    area: Optional[str] = None,
    prioridad: Optional[str] = None,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    conn = db.get_conn()
    try:
        q = """SELECT s.*, p.nombre AS proceso_nombre, p.sla_horas, p.icono AS proceso_icono
               FROM gta.solicitudes s
               LEFT JOIN gta.procesos p ON p.id = s.proceso_id
               WHERE 1=1"""
        params: list = []

        # Filtro por múltiples estados separados por coma (ej: pendiente,en_progreso)
        if estado:
            estados = [e.strip() for e in estado.split(",") if e.strip()]
            placeholders = ",".join(["%s"] * len(estados))
            q += f" AND s.estado IN ({placeholders})"
            params.extend(estados)
        if area:
            q += " AND s.area = %s"
            params.append(area)
        if prioridad:
            q += " AND s.prioridad = %s"
            params.append(prioridad)

        # Usuarios no admin solo ven sus solicitudes o las de su área
        role = (user.get("role") or "").lower()
        if role not in ("admin", "gerencia"):
            q += " AND (s.creado_por = %s OR s.area = ANY(%s::text[]))"
            # Mapear rol a área
            area_map = {
                "redes": "redes", "sistemas": "sistemas", "finance": "finanzas",
                "warehouse": "bodega", "ops": "sistemas",
            }
            user_area = area_map.get(role, "")
            params.extend([user.get("username"), [user_area] if user_area else []])

        q += " ORDER BY s.created_at DESC"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/solicitudes/{sid}")
async def get_solicitud(sid: int, user: dict = Depends(deps.require_permission("gta:read"))):
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT s.*, p.nombre AS proceso_nombre, p.sla_horas, p.pasos_definicion, p.icono AS proceso_icono
               FROM gta.solicitudes s
               LEFT JOIN gta.procesos p ON p.id = s.proceso_id
               WHERE s.id = %s""",
            [sid],
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        return dict(row)
    finally:
        conn.close()


@router.post("/solicitudes")
@audit_action("GTA_CREATE_SOLICITUD", severity="info")
async def create_solicitud(
    solicitud: SolicitudCreate,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    conn = db.get_conn()
    try:
        # Copiar pasos_definicion del proceso como estado inicial (todos pendientes)
        proc = conn.execute(
            "SELECT pasos_definicion FROM gta.procesos WHERE id = %s", [solicitud.proceso_id]
        ).fetchone()
        if not proc:
            raise HTTPException(status_code=404, detail="Proceso no encontrado")

        import json
        pasos_def = proc["pasos_definicion"] or "[]"
        try:
            pasos_list = json.loads(pasos_def)
        except Exception:
            pasos_list = []
        pasos_estado = json.dumps([{"completado": False, "bloqueado": False} for _ in pasos_list])

        cur = conn.execute(
            """INSERT INTO gta.solicitudes
               (proceso_id, titulo, descripcion, area, prioridad, creado_por, pasos_estado, campos_extra)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (solicitud.proceso_id, solicitud.titulo, solicitud.descripcion,
             solicitud.area, solicitud.prioridad or "media", user.get("username"),
             pasos_estado, solicitud.campos_extra or "{}"),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return {"ok": True, "id": new_id}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.patch("/solicitudes/{sid}")
async def update_solicitud(
    sid: int,
    update: SolicitudUpdate,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM gta.solicitudes WHERE id = %s", [sid]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        fields = {k: v for k, v in update.model_dump().items() if v is not None}
        if not fields:
            return {"ok": True}
        set_clause = ", ".join(f"{k} = %s" for k in fields)
        conn.execute(
            f"UPDATE gta.solicitudes SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            list(fields.values()) + [sid],
        )
        conn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/solicitudes/{sid}/pasos/{paso_idx}/completar")
async def completar_paso(
    sid: int,
    paso_idx: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    return await _toggle_paso(sid, paso_idx, {"completado": True, "bloqueado": False})


@router.post("/solicitudes/{sid}/pasos/{paso_idx}/bloquear")
async def bloquear_paso(
    sid: int,
    paso_idx: int,
    body: Dict[str, Any],
    user: dict = Depends(deps.require_permission("gta:read")),
):
    return await _toggle_paso(sid, paso_idx, {"completado": False, "bloqueado": True, "motivo": body.get("motivo", "")})


async def _toggle_paso(sid: int, paso_idx: int, new_state: dict):
    import json
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT pasos_estado FROM gta.solicitudes WHERE id = %s", [sid]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        try:
            pasos = json.loads(row["pasos_estado"] or "[]")
        except Exception:
            pasos = []
        while len(pasos) <= paso_idx:
            pasos.append({"completado": False, "bloqueado": False})
        pasos[paso_idx].update(new_state)

        # Auto-completar solicitud si todos los pasos están completos
        todos_completos = all(p.get("completado") for p in pasos)
        nuevo_estado = "completado" if todos_completos else None

        update_q = "UPDATE gta.solicitudes SET pasos_estado = %s, updated_at = CURRENT_TIMESTAMP"
        params = [json.dumps(pasos)]
        if nuevo_estado:
            update_q += ", estado = %s"
            params.append(nuevo_estado)
        update_q += " WHERE id = %s"
        params.append(sid)
        conn.execute(update_q, params)
        conn.commit()
        return {"ok": True, "auto_completado": todos_completos}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/solicitudes/{sid}/comentarios")
async def get_comentarios(sid: int, user: dict = Depends(deps.require_permission("gta:read"))):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM gta.comentarios_solicitudes WHERE solicitud_id = %s ORDER BY created_at ASC", [sid]
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/solicitudes/{sid}/comentarios")
async def add_comentario(
    sid: int,
    body: Dict[str, Any],
    user: dict = Depends(deps.require_permission("gta:read")),
):
    texto = (body.get("texto") or "").strip()
    if not texto:
        raise HTTPException(status_code=400, detail="Comentario vacío")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO gta.comentarios_solicitudes (solicitud_id, autor, texto) VALUES (%s,%s,%s) RETURNING id",
            [sid, user.get("username"), texto],
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return {"ok": True, "id": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── Quiebres ───────────────────────────────────────────────────────────────

@router.get("/quiebres")
async def list_quiebres(
    estado: Optional[str] = "abierto",
    area: Optional[str] = None,
    tipo: Optional[str] = None,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    conn = db.get_conn()
    try:
        q = "SELECT * FROM gta.quiebres WHERE 1=1"
        params: list = []
        if estado:
            q += " AND estado = %s"
            params.append(estado)
        if area:
            q += " AND area = %s"
            params.append(area)
        if tipo:
            q += " AND tipo = %s"
            params.append(tipo)
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/quiebres")
@audit_action("GTA_CREATE_QUIEBRE", severity="warning")
async def create_quiebre(
    quiebre: QuiebreCreate,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    conn = db.get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO gta.quiebres (descripcion, area, tipo, solicitud_id, reportado_por)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (quiebre.descripcion, quiebre.area, quiebre.tipo or "sin_proceso",
             quiebre.solicitud_id, user.get("username")),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
        return {"ok": True, "id": new_id}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/quiebres/{qid}/resolver")
@audit_action("GTA_RESOLVER_QUIEBRE", severity="info")
async def resolver_quiebre(
    qid: int,
    body: QuiebreResolverBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT id FROM gta.quiebres WHERE id = %s", [qid]).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Quiebre no encontrado")
        conn.execute(
            "UPDATE gta.quiebres SET estado = 'resuelto', nota_resolucion = %s, resuelto_por = %s, resuelto_at = CURRENT_TIMESTAMP WHERE id = %s",
            [body.nota, user.get("username"), qid],
        )
        conn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ── Stats ──────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(user: dict = Depends(deps.require_permission("gta:read"))):
    conn = db.get_conn()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) FILTER (WHERE estado = 'pendiente')                        AS pendientes,
                COUNT(*) FILTER (WHERE estado = 'en_progreso')                      AS en_progreso,
                COUNT(*) FILTER (WHERE estado = 'completado')                       AS completadas,
                COUNT(*) FILTER (WHERE estado = 'completado'
                                   AND updated_at::date = CURRENT_DATE)             AS completadas_hoy,
                COUNT(*) FILTER (WHERE estado = 'bloqueado')                        AS bloqueadas,
                COUNT(*)                                                             AS total
            FROM gta.solicitudes
            WHERE estado NOT IN ('cancelado','completado') OR updated_at::date = CURRENT_DATE
        """).fetchone()
        quiebres = conn.execute(
            "SELECT COUNT(*) AS total FROM gta.quiebres WHERE estado = 'abierto'"
        ).fetchone()
        result = dict(row)
        result["quiebres_abiertos"] = quiebres["total"] if quiebres else 0
        return result
    finally:
        conn.close()
