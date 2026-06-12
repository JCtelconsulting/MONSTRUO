from playwright.sync_api import sync_playwright

E = "juan.lopez@telconsulting.cl"
P = "Terreneitor2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 950}
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
    pg.wait_for_timeout(4500)
    print("URL:", pg.url)
    secs = pg.evaluate(
        "() => Array.from(document.querySelectorAll('.section-block')).filter(s=>!s.hidden&&s.offsetParent!==null).map(s=>s.id)"
    )
    print("secciones visibles:", secs)
    links = pg.evaluate(
        "() => Array.from(document.querySelectorAll('.side-link[data-section]:not([hidden])')).map(b=>b.dataset.section)"
    )
    print("links sidebar:", links)
    pg.evaluate(
        "const m=document.querySelector('main'); m.style.height='auto'; m.style.overflow='visible';"
    )
    pg.wait_for_timeout(500)
    pg.locator("main").screenshot(path=f"{OUT}/portal_unapagina.png")
    print("errores consola:", len(errs), errs[:5])
    b.close()
