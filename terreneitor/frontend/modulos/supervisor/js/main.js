import { SupervisorAPI } from './api.js';
import { SupervisorUI } from './ui.js';
const ENVP = window.location.pathname.startsWith('/dev') ? '/dev' : '';

const AppState = {
  proyectos: [],
  especialistas: [],
  selectedUsers: new Set(),
  selectedItems: {},
  currentView: 'tab-planificar',
  projectPage: 1,
  selectedProjectId: null,
  selectedProjectName: null,
  lb_images: [],
  lb_index: 0,
  currentPlanForAdd: null,
  selectedItemsForAdd: {},
};

// --- AUTH HANDLER ---
const LOGIN_PATH = 'https://terreno.telconsulting.cl/';
function redirectToLogin() {
  window.location.href = LOGIN_PATH;
}

async function init() {
  console.log('Iniciando App Supervisor Modular...');
  SupervisorUI.Loader.init();

  try {
    const user = await SupervisorAPI.whoami();
    if (user.logged) {
      document.getElementById('who').textContent = `${user.name} (${user.role})`;
      setupEventListeners();
      initAddItemsModal();
      loadInitialData();
      exposeGlobalHandlers();
    } else {
      redirectToLogin();
    }
  } catch (e) {
    console.error('Error en init:', e);
    redirectToLogin();
  }
}

function setupEventListeners() {
  // Tab Navigation
  document.querySelectorAll('.tab-link').forEach((link) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const view = link.dataset.tab;
      if (AppState.currentView === view) return;
      AppState.currentView = view;
      SupervisorUI.showView(view);
      handleViewChange(view);
    });
  });

  // Logout
  document.getElementById('btnLogout').onclick = async () => {
    try {
      await SupervisorAPI.logout();
    } catch (e) {}
    redirectToLogin();
  };

  // Filters & Search
  document.getElementById('search-projects')?.addEventListener('input', () => {
    AppState.projectPage = 1;
    SupervisorUI.renderProjectList(AppState.proyectos, AppState, onProjectSelect);
  });

  ['filter-cliente', 'filter-zona-id'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', () => {
      AppState.projectPage = 1;
      SupervisorUI.renderProjectList(AppState.proyectos, AppState, onProjectSelect);
    });
  });

  // Arma el nombre del plan a partir de tipo · cliente · N° · fecha.
  const composePlanDesc = () => {
    const v = (id) => (document.getElementById(id)?.value || '').trim();
    const tipo = v('plan-tipo');
    const cliente = v('plan-cliente');
    const numero = v('plan-numero');
    const fecha = v('plan-fecha'); // YYYY-MM-DD
    const partes = [];
    if (tipo) partes.push(tipo);
    if (cliente) partes.push(cliente);
    if (numero) partes.push(/^\d+$/.test(numero) ? 'N°' + numero : numero);
    if (fecha) {
      const [y, m, d] = fecha.split('-');
      partes.push(`${d}-${m}-${y}`);
    }
    const desc = partes.join(' · ');
    const hid = document.getElementById('plan-descripcion');
    if (hid) hid.value = desc;
    const prev = document.getElementById('plan-preview');
    if (prev) prev.textContent = desc ? `Nombre: ${desc}` : '';
    return desc;
  };
  ['plan-tipo', 'plan-cliente', 'plan-numero', 'plan-fecha'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('input', composePlanDesc);
  });

  // Catálogo de clientes (dropdown) + agregar + número correlativo por cliente.
  const cargarClientes = async (seleccionar) => {
    try {
      const cli = await SupervisorAPI.getClientes();
      const sel = document.getElementById('plan-cliente');
      if (!sel) return;
      const actual = seleccionar || sel.value;
      sel.innerHTML =
        '<option value="">— Selecciona —</option>' +
        cli.map((c) => `<option>${c.nombre}</option>`).join('');
      if (actual) sel.value = actual;
    } catch (e) {}
  };
  const actualizarNumero = async () => {
    const sel = document.getElementById('plan-cliente');
    const numEl = document.getElementById('plan-numero');
    if (!numEl) return;
    if (!sel || !sel.value) {
      numEl.value = '';
      return;
    }
    try {
      const r = await SupervisorAPI.siguienteNumero(sel.value);
      numEl.value = r.siguiente;
    } catch (e) {}
  };
  cargarClientes();
  document.getElementById('plan-cliente')?.addEventListener('change', async () => {
    await actualizarNumero();
    composePlanDesc();
  });
  document.getElementById('btn-nuevo-cliente')?.addEventListener('click', async () => {
    const nombre = prompt('Nombre del cliente nuevo (ej: Claro):');
    if (!nombre || !nombre.trim()) return;
    try {
      const r = await SupervisorAPI.addCliente(nombre);
      await cargarClientes(r.nombre);
      await actualizarNumero();
      composePlanDesc();
    } catch (e) {
      alert('No se pudo agregar el cliente: ' + e.message);
    }
  });

  // Create Plan
  document.getElementById('btn-crear-plan')?.addEventListener('click', async () => {
    const desc = composePlanDesc();
    if (
      !desc ||
      AppState.selectedUsers.size === 0 ||
      Object.keys(AppState.selectedItems).length === 0
    ) {
      alert('Falta el nombre del plan (tipo/cliente/N°/fecha), responsables o tareas.');
      return;
    }

    SupervisorUI.Loader.show('Creando plan...');
    try {
      await SupervisorAPI.createPlan({
        descripcion: desc,
        usuario_ids: Array.from(AppState.selectedUsers),
        item_ids: Object.keys(AppState.selectedItems).map((id) => parseInt(id)),
        cliente: (document.getElementById('plan-cliente')?.value || '').trim() || null,
        numero: parseInt(document.getElementById('plan-numero')?.value) || null,
      });
      alert('Plan creado con éxito.');
      AppState.selectedItems = {};
      SupervisorUI.renderSelectionQueue(AppState.selectedItems, onRemoveTask);
      ['plan-tipo', 'plan-cliente', 'plan-numero', 'plan-fecha'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      composePlanDesc();
    } catch (e) {
      alert('Error: ' + e.message);
    } finally {
      SupervisorUI.Loader.hide();
    }
  });

  // Sidebar Toggle
  document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    document.body.classList.toggle('sidebar-collapsed');
  });

  setupExifModalListeners();
  setupReportsListeners();
  if (typeof window.initModal === 'function') window.initModal();
}

function onProjectSelect(p) {
  AppState.selectedProjectId = p.id;
  AppState.selectedProjectName = p.nombre_pmc;
  document.getElementById('active-project-name').textContent = p.nombre_pmc;
  SupervisorAPI.getProyectoDetalle(p.id).then((det) => {
    SupervisorUI.renderTasks(det, onToggleTask, AppState.selectedItems);
    SupervisorUI.renderProjectList(AppState.proyectos, AppState, onProjectSelect);
  });
}

function onToggleTask(item, checked) {
  if (checked) AppState.selectedItems[item.id] = item;
  else delete AppState.selectedItems[item.id];
  SupervisorUI.renderSelectionQueue(AppState.selectedItems, onRemoveTask);
}

function onRemoveTask(id) {
  delete AppState.selectedItems[id];
  SupervisorUI.renderSelectionQueue(AppState.selectedItems, onRemoveTask);
  const cb = document.getElementById(`i-${id}`);
  if (cb) cb.checked = false;
}

async function loadInitialData() {
  try {
    AppState.proyectos = await SupervisorAPI.getProyectos();
    AppState.especialistas = await SupervisorAPI.getEspecialistas();
    SupervisorUI.populateFilters(AppState.proyectos);
    SupervisorUI.renderProjectList(AppState.proyectos, AppState, onProjectSelect);
    SupervisorUI.renderEspecialistas(
      AppState.especialistas,
      AppState.selectedUsers,
      toggleEspecialista
    );
  } catch (e) {
    console.error('Error loaded data:', e);
  }
}

function toggleEspecialista(uid) {
  if (AppState.selectedUsers.has(uid)) AppState.selectedUsers.delete(uid);
  else AppState.selectedUsers.add(uid);
  SupervisorUI.renderEspecialistas(
    AppState.especialistas,
    AppState.selectedUsers,
    toggleEspecialista
  );
}

function handleViewChange(view) {
  if (view === 'tab-activos') {
    SupervisorAPI.getPlanesActivos().then((planes) =>
      SupervisorUI.renderPlanesActivos(planes, onPlanAction)
    );
  } else if (view === 'tab-validar') {
    Promise.all([
      SupervisorAPI.getAsignacionesPorEstado('COMPLETADA_TERRENO'),
      SupervisorAPI.getFotosCuarentena(),
    ]).then(([asigs, cuarentena]) => {
      SupervisorUI.renderValidacion(asigs, onValidationAction);
      SupervisorUI.renderCuarentena(cuarentena, onCuarentenaAction);
    });
  } else if (view === 'tab-listos') {
    SupervisorAPI.getPlanesListos().then((planes) =>
      SupervisorUI.renderListos(planes, onInformePlan)
    );
  } else if (view === 'tab-reportes') {
    // No data prefetch needed; UI is purely form-driven.
  }
}

async function onCuarentenaAction(type, data) {
  if (type === 'guardar-exif') {
    try {
      await SupervisorAPI.corregirExif(data);
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  } else if (type === 'eliminar-foto') {
    if (!confirm('¿Eliminar foto permanentemente?')) return;
    try {
      await SupervisorAPI.eliminarFotoCuarentena(data);
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  } else if (type === 'abrir-modal') {
    AppState.exifData = data;
    document.getElementById('exif-img-preview').src =
      `${ENVP}/api/common/view?path=${encodeURIComponent(data.ruta)}`;
    document.getElementById('exif-foto-nombre').textContent = data.nombre;
    const now = new Date();
    const localIso = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString();
    document.getElementById('exif-manual-date-only').value = localIso.slice(0, 10);
    document.getElementById('exif-manual-time-only').value = localIso.slice(11, 16);
    document.getElementById('modal-exif-resolver').style.display = 'flex';
  }
}

// --- MODAL ADD ITEMS ---
function initAddItemsModal() {
  const searchInp = document.getElementById('add-items-search-project');
  if (searchInp) {
    searchInp.oninput = () => {
      const query = searchInp.value.toLowerCase();
      renderProjectsInAddModal(query);
    };
  }

  const btnSave = document.getElementById('btn-confirm-add-items');
  if (btnSave) {
    btnSave.onclick = async () => {
      const itemIds = Object.keys(AppState.selectedItemsForAdd).map((id) => parseInt(id));
      if (!itemIds.length) {
        alert('Selecciona al menos una tarea.');
        return;
      }

      SupervisorUI.Loader.show('Agregando tareas...');
      try {
        await SupervisorAPI.addItemsToPlan(AppState.currentPlanForAdd.id, itemIds);
        alert('Tareas agregadas correctamente.');
        document.getElementById('modal-add-items').style.display = 'none';
        handleViewChange('tab-activos');
      } catch (e) {
        alert('Error: ' + e.message);
      } finally {
        SupervisorUI.Loader.hide();
      }
    };
  }
}

function renderProjectsInAddModal(query = '') {
  const container = document.getElementById('add-items-project-list');
  if (!container) return;

  const filtered = AppState.proyectos
    .filter(
      (p) => p.nombre_pmc?.toLowerCase().includes(query) || p.cliente?.toLowerCase().includes(query)
    )
    .sort((a, b) => SupervisorUI.naturalSort(a.nombre_pmc, b.nombre_pmc));

  container.innerHTML = filtered.length
    ? ''
    : '<p class="empty-msg">No se encontraron proyectos.</p>';
  filtered.forEach((p) => {
    const div = document.createElement('div');
    div.className = 'project-item-mini';
    div.innerHTML = `<div>${escapeHtml(p.nombre_pmc)}</div><small>${escapeHtml(
      p.cliente || 'S/C'
    )}</small>`;
    div.onclick = () => loadProjectItemsForAdd(p);
    container.appendChild(div);
  });
}

async function loadProjectItemsForAdd(project) {
  const container = document.getElementById('add-items-list-container');
  if (!container) return;
  container.innerHTML = '<p class="loading">Cargando tareas...</p>';

  try {
    const det = await SupervisorAPI.getProyectoDetalle(project.id);
    container.innerHTML = '';

    const groups = det.grupos || {};
    Object.keys(groups).forEach((g) => {
      groups[g].forEach((c) => {
        if (!c.items.length) return;
        const h = document.createElement('div');
        h.className = 'category-header-mini';
        h.textContent = `${g} / ${c.nombre}`;
        container.appendChild(h);

        c.items.forEach((i) => {
          const row = document.createElement('div');
          row.className = 'item-row-mini';
          const isChecked = !!AppState.selectedItemsForAdd[i.id];
          row.innerHTML = `
                        <input type="checkbox" id="add-i-${i.id}" ${isChecked ? 'checked' : ''}>
                        <label for="add-i-${i.id}">${escapeHtml(i.nombre)}</label>
                    `;
          row.querySelector('input').onchange = (e) => {
            if (e.target.checked) AppState.selectedItemsForAdd[i.id] = i;
            else delete AppState.selectedItemsForAdd[i.id];
          };
          container.appendChild(row);
        });
      });
    });
  } catch (e) {
    container.innerHTML = 'Error al cargar tareas';
  }
}

async function onPlanAction(type, data) {
  if (type === 'archive-plan') {
    if (confirm(`¿Archivar plan "${data.descripcion}"?`)) {
      SupervisorUI.Loader.show('Archivando...');
      try {
        await SupervisorAPI.archivarPlan(data.id);
        handleViewChange('tab-activos');
      } catch (e) {
        alert(e.message);
      } finally {
        SupervisorUI.Loader.hide();
      }
    }
  } else if (type === 'delete-plan') {
    if (
      confirm(
        `¿ELIMINAR DEFINITIVAMENTE el plan "${data.descripcion}"?\nEsto borrará todas las tareas asociadas.`
      )
    ) {
      SupervisorUI.Loader.show('Eliminando plan...');
      try {
        await SupervisorAPI.deletePlan(data.id);
        handleViewChange('tab-activos');
      } catch (e) {
        alert(e.message);
      } finally {
        SupervisorUI.Loader.hide();
      }
    }
  } else if (type === 'delete-item') {
    if (confirm(`¿Quitar tarea de este plan?`)) {
      try {
        await SupervisorAPI.deleteAsignacion(data.id);
        handleViewChange('tab-activos');
      } catch (e) {
        alert(e.message);
      }
    }
  } else if (type === 'add-items') {
    AppState.currentPlanForAdd = data;
    AppState.selectedItemsForAdd = {};
    document.getElementById('add-items-title').textContent =
      `AGREGAR TAREAS A: ${data.descripcion}`;
    document.getElementById('add-items-list-container').innerHTML =
      '<p class="empty-msg">Seleccione un proyecto a la izquierda.</p>';
    document.getElementById('add-items-search-project').value = '';
    renderProjectsInAddModal();
    document.getElementById('modal-add-items').style.display = 'flex';
  } else if (type === 'reassign-item') {
    if (confirm(`¿Reasignar tarea validada? Volverá a estar pendiente.`)) {
      try {
        await SupervisorAPI.reasignarTareaValidada(data.id);
        handleViewChange('tab-activos');
      } catch (e) {
        alert(e.message);
      }
    }
  }
}

async function onValidationAction(type, data) {
  if (type === 'load-thumbs') {
    const { asigId, container } = data;
    try {
      const files = await SupervisorAPI.getArchivosPorValidar(asigId);
      files.forEach((f) => (f.asignacion_id = asigId));
      container.id = `thumbs-${asigId}`;
      container.innerHTML = files
        .map((f, idx) => {
          const re = encodeURIComponent(f.ruta_archivo);
          return `
                    <div class="file-row">
                        <div class="file-thumb-container">
                            <img src="${ENVP}/api/image-thumbnail/?path=${re}" class="file-thumb" onclick="window.openLightbox(${asigId}, ${idx})">
                        </div>
                        <div class="file-info"><div class="file-name">${escapeHtml(
                          f.nombre_archivo
                        )}</div></div>
                        <div class="file-actions">
                            <button class="btn-tiny green" onclick="window.approvePhoto('${re}', ${asigId}, this)"><i class="fas fa-check"></i></button>
                            <button class="btn-tiny red" onclick="window.rejectPhoto('${re}', ${asigId}, this)"><i class="fas fa-times"></i></button>
                        </div>
                    </div>`;
        })
        .join('');
      if (!AppState.reviewFiles) AppState.reviewFiles = {};
      AppState.reviewFiles[asigId] = files;
    } catch (e) {
      container.innerHTML = 'Error';
    }
  } else if (type === 'validar-tarea') {
    try {
      await SupervisorAPI.validarTarea(data.id);
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  } else if (type === 'rechazar-tarea') {
    try {
      await SupervisorAPI.rechazarTarea(data.id);
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  } else if (type === 'validar-bloque') {
    if (!confirm(`¿Validar todas las tareas de este proyecto?`)) return;
    try {
      await SupervisorAPI.validarBloque(data.map((t) => t.id));
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  } else if (type === 'rechazar-bloque') {
    if (!confirm(`¿Rechazar TODAS las tareas de este proyecto?`)) return;
    try {
      await SupervisorAPI.rechazarBloque(data.map((t) => t.id));
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  }
}

function renderLightbox() {
  const files = AppState.lb_images;
  const idx = AppState.lb_index;
  if (!files || !files[idx]) return;
  const f = files[idx];
  const img = document.getElementById('lightbox-img');
  const vid = document.getElementById('lightbox-video');
  if (f.es_video) {
    img.style.display = 'none';
    vid.style.display = 'block';
    vid.src = `${ENVP}/api/video-stream/?path=${encodeURIComponent(f.ruta_archivo)}`;
  } else {
    vid.style.display = 'none';
    img.style.display = 'block';
    img.src = `${ENVP}/api/image-full/?path=${encodeURIComponent(f.ruta_archivo)}`;
  }
}

function setupExifModalListeners() {
  document.getElementById('btn-exif-manual')?.addEventListener('click', async () => {
    const fecha = document.getElementById('exif-manual-date-only')?.value;
    const hora = document.getElementById('exif-manual-time-only')?.value || '00:00';
    if (!fecha) {
      alert('Seleccione una fecha');
      return;
    }
    const dtStr = `${fecha}T${hora}`;
    try {
      await SupervisorAPI.corregirExif({
        ruta_foto_mala: AppState.exifData.ruta,
        fecha_hora_manual: dtStr,
      });
      document.getElementById('modal-exif-resolver').style.display = 'none';
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  });
  document.getElementById('btn-exif-delete')?.addEventListener('click', async () => {
    if (!confirm('¿Eliminar foto permanentemente?')) return;
    try {
      await SupervisorAPI.eliminarFotoCuarentena({ ruta_foto_mala: AppState.exifData.ruta });
      document.getElementById('modal-exif-resolver').style.display = 'none';
      handleViewChange('tab-validar');
    } catch (e) {
      alert(e.message);
    }
  });
  setupTimePicker();
}

function setupTimePicker() {
  const timeInput = document.getElementById('exif-manual-time-only');
  const panel = document.getElementById('tp-integrated-panel');
  const hoursGrid = document.getElementById('tp-hours-grid');
  const minsGrid = document.getElementById('tp-mins-grid');
  const currentSel = document.getElementById('tp-current-sel');
  if (!timeInput || !panel || !hoursGrid || !minsGrid) return;

  const state = { hour: 0, minute: 0 };

  const cellStyle =
    'padding:6px 0;border:1px solid rgba(255,255,255,0.1);border-radius:6px;background:#222;color:#ddd;font-size:0.9rem;cursor:pointer;text-align:center;';
  const cellSelStyle =
    'padding:6px 0;border:1px solid var(--accent-color);border-radius:6px;background:var(--accent-color);color:#000;font-weight:bold;font-size:0.9rem;cursor:pointer;text-align:center;';

  function paintGrids() {
    hoursGrid.innerHTML = '';
    for (let h = 0; h < 24; h++) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = h.toString().padStart(2, '0');
      btn.style.cssText = h === state.hour ? cellSelStyle : cellStyle;
      btn.addEventListener('click', () => {
        state.hour = h;
        paintGrids();
        updateLabel();
      });
      hoursGrid.appendChild(btn);
    }
    minsGrid.innerHTML = '';
    for (let m = 0; m < 60; m += 5) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.textContent = m.toString().padStart(2, '0');
      btn.style.cssText = m === state.minute ? cellSelStyle : cellStyle;
      btn.addEventListener('click', () => {
        state.minute = m;
        paintGrids();
        updateLabel();
      });
      minsGrid.appendChild(btn);
    }
  }

  function updateLabel() {
    const hStr = state.hour.toString().padStart(2, '0');
    const mStr = state.minute.toString().padStart(2, '0');
    if (currentSel) currentSel.textContent = `${hStr}:${mStr}`;
  }

  function openPanel() {
    const cur = timeInput.value;
    if (cur && cur.includes(':')) {
      const [h, m] = cur.split(':').map((n) => parseInt(n, 10) || 0);
      state.hour = h;
      state.minute = (Math.round(m / 5) * 5) % 60;
    } else {
      const now = new Date();
      state.hour = now.getHours();
      state.minute = (Math.round(now.getMinutes() / 5) * 5) % 60;
    }
    paintGrids();
    updateLabel();
    const rect = timeInput.getBoundingClientRect();
    const panelWidth = 280;
    let left = rect.left;
    if (left + panelWidth > window.innerWidth - 10) left = window.innerWidth - panelWidth - 10;
    if (left < 10) left = 10;
    let top = rect.bottom + 5;
    if (top + 280 > window.innerHeight) top = rect.top - 285;
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.display = 'block';
  }

  function closePanel() {
    panel.style.display = 'none';
  }

  window.confirmTimePicker = function () {
    const hStr = state.hour.toString().padStart(2, '0');
    const mStr = state.minute.toString().padStart(2, '0');
    timeInput.value = `${hStr}:${mStr}`;
    closePanel();
  };

  const openHandler = (e) => {
    e.preventDefault();
    e.stopPropagation();
    openPanel();
  };
  timeInput.addEventListener('click', openHandler);
  timeInput.addEventListener('touchend', openHandler);

  document.addEventListener('click', (e) => {
    if (panel.style.display === 'none') return;
    if (panel.contains(e.target) || e.target === timeInput) return;
    closePanel();
  });
}

// --- REPORTS TAB ---
function setupReportsListeners() {
  const inputSemana = document.getElementById('reporte-fecha-semana');
  const labelSemana = document.getElementById('label-rango-semana');
  if (inputSemana && labelSemana) {
    inputSemana.addEventListener('change', () => {
      if (!inputSemana.value) {
        labelSemana.style.display = 'none';
        return;
      }
      const d = new Date(inputSemana.value + 'T12:00:00');
      const day = d.getDay();
      const diff = d.getDate() - day + (day === 0 ? -6 : 1);
      const monday = new Date(d.setDate(diff));
      const sunday = new Date(new Date(monday).setDate(monday.getDate() + 6));
      const opts = { day: 'numeric', month: 'long' };
      labelSemana.textContent = `Reporte del ${monday.toLocaleDateString(
        'es-ES',
        opts
      )} al ${sunday.toLocaleDateString('es-ES', opts)}`;
      labelSemana.style.display = 'block';
    });
  }

  const inputMes = document.getElementById('reporte-fecha-mes');
  const labelMes = document.getElementById('label-rango-mes');
  if (inputMes && labelMes) {
    inputMes.addEventListener('change', () => {
      if (!inputMes.value) {
        labelMes.style.display = 'none';
        return;
      }
      const d = new Date(inputMes.value + 'T12:00:00');
      const monthName = d.toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
      labelMes.textContent = `Reporte mensual de ${monthName}`;
      labelMes.style.display = 'block';
    });
  }

  document.getElementById('btn-generar-reporte')?.addEventListener('click', generateGlobalReport);

  window.selectReportType = function (type, element) {
    document.querySelectorAll('.report-type-card').forEach((c) => c.classList.remove('active'));
    if (element) element.classList.add('active');

    const hidden = document.getElementById('reporte-tipo');
    if (hidden) hidden.value = type;

    const configPanel = document.getElementById('report-config-panel');
    if (configPanel) {
      configPanel.style.display = 'none';
      void configPanel.offsetWidth;
      configPanel.style.display = 'flex';
    }

    document.querySelectorAll('.report-input-group').forEach((d) => {
      d.style.display = 'none';
    });

    if (type === 'diario') {
      const d = document.getElementById('div-fecha-diario');
      if (d) d.style.display = 'flex';
      const di = document.getElementById('reporte-fecha-diario');
      if (di && !di.value) di.valueAsDate = new Date();
    } else if (type === 'semanal') {
      const d = document.getElementById('div-fecha-semana');
      if (d) d.style.display = 'flex';
    } else if (type === 'mensual') {
      const d = document.getElementById('div-fecha-mes');
      if (d) d.style.display = 'flex';
    } else if (type === 'personalizado') {
      const d = document.getElementById('div-fecha-rango');
      if (d) d.style.display = 'flex';
    }
  };
}

async function generateGlobalReport() {
  const t = document.getElementById('reporte-tipo').value;
  if (!t) return alert('Seleccione un tipo de reporte.');

  let f = null;
  if (t === 'diario') f = document.getElementById('reporte-fecha-diario').value;
  else if (t === 'semanal') f = document.getElementById('reporte-fecha-semana').value;
  else if (t === 'mensual') f = document.getElementById('reporte-fecha-mes').value;
  else if (t === 'personalizado') f = document.getElementById('reporte-fecha-inicio').value;

  if (!f) return alert('Seleccione una fecha o rango válido.');

  const body = { tipo: t, fecha_inicio: f };
  if (t === 'personalizado') {
    body.fecha_fin = document.getElementById('reporte-fecha-fin').value;
    if (!body.fecha_fin) return alert('Seleccione fecha de término.');
  }

  const btn = document.getElementById('btn-generar-reporte');
  const progContainer = document.getElementById('global-report-progress-container');
  const progBar = document.getElementById('global-report-progress-bar');
  const progPercent = document.getElementById('global-report-progress-percent');
  const progStatus = document.getElementById('global-report-progress-status');

  btn.disabled = true;
  progContainer.style.display = 'block';
  progBar.style.width = '0%';
  progPercent.textContent = '0%';
  progStatus.style.color = '';
  progStatus.textContent = 'Enviando petición...';

  try {
    const res = await SupervisorAPI.generarReporteGlobal(body);
    const jobId = res.job_id;

    const checkStatus = async () => {
      try {
        const job = await SupervisorAPI.getJobStatus(jobId);
        if (job.status === 'completed') {
          progBar.style.width = '100%';
          progPercent.textContent = '100%';
          progStatus.textContent = '¡Listo! Descargando...';
          const a = document.createElement('a');
          a.href = job.download_url;
          a.download = '';
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => {
            progContainer.style.display = 'none';
            btn.disabled = false;
          }, 3000);
          return;
        }
        if (job.status === 'failed') {
          progStatus.textContent = 'Error: ' + (job.error_message || 'Fallo desconocido');
          progStatus.style.color = 'var(--danger)';
          btn.disabled = false;
          return;
        }
        progBar.style.width = (job.progress || 0) + '%';
        progPercent.textContent = (job.progress || 0) + '%';
        progStatus.textContent = 'Procesando...';
        setTimeout(checkStatus, 2000);
      } catch (e) {
        console.error('Error polling report status', e);
        setTimeout(checkStatus, 5000);
      }
    };
    checkStatus();
  } catch (e) {
    btn.disabled = false;
    progContainer.style.display = 'none';
    alert(e.message);
  }
}

// --- GLOBAL EXPOSURE FOR HTML HANDLERS ---
function exposeGlobalHandlers() {
  window.toggleAcordeon = (el) => SupervisorUI.toggleAcordeon(el);

  window.expandirValidar = () => {
    document
      .querySelectorAll('#tab-validar .item-sublist')
      .forEach((el) => el.classList.remove('hidden'));
    document
      .querySelectorAll('#tab-validar .category-header')
      .forEach((h) => h.classList.remove('collapsed'));
  };
  window.colapsarValidar = () => {
    document
      .querySelectorAll('#tab-validar .item-sublist')
      .forEach((el) => el.classList.add('hidden'));
    document
      .querySelectorAll('#tab-validar .category-header')
      .forEach((h) => h.classList.add('collapsed'));
  };

  window.openLightbox = (asigId, idx) => {
    const files = AppState.reviewFiles[asigId];
    if (!files) return;
    AppState.lb_images = files;
    AppState.lb_index = idx;
    renderLightbox();
    document.getElementById('lightbox-modal').style.display = 'flex';
  };

  window.moveLightbox = (d) => {
    AppState.lb_index += d;
    if (AppState.lb_index < 0) AppState.lb_index = AppState.lb_images.length - 1;
    if (AppState.lb_index >= AppState.lb_images.length) AppState.lb_index = 0;
    renderLightbox();
  };
  window.lb_close = () => {
    document.getElementById('lightbox-modal').style.display = 'none';
  };
  window.lb_approve = async () => {
    const d = AppState.lb_images[AppState.lb_index];
    if (!d) return;
    try {
      await SupervisorAPI.aprobarFoto({
        ruta_archivo: d.ruta_archivo,
        asignacion_id: d.asignacion_id,
      });
      AppState.lb_images.splice(AppState.lb_index, 1);
      if (AppState.lb_images.length === 0) {
        window.lb_close();
        handleViewChange('tab-validar');
      } else {
        if (AppState.lb_index >= AppState.lb_images.length) AppState.lb_index = 0;
        renderLightbox();
      }
    } catch (e) {
      alert(e.message);
    }
  };
  window.lb_reject = async () => {
    const d = AppState.lb_images[AppState.lb_index];
    if (!d || !confirm('Rechazar?')) return;
    try {
      await SupervisorAPI.rechazarFoto({
        ruta_archivo: d.ruta_archivo,
        asignacion_id: d.asignacion_id,
      });
      AppState.lb_images.splice(AppState.lb_index, 1);
      if (AppState.lb_images.length === 0) {
        window.lb_close();
        handleViewChange('tab-validar');
      } else {
        if (AppState.lb_index >= AppState.lb_images.length) AppState.lb_index = 0;
        renderLightbox();
      }
    } catch (e) {
      alert(e.message);
    }
  };

  window.approvePhoto = async (encodedRuta, asigId, btn) => {
    const ruta = decodeURIComponent(encodedRuta);
    try {
      await SupervisorAPI.aprobarFoto({ ruta_archivo: ruta, asignacion_id: asigId });
      const row = btn?.closest('.file-row');
      if (row) {
        row.style.transition = 'all 0.2s';
        row.style.opacity = '0';
        setTimeout(() => row.remove(), 200);
      }
    } catch (e) {
      alert(e.message);
    }
  };
  window.rejectPhoto = async (encodedRuta, asigId, btn) => {
    const ruta = decodeURIComponent(encodedRuta);
    if (!confirm('Rechazar?')) return;
    try {
      await SupervisorAPI.rechazarFoto({ ruta_archivo: ruta, asignacion_id: asigId });
      const row = btn?.closest('.file-row');
      if (row) {
        row.style.transition = 'all 0.2s';
        row.style.opacity = '0';
        setTimeout(() => row.remove(), 200);
      }
    } catch (e) {
      alert(e.message);
    }
  };

  // --- INFORME HANDLERS ---
  window.g_reportPlanId = null;
  window.g_reportInProgress = false;

  window.onInformePlan = async (planId) => {
    window.g_reportPlanId = planId;
    document.getElementById('modal-report-select').style.display = 'flex';
    document.getElementById('report-select-container').innerHTML = 'Cargando...';
    try {
      const d = await SupervisorAPI.getArchivosPlan(planId);
      window.renderReportSelection(d.archivos);
    } catch (e) {
      alert(e.message);
      document.getElementById('report-select-container').innerHTML =
        '<p style="text-align:center;padding:20px">Error cargando archivos</p>';
    }
  };

  window.renderReportSelection = function (tree) {
    const container = document.getElementById('report-select-container');
    if (!container) return;
    container.innerHTML = '';
    if (!tree || Object.keys(tree).length === 0) {
      container.innerHTML =
        '<p style="text-align:center;padding:20px;color:#666">No hay archivos disponibles para este plan.</p>';
      return;
    }
    const fragment = document.createDocumentFragment();
    Object.keys(tree)
      .sort()
      .forEach(function (projectName) {
        const pDiv = document.createElement('div');
        pDiv.innerHTML = `<h4 style="background:#111;color:#fff;padding:8px;margin-top:15px;border-radius:4px;border-left:3px solid var(--neon)">${escapeHtml(
          projectName
        )}</h4>`;
        fragment.appendChild(pDiv);
        const itemsObj = tree[projectName];
        Object.keys(itemsObj)
          .sort()
          .forEach(function (itemName) {
            const iDiv = document.createElement('div');
            iDiv.innerHTML = `<h5 style="margin:10px 0 5px 5px;color:var(--info);font-size:0.9rem">${escapeHtml(
              itemName
            )}</h5>`;
            const grid = document.createElement('div');
            grid.className = 'photo-grid';
            const filesSorted = itemsObj[itemName].sort((a, b) => a.nombre.localeCompare(b.nombre));
            filesSorted.forEach(function (file) {
              const card = document.createElement('div');
              card.className = 'report-photo-card';
              const encodedPath = encodeURIComponent(file.ruta).replace(/'/g, '%27');
              const thumbUrl = `${ENVP}/api/image-thumbnail/?path=${encodedPath}`;
              const isVideo =
                file.nombre.toLowerCase().endsWith('.mp4') ||
                file.nombre.toLowerCase().endsWith('.mov');
              const imgHtml = isVideo
                ? '<div style="height:80px;background:#000;color:#fff;display:flex;align-items:center;justify-content:center;font-size:0.8rem;border-bottom:1px solid #333">VIDEO</div>'
                : `<img src="${thumbUrl}" loading="lazy" style="width:100%;height:80px;object-fit:cover;display:block" onerror="this.onerror=null;this.src='';this.outerHTML='<div style=\'height:80px;display:flex;align-items:center;justify-content:center;color:#666;font-size:0.7rem;background:#111\'>Error Miniatura</div>'">`;
              card.innerHTML = `
                        <div class="thumb-wrapper" style="position:relative;height:80px;background:#111">
                            ${imgHtml}
                        </div>
                        <div style="padding:4px;font-size:0.7rem;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:#050505">${escapeHtml(
                          file.nombre
                        )}</div>
                        <input type="checkbox" class="report-chk" value="${escapeHtml(
                          file.ruta
                        )}" checked style="position:absolute;top:4px;right:4px;width:18px;height:18px;cursor:pointer;z-index:5">
                    `;
              card.onclick = function (e) {
                if (e.target.type !== 'checkbox') {
                  const chk = card.querySelector('input');
                  chk.checked = !chk.checked;
                  window.updRepCnt();
                }
              };
              card.querySelector('input').onchange = window.updRepCnt;
              grid.appendChild(card);
            });
            iDiv.appendChild(grid);
            fragment.appendChild(iDiv);
          });
      });
    container.appendChild(fragment);
    window.updRepCnt();
  };

  window.updRepCnt = () => {
    const count = document.querySelectorAll('.report-chk:checked').length;
    const msg = document.getElementById('report-count-msg');
    if (msg) msg.textContent = count + ' sel';
  };

  window.toggleAllReportPhotos = (e) => {
    document.querySelectorAll('.report-chk').forEach((c) => {
      c.checked = e.checked;
    });
    window.updRepCnt();
  };

  window.closeReportModal = function () {
    if (window.g_reportInProgress) {
      if (
        !confirm(
          'Hay un informe generándose. Si cierras la ventana no verás el progreso (aunque el servidor seguirá trabajando). ¿Cerrar de todas formas?'
        )
      ) {
        return;
      }
    }
    document.getElementById('modal-report-select').style.display = 'none';
    if (!window.g_reportInProgress) {
      document.getElementById('report-progress-container').style.display = 'none';
      const btn = document.getElementById('btn-generate-final-report');
      if (btn) btn.disabled = false;
    }
  };

  window.generateFinalReport = async () => {
    const selectedFiles = Array.from(document.querySelectorAll('.report-chk:checked')).map(
      (c) => c.value
    );
    if (selectedFiles.length === 0) {
      alert('Seleccione al menos una foto');
      return;
    }
    if (!window.g_reportPlanId) {
      alert('Error interno: ID de plan no encontrado. Cierre y abra el modal de nuevo.');
      return;
    }
    const pContainer = document.getElementById('report-progress-container');
    const pBar = document.getElementById('report-progress-bar');
    const pText = document.getElementById('report-progress-status');
    const pPercent = document.getElementById('report-progress-percent');
    const btn = document.getElementById('btn-generate-final-report');

    btn.disabled = true;
    pContainer.style.display = 'block';
    pBar.style.width = '0%';
    pPercent.textContent = '0%';
    pText.textContent = 'Iniciando generación...';
    window.g_reportInProgress = true;

    try {
      const res = await SupervisorAPI.startResumenPlan(window.g_reportPlanId, selectedFiles);
      const jobId = res.job_id;
      const poll = setInterval(async () => {
        try {
          const status = await SupervisorAPI.getJobStatus(jobId);
          pBar.style.width = status.progress + '%';
          pPercent.textContent = status.progress + '%';
          pText.textContent = 'Procesando imágenes...';
          if (status.status === 'completed') {
            clearInterval(poll);
            window.g_reportInProgress = false;
            pText.textContent = '¡Completado! Descargando...';
            window.location.href = `/api/informes/download-job/${jobId}`;
            setTimeout(() => {
              pContainer.style.display = 'none';
              btn.disabled = false;
            }, 3000);
          } else if (status.status === 'error' || status.status === 'failed') {
            clearInterval(poll);
            window.g_reportInProgress = false;
            alert('Error generando informe: ' + (status.error || 'Desconocido'));
            pContainer.style.display = 'none';
            btn.disabled = false;
          }
        } catch (e) {
          clearInterval(poll);
          window.g_reportInProgress = false;
          pContainer.style.display = 'none';
          btn.disabled = false;
        }
      }, 2000);
    } catch (e) {
      window.g_reportInProgress = false;
      alert('Error al iniciar informe: ' + e.message);
      pContainer.style.display = 'none';
      btn.disabled = false;
    }
  };

  // Attach listener to generate button
  document
    .getElementById('btn-generate-final-report')
    ?.addEventListener('click', window.generateFinalReport);
}

init();
