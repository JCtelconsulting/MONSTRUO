#!/usr/bin/env python3
"""Explorador EXHAUSTIVO del entorno dev: por cada modulo recorre cada
seccion/pestaña, abre cada modal/ventana posible (sin ejecutar acciones
destructivas), y registra imagenes rotas, errores de consola y peticiones
fallidas. Genera screenshots en e2e/shots/exp_* y un reporte JSON.
"""
import json
import os
import re

from playwright.sync_api import sync_playwright

OUT = os.environ.get("SHOT_DIR", "/work/e2e/shots")
LOGIN = "https://terreno.telconsulting.cl/dev/"

# Acciones destructivas / que mutan estado: NO se clickean (texto/clase/icono).
PELIGRO = [
    "elimin",
    "borr",
    "delete",
    "quitar",
    "logout",
    "salir",
    "cerrar sesion",
    "cerrar sesión",
    "rechaz",
    "validar",
    "confirm",
    "guardar",
    "aprob",
    "generar",
    "reasign",
    "reinic",
    "archiv",
    "pausar",
    "despausar",
    "toggle",
    "crear plan",
    "enviar",
    "confirmar y crear",
]
ICONOS_PELIGRO = [
    "fa-trash",
    "fa-times",
    "fa-sign-out",
    "fa-ban",
    "fa-xmark",
    "fa-check",
    "fa-pause",
    "fa-play",
    "fa-toggle",
    "fa-lock",
    "fa-unlock",
    "fa-archive",
    "fa-box-archive",
    "fa-paper-plane",
    "fa-save",
    "fa-floppy",
    "fa-rotate",
    "fa-arrows-rotate",
    "fa-undo",
]

MODULOS = [
    {
        "n": "portal",
        "email": "qa.dev@telconsulting.cl",
        "pass": "QaDev2026!",
        "url": "https://portal.telconsulting.cl/dev/",
        "navsel": ".side-link[data-section]",
        "attr": "data-section",
        "secs": [
            "section-general",
            "section-admin",
            "section-users",
            "section-projects",
            "section-system",
            "section-demo",
        ],
    },
    {
        "n": "supervisor",
        "email": "qa.supervisor@telconsulting.cl",
        "pass": "QaSup2026!",
        "url": "https://supervisor.telconsulting.cl/dev/",
        "navsel": ".tab-link[data-tab]",
        "attr": "data-tab",
        "secs": [
            "tab-planificar",
            "tab-activos",
            "tab-validar",
            "tab-listos",
            "tab-reportes",
        ],
    },
    {
        "n": "gerencia",
        "email": "qa.gerencia@telconsulting.cl",
        "pass": "QaGer2026!",
        "url": "https://gerencial.telconsulting.cl/dev/",
        "navsel": ".side-link[data-target]",
        "attr": "data-target",
        "secs": [
            "section-intro",
            "section-kpis",
            "section-salud",
            "section-ritmo",
            "section-mapa",
            "section-evidencia",
            "section-historial",
        ],
    },
    {
        "n": "terreno",
        "email": "qa.terreno@telconsulting.cl",
        "pass": "QaTerr2026!",
        "url": "https://terreneitor.telconsulting.cl/dev/",
        "navsel": ".tab-link[data-tab]",
        "attr": "data-tab",
        "secs": ["tab-pendientes", "tab-curso", "tab-extras"],
    },
]

JS_BROKEN = """() => Array.from(document.querySelectorAll('img'))
  .filter(i => i.complete && i.naturalWidth === 0 && i.src && !i.src.startsWith('data:'))
  .map(i => i.src.split('telconsulting.cl').pop())"""

JS_MODAL_OPEN = """() => {
  const els = Array.from(document.querySelectorAll('.modal-backdrop, .modal-overlay, [id^="modal"], [id$="modal"], #lightbox-modal'));
  return els.some(e => { const s = getComputedStyle(e); return s.display !== 'none' && s.visibility !== 'hidden' && e.offsetParent !== null; });
}"""


def explorar(p, mod):
    rep = {
        "modulo": mod["n"],
        "broken": {},
        "errores": [],
        "fallos": [],
        "modales": [],
        "botones_probados": 0,
    }
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 950}
    )
    pg = ctx.new_page()
    sec = {"v": "login"}
    pg.on(
        "console",
        lambda m: (
            rep["errores"].append(f"[{sec['v']}] {m.text[:140]}")
            if m.type == "error"
            else None
        ),
    )
    pg.on(
        "pageerror",
        lambda e: rep["errores"].append(f"[{sec['v']}] PAGEERROR {str(e)[:140]}"),
    )
    pg.on(
        "requestfailed",
        lambda r: (
            rep["fallos"].append(
                f"[{sec['v']}] {r.url.split('/')[-1][:40]} {r.failure}"
            )
            if "woff" not in r.url
            else None
        ),
    )

    pg.goto(LOGIN, wait_until="networkidle", timeout=30000)
    pg.fill("#email", mod["email"])
    pg.fill("#password", mod["pass"])
    pg.click("#btnLogin")
    pg.wait_for_timeout(3500)
    pg.goto(mod["url"], wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    rep["url_final"] = pg.url
    vistos = set()

    def cerrar_modal():
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(250)
        try:
            cb = pg.locator(".modal-close-btn:visible")
            if cb.count():
                cb.first.click(timeout=1200)
        except Exception:
            pass
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)

    def explorar_botones(scope, s):
        try:
            botones = pg.locator(f"{scope} button:visible")
            cnt = min(botones.count(), 40)
        except Exception:
            return
        for i in range(cnt):
            try:
                btn = pg.locator(f"{scope} button:visible").nth(i)
                label = " ".join(
                    filter(
                        None,
                        [
                            btn.inner_text() or "",
                            btn.get_attribute("title") or "",
                            btn.get_attribute("aria-label") or "",
                            btn.get_attribute("id") or "",
                        ],
                    )
                ).strip()
                html = (btn.inner_html() or "").lower()
                key = (s + "|" + label + "|" + html)[:80]
                if key in vistos:
                    continue
                vistos.add(key)
                blob = label.lower() + " " + html
                if any(pal in blob for pal in PELIGRO):
                    continue
                if any(ic in html for ic in ICONOS_PELIGRO):
                    continue
                rep["botones_probados"] += 1
                btn.click(timeout=2000)
                pg.wait_for_timeout(800)
                if pg.evaluate(JS_MODAL_OPEN):
                    nm = (
                        re.sub(r"[^a-z0-9]+", "_", (label or "modal").lower())[:24]
                        or "modal"
                    )
                    pg.screenshot(path=f'{OUT}/exp_{mod["n"]}_{s}_modal_{nm}.png')
                    rep["modales"].append(f"{s}:{label[:30]}")
                    bk = pg.evaluate(JS_BROKEN)
                    if bk:
                        rep["broken"][f"modal:{s}:{label[:24]}"] = bk
                    cerrar_modal()
            except Exception:
                pass

    for s in mod["secs"]:
        sec["v"] = s
        try:
            btn = pg.locator(f'{mod["navsel"]}[{mod["attr"]}="{s}"]')
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=4000)
                pg.wait_for_timeout(1800)
        except Exception:
            pass
        for _ in range(2):
            cols = pg.locator(".category-header.collapsed")
            for i in range(min(cols.count(), 8)):
                try:
                    pg.locator(".category-header.collapsed").first.click()
                    pg.wait_for_timeout(250)
                except Exception:
                    pass
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f'{OUT}/exp_{mod["n"]}_{s}.png', full_page=False)
        broken = pg.evaluate(JS_BROKEN)
        if broken:
            rep["broken"][s] = broken
        # abrir modales dentro de ESTA seccion
        scope = f"#{s}" if pg.locator(f"#{s}").count() else "main"
        explorar_botones(scope, s)

    b.close()
    return rep


def run():
    os.makedirs(OUT, exist_ok=True)
    allrep = []
    with sync_playwright() as p:
        for mod in MODULOS:
            r = explorar(p, mod)
            allrep.append(r)
            print("=" * 64)
            print(f"MODULO {r['modulo']}  url={r.get('url_final')}")
            print(
                f"  botones probados: {r['botones_probados']} | modales: {len(r['modales'])} -> {r['modales']}"
            )
            print(f"  IMAGENES ROTAS: {sum(len(v) for v in r['broken'].values())}")
            for k, v in r["broken"].items():
                print(f"     [{k}] {len(v)}: {v[:2]}")
            print(f"  errores consola: {len(r['errores'])}")
            for e in r["errores"][:8]:
                print(f"     - {e}")
            print(f"  fallos red: {len(r['fallos'])}")
            for f in r["fallos"][:8]:
                print(f"     - {f}")
    with open(f"{OUT}/../explorador_reporte.json", "w") as fh:
        json.dump(allrep, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    run()
