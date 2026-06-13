from playwright.sync_api import sync_playwright

E = "qa.supervisor@telconsulting.cl"
P = "QaSup2026!"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1366, "height": 900}
    )
    pg = ctx.new_page()
    pg.on("dialog", lambda d: (print(" DIALOG:", d.message[:60]), d.accept()))
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(4000)
    pg.goto(
        "https://supervisor.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(2500)
    # 1) seleccionar proyecto
    pg.locator("text=INSTALACION_DOMICILIO_DEMO").first.click()
    pg.wait_for_timeout(2000)
    # 2) seleccionar primera tarea (checkbox/click en la lista de tareas del proyecto)
    tasks = pg.locator(
        "#tasks-container input[type=checkbox], #tasks-container .task-item, [id^=i-]"
    )
    print("posibles tareas:", tasks.count())
    # intentar varios selectores de tarea
    for sel in [
        '[id^="i-"]',
        "#tasks-container .selectable",
        "#tasks-container li",
        "#tasks-container .task-row",
    ]:
        el = pg.locator(sel)
        if el.count():
            el.first.click()
            print("tarea click via", sel)
            break
    pg.wait_for_timeout(1200)
    # 3) seleccionar cuadrilla
    pg.locator("text=QA Terreno").first.click()
    pg.wait_for_timeout(800)
    # 4) llenar nombre
    pg.select_option("#plan-tipo", "Despacho")
    pg.fill("#plan-cliente", "Entel")
    pg.fill("#plan-numero", "123")
    pg.fill("#plan-fecha", "2026-06-11")
    pg.wait_for_timeout(500)
    enabled = pg.eval_on_selector("#btn-crear-plan", "b=>!b.disabled")
    print(
        "boton habilitado:",
        enabled,
        "| items sel:",
        (
            pg.evaluate(
                "Object.keys(window.AppState?AppState.selectedItems||{}:{}).length"
            )
            if False
            else "n/a"
        ),
    )
    if enabled:
        pg.locator("#btn-crear-plan").click()
        pg.wait_for_timeout(3000)
    b.close()
