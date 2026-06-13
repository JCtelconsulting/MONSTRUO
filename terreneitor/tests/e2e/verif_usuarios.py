from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzI5NTY5fQ.sqb2TDy2tAga33sEY6hP9mU9KKLCQt5Hil6zMOImWu8"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 950})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:90]) if m.type == "error" else None)
    pg.goto("https://config.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(3000)
    # filas con/sin tacho (sesion = sistemas@telconsulting.cl)
    filas = pg.locator('#tbodyUsers tr')
    n = filas.count()
    sin_tacho = []
    for i in range(n):
        u = filas.nth(i).locator('td').first.inner_text()
        tiene = filas.nth(i).locator('[data-action="delete"]').count() > 0
        if not tiene: sin_tacho.append(u)
    print(f"usuarios={n} | sin tacho={sin_tacho}")
    # acordeones cerrados
    print("acordeones:", pg.locator('details.cfg-collapse').count(), "| abiertos:", pg.locator('details.cfg-collapse[open]').count())
    pg.screenshot(path=f"{OUT}/usuarios_compacto.png")
    # abrir el primero
    pg.locator('details.cfg-collapse summary').first.click(); pg.wait_for_timeout(800)
    print("tras clic abiertos:", pg.locator('details.cfg-collapse[open]').count())
    pg.screenshot(path=f"{OUT}/usuarios_abierto.png")
    print("errores:", len(errs), errs[:3])
    b.close()
