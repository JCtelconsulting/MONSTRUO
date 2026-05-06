"""Servicio de membresías persona ↔ sede en Fundación.

Misma idea que gta.area_membresias: versionado por (desde, hasta).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from plataforma.core import db


_VALID_ROLES = {"lider_educativo", "gestora_educativa", "ejecutiva"}


def listar_membresias_sede(sede_id: int, *, incluir_historico: bool = False) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        sql = """
            SELECT m.id, m.usuario_id, m.sede_id, m.rol, m.desde, m.hasta, m.motivo,
                   u.username,
                   s.code AS sede_code, s.nombre AS sede_nombre
            FROM fundacion.sede_membresias m
            JOIN auth.users u ON u.id = m.usuario_id
            JOIN fundacion.sedes s ON s.id = m.sede_id
            WHERE m.sede_id = %s
        """
        if not incluir_historico:
            sql += " AND m.hasta IS NULL"
        sql += " ORDER BY (m.rol = 'lider_educativo') DESC, u.username"
        rows = conn.execute(sql, (sede_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_membresias_usuario(usuario_id: int, *, incluir_historico: bool = False) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        sql = """
            SELECT m.id, m.usuario_id, m.sede_id, m.rol, m.desde, m.hasta, m.motivo,
                   s.code AS sede_code, s.nombre AS sede_nombre
            FROM fundacion.sede_membresias m
            JOIN fundacion.sedes s ON s.id = m.sede_id
            WHERE m.usuario_id = %s
        """
        if not incluir_historico:
            sql += " AND m.hasta IS NULL"
        sql += " ORDER BY m.desde"
        rows = conn.execute(sql, (usuario_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_todas_membresias_vigentes() -> List[Dict[str, Any]]:
    """Para el panel admin: TODAS las membresías vigentes."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT m.id, m.usuario_id, m.sede_id, m.rol, m.desde, m.motivo,
                      u.username,
                      s.code AS sede_code, s.nombre AS sede_nombre
               FROM fundacion.sede_membresias m
               JOIN auth.users u ON u.id = m.usuario_id
               JOIN fundacion.sedes s ON s.id = m.sede_id
               WHERE m.hasta IS NULL
               ORDER BY s.orden, (m.rol='lider_educativo') DESC, u.username"""
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def asignar_membresia(
    *,
    usuario_id: int,
    sede_id: int,
    rol: str,
    asignado_por: Optional[int],
    motivo: Optional[str] = None,
) -> Dict[str, Any]:
    if rol not in _VALID_ROLES:
        raise ValueError(f"rol inválido: {rol}")

    conn = db.get_conn()
    try:
        # Cerrar membresía vigente del mismo (usuario, sede, rol)
        conn.execute(
            """UPDATE fundacion.sede_membresias
               SET hasta = CURRENT_TIMESTAMP
               WHERE usuario_id = %s AND sede_id = %s AND rol = %s AND hasta IS NULL""",
            (usuario_id, sede_id, rol),
        )
        # Si es líder, cerrar al líder vigente actual de la sede
        if rol == "lider_educativo":
            conn.execute(
                """UPDATE fundacion.sede_membresias
                   SET hasta = CURRENT_TIMESTAMP
                   WHERE sede_id = %s AND rol = 'lider_educativo'
                     AND usuario_id <> %s AND hasta IS NULL""",
                (sede_id, usuario_id),
            )

        row = conn.execute(
            """INSERT INTO fundacion.sede_membresias
               (usuario_id, sede_id, rol, asignado_por, motivo)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, desde""",
            (usuario_id, sede_id, rol, asignado_por, motivo),
        ).fetchone()
        conn.commit()
        return {"id": int(row["id"]), "desde": row["desde"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cerrar_membresia(membresia_id: int, *, motivo: Optional[str] = None) -> bool:
    conn = db.get_conn()
    try:
        row = conn.execute(
            """UPDATE fundacion.sede_membresias
               SET hasta = CURRENT_TIMESTAMP,
                   motivo = COALESCE(%s, motivo)
               WHERE id = %s AND hasta IS NULL
               RETURNING id""",
            (motivo, membresia_id),
        ).fetchone()
        conn.commit()
        return bool(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
