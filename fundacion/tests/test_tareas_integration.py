"""
Tests de integración de fundación — contra DB dev real.

Cubren creación de tareas y enforcement server-side del scope sede/curso.
Usa rollback al final.

Ejecutar:
    pytest fundacion/tests/test_tareas_integration.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _crear_tarea_test(conn, sede="metropolitana", curso="prekinder-kinder", titulo="Tarea test"):
    """Inserta una tarea fundacion directa en DB. Devuelve id.

    Nota: la columna real es `creado_by` (no `creado_por`) — typo en el schema.
    """
    now = datetime.now(timezone.utc)
    row = conn.execute(
        """INSERT INTO fundacion.fundacion_tareas
           (titulo, descripcion, fecha_inicio, sede, curso, estado, creado_by, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'pendiente', 'test_user', ?, ?)
           RETURNING id""",
        (titulo, "Test", now, sede, curso, now, now),
    ).fetchone()
    conn.commit()
    return int(row["id"])


@pytest.mark.integration
class TestTareasCreacion:
    """Crear y leer tareas básicas."""

    def test_crear_tarea_persiste(self, db_conn):
        tarea_id = _crear_tarea_test(db_conn, sede="metropolitana", curso="prekinder-kinder")
        row = db_conn.execute(
            "SELECT sede, curso, estado FROM fundacion.fundacion_tareas WHERE id = ?",
            (tarea_id,),
        ).fetchone()
        assert row["sede"] == "metropolitana"
        assert row["curso"] == "prekinder-kinder"
        assert row["estado"] == "pendiente"


@pytest.mark.integration
class TestScopeEnforcementDB:
    """El filtrado por scope realmente filtra tareas en DB.

    Usa los códigos canónicos de FUNDACION_SEDE_ALIASES en auth_service.py.
    """

    def test_solo_tareas_de_sedes_permitidas(self, db_conn):
        from fundacion.backend.router import _is_task_in_scope
        # Insertamos 2 tareas en sedes válidas distintas
        tarea_metro = _crear_tarea_test(db_conn, sede="metropolitana", curso="prekinder-kinder")
        tarea_valpo = _crear_tarea_test(db_conn, sede="valparaiso", curso="prekinder-kinder")

        scope = {"is_global": False, "sedes": ["metropolitana"], "cursos": []}

        row_metro = db_conn.execute(
            "SELECT * FROM fundacion.fundacion_tareas WHERE id = ?",
            (tarea_metro,),
        ).fetchone()
        row_valpo = db_conn.execute(
            "SELECT * FROM fundacion.fundacion_tareas WHERE id = ?",
            (tarea_valpo,),
        ).fetchone()

        assert _is_task_in_scope(scope, dict(row_metro)) is True
        assert _is_task_in_scope(scope, dict(row_valpo)) is False
