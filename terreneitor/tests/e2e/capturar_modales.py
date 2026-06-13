#!/usr/bin/env python3
"""Captura dirigida de las ventanas/modales clave de cada modulo, con datos
reales. Screenshots en e2e/shots/modal_*. Reporta imagenes rotas dentro de cada
modal y errores de consola."""
import os

from playwright.sync_api import sync_playwright

OUT = os.environ.get("SHOT_DIR", "/work/tests/e2e/shots")
LOGIN = "https://terreno.telconsulting.cl/dev/"
JS_BROKEN = """() => Array.from(document.querySelectorAll('img')).filter(i=>i.complete&&i.naturalWidth===0&&i.src&&!i.src.startsWith('data:')&&i.offsetParent!==null).map(i=>i.src.split('telconsulting.cl').pop())"""
errores = []


def login(pg, email, pwd, url):
    try:
        pg.context.clear_cookies()
    except Exception:
        pass
    pg.goto(LOGIN, wait_until="networkidle", timeout=30000)
    pg.fill("#email", email)
    pg.fill("#password", pwd)
    pg.click("#btnLogin")
    pg.wait_for_timeout(3500)
    pg.goto(url, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2000)


def shot_modal(pg, nombre):
    pg.wait_for_timeout(900)
    vis = pg.evaluate(
        """() => { const m=[...document.querySelectorAll('.modal-backdrop,.modal-overlay,[id^=modal],#lightbox-modal,#modal-structure-editor')].find(e=>{const s=getComputedStyle(e);return s.display!=='none'&&e.offsetParent!==null}); return m? m.id||m.className : null; }"""
    )
    pg.screenshot(path=f"{OUT}/modal_{nombre}.png")
    bk = pg.evaluate(JS_BROKEN)
    print(f"  modal {nombre}: visible={vis} rotas={len(bk)} {bk[:2]}")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(250)
    for sel in [
        ".modal-close-btn:visible",
        "button:has-text('Cerrar'):visible",
        ".modal-overlay:visible",
    ]:
        try:
            el = pg.locator(sel)
            if el.count():
                el.first.click(timeout=1000)
                break
        except Exception:
            pass
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(400)


def click_try(pg, selectors):
    for sel in selectors:
        try:
            el = pg.locator(sel)
            if el.count() and el.first.is_visible():
                el.first.click(timeout=2500)
                return True
        except Exception:
            pass
    return False


def run():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(
            ignore_https_errors=True, viewport={"width": 1440, "height": 950}
        )
        pg = ctx.new_page()
        pg.on(
            "console",
            lambda m: errores.append(m.text[:140]) if m.type == "error" else None,
        )

        # ---------- PORTAL ----------
        print("PORTAL")
        login(
            pg,
            "qa.dev@telconsulting.cl",
            "QaDev2026!",
            "https://portal.telconsulting.cl/dev/",
        )
        pg.locator('.side-link[data-section="section-users"]').first.click()
        pg.wait_for_timeout(1500)
        if click_try(pg, ['button:has-text("Nuevo Usuario")']):
            shot_modal(pg, "portal_nuevo_usuario")
        if click_try(pg, ['button[title="Editar Email"]']):
            shot_modal(pg, "portal_editar_email")
        if click_try(pg, ['button[title="Cambiar Clave"]']):
            shot_modal(pg, "portal_reset_clave")
        pg.locator('.side-link[data-section="section-projects"]').first.click()
        pg.wait_for_timeout(1500)
        if click_try(pg, ['button:has-text("Nuevo Proyecto")']):
            shot_modal(pg, "portal_nuevo_proyecto")
        if click_try(pg, ['button[title="Estructura"]']):
            shot_modal(pg, "portal_estructura")
        # cambiar clave (sidebar)
        if click_try(
            pg,
            [
                'button:has-text("Clave"):visible',
                "#btn-change-pass",
                '[onclick*="hange"]',
            ],
        ):
            shot_modal(pg, "portal_cambiar_clave")

        # ---------- TERRENO ----------
        print("TERRENO")
        login(
            pg,
            "qa.terreno@telconsulting.cl",
            "QaTerr2026!",
            "https://terreneitor.telconsulting.cl/dev/",
        )
        # expandir y abrir upload
        for _ in range(3):
            cols = pg.locator(".category-header.collapsed, .plan-header.collapsed")
            if not cols.count():
                break
            try:
                cols.first.click()
                pg.wait_for_timeout(300)
            except Exception:
                break
        if click_try(
            pg,
            [
                'button:has-text("Subir evidencia")',
                'button:has-text("SUBIR EVIDENCIA")',
                '.btn-upload:has-text("evidencia")',
                'button:has-text("AGREGAR MAS FOTOS")',
            ],
        ):
            shot_modal(pg, "terreno_upload")

        # ---------- SUPERVISOR ----------
        print("SUPERVISOR")
        login(
            pg,
            "qa.supervisor@telconsulting.cl",
            "QaSup2026!",
            "https://supervisor.telconsulting.cl/dev/",
        )
        # tab validar -> lightbox (click una miniatura)
        click_try(pg, ['.tab-link[data-tab="tab-validar"]'])
        pg.wait_for_timeout(1800)
        for _ in range(4):
            cols = pg.locator(".category-header.collapsed")
            if not cols.count():
                break
            try:
                cols.first.click()
                pg.wait_for_timeout(300)
            except Exception:
                break
        if click_try(pg, [".file-thumb", "img.file-thumb", "#tab-validar img"]):
            shot_modal(pg, "supervisor_lightbox")
        # tab activos -> add items
        click_try(pg, ['.tab-link[data-tab="tab-activos"]'])
        pg.wait_for_timeout(1500)
        if click_try(
            pg,
            [
                'button:has-text("AGREGAR")',
                'button[title*="Agregar"]',
                'button:has-text("Items")',
            ],
        ):
            shot_modal(pg, "supervisor_add_items")

        b.close()
    print("\nERRORES CONSOLA:", len(errores))
    for e in errores[:15]:
        print("  -", e)


if __name__ == "__main__":
    run()
