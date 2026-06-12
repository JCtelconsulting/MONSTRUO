from playwright.sync_api import sync_playwright
TOK = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzaXN0ZW1hc0B0ZWxjb25zdWx0aW5nLmNsIiwicm9sZSI6ImFkbWluIiwicm9sZXMiOlsiYWRtaW4iXSwiZXhwIjoxNzgxMzAwMjg4fQ.zbn5qloQCDs8e8UOJfVp9Kp24sPgzzjp68chcTzmdp0"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True, viewport={"width": 1400, "height": 950})
    ctx.add_cookies([{"name": "access_token", "value": TOK, "domain": ".telconsulting.cl", "path": "/"}])
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:90]) if m.type == "error" else None)
    pg.goto("https://config.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(2500)
    # ir a pestaña Ticketera
    pg.locator('text=Ticketera').first.click(); pg.wait_for_timeout(1500)
    print("nota plantillas:", pg.locator('text=Dominio/Plantillas').count())
    print("checkbox acuse:", pg.locator('#chkAutoReply').count())
    print("campos tiempos:", pg.locator('#emailPollingInterval').count(), pg.locator('#ticketAutoReplyTime').count(), pg.locator('#ticketAutoCloseTime').count())
    # probar guardar (mismo valor) -> debe responder ok sin error
    pg.locator('#btnSaveConfig').click(); pg.wait_for_timeout(2000)
    pg.screenshot(path=f"{OUT}/config_limpia.png")
    print("errores consola:", len(errs), errs[:3])
    b.close()
