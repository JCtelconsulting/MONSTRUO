#!/usr/bin/env python3
"""
Prueba de navegador (Playwright) para el entorno DEV de Terreneitor.

Replica las pruebas de UI que curl no puede hacer: detecta loops de
redireccion, errores de consola, peticiones fallidas, y verifica que el portal
cargue con datos. Pensado para correr en la imagen oficial de Playwright via
Docker (ver ops/scripts/qa/correr_pruebas_navegador.sh).

Uso:
    BASE_URL=https://portal.telconsulting.cl/dev \
    QA_EMAIL=qa.dev@telconsulting.cl QA_PASS='QaDev2026!' \
    python e2e/test_dev_navegador.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "https://portal.telconsulting.cl/dev").rstrip("/")
EMAIL = os.environ.get("QA_EMAIL", "qa.dev@telconsulting.cl")
PASS = os.environ.get("QA_PASS", "QaDev2026!")
LOGIN_URL = "https://terreno.telconsulting.cl/dev/"
OUT = os.environ.get("SHOT_DIR", "/work/shots")

errores = []  # mensajes de consola tipo error
fallos_red = []  # peticiones que fallaron
navegaciones = []  # urls visitadas (para detectar loop)


def run():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        page.on(
            "console", lambda m: errores.append(m.text) if m.type == "error" else None
        )
        page.on("pageerror", lambda e: errores.append(f"PAGEERROR: {e}"))
        page.on(
            "requestfailed",
            lambda r: fallos_red.append(f"{r.method} {r.url} :: {r.failure}"),
        )
        page.on(
            "framenavigated",
            lambda f: navegaciones.append(f.url) if f == page.main_frame else None,
        )

        # 1) Login
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        page.fill("#email", EMAIL)
        page.fill("#password", PASS)
        page.click("#btnLogin")
        page.wait_for_timeout(4000)  # dar tiempo a redireccion + carga de datos

        url_final = page.url
        page.wait_for_timeout(3000)  # ventana para detectar si sigue rebotando
        url_final_2 = page.url

        page.screenshot(path=f"{OUT}/dev_portal.png", full_page=True)

        # 2) Detectar loop: muchas navegaciones repetidas entre login y portal
        from collections import Counter

        c = Counter(navegaciones)
        repetidas = {u: n for u, n in c.items() if n >= 3}

        # 3) Hay sesion? buscar algo del portal (sidebar/secciones) y datos
        tiene_portal = (
            page.locator("#btnLogout, .side-link, [data-section]").count() > 0
        )
        # contar secciones VISIBLES (no debe estar todo apilado)
        secciones_visibles = page.evaluate(
            "() => Array.from(document.querySelectorAll('.section-block')).filter(s => !s.hidden && s.offsetParent !== null).length"
        )

        browser.close()

    # --- Reporte ---
    print("=" * 60)
    print(f"URL tras login:      {url_final}")
    print(f"URL 3s despues:      {url_final_2}")
    print(f"En /dev/ (no prod):  {'/dev' in url_final}")
    print(f"Llego al portal:     {tiene_portal}")
    print(f"Secciones visibles:  {secciones_visibles} (esperado: 1)")
    print(f"Loop de redireccion: {'SI -> ' + str(repetidas) if repetidas else 'NO'}")
    print(f"Errores consola:     {len(errores)}")
    for e in errores[:8]:
        print(f"   - {e[:120]}")
    print(f"Peticiones fallidas: {len(fallos_red)}")
    for f in fallos_red[:8]:
        print(f"   - {f[:120]}")
    print(f"Screenshot:          {OUT}/dev_portal.png")
    print("=" * 60)

    # Veredicto
    ok = (
        "/dev" in url_final
        and tiene_portal
        and not repetidas
        and secciones_visibles <= 1
    )
    print("RESULTADO:", "OK ✅" if ok else "FALLO ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    run()
