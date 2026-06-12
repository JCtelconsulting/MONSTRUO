from playwright.sync_api import sync_playwright

E = "juan.lopez@telconsulting.cl"
P = "Terreneitor2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.on(
        "response",
        lambda r: (
            print(
                f"  {r.status} {r.request.method} {r.url.split('telconsulting.cl')[-1]}"
            )
            if "/api/auth" in r.url
            else None
        ),
    )
    pg.on(
        "framenavigated",
        lambda f: print(f"  NAV {f.url}") if f == pg.main_frame else None,
    )
    pg.on(
        "console",
        lambda m: (
            print(f"  CONSOLE[{m.type}] {m.text[:140]}")
            if m.type in ("error", "warning")
            else None
        ),
    )
    print("1) abrir login")
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    # ver campos
    print(
        "   #email existe:",
        pg.locator("#email").count(),
        "| #password:",
        pg.locator("#password").count(),
        "| #btnLogin:",
        pg.locator("#btnLogin").count(),
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(5000)
    print("   URL final:", pg.url)
    print("   cookies:", [(c["name"], c.get("domain")) for c in ctx.cookies()])
    pg.screenshot(path=f"{OUT}/juan_login.png", full_page=False)
    b.close()
