"""
Tests de integración para el módulo fundacion.

Ejecutar:
    pytest fundacion/tests/ -v
"""
import pytest


def test_list_planificaciones_requiere_auth(db_conn):
    """El endpoint de planificaciones debe rechazar requests sin token."""
    # TODO
    pass


def test_crear_planificacion_campos_minimos(db_conn):
    """Una planificación con campos mínimos debe crearse correctamente."""
    # TODO
    pass


def test_planificacion_actualiza_estado(db_conn):
    """Actualizar el estado de una planificación debe persistir el cambio."""
    # TODO
    pass
