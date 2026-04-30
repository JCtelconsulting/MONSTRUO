"""
Fixtures compartidas para los tests de este módulo.
Importar desde aquí en todos los test_*.py del módulo.
"""
import pytest


@pytest.fixture
def db_conn():
    """Conexión de test a la DB (usa la misma DB dev — nunca prod)."""
    from plataforma.core import db
    conn = db.get_conn()
    yield conn
    conn.rollback()
    conn.close()
