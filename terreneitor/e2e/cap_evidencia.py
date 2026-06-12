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
    pg.locator('.side-link[data-target="section-evidencia"]').first.click()
    pg.wait_for_timeout(1200)
    for tab in ["listos", "validar", "cuarentena"]:
        pg.locator(f'#evidencia-tabs button[data-evidencia="{tab}"]').click()
        pg.wait_for_timeout(2200)
        pg.locator("#section-evidencia").screenshot(path=f"{OUT}/evi_{tab}.png")
        print(tab, "capturado")
    b.close()
