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
    print(
        "ancho #guia:",
        pg.eval_on_selector("#guia", "e=>Math.round(e.getBoundingClientRect().width)"),
    )
    pg.screenshot(path=f"{OUT}/pc_inicio.png")
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1200)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1200)
    print(
        "columnas grid:",
        pg.eval_on_selector(
            ".guia-lista", "e=>getComputedStyle(e).gridTemplateColumns"
        ),
    )
    pg.screenshot(path=f"{OUT}/pc_plan.png")
    print("errores:", len(errs), errs[:3])
    b.close()
