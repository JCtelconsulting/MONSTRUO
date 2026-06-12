from playwright.sync_api import sync_playwright
OUT="/work/e2e/shots"
with sync_playwright() as p:
    b=p.chromium.launch()
    ctx=b.new_context(ignore_https_errors=True,viewport={"width":1366,"height":860}); pg=ctx.new_page()
    pg.goto("https://portal.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000)
    pg.fill("#email","juan.lopez@telconsulting.cl"); pg.fill("#password","Terreneitor2026!"); pg.click("#btnLogin"); pg.wait_for_timeout(4500)
    print("tras login:", pg.url)
    r = pg.evaluate("fetch('/dev/api/auth/whoami',{credentials:'include'}).then(r=>r.json()).catch(e=>String(e))")
    print("whoami:", r)
    pg.screenshot(path=f"{OUT}/fase1_portal.png")
    b.close()
