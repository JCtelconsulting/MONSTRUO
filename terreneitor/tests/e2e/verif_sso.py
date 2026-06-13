from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMjk4OTAxfQ.4YZlpiEaBPD8rmZY_W01HoMMUXuMfzTckbynBK_duig"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    # 1) dashboard de Monstruo: debe estar logueado y mostrar el tile Terreneitor
    pg.goto("https://login.telconsulting.cl/dev/dashboard", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    tile = pg.locator('text=Terreneitor').count()
    print("dashboard url:", pg.url[:70])
    print("tile Terreneitor visible:", tile > 0)
    pg.screenshot(path=f"{OUT}/sso_dashboard.png")
    # 2) click al tile (si esta) o ir directo: debe entrar SIN login
    pg.goto("https://terreneitor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(3000)
    en_login = pg.locator('#btnLogin').count() > 0
    print("terreneitor url:", pg.url[:70])
    print("pide login?:", en_login)
    pg.screenshot(path=f"{OUT}/sso_terreneitor.png")
    b.close()
