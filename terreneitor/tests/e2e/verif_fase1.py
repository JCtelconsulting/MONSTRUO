from playwright.sync_api import sync_playwright
OUT="/work/tests/e2e/shots"
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(ignore_https_errors=True,viewport={"width":1366,"height":860}); pg=ctx.new_page()
    errs=[]; pg.on("console", lambda m: errs.append(m.text[:100]) if m.type=="error" else None)
    bad=[]; pg.on("response", lambda r: bad.append((r.status,r.url[-60:])) if r.status>=500 else None)
    # login via proxy
    pg.goto("https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.fill("#email","juan.lopez@telconsulting.cl"); pg.fill("#password","Terreneitor2026!"); pg.click("#btnLogin"); pg.wait_for_timeout(4000)
    print("tras login:", pg.url)
    # portal
    pg.goto("https://portal.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000); pg.wait_for_timeout(2000)
    print("portal cargo, usuarios visibles:", pg.locator('.user-card,.usuario-card,[class*=user]').count()>0)
    # supervisor con thumbnails (datos desde la DB + fotos desde disco)
    pg.goto("https://supervisor.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000); pg.wait_for_timeout(2500)
    imgs = pg.eval_on_selector_all('img','els=>els.filter(e=>e.src&&!e.complete||e.naturalWidth===0).length')
    print("imgs rotas supervisor:", imgs)
    pg.screenshot(path=f"{OUT}/fase1_supervisor.png")
    print("console errors:", len(errs), errs[:3])
    print("respuestas 5xx:", bad[:5])
    b.close()
