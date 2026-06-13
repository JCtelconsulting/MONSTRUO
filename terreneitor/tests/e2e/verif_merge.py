from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzIxNDIyfQ.oVvBWZHgXi3S5Ib3Gh9WnfZllGHFRAcEucvkIciYKLA"
OUT = "/work/tests/e2e/shots"
URLS = [
    ("dashboard", "https://login.telconsulting.cl/dev/dashboard", '.launch-card'),
    ("config", "https://config.telconsulting.cl/dev/", 'details.cfg-collapse'),
    ("ticketera", "https://ticketera.telconsulting.cl/dev/", 'body'),
    ("terreneitor_hub", "https://terreneitor.telconsulting.cl/dev/", '.hub-card:visible'),
]
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 950})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:80]) if m.type == "error" else None)
    for nombre, url, sel in URLS:
        e0 = len(errs)
        pg.goto(url, wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(2500)
        n = pg.locator(sel).count()
        print(f"{nombre}: sel={n} errores={len(errs)-e0}")
        pg.screenshot(path=f"{OUT}/merge_{nombre}.png")
    print("errores totales:", errs[:4])
    b.close()
