from fastapi import APIRouter, HTTPException, Depends, Request, File, UploadFile
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any
from plataforma.core import db, deps
from plataforma.core.audit_decorator import audit_action
from gta.backend.models import (
    ProcesoCreate, ProcesoUpdate,
    SolicitudCreate, SolicitudUpdate,
    QuiebreCreate, QuiebreResolverBody,
    FlujoCrear,
    TareaCreate, TareaCerrarBody, TareaDevolverBody, TareaReasignarBody, TareaLiberarBody,
    QuiebreReporteBody,
    ColaboradorAgregar, ColaboradorQuitar,
    MembresiaAsignar, MembresiaCerrar,
)
from gta.backend.services import catalogo as catalogo_service
from gta.backend.services import flujos as flujos_service
from gta.backend.services import procesos as procesos_service
from gta.backend.services import tareas as tareas_service
from gta.backend.services import membresias as membresias_service
from gta.backend.services import preview as preview_service
from gta.backend.services import adjuntos as adjuntos_service
from gta.backend.services import quiebres as quiebres_service
from gta.backend.services import comentarios as comentarios_service
from gta.backend.services import flujo_eventos as flujo_eventos_service
from gta.backend.services import avisos as avisos_service

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
    campos = None
    if update.campos_formulario is not None:
        try:
            campos = _json.loads(update.campos_formulario)
        except Exception:
            campos = []
    try:
        return procesos_service.actualizar_proceso(
            pid,
            actor=user["username"],
            nombre=update.nombre,
            area=update.area,
            subarea_code=update.subarea_code,
            descripcion=update.descripcion,
            pasos_definicion=pasos,
            campos_formulario=campos,
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


@router.get("/areas")
async def listar_areas_para_ui(user: dict = Depends(deps.require_permission("gta:read"))):
    """Lista áreas y subáreas activas (sólo lectura, accesible a cualquier usuario
    con permiso gta:read). El endpoint /api/config/gta/areas requiere admin.settings."""
    conn = db.get_conn()
    try:
        areas = conn.execute(
            "SELECT code, label, lider_username, lider_nombre, es_externa, activo, orden "
            "FROM gta.areas WHERE activo = TRUE ORDER BY orden, code"
        ).fetchall()
        subs = conn.execute(
            "SELECT id, area_code, code, label, lider_username, lider_nombre, activo, orden "
            "FROM gta.subareas WHERE activo = TRUE ORDER BY area_code, orden, code"
        ).fetchall()

        sub_by_area: dict = {}
        for s in subs:
            sub_by_area.setdefault(s["area_code"], []).append({
                "id": int(s["id"]),
                "area_code": s["area_code"],
                "code": s["code"],
                "label": s["label"],
                "lider_username": s.get("lider_username") or "",
                "lider_nombre": s.get("lider_nombre") or "",
                "activo": True,
                "orden": int(s.get("orden") or 99),
            })

        items = []
        for a in areas:
            items.append({
                "code": a["code"],
                "label": a["label"],
                "lider_username": a.get("lider_username") or "",
                "lider_nombre": a.get("lider_nombre") or "",
                "es_externa": bool(a.get("es_externa")),
                "activo": True,
                "orden": int(a.get("orden") or 99),
                "subareas": sub_by_area.get(a["code"], []),
            })
        return {"items": items}
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


@router.get("/catalogo/preview-meta")
async def get_preview_meta(
    path: str,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Indica al frontend cómo previsualizar este documento.

    Respuesta: {mode: 'iframe'|'image'|'text'|'download', mime?: ...}
      - iframe → PDF: usar <iframe src=download_url>
      - image  → imagen: <img>
      - text   → llamar /catalogo/preview-text para extraer texto plano
      - download → no se puede previsualizar, solo descargar
    """
    safe = catalogo_service.resolve_safe_path(path)
    if not safe:
        raise HTTPException(status_code=404, detail="archivo no encontrado o ruta inválida")
    return preview_service.detectar_render_mode(path)


@router.get("/catalogo/preview-text")
async def get_preview_text(
    path: str,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Extrae texto plano de Word/Excel/PowerPoint/TXT/MD para preview en modal.

    Respuesta: {text, truncated, total_chars, kind}.
    Si la extensión no soporta extracción, devuelve 422.
    """
    safe = catalogo_service.resolve_safe_path(path)
    if not safe:
        raise HTTPException(status_code=404, detail="archivo no encontrado o ruta inválida")
    try:
        return preview_service.extraer_texto(path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extrayendo texto: {e}")


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
    """Inicia un flujo nuevo: desde un proceso del catálogo o un flujo libre.

    Permisos:
    - Admin global puede iniciar cualquier flujo.
    - Si viene proceso_id: el actor debe ser miembro vigente del área dueña
      del proceso (cualquier subárea de esa área alcanza). Esto refleja
      que "el proceso es del área, así que cualquiera del área lo arranca".
    - pasos_libres (sin proceso_id) sigue libre — admin se valida por el role.
    """
    if body.proceso_id and not _es_admin(user):
        from plataforma.core import db as _db
        actor_username = user.get("username", "")
        conn = _db.get_conn()
        try:
            row = conn.execute(
                "SELECT area FROM gta.procesos WHERE id = %s",
                (body.proceso_id,),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="proceso no encontrado")
            area_proceso = row["area"]

            actor_row = conn.execute(
                "SELECT id FROM auth.users WHERE username = %s",
                (actor_username,),
            ).fetchone()
            if not actor_row:
                raise HTTPException(status_code=403, detail="usuario no resoluble")
            actor_id = int(actor_row["id"])

            # ¿Tiene membresía vigente en alguna subárea de esa área?
            membresia = conn.execute(
                """SELECT 1
                   FROM gta.area_membresias m
                   JOIN gta.subareas s ON s.id = m.subarea_id
                   WHERE m.usuario_id = %s
                     AND s.area_code = %s
                     AND m.hasta IS NULL
                   LIMIT 1""",
                (actor_id, area_proceso),
            ).fetchone()
        finally:
            conn.close()

        if not membresia:
            raise HTTPException(
                status_code=403,
                detail=f"Solo miembros del área '{area_proceso}' pueden iniciar este proceso.",
            )

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
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Lista de flujos para el tablero. Después del refactor del modelo
    único, los flujos viven dentro de gta.tareas.flujo_id; este endpoint
    los agrupa con sus métricas de avance."""
    return flujos_service.listar_flujos(estado=estado, area_code=area)


@router.get("/flujos/{flujo_id}")
async def ver_flujo(flujo_id: str, user: dict = Depends(deps.require_permission("gta:read"))):
    """Detalle de un flujo: tareas con su estado, dependencias, datos cargados."""
    flujo = flujos_service.get_flujo(flujo_id)
    if not flujo:
        raise HTTPException(status_code=404, detail="flujo no encontrado")
    return flujo


@router.get("/flujos/{flujo_id}/timeline")
async def ver_timeline_flujo(
    flujo_id: str,
    limit: int = 200,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Timeline de eventos del flujo (cierres, devoluciones, quiebres) en orden cronológico."""
    return {"items": flujo_eventos_service.listar_de_flujo(flujo_id, limit=limit)}


@router.get("/metricas")
async def get_metricas(user: dict = Depends(deps.require_permission("gta:read"))):
    """Métricas globales: tiempos por persona, por área, totales."""
    return flujos_service.metricas_globales()


# ── Tareas (modelo área-céntrico) ─────────────────────────────────────

@router.get("/tareas/bandeja")
async def listar_bandeja(
    subarea_id: Optional[int] = None,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Tareas sin responsable vigente.

    - Con `subarea_id`: filtra a esa subárea (cualquiera con gta:read puede consultar).
    - Sin `subarea_id`:
      - Admin global → ve TODAS las tareas sin responsable de todo el sistema.
      - Usuario común → ve solo la unión de sus subáreas con membresía vigente.
    """
    if subarea_id is not None:
        return {"items": tareas_service.listar_bandeja_subarea(subarea_id)}
    if _es_admin(user):
        return {"items": tareas_service.listar_bandeja_global()}
    uid = tareas_service.usuario_id_de_username(user["username"])
    return {"items": tareas_service.listar_bandeja_de_usuario(uid)}


@router.get("/tareas/mias")
async def listar_mis_tareas(
    incluir_cerradas: bool = False,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Tareas donde el actor es responsable vigente. (No es vista global —
    incluso admin solo ve las suyas reales)."""
    uid = tareas_service.usuario_id_de_username(user["username"])
    return {"items": tareas_service.listar_mis_tareas(uid, incluir_cerradas=incluir_cerradas)}


@router.get("/tareas/colaboro")
async def listar_donde_colaboro(
    incluir_cerradas: bool = False,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Tareas donde el actor es co-responsable o ayuda vigente."""
    uid = tareas_service.usuario_id_de_username(user["username"])
    return {"items": tareas_service.listar_donde_colaboro(uid, incluir_cerradas=incluir_cerradas)}


@router.get("/tareas/subarea/{subarea_id}")
async def listar_tareas_subarea(
    subarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Todas las tareas de una subárea (cualquier estado)."""
    return {"items": tareas_service.listar_todas_subarea(subarea_id)}


@router.get("/tareas/{tarea_id}")
async def get_tarea(
    tarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    t = tareas_service.get_tarea(tarea_id)
    if not t:
        raise HTTPException(status_code=404, detail="tarea no encontrada")
    return t


@router.post("/tareas")
@audit_action("GTA_CREATE_TAREA", severity="info")
async def crear_tarea(
    body: TareaCreate,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        uid = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.crear_tarea(
            subarea_id=body.subarea_id,
            titulo=body.titulo,
            descripcion=body.descripcion,
            creado_por=uid,
            proceso_id=body.proceso_id,
            flujo_tarea_id=body.flujo_tarea_id,
            tipo=body.tipo,
            prioridad=body.prioridad or "media",
            sla_horas=body.sla_horas,
            tags=body.tags,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/tomar")
@audit_action("GTA_TOMAR_TAREA", severity="info")
async def tomar_tarea(
    tarea_id: int,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        uid = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.tomar_tarea(
            tarea_id,
            usuario_id=uid,
            bypass_membresia=_es_admin(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/liberar")
@audit_action("GTA_LIBERAR_TAREA", severity="info")
async def liberar_tarea(
    tarea_id: int,
    body: TareaLiberarBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        uid = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.liberar_tarea(tarea_id, usuario_id=uid, motivo=body.motivo)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/reasignar")
@audit_action("GTA_REASIGNAR_TAREA", severity="info")
async def reasignar_tarea(
    tarea_id: int,
    body: TareaReasignarBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Reasigna el responsable. Permitido para líderes vigentes de la
    subárea o admins."""
    try:
        actor_id = tareas_service.usuario_id_de_username(user["username"])
        # Admin bypass
        if not _es_admin(user):
            tarea = tareas_service.get_tarea(tarea_id)
            if not tarea:
                raise HTTPException(status_code=404, detail="tarea no encontrada")
            sub_id = tarea["subarea_id"]
            from plataforma.core import db as _db
            conn = _db.get_conn()
            try:
                row = conn.execute(
                    """SELECT 1 FROM gta.area_membresias
                       WHERE usuario_id = %s AND subarea_id = %s
                         AND rol = 'lider' AND hasta IS NULL""",
                    (actor_id, sub_id),
                ).fetchone()
            finally:
                conn.close()
            if not row:
                raise HTTPException(
                    status_code=403,
                    detail="solo el líder vigente de la subárea o un admin puede reasignar",
                )
        return tareas_service.reasignar_responsable(
            tarea_id,
            nuevo_usuario_id=body.nuevo_usuario_id,
            asignado_por=actor_id,
            motivo=body.motivo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/colaboradores")
@audit_action("GTA_TAREA_ADD_COLAB", severity="info")
async def agregar_colaborador(
    tarea_id: int,
    body: ColaboradorAgregar,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        actor_id = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.agregar_colaborador(
            tarea_id,
            usuario_id=body.usuario_id,
            rol=body.rol,
            asignado_por=actor_id,
            motivo=body.motivo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tareas/{tarea_id}/colaboradores")
@audit_action("GTA_TAREA_DEL_COLAB", severity="info")
async def quitar_colaborador(
    tarea_id: int,
    body: ColaboradorQuitar,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        return tareas_service.quitar_colaborador(
            tarea_id, usuario_id=body.usuario_id, rol=body.rol,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/cerrar")
@audit_action("GTA_CERRAR_TAREA", severity="info")
async def cerrar_tarea(
    tarea_id: int,
    body: TareaCerrarBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        uid = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.cerrar_tarea(
            tarea_id,
            cerrado_por=uid,
            reporte=body.reporte,
            datos_formulario=body.datos_formulario,
            bypass_responsable=_es_admin(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/devolver")
@audit_action("GTA_DEVOLVER_TAREA", severity="info")
async def devolver_tarea(
    tarea_id: int,
    body: TareaDevolverBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Rechaza una tarea de validación y reabre el paso destino para corregir."""
    try:
        uid = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.devolver_tarea(
            tarea_id,
            devuelto_por=uid,
            motivo=body.motivo,
            paso_destino=body.paso_destino,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/borrador")
@audit_action("GTA_GUARDAR_BORRADOR", severity="info")
async def guardar_borrador(
    tarea_id: int,
    body: dict,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Guarda datos parciales del formulario sin cerrar la tarea.

    Útil para cargar lo que ya se tiene mientras se busca el resto.
    No valida obligatorios. Solo el responsable vigente (o admin) puede.
    """
    try:
        uid = tareas_service.usuario_id_de_username(user["username"])
        return tareas_service.guardar_borrador_formulario(
            tarea_id,
            usuario_id=uid,
            datos_formulario=body.get("datos_formulario") or {},
            bypass_responsable=_es_admin(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Quiebres dirigidos desde una tarea hacia otra área del flujo ──────

@router.get("/tareas/{tarea_id}/quiebres/areas-disponibles")
async def areas_disponibles_quiebre(
    tarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Áreas del flujo a las que se puede reportar un quiebre desde esta tarea
    (excluye la propia área de la tarea)."""
    try:
        return {"items": quiebres_service.areas_disponibles_para_quiebre(tarea_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tareas/{tarea_id}/quiebres")
async def listar_quiebres_de_tarea(
    tarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Quiebres del flujo al que pertenece la tarea (visibles desde cualquier paso)."""
    return {"items": quiebres_service.listar_de_tarea(tarea_id)}


@router.post("/tareas/{tarea_id}/quiebres")
@audit_action("GTA_REPORTAR_QUIEBRE_TAREA", severity="warning")
async def reportar_quiebre_desde_tarea(
    tarea_id: int,
    body: QuiebreReporteBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Reporta un quiebre desde la tarea hacia un área del flujo. La tarea
    queda 'esperando_quiebre' hasta que esa área lo resuelva."""
    try:
        return quiebres_service.reportar_desde_tarea(
            tarea_id=tarea_id,
            area_destino=body.area_destino,
            descripcion=body.descripcion,
            tipo=body.tipo,
            reportado_por=user["username"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/quiebres/mios")
async def listar_quiebres_para_mi_area(
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Quiebres abiertos dirigidos a las áreas vigentes del usuario.
    Admin ve todos los quiebres abiertos sin filtro de área."""
    uid = tareas_service.usuario_id_de_username(user["username"])
    codes = membresias_service.area_codes_de_usuario(uid)
    es_admin = _es_admin(user)
    items = quiebres_service.listar_pendientes_para_areas(codes, todos=es_admin)
    return {"items": items, "areas": codes, "es_admin": es_admin}


@router.post("/quiebres/{qid}/resolver-tarea")
@audit_action("GTA_RESOLVER_QUIEBRE_TAREA", severity="info")
async def resolver_quiebre_de_tarea(
    qid: int,
    body: QuiebreResolverBody,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Resuelve un quiebre vinculado a una tarea: marca como resuelto y
    restaura el estado previo de la tarea (sale de 'esperando_quiebre')."""
    try:
        return quiebres_service.resolver(
            qid,
            nota=body.nota,
            resuelto_por=user["username"],
            bypass_area=_es_admin(user),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Avisos de revisión (cambios post-cierre que afectan tareas previas) ──

@router.get("/tareas/{tarea_id}/avisos")
async def listar_avisos_tarea(
    tarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Avisos pendientes (sin revisar) para esta tarea."""
    return {"items": avisos_service.listar_pendientes_de_tarea(tarea_id)}


@router.post("/tareas/{tarea_id}/avisos/{aviso_id}/revisar")
@audit_action("GTA_REVISAR_AVISO", severity="info")
async def marcar_aviso_revisado(
    tarea_id: int,
    aviso_id: int,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Marca un aviso de revisión como ya leído / revisado."""
    try:
        # Coherencia: el aviso debe pertenecer a esta tarea
        pendientes = avisos_service.listar_pendientes_de_tarea(tarea_id)
        if not any(a["id"] == aviso_id for a in pendientes):
            raise HTTPException(
                status_code=403,
                detail="el aviso no pertenece a esta tarea o ya está revisado",
            )
        uid = tareas_service.usuario_id_de_username(user["username"])
        return avisos_service.marcar_revisado(aviso_id, revisado_por_id=uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Comentarios libres del flujo (visibles desde cualquier tarea) ────

@router.get("/tareas/{tarea_id}/comentarios")
async def listar_comentarios_de_tarea(
    tarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Comentarios del flujo al que pertenece la tarea (compartidos)."""
    try:
        return {"items": comentarios_service.listar_de_tarea(tarea_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/comentarios")
@audit_action("GTA_AGREGAR_COMENTARIO_TAREA", severity="info")
async def crear_comentario_de_tarea(
    tarea_id: int,
    body: dict,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Agrega un comentario libre a la tarea (visible al flujo entero)."""
    try:
        return comentarios_service.crear(
            tarea_id=tarea_id,
            autor=user["username"],
            texto=(body.get("texto") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tareas/{tarea_id}/comentarios/{comentario_id}")
@audit_action("GTA_BORRAR_COMENTARIO_TAREA", severity="info")
async def borrar_comentario_de_tarea(
    tarea_id: int,
    comentario_id: int,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        # Verificar coherencia: el comentario debe estar en alguna tarea del flujo
        comentarios_flujo = comentarios_service.listar_de_tarea(tarea_id)
        if not any(c["id"] == comentario_id for c in comentarios_flujo):
            raise HTTPException(status_code=403, detail="el comentario no pertenece al flujo de esta tarea")
        comentarios_service.borrar(
            comentario_id,
            autor_actor=user["username"],
            es_admin=_es_admin(user),
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Adjuntos del flujo (compartidos por todas las tareas del flujo) ──

@router.get("/tareas/{tarea_id}/adjuntos")
async def listar_adjuntos_tarea(
    tarea_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Lista los adjuntos del flujo al que pertenece la tarea."""
    try:
        return {"items": adjuntos_service.listar_adjuntos_tarea(tarea_id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tareas/{tarea_id}/adjuntos")
@audit_action("GTA_SUBIR_ADJUNTO", severity="info")
async def subir_adjunto_tarea(
    tarea_id: int,
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(deps.require_permission("gta:write")),
):
    """Sube un archivo asociado al flujo de la tarea."""
    try:
        contenido = await file.read()
        uid = tareas_service.usuario_id_de_username(user["username"])
        return adjuntos_service.subir_adjunto(
            tarea_id=tarea_id,
            filename=file.filename or "archivo",
            contenido=contenido,
            mime=file.content_type,
            subido_por=uid,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tareas/{tarea_id}/adjuntos/{adjunto_id}")
@audit_action("GTA_BORRAR_ADJUNTO", severity="info")
async def borrar_adjunto_tarea(
    tarea_id: int,
    adjunto_id: int,
    request: Request,
    user: dict = Depends(deps.require_permission("gta:write")),
):
    try:
        # Verificar coherencia: el adjunto debe pertenecer al flujo de esta tarea
        meta = adjuntos_service.get_adjunto(adjunto_id)
        if not meta:
            raise HTTPException(status_code=404, detail="adjunto no encontrado")
        tarea = tareas_service.get_tarea(tarea_id)
        if not tarea or str(tarea.get("flujo_id")) != str(meta["flujo_id"]):
            raise HTTPException(status_code=403, detail="el adjunto no pertenece al flujo de esta tarea")

        uid = tareas_service.usuario_id_de_username(user["username"])
        adjuntos_service.eliminar_adjunto(
            adjunto_id,
            actor_id=uid,
            es_admin=_es_admin(user),
        )
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/adjuntos/{adjunto_id}/download")
async def descargar_adjunto(
    adjunto_id: int,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    """Descarga el archivo físico del adjunto."""
    meta = adjuntos_service.get_adjunto(adjunto_id)
    if not meta:
        raise HTTPException(status_code=404, detail="adjunto no encontrado")
    full = adjuntos_service.ruta_absoluta(meta["ruta"])
    if not full.exists():
        raise HTTPException(status_code=410, detail="archivo no disponible en el filesystem")
    return FileResponse(
        path=str(full),
        filename=meta["filename"],
        media_type=meta.get("mime") or "application/octet-stream",
    )


# ── Membresías área ↔ persona ─────────────────────────────────────────

@router.get("/membresias/subarea/{subarea_id}")
async def listar_membresias_subarea(
    subarea_id: int,
    incluir_historico: bool = False,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    return {"items": membresias_service.listar_membresias_subarea(
        subarea_id, incluir_historico=incluir_historico,
    )}


@router.get("/membresias/mias")
async def listar_mis_membresias(
    incluir_historico: bool = False,
    user: dict = Depends(deps.require_permission("gta:read")),
):
    uid = tareas_service.usuario_id_de_username(user["username"])
    return {"items": membresias_service.listar_membresias_usuario(
        uid, incluir_historico=incluir_historico,
    )}


@router.post("/membresias")
@audit_action("GTA_MEMBRESIA_ASIGNAR", severity="warning")
async def asignar_membresia(
    body: MembresiaAsignar,
    request: Request,
    user: dict = Depends(deps.require_permission("admin.settings")),
):
    """Solo admins pueden asignar membresías por ahora."""
    try:
        actor_id = tareas_service.usuario_id_de_username(user["username"])
        return membresias_service.asignar_membresia(
            usuario_id=body.usuario_id,
            subarea_id=body.subarea_id,
            rol=body.rol,
            es_principal=body.es_principal,
            asignado_por=actor_id,
            motivo=body.motivo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/membresias/{membresia_id}")
@audit_action("GTA_MEMBRESIA_CERRAR", severity="warning")
async def cerrar_membresia(
    membresia_id: int,
    body: MembresiaCerrar,
    request: Request,
    user: dict = Depends(deps.require_permission("admin.settings")),
):
    actor_id = tareas_service.usuario_id_de_username(user["username"])
    ok = membresias_service.cerrar_membresia(
        membresia_id, cerrado_por=actor_id, motivo=body.motivo,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="membresía no encontrada o ya cerrada")
    return {"ok": True}
