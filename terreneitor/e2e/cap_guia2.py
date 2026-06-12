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
    errs = []
    pg.on("console", lambda m: errs.append(m.text[:120]) if m.type == "error" else None)
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
    pg.wait_for_timeout(3000)
    pg.screenshot(path=f"{OUT}/g2_inicio.png")
    print("tiene 'ver lista completa':", pg.locator("text=Ver lista completa").count())
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1500)
    print("planes:", pg.locator(".guia-op").count())
    pg.screenshot(path=f"{OUT}/g2_planes.png")
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1500)
    print("tareas del plan:", pg.locator(".guia-op").count())
    pg.screenshot(path=f"{OUT}/g2_plan.png")
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1200)
    print("vista tarea:", pg.locator(".guia-paso").count() > 0)
    pg.screenshot(path=f"{OUT}/g2_tarea.png")
    print("errores:", len(errs), errs[:4])
    b.close()
