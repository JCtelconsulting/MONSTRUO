from playwright.sync_api import sync_playwright
OUT="/work/e2e/shots"
mods=[("supervisor","qa.supervisor@telconsulting.cl","QaSup2026!","https://supervisor.telconsulting.cl/dev/",1366),
      ("terreno","qa.terreno@telconsulting.cl","QaTerr2026!","https://terreneitor.telconsulting.cl/dev/",420),
      ("gerencia","qa.gerencia@telconsulting.cl","QaGer2026!",None,1366)]
with sync_playwright() as p:
    b=p.chromium.launch()
    for nombre,email,pwd,url,w in mods:
        ctx=b.new_context(ignore_https_errors=True,viewport={"width":w,"height":900}); pg=ctx.new_page()
        errs=[]; pg.on("console", lambda m: errs.append(m.text[:90]) if m.type=="error" else None)
        pg.goto("https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
        pg.fill("#email",email); pg.fill("#password",pwd); pg.click("#btnLogin"); pg.wait_for_timeout(4000)
        if url: pg.goto(url, wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(2500)
        rotas = pg.eval_on_selector_all('img','els=>els.filter(e=>e.src&&e.naturalWidth===0&&e.offsetParent).length')
        print(f"{nombre}: url={pg.url[:60]} imgs_rotas={rotas} errores={len(errs)} {errs[:2]}")
        pg.screenshot(path=f"{OUT}/pg_{nombre}.png"); ctx.close()
    # terreno: abrir un plan (lecturas profundas) 
    ctx=b.new_context(ignore_https_errors=True,viewport={"width":420,"height":900}); pg=ctx.new_page()
    pg.goto("https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.fill("#email","qa.terreno@telconsulting.cl"); pg.fill("#password","QaTerr2026!"); pg.click("#btnLogin"); pg.wait_for_timeout(4000)
    pg.goto("https://terreneitor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000); pg.wait_for_timeout(2500)
    if pg.locator('[data-act="mis"]').count():
        pg.locator('[data-act="mis"]').click(); pg.wait_for_timeout(1200)
        n=pg.locator('.guia-op').count(); print("planes en guia:", n)
        if n: pg.locator('.guia-op').first.click(); pg.wait_for_timeout(1200); print("tareas del plan:", pg.locator('.guia-op').count())
    pg.screenshot(path=f"{OUT}/pg_terreno_plan.png")
    b.close(); print("E2E ok")
