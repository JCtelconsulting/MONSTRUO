from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 950}
    )
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:120]) if m.type == "error" else None)
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    pg.goto(
        "https://terreneitor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    pg.locator('.tab-link[data-tab="tab-disponibles"]').click()
    pg.wait_for_timeout(2500)
    n = pg.locator("#list-disponibles .task-card").count()
    print("tarjetas disponibles:", n)
    pg.screenshot(path=f"{OUT}/terreno_disponibles.png", full_page=False)
    # tomar la primera
    if n:
        pg.locator("#list-disponibles [data-tomar]").first.click()
        pg.wait_for_timeout(2500)
        n2 = pg.locator("#list-disponibles .task-card").count()
        print("tras tomar, disponibles:", n2)
        pg.screenshot(path=f"{OUT}/terreno_disponibles_tras_tomar.png", full_page=False)
    print("errores consola:", len(errs), errs[:5])
    b.close()
