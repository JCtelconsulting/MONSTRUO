from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzIxNDIyfQ.oVvBWZHgXi3S5Ib3Gh9WnfZllGHFRAcEucvkIciYKLA"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    pg.on("response", lambda r: print("RES", r.status, r.url[-75:]) if r.status >= 400 else None)
    pg.on("console", lambda m: print("CONSOLE", m.type, m.text[:110]) if m.type in ("error","warning") else None)
    pg.goto("https://terreneitor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(3000)
    print("url:", pg.url[:70])
    print("hub-cards visibles:", pg.locator('.hub-card:visible').count())
    print("hub.js cargado?:", pg.evaluate("!!document.querySelector('script[src*=hub]')"))
    b.close()
