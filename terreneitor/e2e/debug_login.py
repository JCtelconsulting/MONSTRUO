#!/usr/bin/env python3
"""Debug del flujo de login en el navegador: captura respuestas de /api/auth/*
y las cookies tras el login, para ver por que el portal rebota a login."""
import os

from playwright.sync_api import sync_playwright

EMAIL = os.environ.get("QA_EMAIL", "qa.dev@telconsulting.cl")
PASS = os.environ.get("QA_PASS", "QaDev2026!")
LOGIN_URL = "https://terreno.telconsulting.cl/dev/"

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(ignore_https_errors=True)
    page = ctx.new_page()

    def on_resp(r):
        if "/api/auth/" in r.url:
            print(f"  RESP {r.status} {r.request.method} {r.url}")

    page.on("response", on_resp)
    page.on(
        "framenavigated",
        lambda f: print(f"  NAV  {f.url}") if f == page.main_frame else None,
    )

    print("1) abrir login")
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
    print(
        "   cookies tras abrir login:",
        [(c["name"], c.get("domain")) for c in ctx.cookies()],
    )

    print("2) llenar y enviar login")
    page.fill("#email", EMAIL)
    page.fill("#password", PASS)
    page.click("#btnLogin")
    page.wait_for_timeout(5000)

    print(
        "   cookies tras login:",
        [
            (c["name"], c.get("domain"), "secure=" + str(c.get("secure")))
            for c in ctx.cookies()
        ],
    )
    print("   URL actual:", page.url)
    # probar whoami manualmente desde el contexto del portal
    try:
        res = page.evaluate(
            """async () => {
            const r = await fetch('/dev/api/auth/whoami', {credentials:'include'});
            return {status: r.status, body: (await r.text()).slice(0,120)};
        }"""
        )
        print("   whoami manual desde la pagina actual:", res)
    except Exception as e:
        print("   whoami manual fallo:", e)

    b.close()
