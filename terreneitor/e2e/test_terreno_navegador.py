#!/usr/bin/env python3
"""Prueba de navegador del modulo TERRENO (rol terreno): recorre las pestañas e
intenta ENTRAR a una tarea, capturando errores de consola/red y si la pagina
"vuelve atras" (redirige a login/portal)."""
import os
import sys

from playwright.sync_api import sync_playwright

EMAIL = os.environ.get("QA_EMAIL", "qa.terreno@telconsulting.cl")
PASS = os.environ.get("QA_PASS", "QaTerr2026!")
LOGIN_URL = "https://terreno.telconsulting.cl/dev/"
TERRENO_URL = "https://terreneitor.telconsulting.cl/dev/"
OUT = os.environ.get("SHOT_DIR", "/work/e2e/shots")

errores = []
fallos = []
navs = []


def run():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(ignore_https_errors=True)
        pg = ctx.new_page()
        pg.on(
            "console", lambda m: errores.append(m.text) if m.type == "error" else None
        )
        pg.on("pageerror", lambda e: errores.append(f"PAGEERROR: {e}"))
        pg.on(
            "requestfailed",
            lambda r: fallos.append(f"{r.method} {r.url} :: {r.failure}"),
        )
        pg.on(
            "framenavigated",
            lambda f: navs.append(f.url) if f == pg.main_frame else None,
        )

        # login
        pg.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
        pg.fill("#email", EMAIL)
        pg.fill("#password", PASS)
        pg.click("#btnLogin")
        pg.wait_for_timeout(4000)
        # ir a terreno
        pg.goto(TERRENO_URL, wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(3000)
        print("URL terreno:", pg.url)
        print(
            "Rebotó a login/portal:", "reason=expired" in pg.url or "portal" in pg.url
        )
        pg.screenshot(path=f"{OUT}/terreno_home.png", full_page=True)

        # recorrer pestañas
        tabs = pg.locator(".tab-link")
        print("Pestañas encontradas:", tabs.count())
        for i in range(tabs.count()):
            t = tabs.nth(i)
            label = t.get_attribute("data-tab") or f"tab{i}"
            t.click()
            pg.wait_for_timeout(1500)
            pg.screenshot(path=f"{OUT}/terreno_{label}.png", full_page=True)
            print(f"  click {label}: errores acumulados={len(errores)}")

        # intentar ENTRAR a una tarea: recorrer pestañas hasta hallar un boton
        # de tarea VISIBLE (subir evidencia / ver) y clickearlo.
        url_antes = pg.url
        accion = "ninguna (sin tareas visibles)"
        modal_visible = False
        errores_antes = len(errores)
        for label in ["tab-pendientes", "tab-curso", "tab-extras"]:
            try:
                pg.locator(f'.tab-link[data-tab="{label}"]').click(timeout=4000)
            except Exception:
                pass
            pg.wait_for_timeout(1200)
            # botones de tarea visibles (excluye 'CREAR TAREA')
            cand = pg.locator(
                ".btn-upload, .task-card, .btn-ver, button:has-text('evidencia'), button:has-text('Ver')"
            )
            visibles = [
                cand.nth(i)
                for i in range(cand.count())
                if cand.nth(i).is_visible()
                and "CREAR" not in (cand.nth(i).inner_text() or "").upper()
            ]
            if visibles:
                visibles[0].click()
                pg.wait_for_timeout(2500)
                accion = f"click tarea en {label}"
                modal = pg.locator("#upload-modal, .modal-backdrop, [class*=modal]")
                modal_visible = any(
                    modal.nth(i).is_visible() for i in range(modal.count())
                )
                pg.screenshot(path=f"{OUT}/terreno_entrar_tarea.png", full_page=True)
                break

        url_despues = pg.url
        rebote = url_antes != url_despues or "reason=expired" in url_despues
        print(f"Acción: {accion}")
        print(f"Modal/detalle abierto: {modal_visible}")
        print(f"URL antes/después: {url_antes}  ->  {url_despues}")
        print(f"Volvió atrás (rebote): {rebote}")
        print(f"Errores nuevos al entrar: {len(errores) - errores_antes}")

        b.close()
        veredicto = (not rebote) and (len(errores) == 0)

    print("=" * 60)
    print(f"Acción de entrada: {accion}")
    print(f"Errores de consola/página: {len(errores)}")
    for e in errores[:12]:
        print(f"   - {e[:160]}")
    print(f"Peticiones fallidas: {len(fallos)}")
    for f in fallos[:12]:
        print(f"   - {f[:160]}")
    print("=" * 60)
    print("RESULTADO TERRENO:", "OK ✅" if veredicto else "FALLO ❌")
    sys.exit(0 if veredicto else 1)


if __name__ == "__main__":
    run()
