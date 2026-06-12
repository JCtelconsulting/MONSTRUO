"""Servicio de membresías persona ↔ subárea.

Una persona puede ser miembro o líder de una subárea. La membresía es
versionada (desde/hasta) — cuando alguien se va o cambia de área, se cierra
la fila vigente y se abre una nueva. Las tareas siguen vivas porque apuntan
a la subárea, no al usuario.

Reglas (impuestas también con índices únicos parciales en SQL):
- Una persona tiene UNA membresía principal vigente a la vez.
- Una subárea tiene como mucho UN líder vigente.
- No hay membresías duplicadas (mismo usuario+subárea vigente).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from plataforma.core import db


# ── Listado ─────────────────────────────────────────────────────────────

def listar_membresias_subarea(subarea_id: int, *, incluir_historico: bool = False) -> List[Dict[str, Any]]:
    """Miembros de una subárea (vigentes por default)."""
    conn = db.get_conn()
    try:
        sql = """
            SELECT m.id, m.usuario_id, m.subarea_id, m.rol, m.es_principal,
                   m.desde, m.hasta, m.motivo,
                   u.username
            FROM gta.area_membresias m
            JOIN auth.users u ON u.id = m.usuario_id
            WHERE m.subarea_id = %s
        """
        if not incluir_historico:
            sql += " AND m.hasta IS NULL"
        sql += " ORDER BY (m.rol = 'lider') DESC, m.es_principal DESC, m.desde"
        rows = conn.execute(sql, (subarea_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def listar_membresias_usuario(usuario_id: int, *, incluir_historico: bool = False) -> List[Dict[str, Any]]:
    """Subáreas de un usuario (vigentes por default)."""
    conn = db.get_conn()
    try:
        sql = """
            SELECT m.id, m.usuario_id, m.subarea_id, m.rol, m.es_principal,
                   m.desde, m.hasta, m.motivo,
                   s.code AS subarea_code, s.label AS subarea_label,
                   s.area_code,
                   a.label AS area_label
            FROM gta.area_membresias m
            JOIN gta.subareas s ON s.id = m.subarea_id
            JOIN gta.areas a ON a.code = s.area_code
            WHERE m.usuario_id = %s
        """
        if not incluir_historico:
            sql += " AND m.hasta IS NULL"
        sql += " ORDER BY m.es_principal DESC, m.desde"
        rows = conn.execute(sql, (usuario_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def subarea_ids_de_usuario(usuario_id: int) -> List[int]:
    """IDs de subáreas vigentes del usuario. Útil para 'mi bandeja'."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT subarea_id FROM gta.area_membresias
               WHERE usuario_id = %s AND hasta IS NULL""",
            (usuario_id,),
        ).fetchall()
        return [int(r["subarea_id"]) for r in rows]
    finally:
        conn.close()


def area_codes_de_usuario(usuario_id: int) -> List[str]:
    """Códigos de áreas vigentes del usuario (deduplicados). Útil para
    filtrar quiebres dirigidos a 'mi área'."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT DISTINCT s.area_code
               FROM gta.area_membresias m
               JOIN gta.subareas s ON s.id = m.subarea_id
               WHERE m.usuario_id = %s AND m.hasta IS NULL""",
            (usuario_id,),
        ).fetchall()
        return [r["area_code"] for r in rows]
    finally:
        conn.close()


# ── Asignar / cerrar membresía ──────────────────────────────────────────

def asignar_membresia(
    *,
    usuario_id: int,
    subarea_id: int,
    rol: str = "miembro",
    es_principal: bool = False,
    asignado_por: int,
    motivo: Optional[str] = None,
) -> Dict[str, Any]:
    """Crea una membresía vigente. Si el usuario ya es miembro de esa subárea,
    cierra la anterior y crea una nueva (cambio de rol o de tipo principal).

    Si es_principal=True, cierra cualquier otra membresía principal vigente
    del usuario.
    Si rol='lider', cierra el líder vigente actual de la subárea (si existe).
    """
    if rol not in ("miembro", "lider"):
        raise ValueError("rol debe ser 'miembro' o 'lider'")

    conn = db.get_conn()
    try:
        # Cerrar membresía vigente del mismo (usuario, subárea), si existe
        conn.execute(
            """UPDATE gta.area_membresias
               SET hasta = CURRENT_TIMESTAMP
               WHERE usuario_id = %s AND subarea_id = %s AND hasta IS NULL""",
            (usuario_id, subarea_id),
        )

        # Si va a ser líder, cerrar al líder vigente actual (si no es el mismo user)
        if rol == "lider":
            conn.execute(
                """UPDATE gta.area_membresias
                   SET hasta = CURRENT_TIMESTAMP
                   WHERE subarea_id = %s AND rol = 'lider'
                     AND usuario_id <> %s AND hasta IS NULL""",
                (subarea_id, usuario_id),
            )

        # Si esta es principal, cerrar la principal vigente actual del user en otras subáreas
        if es_principal:
            conn.execute(
                """UPDATE gta.area_membresias
                   SET hasta = CURRENT_TIMESTAMP
                   WHERE usuario_id = %s AND es_principal = TRUE
                     AND subarea_id <> %s AND hasta IS NULL""",
                (usuario_id, subarea_id),
            )

        row = conn.execute(
            """INSERT INTO gta.area_membresias
               (usuario_id, subarea_id, rol, es_principal, asignado_por, motivo)
               VALUES (%s, %s, %s, %s, %s, %s)
               RETURNING id, desde""",
            (usuario_id, subarea_id, rol, es_principal, asignado_por, motivo),
        ).fetchone()
        conn.commit()
        return {"id": int(row["id"]), "desde": row["desde"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cerrar_membresia(membresia_id: int, *, cerrado_por: int, motivo: Optional[str] = None) -> bool:
    """Cierra una membresía vigente seteando hasta=now()."""
    conn = db.get_conn()
    try:
        result = conn.execute(
            """UPDATE gta.area_membresias
               SET hasta = CURRENT_TIMESTAMP,
                   motivo = COALESCE(%s, motivo)
               WHERE id = %s AND hasta IS NULL
               RETURNING id""",
            (motivo, membresia_id),
        ).fetchone()
        conn.commit()
        return bool(result)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
