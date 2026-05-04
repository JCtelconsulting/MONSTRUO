"""Servicio de flujos cross-área del GTA.

Responsabilidades:
- Crear flujos (desde proceso predefinido o libre)
- Avanzar el estado de las tareas según dependencias
- Pedir ayuda entre áreas (con o sin pausa de SLA)
- Confirmación dual: ejecutor marca "hecho" → iniciador valida
- Calcular SLA consumido y semáforo (verde/amarillo/naranjo/rojo)
- Registrar eventos auditables
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from plataforma.core import db


# ── Constantes de estado ────────────────────────────────────────────────────

ESTADOS_FLUJO = {"borrador", "activo", "completado", "cancelado", "vencido"}
ESTADOS_TAREA = {
    "pendiente",      # esperando que termine la dependencia
    "lista",          # puede empezar (todas las dependencias completas) — empieza a contar SLA
    "en_progreso",    # alguien la está haciendo
    "por_validar",    # ejecutor dijo "hecho", falta confirmar el iniciador
    "completada",     # validada por iniciador
    "ayuda_pedida",   # bloqueada por dependencia externa (SLA pausado)
    "vencida",        # SLA llegó al 100%
    "cancelada",
}


# ── Helpers de tiempo y SLA ─────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _settings_get(conn, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM gta.settings WHERE key = %s", (key,)).fetchone()
    return str(row["value"]) if row else default


def calcular_sla_pct(tarea: Dict[str, Any]) -> Dict[str, Any]:
    """Calcula porcentaje de SLA consumido y semáforo de una tarea.

    Retorna dict con: pct, color, minutos_consumidos, minutos_total,
    minutos_pausados, vencida, esta_pausada.
    """
    sla_horas = int(tarea.get("sla_horas") or 0)
    minutos_total = sla_horas * 60
    if minutos_total <= 0:
        return {
            "pct": 0, "color": "gray", "minutos_consumidos": 0,
            "minutos_total": 0, "minutos_pausados": 0,
            "vencida": False, "esta_pausada": False,
        }

    estado = str(tarea.get("estado") or "")
    inicio = _parse_dt(tarea.get("inicio_at"))
    if not inicio:
        return {
            "pct": 0, "color": "gray", "minutos_consumidos": 0,
            "minutos_total": minutos_total, "minutos_pausados": 0,
            "vencida": False, "esta_pausada": False,
        }

    pausados = int(tarea.get("sla_paused_minutes") or 0)
    pause_started = _parse_dt(tarea.get("sla_pause_started_at"))
    fin = _parse_dt(tarea.get("ejecutor_completo_at")) or _parse_dt(tarea.get("validado_at"))

    if estado == "completada" and fin:
        # Tarea completa: tiempo real
        consumidos = int((fin - inicio).total_seconds() / 60) - pausados
    elif pause_started:
        # Está pausada ahora: contamos hasta el momento de la pausa
        consumidos = int((pause_started - inicio).total_seconds() / 60) - pausados
    else:
        consumidos = int((_now() - inicio).total_seconds() / 60) - pausados

    consumidos = max(0, consumidos)
    pct = int((consumidos / minutos_total) * 100) if minutos_total > 0 else 0

    if estado == "completada":
        color = "green" if pct < 100 else "rojo_completado"
    elif estado in {"cancelada"}:
        color = "gray"
    elif pct >= 100:
        color = "red"
    elif pct >= 85:
        color = "orange"
    elif pct >= 70:
        color = "yellow"
    elif estado == "ayuda_pedida":
        color = "purple"
    elif estado == "por_validar":
        color = "blue"
    elif estado in {"lista", "en_progreso"}:
        color = "cyan"
    else:
        color = "gray"

    return {
        "pct": pct,
        "color": color,
        "minutos_consumidos": consumidos,
        "minutos_total": minutos_total,
        "minutos_pausados": pausados,
        "vencida": pct >= 100 and estado != "completada",
        "esta_pausada": pause_started is not None,
    }


# ── Helpers de definición de proceso ────────────────────────────────────────

def _parse_pasos_definicion(raw: Any) -> List[Dict[str, Any]]:
    """Acepta tanto el formato viejo (lista de strings) como el nuevo
    (lista de objetos con area, sla_horas, depende_de, etc.).
    """
    if not raw:
        return []
    if isinstance(raw, list):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except Exception:
            return []

    pasos: List[Dict[str, Any]] = []
    for idx, item in enumerate(data):
        if isinstance(item, str):
            # Formato viejo: solo título → la convertimos a tarea genérica del área del proceso
            pasos.append({
                "orden": idx + 1,
                "titulo": item,
                "area_code": "",
                "subarea_code": None,
                "sla_horas": 24,
                "campos_requeridos": [],
                "depende_de": [],
                "descripcion": "",
            })
        elif isinstance(item, dict):
            pasos.append({
                "orden": int(item.get("orden", idx + 1)),
                "titulo": str(item.get("titulo") or item.get("nombre") or f"Paso {idx + 1}"),
                "descripcion": str(item.get("descripcion") or ""),
                "area_code": str(item.get("area_code") or item.get("area") or ""),
                "subarea_code": item.get("subarea_code") or item.get("subarea") or None,
                "sla_horas": int(item.get("sla_horas") or 24),
                "campos_requeridos": item.get("campos_requeridos") or [],
                "depende_de": item.get("depende_de") or [],  # lista de "orden" de pasos previos
            })
    return pasos


def _resolver_lider_de_area(conn, area_code: str, subarea_code: Optional[str] = None) -> str:
    """Devuelve el username del líder asignado al área/subárea."""
    if subarea_code:
        row = conn.execute(
            "SELECT lider_username FROM gta.subareas WHERE area_code = %s AND code = %s",
            (area_code, subarea_code),
        ).fetchone()
        if row and row.get("lider_username"):
            return str(row["lider_username"])

    row = conn.execute(
        "SELECT lider_username FROM gta.areas WHERE code = %s",
        (area_code,),
    ).fetchone()
    return str(row["lider_username"]) if row and row.get("lider_username") else ""


# ── Eventos auditables ──────────────────────────────────────────────────────

def log_evento(conn, flujo_id: int, tipo: str, actor: str = "",
               tarea_id: Optional[int] = None, mensaje: str = "",
               metadata: Optional[Dict[str, Any]] = None) -> None:
    conn.execute(
        """INSERT INTO gta.flujo_eventos
           (flujo_id, tarea_id, tipo, actor, mensaje, metadata)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (flujo_id, tarea_id, tipo, actor, mensaje, json.dumps(metadata or {}, ensure_ascii=False)),
    )


# ── Crear flujo ─────────────────────────────────────────────────────────────

def crear_flujo(
    *,
    iniciado_por: str,
    titulo: str,
    descripcion: str = "",
    proceso_id: Optional[int] = None,
    datos_formulario: Optional[Dict[str, Any]] = None,
    pasos_libres: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Crea un flujo y sus tareas.

    - Si proceso_id está definido: usa la definición de pasos del proceso del catálogo
    - Si pasos_libres está definido: crea las tareas tal cual vengan (modo libre)
    - Solo uno de los dos puede venir
    """
    if not titulo.strip():
        raise ValueError("titulo es requerido")
    if proceso_id and pasos_libres:
        raise ValueError("usar proceso_id O pasos_libres, no ambos")
    if not proceso_id and not pasos_libres:
        raise ValueError("debe especificar proceso_id o pasos_libres")

    conn = db.get_conn()
    try:
        # Determinar pasos
        if proceso_id:
            proc = conn.execute(
                "SELECT * FROM gta.procesos WHERE id = %s",
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

        sla_total = sum(int(p.get("sla_horas") or 0) for p in pasos)
        now = _now()

        # Crear flujo
        flujo_row = conn.execute(
            """INSERT INTO gta.flujos
               (proceso_id, titulo, descripcion, iniciado_por, estado,
                datos_formulario, sla_horas_total, iniciado_at, created_at, updated_at)
               VALUES (%s, %s, %s, %s, 'activo', %s, %s, %s, %s, %s)
               RETURNING id""",
            (
                proceso_id, titulo.strip(), descripcion.strip(), iniciado_por,
                json.dumps(datos_formulario or {}, ensure_ascii=False),
                sla_total, now, now, now,
            ),
        ).fetchone()
        flujo_id = int(flujo_row["id"])

        # Crear tareas mapeando "orden" → id
        orden_to_id: Dict[int, int] = {}
        for paso in pasos:
            area_code = paso["area_code"]
            subarea_code = paso.get("subarea_code")
            asignado = _resolver_lider_de_area(conn, area_code, subarea_code) if area_code else ""

            tarea_row = conn.execute(
                """INSERT INTO gta.flujo_tareas
                   (flujo_id, orden, area_code, subarea_code, asignado_a,
                    titulo, descripcion, campos_requeridos, depende_de, sla_horas,
                    estado, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pendiente', %s, %s)
                   RETURNING id""",
                (
                    flujo_id,
                    paso["orden"],
                    area_code or "",
                    subarea_code,
                    asignado,
                    paso["titulo"],
                    paso.get("descripcion", ""),
                    json.dumps(paso.get("campos_requeridos") or [], ensure_ascii=False),
                    json.dumps(paso.get("depende_de") or [], ensure_ascii=False),
                    paso["sla_horas"],
                    now, now,
                ),
            ).fetchone()
            orden_to_id[paso["orden"]] = int(tarea_row["id"])

        # Resolver depende_de: convertir órdenes a tarea_ids reales
        for orden, tarea_id in orden_to_id.items():
            paso = next((p for p in pasos if p["orden"] == orden), None)
            if not paso or not paso.get("depende_de"):
                continue
            ids_dep = []
            for dep_orden in paso["depende_de"]:
                if dep_orden in orden_to_id:
                    ids_dep.append(orden_to_id[dep_orden])
            conn.execute(
                "UPDATE gta.flujo_tareas SET depende_de = %s WHERE id = %s",
                (json.dumps(ids_dep), tarea_id),
            )

        # Activar tareas sin dependencias (estado=lista, inicia el SLA)
        _activar_tareas_sin_dependencias(conn, flujo_id, now)

        log_evento(conn, flujo_id, "iniciado", iniciado_por,
                   mensaje=f"Flujo iniciado: {titulo}")
        conn.commit()

        return get_flujo(flujo_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _activar_tareas_sin_dependencias(conn, flujo_id: int, now: datetime) -> None:
    """Marca como 'lista' las tareas cuyo depende_de está vacío o cuyas dependencias
    están todas completadas. Inicia el SLA (inicio_at = now).
    """
    rows = conn.execute(
        "SELECT id, depende_de FROM gta.flujo_tareas WHERE flujo_id = %s AND estado = 'pendiente'",
        (flujo_id,),
    ).fetchall()

    for r in rows:
        deps = []
        try:
            deps = json.loads(r.get("depende_de") or "[]")
        except Exception:
            deps = []

        if not deps:
            puede_iniciar = True
        else:
            placeholders = ",".join(["%s"] * len(deps))
            done = conn.execute(
                f"SELECT COUNT(*) AS c FROM gta.flujo_tareas WHERE id IN ({placeholders}) AND estado = 'completada'",
                tuple(deps),
            ).fetchone()
            puede_iniciar = int(done["c"]) == len(deps)

        if puede_iniciar:
            conn.execute(
                "UPDATE gta.flujo_tareas SET estado = 'lista', inicio_at = %s, updated_at = %s WHERE id = %s",
                (now, now, r["id"]),
            )
            log_evento(conn, flujo_id, "tarea_lista", "system", tarea_id=r["id"],
                       mensaje="Tarea lista para ejecución")


# ── Marcar tarea como ejecutor_completo / validar ──────────────────────────

def marcar_ejecutor_completo(tarea_id: int, actor: str,
                             campos_completados: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """El ejecutor (líder del área) marca la tarea como hecha. Pasa a 'por_validar'.
    El iniciador del flujo debe validarla después.
    """
    conn = db.get_conn()
    try:
        tarea = conn.execute(
            "SELECT * FROM gta.flujo_tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea:
            raise ValueError("tarea no encontrada")
        if tarea["estado"] not in {"lista", "en_progreso", "ayuda_pedida"}:
            raise ValueError(f"no se puede completar tarea en estado '{tarea['estado']}'")

        now = _now()

        # Si está pausada por ayuda, primero reanudar
        if tarea.get("sla_pause_started_at"):
            _reanudar_sla(conn, tarea_id, now)

        conn.execute(
            """UPDATE gta.flujo_tareas
               SET estado = 'por_validar',
                   ejecutor_completo_at = %s,
                   ejecutor_completo_por = %s,
                   campos_completados = %s,
                   updated_at = %s
               WHERE id = %s""",
            (
                now, actor,
                json.dumps(campos_completados or {}, ensure_ascii=False),
                now, tarea_id,
            ),
        )
        log_evento(conn, tarea["flujo_id"], "ejecutor_completo", actor, tarea_id=tarea_id,
                   mensaje=f"Ejecutor marcó como hecha la tarea: {tarea['titulo']}")
        conn.commit()
        return _serialize_tarea(conn, tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def validar_tarea(tarea_id: int, actor: str, aceptada: bool, comentario: str = "") -> Dict[str, Any]:
    """El iniciador del flujo valida (aceptada=True) o rechaza (aceptada=False).
    Si acepta: tarea queda 'completada' y se intentan activar las dependientes.
    Si rechaza: vuelve a 'en_progreso' y queda registrado el motivo.
    """
    conn = db.get_conn()
    try:
        tarea = conn.execute(
            "SELECT t.*, f.iniciado_por FROM gta.flujo_tareas t "
            "JOIN gta.flujos f ON f.id = t.flujo_id WHERE t.id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea:
            raise ValueError("tarea no encontrada")
        if tarea["estado"] != "por_validar":
            raise ValueError(f"solo se pueden validar tareas en 'por_validar', está en '{tarea['estado']}'")

        # Solo el iniciador del flujo (o el jefe) puede validar
        flujo_iniciador = tarea["iniciado_por"]
        jefe = _settings_get(conn, "jefe_username")
        if actor != flujo_iniciador and actor != jefe:
            raise PermissionError("solo el iniciador del flujo o el jefe puede validar")

        now = _now()

        if aceptada:
            conn.execute(
                """UPDATE gta.flujo_tareas
                   SET estado = 'completada',
                       validado_at = %s,
                       validado_por = %s,
                       updated_at = %s
                   WHERE id = %s""",
                (now, actor, now, tarea_id),
            )
            log_evento(conn, tarea["flujo_id"], "validada", actor, tarea_id=tarea_id,
                       mensaje=f"Tarea validada: {tarea['titulo']}",
                       metadata={"comentario": comentario})

            # Activar dependientes
            _activar_tareas_sin_dependencias(conn, tarea["flujo_id"], now)
            _verificar_completado_flujo(conn, tarea["flujo_id"], now, actor)
        else:
            # Rechazada: vuelve a en_progreso, ejecutor debe re-trabajar
            conn.execute(
                """UPDATE gta.flujo_tareas
                   SET estado = 'en_progreso',
                       ejecutor_completo_at = NULL,
                       ejecutor_completo_por = NULL,
                       updated_at = %s
                   WHERE id = %s""",
                (now, tarea_id),
            )
            log_evento(conn, tarea["flujo_id"], "rechazada", actor, tarea_id=tarea_id,
                       mensaje=f"Tarea rechazada por validador: {tarea['titulo']}",
                       metadata={"comentario": comentario})

        conn.commit()
        return _serialize_tarea(conn, tarea_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verificar_completado_flujo(conn, flujo_id: int, now: datetime, actor: str) -> None:
    """Si todas las tareas están completadas, marca el flujo como completado."""
    pendientes = conn.execute(
        "SELECT COUNT(*) AS c FROM gta.flujo_tareas WHERE flujo_id = %s "
        "AND estado NOT IN ('completada', 'cancelada')",
        (flujo_id,),
    ).fetchone()
    if int(pendientes["c"]) == 0:
        conn.execute(
            "UPDATE gta.flujos SET estado = 'completado', completado_at = %s, updated_at = %s WHERE id = %s",
            (now, now, flujo_id),
        )
        log_evento(conn, flujo_id, "flujo_completado", actor,
                   mensaje="Todas las tareas completadas")


# ── Pedir/responder ayuda ──────────────────────────────────────────────────

def pedir_ayuda(*, tarea_id: int, pedido_por: str, pedido_a_area: str,
                pedido_a_user: str = "", mensaje: str = "",
                bloquea_sla: bool = False) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        tarea = conn.execute(
            "SELECT * FROM gta.flujo_tareas WHERE id = %s",
            (tarea_id,),
        ).fetchone()
        if not tarea:
            raise ValueError("tarea no encontrada")

        now = _now()
        ayuda_row = conn.execute(
            """INSERT INTO gta.flujo_ayudas
               (tarea_id, pedido_por, pedido_a_area, pedido_a_user, mensaje, bloquea_sla)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (tarea_id, pedido_por, pedido_a_area, pedido_a_user, mensaje, bloquea_sla),
        ).fetchone()
        ayuda_id = int(ayuda_row["id"])

        if bloquea_sla:
            conn.execute(
                """UPDATE gta.flujo_tareas
                   SET estado = 'ayuda_pedida',
                       sla_pause_started_at = %s,
                       updated_at = %s
                   WHERE id = %s""",
                (now, now, tarea_id),
            )

        log_evento(
            conn, tarea["flujo_id"], "ayuda_pedida", pedido_por, tarea_id=tarea_id,
            mensaje=f"Ayuda pedida a {pedido_a_area}: {mensaje[:80]}",
            metadata={"ayuda_id": ayuda_id, "bloquea_sla": bloquea_sla},
        )
        conn.commit()
        return {"ayuda_id": ayuda_id, "bloquea_sla": bloquea_sla, "tarea_id": tarea_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def responder_ayuda(ayuda_id: int, respondido_por: str, respuesta: str) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        ayuda = conn.execute(
            "SELECT * FROM gta.flujo_ayudas WHERE id = %s",
            (ayuda_id,),
        ).fetchone()
        if not ayuda:
            raise ValueError("ayuda no encontrada")
        if ayuda["estado"] != "abierto":
            raise ValueError(f"ayuda ya está {ayuda['estado']}")

        now = _now()
        conn.execute(
            """UPDATE gta.flujo_ayudas
               SET estado = 'respondido',
                   respondido_por = %s,
                   respuesta = %s,
                   respondido_at = %s
               WHERE id = %s""",
            (respondido_por, respuesta, now, ayuda_id),
        )

        # Si bloqueaba el SLA, reanudarlo
        if ayuda.get("bloquea_sla"):
            _reanudar_sla(conn, int(ayuda["tarea_id"]), now)
            # La tarea vuelve a 'en_progreso' (tenía 'ayuda_pedida')
            conn.execute(
                "UPDATE gta.flujo_tareas SET estado = 'en_progreso', updated_at = %s WHERE id = %s "
                "AND estado = 'ayuda_pedida'",
                (now, ayuda["tarea_id"]),
            )

        # Buscar el flujo para el evento
        tarea = conn.execute(
            "SELECT flujo_id FROM gta.flujo_tareas WHERE id = %s",
            (ayuda["tarea_id"],),
        ).fetchone()
        if tarea:
            log_evento(
                conn, int(tarea["flujo_id"]), "ayuda_respondida", respondido_por,
                tarea_id=int(ayuda["tarea_id"]),
                mensaje=f"Ayuda respondida: {respuesta[:80]}",
                metadata={"ayuda_id": ayuda_id},
            )
        conn.commit()
        return {"ayuda_id": ayuda_id, "estado": "respondido"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _reanudar_sla(conn, tarea_id: int, now: datetime) -> None:
    """Acumula el tiempo pausado en sla_paused_minutes y limpia sla_pause_started_at."""
    tarea = conn.execute(
        "SELECT sla_pause_started_at, sla_paused_minutes FROM gta.flujo_tareas WHERE id = %s",
        (tarea_id,),
    ).fetchone()
    if not tarea or not tarea.get("sla_pause_started_at"):
        return
    pause_started = _parse_dt(tarea["sla_pause_started_at"])
    if not pause_started:
        return
    pausados_extra = int((now - pause_started).total_seconds() / 60)
    nuevos_pausados = int(tarea.get("sla_paused_minutes") or 0) + max(0, pausados_extra)
    conn.execute(
        "UPDATE gta.flujo_tareas SET sla_paused_minutes = %s, sla_pause_started_at = NULL WHERE id = %s",
        (nuevos_pausados, tarea_id),
    )


# ── Lectura ────────────────────────────────────────────────────────────────

def _serialize_tarea(conn, tarea_id: int) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM gta.flujo_tareas WHERE id = %s", (tarea_id,)).fetchone()
    if not row:
        return {}
    tarea = dict(row)
    sla = calcular_sla_pct(tarea)
    tarea["sla"] = sla
    try:
        tarea["depende_de"] = json.loads(tarea.get("depende_de") or "[]")
    except Exception:
        tarea["depende_de"] = []
    try:
        tarea["campos_requeridos"] = json.loads(tarea.get("campos_requeridos") or "[]")
    except Exception:
        tarea["campos_requeridos"] = []
    try:
        tarea["campos_completados"] = json.loads(tarea.get("campos_completados") or "{}")
    except Exception:
        tarea["campos_completados"] = {}
    return tarea


def get_flujo(flujo_id: int) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        flujo = conn.execute(
            "SELECT * FROM gta.flujos WHERE id = %s",
            (flujo_id,),
        ).fetchone()
        if not flujo:
            return {}
        result = dict(flujo)
        try:
            result["datos_formulario"] = json.loads(result.get("datos_formulario") or "{}")
        except Exception:
            result["datos_formulario"] = {}

        tareas_raw = conn.execute(
            "SELECT id FROM gta.flujo_tareas WHERE flujo_id = %s ORDER BY orden, id",
            (flujo_id,),
        ).fetchall()
        result["tareas"] = [_serialize_tarea(conn, int(r["id"])) for r in tareas_raw]

        # Resumen de SLA del flujo
        total = len(result["tareas"])
        completadas = sum(1 for t in result["tareas"] if t.get("estado") == "completada")
        vencidas = sum(1 for t in result["tareas"] if t.get("sla", {}).get("vencida"))
        result["resumen"] = {
            "total_tareas": total,
            "completadas": completadas,
            "vencidas": vencidas,
            "pct_completado": int((completadas / total) * 100) if total > 0 else 0,
        }
        return result
    finally:
        conn.close()


def listar_flujos(
    *,
    actor: str,
    es_admin: bool = False,
    rol_usuario: str = "",
    estado: Optional[str] = None,
    area_code: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Lista flujos aplicando RBAC:
    - admin/jefe: ven todo
    - líder de área: ven flujos donde su área participa
    - usuario normal: ven flujos que iniciaron O donde tienen tarea asignada
    """
    conn = db.get_conn()
    try:
        jefe = _settings_get(conn, "jefe_username")
        es_jefe = (actor == jefe)
        where = ["1=1"]
        params: List[Any] = []

        if estado:
            where.append("f.estado = %s")
            params.append(estado)

        if not es_admin and not es_jefe:
            # Filtrado por visibilidad
            # ¿es líder de algún área?
            areas_lideradas = conn.execute(
                "SELECT code FROM gta.areas WHERE lider_username = %s",
                (actor,),
            ).fetchall()
            sub_lideradas = conn.execute(
                "SELECT area_code FROM gta.subareas WHERE lider_username = %s",
                (actor,),
            ).fetchall()

            visible_areas = {a["code"] for a in areas_lideradas} | {s["area_code"] for s in sub_lideradas}

            if visible_areas:
                # Líder: ve flujos donde su área participa O que él inició O donde tiene tarea
                placeholders = ",".join(["%s"] * len(visible_areas))
                where.append(
                    f"(f.iniciado_por = %s OR EXISTS (SELECT 1 FROM gta.flujo_tareas t WHERE t.flujo_id = f.id "
                    f"AND (t.asignado_a = %s OR t.area_code IN ({placeholders}))))"
                )
                params.append(actor)
                params.append(actor)
                params.extend(visible_areas)
            else:
                # Usuario común: solo lo suyo
                where.append(
                    "(f.iniciado_por = %s OR EXISTS (SELECT 1 FROM gta.flujo_tareas t WHERE t.flujo_id = f.id AND t.asignado_a = %s))"
                )
                params.append(actor)
                params.append(actor)

        if area_code:
            where.append(
                "EXISTS (SELECT 1 FROM gta.flujo_tareas t WHERE t.flujo_id = f.id AND t.area_code = %s)"
            )
            params.append(area_code)

        sql = f"""
            SELECT f.*,
                   (SELECT COUNT(*) FROM gta.flujo_tareas t WHERE t.flujo_id = f.id) AS total_tareas,
                   (SELECT COUNT(*) FROM gta.flujo_tareas t WHERE t.flujo_id = f.id AND t.estado = 'completada') AS completadas
            FROM gta.flujos f
            WHERE {' AND '.join(where)}
            ORDER BY f.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        rows = conn.execute(sql, tuple(params)).fetchall()

        items = []
        for r in rows:
            d = dict(r)
            d["pct_completado"] = int((d["completadas"] / d["total_tareas"]) * 100) if d["total_tareas"] else 0
            items.append(d)

        return {"items": items, "total": len(items)}
    finally:
        conn.close()


def get_eventos(flujo_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM gta.flujo_eventos WHERE flujo_id = %s ORDER BY created_at DESC, id DESC LIMIT %s",
            (flujo_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Métricas (resumen para el jefe) ────────────────────────────────────────

def metricas_globales() -> Dict[str, Any]:
    """Resumen general: por persona y por área."""
    conn = db.get_conn()
    try:
        # Por persona: cuántas tareas activas/completadas, tiempo promedio
        por_persona = conn.execute(
            """SELECT t.asignado_a AS persona,
                      COUNT(*) FILTER (WHERE t.estado = 'completada') AS completadas,
                      COUNT(*) FILTER (WHERE t.estado IN ('lista','en_progreso','por_validar','ayuda_pedida')) AS activas,
                      COUNT(*) FILTER (WHERE t.estado IN ('lista','en_progreso','ayuda_pedida')
                                       AND t.inicio_at IS NOT NULL
                                       AND t.sla_horas > 0
                                       AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - t.inicio_at)) / 60
                                           - COALESCE(t.sla_paused_minutes, 0)
                                           >= t.sla_horas * 60) AS vencidas,
                      AVG(EXTRACT(EPOCH FROM (t.ejecutor_completo_at - t.inicio_at)) / 60
                          - COALESCE(t.sla_paused_minutes, 0))
                          FILTER (WHERE t.estado = 'completada' AND t.inicio_at IS NOT NULL) AS prom_min
               FROM gta.flujo_tareas t
               WHERE t.asignado_a IS NOT NULL AND t.asignado_a <> ''
               GROUP BY t.asignado_a
               ORDER BY activas DESC, completadas DESC"""
        ).fetchall()

        # Por área
        por_area = conn.execute(
            """SELECT t.area_code AS area,
                      COUNT(*) FILTER (WHERE t.estado = 'completada') AS completadas,
                      COUNT(*) FILTER (WHERE t.estado IN ('lista','en_progreso','por_validar','ayuda_pedida')) AS activas,
                      COUNT(*) FILTER (WHERE t.estado IN ('lista','en_progreso','ayuda_pedida')
                                       AND t.inicio_at IS NOT NULL
                                       AND t.sla_horas > 0
                                       AND EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - t.inicio_at)) / 60
                                           - COALESCE(t.sla_paused_minutes, 0)
                                           >= t.sla_horas * 60) AS vencidas
               FROM gta.flujo_tareas t
               WHERE t.area_code IS NOT NULL AND t.area_code <> ''
               GROUP BY t.area_code
               ORDER BY activas DESC"""
        ).fetchall()

        # Totales globales
        total_flujos = conn.execute(
            """SELECT
                  COUNT(*) FILTER (WHERE estado = 'activo') AS activos,
                  COUNT(*) FILTER (WHERE estado = 'completado') AS completados,
                  COUNT(*) FILTER (WHERE estado = 'vencido') AS vencidos,
                  COUNT(*) AS total
               FROM gta.flujos"""
        ).fetchone()

        return {
            "totales": dict(total_flujos) if total_flujos else {},
            "por_persona": [dict(r) for r in por_persona],
            "por_area": [dict(r) for r in por_area],
        }
    finally:
        conn.close()
