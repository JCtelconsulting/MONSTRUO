from playwright.sync_api import sync_playwright

E = "qa.gerencia@telconsulting.cl"
P = "QaGer2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 1000}
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
    pg.wait_for_timeout(1000)
    for tab in ["listos", "cuarentena"]:
        pg.locator(f'#evidencia-tabs button[data-evidencia="{tab}"]').click()
        pg.wait_for_timeout(2200)
        # expandir TODOS los category-header (plan y proyecto)
        for _ in range(2):
            heads = pg.locator("#evidencia-content .category-header.collapsed")
            n = heads.count()
            for i in range(n):
                try:
                    pg.locator(
                        "#evidencia-content .category-header.collapsed"
                    ).first.click()
                    pg.wait_for_timeout(300)
                except Exception:
                    pass
        pg.wait_for_timeout(2500)  # cargar thumbnails
        pg.locator("#section-evidencia").screenshot(path=f"{OUT}/evi_{tab}_exp.png")
        print(tab, "expandido")
    b.close()
