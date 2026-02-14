#!/usr/bin/env python3
"""
Reasigna tickets con asignado_a huérfano (usuario eliminado).

Uso:
  python3 code/scripts/maintenance/reassign_orphan_tickets.py --dry-run
  python3 code/scripts/maintenance/reassign_orphan_tickets.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import db, tickets_service


TECH_ROLES = ("redes", "sistemas", "implementaciones", "ops")
PRIORITY_BY_CATEGORY: Dict[str, List[str]] = {
    "redes": ["redes", "sistemas", "ejecucion"],
    "sistemas": ["sistemas", "redes", "ejecucion"],
    "ejecucion": ["ejecucion", "sistemas", "redes"],
    "admin": ["ejecucion", "sistemas", "redes"],
    # Para "general", preferimos balancear entre técnicos disponibles
    # en vez de sesgar siempre a una especialidad concreta.
    "general": [],
}


def _select_by_specialty(conn, specialty: str) -> Optional[str]:
    role_placeholders = ", ".join(["?"] * len(TECH_ROLES))
    params = (specialty, *TECH_ROLES)
    row = conn.execute(
        f"""
        SELECT us.username
        FROM user_specialties us
        JOIN users u ON u.username = us.username
        WHERE us.specialty = ?
          AND us.is_available = 1
          AND us.current_load < us.max_load
          AND COALESCE(u.is_active, 1) = 1
          AND u.role IN ({role_placeholders})
        ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
        LIMIT 1
        """,
        params,
    ).fetchone()
    return row["username"] if row else None


def _select_any_technical(conn) -> Optional[str]:
    role_placeholders = ", ".join(["?"] * len(TECH_ROLES))
    row = conn.execute(
        f"""
        SELECT us.username
        FROM user_specialties us
        JOIN users u ON u.username = us.username
        WHERE us.is_available = 1
          AND us.current_load < us.max_load
          AND COALESCE(u.is_active, 1) = 1
          AND u.role IN ({role_placeholders})
        ORDER BY us.current_load ASC, us.updated_at ASC NULLS FIRST, us.username ASC
        LIMIT 1
        """,
        TECH_ROLES,
    ).fetchone()
    return row["username"] if row else None


def _pick_candidate(conn, category: Optional[str]) -> Optional[str]:
    cat = (category or "general").strip().lower()
    priorities = PRIORITY_BY_CATEGORY.get(cat, PRIORITY_BY_CATEGORY["general"])

    for specialty in priorities:
        username = _select_by_specialty(conn, specialty)
        if username:
            return username

    return _select_any_technical(conn)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplica cambios")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita tickets a procesar (0 = todos)",
    )
    args = parser.parse_args()

    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT t.id, t.codigo, t.titulo, COALESCE(t.categoria, 'general') AS categoria, t.asignado_a
            FROM tickets t
            LEFT JOIN users u ON u.username = t.asignado_a
            WHERE t.asignado_a IS NOT NULL
              AND u.username IS NULL
            ORDER BY t.id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    if not rows:
        print("No hay tickets con asignado_a huérfano.")
        return 0

    print(f"Tickets huérfanos detectados: {len(rows)}")
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Modo: {mode}")

    applied = 0
    unresolved = 0

    for row in rows:
        conn = db.get_conn()
        try:
            candidate = _pick_candidate(conn, row["categoria"])
        finally:
            conn.close()

        old_assignee = row["asignado_a"]
        code = row["codigo"] or f"#{row['id']}"
        title = (row["titulo"] or "").strip()
        if len(title) > 80:
            title = title[:77] + "..."

        if not candidate:
            unresolved += 1
            print(
                f"[WARN] {code}: sin candidato disponible (cat={row['categoria']}, old={old_assignee})"
            )
            if args.apply:
                tickets_service.update_ticket(row["id"], {"asignado_a": None})
                applied += 1
            continue

        print(
            f"[OK] {code}: {old_assignee} -> {candidate} "
            f"(cat={row['categoria']}) | {title}"
        )
        if args.apply:
            tickets_service.update_ticket(row["id"], {"asignado_a": candidate})
            applied += 1

    print(
        f"Resumen: total={len(rows)} apply={applied} unresolved={unresolved} mode={mode}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
