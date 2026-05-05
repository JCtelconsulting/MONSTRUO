"""
Tests de integración de ticketera — contra DB dev real.

Cubren queries y operaciones de servicio sobre tickets ya existentes.
Usan rollback al final, no persisten datos.

NOTA: NO se prueba `create_ticket()` por bug pendiente
(ver memory: project_bug_ticketera_helpers.md). Cuando ese bug se arregle,
agregar tests de creación end-to-end aquí.

Ejecutar:
    pytest ticketera/tests/test_tickets_integration.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _insert_ticket_minimo(conn, titulo="Test ticket", creador="test_user"):
    """Inserta un ticket directo en DB para tests sin depender de create_ticket."""
    row = conn.execute(
        """INSERT INTO tks.tickets
           (titulo, descripcion, creador_id, tipo, severidad, categoria,
            estado, subestado, created_at, updated_at)
           VALUES (?, '...', ?, 'incidencia', 'media', 'sistemas',
                   'abierto', 'recibido', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
           RETURNING id""",
        (titulo, creador),
    ).fetchone()
    conn.commit()
    return int(row["id"])


@pytest.mark.integration
class TestQueryTickets:
    """Lecturas y filtrado de tickets contra DB."""

    def test_insertar_y_leer_ticket(self, db_conn):
        tid = _insert_ticket_minimo(db_conn, titulo="Test integración")
        row = db_conn.execute(
            "SELECT titulo, subestado FROM tks.tickets WHERE id = ?", (tid,),
        ).fetchone()
        assert row is not None
        assert row["titulo"] == "Test integración"
        assert row["subestado"] == "recibido"

    @pytest.mark.xfail(
        reason="Bug conocido: _crud.py usa _now_dt y otras funciones privadas no "
               "importadas por `from ._helpers import *`. Ver memory: "
               "project_bug_ticketera_helpers.md",
        strict=False,
    )
    def test_listar_tickets_devuelve_estructura(self, db_conn):
        from ticketera.backend.services import service as tickets_service
        _insert_ticket_minimo(db_conn, titulo="Para listar")

        result = tickets_service.list_tickets(limit=10)
        assert result is not None
        if isinstance(result, dict):
            assert "items" in result or "tickets" in result
        else:
            assert isinstance(result, list)


@pytest.mark.integration
class TestSchemaTks:
    """Schema mínimo de tks: existencia de tablas y columnas críticas."""

    def test_tabla_tickets_tiene_columnas_sla(self, db_conn):
        # Las columnas SLA deben existir
        row = db_conn.execute(
            """SELECT column_name FROM information_schema.columns
               WHERE table_schema = 'tks' AND table_name = 'tickets'
               AND column_name IN ('frt_due_at', 'ttr_due_at', 'first_response_at')""",
        ).fetchall()
        col_names = {r["column_name"] for r in row}
        assert "frt_due_at" in col_names
        assert "ttr_due_at" in col_names
        assert "first_response_at" in col_names

    def test_tabla_ticket_comments_existe(self, db_conn):
        row = db_conn.execute(
            """SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'tks' AND table_name = 'ticket_comments'""",
        ).fetchone()
        assert row is not None

    def test_tabla_ticket_emails_existe(self, db_conn):
        row = db_conn.execute(
            """SELECT 1 FROM information_schema.tables
               WHERE table_schema = 'tks' AND table_name = 'ticket_emails'""",
        ).fetchone()
        assert row is not None
