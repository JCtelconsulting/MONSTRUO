// ==========================================================================
// TERRENO.JS (v16.1 PROD - NESTED ACCORDIONS)
// ==========================================================================

// --- 1. GLOBALS ---
window.g_tareas = [];
window.g_taskUploadId = null;
window.g_filesToUpload = [];
window.g_selectedFileIndex = 0;
window.g_uploadQueue = [];
window.g_uploadActive = false;
window.g_uploadHideTimer = null;

const APP_VERSION = '2026-03-05.V16.2-Simple';

const MANDATORY_STEPS = [];

const MANDATORY_HOUR_LIMIT = 11;
const DEMO_PARAM = 'demo';
const DEMO_SKIP_KEY = 'terreno_demo_skip_mandatory';
const APP_VERSION_KEY = 'terreno_app_version';

let authRedirecting = false;

const TASK_HINTS = [
  {
    match: /PUNTAS TIPO TIBURON|SERPENTINA|PORTON/i,
    hint: 'Foto general de instalacion y detalle de fijaciones.',
  },
  { match: /SOLERILLA/i, hint: 'Indica tramo y nivel. Foto general y detalle de alineacion.' },
  {
    match: /HORMIGON|HORMIGONADO|CONCRETO|VACIADO/i,
    hint: 'Indica m3, elemento y hora de vaciado. Foto del vaciado y terminacion.',
  },
  {
    match: /ENFIERRAD|FIERRO|ACERO|MALLA/i,
    hint: 'Indica diametro, separacion y ubicacion. Foto general y detalle de amarras.',
  },
  {
    match: /EXCAVACION|EXCAVACIONES/i,
    hint: 'Indica profundidad, ancho y largo (m). Foto general y detalle de cota.',
  },
  {
    match: /DEMOLICION|RETIRO/i,
    hint: 'Indica area intervenida y volumen retirado. Foto antes y despues.',
  },
  { match: /MOVIMIENTO DE TIERRA/i, hint: 'Indica zona y volumen movido. Foto general y detalle.' },
  {
    match: /COMPACTACION|COMPACTAR/i,
    hint: 'Indica area, equipo usado y % objetivo. Foto del equipo en uso.',
  },
  { match: /RELLENO/i, hint: 'Indica material, capas y espesor (cm). Foto general y detalle.' },
  { match: /NIVELACION|NIVEL/i, hint: 'Indica cota o nivel. Foto con instrumento de medicion.' },
  {
    match: /ELECTRICIDAD|TABLERO|CABLE|CANALIZACION/i,
    hint: 'Indica zona/circuito y estado. Foto de canalizacion y conexiones.',
  },
  {
    match: /SANITARIO|BANOS|AGUA|DESAGUE|ALCANTARILLADO/i,
    hint: 'Indica ubicacion y estado. Foto general y detalle de conexiones.',
  },
  {
    match: /MATERIALES|RECEPCION|GUIAS|FACTURAS/i,
    hint: 'Foto de materiales recibidos y guia/factura visible.',
  },
  {
    match: /INSPECCION|CONTROL/i,
    hint: 'Foto del area inspeccionada con detalle del punto critico.',
  },
  { match: /ACOPIO|ORDENAMIENTO/i, hint: 'Foto del acopio ordenado y protegido. Indica zona.' },
  { match: /SEGURIDAD|EPP|PLAN Y EPP/i, hint: 'Foto de EPP usado y checklist de seguridad.' },
  { match: /LIMPIEZA|ASEO/i, hint: 'Foto del area limpia y residuos retirados.' },
  { match: /SENAL|ETIQUETADO/i, hint: 'Foto de senaletica o etiqueta instalada y visible.' },
  { match: /MOVILIZACION/i, hint: 'Foto del equipo y carga antes del traslado.' },
];

function isDemoMode() {
  return new URLSearchParams(window.location.search).has(DEMO_PARAM);
}

function isDemoSkipActive() {
  return isDemoMode() && localStorage.getItem(DEMO_SKIP_KEY) === '1';
}

function setDemoSkipActive(enabled) {
  if (!isDemoMode()) {
    return;
  }
  if (enabled) {
    localStorage.setItem(DEMO_SKIP_KEY, '1');
  } else {
    localStorage.removeItem(DEMO_SKIP_KEY);
  }
}

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

  // NO_BOUNCE_AUTH_EXPIRED: si ya hay sesión (whoami true), no rebotar al login central
  if (window.__lastWhoamiLogged === true) {
    try {
      if (window.showToast)
        window.showToast('Sesión OK. Acceso restringido o error de API en Terreno.', 'warning');
    } catch (e) {}
    authRedirecting = false;
    return;
  }

  // ADMIN: no rebotar al login central por errores de permisos en módulo Terreno
  if (String(window.__meRole || '').includes('ADMIN')) {
    try {
      if (window.showToast)
        window.showToast('Acceso restringido en módulo Terreno (ADMIN).', 'warning');
    } catch (e) {}
    authRedirecting = false;
    return;
  }

  // Si llegamos aquí, NO hay sesión validada o no es ADMIN, se procede con la redirección.
  try {
    Loader.show('Sesion expirada. Reingresando...');
  } catch (e) {}
  setTimeout(() => {
    const targetLogin =
      typeof window.getEnvLoginUrl === 'function'
        ? window.getEnvLoginUrl()
        : `${window.location.origin}${window.location.pathname.startsWith('/dev') ? '/dev' : ''}/`;
    window.location.href = targetLogin;
  }, 1200);
}

window.handleAuthExpired = handleAuthExpired;

// --- 2. UTILS ---
const Loader = {
  overlay: null,
  init() {
    this.overlay = document.getElementById('global-loader');
  },
  show(t = 'Procesando...') {
    if (!this.overlay) {
      this.init();
    }
    if (this.overlay) {
      this.overlay.querySelector('h3').textContent = t;
      this.overlay.style.display = 'flex';
    }
  },
  hide() {
    if (!this.overlay) {
      this.init();
    }
    if (this.overlay) {
      this.overlay.style.display = 'none';
    }
  },
};

async function fetchApi(url, options = {}) {
  const IS_DEV = window.location.pathname.startsWith('/dev');
  const API_BASE = IS_DEV ? '/dev' : '';
  let finalUrl = url;

  if (typeof url === 'string' && url.startsWith('/')) {
    if (url.startsWith('/auth/')) {
      // El endpoint real es /api/auth/... ; antes mapeaba a /dev/auth/whoami
      // (sin /api) => 404 => handleAuthExpired => rebote a login en terreno.
      finalUrl = `${API_BASE}/api${url}`;
    } else if (url.startsWith('/api/')) {
      finalUrl = `${API_BASE}${url}`;
    }
  }

  options.credentials = 'include';
  options.headers = options.headers || {};
  if (options.body && typeof options.body !== 'string' && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const resp = await fetch(finalUrl, options);
  // Solo 401 (no autenticado) desloguea; 403 (sin permiso) NO debe rebotar
  // al login: cae al manejo de error normal para que la seccion lo muestre.
  if (resp.status === 401) {
    if (typeof window.handleAuthExpired === 'function') {
      window.handleAuthExpired();
    }
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

window.naturalSort = function (a, b) {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
};

function getMandatoryStep(taskName) {
  if (!taskName) {
    return null;
  }
  return MANDATORY_STEPS.find((step) => step.match.test(taskName)) || null;
}

function isMandatoryTask(tarea) {
  if (!tarea || !tarea.item || !tarea.item.nombre) {
    return false;
  }
  return Boolean(getMandatoryStep(tarea.item.nombre));
}

function isMandatoryGateTask(tarea) {
  const step = getMandatoryStep(tarea?.item?.nombre);
  return Boolean(step && step.gate);
}

function isMandatoryComplete(estado) {
  return ['COMPLETADA_TERRENO', 'PENDIENTE_EXIF', 'VALIDADA'].includes(estado);
}

window.getTaskHint = function (taskName) {
  const step = getMandatoryStep(taskName);
  if (step && step.hint) {
    return step.hint;
  }
  const name = (taskName || '').toUpperCase();
  for (const rule of TASK_HINTS) {
    if (rule.match.test(name)) {
      return rule.hint;
    }
  }
  return 'Sube fotos claras del avance: una general y un detalle.';
};

function updateUploadStatus(text, percent, state) {
  const box = document.getElementById('upload-queue-status');
  if (!box) {
    return;
  }
  const msg = document.getElementById('upload-queue-text');
  const bar = document.getElementById('upload-progress-bar');
  if (msg) {
    msg.textContent = text || '';
  }
  if (bar) {
    const safe = Math.max(0, Math.min(100, percent || 0));
    bar.style.width = `${safe}%`;
  }
  box.classList.remove('error', 'success');
  if (state === 'error') {
    box.classList.add('error');
  } else if (state === 'success') {
    box.classList.add('success');
  }
  box.style.display = 'block';
  if (window.g_uploadHideTimer) {
    clearTimeout(window.g_uploadHideTimer);
    window.g_uploadHideTimer = null;
  }
}

function hideUploadStatus(delayMs = 2000) {
  const box = document.getElementById('upload-queue-status');
  if (!box) {
    return;
  }
  if (window.g_uploadHideTimer) {
    clearTimeout(window.g_uploadHideTimer);
  }
  window.g_uploadHideTimer = setTimeout(() => {
    box.style.display = 'none';
  }, delayMs);
}

function uploadWithProgress(url, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    // Prefijo de entorno: sin esto el XHR pegaba a PROD (/api/...) en /dev => 401.
    const ENVP = window.location.pathname.startsWith('/dev') ? '/dev' : '';
    const finalUrl = typeof url === 'string' && url.startsWith('/api') ? `${ENVP}${url}` : url;
    xhr.open('POST', finalUrl, true);
    xhr.withCredentials = true;
    xhr.upload.onprogress = (evt) => {
      if (!evt.lengthComputable) {
        return;
      }
      const percent = Math.round((evt.loaded / evt.total) * 100);
      onProgress(percent);
    };
    xhr.onerror = () => reject(new Error('Error de red'));
    xhr.onload = () => {
      let data = {};
      try {
        data = JSON.parse(xhr.responseText || '{}');
      } catch (e) {}
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
      } else if (xhr.status === 413) {
        reject(new Error('ERROR: Fotos muy pesadas.'));
      } else {
        reject(new Error(data.detail || `Error ${xhr.status}`));
      }
    };
    xhr.send(formData);
  });
}

function processNextUpload() {
  if (window.g_uploadActive) {
    return;
  }
  const job = window.g_uploadQueue.shift();
  if (!job) {
    hideUploadStatus(1500);
    return;
  }
  window.g_uploadActive = true;
  const queueLeft = window.g_uploadQueue.length;
  updateUploadStatus(`Subiendo 0%${queueLeft ? ` | En cola ${queueLeft}` : ''}`, 0, 'loading');

  uploadWithProgress(
    `/api/asignaciones/${job.taskId}/upload-multiple/`,
    job.formData,
    (percent) => {
      const left = window.g_uploadQueue.length;
      updateUploadStatus(
        `Subiendo ${percent}%${left ? ` | En cola ${left}` : ''}`,
        percent,
        'loading'
      );
    }
  )
    .then((res) => {
      const left = window.g_uploadQueue.length;
      const msg = res && res.message ? res.message : `En cola ${job.filesCount} archivos.`;
      updateUploadStatus(`${msg}${left ? ` | En cola ${left}` : ''}`, 100, 'success');

      // OFFLINE: Cleanup
      if (window.OfflineStore && job.dbIds && job.dbIds.length > 0) {
        job.dbIds.forEach((id) => window.OfflineStore.remove(id).catch((e) => console.log(e)));
      }

      window.cargarTareas();
      if (window.Guia && window.Guia.activo) {
        window.Guia.fotoSubida(job.taskId);
      }
    })
    .catch((error) => {
      updateUploadStatus(`Error: ${error.message}`, 0, 'error');
      alert(error.message);
    })
    .finally(() => {
      window.g_uploadActive = false;
      if (window.g_uploadQueue.length) {
        setTimeout(processNextUpload, 200);
      } else {
        hideUploadStatus(2500);
      }
    });
}

// --- 3. CORE ---
window.cargarTareas = async function () {
  const c1 = document.getElementById('list-pendientes');
  if (c1) {
    c1.innerHTML = '<p style="text-align:center; color:#666; padding:20px;">Cargando...</p>';
  }
  try {
    const data = await fetchApi('/api/planes-trabajo/activos/');
    window.g_tareas = data;
    const planesMap = {};
    data.forEach((t) => {
      planesMap[t.plan.id] = t.plan.descripcion;
    });
    const sel = document.getElementById('extra-plan-select');
    if (sel) {
      sel.innerHTML = '';
      Object.keys(planesMap).forEach((id) => {
        const o = document.createElement('option');
        o.value = id;
        o.textContent = planesMap[id];
        sel.appendChild(o);
      });
    }
    window.renderAllLists();
  } catch (error) {
    if (c1) {
      c1.innerHTML = `<p style="color:red;text-align:center;">Error: ${escapeHtml(
        error.message
      )}</p>`;
    }
  }
};

// --- Auto-asignación: tareas disponibles para tomar ---
window.cargarDisponibles = async function () {
  const cont = document.getElementById('list-disponibles');
  if (!cont) return;
  cont.innerHTML = '<p style="text-align:center; color:#666; padding:20px;">Cargando...</p>';
  try {
    const data = await fetchApi('/api/asignaciones/disponibles/');
    if (!data.length) {
      cont.innerHTML =
        '<p style="text-align:center; color:#666; padding:30px;">No hay tareas disponibles para tomar.</p>';
      return;
    }
    cont.innerHTML = '';
    data.forEach((t) => {
      const proy = t.item?.categoria?.proyecto?.nombre_pmc || '';
      const card = document.createElement('div');
      card.className = 'task-card status-asignada';
      card.innerHTML = `
        <div class="task-header">
          <div class="task-title">${escapeHtml(t.item.nombre)}</div>
          <span class="task-status-badge badge-asignada">DISPONIBLE</span>
        </div>
        <div class="task-hint-inline">${escapeHtml(proy)} · ${escapeHtml(
          t.plan?.descripcion || ''
        )}</div>
        <div class="task-actions">
          <button class="btn-upload" data-tomar="${
            t.id
          }"><i class="fas fa-hand-pointer"></i> TOMAR TAREA</button>
        </div>`;
      card.querySelector('[data-tomar]').addEventListener('click', () => window.tomarTarea(t.id));
      cont.appendChild(card);
    });
  } catch (error) {
    cont.innerHTML = `<p style="color:red;text-align:center;">Error: ${escapeHtml(
      error.message
    )}</p>`;
  }
};

window.tomarTarea = async function (asignacionId) {
  try {
    await fetchApi(`/api/asignaciones/${asignacionId}/tomar`, { method: 'POST' });
    if (window.showToast) window.showToast('Tarea tomada. La verás en Pendientes.', 'success');
    await window.cargarDisponibles(); // refresca el pool
    await window.cargarTareas(); // ahora aparece en mis tareas
  } catch (error) {
    if (window.showToast) window.showToast('No se pudo tomar: ' + error.message, 'error');
    else alert('No se pudo tomar la tarea: ' + error.message);
  }
};

// ==========================================================================
// MODO GUIADO: el técnico no necesita saber la estructura; la app lo lleva
// paso a paso (abre -> "¿qué quieres hacer?" -> elige/toma -> guía tarea x tarea).
// ==========================================================================
// Estados "trabajables" por el tecnico (se listan en el plan; las con fotos
// quedan para poder agregar mas). "Por subir de verdad" = ASIGNADA/RECHAZADA.
const POR_HACER = ['ASIGNADA', 'RECHAZADA', 'EN_PROGRESO', 'PENDIENTE_EXIF', 'COMPLETADA_TERRENO'];
const PEND_SUBIR = ['ASIGNADA', 'RECHAZADA'];

window.Guia = {
  cont: null,
  activo: false,
  vista: 'inicio',
  planes: [],
  planActual: null,
  idx: 0,
  _disp: [],

  async iniciar() {
    this.cont = document.getElementById('guia');
    if (!this.cont) return;
    this.activo = true;
    this.cont.style.display = 'block';
    const fb = document.querySelector('.filter-bar');
    const tc = document.querySelector('.tab-content');
    if (fb) fb.style.display = 'none';
    if (tc) tc.style.display = 'none';
    await this.inicio();
  },

  async _cargarMisPlanes() {
    let mis = [];
    try {
      mis = await fetchApi('/api/planes-trabajo/activos/');
    } catch (e) {}
    const map = {};
    (mis || []).forEach((t) => {
      const pid = t.plan && t.plan.id;
      if (!pid || !POR_HACER.includes(t.estado)) return;
      if (!map[pid]) map[pid] = { id: pid, descripcion: t.plan.descripcion || 'Plan', tareas: [] };
      map[pid].tareas.push(t);
    });
    this.planes = Object.values(map);
    return this.planes;
  },

  async inicio() {
    this.vista = 'inicio';
    this.cont.innerHTML = '<p class="guia-cargando">Cargando...</p>';
    await this._cargarMisPlanes();
    try {
      this._disp = (await fetchApi('/api/asignaciones/disponibles/')) || [];
    } catch (e) {
      this._disp = [];
    }
    const total = this.planes.reduce((n, p) => n + p.tareas.length, 0);
    const planesDisp = new Set((this._disp || []).map((t) => t.plan && t.plan.id).filter(Boolean))
      .size;
    let h = `<div class="guia-card guia-inicio"><h2>¿Qué quieres hacer?</h2>`;
    if (total)
      h += `<button class="guia-btn primary" data-act="mis"><i class="fas fa-play"></i> Hacer mis tareas <span class="guia-pill">${total}</span></button>`;
    if (planesDisp)
      h += `<button class="guia-btn" data-act="tomar"><i class="fas fa-hand-pointer"></i> Tomar un trabajo <span class="guia-pill">${planesDisp}</span></button>`;
    if (!total && !planesDisp)
      h += `<p class="guia-vacio">No tienes tareas asignadas. Toma o crea un trabajo.</p>`;
    h += `<button class="guia-btn" data-act="crear"><i class="fas fa-plus"></i> Crear un trabajo</button>`;
    h += `</div>`;
    this.cont.innerHTML = h;
    this._on('[data-act="mis"]', () => this.listaPlanes());
    this._on('[data-act="tomar"]', () => this.elegirNueva());
    this._on('[data-act="crear"]', () => this.crearTrabajo());
  },

  listaPlanes() {
    this.vista = 'planes';
    let h = `<div class="guia-card"><button class="guia-link" data-act="atras">← Volver</button>
      <h2>Tus planes</h2><p class="guia-sub">Toca un plan para trabajarlo.</p><div class="guia-lista">`;
    this.planes.forEach((p, i) => {
      const pend = p.tareas.filter((t) => PEND_SUBIR.includes(t.estado)).length;
      h += `<button class="guia-op" data-i="${i}"><strong>${escapeHtml(p.descripcion)}</strong>
        <small>${p.tareas.length} tareas · ${pend} por subir</small></button>`;
    });
    h += `</div></div>`;
    this.cont.innerHTML = h;
    this._on('[data-act="atras"]', () => this.inicio());
    this.cont
      .querySelectorAll('.guia-op')
      .forEach((b) => b.addEventListener('click', () => this.abrirPlan(this.planes[+b.dataset.i])));
  },

  _badge(estado) {
    if (['EN_PROGRESO', 'COMPLETADA_TERRENO'].includes(estado))
      return '<span class="guia-badge ok"><i class="fas fa-check"></i> con fotos</span>';
    if (estado === 'PENDIENTE_EXIF') return '<span class="guia-badge warn">revisar fecha</span>';
    if (estado === 'RECHAZADA') return '<span class="guia-badge bad">repetir</span>';
    return '<span class="guia-badge">sin fotos</span>';
  },

  _estClass(estado) {
    if (['EN_PROGRESO', 'COMPLETADA_TERRENO'].includes(estado)) return 'est-ok';
    if (estado === 'PENDIENTE_EXIF') return 'est-warn';
    if (estado === 'RECHAZADA') return 'est-bad';
    return 'est-new';
  },

  abrirPlan(plan) {
    if (!plan) return this.listaPlanes();
    this.planActual = plan;
    this.vista = 'plan';
    const hechas = plan.tareas.filter((t) =>
      ['EN_PROGRESO', 'COMPLETADA_TERRENO'].includes(t.estado)
    ).length;
    let h = `<div class="guia-card"><button class="guia-link" data-act="atras">← Mis planes</button>
      <h2>${escapeHtml(plan.descripcion)}</h2>
      <p class="guia-sub">${hechas} de ${
        plan.tareas.length
      } con fotos · toca la tarea que vas a subir</p>
      <div class="guia-lista">`;
    plan.tareas.forEach((t, i) => {
      const hint = (window.getTaskHint && window.getTaskHint(t.item.nombre)) || '';
      h += `<button class="guia-op guia-tarea-card ${this._estClass(t.estado)}" data-i="${i}">
        <span class="guia-op-top"><strong>${escapeHtml(t.item.nombre)}</strong>${this._badge(
          t.estado
        )}</span>
        <span class="guia-op-hint">${escapeHtml(hint)}</span>
        <span class="guia-op-cta">Subir fotos <i class="fas fa-arrow-right"></i></span>
      </button>`;
    });
    h += `</div></div>`;
    this.cont.innerHTML = h;
    this._on('[data-act="atras"]', () => this.listaPlanes());
    this.cont
      .querySelectorAll('.guia-op')
      .forEach((b) => b.addEventListener('click', () => this.tarea(+b.dataset.i)));
  },

  tarea(idx) {
    const plan = this.planActual;
    if (!plan || idx < 0 || idx >= plan.tareas.length) return this.abrirPlan(plan);
    this.vista = 'tarea';
    this.idx = idx;
    const t = plan.tareas[idx];
    const proy =
      (t.item &&
        t.item.categoria &&
        t.item.categoria.proyecto &&
        t.item.categoria.proyecto.nombre_pmc) ||
      '';
    const total = plan.tareas.length;
    const pct = Math.round((idx / total) * 100);
    const safe = (t.item.nombre || '').replace(/['"]/g, '');
    let aviso = '';
    if (['EN_PROGRESO', 'COMPLETADA_TERRENO'].includes(t.estado))
      aviso = `<div class="guia-aviso ok"><i class="fas fa-check"></i> Ya subiste fotos en esta tarea. Puedes agregar más.</div>`;
    else if (t.estado === 'PENDIENTE_EXIF')
      aviso = `<div class="guia-aviso warn">Subiste fotos pero faltó la fecha; el supervisor las revisa. Puedes subir más.</div>`;
    else if (t.estado === 'RECHAZADA' && t.comentario_rechazo_supervisor)
      aviso = `<div class="guia-rechazo"><i class="fas fa-rotate-left"></i> El supervisor pidió repetir: ${escapeHtml(
        t.comentario_rechazo_supervisor
      )}</div>`;
    this.cont.innerHTML = `<div class="guia-card guia-paso">
      <button class="guia-link" data-act="atras">← ${escapeHtml(plan.descripcion)}</button>
      <div class="guia-progreso">Tarea ${idx + 1} de ${total}</div>
      <div class="guia-barra"><div style="width:${pct}%"></div></div>
      <small class="guia-proy">${escapeHtml(proy)}</small>
      <h2>${escapeHtml(t.item.nombre)}</h2>
      <div class="guia-instru"><span>Qué hacer</span>${escapeHtml(
        window.getTaskHint(t.item.nombre)
      )}</div>
      ${aviso}
      <button class="guia-btn primary" data-act="foto"><i class="fas fa-camera"></i> Sacar / subir fotos</button>
      <div class="guia-nav">
        ${
          idx > 0
            ? '<button class="guia-link" data-act="prev">← Anterior</button>'
            : '<span></span>'
        }
        ${
          idx < total - 1
            ? '<button class="guia-link" data-act="next">Siguiente →</button>'
            : '<span></span>'
        }
      </div></div>`;
    this._on('[data-act="atras"]', () => this.abrirPlan(plan));
    this._on('[data-act="foto"]', () => window.openUploadModal(t.id, safe));
    this._on('[data-act="prev"]', () => this.tarea(idx - 1));
    this._on('[data-act="next"]', () => this.tarea(idx + 1));
  },

  async fotoSubida(taskId) {
    if (this.vista !== 'tarea' || !this.planActual) return;
    const actual = this.planActual.tareas[this.idx];
    if (!actual || actual.id !== taskId) return;
    if (window.showToast) window.showToast('Foto subida ✓ — pasando a la siguiente', 'success');
    const pid = this.planActual.id;
    await this._cargarMisPlanes();
    this.planActual = this.planes.find((p) => p.id === pid) || this.planActual;
    const sig = this.idx + 1;
    if (this.planActual && sig < this.planActual.tareas.length) this.tarea(sig);
    else this.finPlan();
  },

  finPlan() {
    this.vista = 'fin';
    this.cont.innerHTML = `<div class="guia-card guia-fin">
      <div class="guia-emoji">🎉</div><h2>¡Plan listo!</h2>
      <p>Subiste las fotos de este plan. El supervisor las revisará.</p>
      <button class="guia-btn primary" data-act="planes"><i class="fas fa-list"></i> Mis planes</button>
      <button class="guia-link" data-act="inicio">Inicio</button></div>`;
    this._on('[data-act="planes"]', () => this._cargarMisPlanes().then(() => this.listaPlanes()));
    this._on('[data-act="inicio"]', () => this.inicio());
  },

  // Mapea el texto del plan a uno de los 7 casos de Diego (para el badge).
  _casoDiego(texto) {
    const t = (texto || '').toLowerCase();
    if (/instalaci/.test(t)) return { n: 'Instalación', i: 'fa-screwdriver-wrench' };
    if (/retiro/.test(t)) return { n: 'Retiro', i: 'fa-box-open' };
    if (/traslado/.test(t)) return { n: 'Traslado', i: 'fa-truck-arrow-right' };
    if (/despacho/.test(t)) return { n: 'Despacho', i: 'fa-truck' };
    if (/epp|segur|prevenc/.test(t)) return { n: 'EPP / Seguridad', i: 'fa-helmet-safety' };
    if (/avance|produc/.test(t)) return { n: 'Avance del día', i: 'fa-chart-line' };
    if (/visita|preventa|levantam/.test(t))
      return { n: 'Visita / Preventa', i: 'fa-clipboard-check' };
    return { n: 'Trabajo', i: 'fa-briefcase' };
  },

  elegirNueva() {
    this.vista = 'tomar';
    // Agrupar el pool por PLAN (tomar un trabajo completo, no tareas sueltas).
    const map = {};
    (this._disp || []).forEach((t) => {
      const pid = t.plan && t.plan.id;
      if (!pid) return;
      if (!map[pid])
        map[pid] = {
          id: pid,
          descripcion: (t.plan && t.plan.descripcion) || 'Plan',
          n: 0,
          proy:
            (t.item &&
              t.item.categoria &&
              t.item.categoria.proyecto &&
              t.item.categoria.proyecto.nombre_pmc) ||
            '',
        };
      map[pid].n++;
    });
    const planes = Object.values(map);
    let h = `<div class="guia-card"><button class="guia-link" data-act="atras">← Volver</button>
      <h2>Tomar un trabajo</h2><p class="guia-sub">Elige el trabajo que vas a hacer. Quedará en "Mis planes".</p><div class="guia-lista">`;
    if (!planes.length) h += `<p class="guia-vacio">No hay trabajos disponibles ahora.</p>`;
    planes.forEach((p, i) => {
      const c = this._casoDiego(p.descripcion);
      h += `<button class="guia-op" data-i="${i}">
        <span class="guia-op-top"><strong>${escapeHtml(p.descripcion)}</strong>
          <span class="guia-badge caso"><i class="fas ${c.i}"></i> ${c.n}</span></span>
        <small>${p.n} tarea${p.n === 1 ? '' : 's'}${
          p.proy ? ' · ' + escapeHtml(p.proy) : ''
        }</small></button>`;
    });
    h += `</div></div>`;
    this.cont.innerHTML = h;
    this._on('[data-act="atras"]', () => this.inicio());
    this.cont.querySelectorAll('.guia-op').forEach((b) =>
      b.addEventListener('click', async () => {
        const p = planes[+b.dataset.i];
        b.disabled = true;
        b.innerHTML = 'Tomando trabajo...';
        try {
          await fetchApi(`/api/planes-trabajo/${p.id}/tomar`, { method: 'POST' });
        } catch (e) {}
        if (window.showToast) window.showToast('Trabajo tomado. Está en "Mis planes".', 'success');
        await this._cargarMisPlanes();
        const plan = this.planes.find((x) => x.id === p.id);
        if (plan) this.abrirPlan(plan);
        else this.inicio();
      })
    );
  },

  // El técnico crea su propio trabajo (mismo formulario que el supervisor).
  async crearTrabajo() {
    this.vista = 'crear';
    let clientes = [];
    try {
      clientes = await fetchApi('/api/clientes');
    } catch (e) {}
    const opts = (clientes || []).map((c) => `<option>${escapeHtml(c.nombre)}</option>`).join('');
    this.cont.innerHTML = `<div class="guia-card guia-crear">
      <button class="guia-link" data-act="atras">← Volver</button>
      <h2>Crear un trabajo</h2>
      <p class="guia-sub">Llena estos datos y se crea con sus tareas.</p>
      <label class="guia-lbl">Tipo de trabajo</label>
      <select id="ct-tipo" class="guia-input">
        <option value="">— Elegir —</option>
        <option>Instalación</option><option>Retiro</option><option>Traslado</option>
        <option>Despacho</option><option>Reportabilidad EPP</option>
        <option>Avance del día</option><option>Visita / Preventa</option>
      </select>
      <label class="guia-lbl">Cliente</label>
      <div style="display:flex; gap:8px">
        <select id="ct-cliente" class="guia-input" style="flex:1"><option value="">— Elegir —</option>${opts}</select>
        <button class="guia-btn-mini" data-act="nuevo-cli" title="Agregar cliente">+</button>
      </div>
      <label class="guia-lbl">N° (correlativo del cliente)</label>
      <input id="ct-numero" class="guia-input" type="number" min="1" placeholder="Se asigna solo" />
      <label class="guia-lbl">Fecha</label>
      <input id="ct-fecha" class="guia-input" type="date" />
      <button class="guia-btn primary" data-act="crear"><i class="fas fa-check"></i> Crear y empezar</button>
    </div>`;
    const numEl = () => this.cont.querySelector('#ct-numero');
    const cliEl = () => this.cont.querySelector('#ct-cliente');
    const actualizarNum = async () => {
      const cli = cliEl()?.value;
      if (!cli) {
        numEl().value = '';
        return;
      }
      try {
        const r = await fetchApi(
          '/api/planes-trabajo/siguiente-numero?cliente=' + encodeURIComponent(cli)
        );
        numEl().value = r.siguiente;
      } catch (e) {}
    };
    this._on('[data-act="atras"]', () => this.inicio());
    cliEl()?.addEventListener('change', actualizarNum);
    this._on('[data-act="nuevo-cli"]', async () => {
      const nombre = prompt('Nombre del cliente nuevo:');
      if (!nombre || !nombre.trim()) return;
      try {
        const r = await fetchApi('/api/clientes', { method: 'POST', body: { nombre } });
        const sel = cliEl();
        if (![...sel.options].some((o) => o.text === r.nombre))
          sel.insertAdjacentHTML('beforeend', `<option>${escapeHtml(r.nombre)}</option>`);
        sel.value = r.nombre;
        await actualizarNum();
      } catch (e) {
        if (window.showToast) window.showToast('No se pudo: ' + e.message, 'error');
      }
    });
    this._on('[data-act="crear"]', async () => {
      const v = (id) => (this.cont.querySelector('#' + id)?.value || '').trim();
      const tipo = v('ct-tipo');
      const cliente = v('ct-cliente');
      const numero = parseInt(v('ct-numero')) || null;
      const fecha = v('ct-fecha');
      if (!tipo || !cliente) {
        if (window.showToast) window.showToast('Elige tipo y cliente', 'error');
        return;
      }
      const partes = [tipo, cliente];
      if (numero) partes.push('N°' + numero);
      if (fecha) {
        const [y, m, d] = fecha.split('-');
        partes.push(`${d}-${m}-${y}`);
      }
      const btn = this.cont.querySelector('[data-act="crear"]');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = 'Creando...';
      }
      try {
        const r = await fetchApi('/api/terreno/crear-trabajo', {
          method: 'POST',
          body: { tipo, cliente, numero, descripcion: partes.join(' · ') },
        });
        if (window.showToast) window.showToast('Trabajo creado ✓', 'success');
        await this._cargarMisPlanes();
        const plan = this.planes.find((p) => p.id === r.plan_id);
        if (plan) this.abrirPlan(plan);
        else this.inicio();
      } catch (e) {
        if (window.showToast) window.showToast('No se pudo crear: ' + e.message, 'error');
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fas fa-check"></i> Crear y empezar';
        }
      }
    });
  },

  _on(sel, fn) {
    const el = this.cont.querySelector(sel);
    if (el) el.addEventListener('click', fn);
  },
};

window.renderAllLists = function (filtro = '') {
  const f = filtro.toLowerCase();
  const visibles = window.g_tareas.filter((t) => !isMandatoryTask(t));
  const filtradas = visibles.filter((t) =>
    `${t.item.nombre} ${t.plan.descripcion} ${t.item.categoria.proyecto.nombre_pmc}`
      .toLowerCase()
      .includes(f)
  );
  const pendientes = [];
  const enCurso = [];
  filtradas.forEach((t) => {
    if (t.estado === 'ASIGNADA' || t.estado === 'RECHAZADA') pendientes.push(t);
    else enCurso.push(t);
  });
  window.renderGroupedList('list-pendientes', pendientes, true);
  window.renderGroupedList('list-curso', enCurso, false);
  window.renderMandatoryFlow();
};

window.renderGroupedList = function (containerId, tareas, isPendiente) {
  const container = document.getElementById(containerId);
  if (!container) {
    return;
  }
  container.innerHTML = '';
  if (tareas.length === 0) {
    container.innerHTML =
      '<p style="color:#666;text-align:center;margin-top:20px;">Sin tareas.</p>';
    return;
  }

  // 1. Agrupar por PLAN
  const gruposPlan = {};
  tareas.forEach((t) => {
    const pk = t.plan.descripcion || 'Sin Plan';
    if (!gruposPlan[pk]) gruposPlan[pk] = [];
    gruposPlan[pk].push(t);
  });

  Object.keys(gruposPlan)
    .sort()
    .forEach((planName) => {
      // PLAN CONTAINER
      const planDiv = document.createElement('div');
      planDiv.className = 'plan-group';

      const pHeader = document.createElement('div');
      pHeader.className = 'plan-header';
      pHeader.innerHTML = `<span>${escapeHtml(
        planName
      )}</span> <i class="fas fa-chevron-down"></i>`;
      pHeader.onclick = () => planDiv.classList.toggle('collapsed');

      const pContent = document.createElement('div');
      pContent.className = 'plan-content';

      // 2. Agrupar por PROYECTO dentro del Plan
      const tareasDelPlan = gruposPlan[planName];
      const gruposProyecto = {};

      tareasDelPlan.forEach((t) => {
        const projName = t.item.categoria.proyecto.nombre_pmc || 'Sin Proyecto';
        if (!gruposProyecto[projName]) gruposProyecto[projName] = [];
        gruposProyecto[projName].push(t);
      });

      Object.keys(gruposProyecto)
        .sort(window.naturalSort)
        .forEach((projName) => {
          // PROJECT CONTAINER
          const projDiv = document.createElement('div');
          projDiv.className = 'project-group'; // Clase nueva para estilo

          const prHeader = document.createElement('div');
          prHeader.className = 'project-header';
          prHeader.innerHTML = `<span>${escapeHtml(
            projName
          )}</span> <i class="fas fa-chevron-down"></i>`;
          prHeader.onclick = (e) => {
            e.stopPropagation();
            projDiv.classList.toggle('collapsed');
          };

          const taskListDiv = document.createElement('div');
          taskListDiv.className = 'project-content';

          // 3. Renderizar Tareas
          const taskList = gruposProyecto[projName];
          taskList.sort((a, b) => window.naturalSort(a.item.nombre, b.item.nombre));

          taskList.forEach((t) => {
            const card = document.createElement('div');
            let sClass = 'status-asignada';
            let bClass = 'badge-asignada';
            if (t.estado === 'RECHAZADA') {
              sClass = 'status-rechazada';
              bClass = 'badge-rechazada';
            } else if (t.estado === 'PENDIENTE_EXIF') {
              sClass = 'status-pendiente-exif';
              bClass = 'badge-warning';
            } else if (t.estado === 'COMPLETADA_TERRENO') {
              sClass = 'status-asignada';
              bClass = 'badge-asignada';
            }

            const isExtra = t.es_complementaria ? 'border: 1px dashed #ffcc00;' : '';
            const tagExtra = t.es_complementaria
              ? '<span style="color:#ffcc00;font-size:0.7rem;">[EXTRA]</span>'
              : '';
            const btnText = isPendiente ? 'SUBIR EVIDENCIA' : 'AGREGAR MAS FOTOS';
            const safeName = t.item.nombre.replace(/'/g, '').replace(/"/g, '');

            card.className = `task-card ${sClass}`;
            if (isExtra) card.style.cssText = isExtra;

            let rejHtml =
              t.estado === 'RECHAZADA' && t.comentario_rechazo_supervisor
                ? `<div class="rejection-note">ATENCION: ${escapeHtml(
                    t.comentario_rechazo_supervisor
                  )}</div>`
                : '';
            if (t.estado === 'PENDIENTE_EXIF')
              rejHtml += `<div class="rejection-note" style="border-color:orange;color:orange;">ATENCION: Sin fecha EXIF.</div>`;

            card.innerHTML = `
                    <div class="task-header">
                        <div class="task-title">${escapeHtml(t.item.nombre)} ${tagExtra}</div>
                        <span class="task-status-badge ${bClass}">${escapeHtml(
                          t.estado.replace('ITEM_', '').replace('_TERRENO', '')
                        )}</span>
                    </div>
                    <div class="task-hint-inline">${window.getTaskHint(t.item.nombre)}</div>
                    ${rejHtml}
                    <div class="task-actions">
                        <button class="btn-upload" onclick="window.openUploadModal(${
                          t.id
                        }, '${safeName}')"><i class="fas fa-camera"></i> ${btnText}</button>
                    </div>
                `;
            taskListDiv.appendChild(card);
          });

          projDiv.appendChild(prHeader);
          projDiv.appendChild(taskListDiv);
          pContent.appendChild(projDiv);
        });

      planDiv.appendChild(pHeader);
      planDiv.appendChild(pContent);
      container.appendChild(planDiv);
    });
};

window.renderMandatoryFlow = function () {
  const panel = document.getElementById('mandatory-flow');
  const list = document.getElementById('mandatory-list');
  const progress = document.getElementById('mandatory-progress');
  const demoBtn = document.getElementById('btn-demo-skip');
  if (!panel || !list || !progress) {
    return;
  }

  const tareas = window.g_tareas.filter((t) => isMandatoryTask(t));
  if (tareas.length === 0) {
    panel.style.display = 'none';
    document.body.classList.remove('gating-active');
    document.body.classList.remove('mandatory-after');
    return;
  }

  const demoMode = isDemoMode();
  const demoSkip = isDemoSkipActive();
  if (demoBtn) {
    demoBtn.style.display = demoMode ? 'inline-flex' : 'none';
    demoBtn.textContent = demoSkip ? 'Simulacion activa' : 'Simular inicio listo';
    demoBtn.classList.toggle('active', demoSkip);
  }

  const isDone = (t) => demoSkip || isMandatoryComplete(t.estado);
  const completadas = tareas.filter((t) => isDone(t));
  const gateTasks = tareas.filter((t) => isMandatoryGateTask(t));
  const gateDone = gateTasks.filter((t) => isDone(t));
  progress.textContent = `Inicio ${gateDone.length}/${gateTasks.length}`;

  const pendientes = tareas.filter((t) => !isDone(t));
  const gatePendientes = gateTasks.filter((t) => !isDone(t));
  const shouldGate = gatePendientes.length > 0 && !demoSkip;

  panel.style.display = pendientes.length || demoMode ? 'block' : 'none';
  document.body.classList.toggle('gating-active', shouldGate);
  document.body.classList.toggle('mandatory-after', !shouldGate && pendientes.length > 0);

  list.innerHTML = '';
  tareas.sort((a, b) => window.naturalSort(a.item.nombre, b.item.nombre));
  tareas.forEach((t) => {
    const step = getMandatoryStep(t.item.nombre);
    const done = isDone(t);
    const planName = t.plan.descripcion || 'Sin plan';
    const projName = t.item.categoria.proyecto.nombre_pmc || 'Sin proyecto';
    const safeName = t.item.nombre.replace(/'/g, '').replace(/\"/g, '');
    const statusLabel = done
      ? demoSkip && !isMandatoryComplete(t.estado)
        ? 'Listo (demo)'
        : 'Listo'
      : 'Pendiente';
    const statusClass = done ? 'mandatory-status ok' : 'mandatory-status';
    const phaseLabel = step ? (step.gate ? 'Inicio obligatorio' : 'Cierre') : 'Obligatorio';
    const phaseClass =
      step && step.gate ? 'mandatory-phase mandatory-phase--gate' : 'mandatory-phase';
    const card = document.createElement('div');
    card.className = 'mandatory-card';
    card.innerHTML = `
            <div class="mandatory-title">
                <span>${escapeHtml(step ? step.label : t.item.nombre)}</span>
                <span class="${phaseClass}">${phaseLabel}</span>
            </div>
            <span class="${statusClass}">${statusLabel}</span>
            <div class="mandatory-meta">Plan ${escapeHtml(planName)} - ${escapeHtml(projName)}</div>
            <div class="mandatory-hint">${window.getTaskHint(t.item.nombre)}</div>
            ${
              done
                ? ''
                : `<button class="btn-upload" onclick="window.openUploadModal(${t.id}, '${safeName}')"><i class="fas fa-camera"></i> Subir evidencia</button>`
            }
        `;
    list.appendChild(card);
  });

  const now = new Date();
  if (now.getHours() >= MANDATORY_HOUR_LIMIT) {
    const note = panel.querySelector('.mandatory-note');
    if (note) {
      note.textContent = 'Fuera de horario. Igual es obligatorio completar el inicio.';
    }
  }
};

window.crearTareaExtra = async function () {
  const pid = document.getElementById('extra-plan-select').value;
  const name = document.getElementById('extra-task-name').value.trim();
  if (!pid || !name) {
    return alert('Faltan datos.');
  }
  Loader.show('Creando...');
  try {
    const tareaRef = window.g_tareas.find((t) => t.plan.id == pid);
    if (!tareaRef) {
      throw new Error('Plan no encontrado.');
    }
    await fetchApi('/api/tareas/crear-complemento', {
      method: 'POST',
      body: {
        plan_id: parseInt(pid),
        nombre_tarea: name,
        proyecto_id: tareaRef.item.categoria.proyecto.id,
      },
    });
    Loader.hide();
    alert('Creada.');
    document.getElementById('extra-task-name').value = '';
    document.querySelector('[data-tab="tab-pendientes"]').click();
    window.cargarTareas();
  } catch (e) {
    Loader.hide();
    alert(e.message);
  }
};

// --- GALERIA & INIT (IGUAL QUE ANTES) ---
window.openUploadModal = function (taskId, taskName) {
  try {
    window.g_taskUploadId = taskId;
    window.g_filesToUpload = [];
    window.g_selectedFileIndex = -1;
    const tName = document.getElementById('upload-task-name');
    if (tName) tName.textContent = taskName;

    const hint = document.getElementById('upload-task-hint');
    if (hint) {
      hint.textContent = window.getTaskHint(taskName);
    }
    window.updateGalleryUI();
    document.getElementById('modal-upload').style.display = 'flex';
  } catch (e) {
    alert('Error Modal: ' + e.message);
    console.error(e);
  }
};
window.closeUploadModal = function () {
  document.getElementById('modal-upload').style.display = 'none';
  window.g_filesToUpload = [];
  document.getElementById('file-input').value = '';
};
window.handleFiles = function (files) {
  const newFiles = Array.from(files);
  let added = 0;
  newFiles.forEach((f) => {
    if (!window.g_filesToUpload.some((x) => x.name === f.name && x.size === f.size)) {
      window.g_filesToUpload.push(f);
      added++;
    }
  });
  if (added > 0) {
    window.g_selectedFileIndex = window.g_filesToUpload.length - added;
    window.updateGalleryUI();
  }
  document.getElementById('file-input').value = '';
};
window.prevImage = function (e) {
  e.preventDefault();
  e.stopPropagation();
  if (!window.g_filesToUpload.length) {
    return;
  }
  window.g_selectedFileIndex--;
  if (window.g_selectedFileIndex < 0) {
    window.g_selectedFileIndex = window.g_filesToUpload.length - 1;
  }
  window.updateGalleryUI();
};
window.nextImage = function (e) {
  e.preventDefault();
  e.stopPropagation();
  if (!window.g_filesToUpload.length) {
    return;
  }
  window.g_selectedFileIndex++;
  if (window.g_selectedFileIndex >= window.g_filesToUpload.length) {
    window.g_selectedFileIndex = 0;
  }
  window.updateGalleryUI();
};
window.updateGalleryUI = function () {
  const hero = document.getElementById('gallery-hero');
  const strip = document.getElementById('gallery-strip');
  strip.innerHTML = '';
  const btnAdd = document.createElement('div');
  btnAdd.className = 'add-more-btn';
  btnAdd.innerHTML =
    '<i class="fas fa-camera" style="font-size:1.5rem;margin-bottom:5px;"></i><span>AGREGAR</span>';
  btnAdd.onclick = () => document.getElementById('file-input').click();
  if (!window.g_filesToUpload.length) {
    hero.innerHTML = '<div class="gallery-hero-placeholder">Sin fotos</div>';
    strip.appendChild(btnAdd);
    return;
  }
  if (window.g_selectedFileIndex >= window.g_filesToUpload.length) {
    window.g_selectedFileIndex = 0;
  }
  const curr = window.g_filesToUpload[window.g_selectedFileIndex];
  const url = URL.createObjectURL(curr);
  const isVid = curr.type.startsWith('video/');
  hero.innerHTML = `
        <button class="gallery-nav-btn prev" onclick="window.prevImage(event)">&#10094;</button>
        ${
          isVid
            ? `<video src="${url}" controls style="max-width:100%;max-height:100%"></video>`
            : `<img src="${url}">`
        }
        <button class="gallery-nav-btn next" onclick="window.nextImage(event)">&#10095;</button>
    `;
  window.g_filesToUpload.forEach((f, i) => {
    const th = document.createElement('div');
    th.className = `thumb-card ${i === window.g_selectedFileIndex ? 'active' : ''}`;
    if (f.type.startsWith('video/')) {
      th.innerHTML =
        '<div style="background:#222;color:#fff;height:100%;display:flex;justify-content:center;align-items:center;">VID</div>';
    } else {
      const img = document.createElement('img');
      img.src = URL.createObjectURL(f);
      th.appendChild(img);
    }
    const del = document.createElement('div');
    del.className = 'thumb-remove';
    del.innerHTML = 'x';
    del.onclick = (e) => {
      e.stopPropagation();
      window.removeFile(i);
    };
    th.appendChild(del);
    th.onclick = () => {
      window.g_selectedFileIndex = i;
      window.updateGalleryUI();
    };
    strip.appendChild(th);
  });
  strip.appendChild(btnAdd);
};
window.removeFile = function (i) {
  window.g_filesToUpload.splice(i, 1);
  if (window.g_selectedFileIndex >= window.g_filesToUpload.length) {
    window.g_selectedFileIndex = Math.max(0, window.g_filesToUpload.length - 1);
  }
  window.updateGalleryUI();
};
window.subirArchivos = async function () {
  if (!window.g_taskUploadId) {
    return;
  }
  const taskId = window.g_taskUploadId;
  const files = window.g_filesToUpload.slice();
  if (files.length === 0) {
    return;
  }
  const fd = new FormData();
  files.forEach((f) => fd.append('files', f));
  window.closeUploadModal();

  // OFFLINE: Save to IndexedDB
  const dbIds = [];
  if (window.OfflineStore) {
    try {
      for (const f of files) {
        const id = await window.OfflineStore.save(f, { taskId: taskId, name: f.name });
        dbIds.push(id);
      }
    } catch (e) {
      console.error('Offline Save Err', e);
    }
  }

  window.g_uploadQueue.push({
    taskId: taskId,
    formData: fd,
    filesCount: files.length,
    dbIds: dbIds,
  });

  if (window.g_uploadActive) {
    const left = window.g_uploadQueue.length;
    updateUploadStatus(`En cola ${left}`, 0, 'loading');
    return;
  }
  processNextUpload();
};

document.addEventListener('DOMContentLoaded', () => {
  // PWA Service Worker Registration
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker
      .register(withEnvPrefix('/service-worker.js'), { scope: withEnvPrefix('/') })
      .catch((err) => console.log('SW Fail:', err));
  }

  // SYNC OFFLINE PHOTOS
  if (window.OfflineStore) {
    setTimeout(async () => {
      try {
        const records = await window.OfflineStore.getAll();
        if (records && records.length > 0) {
          console.log(`Syncing ${records.length} offline photos...`);
          // Group by Task
          const tasks = {};
          records.forEach((r) => {
            const tid = r.metadata.taskId;
            if (!tasks[tid]) tasks[tid] = { ids: [], files: [] };
            tasks[tid].ids.push(r.id);
            tasks[tid].files.push(r.photo); // r.photo is the Blob/File
          });

          // Re-queue
          Object.keys(tasks).forEach((tid) => {
            const t = tasks[tid];
            const fd = new FormData();
            t.files.forEach((f) => fd.append('files', f));
            window.g_uploadQueue.push({
              taskId: tid,
              formData: fd,
              filesCount: t.files.length,
              dbIds: t.ids,
            });
          });

          if (window.g_uploadQueue.length > 0 && !window.g_uploadActive) {
            processNextUpload();
          }
        }
      } catch (e) {
        console.error('Sync Err', e);
      }
    }, 1000);
  }

  if (ensureAppVersion()) {
    return;
  }
  fetchApi('/auth/whoami')
    .then((u) => {
      window.__meRole = String(u?.role || '').toUpperCase();
      if (u.logged && document.getElementById('who')) {
        document.getElementById('who').textContent = `${u.name} (${u.role})`;
      }
    })
    .catch(() => handleAuthExpired());
  if (typeof initLogout === 'function') {
    initLogout();
  }
  if (typeof initModal === 'function') {
    initModal();
  }
  document.querySelectorAll('.tab-link').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.tab-link').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
      if (btn.dataset.tab === 'tab-disponibles') window.cargarDisponibles();
    });
  });
  window.cargarTareas();
  window.Guia.iniciar(); // modo guiado por defecto (único módulo)
  document.getElementById('btn-guia-home')?.addEventListener('click', () => window.Guia.iniciar());
  document
    .getElementById('btn-modo-guiado')
    ?.addEventListener('click', () => window.Guia.iniciar());
  document
    .getElementById('search-task')
    ?.addEventListener('input', (e) => window.renderAllLists(e.target.value));
  document.getElementById('btn-create-extra')?.addEventListener('click', window.crearTareaExtra);
  const fi = document.getElementById('file-input');
  if (fi) {
    fi.addEventListener('change', (e) => window.handleFiles(e.target.files));
  }
  const demoBtn = document.getElementById('btn-demo-skip');
  if (demoBtn) {
    demoBtn.addEventListener('click', () => {
      // Allow skip always as per user request
      const next = !isDemoSkipActive();
      setDemoSkipActive(next);
      window.renderMandatoryFlow();
    });
  }
  const dz = document.getElementById('drop-zone');
  if (dz) {
    dz.addEventListener('click', () => document.getElementById('file-input').click());
  }

  // Modal Change Password Logic
  const btnChangePass = document.getElementById('btn-open-change-password');
  const modalChangePass = document.getElementById('modal-change-password');

  if (btnChangePass && modalChangePass) {
    const getScrollbarWidth = () => window.innerWidth - document.documentElement.clientWidth;

    btnChangePass.addEventListener('click', () => {
      const scrollWidth = getScrollbarWidth();
      modalChangePass.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      if (scrollWidth > 0) {
        document.body.style.paddingRight = `${scrollWidth}px`;
      }
    });

    const closeModal = () => {
      modalChangePass.style.display = 'none';
      document.body.style.overflow = '';
      document.body.style.paddingRight = '';
    };

    // Close via Button
    const closeBtns = modalChangePass.querySelectorAll('.modal-close-btn');
    closeBtns.forEach((btn) => {
      btn.addEventListener('click', closeModal);
    });

    // Close via Backdrop Click
    modalChangePass.addEventListener('click', (e) => {
      if (e.target === modalChangePass) {
        closeModal();
      }
    });
  }
  // SIDEBAR TOGGLE LOGIC (PORTED FROM PORTAL)
  const toggleBtn = document.getElementById('sidebar-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      document.body.classList.toggle('sidebar-collapsed');
      // Save preference if needed
      const isCollapsed = document.body.classList.contains('sidebar-collapsed');
      localStorage.setItem('sidebar_collapsed', isCollapsed);
    });
  }

  // Restore sidebar state
  if (localStorage.getItem('sidebar_collapsed') === 'true') {
    document.body.classList.add('sidebar-collapsed');
  }

  document.getElementById('form-upload')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (window.g_filesToUpload.length === 0) {
      return alert('Seleccione fotos.');
    }
    await window.subirArchivos();
  });
});
