from playwright.sync_api import sync_playwright
OUT="/work/e2e/shots"
with sync_playwright() as p:
    b=p.chromium.launch()
    # supervisor: datos DB + thumbnails de fotos
    ctx=b.new_context(ignore_https_errors=True,viewport={"width":1366,"height":860}); pg=ctx.new_page()
    errs=[]; pg.on("console", lambda m: errs.append(m.text[:100]) if m.type=="error" else None)
    pg.goto("https://supervisor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.fill("#email","qa.supervisor@telconsulting.cl"); pg.fill("#password","QaSup2026!"); pg.click("#btnLogin"); pg.wait_for_timeout(4000)
    pg.goto("https://supervisor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000); pg.wait_for_timeout(2500)
    print("supervisor url:", pg.url)
    rotas = pg.eval_on_selector_all('img','els=>els.filter(e=>e.src&&e.naturalWidth===0&&e.offsetParent).length')
    print("imgs rotas:", rotas, "| console errors:", len(errs))
    pg.screenshot(path=f"{OUT}/fase1_supervisor_ok.png"); ctx.close()
    # terreno: guía con planes desde la DB
    ctx=b.new_context(ignore_https_errors=True,viewport={"width":420,"height":900}); pg=ctx.new_page()
    errs2=[]; pg.on("console", lambda m: errs2.append(m.text[:100]) if m.type=="error" else None)
    pg.goto("https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.fill("#email","qa.terreno@telconsulting.cl"); pg.fill("#password","QaTerr2026!"); pg.click("#btnLogin"); pg.wait_for_timeout(4000)
    pg.goto("https://terreneitor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000); pg.wait_for_timeout(2500)
    botones = pg.locator('.guia-btn').count()
    print("terreno guia botones:", botones, "| console errors:", len(errs2))
    pg.screenshot(path=f"{OUT}/fase1_terreno_ok.png"); ctx.close()
    b.close(); print("ok")
