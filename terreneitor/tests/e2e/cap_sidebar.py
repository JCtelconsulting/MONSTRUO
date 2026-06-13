from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
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
    print("botones en sidebar (side-link):", pg.locator(".side-nav .side-link").count())
    print(
        "textos:",
        pg.eval_on_selector_all(
            ".side-nav .side-link span", "els=>els.map(e=>e.textContent)"
        ),
    )
    pg.screenshot(path=f"{OUT}/sidebar_uno.png")
    # probar que el boton Inicio funciona (ir a un plan y volver)
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1000)
    pg.locator("#btn-guia-home").click()
    pg.wait_for_timeout(800)
    print("volvio a inicio:", pg.locator(".guia-inicio").count() > 0)
    print("errores:", len(errs), errs[:3])
    b.close()
