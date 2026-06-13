from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.on(
        "response",
        lambda r: (
            print(f"  RESP {r.status} {r.request.method} {r.url}")
            if "/api/" in r.url
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
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    print("== tras login, voy al modulo terreno ==")
    pg.goto(
        "https://terreneitor.telconsulting.cl/dev/",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    pg.wait_for_timeout(4000)
    print("URL final:", pg.url)
    print("cookies:", [(c["name"]) for c in ctx.cookies()])
    b.close()
