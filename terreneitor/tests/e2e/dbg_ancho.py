from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
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
    for sel in ["#guia", ".guia-card", ".guia-btn"]:
        el = pg.locator(sel).first
        if el.count():
            print(
                sel,
                "->",
                pg.eval_on_selector(
                    sel, 'e=>Math.round(e.getBoundingClientRect().width)+"px"'
                ),
            )
    print(
        "--max-content-width:",
        pg.evaluate(
            "getComputedStyle(document.documentElement).getPropertyValue('--max-content-width')"
        ),
    )
    b.close()
