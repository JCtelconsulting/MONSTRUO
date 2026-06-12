"""
Configuración central de pytest para Terreneitor.
Define fixtures reutilizables para todos los tests.
"""

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Configurar variables de entorno para tests
os.environ["TERRENEITOR_SECRET_KEY"] = "test_secret_key_for_testing_only"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["TERRENEITOR_DISABLE_AUTOFIX"] = "1"
os.environ["TERRENEITOR_DISABLE_RATELIMIT"] = "1"
os.environ["ENV"] = "test"
os.environ["TERRENEITOR_COOKIE_SECURE"] = "0"
os.environ["TERRENEITOR_SYNC_INTERVAL"] = "0"

# Evitar rutas absolutas de producción durante tests (GitHub Actions no tiene /srv/terreneitor)
_TEST_ROOT = Path(tempfile.gettempdir()) / "terreneitor_test"
os.environ.setdefault("TERRENEITOR_DB_DIR", str(_TEST_ROOT / "db"))
os.environ.setdefault("TERRENEITOR_LOCKS_DIR", str(_TEST_ROOT / "locks"))
os.environ.setdefault("BASE_FILES_DIR", str(_TEST_ROOT / "files"))
Path(os.environ["TERRENEITOR_DB_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["TERRENEITOR_LOCKS_DIR"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["BASE_FILES_DIR"]).mkdir(parents=True, exist_ok=True)

from backend import modelos
from backend.core.cerebro import app
from backend.core.dependencias import get_db, get_db_hash


@pytest.fixture(scope="function")
def test_db():
    """
    Crea una base de datos SQLite en memoria para cada test.
    Se destruye automáticamente al finalizar el test.
    """
    # Crear engine de prueba
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Crear todas las tablas
    modelos.Base.metadata.create_all(bind=engine)

    # Crear sesión de prueba
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield TestingSessionLocal()

    # Limpiar
    modelos.Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_client(test_db):
    """
    Cliente de pruebas de FastAPI con base de datos de prueba.
    """
    return TestClient(app)


@pytest.fixture(scope="function")
def client(test_client):
    return test_client


@pytest.fixture(scope="function")
def test_user(test_db):
    """
    Crea un usuario de prueba en la base de datos.
    """
    user = modelos.User(
        email="test@terreneitor.com",
        name="Usuario de Prueba",
        role=modelos.UserRoleEnum.ADMIN,
        hashed_password=get_db_hash("password123"),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def auth_headers(test_client, test_user):
    """
    Headers de autenticación con token JWT válido.
    """
    response = test_client.post(
        "/api/auth/login",
        json={"email": "test@terreneitor.com", "password": "password123"},
    )
    assert response.status_code == 200
    return {}


@pytest.fixture(scope="function")
def temp_files_dir():
    """
    Crea un directorio temporal para archivos de prueba.
    Se limpia automáticamente al finalizar el test.
    """
    temp_dir = tempfile.mkdtemp(prefix="terreneitor_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def sample_image(temp_files_dir):
    """
    Crea una imagen de prueba válida (1x1 pixel PNG).
    """
    from PIL import Image

    img_path = temp_files_dir / "test_image.jpg"
    img = Image.new("RGB", (100, 100), color="red")
    img.save(img_path, "JPEG")
    return img_path
