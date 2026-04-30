"""
Tests de integración para el módulo ERP.

Ejecutar:
    pytest erp/tests/ -v
"""
import pytest


def test_list_facturas_requiere_auth(db_conn):
    """El endpoint de facturas debe rechazar requests sin token."""
    # TODO
    pass


def test_crear_borrador_factura(db_conn):
    """Crear un borrador de factura debe retornar id y estado DRAFT."""
    # TODO
    pass


def test_indicadores_financieros_retorna_estructura(db_conn):
    """El endpoint de indicadores debe retornar las claves esperadas."""
    # TODO
    pass
