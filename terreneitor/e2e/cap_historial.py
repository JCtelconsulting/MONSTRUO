from playwright.sync_api import sync_playwright

E = "qa.gerencia@telconsulting.cl"
P = "QaGer2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(3500)
    pg.goto(
        "https://gerencial.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(1500)
    pg.locator('.side-link[data-target="section-historial"]').first.click()
    pg.wait_for_timeout(1500)
    pg.locator("#btn-buscar-historial").first.click()
    pg.wait_for_timeout(2500)
    # element screenshot de la seccion historial completa
    pg.locator("#section-historial").screenshot(path=f"{OUT}/hist_seccion.png")
    # tambien scrollear main al fondo y screenshot viewport (ver si la ultima fila tapa la barra inferior/sidebar)
    pg.evaluate(
        "document.querySelector('main').scrollTo(0, document.querySelector('main').scrollHeight)"
    )
    pg.wait_for_timeout(800)
    pg.screenshot(path=f"{OUT}/hist_scroll_fondo.png", full_page=False)
    print("ok")
    b.close()
