"""Servicio de procesos unificado.

Un proceso es la entidad central:
- Puede tener un archivo descriptivo (gta/data/procesos/<area>/<sub>/<file>)
- Puede tener una definición ejecutable (pasos_definicion JSON con áreas/SLAs/dependencias)
- Tiene quiebres asociados (gta.quiebres.proceso_id)
- Tiene comentarios/decisiones (gta.proceso_comentarios)
- Puede generar flujos (gta.flujos.proceso_id)

Esto reemplaza la separación previa entre Catálogo (procesos ejecutables),
Documentos (archivos descargados) y la gestión admin de procesos.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from plataforma.core import db
from gta.backend.services import catalogo as catalogo_service


# ── Helpers ──────────────────────────────────────────────────────────────

def _data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "procesos"


def _safe_json_load(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _serialize_proceso(row: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(row)
    p["pasos_definicion"] = _safe_json_load(p.get("pasos_definicion"), [])
    p["campos_formulario"] = _safe_json_load(p.get("campos_formulario"), [])
    p["tiene_archivo"] = bool(p.get("archivo_path"))
    p["tiene_definicion"] = bool(p["pasos_definicion"])
    return p


# ── Seed: poblar procesos desde archivos descargados ────────────────────

def seed_procesos_from_files(actor: str = "system") -> Dict[str, Any]:
    """Recorre gta/data/procesos/ y crea registros en gta.procesos por cada archivo
    que aún no esté registrado. Idempotente: si ya existe un proceso con ese
    archivo_path, no lo duplica.
    """
    catalog = catalogo_service.scan_catalog()
    creados = 0
    omitidos = 0
    archivos: List[Dict[str, Any]] = []

    # Aplanar todos los archivos del scan
    for area in catalog.get("areas", []):
        area_code = area["code"]
        for f in area.get("files", []):
            archivos.append({
                "area_code": area_code, "subarea_code": None, **f,
            })
        for sub in area.get("subareas", []):
            for f in sub.get("files", []):
                archivos.append({
                    "area_code": area_code, "subarea_code": sub["code"], **f,
                })
    # Sueltos en raíz: sin área conocida, los saltamos del seed automático
    # para evitar adivinar mal — el admin puede crearlos manualmente

    conn = db.get_conn()
    try:
        for f in archivos:
            existing = conn.execute(
                "SELECT id FROM gta.procesos WHERE archivo_path = %s",
                (f["path"],),
            ).fetchone()
            if existing:
                omitidos += 1
                continue

            nombre = f["name"]
            descripcion = f"Proceso documentado en archivo {f['filename']}"
            conn.execute(
                """INSERT INTO gta.procesos
                   (nombre, area, subarea_code, descripcion, archivo_path,
                    pasos_definicion, campos_formulario, estado, creado_por,
                    icono, version)
                   VALUES (%s, %s, %s, %s, %s, '[]', '[]', 'activo', %s, %s, 1)""",
                (
                    nombre,
                    f["area_code"],
                    f.get("subarea_code"),
                    descripcion,
                    f["path"],
                    actor,
                    f.get("icon", "fa-file"),
                ),
            )
            creados += 1

        conn.commit()
        return {"creados": creados, "omitidos": omitidos, "total_archivos": len(archivos)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Listado / detalle ──────────────────────────────────────────────────

def listar_procesos(
    *,
    area_code: Optional[str] = None,
    subarea_code: Optional[str] = None,
    estado: Optional[str] = "activo",
    busqueda: Optional[str] = None,
) -> Dict[str, Any]:
    """Devuelve procesos agrupados por área → subárea, con metadatos clave."""
    conn = db.get_conn()
    try:
        where = ["1=1"]
        params: List[Any] = []

        if estado:
            where.append("p.estado = %s")
            params.append(estado)
        if area_code:
            where.append("p.area = %s")
            params.append(area_code)
        if subarea_code:
            where.append("p.subarea_code = %s")
            params.append(subarea_code)
        if busqueda:
            where.append("(LOWER(p.nombre) LIKE %s OR LOWER(p.descripcion) LIKE %s)")
            q = f"%{busqueda.lower()}%"
            params.append(q)
            params.append(q)

        rows = conn.execute(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM gta.flujos f WHERE f.proceso_id = p.id) AS flujos_count,
                       (SELECT COUNT(*) FROM gta.quiebres q WHERE q.proceso_id = p.id) AS quiebres_count,
                       (SELECT COUNT(*) FROM gta.quiebres q WHERE q.proceso_id = p.id AND q.estado = 'abierto') AS quiebres_abiertos
                FROM gta.procesos p
                WHERE {' AND '.join(where)}
                ORDER BY p.area, p.subarea_code NULLS FIRST, p.nombre""",
            tuple(params),
        ).fetchall()

        return {"items": [_serialize_proceso(r) for r in rows]}
    finally:
        conn.close()


def get_proceso(proceso_id: int) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """SELECT p.*,
                      (SELECT COUNT(*) FROM gta.flujos f WHERE f.proceso_id = p.id) AS flujos_count,
                      (SELECT COUNT(*) FROM gta.quiebres q WHERE q.proceso_id = p.id) AS quiebres_count
               FROM gta.procesos p WHERE p.id = %s""",
            (proceso_id,),
        ).fetchone()
        if not row:
            return {}
        proc = _serialize_proceso(row)

        # Flujos ejecutados de este proceso
        flujos = conn.execute(
            """SELECT id, titulo, estado, iniciado_por, created_at, completado_at,
                      (SELECT COUNT(*) FROM gta.flujo_tareas t WHERE t.flujo_id = f.id) AS total_tareas,
                      (SELECT COUNT(*) FROM gta.flujo_tareas t WHERE t.flujo_id = f.id AND t.estado = 'completada') AS completadas
               FROM gta.flujos f
               WHERE proceso_id = %s
               ORDER BY created_at DESC
               LIMIT 50""",
            (proceso_id,),
        ).fetchall()
        proc["flujos"] = [dict(f) for f in flujos]

        # Quiebres de este proceso
        quiebres = conn.execute(
            """SELECT id, descripcion, area, tipo, estado, reportado_por,
                      nota_resolucion, resuelto_por, resuelto_at, created_at
               FROM gta.quiebres
               WHERE proceso_id = %s
               ORDER BY created_at DESC""",
            (proceso_id,),
        ).fetchall()
        proc["quiebres"] = [dict(q) for q in quiebres]

        # Comentarios / decisiones / cambios
        comentarios = conn.execute(
            """SELECT id, autor, texto, tipo, created_at
               FROM gta.proceso_comentarios
               WHERE proceso_id = %s
               ORDER BY created_at DESC""",
            (proceso_id,),
        ).fetchall()
        proc["comentarios"] = [dict(c) for c in comentarios]

        # Métrica simple: tiempo promedio real de los flujos completados
        m = conn.execute(
            """SELECT
                  AVG(EXTRACT(EPOCH FROM (completado_at - iniciado_at)) / 3600) AS prom_horas,
                  COUNT(*) AS completados
               FROM gta.flujos
               WHERE proceso_id = %s AND estado = 'completado'
                 AND iniciado_at IS NOT NULL AND completado_at IS NOT NULL""",
            (proceso_id,),
        ).fetchone()
        proc["metricas"] = {
            "prom_horas": float(m["prom_horas"]) if m and m.get("prom_horas") else None,
            "flujos_completados": int(m.get("completados") or 0) if m else 0,
            "sla_horas_total": int(proc.get("sla_horas") or 0),
        }

        return proc
    finally:
        conn.close()


# ── Crear / editar ──────────────────────────────────────────────────────

def crear_proceso(
    *,
    nombre: str,
    area: str,
    subarea_code: Optional[str] = None,
    descripcion: str = "",
    pasos_definicion: Optional[List[Dict[str, Any]]] = None,
    archivo_path: Optional[str] = None,
    sla_horas: Optional[int] = None,
    icono: str = "fa-tasks",
    creado_por: str = "system",
) -> Dict[str, Any]:
    if not nombre.strip():
        raise ValueError("nombre es requerido")
    if not area.strip():
        raise ValueError("area es requerida")

    pasos = pasos_definicion or []
    sla_total = sla_horas
    if sla_total is None and pasos:
        sla_total = sum(int(p.get("sla_horas") or 0) for p in pasos)

    conn = db.get_conn()
    try:
        row = conn.execute(
            """INSERT INTO gta.procesos
               (nombre, area, subarea_code, descripcion, pasos_definicion,
                campos_formulario, sla_horas, icono, archivo_path,
                estado, creado_por, version)
               VALUES (%s, %s, %s, %s, %s, '[]', %s, %s, %s, 'activo', %s, 1)
               RETURNING id""",
            (
                nombre.strip(), area, subarea_code, descripcion,
                json.dumps(pasos, ensure_ascii=False),
                sla_total, icono, archivo_path, creado_por,
            ),
        ).fetchone()
        nuevo_id = int(row["id"])
        conn.execute(
            """INSERT INTO gta.proceso_comentarios (proceso_id, autor, texto, tipo)
               VALUES (%s, %s, %s, 'cambio')""",
            (nuevo_id, creado_por, "Proceso creado"),
        )
        conn.commit()
        return get_proceso(nuevo_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def actualizar_proceso(
    proceso_id: int,
    *,
    actor: str,
    nombre: Optional[str] = None,
    area: Optional[str] = None,
    subarea_code: Optional[str] = None,
    descripcion: Optional[str] = None,
    pasos_definicion: Optional[List[Dict[str, Any]]] = None,
    campos_formulario: Optional[List[Dict[str, Any]]] = None,
    sla_horas: Optional[int] = None,
    icono: Optional[str] = None,
    archivo_path: Optional[str] = None,
    estado: Optional[str] = None,
) -> Dict[str, Any]:
    fields: List[str] = []
    params: List[Any] = []
    cambios: List[str] = []

    for col, val, label in (
        ("nombre", nombre, "nombre"),
        ("area", area, "área"),
        ("subarea_code", subarea_code, "subárea"),
        ("descripcion", descripcion, "descripción"),
        ("sla_horas", sla_horas, "SLA"),
        ("icono", icono, "icono"),
        ("archivo_path", archivo_path, "archivo"),
        ("estado", estado, "estado"),
    ):
        if val is not None:
            fields.append(f"{col} = %s")
            params.append(val)
            cambios.append(label)

    if pasos_definicion is not None:
        fields.append("pasos_definicion = %s")
        params.append(json.dumps(pasos_definicion, ensure_ascii=False))
        cambios.append("definición de pasos")
        # Recalcular SLA total si no vino explícito
        if sla_horas is None:
            sla_total = sum(int(p.get("sla_horas") or 0) for p in pasos_definicion)
            fields.append("sla_horas = %s")
            params.append(sla_total)

    if campos_formulario is not None:
        fields.append("campos_formulario = %s")
        params.append(json.dumps(campos_formulario, ensure_ascii=False))
        cambios.append("campos del formulario")

    if not fields:
        return get_proceso(proceso_id)

    fields.append("version = COALESCE(version, 1) + 1")
    fields.append("updated_at = CURRENT_TIMESTAMP")
    params.append(proceso_id)

    conn = db.get_conn()
    try:
        conn.execute(
            f"UPDATE gta.procesos SET {', '.join(fields)} WHERE id = %s",
            tuple(params),
        )
        if cambios:
            conn.execute(
                """INSERT INTO gta.proceso_comentarios (proceso_id, autor, texto, tipo)
                   VALUES (%s, %s, %s, 'cambio')""",
                (proceso_id, actor, f"Modificado: {', '.join(cambios)}"),
            )
        conn.commit()
        return get_proceso(proceso_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Comentarios ────────────────────────────────────────────────────────

def agregar_comentario(proceso_id: int, autor: str, texto: str, tipo: str = "nota") -> Dict[str, Any]:
    if not texto.strip():
        raise ValueError("texto es requerido")
    if tipo not in {"nota", "cambio", "decision"}:
        tipo = "nota"
    conn = db.get_conn()
    try:
        row = conn.execute(
            """INSERT INTO gta.proceso_comentarios (proceso_id, autor, texto, tipo)
               VALUES (%s, %s, %s, %s)
               RETURNING id, created_at""",
            (proceso_id, autor, texto.strip(), tipo),
        ).fetchone()
        conn.commit()
        return {"id": int(row["id"]), "created_at": row["created_at"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Quiebres asociados a procesos ─────────────────────────────────────

def reportar_quiebre(
    *,
    proceso_id: Optional[int],
    descripcion: str,
    area: str,
    reportado_por: str,
    tipo: str = "sin_proceso",
    flujo_tarea_id: Optional[int] = None,
) -> Dict[str, Any]:
    if not descripcion.strip():
        raise ValueError("descripción es requerida")
    conn = db.get_conn()
    try:
        # Si viene flujo_tarea_id, heredar proceso_id automáticamente
        if flujo_tarea_id and not proceso_id:
            inh = conn.execute(
                """SELECT f.proceso_id FROM gta.flujo_tareas t
                   JOIN gta.flujos f ON f.id = t.flujo_id
                   WHERE t.id = %s""",
                (flujo_tarea_id,),
            ).fetchone()
            if inh and inh.get("proceso_id"):
                proceso_id = int(inh["proceso_id"])

        row = conn.execute(
            """INSERT INTO gta.quiebres
               (descripcion, area, tipo, proceso_id, reportado_por, estado)
               VALUES (%s, %s, %s, %s, %s, 'abierto')
               RETURNING id, created_at""",
            (descripcion.strip(), area, tipo, proceso_id, reportado_por),
        ).fetchone()
        conn.commit()
        return {"id": int(row["id"]), "created_at": row["created_at"], "proceso_id": proceso_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Subir archivo a un proceso (o crear proceso a partir de archivo) ──

ALLOWED_UPLOAD_EXT = {".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".md"}


def _sanitize_filename(name: str) -> str:
    import re
    safe = re.sub(r"[^a-zA-Z0-9_.\- ]", "_", name)
    return safe.strip()[:200] or "archivo"


def guardar_archivo_subido(
    *,
    proceso_id: int,
    filename: str,
    contenido: bytes,
    actor: str,
) -> Dict[str, Any]:
    """Guarda un archivo en gta/data/procesos/<area>/<sub>/ y vincula al proceso."""
    proc = get_proceso(proceso_id)
    if not proc:
        raise ValueError("proceso no encontrado")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_UPLOAD_EXT:
        raise ValueError(f"extensión no permitida: {ext}")

    safe_name = _sanitize_filename(filename)
    area = str(proc.get("area") or "_sin_area")
    subarea = str(proc.get("subarea_code") or "")

    target_dir = _data_root() / area
    if subarea:
        target_dir = target_dir / subarea
    target_dir.mkdir(parents=True, exist_ok=True)

    target = target_dir / safe_name
    # Si existe, agregar sufijo
    if target.exists():
        stem = target.stem
        idx = 1
        while target.exists():
            target = target_dir / f"{stem}_{idx}{ext}"
            idx += 1

    target.write_bytes(contenido)

    rel_path = target.relative_to(_data_root()).as_posix()
    return actualizar_proceso(
        proceso_id, actor=actor, archivo_path=rel_path,
    )
