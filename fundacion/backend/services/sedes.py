"""Servicio de sedes y scope por sede.

El scope se basa en `fundacion.sede_membresias` versionada. Admin global,
admin de Fundación y jefatura (directora_social, jefa_pedagogica,
coordinadora_territorial) tienen super_scope = todas las sedes activas.

El bloqueo es bilateral: backend filtra TODO endpoint que reciba sede_id, y
el frontend solo ve las sedes que el backend autoriza.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from plataforma.core import db


# ── Helpers de identidad ────────────────────────────────────────────────

def usuario_id_de_username(username: str) -> Optional[int]:
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


# ── Scope ──────────────────────────────────────────────────────────────

def es_super_scope(usuario_id: int) -> bool:
    """Admin/Jefatura ve todas las sedes sin necesidad de membresía."""
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT fundacion.es_super_scope(%s) AS r", (usuario_id,),
        ).fetchone()
        return bool(row and row["r"])
    finally:
        conn.close()


def sedes_accesibles(usuario_id: int) -> List[Dict[str, Any]]:
    """Sedes accesibles por el usuario, en formato listo para serializar."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT s.id, s.code, s.nombre, s.region, s.descripcion,
                      s.icono, s.color, s.activo, s.orden,
                      fundacion.lider_vigente_sede(s.id) AS lider_id
               FROM fundacion.sedes s
               JOIN fundacion.sedes_accesibles(%s) a ON a.sede_id = s.id
               ORDER BY s.orden, s.code""",
            (usuario_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def tiene_acceso_sede(usuario_id: int, sede_id: int) -> bool:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT fundacion.tiene_acceso_sede(%s, %s) AS r",
            (usuario_id, sede_id),
        ).fetchone()
        return bool(row and row["r"])
    finally:
        conn.close()


def sede_codes_accesibles(usuario_id: int) -> List[str]:
    """Lista de códigos (string) de sedes accesibles. Útil para filtrar
    consultas que aún usan `sede` como text (ej: fundacion_tareas.sede)."""
    sedes = sedes_accesibles(usuario_id)
    return [s["code"] for s in sedes]


# ── Listado / detalle / CRUD de sedes ──────────────────────────────────

def listar_todas_sedes(*, incluir_inactivas: bool = False) -> List[Dict[str, Any]]:
    """Vista admin: todas las sedes existentes. NO filtra por scope (la usa
    solo el panel de configuración para admins)."""
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM fundacion.sedes"
        if not incluir_inactivas:
            sql += " WHERE activo = TRUE"
        sql += " ORDER BY orden, code"
        rows = conn.execute(sql).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_sede_por_id(sede_id: int) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM fundacion.sedes WHERE id = %s", (sede_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_sede_por_code(code: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM fundacion.sedes WHERE code = %s", (code,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def crear_sede(
    *,
    code: str, nombre: str,
    region: Optional[str] = None,
    descripcion: Optional[str] = None,
    icono: Optional[str] = None,
    color: Optional[str] = None,
    orden: int = 99,
) -> Dict[str, Any]:
    code = (code or "").strip().lower()
    nombre = (nombre or "").strip()
    if not code or not nombre:
        raise ValueError("code y nombre son obligatorios")

    conn = db.get_conn()
    try:
        row = conn.execute(
            """INSERT INTO fundacion.sedes (code, nombre, region, descripcion, icono, color, orden)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
            (code, nombre, region, descripcion, icono, color, orden),
        ).fetchone()
        conn.commit()
        return get_sede_por_id(int(row["id"])) or {}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def actualizar_sede(sede_id: int, **fields: Any) -> Dict[str, Any]:
    allowed = {"nombre", "region", "descripcion", "icono", "color", "activo", "orden"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k} = %s")
            params.append(v)
    if not sets:
        return get_sede_por_id(sede_id) or {}
    params.append(sede_id)

    conn = db.get_conn()
    try:
        conn.execute(
            f"UPDATE fundacion.sedes SET {', '.join(sets)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            tuple(params),
        )
        conn.commit()
        return get_sede_por_id(sede_id) or {}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
