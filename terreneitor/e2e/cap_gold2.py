from playwright.sync_api import sync_playwright

OUT = "/work/e2e/shots"


def login(pg, email, pwd):
    pg.goto(
        "https://portal.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", email)
    pg.fill("#password", pwd)
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)


with sync_playwright() as p:
    b = p.chromium.launch()
    # portal (admin)
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    login(pg, "juan.lopez@telconsulting.cl", "Terreneitor2026!")
    pg.goto(
        "https://portal.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.wait_for_timeout(2500)
    print("portal url:", pg.url)
    pg.screenshot(path=f"{OUT}/gold_portal.png")
    ctx.close()
    # gerencia (rol gerencia)
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    login(pg, "qa.gerencia@telconsulting.cl", "QaGer2026!")
    pg.wait_for_timeout(2500)
    print("gerencia url:", pg.url)
    pg.screenshot(path=f"{OUT}/gold_gerencia.png")
    ctx.close()
    b.close()
    print("ok")
