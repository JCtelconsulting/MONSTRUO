"""
Tests de integración para el módulo PMO.

Ejecutar:
    pytest pmo/tests/ -v
"""
import pytest


def test_health_retorna_ok(db_conn):
    """El endpoint /health debe retornar status ok."""
    # TODO
    pass


def test_list_proyectos_requiere_auth(db_conn):
    """El endpoint de proyectos debe rechazar requests sin token."""
    # TODO
    pass
