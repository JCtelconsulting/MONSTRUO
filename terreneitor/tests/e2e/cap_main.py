from playwright.sync_api import sync_playwright

E = "qa.gerencia@telconsulting.cl"
P = "QaGer2026!"
OUT = "/work/tests/e2e/shots"
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
    pg.wait_for_timeout(1200)
    pg.locator("#btn-buscar-historial").first.click()
    pg.wait_for_timeout(2500)
    # quitar el limite de altura de main temporalmente para capturarlo completo
    pg.evaluate(
        "const m=document.querySelector('main'); m.style.height='auto'; m.style.overflow='visible'; document.body.style.height='auto';"
    )
    pg.wait_for_timeout(500)
    pg.locator("main").screenshot(path=f"{OUT}/gerencia_main_full.png")
    print("ok, alto main:", pg.evaluate("document.querySelector('main').scrollHeight"))
    b.close()
