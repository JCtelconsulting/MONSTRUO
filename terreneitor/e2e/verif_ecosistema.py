from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzAwMjg4fQ.zbn5qloQCDs8e8UOJfVp9Kp24sPgzzjp68chcTzmdp0"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    # --- 1) SIN sesion: el hub debe rebotar al login del gateway
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    pg.goto("https://terreneitor.telconsulting.cl/dev/", timeout=30000)
    pg.wait_for_timeout(3500)
    print("sin sesion ->", pg.url[:60])
    ctx.close()
    # --- 2) CON sesion del gateway (admin)
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1366, "height": 900})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:90]) if m.type == "error" else None)
    pg.goto("https://terreneitor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    cards = pg.locator('.hub-card:visible').count()
    eco = pg.locator('#nav-ecosistema .side-link').count()
    print(f"hub: cards visibles={cards} links ecosistema={eco} errores={len(errs)}")
    pg.screenshot(path=f"{OUT}/eco_hub.png")
    # entrar a SUPERVISION por la card
    pg.locator('.hub-card', has_text="SUPERVISI").click()
    pg.wait_for_timeout(3500)
    print("supervisor ->", pg.url[:70])
    rotas = pg.eval_on_selector_all('img', 'els=>els.filter(e=>e.src&&e.naturalWidth===0&&e.offsetParent).length')
    print("supervisor imgs rotas:", rotas)
    pg.screenshot(path=f"{OUT}/eco_supervisor.png")
    # volver al hub y entrar a TERRENO
    pg.goto("https://terreneitor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2000)
    pg.locator('.hub-card', has_text="TERRENO").first.click()
    pg.wait_for_timeout(3500)
    print("terreno ->", pg.url[:70], "| guia:", pg.locator('.guia-card').count() > 0)
    # --- 3) gateway dorado
    pg.goto("https://login.telconsulting.cl/dev/dashboard", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/eco_gateway_gold.png")
    print("errores totales:", len(errs), errs[:3])
    b.close()
