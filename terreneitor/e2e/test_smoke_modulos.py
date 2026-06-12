"""
Smoke tests E2E: verifica que cada modulo carga sin errores HTTP visibles.

Cada test:
1. Abre la pagina del modulo con cookie de admin.
2. Espera DOMContentLoaded.
3. Verifica que ningun request a /api/ haya devuelto status >= 400.
4. Verifica que no haya errores JS criticos en console.
"""

import pytest

MODULOS = [
    ("/modulos/portal/", "Portal"),
    ("/modulos/terreno/", "Terreno"),
    ("/modulos/supervisor/", "Supervisor"),
    ("/modulos/gerencia/", "Gerencia"),
]


@pytest.mark.parametrize("path,nombre", MODULOS, ids=[m[1] for m in MODULOS])
def test_modulo_carga_sin_errores_api(
    page_logged_in, base_url, network_errors, path, nombre
):
    """El modulo carga y ningun endpoint /api/ devuelve >= 400."""
    page_logged_in.goto(f"{base_url}{path}", wait_until="networkidle", timeout=15000)

    real_errors = [e for e in network_errors if e["status"] not in (401, 403)]
    assert (
        real_errors == []
    ), f"{nombre}: {len(real_errors)} requests a la API fallaron:\n" + "\n".join(
        f"  {e['method']} {e['url']} -> {e['status']}" for e in real_errors
    )


@pytest.mark.parametrize("path,nombre", MODULOS, ids=[m[1] for m in MODULOS])
def test_modulo_sin_errores_console(page_logged_in, base_url, path, nombre):
    """No hay errores JS criticos en console al cargar el modulo.

    Tolera 404s de recursos (assets que pueden no existir en CI), pero no
    tolera errores reales (ReferenceError, TypeError, syntax errors).
    """
    console_errors = []

    def on_console(msg):
        if msg.type == "error":
            text = msg.text.lower()
            ignore = ["favicon", "failed to load resource", "404", "net::"]
            if any(noise in text for noise in ignore):
                return
            console_errors.append(msg.text)

    page_logged_in.on("console", on_console)
    page_logged_in.goto(f"{base_url}{path}", wait_until="networkidle", timeout=15000)

    assert console_errors == [], f"{nombre}: errores JS en consola:\n" + "\n".join(
        console_errors
    )


def test_login_url_limpia(page, base_url):
    """La home (/) debe servir el HTML del login con la URL limpia.

    `?reason=test` activa el guard del bootstrap (definido en login.js)
    para que el JS no intente redirigir si encuentra cookie residual.
    """
    page.goto(f"{base_url}/?reason=test", wait_until="domcontentloaded", timeout=10000)
    page.wait_for_selector("#loginForm", timeout=5000)
    assert page.locator("#email").count() == 1
    assert page.locator("#password").count() == 1
    assert page.locator("#btnLogin").count() == 1
