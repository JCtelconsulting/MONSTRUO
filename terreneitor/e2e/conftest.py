"""
Fixtures compartidas para los tests E2E.

Variables de entorno que controlan la corrida:
- E2E_BASE_URL          URL contra la que correr los tests (default: http://localhost:8005)
- E2E_LOGIN_EMAIL       Email del usuario de prueba (default: e2e@test.local)
- E2E_LOGIN_PASSWORD    Password del usuario de prueba (default: e2e1234)

En CI, antes de correr los tests se crea el usuario via /api/auth/login fallido
y luego se hace seed via DB directa o un endpoint admin (no-op si ya existe).
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8005").rstrip("/")
LOGIN_EMAIL = os.environ.get("E2E_LOGIN_EMAIL", "juan.lopez@telconsulting.cl")
LOGIN_PASSWORD = os.environ.get("E2E_LOGIN_PASSWORD", "1234")


@pytest.fixture(scope="session")
def base_url() -> str:
    """URL base contra la que apuntan los tests."""
    return BASE_URL


@pytest.fixture(scope="session")
def auth_cookies() -> dict:
    """Hace login una vez por sesion y devuelve las cookies para reusar."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=10,
    )
    if resp.status_code != 200:
        pytest.skip(
            f"Login E2E fallo ({resp.status_code}): {resp.text}. "
            f"Verifica E2E_LOGIN_EMAIL/PASSWORD."
        )
    return resp.cookies.get_dict()


@pytest.fixture
def page_logged_in(page, base_url, auth_cookies):
    """Una page de Playwright con la cookie ya seteada."""
    cookies_for_browser = [
        {
            "name": k,
            "value": v,
            "url": base_url,
        }
        for k, v in auth_cookies.items()
    ]
    page.context.add_cookies(cookies_for_browser)
    return page


@pytest.fixture
def network_errors(page):
    """Captura errores HTTP (>=400) durante el test para verificar al final."""
    errors = []

    def on_response(response):
        if response.status >= 400 and "/api/" in response.url:
            errors.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "method": response.request.method,
                }
            )

    page.on("response", on_response)
    return errors
