"""
Fixtures de test compartidas para toda la plataforma.
Importar en conftest.py de cada módulo:

    from fundacion.core.tests.conftest import db_conn  # noqa: F401
"""
import pytest


@pytest.fixture
def db_conn():
    """Conexión de test a la DB dev. Hace rollback al terminar — nunca persiste datos."""
    from fundacion.core import db
    conn = db.get_conn()
    yield conn
    conn.rollback()
    conn.close()
