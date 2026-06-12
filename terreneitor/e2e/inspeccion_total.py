#!/usr/bin/env python3
"""Inspección visual TOTAL del entorno dev: entra a cada módulo con su rol y
captura un screenshot de CADA sección/pestaña, registrando errores de consola y
peticiones fallidas por sección. Genera e2e/shots/<modulo>_<seccion>.png."""
import os

from playwright.sync_api import sync_playwright

OUT = os.environ.get("SHOT_DIR", "/work/e2e/shots")
LOGIN = "https://terreno.telconsulting.cl/dev/"

MODULOS = [
    {
        "nombre": "gerencia",
        "email": "qa.gerencia@telconsulting.cl",
        "pass": "QaGer2026!",
        "url": "https://gerencial.telconsulting.cl/dev/",
        "attr": "data-target",
        "selector": ".side-link[data-target]",
        "secciones": [
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
        "nombre": "supervisor",
        "email": "qa.supervisor@telconsulting.cl",
        "pass": "QaSup2026!",
        "url": "https://supervisor.telconsulting.cl/dev/",
        "attr": "data-tab",
        "selector": ".tab-link[data-tab]",
        "secciones": [
            "tab-planificar",
            "tab-activos",
            "tab-validar",
            "tab-listos",
            "tab-reportes",
        ],
    },
    {
        "nombre": "portal",
        "email": "qa.dev@telconsulting.cl",
        "pass": "QaDev2026!",
        "url": "https://portal.telconsulting.cl/dev/",
        "attr": "data-section",
        "selector": ".side-link[data-section]",
        "secciones": [
            "section-general",
            "section-admin",
            "section-users",
            "section-projects",
            "section-system",
            "section-demo",
        ],
    },
    {
        "nombre": "terreno",
        "email": "qa.terreno@telconsulting.cl",
        "pass": "QaTerr2026!",
        "url": "https://terreneitor.telconsulting.cl/dev/",
        "attr": "data-tab",
        "selector": ".tab-link[data-tab]",
        "secciones": ["tab-pendientes", "tab-curso", "tab-extras"],
    },
]


def inspeccionar(p, mod):
    res = {"modulo": mod["nombre"], "errores": [], "fallos": [], "secciones": {}}
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1366, "height": 900}
    )
    pg = ctx.new_page()
    seccion_actual = {"v": "login"}
    pg.on(
        "console",
        lambda m: (
            res["errores"].append(f"[{seccion_actual['v']}] {m.text}")
            if m.type == "error"
            else None
        ),
    )
    pg.on(
        "pageerror",
        lambda e: res["errores"].append(f"[{seccion_actual['v']}] PAGEERROR {e}"),
    )
    pg.on(
        "requestfailed",
        lambda r: res["fallos"].append(
            f"[{seccion_actual['v']}] {r.url.split('/')[-1]} {r.failure}"
        ),
    )

    # login
    pg.goto(LOGIN, wait_until="networkidle", timeout=30000)
    pg.fill("#email", mod["email"])
    pg.fill("#password", mod["pass"])
    pg.click("#btnLogin")
    pg.wait_for_timeout(3500)
    # ir al modulo
    pg.goto(mod["url"], wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    res["url_final"] = pg.url
    res["rebote_login"] = (
        "terreno.telconsulting.cl" in pg.url and mod["nombre"] != "terreno"
    )

    for sec in mod["secciones"]:
        seccion_actual["v"] = sec
        try:
            btn = pg.locator(f'{mod["selector"]}[{mod["attr"]}="{sec}"]')
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=4000)
                pg.wait_for_timeout(1500)
                clicked = True
            else:
                clicked = False
        except Exception as e:
            clicked = f"err: {e}"
        pg.screenshot(path=f'{OUT}/insp_{mod["nombre"]}_{sec}.png', full_page=True)
        res["secciones"][sec] = clicked

    b.close()
    return res


def run():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        for mod in MODULOS:
            r = inspeccionar(p, mod)
            print("=" * 60)
            print(f"MÓDULO: {r['modulo']}  url={r.get('url_final')}")
            print(f"  rebote a login: {r.get('rebote_login')}")
            print(f"  secciones: {r['secciones']}")
            print(f"  errores consola ({len(r['errores'])}):")
            for e in r["errores"][:15]:
                print(f"     - {e[:150]}")
            print(f"  peticiones fallidas ({len(r['fallos'])}):")
            for f in r["fallos"][:15]:
                print(f"     - {f[:150]}")


if __name__ == "__main__":
    run()
