// ==========================================================================
// PORTAL.JS (v54.0 FINAL)
// ==========================================================================

const APP_VERSION = '2026-03-11-ADMIN-DELETE-V17';
const APP_VERSION_KEY = 'portal_app_version';

// --- ENV INTERCEPTOR ---
(function () {
  const path = window.location.pathname;
  if (path.startsWith('/__env/')) {
    const mode = path.split('/')[2]; // dev or prod
    if (mode === 'dev' || mode === 'prod') {
      // Redirigir por URL (no por cookie)
      window.location.replace(mode === 'dev' ? '/dev/' : '/');
    }
  }
})();

const LOGIN_URL_APP =
  typeof window.getEnvLoginUrl === 'function'
    ? window.getEnvLoginUrl()
    : `${window.location.origin}${window.location.pathname.startsWith('/dev') ? '/dev' : ''}/`;
let authRedirecting = false;
let envSwitching = false;
let adminStatsTimer = null;
let adminStatsLoading = false;
let usersLoading = false;
let projectsLoading = false;
let portalActiveSection = null;
let adminAuxStatusCache = null;
let adminAuxStatusUpdatedAt = 0;
const ADMIN_AUX_TTL_MS = 120000;
let usersLastLoadedAt = 0;
let projectsLastLoadedAt = 0;
const ADMIN_DATA_TTL_MS = 60000;

async function clearClientStateForEnvSwitch() {
  try {
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((r) => r.unregister()));
    }
  } catch (e) {}
  try {
    if (window.caches && typeof window.caches.keys === 'function') {
      const keys = await window.caches.keys();
      await Promise.all(keys.map((k) => window.caches.delete(k)));
    }
  } catch (e) {}
}

window.switchEnvironment = function (targetEnv) {
  const env = targetEnv === 'dev' ? 'dev' : 'prod';
  if (envSwitching) {
    return;
  }
  envSwitching = true;

  const targetUrl = env === 'dev' ? '/dev/' : '/';
  const navigate = () => window.location.replace(targetUrl);

  // Fallback para evitar quedarse pegado si limpiar SW/cache demora.
  const timeoutId = setTimeout(navigate, 450);

  clearClientStateForEnvSwitch()
    .catch(() => {})
    .finally(() => {
      clearTimeout(timeoutId);
      navigate();
    });
};

function ensureAppVersion() {
  const current = localStorage.getItem(APP_VERSION_KEY);
  if (current !== APP_VERSION) {
    localStorage.setItem(APP_VERSION_KEY, APP_VERSION);
  }
  if (typeof window.cleanNavigationParams === 'function') {
    window.cleanNavigationParams();
  }
  return false;
}

function handleAuthExpired() {
  if (authRedirecting) {
    return;
  }
  authRedirecting = true;
  // Marcar la URL del login con reason=expired para que el login NO haga
  // bootstrap automatico (evita bucle si la cookie viene rota).
  const sep = LOGIN_URL_APP.includes('?') ? '&' : '?';
  window.location.href = `${LOGIN_URL_APP}${sep}reason=expired`;
}

window.handleAuthExpired = handleAuthExpired;

function isAdminRole(roleValue) {
  return (
    String(roleValue || '')
      .toUpperCase()
      .trim() === 'ADMIN'
  );
}

// --- ENVIRONMENT INDICATORS ---
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}

function renderEnvironmentIndicators() {
  // Entorno SOLO por URL (/dev). La cookie legacy causaba "mezclas" visuales.
  try {
    // Intento de limpieza por si quedo una cookie antigua compartida por .telconsulting.cl
    document.cookie = 'terreneitor_env=; path=/; domain=.telconsulting.cl; max-age=0; samesite=lax';
  } catch (e) {}
  const isDevUrl = window.location.pathname.startsWith('/dev');

  const isDev = isDevUrl;

  const container = document.querySelector('.header-actions');
  if (!container) return;

  const existing = container.querySelectorAll('.env-indicator-group');
  existing.forEach((e) => e.remove());

  const group = document.createElement('div');
  group.className = 'env-indicator-group footer-buttons-container';
  group.style.marginTop = 'auto';
  group.style.marginBottom = '10px';

  if (isDev) {
    // Estamos en DEV (sin badge de entorno)
    group.innerHTML = `
      <button type="button" class="btn-env-switch" data-target-env="prod" title="Ir a Producción">
        <i class="fas fa-rocket"></i> <span>IR A PROD</span>
      </button>
    `;
  } else {
    group.innerHTML = `
        <button type="button" class="btn-env-switch to-dev" data-target-env="dev" title="Ir a Desarrollo">
            <i class="fas fa-bug"></i> <span>IR A DEV</span>
        </button>
    `;
  }

  const profile = document.getElementById('who');
  if (profile) {
    container.insertBefore(group, profile);
  } else {
    container.appendChild(group);
  }

  const btnSwitch = group.querySelector('[data-target-env]');
  if (btnSwitch) {
    btnSwitch.addEventListener('click', () => {
      window.switchEnvironment(btnSwitch.dataset.targetEnv);
    });
  }
}

// Fallback robusto: si la inicialización del nav falla por algún motivo,
// este delegado mantiene funcional el cambio de secciones.
document.addEventListener('click', (event) => {
  const btn = event.target.closest('.side-link[data-section]');
  if (!btn) return;
  if (typeof window.showSection !== 'function') return;
  event.preventDefault();
  window.showSection(btn.dataset.section, btn);
});

function isSectionActive(sectionId) {
  return document.querySelector('.side-link.active')?.dataset.section === sectionId;
}

function updateDriveCard(driveRes) {
  const driveIcon = document.getElementById('stat-drive-icon');
  const driveVal = document.getElementById('stat-drive-val');
  const driveDetail = document.getElementById('stat-drive-detail');
  if (!driveIcon || !driveVal || !driveDetail) return;

  if (driveRes.status === 'fulfilled' && driveRes.value && driveRes.value.connected) {
    driveIcon.classList.add('connected');
    driveIcon.classList.remove('disconnected');
    driveVal.textContent = 'SI';
    driveDetail.textContent = 'Unidad compartida operativa';
  } else {
    driveIcon.classList.add('disconnected');
    driveIcon.classList.remove('connected');
    driveVal.textContent = 'NO';
    const reason =
      driveRes.status === 'fulfilled' && driveRes.value && driveRes.value.msg
        ? driveRes.value.msg
        : 'Sin conexion';
    driveDetail.textContent = reason;
  }
}

function updateTempCard(backupRes) {
  const tempIcon = document.getElementById('stat-temp-icon');
  const tempVal = document.getElementById('stat-temp-val');
  const tempDetail = document.getElementById('stat-temp-detail');
  if (!tempIcon || !tempVal || !tempDetail) return;

  let tempC = null;
  let tempStatus = 'unknown';
  let tempMessage = 'Sin lectura';

  if (backupRes.status === 'fulfilled' && backupRes.value) {
    const payload = backupRes.value;
    const temperature = payload.server_temperature || {};
    const parsed =
      typeof temperature.celsius === 'number'
        ? temperature.celsius
        : typeof payload.server_temperature_c === 'number'
          ? payload.server_temperature_c
          : null;
    tempC = Number.isFinite(parsed) ? parsed : null;
    tempStatus = temperature.status || payload.server_temperature_status || tempStatus;
    tempMessage = temperature.message || payload.server_temperature_message || tempMessage;
  }

  if (tempC !== null) {
    tempVal.textContent = `${tempC.toFixed(1)} C`;
    tempDetail.textContent = tempMessage || 'Lectura de temperatura';
    tempIcon.classList.remove('disconnected');
    tempIcon.classList.add('connected');
  } else {
    tempVal.textContent = 'N/D';
    tempDetail.textContent = tempMessage || 'Sensor no disponible';
    tempIcon.classList.remove('connected');
    if (tempStatus === 'error') {
      tempIcon.classList.add('disconnected');
    } else {
      tempIcon.classList.remove('disconnected');
    }
  }
}

async function loadAdminAuxStatus(force = false) {
  const now = Date.now();
  if (!force && adminAuxStatusCache && now - adminAuxStatusUpdatedAt < ADMIN_AUX_TTL_MS) {
    updateDriveCard(adminAuxStatusCache.driveRes);
    updateTempCard(adminAuxStatusCache.backupRes);
    return;
  }

  const [driveRes, backupRes] = await Promise.allSettled([
    fetchApi('/api/status/drive'),
    fetchApi('/api/system/backup-status'),
  ]);
  adminAuxStatusCache = { driveRes, backupRes };
  adminAuxStatusUpdatedAt = Date.now();

  updateDriveCard(driveRes);
  updateTempCard(backupRes);
}

function clearAdminStatsTimer() {
  if (adminStatsTimer) {
    clearTimeout(adminStatsTimer);
    adminStatsTimer = null;
  }
}

function scheduleAdminStatsRefresh() {
  clearAdminStatsTimer();
  adminStatsTimer = setTimeout(() => {
    if (isSectionActive('section-admin') && !document.getElementById('section-admin').hidden) {
      window.loadAdminStats(true);
    }
  }, 30000);
}

// --- UTILS ---
async function fetchApi(url, options = {}) {
  if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/api')) {
    url = '/api' + url;
  }
  // Respetar el prefijo de entorno (/dev): sin esto, estando en /dev las
  // llamadas pegaban a PROD (/api/...) y el portal rebotaba al login.
  if (typeof url === 'string' && url.startsWith('/api') && typeof withEnvPrefix === 'function') {
    url = withEnvPrefix(url);
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

// --- FUNCIONES GLOBALES ---
window.loadAdminStats = async function (force = false) {
  const _adminSec = document.getElementById('section-admin');
  if (!_adminSec || _adminSec.hidden) {
    clearAdminStatsTimer();
    return;
  }
  if (!force && !isSectionActive('section-admin')) {
    clearAdminStatsTimer();
    return;
  }
  if (adminStatsLoading) {
    return;
  }
  adminStatsLoading = true;

  try {
    const stats = await fetchApi('/api/admin/system/stats');

    const cpuBar = document.getElementById('stat-cpu-bar');
    if (cpuBar) {
      cpuBar.style.width = `${stats.cpu}%`;
      document.getElementById('stat-cpu-val').textContent = `${stats.cpu}%`;
    }

    const ramBar = document.getElementById('stat-ram-bar');
    if (ramBar) {
      ramBar.style.width = `${stats.ram}%`;
      document.getElementById('stat-ram-val').textContent =
        `${stats.ram_gb} / ${stats.ram_total_gb} GB`;
    }

    const diskBar = document.getElementById('stat-disk-bar');
    if (diskBar) {
      diskBar.style.width = `${stats.disk}%`;
      document.getElementById('stat-disk-val').textContent =
        `${stats.disk_gb} / ${stats.disk_total_gb} GB`;
    }

    const uptimeEl = document.getElementById('stat-uptime-val');
    if (uptimeEl) uptimeEl.textContent = stats.uptime;
  } catch (e) {
    console.error('Stats error', e);
  }

  // Drive y temperatura cargan en background para no bloquear el render principal.
  loadAdminAuxStatus().catch((e) => console.error('Admin aux status error', e));

  adminStatsLoading = false;
  if (!document.getElementById('section-admin').hidden && isSectionActive('section-admin')) {
    scheduleAdminStatsRefresh();
  } else {
    clearAdminStatsTimer();
  }
};

window.loadUsers = async function (force = false) {
  const container = document.getElementById('users-list');
  if (!container) return;
  const now = Date.now();
  if (!force && window.usersLoaded && now - usersLastLoadedAt < ADMIN_DATA_TTL_MS) return;
  if (usersLoading) return;
  usersLoading = true;

  try {
    const users = await fetchApi('/api/admin/users');
    if (users.length === 0) {
      container.innerHTML = '<div class="empty-state">No hay usuarios registrados.</div>';
      return;
    }

    let html = '';
    users.sort((a, b) => a.id - b.id); // Sort by ID

    users.forEach((u) => {
      // Initials
      const initials = u.name ? u.name.substring(0, 2).toUpperCase() : '??';

      // Role Colors
      let roleColor = 'kpi-blue';
      if (u.role === 'ADMIN') roleColor = 'kpi-red';
      if (u.role === 'GERENCIA') roleColor = 'kpi-purple';
      if (u.role === 'TERRENO') roleColor = 'kpi-green';

      html += `
            <div class="user-card">
                <div style="display:flex; align-items:center; gap:1rem;">
                    <div style="width:40px; height:40px; border-radius:50%; background:var(--panel-strong); color:var(--text-main); display:flex; align-items:center; justify-content:center; font-weight:bold;">
                        ${escapeHtml(initials)}
                    </div>
                    <div style="flex:1;">
                        <h4 style="margin:0; font-size:1rem;">${escapeHtml(u.name)}</h4>
                        <span style="font-size:0.8rem; color:var(--text-muted);">${escapeHtml(
                          u.email
                        )}</span>
                    </div>
                    <span class="pill ${roleColor}">${escapeHtml(u.role)}</span>
                </div>

                <div style="display:flex; justify-content:flex-end; gap:0.5rem; margin-top:0.5rem; padding-top:0.5rem; border-top:1px solid rgba(255,255,255,0.05);">
                    <button class="btn-sm" title="Editar Email" onclick="window.editUserEmail(${
                      u.id
                    }, '${escapeHtml(u.email)}')"><i class="fas fa-pen"></i></button>
                    <button class="btn-sm" title="Cambiar Clave" onclick="window.resetPass(${
                      u.id
                    }, '${escapeHtml(u.email)}')"><i class="fas fa-key"></i></button>
                    ${
                      u.id === window.currentUserId
                        ? '<button class="btn-sm btn-danger" title="No puedes eliminar tu propia cuenta" disabled><i class="fas fa-trash"></i></button>'
                        : `<button class="btn-sm btn-danger" title="Eliminar usuario" onclick='window.deleteUser(${
                            u.id
                          }, ${JSON.stringify(u.email)})'><i class="fas fa-trash"></i></button>`
                    }
                </div>
            </div>`;
    });
    container.innerHTML = html;
    window.usersLoaded = true;
    usersLastLoadedAt = Date.now();
  } catch (e) {
    container.innerHTML = `<div class="empty-state error">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    usersLoading = false;
  }
};

window.deleteUser = async function (id, email) {
  if (!confirm(`Eliminar usuario ${email}?`)) {
    return;
  }
  try {
    await fetchApi(`/api/admin/users/${id}`, { method: 'DELETE' });
    window.loadUsers(true);
  } catch (e) {
    alert(e.message);
  }
};

window.editUserEmail = async function (id, currentEmail) {
  const newEmail = prompt('Nuevo email del usuario:', currentEmail || '');
  if (newEmail === null) return;
  const clean = String(newEmail).trim().toLowerCase();
  if (!clean) return alert('Email inválido');
  if (
    clean ===
    String(currentEmail || '')
      .trim()
      .toLowerCase()
  )
    return;

  try {
    await fetchApi(`/api/admin/users/${id}`, {
      method: 'PUT',
      body: { email: clean },
    });
    window.loadUsers(true);
  } catch (e) {
    alert(e.message);
  }
};

window.resetPass = function (id, email) {
  const modal = document.getElementById('modal-admin-reset-password');
  document.getElementById('modal-admin-reset-user-id').value = id;
  document.getElementById('modal-admin-reset-user-email').textContent = email;
  document.getElementById('modal-admin-new-pass').value = '';
  document.getElementById('modal-admin-status-msg').textContent = '';
  modal.style.display = 'flex';

  const form = document.getElementById('form-admin-reset-password');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const newPass = document.getElementById('modal-admin-new-pass').value;
    const st = document.getElementById('modal-admin-status-msg');
    st.textContent = 'Procesando...';
    st.className = 'modal-status loading';

    try {
      await fetchApi(`/api/admin/users/${id}/reset-password`, {
        method: 'POST',
        body: { new_password: newPass },
      });
      st.textContent = 'Contrasena restablecida.';
      st.className = 'modal-status success';
      setTimeout(() => {
        modal.style.display = 'none';
      }, 1500);
    } catch (err) {
      st.textContent = err.message;
      st.className = 'modal-status error';
    }
  };
};

window.loadProjects = async function (force = false) {
  const container = document.getElementById('projects-list');
  if (!container) return;
  const now = Date.now();
  if (!force && window.projectsLoaded && now - projectsLastLoadedAt < ADMIN_DATA_TTL_MS) return;
  if (projectsLoading) return;
  projectsLoading = true;

  const oldTbody = document.getElementById('admin-project-list-tbody');
  if (oldTbody) console.warn('Tabla antigua detectada');

  try {
    const projects = await fetchApi('/api/admin/proyectos');
    window.projectsCache = projects;

    // Populate Client Filter
    const clients = [...new Set(projects.map((p) => p.cliente))].filter(Boolean).sort();
    const clientSelect = document.getElementById('project-filter-client');
    if (clientSelect) {
      const currentVal = clientSelect.value;
      clientSelect.innerHTML = '<option value="">Todo Cliente</option>';
      clients.forEach((c) => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        clientSelect.appendChild(opt);
      });
      if (clients.includes(currentVal)) clientSelect.value = currentVal;
    }

    // Populate Combined Filter (Zona) - Label request: "ID o Comuna" but only list Zonas
    const zonas = [...new Set(projects.map((p) => p.area || p.zona))].filter(Boolean).sort();

    const zonaSelect = document.getElementById('project-filter-zona');
    if (zonaSelect) {
      const currentVal = zonaSelect.value;
      zonaSelect.innerHTML = '<option value="">ID o Comuna</option>';

      zonas.forEach((z) => {
        const opt = document.createElement('option');
        opt.value = z;
        opt.textContent = z;
        zonaSelect.appendChild(opt);
      });

      if (currentVal) zonaSelect.value = currentVal;
    }

    window.renderProjects();
    window.projectsLoaded = true;
    projectsLastLoadedAt = Date.now();
  } catch (e) {
    container.innerHTML = `<div class="empty-state error">Error: ${escapeHtml(e.message)}</div>`;
  } finally {
    projectsLoading = false;
  }
};

// Robust Natural Sort (Alphanum Alg)
window.naturalSort = function (a, b) {
  if (!a && !b) return 0;
  if (!a) return -1;
  if (!b) return 1;

  const chunk = (t) => {
    const r = [];
    let m;
    const reg = /(\d+)|(\D+)/g;
    // Normalize to string
    const s = t.toString().toLowerCase();
    while ((m = reg.exec(s)) !== null) {
      r.push(m[1] ? parseInt(m[1], 10) : m[2]);
    }
    return r;
  };

  const aa = chunk(a);
  const bb = chunk(b);

  for (let i = 0; i < Math.max(aa.length, bb.length); i++) {
    const ac = aa[i];
    const bc = bb[i];
    if (ac === undefined) return -1;
    if (bc === undefined) return 1;
    if (ac !== bc) {
      if (typeof ac === 'number' && typeof bc === 'number') return ac - bc;
      if (typeof ac !== typeof bc) return typeof ac === 'number' ? -1 : 1;
      return ac < bc ? -1 : 1;
    }
  }
  return 0;
};

window.renderProjects = function () {
  const container = document.getElementById('projects-list');
  if (!container || !window.projectsCache) return;

  let projects = [...window.projectsCache];

  // Filters
  const fClient = document.getElementById('project-filter-client')?.value;
  const fFilter = document.getElementById('project-filter-zona')?.value; // Combined filter

  if (fClient) {
    projects = projects.filter((p) => p.cliente === fClient);
  }
  if (fFilter) {
    // Match against area, zona OR ID
    // Because IDs in select value are strings "123", we compare loosely or toString
    projects = projects.filter((p) => p.area === fFilter || p.zona === fFilter || p.id == fFilter);
  }

  // Sort
  const sortSelect = document.getElementById('project-sort-select');
  const sortMode = sortSelect ? sortSelect.value : 'status';

  projects.sort((a, b) => {
    if (sortMode === 'status') {
      const map = { ACTIVO: 1, PAUSADO: 2, CERRADO: 3 };
      const sa = map[a.estado] || 99;
      const sb = map[b.estado] || 99;
      if (sa !== sb) return sa - sb;
      return window.naturalSort(a.nombre_pmc, b.nombre_pmc);
    } else if (sortMode === 'client') {
      const ca = (a.cliente || '') + (a.zona || '');
      const cb = (b.cliente || '') + (b.zona || '');
      return ca.localeCompare(cb);
    } else {
      return window.naturalSort(a.nombre_pmc, b.nombre_pmc);
    }
  });

  if (projects.length === 0) {
    container.innerHTML =
      '<div class="empty-state">No hay proyectos que coincidan con el filtro.</div>';
    return;
  }

  let html = '';
  projects.forEach((p) => {
    const estado = p.estado || 'ACTIVO';
    const estadoClass =
      estado === 'ACTIVO' ? 'kpi-green' : estado === 'PAUSADO' ? 'kpi-orange' : 'kpi-red';
    html += `
        <div class="project-card">
            <div class="pc-header">
                <h4>${escapeHtml(p.nombre_pmc)}</h4>
                <span class="pill ${estadoClass}">${escapeHtml(estado)}</span>
            </div>
            <div class="pc-meta">
                <span>${escapeHtml(p.cliente)}</span> • <span>${escapeHtml(
                  p.area || p.zona || ''
                )}</span>
                <span style="opacity:0.6; font-size:0.8em; display:block; margin-top:4px;">ID: ${
                  p.id
                }</span>
            </div>
            <div class="pc-actions">
                <button class="btn-sm" onclick="window.openEditProject(${
                  p.id
                })"><i class="fas fa-edit"></i></button>
                <button class="btn-sm" title="Estructura" onclick="window.openStructureEditor(${
                  p.id
                })"><i class="fas fa-folder-tree"></i></button>
                ${
                  estado === 'ACTIVO'
                    ? `<button class="btn-sm" title="Pausar" onclick="window.changeProjectState(${p.id}, 'PAUSADO')"><i class="fas fa-pause"></i></button>`
                    : `<button class="btn-sm" title="Activar" onclick="window.changeProjectState(${p.id}, 'ACTIVO')"><i class="fas fa-play"></i></button>`
                }
                <button class="btn-sm btn-danger" onclick="window.deleteProject(${
                  p.id
                }, '${escapeHtml(p.nombre_pmc)}')"><i class="fas fa-trash"></i></button>
            </div>
        </div>`;
  });
  container.innerHTML = html;
};

window.openModalCreateProject = function () {
  const m = document.getElementById('modal-create-project');
  if (m) {
    m.style.display = 'flex';
    document.getElementById('cp-status-msg').textContent = '';
    document.getElementById('form-create-project').reset();
  }
};

window.createProject = async function (e) {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  const msg = document.getElementById('cp-status-msg');

  const payload = {
    cliente: document.getElementById('cp-cliente').value,
    zona: document.getElementById('cp-area').value,
    nombre: document.getElementById('cp-nombre').value,
    tipo: document.getElementById('cp-tipo').value,
  };

  try {
    btn.disabled = true;
    btn.textContent = 'Creando...';
    msg.textContent = '';

    await fetchApi('/api/admin/proyectos', {
      method: 'POST',
      body: payload,
    });

    document.getElementById('modal-create-project').style.display = 'none';
    window.loadProjects(true);
    showToast('Proyecto creado exitosamente', 'success');
  } catch (err) {
    msg.textContent = 'Error: ' + err.message;
    msg.className = 'modal-status error';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Crear Proyecto';
  }
};

window.changeProjectState = async function (id, newState) {
  // confirmation optional for state change or subtle
  try {
    await fetchApi(`/api/admin/proyectos/${id}/estado`, {
      method: 'PUT',
      body: { estado: newState },
    });
    window.loadProjects(true);
  } catch (e) {
    alert('Error: ' + e.message);
  }
};

// --- STRUCTURE EDITOR LOGIC ---
window.currentStructure = null;
window.selectedItem = null;
window.selectedPhotos = new Set();

window.openStructureEditor = async function (projectId) {
  const modal = document.getElementById('modal-structure-editor');
  if (!modal) return;

  console.log(`[UI] Opening Structure Editor for Project ID: ${projectId}`);

  // RESET UI STATE IMMEDIATELY
  window.currentProjectId = projectId;
  document.getElementById('structure-project-name').textContent = 'Cargando...';
  document.getElementById('structure-tree').innerHTML =
    '<div style="padding:1rem; color:var(--text-muted)">Iniciando...</div>';
  window.selectedItem = null;
  window.selectedPhotos.clear();
  window.renderInspector();

  modal.style.display = 'flex';

  // FETCH
  await window.refreshStructure();
};

window.agregarInterposte = async function () {
  const pid = window.currentProjectId;
  if (!pid) return;
  if (
    !confirm(
      '¿Agregar la parametrización Interposte (Previo, Excavación, Hormigón, Conexiones, Aplomado, Terminaciones) a este proyecto?'
    )
  )
    return;
  try {
    const r = await fetchApi(`/api/admin/proyectos/${pid}/agregar-interposte`, { method: 'POST' });
    const n = (r && r.items_agregados) || 0;
    const msg = n > 0 ? `Interposte agregado (${n} tareas) ✓` : 'El Interposte ya estaba en este proyecto';
    if (window.showToast) window.showToast(msg, 'success');
    else alert(msg);
    await window.refreshStructure();
  } catch (e) {
    if (window.showToast) window.showToast('No se pudo agregar Interposte: ' + e.message, 'error');
    else alert('No se pudo agregar Interposte: ' + e.message);
  }
};

window.refreshStructure = async function () {
  const pid = window.currentProjectId;
  if (!pid) return;

  try {
    const data = await fetchApi(`/api/admin/proyectos/${pid}/structure`);
    window.currentStructure = data;

    // Update UI
    document.getElementById('structure-project-name').textContent = data.name;
    window.renderTree(data.tree);

    // Reset Inspector again just in case
    window.selectedItem = null;
    window.selectedPhotos.clear();
    window.renderInspector();
  } catch (e) {
    console.error(e);
    document.getElementById('structure-tree').innerHTML =
      `<div style="color:var(--kpi-red); padding:1rem;">Error cargando estructura: ${escapeHtml(
        e.message
      )}</div>`;
    document.getElementById('structure-project-name').textContent = 'Error de Carga';
  }
};

window.renderTree = function (tree) {
  const container = document.getElementById('structure-tree');
  container.innerHTML = '';

  tree.forEach((cat) => {
    const catDiv = document.createElement('div');
    catDiv.className = 'tree-node';
    catDiv.innerHTML = `<div class="tree-cat-label">${escapeHtml(cat.name)}</div>`;

    cat.items.forEach((item) => {
      const itemDiv = document.createElement('div');
      itemDiv.className = 'tree-item';
      itemDiv.dataset.id = item.id;
      itemDiv.innerHTML = `
                <span>${escapeHtml(item.name)}</span>
                <span class="item-badge">${item.photos}</span>
            `;
      itemDiv.onclick = () => window.selectTreeItem(item.id, itemDiv);
      catDiv.appendChild(itemDiv);
    });
    container.appendChild(catDiv);
  });
};

window.selectTreeItem = function (itemId, el) {
  // UI Update
  document.querySelectorAll('.tree-item').forEach((d) => d.classList.remove('active'));
  el.classList.add('active');

  // Find Item Data
  let item = null;
  let cat = null;
  for (const c of window.currentStructure.tree) {
    const found = c.items.find((i) => i.id === itemId);
    if (found) {
      item = found;
      cat = c;
      break;
    }
  }

  if (item) {
    window.selectedItem = { ...item, categoryName: cat.name };
    window.selectedPhotos.clear();
    window.renderInspector();
  }
};

window.renderInspector = function () {
  const empty = document.getElementById('structure-inspector-empty');
  const content = document.getElementById('structure-inspector');

  if (!window.selectedItem) {
    empty.hidden = false;
    content.hidden = true;
    return;
  }

  empty.hidden = true;
  content.hidden = false;

  document.getElementById('inspector-title').textContent =
    `${window.selectedItem.categoryName} / ${window.selectedItem.name}`;
  document.getElementById('inspector-photo-count').textContent = window.selectedItem.photos;

  // Reset Tabs
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
  document.querySelector('[data-tab="photos"]').classList.add('active');
  document.querySelectorAll('.inspector-content').forEach((c) => (c.style.display = 'none'));
  document.getElementById('tab-photos').style.display = 'block';

  window.renderPhotosGrid();
  window.updateSelectionBar();
};

window.renderPhotosGrid = async function () {
  const grid = document.getElementById('inspector-photos-grid');
  grid.innerHTML = '';

  // Now window.selectedItem should have .files array
  const files = window.selectedItem.files || [];
  console.log(`Rendering photos for ${window.selectedItem.name}. Count: ${files.length}`);

  if (files.length === 0) {
    grid.innerHTML =
      '<div style="color:var(--text-muted); padding:1rem; text-align:center;">Sin fotos</div>';
    return;
  }

  files.forEach((f) => {
    const div = document.createElement('div');
    div.className = 'photo-item';
    div.title = f; // Tooltip with full path
    if (window.selectedPhotos.has(f)) {
      div.classList.add('selected');
    }
    div.onclick = () => window.togglePhotoSelection(f, div);

    // Display just the filename for brevity, but allow full path inspection
    // If path is deep, maybe showing just the filename is misleading if duplicates exist?
    // Let's show the last part of path if it's long?
    // The user complained about "viven en carpetas mas abajo".
    // Let's show the filename AND a small subtext with the folder if it's nested

    const parts = f.split('/');
    const filename = parts.pop();
    const folder = parts.join('/');

    // Construct absolute path for the view endpoint
    // item.path is absolute path of the item folder
    const fullPath = `${window.selectedItem.path}/${f}`;
    const encodedPath = encodeURIComponent(fullPath);
    const timestamp = new Date().getTime();
    const viewUrl = `/api/common/view?path=${encodedPath}&thumb=true&t=${timestamp}`;

    console.log(`[Photo] Loading: ${filename} from ${viewUrl}`);

    div.innerHTML = `
            <div class="photo-thumbnail">
                <img src="${viewUrl}" loading="lazy" alt="${escapeHtml(
                  filename
                )}" onerror="console.error('Failed to load: ${viewUrl}'); this.style.display='none'; this.nextElementSibling.style.display='block'">
                <div class="photo-icon-fallback">📷</div>
            </div>
            <div class="photo-info">
                <div class="photo-name" title="${escapeHtml(filename)}">${escapeHtml(
                  filename
                )}</div>
                ${
                  folder
                    ? `<div class="photo-folder" title="${escapeHtml(folder)}">${escapeHtml(
                        folder
                      )}</div>`
                    : ''
                }
            </div>
        `;
    grid.appendChild(div);
  });
};

window.togglePhotoSelection = function (filename, el) {
  if (window.selectedPhotos.has(filename)) {
    window.selectedPhotos.delete(filename);
    el.classList.remove('selected');
  } else {
    window.selectedPhotos.add(filename);
    el.classList.add('selected');
  }
  window.updateSelectionBar();
};

window.updateSelectionBar = function () {
  const bar = document.getElementById('selection-bar');
  const count = window.selectedPhotos.size;

  document.getElementById('sel-count').textContent = count;
  bar.hidden = count === 0;
};

window.switchToMoveTab = function () {
  // Populate select
  const select = document.getElementById('move-target-select');
  select.innerHTML = '';

  // Flatten tree to get all items EXCEPT current
  const currentId = window.selectedItem.id;

  if (window.currentStructure && window.currentStructure.tree) {
    window.currentStructure.tree.forEach((cat) => {
      if (cat.items.length === 0) return;
      const grp = document.createElement('optgroup');
      grp.label = cat.name;

      cat.items.forEach((item) => {
        if (item.id === currentId) return; // Skip self
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = item.name;
        grp.appendChild(opt);
      });

      if (grp.children.length > 0) select.appendChild(grp);
    });
  }

  // Switch Tab
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
  document.querySelector('[data-tab="move"]').classList.add('active');

  document.querySelectorAll('.inspector-content').forEach((c) => (c.style.display = 'none'));
  document.getElementById('tab-move').style.display = 'block';
};

window.cancelMove = function () {
  document.querySelector('[data-tab="photos"]').click();
};

window.executeMovePhotos = async function () {
  const destId = document.getElementById('move-target-select').value;
  if (!destId) {
    showToast('Selecciona un destino', 'warning');
    return;
  }

  if (!confirm(`¿Mover ${window.selectedPhotos.size} fotos?`)) return;

  const payload = {
    src_item_id: window.selectedItem.id,
    dest_item_id: parseInt(destId),
    photos: Array.from(window.selectedPhotos),
  };

  try {
    const res = await fetchApi(`/api/admin/items/move-photos`, {
      method: 'POST',
      body: payload,
    });

    // Show result
    let msg = `Movidas: ${res.moved}`;
    if (res.errors && res.errors.length > 0) {
      msg += `\nErrores:\n${res.errors.join('\n')}`;
    }
    showToast(msg, res.errors && res.errors.length ? 'warning' : 'success');

    // Refresh
    await window.refreshStructure();
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
};

// Tabs Logic
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.onclick = () => {
      // UI Toggle
      document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      const tabName = btn.dataset.tab;
      document.querySelectorAll('.inspector-content').forEach((c) => (c.style.display = 'none'));
      document.getElementById(`tab-${tabName}`).style.display = 'block';
    };
  });
});

// ... Placeholder for rest ...
window.promptAddItem = async function () {
  if (!window.currentProjectId) return;
  const cat = prompt('Clase/Categoria (Ej: GENERAL, OBRA_GRUESA):');
  if (!cat) return;
  const name = prompt('Nombre del Item (Ej: Losa, Muro):');
  if (!name) return;

  try {
    await fetchApi(`/api/admin/proyectos/${window.currentProjectId}/items`, {
      method: 'POST',
      body: { category: cat, item: name },
    });
    window.refreshStructure();
  } catch (e) {
    alert(e.message);
  }
};

window.deleteCurrentItem = async function () {
  if (!window.selectedItem) return;
  if (!confirm(`Eliminar item ${window.selectedItem.name}? Se moverá a la papelera.`)) return;

  try {
    await fetchApi(`/api/admin/items/${window.selectedItem.id}`, { method: 'DELETE' });
    window.refreshStructure();
  } catch (e) {
    showToast(e.message, 'error');
  }
};

// Add button to open editor in main list
window.openStructureEditorBtn = function (id) {
  // Add logic to UI
  window.openStructureEditor(id);
};

window.deleteProject = async function (id, nombre) {
  if (
    !confirm(
      `PELIGRO: ¿Estas seguro de eliminar el proyecto ${nombre}?\nEsta accion borrara el registro y movera los archivos a la papelera.`
    )
  ) {
    return;
  }
  try {
    await fetchApi(`/api/admin/proyectos/${id}`, { method: 'DELETE' });
    window.loadProjects(true);
  } catch (e) {
    showToast('Error: ' + e.message, 'error');
  }
};

window.openEditProject = function (id) {
  const p = window.projectsCache.find((x) => x.id === id);
  if (!p) return;

  document.getElementById('modal-project-id').value = p.id;
  document.getElementById('modal-project-nombre').value = p.nombre_pmc.replace(
    /^(PMC|OBRA|SATLINK|DOMICILIO|LEVANTAMIENTO|INTERPOSTE)_/,
    ''
  ); // Attempt to strip prefix for editing friendly name if desired, or show full
  // actually, let's show user friendly raw parts if we can, but backend stores normalized.
  // Simplify: just show current values.
  document.getElementById('modal-project-nombre').value = p.nombre_pmc;
  document.getElementById('modal-project-cliente').value = p.cliente;
  document.getElementById('modal-project-zona').value = p.area || p.zona;

  document.getElementById('modal-admin-edit-project').style.display = 'flex';
  document.getElementById('modal-project-status-msg').textContent = '';
};

window.updateProject = async function (e) {
  e.preventDefault();
  const id = document.getElementById('modal-project-id').value;
  const btn = e.target.querySelector('button');
  const msg = document.getElementById('modal-project-status-msg');

  const payload = {
    nombre: document.getElementById('modal-project-nombre').value,
    cliente: document.getElementById('modal-project-cliente').value,
    zona: document.getElementById('modal-project-zona').value,
  };

  try {
    btn.disabled = true;
    msg.textContent = 'Guardando...';
    await fetchApi(`/api/admin/proyectos/${id}`, {
      method: 'PUT',
      body: payload,
    });
    document.getElementById('modal-admin-edit-project').style.display = 'none';
    window.loadProjects(true);
  } catch (err) {
    msg.textContent = err.message;
    msg.className = 'modal-status error';
  } finally {
    btn.disabled = false;
    msg.textContent = '';
  }
};

window.runScript = async function (scriptId) {
  const statusSpan = document.getElementById(`status-${scriptId}`);
  if (statusSpan) {
    statusSpan.textContent = 'Ejecutando...';
  }

  try {
    const res = await fetchApi(`/api/admin/trigger/${scriptId}`, { method: 'POST' });
    if (statusSpan) {
      statusSpan.textContent = 'OK';
      statusSpan.style.color = '#00ff41';
      setTimeout(() => {
        statusSpan.textContent = '';
      }, 5000);
    }
    showToast(res.message || res.detail || 'Script ejecutado', 'info');
  } catch (e) {
    if (statusSpan) {
      statusSpan.textContent = 'Error';
      statusSpan.style.color = 'red';
    }
    alert(e.message);
  }
};

window.createUser = async function (e) {
  e.preventDefault();
  const btn = document.getElementById('btn-admin-create-user');
  const status = document.getElementById('admin-create-status-msg');

  const email = document.getElementById('admin-new-email').value;
  const name = document.getElementById('admin-new-name').value;
  const password = document.getElementById('admin-new-pass').value;
  const role = document.getElementById('admin-new-role').value;

  if (!role) {
    showToast('Seleccione un rol', 'warning');
    return;
  }

  btn.disabled = true;
  status.textContent = 'Creando...';
  status.className = 'modal-status loading';

  try {
    await fetchApi('/api/admin/users', {
      method: 'POST',
      body: { email, name, password, role },
    });
    status.textContent = 'Usuario creado exitosamente.';
    status.className = 'modal-status success';
    document.getElementById('form-create-user').reset();
    setTimeout(() => (status.textContent = ''), 3000);
    window.loadUsers(true); // Recargar tabla
  } catch (error) {
    status.textContent = error.message;
    status.className = 'modal-status error';
  } finally {
    btn.disabled = false;
  }
};

// --- CLIENTES ---
window.loadClientes = async function () {
  const container = document.getElementById('clientes-list');
  if (!container) return;
  try {
    const clientes = await fetchApi('/api/clientes');
    if (!Array.isArray(clientes) || clientes.length === 0) {
      container.innerHTML = '<div class="empty-state">No hay clientes registrados.</div>';
      return;
    }
    let html = '';
    clientes.forEach((c) => {
      html += `
        <div class="project-card">
            <div class="pc-header">
                <h4>${escapeHtml(c.nombre)}</h4>
            </div>
            <div class="pc-meta">
                <span style="opacity:0.6; font-size:0.8em;">ID: ${c.id}</span>
            </div>
            <div class="pc-actions">
                <button class="btn-sm" title="Editar" onclick='window.editarCliente(${c.id}, ${JSON.stringify(
                  c.nombre
                )})'><i class="fas fa-edit"></i></button>
                <button class="btn-sm btn-danger" title="Borrar" onclick='window.borrarCliente(${c.id}, ${JSON.stringify(
                  c.nombre
                )})'><i class="fas fa-trash"></i></button>
            </div>
        </div>`;
    });
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<div class="empty-state error">Error: ${escapeHtml(e.message)}</div>`;
    showToast(e.message, 'error');
  }
};

window.crearClientePrompt = async function () {
  const n = prompt('Nombre del cliente:');
  if (!n || !n.trim()) return;
  try {
    await fetchApi('/api/clientes', { method: 'POST', body: { nombre: n.trim() } });
    showToast('Cliente creado', 'success');
    await window.loadClientes();
  } catch (e) {
    showToast(e.message, 'error');
  }
};

window.editarCliente = async function (id, nombre) {
  const n = prompt('Nuevo nombre:', nombre);
  if (!n || !n.trim()) return;
  try {
    await fetchApi('/api/clientes/' + id, { method: 'PATCH', body: { nombre: n.trim() } });
    showToast('Cliente actualizado', 'success');
    await window.loadClientes();
  } catch (e) {
    showToast(e.message, 'error');
  }
};

window.borrarCliente = async function (id, nombre) {
  if (!confirm('¿Borrar el cliente ' + nombre + '? (no afecta proyectos ni planes ya creados)'))
    return;
  try {
    await fetchApi('/api/clientes/' + id, { method: 'DELETE' });
    showToast('Cliente borrado', 'success');
    await window.loadClientes();
  } catch (e) {
    showToast(e.message, 'error');
  }
};

window.sincronizarClientes = async function () {
  try {
    const r = await fetchApi('/api/clientes/sincronizar', { method: 'POST' });
    showToast('Sincronizado: ' + (r.agregados || 0) + ' clientes nuevos', 'success');
    await window.loadClientes();
  } catch (e) {
    showToast(e.message, 'error');
  }
};

window.showTab = function (tabId, btn) {
  document.querySelectorAll('.tab-link').forEach((t) => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach((c) => c.classList.remove('active'));
  btn.classList.add('active');
  const target = document.getElementById(tabId);
  if (target) {
    target.classList.add('active');
    if (tabId === 'tab-agregar') window.loadUsers();
    if (tabId === 'tab-proyectos') window.loadProjects();
  }
};

window.isAdmin = false;
window.currentUserId = null;
window.usersLoaded = false;
window.projectsLoaded = false;

window.showSection = function (sectionId, btn) {
  const targetId = sectionId || (btn && btn.dataset.section);
  if (!targetId) {
    return;
  }
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  // Las secciones admin solo son accesibles para admin.
  if (target.classList.contains('admin-section') && !window.isAdmin) {
    return;
  }

  // Estilo gerencia: NO se oculta nada; la barra lateral solo hace scroll a la
  // sección elegida (todas las secciones viven apiladas en una sola página).
  document.querySelectorAll('.side-link').forEach((link) => link.classList.remove('active'));
  const activeBtn = btn || document.querySelector(`.side-link[data-section="${targetId}"]`);
  if (activeBtn) activeBtn.classList.add('active');
  portalActiveSection = targetId;

  if (targetId === 'section-projects') {
    window.loadProjects();
  }
  if (targetId === 'section-clientes') {
    window.loadClientes();
  }

  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

function initPortalNav() {
  const navButtons = Array.from(document.querySelectorAll('.side-link[data-section]')).filter(
    (btn) => !btn.hidden
  );
  if (!navButtons.length) {
    return;
  }

  const sections = navButtons
    .map((btn) => {
      const targetId = btn.dataset.section;
      const target = targetId ? document.getElementById(targetId) : null;
      if (!target || target.hidden) {
        return null;
      }
      return { id: targetId, el: target };
    })
    .filter(Boolean);

  const buttons = navButtons.slice();

  const setActive = (sectionId) => {
    buttons.forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.section === sectionId);
    });
  };

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      window.showSection(btn.dataset.section, btn);
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
  let lastScrollSection = null;

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
      if (getSectionTop(section.el) <= anchor) {
        current = section;
      }
    });
    if (current && current.id) {
      if (current.id === lastScrollSection) {
        return;
      }
      lastScrollSection = current.id;
      portalActiveSection = current.id;
      setActive(current.id);
      if (current.id === 'section-projects') {
        window.loadProjects();
      }
      if (current.id === 'section-clientes') {
        window.loadClientes();
      }
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

// --- INIT ---
document.addEventListener('DOMContentLoaded', () => {
  if (ensureAppVersion()) {
    return;
  }

  fetchApi('/auth/whoami')
    .then((u) => {
      if (u.logged) {
        document.getElementById('who').textContent = `${u.name} (${u.role})`;
        window.isAdmin = isAdminRole(u.role);
        window.currentUserId = Number.isFinite(Number(u.user_id)) ? Number(u.user_id) : null;
        const isDevPath = window.location.pathname.startsWith('/dev');
        if (isDevPath) {
          document.body.classList.add('dev-mode');
        }
        renderEnvironmentIndicators();
        document.querySelectorAll('.side-link[data-admin="true"]').forEach((btn) => {
          btn.hidden = !window.isAdmin;
        });
        // Estilo gerencia: para admin, mostrar TODAS las secciones apiladas en
        // una sola página (la barra lateral solo hace scroll a cada una).
        document.querySelectorAll('.section-block.admin-section').forEach((sec) => {
          sec.hidden = !window.isAdmin;
        });
        initPortalNav();

        if (window.isAdmin) {
          // Proyectos es la seccion por defecto; Clientes carga al pie.
          window.loadProjects(true);
          setTimeout(() => {
            window.loadClientes();
          }, 350);
        }
      } else {
        handleAuthExpired();
      }
    })
    .catch(() => handleAuthExpired());

  if (typeof initLogout === 'function') {
    initLogout();
  }
  if (typeof initModal === 'function') {
    initModal();
  }

  const formCreate = document.getElementById('form-create-user');
  if (formCreate) {
    formCreate.addEventListener('submit', window.createUser);
  }

  const formProject = document.getElementById('form-create-project');
  if (formProject) {
    formProject.addEventListener('submit', window.createProject);
  }
  const formEditProject = document.getElementById('form-admin-edit-project');
  if (formEditProject) {
    formEditProject.addEventListener('submit', window.updateProject);
  }
  const btnSyncProjects = document.getElementById('btn-admin-sync-projects');
  if (btnSyncProjects) {
    btnSyncProjects.addEventListener('click', window.syncProjects);
  }

  const scriptRunner = document.querySelector('.script-runner');
  if (scriptRunner) {
    scriptRunner.addEventListener('click', (e) => {
      if (e.target.tagName === 'BUTTON' && e.target.dataset.action === 'run-script') {
        window.runScript(e.target.dataset.script);
      }
    });
  }

  document.querySelectorAll('[data-project-filter]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      window.openProjectFilterPopover(btn);
    });
  });

  const toggleBtn = document.getElementById('sidebar-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      document.body.classList.toggle('sidebar-collapsed');
    });
  }

  // Init Mobile State
  if (window.innerWidth <= 768) {
    document.body.classList.add('sidebar-collapsed');
  }

  // PWA Service Worker Registration
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register(withEnvPrefix('/service-worker.js'), { scope: withEnvPrefix('/') })
        .then((reg) => {
          console.log('SW Registered:', reg.scope);
        })
        .catch((err) => {
          console.log('SW Fail:', err);
        });
    });
  }
});

// --- FORCE REFRESH ON MODULE LINKS ---
document.addEventListener('DOMContentLoaded', () => {
  const cards = document.querySelectorAll('.card');
  cards.forEach((card) => {
    card.addEventListener('click', (e) => {
      // Solo si es navegacion interna/subdominio
      if (card.href && card.href.includes('telconsulting.cl')) {
        e.preventDefault();
        const url = new URL(card.href);
        window.location.href = url.toString();
      }
    });
  });
});
