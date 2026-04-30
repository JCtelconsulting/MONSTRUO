"""
Tests de integración para el módulo de ticketera.

Ejecutar:
    pytest ticketera/tests/ -v
"""
import pytest


def test_crear_ticket_campos_minimos(db_conn):
    """Un ticket con campos mínimos debe crearse correctamente."""
    # TODO
    pass


def test_sla_se_calcula_al_crear_ticket(db_conn):
    """Al crear un ticket debe calcularse la fecha de vencimiento SLA."""
    # TODO
    pass


def test_ticket_cerrado_no_acepta_comentarios(db_conn):
    """Un ticket en estado cerrado no debe aceptar nuevos comentarios."""
    # TODO
    pass
