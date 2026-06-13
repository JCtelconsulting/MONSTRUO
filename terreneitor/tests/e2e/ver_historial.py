from playwright.sync_api import sync_playwright

E = "qa.gerencia@telconsulting.cl"
P = "QaGer2026!"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1366, "height": 900}
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
    pg.wait_for_timeout(2000)
    # ir a la seccion historial
    pg.locator('.side-link[data-target="section-historial"]').first.click()
    pg.wait_for_timeout(2500)
    # buscar para cargar el historial
    try:
        pg.locator(
            "#section-historial button:has-text('BUSCAR'), #section-historial .btn-principal"
        ).first.click(timeout=4000)
        pg.wait_for_timeout(2000)
    except Exception as e:
        print("no buscar btn:", e)
    # contar filas
    rows = pg.locator("#tabla-historial tbody tr, #section-historial table tr").count()
    print("filas visibles en tabla historial:", rows)
    pg.screenshot(path=f"{OUT}/hist_full.png", full_page=True)
    # screenshot del viewport (no full) para ver si se sale por encima
    pg.screenshot(path=f"{OUT}/hist_viewport.png", full_page=False)
    b.close()
