from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzI5NTY5fQ.sqb2TDy2tAga33sEY6hP9mU9KKLCQt5Hil6zMOImWu8"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 950})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    pg.goto("https://config.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    a = pg.locator('details.cfg-collapse').nth(0).bounding_box()
    c = pg.locator('details.cfg-collapse').nth(1).bounding_box()
    print(f"izq: y={a['y']:.0f} h={a['height']:.0f} | der: y={c['y']:.0f} h={c['height']:.0f}")
    pg.screenshot(path=f"{OUT}/alineado.png")
    b.close()
