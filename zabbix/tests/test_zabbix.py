"""
Tests de integración para el módulo Zabbix.

Ejecutar:
    pytest zabbix/tests/ -v
"""
import pytest


def test_health_retorna_ok(db_conn):
    """El endpoint /health debe retornar status ok."""
    # TODO
    pass


def test_proxy_zabbix_requiere_auth(db_conn):
    """El proxy hacia Zabbix debe rechazar requests sin token."""
    # TODO
    pass
