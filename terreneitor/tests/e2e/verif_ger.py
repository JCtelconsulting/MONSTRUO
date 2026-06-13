from playwright.sync_api import sync_playwright
OUT="/work/tests/e2e/shots"
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(ignore_https_errors=True,viewport={"width":1366,"height":900}); pg=ctx.new_page()
    errs=[]; pg.on("console", lambda m: errs.append(m.text[:90]) if m.type=="error" else None)
    cincos=[]; pg.on("response", lambda r: cincos.append((r.status,r.url[-70:])) if r.status>=500 else None)
    pg.goto("https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.fill("#email","qa.gerencia@telconsulting.cl"); pg.fill("#password","QaGer2026!"); pg.click("#btnLogin"); pg.wait_for_timeout(4500)
    pg.wait_for_timeout(3000)
    print("url:", pg.url[:60])
    print("5xx:", cincos)
    print("console errors:", len(errs), errs[:3])
    pg.screenshot(path=f"{OUT}/pg_gerencia_ok.png", full_page=False)
    b.close()
