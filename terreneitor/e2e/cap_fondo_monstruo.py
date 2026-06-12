from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzAwMjg4fQ.zbn5qloQCDs8e8UOJfVp9Kp24sPgzzjp68chcTzmdp0"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    # dashboard monstruo
    pg.goto("https://login.telconsulting.cl/dev/dashboard", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2200)
    pg.screenshot(path=f"{OUT}/fondo_gw_dash.png")
    # ticketera
    pg.goto("https://ticketera.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/fondo_tks.png")
    b.close()
    # login (sin sesion)
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    pg.goto("https://login.telconsulting.cl/dev/login", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(1800)
    pg.screenshot(path=f"{OUT}/fondo_login.png")
    b.close(); print("ok")
