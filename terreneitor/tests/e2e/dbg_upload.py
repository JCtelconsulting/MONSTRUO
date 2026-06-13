from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 420, "height": 860}
    )
    pg = ctx.new_page()
    pg.on(
        "console",
        lambda m: (
            print(" C:", m.type, m.text[:120])
            if m.type in ("error", "warning")
            else None
        ),
    )
    pg.on(
        "response",
        lambda r: (
            print("  R", r.status, r.url.split("telconsulting.cl")[-1])
            if "upload-multiple" in r.url
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
    pg.goto(
        "https://terreneitor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(3000)
    pg.locator('[data-act="mis"]').click()
    pg.wait_for_timeout(1000)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1000)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(900)
    print(
        "Guia.activo:",
        pg.evaluate("window.Guia && window.Guia.activo"),
        "vista:",
        pg.evaluate("window.Guia && window.Guia.vista"),
    )
    pg.locator('[data-act="foto"]').click()
    pg.wait_for_timeout(800)
    print(
        "modal abierto:",
        pg.locator("#modal-upload").is_visible(),
        "g_taskUploadId:",
        pg.evaluate("window.g_taskUploadId"),
    )
    pg.set_input_files("#file-input", "/work/data/_demo_fotos/con1.jpg")
    pg.wait_for_timeout(1200)
    print(
        "g_filesToUpload:",
        pg.evaluate("window.g_filesToUpload ? window.g_filesToUpload.length : 'n/a'"),
    )
    pg.locator('#form-upload button[type="submit"]').click()
    pg.wait_for_timeout(7000)
    print(
        "vista despues:",
        pg.evaluate("window.Guia && window.Guia.vista"),
        "idx:",
        pg.evaluate("window.Guia && window.Guia.idx"),
    )
    b.close()
