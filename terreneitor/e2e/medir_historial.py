from playwright.sync_api import sync_playwright

E = "qa.gerencia@telconsulting.cl"
P = "QaGer2026!"
OUT = "/work/e2e/shots"
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(
        ignore_https_errors=True, viewport={"width": 1440, "height": 900}
    )
    pg = ctx.new_page()
    pg.goto(
        "https://terreno.telconsulting.cl/dev/", wait_until="networkidle", timeout=30000
    )
    pg.fill("#email", E)
    pg.fill("#password", P)
    pg.click("#btnLogin")
    pg.wait_for_timeout(3500)
    pg.goto(
        "https://gerencial.telconsulting.cl/dev/",
        wait_until="networkidle",
        timeout=30000,
    )
    pg.wait_for_timeout(1500)
    pg.locator('.side-link[data-target="section-historial"]').first.click()
    pg.wait_for_timeout(1500)
    pg.locator("#btn-buscar-historial").first.click()
    pg.wait_for_timeout(2500)
    info = pg.evaluate(
        """() => {
      const out = {};
      const rows = document.querySelectorAll('#lista-historial tr');
      out.rows = rows.length;
      const r = (el)=> el? (()=>{const b=el.getBoundingClientRect();const cs=getComputedStyle(el);return {top:Math.round(b.top),bottom:Math.round(b.bottom),h:Math.round(b.height),pos:cs.position,overflowY:cs.overflowY,maxH:cs.maxHeight,z:cs.zIndex};})():null;
      out.section_historial = r(document.getElementById('section-historial'));
      out.table_container = r(document.querySelector('#section-historial .table-container'));
      out.table = r(document.getElementById('tabla-historial'));
      out.section_evidencia = r(document.getElementById('section-evidencia'));
      // que elemento scrollea (main/body)
      const main = document.querySelector('main') || document.body;
      out.main = {pos:getComputedStyle(main).position, overflowY:getComputedStyle(main).overflowY, scrollH:main.scrollHeight, clientH:main.clientHeight, tag:main.tagName};
      out.body = {scrollH:document.body.scrollHeight, clientH:document.documentElement.clientHeight};
      // ultima fila: se sale del contenedor?
      const last = rows[rows.length-1];
      out.last_row = r(last);
      const sec = document.getElementById('section-historial');
      out.table_overflows_section = out.table && out.section_historial ? (out.table.bottom > out.section_historial.bottom+2) : null;
      return out;
    }"""
    )
    import json

    print(json.dumps(info, indent=2))
    pg.screenshot(path=f"{OUT}/hist_medido_full.png", full_page=True)
    b.close()
