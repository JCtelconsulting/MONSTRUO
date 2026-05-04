from fastapi import APIRouter, HTTPException, Depends, Request, File, UploadFile
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any
from plataforma.core import db, deps
from plataforma.core.audit_decorator import audit_action
from gta.backend.models import (
    ProcesoCreate, ProcesoUpdate,
    SolicitudCreate, SolicitudUpdate,
    QuiebreCreate, QuiebreResolverBody,
    FlujoCrear, TareaCompletarBody, TareaValidarBody,
    AyudaCrear, AyudaResponder,
)
from gta.backend.services import catalogo as catalogo_service
from gta.backend.services import flujos as flujos_service
from gta.backend.services import procesos as procesos_service

router = APIRouter(prefix="/api/gta", tags=["gta"])


# ── Procesos (biblioteca unificada: definiciones + archivos + historial) ───

@router.get("/procesos")
async def list_procesos(
    estado: Optional[str] = "activo",
    area: Optional[str] = None,
    subarea: Optional[str] = None,
    busqueda: Optional[str] = None,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    return procesos_service.listar_procesos(
        area_code=area, subarea_code=subarea,
        estado=estado, busqueda=busqueda,
    )


@router.get("/procesos/{pid}")
async def get_proceso(pid: int, user: dict = Depends(deps.require_permission("gta:read"))):
    proc = procesos_service.get_proceso(pid)
    if not proc:
        raise HTTPException(status_code=404, detail="proceso no encontrado")
    return proc


@router.post("/procesos")
async def crear_proceso(
    proceso: ProcesoCreate,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Crea un proceso nuevo (con o sin definición ejecutable)."""
    try:
        # pasos_definicion viene como JSON string en ProcesoCreate; lo parseamos
        import json as _json
        pasos = []
        if proceso.pasos_definicion:
            try:
                pasos = _json.loads(proceso.pasos_definicion)
            except Exception:
                pasos = []
        return procesos_service.crear_proceso(
            nombre=proceso.nombre,
            area=proceso.area,
            descripcion=proceso.descripcion or "",
            pasos_definicion=pasos,
            sla_horas=proceso.sla_horas,
            icono=proceso.icono or "fa-tasks",
            creado_por=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/procesos/{pid}")
async def actualizar_proceso(
    pid: int,
    update: ProcesoUpdate,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    import json as _json
    pasos = None
    if update.pasos_definicion is not None:
        try:
            pasos = _json.loads(update.pasos_definicion)
        except Exception:
            pasos = []
    try:
        return procesos_service.actualizar_proceso(
            pid,
            actor=user["username"],
            nombre=update.nombre,
            area=update.area,
            descripcion=update.descripcion,
            pasos_definicion=pasos,
            sla_horas=update.sla_horas,
            icono=update.icono,
            estado=update.estado,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/procesos/{pid}/comentarios")
async def agregar_comentario_proceso(
    pid: int,
    body: dict,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """body: {texto, tipo} — tipo: nota | cambio | decision"""
    try:
        return procesos_service.agregar_comentario(
            proceso_id=pid,
            autor=user["username"],
            texto=str(body.get("texto") or "").strip(),
            tipo=str(body.get("tipo") or "nota"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/procesos/{pid}/quiebres")
async def reportar_quiebre_proceso(
    pid: int,
    body: dict,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """body: {descripcion, area, tipo?}"""
    try:
        return procesos_service.reportar_quiebre(
            proceso_id=pid,
            descripcion=str(body.get("descripcion") or ""),
            area=str(body.get("area") or ""),
            tipo=str(body.get("tipo") or "sin_proceso"),
            reportado_por=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/procesos/{pid}/archivo")
async def subir_archivo_proceso(
    pid: int,
    file: "UploadFile" = File(...),
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Sube un archivo al proceso (lo guarda en gta/data/procesos/<area>/<sub>/)."""
    try:
        contenido = await file.read()
        return procesos_service.guardar_archivo_subido(
            proceso_id=pid,
            filename=file.filename or "archivo",
            contenido=contenido,
            actor=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/procesos/seed-from-files")
async def seed_procesos(user: dict = Depends(deps.require_permission("admin.settings"))):
    """Endpoint admin: crea registros gta.procesos a partir de los archivos en
    gta/data/procesos/. Idempotente: omite los ya registrados."""
    return procesos_service.seed_procesos_from_files(actor=user["username"])


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


# ── Catálogo de procesos en disco (gta/data/procesos) ──────────────────────

@router.get("/catalogo")
async def get_catalogo(user: dict = Depends(deps.require_permission("gta:read"))):
    """Devuelve el índice de procesos descargados desde Drive (gta/data/procesos)."""
    return catalogo_service.scan_catalog()


@router.get("/catalogo/download")
async def download_catalogo_file(
    path: str,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Descarga un archivo del catálogo. El path es relativo a gta/data/procesos."""
    safe = catalogo_service.resolve_safe_path(path)
    if not safe:
        raise HTTPException(status_code=404, detail="archivo no encontrado o ruta inválida")
    return FileResponse(
        path=str(safe),
        filename=safe.name,
        media_type="application/octet-stream",
    )


# ── Flujos cross-área ──────────────────────────────────────────────────────

def _es_admin(user: dict) -> bool:
    """admin = role admin O permiso global '*' O username del admin del sistema."""
    role = str(user.get("role") or "").lower()
    if role == "admin":
        return True
    username = str(user.get("username") or "")
    if username == "sistemas@telconsulting.cl":
        return True
    return False


@router.post("/flujos")
async def crear_flujo(body: FlujoCrear, user: dict = Depends(deps.require_permission("gta:write"))):
    """Inicia un flujo nuevo: desde un proceso del catálogo o un flujo libre."""
    try:
        return flujos_service.crear_flujo(
            iniciado_por=user["username"],
            titulo=body.titulo,
            descripcion=body.descripcion or "",
            proceso_id=body.proceso_id,
            datos_formulario=body.datos_formulario,
            pasos_libres=body.pasos_libres,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/flujos")
async def listar_flujos(
    estado: Optional[str] = None,
    area: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    return flujos_service.listar_flujos(
        actor=user["username"],
        es_admin=_es_admin(user),
        rol_usuario=str(user.get("role") or ""),
        estado=estado,
        area_code=area,
        limit=limit,
        offset=offset,
    )


@router.get("/flujos/{flujo_id}")
async def ver_flujo(flujo_id: int, user: dict = Depends(deps.require_permission("gta:read"))):
    flujo = flujos_service.get_flujo(flujo_id)
    if not flujo:
        raise HTTPException(status_code=404, detail="flujo no encontrado")
    return flujo


@router.get("/flujos/{flujo_id}/eventos")
async def listar_eventos(
    flujo_id: int,
    limit: int = 100,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    return flujos_service.get_eventos(flujo_id, limit=limit)


@router.post("/flujo-tareas/{tarea_id}/completar")
async def completar_tarea(
    tarea_id: int,
    body: TareaCompletarBody,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """El ejecutor (líder del área asignada) marca su tarea como hecha.
    Pasa a estado 'por_validar' hasta que el iniciador del flujo confirme.
    """
    try:
        return flujos_service.marcar_ejecutor_completo(
            tarea_id=tarea_id,
            actor=user["username"],
            campos_completados=body.campos_completados,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/flujo-tareas/{tarea_id}/validar")
async def validar_tarea(
    tarea_id: int,
    body: TareaValidarBody,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """El iniciador del flujo (o el jefe) valida o rechaza una tarea en 'por_validar'."""
    try:
        return flujos_service.validar_tarea(
            tarea_id=tarea_id,
            actor=user["username"],
            aceptada=body.aceptada,
            comentario=body.comentario or "",
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/flujo-tareas/{tarea_id}/ayuda")
async def pedir_ayuda(
    tarea_id: int,
    body: AyudaCrear,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Pedir ayuda a otra área. Si bloquea_sla=True, pausa el SLA hasta la respuesta."""
    try:
        return flujos_service.pedir_ayuda(
            tarea_id=tarea_id,
            pedido_por=user["username"],
            pedido_a_area=body.pedido_a_area,
            pedido_a_user=body.pedido_a_user or "",
            mensaje=body.mensaje,
            bloquea_sla=body.bloquea_sla,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/flujo-ayudas/{ayuda_id}/responder")
async def responder_ayuda(
    ayuda_id: int,
    body: AyudaResponder,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        return flujos_service.responder_ayuda(
            ayuda_id=ayuda_id,
            respondido_por=user["username"],
            respuesta=body.respuesta,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/metricas")
async def get_metricas(user: dict = Depends(deps.require_permission("gta:read"))):
    """Métricas globales: tiempos por persona, por área, totales."""
    return flujos_service.metricas_globales()
