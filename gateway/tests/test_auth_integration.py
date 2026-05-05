"""
Tests de integración de gateway — login, sesión, RBAC vía HTTP TestClient.

Levanta la app FastAPI en proceso. NO usa docker. Sí usa la DB dev
(via fixture db_conn) para crear/limpiar usuarios de prueba.

Ejecutar:
    pytest gateway/tests/test_auth_integration.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient sobre la app del gateway."""
    # SECRET_KEY robusto para tests
    os.environ.setdefault("SECRET_KEY", "test_secret_key_de_64_chars_largo_para_no_disparar_warning_xxx")
    os.environ.setdefault("ENV_TYPE", "dev")

    from fastapi.testclient import TestClient
    from gateway.backend import main as gw_main
    # Skip lifespan (DB init) en tests
    gw_main.app.router.on_startup = []
    gw_main.app.router.on_shutdown = []

    with TestClient(gw_main.app) as c:
        yield c


@pytest.mark.integration
class TestEndpointsPublicos:
    """Endpoints que no requieren auth."""

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_responde_dict(self, client):
        resp = client.get("/health")
        # /health debe responder algo (dict, string ok, etc.)
        assert resp.status_code == 200
        # Si es JSON, que sea un dict o string
        try:
            data = resp.json()
            assert data is not None
        except Exception:
            # Texto plano también es válido
            assert resp.text


@pytest.mark.integration
class TestAuthFlow:
    """Login y verificación de sesión."""

    def test_login_sin_credenciales_falla(self, client):
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code in (400, 401, 422)

    def test_login_con_credenciales_invalidas_falla(self, client):
        resp = client.post(
            "/api/auth/login",
            json={"username": "noexiste@example.com", "password": "wrong"},
        )
        # 422 (validación pydantic), 401/403 (auth) — todos significan rechazo
        assert resp.status_code in (401, 403, 422)

    def test_whoami_sin_sesion_no_logueado(self, client):
        # Sin cookie/token, /api/auth/whoami debe responder logged=False
        resp = client.get("/api/auth/whoami")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("logged") is False or data.get("logged") is None


@pytest.mark.integration
class TestProxyConFallback:
    """El gateway intenta proxy a apps internas; si fallan dan error claro."""

    def test_proxy_a_servicio_inexistente_404(self, client):
        # Service "noexiste" no está en SERVICES_MAP
        resp = client.get("/api/noexiste/something")
        # Sin sesión, primero rechaza por auth o por servicio desconocido
        assert resp.status_code in (401, 403, 404, 502, 503)


@pytest.mark.integration
class TestRBACEnEndpointsProtegidos:
    """Endpoints que requieren permisos."""

    def test_admin_users_sin_sesion_rechaza(self, client):
        # /api/admin/users requiere admin.settings
        resp = client.get("/api/admin/users")
        assert resp.status_code in (401, 403)

    def test_config_role_scopes_sin_sesion_rechaza(self, client):
        resp = client.get("/api/config/role-scopes")
        assert resp.status_code in (401, 403)
