from playwright.sync_api import sync_playwright

E = "qa.terreno@telconsulting.cl"
P = "QaTerr2026!"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 420, "height": 860}
    )
    pg = ctx.new_page()
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
    pg.wait_for_timeout(1200)
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1200)  # abrir plan
    pg.locator(".guia-op").first.click()
    pg.wait_for_timeout(1000)  # abrir tarea 1
    antes = (
        pg.locator(".guia-progreso").inner_text()
        if pg.locator(".guia-progreso").count()
        else "?"
    )
    print("antes:", antes)
    pg.locator('[data-act="foto"]').click()
    pg.wait_for_timeout(1000)  # abrir modal upload
    pg.set_input_files("#file-input", "/work/data/_demo_fotos/con1.jpg")
    pg.wait_for_timeout(1500)
    # submit del form de upload
    pg.locator('#form-upload button[type="submit"]').click()
    pg.wait_for_timeout(7000)  # esperar subida + auto-avance
    despues = (
        pg.locator(".guia-progreso").inner_text()
        if pg.locator(".guia-progreso").count()
        else "(no en tarea)"
    )
    print("despues:", despues)
    print("avanzo solo:", antes != despues)
    pg.screenshot(path="/work/e2e/shots/g2_autoavance.png")
    b.close()
