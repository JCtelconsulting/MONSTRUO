from playwright.sync_api import sync_playwright

EMAIL = "qa.dev@telconsulting.cl"
PASS = "QaDev2026!"
mods = {
    "supervisor": "https://supervisor.telconsulting.cl/dev/",
    "gerencia": "https://gerencial.telconsulting.cl/dev/",
    "terreno": "https://terreneitor.telconsulting.cl/dev/",
}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", EMAIL)
    pg.fill("#password", PASS)
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    print("login ->", "OK" if "/dev" in pg.url and "portal" in pg.url else pg.url)
    for name, url in mods.items():
        pg.goto(url, wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(2500)
        expired = "reason=expired" in pg.url
        print(
            f"  {name:11s} -> url_ok={'/dev' in pg.url and not expired}  (final={pg.url.split('telconsulting.cl')[-1][:40]})"
        )
        pg.screenshot(path=f"/work/tests/e2e/shots/dev_{name}.png")
    b.close()
