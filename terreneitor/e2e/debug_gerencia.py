from playwright.sync_api import sync_playwright

E = "qa.gerencia@telconsulting.cl"
P = "QaGer2026!"
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
            print(f"  CONSOLE[{m.type}] {m.text[:120]}") if m.type == "error" else None
        ),
    )
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(6000)
    print("URL final:", pg.url)
    b.close()
