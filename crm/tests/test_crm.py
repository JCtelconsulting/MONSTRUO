"""
Tests de integración para el módulo CRM.

Ejecutar:
    pytest crm/tests/ -v
"""
import pytest


def test_buscar_cliente_por_rut(db_conn):
    """Buscar un cliente existente por RUT debe retornar sus datos."""
    # TODO
    pass


def test_agregar_interaccion_a_cliente(db_conn):
    """Registrar una interacción debe asociarse al cliente correcto."""
    # TODO
    pass


def test_cliente_inexistente_retorna_404(db_conn):
    """Buscar un cliente que no existe debe retornar 404."""
    # TODO
    pass
