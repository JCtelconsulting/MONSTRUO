"""
Tests de integración para el endpoint de solicitudes GTA.
Requieren DB dev activa — nunca correr contra prod.

Ejecutar:
    pytest gta/tests/ -v
"""
import pytest


def test_list_solicitudes_requiere_auth(db_conn):
    """El endpoint /api/gta/solicitudes debe rechazar requests sin token."""
    # TODO: implementar con httpx TestClient cuando el backend esté completo
    pass


def test_crear_solicitud_con_proceso_valido(db_conn):
    """Crear una solicitud con proceso existente debe retornar id."""
    # TODO: insertar proceso de prueba, crear solicitud, verificar id
    pass


def test_crear_solicitud_proceso_inexistente(db_conn):
    """Crear solicitud con proceso_id inválido debe retornar 404."""
    # TODO
    pass


def test_quiebre_se_crea_al_bloquear_paso(db_conn):
    """Bloquear un paso debe generar automáticamente un quiebre."""
    # TODO
    pass
