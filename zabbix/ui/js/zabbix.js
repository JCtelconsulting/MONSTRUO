async function _fetchJson(url) {
  try {
    const data = await window.fetchApi(url);
    return { ok: true, status: 200, data };
  } catch (e) {
    console.error("Zabbix fetch error:", e);
    return { ok: false, status: 0, data: null };
  }
}

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function _fillTable(tbody, rows) {
  tbody.innerHTML = "";
  for (const tr of rows) tbody.appendChild(tr);
}

function _tr(cells) {
  const tr = document.createElement("tr");
  for (const c of cells) {
    const td = document.createElement("td");
    td.textContent = c == null ? "" : String(c);
    tr.appendChild(td);
  }
  return tr;
}

async function cargarZabbix() {
  _setText("zbx-estado", "Cargando...");
  _setText("zbx-detalle", "");
  const estadoRes = await _fetchJson("/api/zabbix/estado");

  if (!estadoRes.ok || !estadoRes.data) {
    _setText("zbx-estado", "Falta informacion: API no disponible");
    _setText("zbx-problemas-estado", "Falta informacion: API no disponible");
    return;
  }

  const est = estadoRes.data.estado || "DESCONOCIDO";
  _setText("zbx-estado", est);
  _setText("zbx-detalle", estadoRes.data.detalle || "");

  const tbody = document.querySelector("#zbx-problemas-tabla tbody");

  if (est === "ACTIVO_EN_UN_FUTURO") {
    _setText("zbx-problemas-estado", "ACTIVO EN UN FUTURO (sin credenciales)");
    if (tbody) _fillTable(tbody, []);
    return;
  }

  const probRes = await _fetchJson("/api/zabbix/problemas");
  const lista = probRes.data && Array.isArray(probRes.data.problemas) ? probRes.data.problemas : [];

  if (!probRes.ok) {
    _setText("zbx-problemas-estado", "Falta informacion: no se pudo obtener problemas");
    if (tbody) _fillTable(tbody, []);
    return;
  }

  _setText("zbx-problemas-estado", `Problemas: ${lista.length}`);
  if (tbody) {
    const rows = lista.map((p) => _tr([p.eventid, p.name, p.severity, p.clock]));
    _fillTable(tbody, rows);
  }
}

document.addEventListener("DOMContentLoaded", cargarZabbix);
