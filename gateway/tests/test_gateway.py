"""
Tests de integración para el módulo gateway.

Ejecutar:
    pytest gateway/tests/ -v
"""
import pytest


def test_login_requiere_credenciales(db_conn):
    """El endpoint /auth/login debe rechazar requests sin credenciales."""
    # TODO
    pass


def test_sesion_invalida_retorna_401(db_conn):
    """Un token inválido debe retornar 401."""
    # TODO
    pass


def test_proxy_redirige_a_servicio_correcto(db_conn):
    """El proxy debe enrutar /api/tks/ al servicio ticketera."""
    # TODO
    pass
