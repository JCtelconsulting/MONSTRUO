from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 420, "height": 840}
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
    pg.wait_for_timeout(3000)
    print("guia visible:", pg.locator("#guia .guia-card").count() > 0)
    pg.screenshot(path=f"{OUT}/guia_1_inicio.png")
    # click "Hacer mis tareas" si existe, si no "Tomar nueva"
    if pg.locator('[data-act="hacer"]').count():
        pg.locator('[data-act="hacer"]').click()
        pg.wait_for_timeout(1800)
        print("paso visible:", pg.locator(".guia-paso").count() > 0)
        pg.screenshot(path=f"{OUT}/guia_2_paso.png")
    elif pg.locator('[data-act="tomar"]').count():
        pg.locator('[data-act="tomar"]').click()
        pg.wait_for_timeout(1800)
        pg.screenshot(path=f"{OUT}/guia_2_elegir.png")
    # probar "tomar nueva" tambien
    (
        pg.locator('[data-act="inicio"]').first.click()
        if pg.locator('[data-act="inicio"]').count()
        else None
    )
    pg.wait_for_timeout(1200)
    if pg.locator('[data-act="tomar"]').count():
        pg.locator('[data-act="tomar"]').click()
        pg.wait_for_timeout(1800)
        pg.screenshot(path=f"{OUT}/guia_3_elegir.png")
    print("errores consola:", len(errs), errs[:5])
    b.close()
