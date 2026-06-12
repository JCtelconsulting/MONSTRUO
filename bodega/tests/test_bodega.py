"""
Tests de integración para el módulo bodega.

Ejecutar:
    pytest bodega/tests/ -v
"""
import pytest


def test_buscar_producto_por_sku(db_conn):
    """Buscar un producto existente por SKU debe retornar sus datos."""
    # TODO
    pass


def test_ajuste_stock_registra_movimiento(db_conn):
    """Un ajuste de stock debe crear un movimiento en el kardex."""
    # TODO
    pass


def test_producto_inexistente_retorna_404(db_conn):
    """Buscar un SKU que no existe debe retornar 404."""
    # TODO
    pass
