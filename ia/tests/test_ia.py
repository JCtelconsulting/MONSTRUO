"""
Tests de integración para el módulo IA.

Ejecutar:
    pytest ia/tests/ -v
"""
import pytest


def test_health_retorna_ok(db_conn):
    """El endpoint /health debe retornar status ok."""
    # TODO
    pass


def test_consulta_requiere_auth(db_conn):
    """El endpoint de consultas debe rechazar requests sin token."""
    # TODO
    pass
