from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 420, "height": 860}
    )
    pg = ctx.new_page()
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    pg.goto(
        "https://terreneitor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1000)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1000)  # plan
    pg.screenshot(path=f"{OUT}/g2_plan_conbadges.png")  # lista con badge 'con fotos'
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(900)  # tarea 1 (con fotos)
    pg.screenshot(path=f"{OUT}/g2_tarea_conaviso.png")
    print("aviso visible:", pg.locator(".guia-aviso").count())
    b.close()
