from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 420, "height": 1100}
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
    pg.locator('[data-act="tomar"]').click()
    pg.wait_for_timeout(1500)
    print("planes 'tomar un trabajo':", pg.locator(".guia-op").count())
    pg.screenshot(path=f"{OUT}/tomar_planes.png")
    # tomar el primero (Instalacion)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(2500)
    print("tras tomar, vista:", pg.evaluate("window.Guia && window.Guia.vista"))
    pg.screenshot(path=f"{OUT}/tomar_tras_tomar.png")
    print("errores:", len(errs), errs[:4])
    b.close()
