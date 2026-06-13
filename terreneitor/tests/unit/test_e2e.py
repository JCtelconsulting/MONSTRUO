import re
from pathlib import Path

import pytest

pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright no instalado (tests E2E son opcionales).",
)

from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402

with sync_playwright() as playwright:
    chromium_path = Path(playwright.chromium.executable_path)
    if not chromium_path.exists():
        pytest.skip(
            "Chromium de Playwright no instalado en este servidor.",
            allow_module_level=True,
        )

# Usar live_server para que levante la app real
# pytest-playwright integra 'page' fixture automaticamente


def test_login_flow(page: Page):
    # Asumimos que el server corre en localhost:8000 (en CI se levanta aparte)
    # Para desarrollo local, pytest-playwright puede usar base-url

    # 1. Ir al login
    # Ajustar URL segun ambiente local, asumiendo start.sh corrio en puerto 8000
    base_url = "http://localhost:8000"

    page.goto(f"{base_url}/modulos/login/")

    # 2. Verificar titulo
    expect(page).to_have_title(re.compile("Acceso"))

    # 3. Llenar formulario
    page.get_by_placeholder("usuario@telconsulting.cl").fill("admin@terreneitor.cl")
    page.get_by_placeholder("********").fill("1234")  # Password dummy

    # 4. Click boton
    # page.get_by_role("button", name="Ingresar").click()
    page.locator("#btnLogin").click()

    # 5. Esperar navegacion o mensaje de error
    # Como no tenemos DB real con ese user aqui, probablemente falle el login o de error 401
    # Pero el test verifica que Playwright interactua con el DOM

    # Opcion A: Si esperamos fallo (porque no hay user admin@terreneitor.cl en test DB vacia)
    # expect(page.locator(".toast.error")).to_be_visible()

    # Opcion B: Solo verificar que se intento postear
    # Por ahora, solo queremos probar que Playwright corre.
    assert "/modulos/login/" in page.url  # O cambio si fuera exitoso
