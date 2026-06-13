from playwright.sync_api import sync_playwright

OUT = "/work/tests/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    # login
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1280, "height": 820}
    )
    pg = ctx.new_page()
    bad = []
    pg.on(
        "response",
        lambda r: (
            bad.append((r.status, r.url.split("/")[-1]))
            if (r.status >= 400 and ("logo" in r.url or "img" in r.url))
            else None
        ),
    )
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.wait_for_timeout(1800)
    logo_ok = (
        pg.eval_on_selector(".brand-logo", "e=>e.complete && e.naturalWidth>0")
        if pg.locator(".brand-logo").count()
        else "no-logo"
    )
    print("login logo carga:", logo_ok, "| 404s img:", bad)
    pg.screenshot(path=f"{OUT}/marca_login.png")
    # terreno
    pg.fill("#email", "qa.terreno@telconsulting.cl")
    pg.fill("#password", "QaTerr2026!")
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    pg.goto(
        "https://terreneitor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    cube = (
        pg.eval_on_selector(".brand-cube", "e=>e.complete && e.naturalWidth>0")
        if pg.locator(".brand-cube").count()
        else "no-cube"
    )
    font = pg.evaluate("getComputedStyle(document.body).fontFamily")
    print("cubo carga:", cube, "| font:", font)
    pg.screenshot(path=f"{OUT}/marca_terreno.png")
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(900)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(900)
    pg.screenshot(path=f"{OUT}/marca_terreno_plan.png")
    b.close()
    print("ok")
