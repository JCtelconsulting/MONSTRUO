from playwright.sync_api import sync_playwright

E = "qa.supervisor@telconsulting.cl"
P = "QaSup2026!"
OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1366, "height": 900}
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
        "https://supervisor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    opts = pg.eval_on_selector_all(
        "#plan-cliente option", "els=>els.map(e=>e.textContent)"
    )
    print("opciones cliente:", opts)
    pg.select_option("#plan-cliente", "Entel")
    pg.wait_for_timeout(1200)
    print(
        "N° auto tras elegir Entel:", pg.eval_on_selector("#plan-numero", "e=>e.value")
    )
    pg.select_option("#plan-tipo", "Despacho")
    pg.fill("#plan-fecha", "2026-06-11")
    pg.wait_for_timeout(500)
    print("preview:", pg.locator("#plan-preview").inner_text())
    pg.screenshot(path=f"{OUT}/plan_form_clientes.png")
    print("errores:", len(errs), errs[:3])
    b.close()
