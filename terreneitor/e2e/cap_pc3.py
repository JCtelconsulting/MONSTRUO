from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1920, "height": 1080}
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
    pg.wait_for_timeout(2500)
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1000)
    pg.screenshot(path=f"{OUT}/pc3_planes.png")
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1000)
    print(
        "ancho tarjeta:",
        pg.eval_on_selector(
            ".guia-tarea-card", "e=>Math.round(e.getBoundingClientRect().width)"
        ),
    )
    pg.screenshot(path=f"{OUT}/pc3_plan.png")
    print("errores:", len(errs), errs[:3])
    b.close()
