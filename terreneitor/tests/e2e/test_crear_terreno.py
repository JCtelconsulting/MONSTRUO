from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 420, "height": 960}
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
    pg.locator('[data-act="crear"]').click()
    pg.wait_for_timeout(1200)
    print("form crear visible:", pg.locator(".guia-crear").count() > 0)
    pg.select_option("#ct-tipo", "Despacho")
    pg.select_option("#ct-cliente", "Entel")
    pg.wait_for_timeout(1200)
    print("N auto tras Entel:", pg.eval_on_selector("#ct-numero", "e=>e.value"))
    pg.fill("#ct-fecha", "2026-06-11")
    pg.wait_for_timeout(300)
    pg.screenshot(path=f"{OUT}/crear_terreno_form.png")
    pg.locator('[data-act="crear"]').click()
    pg.wait_for_timeout(3500)
    print("vista tras crear:", pg.evaluate("window.Guia && window.Guia.vista"))
    print(
        "plan abierto:",
        (
            pg.locator(".guia-card h2").first.inner_text()
            if pg.locator(".guia-card h2").count()
            else "?"
        ),
    )
    print("tareas en el plan:", pg.locator(".guia-op").count())
    pg.screenshot(path=f"{OUT}/crear_terreno_plan.png")
    print("errores:", len(errs), errs[:4])
    b.close()
