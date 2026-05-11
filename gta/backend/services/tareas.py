"""Servicio de tareas.

Modelo: una tarea pertenece a una subárea (no a una persona). La asignación
se versiona en gta.tarea_participaciones — un único responsable vigente +
N co-responsables/ayudas vigentes.

Vistas principales:
- bandeja_subarea: tareas de una subárea sin responsable vigente (esperan
  ser tomadas).
- mis_tareas: tareas donde soy responsable vigente.
- donde_colaboro: tareas donde tengo participación vigente como
  co_responsable o ayuda (no responsable).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from plataforma.core import db
from gta.backend.services import membresias as membresias_service


# ── Helpers ─────────────────────────────────────────────────────────────

def usuario_id_de_username(username: str) -> int:
    """Resuelve username → id en auth.users. Lanza ValueError si no existe."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM auth.users WHERE username = %s",
            (username,),
        ).fetchone()
        if not row:
            raise ValueError(f"usuario no encontrado: {username}")
        return int(row["id"])
    finally:
        conn.close()


def _serialize_tarea(row: Dict[str, Any]) -> Dict[str, Any]:
    t = dict(row)
    raw_tags = t.get("tags")
    if isinstance(raw_tags, str):
        try:
            t["tags"] = json.loads(raw_tags)
        except Exception:
            t["tags"] = []
    elif raw_tags is None:
        t["tags"] = []
    return t


def _attach_participaciones(conn, tarea: Dict[str, Any]) -> Dict[str, Any]:
    """Agrega responsable_actual + colaboradores_actuales + historial."""
    rows = conn.execute(
        """SELECT p.id, p.usuario_id, p.rol, p.desde, p.hasta, p.motivo,
                  u.username
           FROM gta.tarea_participaciones p
           JOIN auth.users u ON u.id = p.usuario_id
           WHERE p.tarea_id = %s
           ORDER BY p.desde DESC""",
        (tarea["id"],),
    ).fetchall()
    todas = [dict(r) for r in rows]
    vigentes = [p for p in todas if p["hasta"] is None]
    responsable = next((p for p in vigentes if p["rol"] == "responsable"), None)
    colaboradores = [p for p in vigentes if p["rol"] != "responsable"]
    tarea["responsable_actual"] = responsable
    tarea["colaboradores_actuales"] = colaboradores
    tarea["historial_participaciones"] = todas
    return tarea


# ── Crear / cerrar ──────────────────────────────────────────────────────

def crear_tarea(
    *,
    subarea_id: int,
    titulo: str,
    descripcion: Optional[str],
    creado_por: int,
    proceso_id: Optional[int] = None,
    tipo: Optional[str] = None,
    prioridad: str = "media",
    sla_horas: Optional[int] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not titulo.strip():
        raise ValueError("titulo es requerido")
    if prioridad not in ("baja", "media", "alta", "urgente"):
        raise ValueError("prioridad inválida")

    conn = db.get_conn()
    try:
        sla_due = None
        if sla_horas and sla_horas > 0:
            row = conn.execute(
                "SELECT CURRENT_TIMESTAMP + (%s || ' hours')::interval AS due",
                (str(sla_horas),),
            ).fetchone()
            sla_due = row["due"]

        row = conn.execute(
            """INSERT INTO gta.tareas
               (subarea_id, proceso_id, titulo, descripcion,
                tipo, prioridad, sla_horas, sla_due_at, creado_por, tags)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                subarea_id, proceso_id, titulo.strip(),
                descripcion, tipo, prioridad, sla_horas, sla_due, creado_por,
                json.dumps(tags or [], ensure_ascii=False),
            ),
        ).fetchone()
        conn.commit()
        return get_tarea(int(row["id"]))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cerrar_tarea(
    tarea_id: int,
    *,
    cerrado_por: int,
    reporte: Optional[str] = None,
    datos_formulario: Optional[Dict[str, Any]] = None,
    bypass_responsable: bool = False,
) -> Dict[str, Any]:
    """Cierra una tarea.

    - Solo el responsable vigente (o admin con bypass=True) puede cerrar.
      Esto evita que cualquier usuario con gta:write pise datos del flujo.
    - Si la tarea pertenece a un flujo y es el paso inicial (paso_orden=1),
      valida que los campos del formulario obligatorios estén completos y
      los guarda en TODAS las tareas del flujo (datos_flujo) para que los
      pasos siguientes los vean al ser tomadas.
    """
    conn = db.get_conn()
    try:
        # Contexto: ¿pertenece a un flujo? ¿es el paso 1?
        ctx = conn.execute(
            """SELECT t.flujo_id, t.paso_orden, t.proceso_id,
                      t.datos_flujo,
                      p.campos_formulario AS proceso_campos
               FROM gta.tareas t
               LEFT JOIN gta.procesos p ON p.id = t.proceso_id
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not ctx:
            raise ValueError("tarea no encontrada")

        # Validar que el actor sea responsable vigente (o admin con bypass).
        # Patrón idéntico al de guardar_borrador_formulario para consistencia.
        if not bypass_responsable:
            es_resp = conn.execute(
                """SELECT 1 FROM gta.tarea_participaciones
                   WHERE tarea_id = %s AND usuario_id = %s
                     AND rol = 'responsable' AND hasta IS NULL""",
                (tarea_id, cerrado_por),
            ).fetchone()
            if not es_resp:
                raise ValueError("Solo el responsable vigente de la tarea puede cerrarla")

        es_paso_inicial = bool(
            ctx.get("flujo_id") and ctx.get("paso_orden") == 1
        )

        # Snapshot pre-cierre para detectar cambios si esta tarea fue
        # reabierta antes (devolución). Sin esto no podemos avisar a los
        # pasos cerrados posteriores que algo cambió.
        import json as _json_snap
        raw_datos_antes = ctx.get("datos_flujo")
        try:
            if isinstance(raw_datos_antes, dict):
                datos_antes = raw_datos_antes
            elif isinstance(raw_datos_antes, str):
                datos_antes = _json_snap.loads(raw_datos_antes or "{}") or {}
            else:
                datos_antes = {}
        except Exception:
            datos_antes = {}
        adjuntos_antes = 0
        if ctx.get("flujo_id"):
            adj_row = conn.execute(
                "SELECT COUNT(*) AS n FROM gta.flujo_adjuntos WHERE flujo_id = %s",
                (ctx["flujo_id"],),
            ).fetchone()
            adjuntos_antes = int((adj_row or {}).get("n") or 0)
        # ¿Esta tarea fue reabierta antes? (si hay un evento TAREA_REABIERTA con su id)
        fue_reabierta = False
        if ctx.get("flujo_id"):
            ev_row = conn.execute(
                """SELECT 1 FROM gta.flujo_eventos
                   WHERE tarea_id = %s AND tipo = 'tarea_reabierta' LIMIT 1""",
                (tarea_id,),
            ).fetchone()
            fue_reabierta = bool(ev_row)

        if es_paso_inicial:
            import json as _json
            try:
                campos_def = _json.loads(ctx.get("proceso_campos") or "[]") or []
                if not isinstance(campos_def, list):
                    campos_def = []
            except Exception:
                campos_def = []

            datos = datos_formulario or {}
            faltantes = [
                c for c in campos_def
                if c.get("requerido") is not False
                   and not str(datos.get(c.get("key", ""), "")).strip()
            ]
            if faltantes:
                etiquetas = ", ".join(c.get("label") or c.get("key") or "?" for c in faltantes)
                raise ValueError(f"Faltan completar campos obligatorios: {etiquetas}")

            # Propagamos los datos a TODAS las tareas del flujo (incluida ésta).
            # Así cualquier área que abra una tarea siguiente ve los datos
            # cargados por el iniciador.
            conn.execute(
                "UPDATE gta.tareas SET datos_flujo = %s::jsonb, updated_at = CURRENT_TIMESTAMP "
                "WHERE flujo_id = %s",
                (_json.dumps(datos, ensure_ascii=False), ctx["flujo_id"]),
            )

        # Cerrar todas las participaciones vigentes
        conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND hasta IS NULL""",
            (tarea_id,),
        )
        result = conn.execute(
            """UPDATE gta.tareas
               SET estado = 'cerrada',
                   cerrado_por = %s,
                   cerrado_at = CURRENT_TIMESTAMP,
                   reporte_cierre = %s,
                   fecha_fin = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s AND estado <> 'cerrada'
               RETURNING id, flujo_id, paso_orden""",
            (cerrado_por, reporte, tarea_id),
        ).fetchone()
        if not result:
            raise ValueError("tarea no encontrada o ya cerrada")

        # Si pertenece a un flujo, desbloquear las hermanas que dependían de
        # este paso (cuando todas sus deps bloqueantes ya están cerradas).
        if result.get("flujo_id") and result.get("paso_orden") is not None:
            _desbloquear_dependientes(
                conn,
                flujo_id=result["flujo_id"],
                paso_predecesor=int(result["paso_orden"]),
            )

            # Evento: tarea cerrada (y quizás flujo completado)
            from gta.backend.services import flujo_eventos as evt
            actor_username = conn.execute(
                "SELECT username FROM auth.users WHERE id = %s", (cerrado_por,),
            ).fetchone()
            actor = (actor_username or {}).get("username") or "sistema"
            paso_n = result["paso_orden"]
            evt.registrar(
                conn, result["flujo_id"],
                tipo=evt.TAREA_CERRADA,
                actor=actor,
                tarea_id=tarea_id,
                mensaje=f"Cerró paso {paso_n}",
                metadata={"paso_orden": paso_n},
            )
            # Reanimar tareas que estaban devueltas esperando a este paso.
            # La tarea origen vuelve a 'pendiente' o 'en_curso' según conserve
            # responsable vigente, y se limpia espera_devolucion_paso.
            esperando = conn.execute(
                """SELECT id FROM gta.tareas
                   WHERE flujo_id = %s
                     AND espera_devolucion_paso = %s
                     AND estado = 'devuelta'""",
                (result["flujo_id"], int(result["paso_orden"])),
            ).fetchall()
            for t in esperando:
                tiene_resp = conn.execute(
                    """SELECT 1 FROM gta.tarea_participaciones
                       WHERE tarea_id = %s AND rol = 'responsable' AND hasta IS NULL""",
                    (t["id"],),
                ).fetchone()
                nuevo_estado = 'en_curso' if tiene_resp else 'pendiente'
                conn.execute(
                    """UPDATE gta.tareas
                       SET estado = %s,
                           espera_devolucion_paso = NULL,
                           cerrado_por = NULL,
                           cerrado_at = NULL,
                           reporte_cierre = NULL,
                           fecha_fin = NULL,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s""",
                    (nuevo_estado, t["id"]),
                )
                evt.registrar(
                    conn, result["flujo_id"],
                    tipo=evt.TAREA_REABIERTA,
                    actor=actor,
                    tarea_id=t["id"],
                    mensaje=f"Reanudada tras cierre del paso {result['paso_orden']}",
                    metadata={"reanudada_por_paso": result["paso_orden"]},
                )

            # Si esta tarea había sido reabierta antes (por devolución), comparamos
            # datos del flujo y adjuntos antes/después; si hubo cambios, avisamos
            # a los pasos cerrados posteriores que revisen.
            if fue_reabierta:
                datos_despues_row = conn.execute(
                    "SELECT datos_flujo FROM gta.tareas WHERE id = %s",
                    (tarea_id,),
                ).fetchone()
                raw_d = (datos_despues_row or {}).get("datos_flujo")
                try:
                    if isinstance(raw_d, dict):
                        datos_despues = raw_d
                    elif isinstance(raw_d, str):
                        datos_despues = _json_snap.loads(raw_d or "{}") or {}
                    else:
                        datos_despues = {}
                except Exception:
                    datos_despues = {}
                adj_despues_row = conn.execute(
                    "SELECT COUNT(*) AS n FROM gta.flujo_adjuntos WHERE flujo_id = %s",
                    (result["flujo_id"],),
                ).fetchone()
                adjuntos_despues = int((adj_despues_row or {}).get("n") or 0)
                from gta.backend.services import avisos as avisos_service
                avisos_service.detectar_cambios_y_avisar(
                    conn,
                    tarea_cerrada_id=tarea_id,
                    flujo_id=result["flujo_id"],
                    paso_orden_cerrado=int(result["paso_orden"]),
                    datos_flujo_antes=datos_antes,
                    datos_flujo_despues=datos_despues,
                    adjuntos_antes_count=adjuntos_antes,
                    adjuntos_despues_count=adjuntos_despues,
                )

            # Si todas las tareas del flujo están cerradas, registrar completado
            pendientes = conn.execute(
                """SELECT COUNT(*) AS n FROM gta.tareas
                   WHERE flujo_id = %s AND estado NOT IN ('cerrada','cancelada')""",
                (result["flujo_id"],),
            ).fetchone()
            if pendientes and int(pendientes.get("n") or 0) == 0:
                evt.registrar(
                    conn, result["flujo_id"],
                    tipo=evt.FLUJO_COMPLETADO,
                    actor=actor,
                    mensaje="Flujo completado",
                )

        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def devolver_tarea(
    tarea_id: int,
    *,
    devuelto_por: int,
    motivo: str,
    paso_destino: int,
) -> Dict[str, Any]:
    """Devuelve la tarea actual al paso destino para que su responsable corrija.

    Modelo unificado (sin distinción validación/quiebre): cualquier paso de
    flujo puede devolver a cualquier paso anterior del mismo flujo.

    Efecto:
      - La tarea actual queda 'devuelta' con motivo en reporte_cierre y
        espera_devolucion_paso=destino. NO se desbloquea hasta que el paso
        destino se cierre nuevamente (vía cerrar_tarea, que reanima las
        tareas con espera_devolucion_paso = paso recién cerrado).
      - Los pasos intermedios entre destino y origen siguen cerrados (no
        se rehace trabajo). Si al cerrarse de nuevo el paso destino los
        datos del flujo cambiaron o se modificaron adjuntos, esos pasos
        intermedios reciben un aviso de revisión (ver avisos.py).
      - La tarea destino se reabre: 'pendiente', limpia cierre.
    """
    motivo_clean = (motivo or "").strip()
    if not motivo_clean:
        raise ValueError("El motivo es obligatorio para devolver una tarea")
    if paso_destino is None or paso_destino < 1:
        raise ValueError("paso_destino requerido y debe ser >= 1")

    conn = db.get_conn()
    try:
        ctx = conn.execute(
            """SELECT t.flujo_id, t.paso_orden, t.proceso_id, t.estado
               FROM gta.tareas t
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not ctx:
            raise ValueError("tarea no encontrada")
        if not ctx.get("flujo_id"):
            raise ValueError("solo se pueden devolver tareas que pertenecen a un flujo")
        if ctx["estado"] in ("cerrada", "cancelada", "devuelta"):
            raise ValueError("la tarea ya está finalizada")
        if paso_destino >= ctx["paso_orden"]:
            raise ValueError(
                f"paso_destino={paso_destino} debe ser anterior al paso actual "
                f"({ctx['paso_orden']}). Solo se puede devolver hacia atrás."
            )

        # Tarea destino del mismo flujo
        destino = conn.execute(
            "SELECT id, estado FROM gta.tareas WHERE flujo_id = %s AND paso_orden = %s",
            (ctx["flujo_id"], int(paso_destino)),
        ).fetchone()
        if not destino:
            raise ValueError(f"no se encontró el paso destino (orden={paso_destino})")

        # Cerrar participaciones vigentes de la tarea actual
        conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND hasta IS NULL""",
            (tarea_id,),
        )

        # Marcar tarea actual como devuelta, esperando al paso destino
        conn.execute(
            """UPDATE gta.tareas
               SET estado = 'devuelta',
                   cerrado_por = %s,
                   cerrado_at = CURRENT_TIMESTAMP,
                   reporte_cierre = %s,
                   fecha_fin = CURRENT_TIMESTAMP,
                   espera_devolucion_paso = %s,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (devuelto_por, motivo_clean, int(paso_destino), tarea_id),
        )

        # Reabrir tarea destino: limpiar cierre y dejar pendiente
        conn.execute(
            """UPDATE gta.tareas
               SET estado = 'pendiente',
                   cerrado_por = NULL,
                   cerrado_at = NULL,
                   reporte_cierre = NULL,
                   fecha_fin = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (destino["id"],),
        )

        # Dejar registro en comentarios del flujo (visible en la tarea destino)
        autor_row = conn.execute(
            "SELECT username FROM auth.users WHERE id = %s",
            (devuelto_por,),
        ).fetchone()
        autor = (autor_row or {}).get("username") or "sistema"
        conn.execute(
            """INSERT INTO gta.comentarios (tarea_id, autor, texto, created_at)
               VALUES (%s, %s, %s, CURRENT_TIMESTAMP)""",
            (
                destino["id"],
                autor,
                f"[Devuelto desde paso {ctx['paso_orden']}] {motivo_clean}",
            ),
        )

        # Eventos: timeline del flujo
        from gta.backend.services import flujo_eventos as evt
        evt.registrar(
            conn, ctx["flujo_id"],
            tipo=evt.TAREA_DEVUELTA,
            actor=autor,
            tarea_id=tarea_id,
            mensaje=f"Devolvió paso {ctx['paso_orden']} → paso {paso_destino}: {motivo_clean}",
            metadata={
                "paso_origen": ctx["paso_orden"],
                "paso_destino": paso_destino,
                "motivo": motivo_clean,
            },
        )
        evt.registrar(
            conn, ctx["flujo_id"],
            tipo=evt.TAREA_REABIERTA,
            actor=autor,
            tarea_id=destino["id"],
            mensaje=f"Reabierto paso {paso_destino} para corregir",
            metadata={"paso_orden": paso_destino},
        )

        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def guardar_borrador_formulario(
    tarea_id: int,
    *,
    usuario_id: int,
    datos_formulario: Dict[str, Any],
    bypass_responsable: bool = False,
) -> Dict[str, Any]:
    """Guarda datos parciales del formulario sin cerrar la tarea.

    Útil para que el responsable cargue lo que tiene mientras consigue el
    resto. Los datos quedan visibles para todos los miembros del área (por
    si la persona se enferma o pasa algo, otro retoma).

    - El usuario debe ser el responsable vigente (o admin si bypass=True).
    - Los datos se propagan a TODAS las tareas del flujo (igual que al
      cerrar el paso 1), así los siguientes pasos los van viendo crecer.
    - NO valida campos obligatorios. Es un borrador.
    """
    conn = db.get_conn()
    try:
        ctx = conn.execute(
            "SELECT flujo_id, paso_orden, estado FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not ctx:
            raise ValueError("tarea no encontrada")
        if ctx["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")
        if ctx["estado"] == "bloqueada":
            raise ValueError("no se puede guardar borrador en una tarea bloqueada")

        # Validar que el actor sea responsable vigente (o admin)
        if not bypass_responsable:
            es_resp = conn.execute(
                """SELECT 1 FROM gta.tarea_participaciones
                   WHERE tarea_id = %s AND usuario_id = %s
                     AND rol = 'responsable' AND hasta IS NULL""",
                (tarea_id, usuario_id),
            ).fetchone()
            if not es_resp:
                raise ValueError("Solo el responsable de la tarea puede guardar el borrador")

        flujo_id = ctx["flujo_id"]
        if flujo_id:
            # Propagar a todas las tareas del flujo
            conn.execute(
                "UPDATE gta.tareas SET datos_flujo = %s::jsonb, "
                "updated_at = CURRENT_TIMESTAMP WHERE flujo_id = %s",
                (json.dumps(datos_formulario or {}, ensure_ascii=False), flujo_id),
            )
        else:
            # Tarea suelta: solo en esta fila
            conn.execute(
                "UPDATE gta.tareas SET datos_flujo = %s::jsonb, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (json.dumps(datos_formulario or {}, ensure_ascii=False), tarea_id),
            )

        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _desbloquear_dependientes(conn, *, flujo_id: str, paso_predecesor: int) -> None:
    """Cuando un paso del flujo se cierra, busca hermanas que dependan de él
    y las pasa de 'bloqueada' a 'pendiente' si TODAS sus deps bloqueantes
    ya están cerradas.

    El modelo nuevo guarda paso_depende_de como JSONB en gta.tareas, con los
    paso_orden de los predecesores. Identificamos hermanas por flujo_id.
    """
    # Hermanas del mismo flujo, bloqueadas, que tienen al predecesor en su
    # lista de dependencias. Las tareas 'devuelta' ya no se reanudan por
    # cascada normal: lo hace cerrar_tarea mirando espera_devolucion_paso.
    hermanas = conn.execute(
        """SELECT id, paso_orden, paso_depende_de, sla_horas, sla_due_at
           FROM gta.tareas
           WHERE flujo_id = %s
             AND estado = 'bloqueada'
             AND paso_depende_de @> %s::jsonb""",
        (flujo_id, json.dumps([paso_predecesor])),
    ).fetchall()

    import json as _json
    for h in hermanas:
        raw = h.get("paso_depende_de")
        if isinstance(raw, list):
            deps = raw
        elif isinstance(raw, str):
            try:
                deps = _json.loads(raw or "[]") or []
            except Exception:
                deps = []
        else:
            deps = []
        if not deps:
            continue

        # ¿Todas las deps bloqueantes están cerradas? Las no-bloqueantes nunca
        # traban, así que solo evaluamos las que tienen paso_bloqueante=TRUE.
        placeholders = ",".join(["%s"] * len(deps))
        check = conn.execute(
            f"""SELECT COUNT(*) AS bloqueantes_pendientes
                FROM gta.tareas
                WHERE flujo_id = %s
                  AND paso_orden IN ({placeholders})
                  AND paso_bloqueante = TRUE
                  AND estado <> 'cerrada'""",
            tuple([flujo_id] + deps),
        ).fetchone()
        if check and int(check["bloqueantes_pendientes"] or 0) > 0:
            continue

        # Desbloquear: pasa a pendiente, limpia residual de devolución previa
        # (cerrado_at/por/reporte que quedaron de cuando se devolvió) e inicia SLA
        conn.execute(
            """UPDATE gta.tareas
               SET estado = 'pendiente',
                   cerrado_at = NULL,
                   cerrado_por = NULL,
                   reporte_cierre = NULL,
                   fecha_fin = NULL,
                   sla_due_at = CASE
                       WHEN sla_horas IS NOT NULL AND sla_due_at IS NULL
                       THEN CURRENT_TIMESTAMP + (sla_horas || ' hours')::interval
                       ELSE sla_due_at
                   END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (h["id"],),
        )


# ── Detalle ─────────────────────────────────────────────────────────────

def get_tarea(tarea_id: int) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT t.*,
                      s.code AS subarea_code, s.label AS subarea_label,
                      s.area_code,
                      a.label AS area_label,
                      uc.username AS creado_por_username
               FROM gta.tareas t
               JOIN gta.subareas s ON s.id = t.subarea_id
               JOIN gta.areas a ON a.code = s.area_code
               JOIN auth.users uc ON uc.id = t.creado_por
               WHERE t.id = %s""",
            (tarea_id,),
        ).fetchone()
        if not row:
            return {}
        tarea = _serialize_tarea(row)
        tarea = _attach_participaciones(conn, tarea)
        tarea = _attach_contexto_flujo(conn, tarea)
        return tarea
    finally:
        conn.close()


def _attach_contexto_flujo(conn, tarea: Dict[str, Any]) -> Dict[str, Any]:
    """Si la tarea pertenece a un flujo, adjunta el contexto al dict:
    - flujo: {id, titulo, datos_formulario, proceso_id}
    - paso_orden, paso_depende_de, paso_bloqueante (ya están en gta.tareas)
    - es_paso_inicial: True si paso_orden == 1
    - campos_formulario_proceso: definición de campos del proceso (para el
      modal de cierre del paso 1)
    """
    flujo_id = tarea.get("flujo_id")
    if not flujo_id:
        return tarea

    import json as _json

    # Datos del flujo: ya viven en datos_flujo (mismo en todas las tareas del flujo)
    raw_datos = tarea.get("datos_flujo")
    try:
        if isinstance(raw_datos, str):
            datos = _json.loads(raw_datos or "{}") or {}
        elif isinstance(raw_datos, dict):
            datos = raw_datos
        else:
            datos = {}
    except Exception:
        datos = {}

    # paso_depende_de viene como JSONB → en psycopg3 se decodifica solo
    raw_deps = tarea.get("paso_depende_de")
    try:
        if isinstance(raw_deps, str):
            deps = _json.loads(raw_deps or "[]") or []
        elif isinstance(raw_deps, list):
            deps = raw_deps
        else:
            deps = []
    except Exception:
        deps = []
    tarea["paso_depende_de"] = deps

    # Definición de campos del formulario y del paso (desde el proceso del catálogo)
    proc_id = tarea.get("proceso_id")
    campos_def: List[Any] = []
    paso_def: Dict[str, Any] = {}
    if proc_id:
        proc_row = conn.execute(
            "SELECT campos_formulario, pasos_definicion FROM gta.procesos WHERE id = %s",
            (proc_id,),
        ).fetchone()
        if proc_row:
            try:
                campos_def = _json.loads(proc_row.get("campos_formulario") or "[]") or []
                if not isinstance(campos_def, list):
                    campos_def = []
            except Exception:
                campos_def = []
            try:
                pasos_def = _json.loads(proc_row.get("pasos_definicion") or "[]") or []
                if isinstance(pasos_def, list):
                    paso_def = next(
                        (p for p in pasos_def if isinstance(p, dict)
                         and p.get("orden") == tarea.get("paso_orden")),
                        {},
                    ) or {}
            except Exception:
                paso_def = {}

    tarea["flujo"] = {
        "id": flujo_id,
        "titulo": tarea.get("flujo_titulo") or "",
        "proceso_id": proc_id,
        "datos_formulario": datos,
    }
    tarea["es_paso_inicial"] = (tarea.get("paso_orden") == 1)
    tarea["campos_formulario_proceso"] = campos_def
    # Modelo nuevo: cualquier paso de flujo puede devolver a cualquier paso
    # anterior. La UI muestra como opciones todos los pasos < paso_orden actual.
    pasos_def_list = pasos_def if isinstance(pasos_def, list) else []
    mi_orden = tarea.get("paso_orden") or 0
    destinos_info = sorted(
        [
            {
                "orden": p.get("orden"),
                "titulo": p.get("titulo") or f"Paso {p.get('orden')}",
                "area_code": p.get("area_code"),
            }
            for p in pasos_def_list
            if isinstance(p, dict) and isinstance(p.get("orden"), int)
            and p["orden"] < mi_orden
        ],
        key=lambda x: x["orden"],
    )
    tarea["paso_devolver_a_info"] = destinos_info
    # paso_tipo se mantiene por compatibilidad pero ya no controla la UI:
    # cualquier paso ≥ 2 muestra el botón "Devolver al paso..."
    tarea["paso_tipo"] = paso_def.get("tipo") or "ejecucion"
    return tarea


# ── Asignación / participaciones ────────────────────────────────────────

def tomar_tarea(
    tarea_id: int,
    *,
    usuario_id: int,
    bypass_membresia: bool = False,
) -> Dict[str, Any]:
    """Auto-asignación: el usuario se vuelve responsable.

    Requiere que la tarea esté vigente y sin responsable activo. Por defecto,
    el usuario debe ser miembro vigente de la subárea de la tarea. Admin
    global puede pasar `bypass_membresia=True` para tomar cualquier tarea
    sin estar asignado al área (típico de monitoreo/intervención).
    """
    conn = db.get_conn()
    try:
        tarea_row = conn.execute(
            "SELECT id, subarea_id, estado FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea_row:
            raise ValueError("tarea no encontrada")
        if tarea_row["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")

        if not bypass_membresia:
            es_miembro = conn.execute(
                """SELECT 1 FROM gta.area_membresias
                   WHERE usuario_id = %s AND subarea_id = %s AND hasta IS NULL""",
                (usuario_id, tarea_row["subarea_id"]),
            ).fetchone()
            if not es_miembro:
                raise ValueError("No eres miembro vigente de la subárea de esta tarea")

        ya_responsable = conn.execute(
            """SELECT usuario_id FROM gta.tarea_participaciones
               WHERE tarea_id = %s AND rol = 'responsable' AND hasta IS NULL""",
            (tarea_id,),
        ).fetchone()
        if ya_responsable:
            raise ValueError("la tarea ya tiene un responsable vigente")

        conn.execute(
            """INSERT INTO gta.tarea_participaciones
               (tarea_id, usuario_id, rol, asignado_por)
               VALUES (%s, %s, 'responsable', %s)""",
            (tarea_id, usuario_id, usuario_id),
        )
        conn.execute(
            """UPDATE gta.tareas
               SET estado = CASE WHEN estado = 'pendiente' THEN 'en_curso' ELSE estado END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def liberar_tarea(tarea_id: int, *, usuario_id: int, motivo: Optional[str] = None) -> Dict[str, Any]:
    """El responsable vigente libera la tarea — vuelve a la bandeja."""
    conn = db.get_conn()
    try:
        result = conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP,
                   motivo = COALESCE(%s, motivo)
               WHERE tarea_id = %s AND usuario_id = %s
                 AND rol = 'responsable' AND hasta IS NULL
               RETURNING id""",
            (motivo, tarea_id, usuario_id),
        ).fetchone()
        if not result:
            raise ValueError("no sos el responsable vigente de esta tarea")
        conn.execute(
            """UPDATE gta.tareas
               SET estado = CASE WHEN estado = 'en_curso' THEN 'pendiente' ELSE estado END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def reasignar_responsable(
    tarea_id: int,
    *,
    nuevo_usuario_id: int,
    asignado_por: int,
    motivo: Optional[str] = None,
) -> Dict[str, Any]:
    """Cambia el responsable. Cierra el actual (si hay) y abre uno nuevo.

    No exige que asignado_por sea líder — el endpoint decide quién puede.
    """
    conn = db.get_conn()
    try:
        tarea_row = conn.execute(
            "SELECT id, subarea_id, estado FROM gta.tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea_row:
            raise ValueError("tarea no encontrada")
        if tarea_row["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")

        # Si el nuevo responsable no es miembro del área, igual lo aceptamos
        # cuando viene de un admin (que ya pasó el check arriba en el router).
        # En el caso normal (líder de subárea reasignando), exigimos membresía.
        es_miembro = conn.execute(
            """SELECT 1 FROM gta.area_membresias
               WHERE usuario_id = %s AND subarea_id = %s AND hasta IS NULL""",
            (nuevo_usuario_id, tarea_row["subarea_id"]),
        ).fetchone()
        if not es_miembro:
            # Verificar si el actor (asignado_por) es admin global; si lo es,
            # permitimos asignar a cualquiera. Si no, rechazamos.
            es_admin_actor = conn.execute(
                "SELECT role FROM auth.users WHERE id = %s",
                (asignado_por,),
            ).fetchone()
            actor_es_admin = bool(
                es_admin_actor and (es_admin_actor.get("role") or "").lower() == "admin"
            )
            if not actor_es_admin:
                raise ValueError("el nuevo responsable no es miembro vigente de la subárea")

        conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND rol = 'responsable' AND hasta IS NULL""",
            (tarea_id,),
        )
        conn.execute(
            """INSERT INTO gta.tarea_participaciones
               (tarea_id, usuario_id, rol, asignado_por, motivo)
               VALUES (%s, %s, 'responsable', %s, %s)""",
            (tarea_id, nuevo_usuario_id, asignado_por, motivo),
        )
        conn.execute(
            """UPDATE gta.tareas
               SET estado = CASE WHEN estado = 'pendiente' THEN 'en_curso' ELSE estado END,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (tarea_id,),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def agregar_colaborador(
    tarea_id: int,
    *,
    usuario_id: int,
    rol: str,
    asignado_por: int,
    motivo: Optional[str] = None,
) -> Dict[str, Any]:
    """Agrega un co-responsable o ayuda. No toca al responsable vigente.

    rol: 'co_responsable' | 'ayuda'
    """
    if rol not in ("co_responsable", "ayuda"):
        raise ValueError("rol debe ser 'co_responsable' o 'ayuda'")

    conn = db.get_conn()
    try:
        tarea_row = conn.execute(
            "SELECT id, estado FROM gta.tareas WHERE id = %s", (tarea_id,),
        ).fetchone()
        if not tarea_row:
            raise ValueError("tarea no encontrada")
        if tarea_row["estado"] in ("cerrada", "cancelada"):
            raise ValueError("la tarea está cerrada")

        # Si ya tiene una participación vigente con ese rol, no duplicar
        ya = conn.execute(
            """SELECT 1 FROM gta.tarea_participaciones
               WHERE tarea_id = %s AND usuario_id = %s AND rol = %s AND hasta IS NULL""",
            (tarea_id, usuario_id, rol),
        ).fetchone()
        if ya:
            raise ValueError("ese usuario ya participa con ese rol")

        conn.execute(
            """INSERT INTO gta.tarea_participaciones
               (tarea_id, usuario_id, rol, asignado_por, motivo)
               VALUES (%s, %s, %s, %s, %s)""",
            (tarea_id, usuario_id, rol, asignado_por, motivo),
        )
        conn.commit()
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def quitar_colaborador(
    tarea_id: int, *, usuario_id: int, rol: str
) -> Dict[str, Any]:
    """Cierra una participación de co-responsable / ayuda vigente."""
    if rol not in ("co_responsable", "ayuda"):
        raise ValueError("rol inválido para quitar colaborador")
    conn = db.get_conn()
    try:
        result = conn.execute(
            """UPDATE gta.tarea_participaciones
               SET hasta = CURRENT_TIMESTAMP
               WHERE tarea_id = %s AND usuario_id = %s AND rol = %s
                 AND hasta IS NULL
               RETURNING id""",
            (tarea_id, usuario_id, rol),
        ).fetchone()
        conn.commit()
        if not result:
            raise ValueError("no se encontró participación vigente")
        return get_tarea(tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Listados / vistas ──────────────────────────────────────────────────

_BASE_SELECT = """
    SELECT t.id, t.subarea_id, t.proceso_id,
           t.flujo_id, t.flujo_titulo, t.paso_orden,
           t.paso_depende_de, t.paso_bloqueante,
           t.titulo, t.descripcion, t.tipo, t.prioridad, t.estado,
           t.sla_horas, t.sla_due_at, t.fecha_inicio, t.fecha_fin,
           t.creado_por, t.cerrado_por, t.cerrado_at, t.tags,
           t.created_at, t.updated_at,
           s.code AS subarea_code, s.label AS subarea_label,
           s.area_code,
           a.label AS area_label,
           gta.responsable_vigente(t.id) AS responsable_id,
           ur.username AS responsable_username,
           EXISTS (SELECT 1 FROM gta.avisos_revision av
                   WHERE av.tarea_id = t.id AND av.revisado_at IS NULL)
             AS tiene_avisos_pendientes
    FROM gta.tareas t
    JOIN gta.subareas s ON s.id = t.subarea_id
    JOIN gta.areas a ON a.code = s.area_code
    LEFT JOIN auth.users ur ON ur.id = gta.responsable_vigente(t.id)
"""

# Orden estándar para listados de tareas:
#   1. Tareas de flujo primero (agrupadas por flujo_id, ordenadas por inicio del flujo).
#   2. Dentro de cada flujo, por paso_orden ascendente (1, 2, 3, ...).
#   3. Tareas sueltas después: prioridad (urgente → baja) y fecha más reciente.
_ORDER_BY = """
    ORDER BY
      (t.flujo_id IS NULL),
      MIN(t.created_at) OVER (PARTITION BY t.flujo_id),
      t.flujo_id,
      t.paso_orden NULLS LAST,
      CASE t.prioridad WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1
                       WHEN 'media' THEN 2 ELSE 3 END,
      t.created_at DESC
"""


def listar_bandeja_subarea(subarea_id: int) -> List[Dict[str, Any]]:
    """Tareas de una subárea sin responsable vigente y no cerradas."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            _BASE_SELECT + """
            WHERE t.subarea_id = %s
              AND t.estado NOT IN ('cerrada', 'cancelada')
              AND gta.responsable_vigente(t.id) IS NULL
            """ + _ORDER_BY + """
""",
            (subarea_id,),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_bandeja_de_usuario(usuario_id: int) -> List[Dict[str, Any]]:
    """Bandejas combinadas de todas las subáreas del usuario."""
    sub_ids = membresias_service.subarea_ids_de_usuario(usuario_id)
    if not sub_ids:
        return []
    conn = db.get_conn()
    try:
        placeholders = ",".join(["%s"] * len(sub_ids))
        rows = conn.execute(
            _BASE_SELECT + f"""
            WHERE t.subarea_id IN ({placeholders})
              AND t.estado NOT IN ('cerrada', 'cancelada')
              AND gta.responsable_vigente(t.id) IS NULL
            """ + _ORDER_BY + """
""",
            tuple(sub_ids),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_bandeja_global() -> List[Dict[str, Any]]:
    """Bandeja de TODAS las subáreas (vista admin). Sin filtro por membresía."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            _BASE_SELECT + """
            WHERE t.estado NOT IN ('cerrada', 'cancelada')
              AND gta.responsable_vigente(t.id) IS NULL
            """ + _ORDER_BY + """
""",
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_todas_global(*, incluir_cerradas: bool = False) -> List[Dict[str, Any]]:
    """TODAS las tareas (vista admin). Sin filtro por membresía ni responsable."""
    conn = db.get_conn()
    try:
        where_estado = "" if incluir_cerradas else "WHERE t.estado NOT IN ('cerrada', 'cancelada')"
        rows = conn.execute(
            _BASE_SELECT + f"""
            {where_estado}
            """ + _ORDER_BY + """
""",
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_mis_tareas(usuario_id: int, *, incluir_cerradas: bool = False) -> List[Dict[str, Any]]:
    """Tareas donde el usuario es responsable vigente."""
    conn = db.get_conn()
    try:
        where_estado = "" if incluir_cerradas else "AND t.estado NOT IN ('cerrada', 'cancelada')"
        rows = conn.execute(
            _BASE_SELECT + f"""
            JOIN gta.tarea_participaciones p
              ON p.tarea_id = t.id AND p.rol = 'responsable' AND p.hasta IS NULL
            WHERE p.usuario_id = %s
              {where_estado}
            """ + _ORDER_BY + """
""",
            (usuario_id,),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()


def listar_donde_colaboro(usuario_id: int, *, incluir_cerradas: bool = False) -> List[Dict[str, Any]]:
    """Tareas donde el usuario es co-responsable o ayuda (vigente)."""
    conn = db.get_conn()
    try:
        where_estado = "" if incluir_cerradas else "AND t.estado NOT IN ('cerrada', 'cancelada')"
        rows = conn.execute(
            _BASE_SELECT + f"""
            JOIN gta.tarea_participaciones p
              ON p.tarea_id = t.id AND p.hasta IS NULL
            WHERE p.usuario_id = %s
              AND p.rol IN ('co_responsable', 'ayuda')
              {where_estado}
            """ + _ORDER_BY + """
""",
            (usuario_id,),
        ).fetchall()
        # Adjuntar el rol con el que participa
        out = []
        for r in rows:
            t = _serialize_tarea(r)
            out.append(t)
        return out
    finally:
        conn.close()


def listar_todas_subarea(subarea_id: int) -> List[Dict[str, Any]]:
    """Todas las tareas de una subárea (admin / vista de líder)."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            _BASE_SELECT + """
            WHERE t.subarea_id = %s
            """ + _ORDER_BY + """
""",
            (subarea_id,),
        ).fetchall()
        return [_serialize_tarea(r) for r in rows]
    finally:
        conn.close()
