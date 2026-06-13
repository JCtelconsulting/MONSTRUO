// ==========================================================================
// GERENCIA.JS (v65.0 PROD - EXEC DASHBOARD)
// ==========================================================================

const APP_VERSION = '2026-01-10.1';
const APP_VERSION_KEY = 'gerencia_app_version';
const LOGIN_URL_APP =
  typeof window.getEnvLoginUrl === 'function'
    ? window.getEnvLoginUrl()
    : `${window.location.origin}${window.location.pathname.startsWith('/dev') ? '/dev' : ''}/`;
let authRedirecting = false;

const Loader = {
  show() {
    document.getElementById('global-loader').style.display = 'flex';
  },
  hide() {
    document.getElementById('global-loader').style.display = 'none';
  },
};

function ensureAppVersion() {
  const current = localStorage.getItem(APP_VERSION_KEY);
  if (current !== APP_VERSION) {
    localStorage.setItem(APP_VERSION_KEY, APP_VERSION);
    const url = new URL(window.location.href);
    url.searchParams.set('v', APP_VERSION);
    window.location.replace(url.toString());
    return true;
  }
  return false;
}

function handleAuthExpired() {
  if (authRedirecting) {
    return;
  }
  authRedirecting = true;
  try {
    Loader.show('Sesion expirada. Reingresando...');
  } catch (e) {}
  setTimeout(() => {
    window.location.href = LOGIN_URL_APP;
  }, 250);
}

window.handleAuthExpired = handleAuthExpired;

let productividadChart = null;
let mapInstance = null;
let mapHeatLayer = null;
let mapMarkerLayer = null;
let mapPoints = [];
let mapMode = 'heat';

// --- FIX: FUNCION FETCH COMPLETA (SOPORTA POST/LOGIN) ---
async function fetchApi(url, options = {}) {
  if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/api')) {
    url = '/api' + url;
  }
  // Prefijo de entorno (/dev): sin esto, estando en /dev las llamadas pegaban
  // a PROD y la app rebotaba al login.
  if (
    typeof url === 'string' &&
    url.startsWith('/api') &&
    window.location.pathname.startsWith('/dev')
  ) {
    url = '/dev' + url;
  }
  options.credentials = 'include';
  options.headers = options.headers || {};

  if (options.body && typeof options.body !== 'string' && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const resp = await fetch(url, options);
  // Solo 401 (no autenticado) desloguea; 403 (sin permiso) NO debe rebotar
  // al login: cae al manejo de error normal para que la seccion lo muestre.
  if (resp.status === 401) {
    handleAuthExpired();
    throw new Error('Sesion expirada');
  }
  if (!resp.ok) {
    let m = `Error ${resp.status}`;
    try {
      const d = await resp.json();
      m = d.detail || m;
    } catch (e) {}
    throw new Error(m);
  }
  const text = await resp.text();
  return text ? JSON.parse(text) : {};
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
  }
}

function formatNumber(value, decimals = 1) {
  const num = Number(value);
  if (Number.isNaN(num)) {
    return '0';
  }
  return num.toFixed(decimals);
}

function formatDateShort(value) {
  if (!value) {
    return '';
  }
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    return '';
  }
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  return `${day}-${month}-${d.getFullYear()}`;
}

function setSegmentActive(container, value, dataAttr) {
  if (!container) {
    return;
  }
  const attr = dataAttr || 'value';
  const selector = `button[data-${attr}]`;
  const dataKey = attr.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
  const buttons = container.querySelectorAll(selector);
  buttons.forEach((btn) => {
    if (btn.dataset[dataKey] === value) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function initSideNav() {
  const nav = document.querySelector('.side-nav');
  if (!nav) {
    return;
  }

  // Logic for Sidebar Toggle
  const toggleBtn = document.getElementById('sidebar-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      document.body.classList.toggle('sidebar-collapsed');
    });
  }

  const buttons = Array.from(nav.querySelectorAll('[data-target]'));
  if (!buttons.length) {
    return;
  }
  const sections = buttons
    .map((btn) => {
      const targetId = btn.dataset.target;
      const target = targetId ? document.getElementById(targetId) : null;
      return target || null;
    })
    .filter(Boolean);

  const setActive = (targetId) => {
    buttons.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.target === targetId);
    });
  };

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target;
      const target = targetId ? document.getElementById(targetId) : null;
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      if (targetId) {
        setActive(targetId);
      }
    });
  });

  const resolveScrollRoot = () => {
    const bodyOverflow = window.getComputedStyle(document.body).overflowY;
    if (bodyOverflow !== 'hidden') {
      return null;
    }
    return document.querySelector('main');
  };

  let scrollRoot = resolveScrollRoot();
  let scrollTarget = scrollRoot || window;
  const offsetTop = 140;
  let ticking = false;

  const getSectionTop = (section) => {
    const rect = section.getBoundingClientRect();
    if (!scrollRoot) {
      return rect.top + window.scrollY;
    }
    const rootRect = scrollRoot.getBoundingClientRect();
    return rect.top - rootRect.top + scrollRoot.scrollTop;
  };

  const updateActiveOnScroll = () => {
    if (!sections.length) {
      return;
    }
    const scrollPos = scrollRoot ? scrollRoot.scrollTop : window.scrollY;
    const anchor = scrollPos + offsetTop;
    let current = sections[0];
    sections.forEach((section) => {
      if (getSectionTop(section) <= anchor) {
        current = section;
      }
    });
    if (current && current.id) {
      setActive(current.id);
    }
  };

  const onScroll = () => {
    if (ticking) {
      return;
    }
    ticking = true;
    requestAnimationFrame(() => {
      updateActiveOnScroll();
      ticking = false;
    });
  };

  const bindScroll = (target) => {
    target.addEventListener('scroll', onScroll, { passive: true });
  };

  const unbindScroll = (target) => {
    target.removeEventListener('scroll', onScroll);
  };

  const handleResize = () => {
    const nextRoot = resolveScrollRoot();
    const nextTarget = nextRoot || window;
    if (nextTarget !== scrollTarget) {
      unbindScroll(scrollTarget);
      scrollRoot = nextRoot;
      scrollTarget = nextTarget;
      bindScroll(scrollTarget);
    }
    onScroll();
  };

  bindScroll(scrollTarget);
  window.addEventListener('resize', handleResize);

  updateActiveOnScroll();
}

// Init
document.addEventListener('DOMContentLoaded', () => {
  // PWA Service Worker Registration
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker
      .register(withEnvPrefix('/service-worker.js'), { scope: withEnvPrefix('/') })
      .catch((err) => console.log('SW Fail:', err));
  }

  if (ensureAppVersion()) {
    return;
  }
  console.log('Gerencia JS v65.0 (Exec Dashboard)');

  // Auth Check
  fetchApi('/auth/whoami')
    .then((u) => {
      if (u.logged) {
        document.getElementById('who').textContent = `${u.name} (${u.role})`;
      } else {
        window.location.href = LOGIN_URL_APP;
      }
    })
    .catch(() => (window.location.href = LOGIN_URL_APP));

  // Inicializar Modales y Logout (Usando la fetchApi corregida de arriba)
  if (typeof initLogout === 'function') initLogout();
  if (typeof initModal === 'function') initModal();

  initSideNav();
  initProductividadControls();
  initMap();
  initHistorial();
  initEvidencia();
  loadDashboard();
});

async function loadDashboard() {
  Loader.show();
  try {
    // 1. Cargar KPIs
    const kpis = await fetchApi('/api/gerencia/dashboard/kpis');
    document.getElementById('kpi-proyectos').textContent = kpis.proyectos_activos;
    document.getElementById('kpi-planes').textContent = kpis.planes_en_curso;
    document.getElementById('kpi-rechazo').textContent = kpis.tasa_rechazo;
    document.getElementById('kpi-cuarentena').textContent = kpis.fotos_cuarentena;

    // 2. Cargar Graficos y paneles
    await Promise.all([renderCharts(), loadStorage(), loadSla(), loadRisks()]);
  } catch (e) {
    console.error(e);
    // No alertamos para no molestar si es solo un error de red menor
  } finally {
    Loader.hide();
  }
}

async function renderCharts() {
  if (window.Chart && window.Chart.defaults) {
    window.Chart.defaults.color = '#e6eef2';
    window.Chart.defaults.font.family = '"Space Grotesk", "Sora", sans-serif';
  }
  try {
    const statsData = await fetchApi('/api/gerencia/dashboard/graficos/estados');
    const ctx1 = document.getElementById('chart-estados').getContext('2d');
    new Chart(ctx1, {
      type: 'doughnut',
      data: {
        labels: statsData.labels,
        datasets: [
          {
            data: statsData.data,
            backgroundColor: statsData.colors,
            borderColor: '#000',
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { color: '#fff' } } },
      },
    });
  } catch (e) {
    console.log('Error charts', e);
  }

  await renderProductividad('semanal');
}

function initProductividadControls() {
  const controls = document.getElementById('productividad-controls');
  if (!controls) {
    return;
  }
  controls.querySelectorAll('button[data-productividad]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const periodo = btn.dataset.productividad || 'semanal';
      renderProductividad(periodo);
    });
  });
}

async function renderProductividad(periodo) {
  const metaMap = {
    diario: 'Ultimos 14 dias',
    semanal: 'Ultimas 8 semanas',
    mensual: 'Ultimos 12 meses',
  };
  const meta = document.getElementById('productividad-meta');
  if (meta) {
    meta.textContent = metaMap[periodo] || 'Resumen';
  }

  try {
    const data = await fetchApi(`/api/gerencia/dashboard/productividad?periodo=${periodo}`);
    const ctx = document.getElementById('chart-avance').getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, 0, 320);
    grad.addColorStop(0, 'rgba(0, 255, 65, 0.9)');
    grad.addColorStop(1, 'rgba(0, 255, 65, 0.2)');

    if (!productividadChart) {
      productividadChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: data.labels || [],
          datasets: [
            {
              label: 'Tareas Validadas',
              data: data.data || [],
              backgroundColor: grad,
              borderColor: '#00ff41',
              borderWidth: 1,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: 'rgba(255,255,255,0.06)' },
              ticks: { color: '#d6dde3' },
            },
            x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#d6dde3' } },
          },
          plugins: { legend: { display: false } },
        },
      });
    } else {
      productividadChart.data.labels = data.labels || [];
      productividadChart.data.datasets[0].data = data.data || [];
      productividadChart.update();
    }
  } catch (e) {
    console.log('Error productividad', e);
  }

  setSegmentActive(document.getElementById('productividad-controls'), periodo, 'productividad');
}

async function loadStorage() {
  try {
    const data = await fetchApi('/api/gerencia/dashboard/storage');
    setText('storage-used', formatNumber(data.used_gb, 1));
    setText('storage-total', formatNumber(data.total_gb, 1));
    setText('storage-free', `Libre: ${formatNumber(data.free_gb, 1)} GB`);

    const bar = document.getElementById('storage-bar');
    if (bar) {
      const pct = Math.min(100, Math.max(0, Number(data.used_pct || 0)));
      bar.style.width = `${pct}%`;
      bar.classList.remove('bar-warning', 'bar-danger');
      if (pct >= 85) {
        bar.classList.add('bar-danger');
      } else if (pct >= 70) {
        bar.classList.add('bar-warning');
      }
    }
  } catch (e) {
    console.log('Error storage', e);
  }
}

async function loadSla() {
  try {
    const data = await fetchApi('/api/gerencia/dashboard/sla');
    setText('sla-avg', `${formatNumber(data.avg_h, 1)} h`);
    setText('sla-p90', `${formatNumber(data.p90_h, 1)} h`);
    setText('sla-breach', `${formatNumber(data.breach_pct, 1)}%`);

    const range = document.getElementById('sla-range');
    if (range) {
      const parts = [];
      const desde = formatDateShort(data.desde);
      const hasta = formatDateShort(data.hasta);
      if (desde || hasta) {
        parts.push(`${desde || '--'} a ${hasta || '--'}`);
      } else {
        parts.push('Global');
      }
      parts.push(`${data.count || 0} items`);
      range.textContent = parts.join(' | ');
    }
  } catch (e) {
    console.log('Error SLA', e);
  }
}

async function loadRisks() {
  const list = document.getElementById('risk-list');
  if (!list) {
    return;
  }
  list.innerHTML = '';
  try {
    const riesgos = await fetchApi('/api/gerencia/dashboard/riesgos');
    if (!riesgos || riesgos.length === 0) {
      const item = document.createElement('li');
      item.className = 'risk-item risk-low';
      const content = document.createElement('div');
      const title = document.createElement('div');
      title.className = 'risk-title';
      title.textContent = 'Sin alertas';
      const detail = document.createElement('div');
      detail.className = 'risk-detail';
      detail.textContent = 'Operacion estable.';
      content.appendChild(title);
      content.appendChild(detail);
      const pill = document.createElement('span');
      pill.className = 'risk-pill';
      pill.textContent = 'OK';
      item.appendChild(content);
      item.appendChild(pill);
      list.appendChild(item);
      return;
    }

    riesgos.forEach((r) => {
      const nivel = (r.nivel || '').toUpperCase();
      const item = document.createElement('li');
      if (nivel === 'ALTO') {
        item.className = 'risk-item risk-high';
      } else if (nivel === 'MEDIO') {
        item.className = 'risk-item risk-mid';
      } else {
        item.className = 'risk-item risk-low';
      }

      const content = document.createElement('div');
      const title = document.createElement('div');
      title.className = 'risk-title';
      title.textContent = r.titulo || 'Alerta';
      const detail = document.createElement('div');
      detail.className = 'risk-detail';
      detail.textContent = r.detalle || '';
      content.appendChild(title);
      content.appendChild(detail);

      const pill = document.createElement('span');
      pill.className = 'risk-pill';
      pill.textContent = nivel || 'INFO';

      item.appendChild(content);
      item.appendChild(pill);
      list.appendChild(item);
    });
  } catch (e) {
    console.log('Error riesgos', e);
  }
}

function initMap() {
  const mapEl = document.getElementById('map');
  if (!mapEl || !window.L) {
    return;
  }

  const toInput = document.getElementById('map-to');
  const fromInput = document.getElementById('map-from');
  if (toInput && !toInput.value) {
    toInput.value = new Date().toISOString().slice(0, 10);
  }
  if (fromInput && !fromInput.value) {
    const start = new Date();
    start.setDate(start.getDate() - 30);
    fromInput.value = start.toISOString().slice(0, 10);
  }

  mapInstance = L.map(mapEl, { zoomControl: true }).setView([-33.45, -70.66], 5);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
  }).addTo(mapInstance);

  const refreshBtn = document.getElementById('map-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', loadMapData);
  }

  const modeWrap = document.getElementById('map-mode');
  if (modeWrap) {
    modeWrap.querySelectorAll('button[data-map-mode]').forEach((btn) => {
      btn.addEventListener('click', () => {
        mapMode = btn.dataset.mapMode || 'heat';
        setSegmentActive(modeWrap, mapMode, 'map-mode');
        renderMapPoints(mapPoints);
      });
    });
  }

  // loadProjects() call removed
}

// loadProjects function removed

async function loadMapData() {
  if (!mapInstance) {
    return;
  }
  try {
    const params = new URLSearchParams();
    // Project filter logic removed as element #map-project likely removed from HTML or logic removed here
    const fromValue = document.getElementById('map-from')?.value;
    const toValue = document.getElementById('map-to')?.value;

    if (fromValue) {
      params.set('desde', fromValue);
    }
    if (toValue) {
      params.set('hasta', toValue);
    }
    params.set('max_puntos', '4000');

    const data = await fetchApi(`/api/gerencia/dashboard/mapa?${params.toString()}`);
    mapPoints = data.points || [];
    renderMapPoints(mapPoints);
    setText('map-count', `${mapPoints.length} puntos`);

    const rangeParts = [];
    if (fromValue || toValue) {
      rangeParts.push(`Fechas: ${fromValue || '--'} a ${toValue || '--'}`);
    }
    setText('map-range', rangeParts.length ? rangeParts.join(' | ') : 'Filtrado global');
  } catch (e) {
    console.log('Error mapa', e);
  }
}

function renderMapPoints(points) {
  if (!mapInstance) {
    return;
  }
  if (mapHeatLayer) {
    mapInstance.removeLayer(mapHeatLayer);
    mapHeatLayer = null;
  }
  if (mapMarkerLayer) {
    mapInstance.removeLayer(mapMarkerLayer);
    mapMarkerLayer = null;
  }

  if (!points || points.length === 0) {
    mapInstance.setView([-33.45, -70.66], 5);
    return;
  }

  const coords = points.map((p) => [p[0], p[1]]);
  if (mapMode === 'points') {
    const markers = coords.map((c) =>
      L.circleMarker(c, {
        radius: 4,
        color: '#00ff41',
        fillColor: '#00ff41',
        fillOpacity: 0.6,
        weight: 1,
      })
    );
    mapMarkerLayer = L.layerGroup(markers).addTo(mapInstance);
  } else if (window.L && L.heatLayer) {
    mapHeatLayer = L.heatLayer(points, {
      radius: 20,
      blur: 18,
      maxZoom: 12,
      gradient: {
        0.2: '#00f3ff',
        0.5: '#00ff41',
        0.8: '#ffcc00',
        1.0: '#ff3333',
      },
    }).addTo(mapInstance);
  }

  const bounds = L.latLngBounds(coords);
  mapInstance.fitBounds(bounds, { padding: [20, 20] });
}

// --- HISTORIAL DE INFORMES ---
async function initHistorial() {
  const btnBuscar = document.getElementById('btn-buscar-historial');
  if (!btnBuscar) return;

  btnBuscar.addEventListener('click', buscarHistorial);

  // Cargar filtros iniciales
  await loadHistorialFilters();

  // Cargar lista automáticamente
  buscarHistorial();
}

async function loadHistorialFilters() {
  try {
    const data = await fetchApi('/api/gerencia/informes/filtros');

    const selProj = document.getElementById('historial-proyecto');
    const selPlan = document.getElementById('historial-plan');
    const selCli = document.getElementById('historial-cliente');

    if (selProj && data.proyectos) {
      data.proyectos.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.nombre;
        selProj.appendChild(opt);
      });
    }

    if (selPlan && data.planes) {
      data.planes.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.descripcion;
        selPlan.appendChild(opt);
      });
    }

    if (selCli && data.clientes) {
      data.clientes.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        selCli.appendChild(opt);
      });
    }
  } catch (e) {
    console.error('Error cargando filtros historial', e);
  }
}

async function buscarHistorial() {
  const lista = document.getElementById('lista-historial');
  if (!lista) return;

  const cliente = document.getElementById('historial-cliente').value;
  const proyectoId = document.getElementById('historial-proyecto').value;
  const planId = document.getElementById('historial-plan').value;

  const params = new URLSearchParams();
  if (cliente) params.set('cliente', cliente);
  if (proyectoId) params.set('proyecto_id', proyectoId);
  if (planId) params.set('plan_id', planId);

  lista.innerHTML =
    '<tr><td colspan="6" style="text-align:center; padding:40px;">Buscando...</td></tr>';

  try {
    const data = await fetchApi(`/api/gerencia/informes/historial?${params.toString()}`);
    lista.innerHTML = '';

    if (data.length === 0) {
      lista.innerHTML =
        '<tr><td colspan="6" style="text-align:center; padding:40px; opacity:0.5;">No se encontraron reportes con estos filtros.</td></tr>';
      return;
    }

    data.forEach((r) => {
      const tr = document.createElement('tr');
      const fecha = new Date(r.fecha).toLocaleString();

      tr.innerHTML = `
        <td>${escapeHtml(fecha)}</td>
        <td><span class="type-pill">${escapeHtml(r.tipo)}</span></td>
        <td>${escapeHtml(r.cliente || '---')}</td>
        <td>
          <div style="font-weight:bold">${escapeHtml(r.proyecto)}</div>
          <div style="font-size:0.75rem; opacity:0.7">${escapeHtml(r.plan)}</div>
        </td>
        <td style="font-size:0.8rem; opacity:0.6">${escapeHtml(r.archivo)}</td>
        <td>
          <button class="btn-download-sm" onclick="window.location.href='${escapeHtml(r.url)}'">
            <i class="fas fa-download"></i> Descargar
          </button>
        </td>
      `;
      lista.appendChild(tr);
    });
  } catch (e) {
    lista.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:40px; color:var(--danger);">Error: ${e.message}</td></tr>`;
  }
}

// --- EVIDENCIA FOTOGRAFICA (Listos / Por Validar / Cuarentena) ---
let evidenciaActiva = 'listos';

function initEvidencia() {
  const tabs = document.getElementById('evidencia-tabs');
  if (!tabs) return;

  tabs.querySelectorAll('button[data-evidencia]').forEach((btn) => {
    btn.addEventListener('click', () => {
      evidenciaActiva = btn.dataset.evidencia || 'listos';
      setSegmentActive(tabs, evidenciaActiva, 'evidencia');
      loadEvidencia(evidenciaActiva);
    });
  });

  document.getElementById('btn-refresh-evidencia')?.addEventListener('click', () => {
    loadEvidencia(evidenciaActiva);
  });

  // Carga inicial
  loadEvidencia(evidenciaActiva);
}

async function loadEvidencia(tipo) {
  const container = document.getElementById('evidencia-content');
  if (!container) return;
  container.innerHTML =
    '<p class="empty-msg" style="text-align:center; padding:40px">Cargando...</p>';

  try {
    if (tipo === 'listos') {
      const asigs = await fetchApi('/api/gerencia/asignaciones/por-estado/VALIDADA');
      renderEvidenciaAsigs(container, asigs, 'VALIDADA');
    } else if (tipo === 'validar') {
      const asigs = await fetchApi('/api/gerencia/asignaciones/por-estado/COMPLETADA_TERRENO');
      renderEvidenciaAsigs(container, asigs, 'COMPLETADA_TERRENO');
    } else if (tipo === 'cuarentena') {
      const fotos = await fetchApi('/api/gerencia/excepciones/fotos');
      renderEvidenciaCuarentena(container, fotos);
    }
  } catch (e) {
    container.innerHTML = `<p class="empty-msg" style="text-align:center; padding:40px; color:var(--danger)">Error: ${e.message}</p>`;
  }
}

function renderEvidenciaAsigs(container, asigs, estado) {
  if (!asigs || asigs.length === 0) {
    container.innerHTML =
      '<p class="empty-msg" style="text-align:center; padding:40px; opacity:0.5">Limpio</p>';
    return;
  }

  const clean = (t) =>
    t
      ?.replace(
        /([\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF])/g,
        ''
      )
      .trim();

  const mp = {};
  asigs.forEach((a) => {
    const pn = clean(a.plan?.descripcion || 'Sin Plan');
    const pm = clean(a.categoria?.proyecto?.nombre_pmc || 'S/P');
    if (!mp[pn]) mp[pn] = {};
    if (!mp[pn][pm]) mp[pn][pm] = [];
    mp[pn][pm].push(a);
  });

  container.innerHTML = '';

  Object.keys(mp)
    .sort()
    .forEach((pn) => {
      const ph = document.createElement('div');
      ph.className = 'category-header color-0 collapsed';
      ph.style.cursor = 'pointer';
      ph.innerHTML = `<span>${escapeHtml(pn)}</span>`;
      container.appendChild(ph);

      const pb = document.createElement('div');
      pb.className = 'item-sublist hidden';
      container.appendChild(pb);

      ph.onclick = () => {
        ph.classList.toggle('collapsed');
        pb.classList.toggle('hidden');
      };

      Object.keys(mp[pn])
        .sort()
        .forEach((pm) => {
          const mh = document.createElement('div');
          mh.className = 'category-header color-1 collapsed';
          mh.style.marginLeft = '10px';
          mh.style.cursor = 'pointer';
          mh.innerHTML = `<span>${escapeHtml(pm)}</span>`;
          pb.appendChild(mh);

          const mb = document.createElement('div');
          mb.className = 'item-sublist hidden';
          mb.style.marginLeft = '10px';
          pb.appendChild(mb);

          mh.onclick = (e) => {
            if (e.target.tagName !== 'BUTTON') {
              mh.classList.toggle('collapsed');
              mb.classList.toggle('hidden');
            }
          };

          mp[pn][pm].forEach((a) => {
            const row = document.createElement('div');
            row.className = 'split-row';
            row.innerHTML = `<div class="col-name">${escapeHtml(a.nombre)}</div>`;
            mb.appendChild(row);

            const thumbs = document.createElement('div');
            thumbs.className = 'file-row-container';
            mb.appendChild(thumbs);

            cargarThumbsAsig(a.id, thumbs);
          });
        });
    });
}

async function cargarThumbsAsig(asigId, container) {
  try {
    // Endpoint de gerencia: incluye fotos VALIDADAS (PLAN_*) y por validar, y
    // usa thumbnails de gerencia (los de supervisor daban 403 = imagen rota).
    const files = await fetchApi(`/api/gerencia/asignacion/${asigId}/archivos`);
    if (!files.length) {
      container.innerHTML = '<p class="evi-empty">Sin fotos para esta tarea</p>';
      return;
    }
    container.innerHTML = files
      .map((f) => {
        const re = encodeURIComponent(f.ruta_archivo).replace(/'/g, '%27');
        const env = withEnvPrefix('/api/gerencia');
        return `
        <figure class="evi-foto">
          <img src="${env}/image-thumbnail/?path=${re}" loading="lazy" alt="${escapeHtml(
            f.nombre_archivo
          )}"
            onclick="window.open('${env}/image-full/?path=${re}', '_blank')" />
          <figcaption title="${escapeHtml(f.nombre_archivo)}">${escapeHtml(
            f.nombre_archivo
          )}</figcaption>
        </figure>`;
      })
      .join('');
  } catch (e) {
    container.innerHTML = '<p class="evi-empty evi-error">Error cargando fotos</p>';
  }
}

function renderEvidenciaCuarentena(container, fotos) {
  if (!fotos || fotos.length === 0) {
    container.innerHTML =
      '<p class="empty-msg" style="text-align:center; padding:40px; opacity:0.5">Limpio</p>';
    return;
  }

  const clean = (t) =>
    t
      ?.replace(
        /([\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF])/g,
        ''
      )
      .trim();

  const mp = {};
  fotos.forEach((f) => {
    const pn = clean(f.plan_descripcion || 'Sin Plan');
    const pm = clean(f.proyecto_nombre || 'S/P');
    if (!mp[pn]) mp[pn] = {};
    if (!mp[pn][pm]) mp[pn][pm] = [];
    mp[pn][pm].push(f);
  });

  container.innerHTML = '';

  Object.keys(mp)
    .sort()
    .forEach((pn) => {
      const ph = document.createElement('div');
      ph.className = 'category-header color-0 collapsed';
      ph.style.cursor = 'pointer';
      ph.innerHTML = `<span>${escapeHtml(pn)}</span>`;
      container.appendChild(ph);

      const pb = document.createElement('div');
      pb.className = 'item-sublist hidden';
      container.appendChild(pb);

      ph.onclick = () => {
        ph.classList.toggle('collapsed');
        pb.classList.toggle('hidden');
      };

      Object.keys(mp[pn])
        .sort()
        .forEach((pm) => {
          const mh = document.createElement('div');
          mh.className = 'category-header color-1 collapsed';
          mh.style.marginLeft = '10px';
          mh.style.cursor = 'pointer';
          mh.innerHTML = `<span>${escapeHtml(pm)}</span>`;
          pb.appendChild(mh);

          const mb = document.createElement('div');
          mb.className = 'item-sublist hidden';
          mb.style.marginLeft = '10px';
          pb.appendChild(mb);

          mh.onclick = (e) => {
            if (e.target.tagName !== 'BUTTON') {
              mh.classList.toggle('collapsed');
              mb.classList.toggle('hidden');
            }
          };

          const gal = document.createElement('div');
          gal.className = 'file-row-container';
          mb.appendChild(gal);
          const view = withEnvPrefix('/api/common/view');
          gal.innerHTML = mp[pn][pm]
            .map((f) => {
              const re = encodeURIComponent(f.ruta_foto_mala).replace(/'/g, '%27');
              const fn = f.ruta_foto_mala.split('/').pop();
              return `
            <figure class="evi-foto evi-cuarentena">
              <img src="${view}?path=${re}&thumb=1" loading="lazy" alt="${escapeHtml(fn)}"
                onerror="this.onerror=null;this.src='${view}?path=${re}'"
                onclick="window.open('${view}?path=${re}', '_blank')" />
              <figcaption title="${escapeHtml(f.item_nombre)} - ${escapeHtml(fn)}">${escapeHtml(
                f.item_nombre
              )}</figcaption>
            </figure>`;
            })
            .join('');
        });
    });
}
