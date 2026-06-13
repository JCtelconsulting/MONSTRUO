from playwright.sync_api import sync_playwright

OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1280, "height": 860}
    )
    pg = ctx.new_page()
    pg.goto(
        "https://portal.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", "juan.lopez@telconsulting.cl")
    pg.fill("#password", "Terreneitor2026!")
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    pg.goto(
        "https://portal.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.wait_for_timeout(2000)
    # recortar la esquina sup izq (sidebar) para ver el logo
    pg.screenshot(path=f"{OUT}/logo_portal_full.png")
    el = pg.locator("#app-header")
    if el.count():
        el.screenshot(path=f"{OUT}/logo_sidebar.png")
    print("ok")
    b.close()
