from playwright.sync_api import sync_playwright

OUT = "/work/tests/e2e/shots"


def login(pg, email, pwd):
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", email)
    pg.fill("#password", pwd)
    pg.click("#btnLogin")
    pg.wait_for_timeout(3500)


with sync_playwright() as p:
    b = p.chromium.launch()
    # 1) login page (sin auth)
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1366, "height": 860}
    )
    pg = ctx.new_page()
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.wait_for_timeout(1500)
    pg.screenshot(path=f"{OUT}/gold_login.png")
    ctx.close()
    # 2) terreno
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    login(pg, "qa.terreno@telconsulting.cl", "QaTerr2026!")
    pg.goto(
        "https://terreneitor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/gold_terreno_inicio.png")
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1000)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1000)
    pg.screenshot(path=f"{OUT}/gold_terreno_plan.png")
    ctx.close()
    # 3) supervisor
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    login(pg, "qa.supervisor@telconsulting.cl", "QaSup2026!")
    pg.goto(
        "https://supervisor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/gold_supervisor.png")
    ctx.close()
    # 4) gerencia
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    login(pg, "qa.gerencia@telconsulting.cl", "QaGer2026!")
    pg.goto(
        "https://gerencia.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    pg.screenshot(path=f"{OUT}/gold_gerencia.png")
    ctx.close()
    b.close()
    print("ok")
