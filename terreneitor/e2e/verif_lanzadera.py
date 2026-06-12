from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzI5NTY5fQ.sqb2TDy2tAga33sEY6hP9mU9KKLCQt5Hil6zMOImWu8"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 950})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:90]) if m.type == "error" else None)
    pg.goto("https://login.telconsulting.cl/dev/dashboard", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    cards = pg.locator('.launch-card').count()
    kpis = pg.locator('#ops-kpi-grid, #tks-widget-container, #failures-container').count()
    print(f"tarjetas modulo={cards} | widgets viejos={kpis} | errores={len(errs)} {errs[:2]}")
    pg.screenshot(path=f"{OUT}/lanzadera.png")
    b.close()
