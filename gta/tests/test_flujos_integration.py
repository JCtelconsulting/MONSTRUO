"""
Tests de integración de GTA — contra DB dev real (Postgres).

Cubren: crear flujo desde catálogo, confirmación dual (ejecutor → validador),
pedir/responder ayuda con pausa de SLA, encadenamiento de tareas con
dependencias.

Requieren docker-compose corriendo en DEV con la DB `monstruo_dev`. NUNCA
correr contra prod. Usan rollback al final, no persisten datos.

Ejecutar:
    pytest gta/tests/test_flujos_integration.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _asegurar_usuario(conn, username: str) -> None:
    """Crea el usuario en auth.users si no existe. crear_flujo resuelve el actor
    como FK a auth.users, así que los actores del test ('test_user', 'initiator')
    deben existir."""
    conn.execute(
        """INSERT INTO auth.users (username, password_hash, role, is_active, created_at)
           VALUES (?, 'x', 'ops', 1, CURRENT_TIMESTAMP)
           ON CONFLICT (username) DO NOTHING""",
        (username,),
    )


def _asegurar_subarea(conn, area_code: str, code: str = "general") -> None:
    """Asegura una subárea activa para el área. crear_flujo resuelve cada paso
    (area_code) a una subárea activa; si el área no tiene ninguna, salta el paso."""
    conn.execute(
        """INSERT INTO gta.subareas (area_code, code, label, activo, orden, created_at, updated_at)
           VALUES (?, ?, ?, TRUE, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
           ON CONFLICT (area_code, code) DO UPDATE SET activo = TRUE""",
        (area_code, code, code.title()),
    )


def _crear_proceso_test(conn, nombre="Test proceso integración") -> int:
    """Inserta un proceso de prueba con 3 pasos cross-área. Devuelve id."""
    # Actores que usan los tests (FK a auth.users).
    for _u in ("test_user", "initiator"):
        _asegurar_usuario(conn, _u)
    # Las áreas del proceso de prueba necesitan una subárea activa para resolver.
    for _a in ("comercial", "sistemas", "contabilidad"):
        _asegurar_subarea(conn, _a)
    pasos = [
        {"orden": 1, "titulo": "Comercial valida", "area_code": "comercial",
         "sla_horas": 4, "depende_de": []},
        {"orden": 2, "titulo": "Sistemas instala", "area_code": "sistemas",
         "sla_horas": 8, "depende_de": [1]},
        {"orden": 3, "titulo": "Contabilidad registra", "area_code": "contabilidad",
         "sla_horas": 4, "depende_de": [2]},
    ]
    row = conn.execute(
        """INSERT INTO gta.procesos
           (nombre, area, descripcion, sla_horas, pasos_definicion, estado, creado_por, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'activo', 'test_user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
           RETURNING id""",
        (nombre, "comercial", "Proceso de prueba", 16, json.dumps(pasos)),
    ).fetchone()
    conn.commit()
    return int(row["id"])


@pytest.mark.integration
class TestFlujoCreacionYActivacion:
    """Crear un flujo dispara la activación de tareas sin dependencias."""

    def test_crear_flujo_desde_proceso_activa_tarea_sin_deps(self, db_conn):
        from gta.backend.services import flujos
        proceso_id = _crear_proceso_test(db_conn)

        result = flujos.crear_flujo(
            iniciado_por="test_user",
            titulo="Flujo de prueba",
            proceso_id=proceso_id,
        )

        # 3 pasos del proceso → 3 tareas materializadas, ninguno saltado por falta de
        # subárea resoluble (las 3 áreas tienen subárea activa). crear_flujo usa su propia
        # conexión y commitea, así que verificamos su retorno (no el db_conn del test, que
        # está en otra transacción y no vería las filas nuevas).
        assert result["flujo_id"]
        assert len(result["tareas_ids"]) == 3
        assert result["pasos_skipeados"] == []


# El sistema viejo de confirmación dual (ejecutor/validador) y de ayudas inter-área con
# pausa de SLA fue REMOVIDO (ver gta/backend/services/flujos.py: "Las funciones del sistema
# viejo (validar_tarea, pedir_ayuda, etc.) ya no aplican y fueron removidas"). El modelo
# actual es unificado (tomar/cerrar/devolver tarea). Estos tests quedan en skip hasta
# reescribirlos contra ese modelo, como parte del desarrollo de GTA.
@pytest.mark.integration
@pytest.mark.skip(
    reason="Sistema viejo confirmación dual removido; reescribir para modelo unificado (tomar/cerrar/devolver)"
)
class TestConfirmacionDual:
    """El ejecutor marca → validador acepta o rechaza. (SISTEMA VIEJO — REMOVIDO)"""

    def test_ejecutor_completa_pasa_a_por_validar(self, db_conn):
        from gta.backend.services import flujos
        proceso_id = _crear_proceso_test(db_conn)
        flujo = flujos.crear_flujo(
            iniciado_por="initiator", titulo="t", proceso_id=proceso_id,
        )
        tarea_id = next(t["id"] for t in flujo["tareas"] if t["estado"] == "lista")

        result = flujos.marcar_ejecutor_completo(
            tarea_id=tarea_id, actor="ejecutor_user",
        )

        assert result["estado"] == "por_validar"
        assert result["ejecutor_completo_at"] is not None
        assert result["ejecutor_completo_por"] == "ejecutor_user"

    def test_validador_acepta_avanza_flujo(self, db_conn):
        from gta.backend.services import flujos
        proceso_id = _crear_proceso_test(db_conn)
        flujo = flujos.crear_flujo(
            iniciado_por="initiator", titulo="t", proceso_id=proceso_id,
        )
        tarea1_id = next(t["id"] for t in flujo["tareas"] if t["estado"] == "lista")

        flujos.marcar_ejecutor_completo(tarea_id=tarea1_id, actor="ejecutor")
        result = flujos.validar_tarea(
            tarea_id=tarea1_id, actor="initiator", aceptada=True,
        )

        assert result["estado"] == "completada"
        # La siguiente tarea debe haberse activado
        flujo_actual = flujos.get_flujo(flujo["id"])
        tarea2 = next(t for t in flujo_actual["tareas"] if t["orden"] == 2)
        assert tarea2["estado"] == "lista"

    def test_validador_rechaza_vuelve_a_en_progreso(self, db_conn):
        from gta.backend.services import flujos
        proceso_id = _crear_proceso_test(db_conn)
        flujo = flujos.crear_flujo(
            iniciado_por="initiator", titulo="t", proceso_id=proceso_id,
        )
        tarea_id = next(t["id"] for t in flujo["tareas"] if t["estado"] == "lista")

        flujos.marcar_ejecutor_completo(tarea_id=tarea_id, actor="ejecutor")
        result = flujos.validar_tarea(
            tarea_id=tarea_id, actor="initiator",
            aceptada=False, comentario="No cumple criterio",
        )

        assert result["estado"] == "en_progreso"


@pytest.mark.integration
@pytest.mark.skip(
    reason="Sistema viejo de ayudas inter-área con pausa SLA removido del modelo unificado"
)
class TestAyudasInterAreas:
    """Pedir ayuda pausa el SLA si bloquea_sla=True; responder lo reanuda. (SISTEMA VIEJO — REMOVIDO)"""

    def test_pedir_ayuda_con_bloqueo_pausa_sla(self, db_conn):
        from gta.backend.services import flujos
        proceso_id = _crear_proceso_test(db_conn)
        flujo = flujos.crear_flujo(
            iniciado_por="initiator", titulo="t", proceso_id=proceso_id,
        )
        tarea_id = next(t["id"] for t in flujo["tareas"] if t["estado"] == "lista")

        result = flujos.pedir_ayuda(
            tarea_id=tarea_id, pedido_por="ejecutor",
            pedido_a_area="redes",
            mensaje="Necesito IP libre",
            bloquea_sla=True,
        )

        assert result["bloquea_sla"] is True
        # Tarea ahora está pausada
        tarea_row = db_conn.execute(
            "SELECT estado, sla_pause_started_at FROM gta.flujo_tareas WHERE id = ?",
            (tarea_id,),
        ).fetchone()
        assert tarea_row["estado"] == "ayuda_pedida"
        assert tarea_row["sla_pause_started_at"] is not None

    def test_responder_ayuda_reanuda_sla(self, db_conn):
        from gta.backend.services import flujos
        proceso_id = _crear_proceso_test(db_conn)
        flujo = flujos.crear_flujo(
            iniciado_por="initiator", titulo="t", proceso_id=proceso_id,
        )
        tarea_id = next(t["id"] for t in flujo["tareas"] if t["estado"] == "lista")
        ayuda = flujos.pedir_ayuda(
            tarea_id=tarea_id, pedido_por="ejecutor",
            pedido_a_area="redes", mensaje="...", bloquea_sla=True,
        )

        flujos.responder_ayuda(
            ayuda_id=ayuda["ayuda_id"], respondido_por="redes_user",
            respuesta="IP 10.0.0.5",
        )

        tarea_row = db_conn.execute(
            "SELECT estado, sla_pause_started_at, sla_paused_minutes "
            "FROM gta.flujo_tareas WHERE id = ?",
            (tarea_id,),
        ).fetchone()
        assert tarea_row["estado"] == "en_progreso"
        assert tarea_row["sla_pause_started_at"] is None
        # Se acumuló algo de tiempo pausado (al menos 0, dependiendo de timing)
        assert tarea_row["sla_paused_minutes"] >= 0


@pytest.mark.integration
class TestQuiebres:
    """Reportar y resolver quiebres."""

    def test_reportar_quiebre_lo_crea_abierto(self, db_conn):
        from gta.backend.services import procesos
        proceso_id = _crear_proceso_test(db_conn)

        result = procesos.reportar_quiebre(
            proceso_id=proceso_id,
            descripcion="Paso bloqueado por proveedor externo",
            area="comercial",
            reportado_por="test_user",
            tipo="paso_bloqueado",
        )

        assert result["id"] is not None
        # Verificar en DB
        row = db_conn.execute(
            "SELECT estado FROM gta.quiebres WHERE id = ?", (result["id"],),
        ).fetchone()
        assert row["estado"] == "abierto"
