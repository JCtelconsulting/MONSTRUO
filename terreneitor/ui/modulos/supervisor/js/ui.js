import { SupervisorAPI } from './api.js';
const ENVP = window.location.pathname.startsWith('/dev') ? '/dev' : '';

export const SupervisorUI = {
  Loader: {
    overlay: null,
    _timer: null,
    _delayMs: 350,
    init() {
      this.overlay = document.getElementById('global-loader');
    },
    show(t = 'Procesando...') {
      if (!this.overlay) this.init();
      if (!this.overlay) return;
      clearTimeout(this._timer);
      this._timer = setTimeout(() => {
        this.overlay.querySelector('h3').textContent = t;
        this.overlay.style.display = 'flex';
        this._timer = null;
      }, this._delayMs);
    },
    hide() {
      if (!this.overlay) this.init();
      clearTimeout(this._timer);
      this._timer = null;
      if (this.overlay) this.overlay.style.display = 'none';
    },
  },

  showView(v) {
    document.querySelectorAll('.tab-link').forEach((b) => {
      b.classList.toggle('active', b.dataset.tab === v);
    });
    document.querySelectorAll('.tab-content .tab-pane').forEach((p) => {
      p.classList.toggle('active', p.id === v);
    });
  },

  toggleAcordeon(el) {
    el.classList.toggle('collapsed');
    const next = el.nextElementSibling;
    if (next) next.classList.toggle('hidden');
  },

  naturalSort(a, b) {
    if (!a || !b) return 0;
    const ax = [],
      bx = [];
    const norm = (s) => String(s).toLowerCase().trim();
    norm(a).replace(/(\d+)|(\D+)/g, (_, $1, $2) => {
      ax.push([$1 || Infinity, $2 || '']);
    });
    norm(b).replace(/(\d+)|(\D+)/g, (_, $1, $2) => {
      bx.push([$1 || Infinity, $2 || '']);
    });
    while (ax.length && bx.length) {
      const an = ax.shift(),
        bn = bx.shift();
      const nn = an[0] - bn[0] || an[1].localeCompare(bn[1]);
      if (nn) return nn;
    }
    return ax.length - bx.length;
  },

  normalizeText(t) {
    if (!t) return '';
    return t
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  },

  renderEspecialistas(users, selectedSet, onToggle) {
    const container = document.getElementById('especialistas-grid');
    if (!container) return;
    container.innerHTML = users.length ? '' : '<p class="loading">Cargando especialistas...</p>';

    users.forEach((u) => {
      const isSelected = selectedSet.has(u.id);
      const roleText = u.role === 'SUPERVISOR' ? 'SUP' : 'TER';
      const roleClass = u.role === 'SUPERVISOR' ? 'role-sup' : 'role-ter';

      const card = document.createElement('div');
      card.className = `user-card ${roleClass} ${isSelected ? 'selected' : ''}`;
      card.innerHTML = `
                <i class="fas fa-check-circle check-mark"></i>
                <div class="user-avatar-small">${escapeHtml(
                  (u.name || u.email).substring(0, 2).toUpperCase()
                )}</div>
                <div class="user-name">${escapeHtml(u.name || u.email.split('@')[0])}</div>
                <div class="user-role-tag">${roleText}</div>
            `;
      card.onclick = () => onToggle(u.id);
      container.appendChild(card);
    });
  },

  renderProjectList(projects, state, onSelect) {
    const pl = document.getElementById('project-list');
    if (!pl) return;

    const fClient = document.getElementById('filter-cliente')?.value || '';
    const fMixed = document.getElementById('filter-zona-id')?.value || '';
    const fSearch = this.normalizeText(document.getElementById('search-projects')?.value || '');

    const filtered = projects
      .filter((p) => {
        let pClient = (p.cliente || '(Sin Cliente)').trim();
        if (pClient.toUpperCase() === 'SIN CLIENTE') pClient = '(Sin Cliente)';
        let pArea = (p.area || p.zona || '(Sin Zona)').trim();
        if (pArea.toUpperCase() === 'SIN ZONA') pArea = '(Sin Zona)';

        const matchClient = !fClient || pClient === fClient;
        const matchMixed = !fMixed || pArea === fMixed;
        const pNameNorm = this.normalizeText(p.nombre_pmc || '');
        const matchSearch =
          !fSearch || pNameNorm.includes(fSearch) || this.normalizeText(pClient).includes(fSearch);

        return matchClient && matchMixed && matchSearch;
      })
      .sort((a, b) => this.naturalSort(a.nombre_pmc, b.nombre_pmc));

    const totalItems = filtered.length;
    const pageSize = 20;
    const totalPages = Math.ceil(totalItems / pageSize) || 1;
    if (state.projectPage > totalPages) state.projectPage = totalPages;

    const start = (state.projectPage - 1) * pageSize;
    const visible = filtered.slice(start, start + pageSize);

    pl.innerHTML = visible.length ? '' : '<li class="empty-msg">Sin resultados.</li>';
    visible.forEach((p) => {
      const li = document.createElement('li');
      li.className = `project-card-item ${state.selectedProjectId === p.id ? 'active' : ''}`;
      li.innerHTML = `
                <div class="card-header"><span class="card-title">${escapeHtml(
                  p.nombre_pmc
                )}</span></div>
                <div class="card-meta">
                    ${escapeHtml(
                      p.cliente || 'Sin Cliente'
                    )} <span class="card-separator">•</span> ${escapeHtml(
                      p.area || p.zona || 'Sin Zona'
                    )}
                </div>
            `;
      li.onclick = () => onSelect(p);
      pl.appendChild(li);
    });

    this.renderPagination(totalItems, state.projectPage, totalPages, (p) => {
      state.projectPage = p;
      this.renderProjectList(projects, state, onSelect);
    });
  },

  renderPagination(total, current, totalPages, onChange) {
    const container = document.getElementById('project-pagination');
    if (!container) return;
    container.innerHTML = '';
    if (total === 0) return;

    const prev = document.createElement('button');
    prev.className = 'btn-tiny';
    prev.innerHTML = '<i class="fas fa-chevron-left"></i>';
    prev.disabled = current === 1;
    prev.onclick = () => onChange(current - 1);

    const info = document.createElement('span');
    info.className = 'pagination-info';
    info.textContent = `Página ${current} de ${totalPages}`;

    const next = document.createElement('button');
    next.className = 'btn-tiny';
    next.innerHTML = '<i class="fas fa-chevron-right"></i>';
    next.disabled = current === totalPages;
    next.onclick = () => onChange(current + 1);

    container.appendChild(prev);
    container.appendChild(info);
    container.appendChild(next);
  },

  renderTasks(det, onToggle, currentSel = {}) {
    const il = document.getElementById('item-list');
    if (!il) return;
    il.innerHTML = '';

    const ord = ['EDP', 'INFORME', 'OTROS'];
    const groups = det.grupos || {};
    const groupKeys = Object.keys(groups).sort(
      (a, b) =>
        (ord.indexOf(a) === -1 ? 99 : ord.indexOf(a)) -
        (ord.indexOf(b) === -1 ? 99 : ord.indexOf(b))
    );

    groupKeys.forEach((g) => {
      const cs = groups[g];
      cs.forEach((c) => {
        if (!c.items.length) return;
        const h = document.createElement('div');
        h.className = 'category-header collapsed';
        h.innerHTML = `<span>${escapeHtml(g)} / ${escapeHtml(c.nombre)}</span> <small>(${
          c.items.length
        })</small>`;
        h.onclick = () => this.toggleAcordeon(h);
        il.appendChild(h);

        const u = document.createElement('ul');
        u.className = 'item-sublist hidden';
        c.items.forEach((i) => {
          const li = document.createElement('li');
          li.className = 'item-label';
          const isChecked = !!currentSel[i.id];
          li.innerHTML = `
                        <input type="checkbox" id="i-${i.id}" ${isChecked ? 'checked' : ''}>
                        <label for="i-${
                          i.id
                        }" style="cursor:pointer;flex-grow:1;color:#ccc;margin-left:10px;">${escapeHtml(
                          i.nombre
                        )}</label>
                    `;
          li.querySelector('input').onchange = (e) => onToggle(i, e.target.checked);
          u.appendChild(li);
        });
        il.appendChild(u);
      });
    });
  },

  renderSelectionQueue(selectedItems, onRemove) {
    const q = document.getElementById('selected-items-list');
    if (!q) return;
    q.innerHTML = '';
    Object.values(selectedItems).forEach((item) => {
      const li = document.createElement('li');
      li.innerHTML = `<span>${escapeHtml(
        item.nombre
      )}</span> <i class="fas fa-times remove-btn"></i>`;
      li.querySelector('.remove-btn').onclick = () => onRemove(item.id);
      q.appendChild(li);
    });

    const count = document.getElementById('item-count');
    if (count) count.textContent = `${Object.keys(selectedItems).length} tareas`;

    const btn = document.getElementById('btn-crear-plan');
    if (btn) btn.disabled = Object.keys(selectedItems).length === 0;
  },

  renderPlanesActivos(planes, onAction) {
    const container = document.getElementById('planes-activos-container');
    if (!container) return;
    container.innerHTML = planes.length ? '' : '<p class="empty-msg">No hay planes activos.</p>';

    planes.forEach((p) => {
      const card = document.createElement('div');
      card.className = 'panel-container glass-panel plan-card';
      card.style.marginBottom = '15px';

      // Cuadrilla del plan = unión de los usuarios asignados en sus tareas.
      const crewMap = {};
      (p.asignaciones || []).forEach((a) =>
        (a.usuarios || []).forEach((u) => {
          crewMap[u.id] = u.name || u.username || '?';
        })
      );
      const crewNames = Object.values(crewMap);
      let avatars =
        crewNames
          .map(
            (n) =>
              `<div class="user-avatar-mini" title="${escapeHtml(n)}">${escapeHtml(
                n.substring(0, 2).toUpperCase()
              )}</div>`
          )
          .join('') ||
        '<span style="opacity:0.55;font-size:0.72rem">Sin asignar</span>';

      card.innerHTML = `
                <div class="panel-header collapsed" style="cursor:pointer; display: flex; justify-content: space-between; align-items: center;">
                    <div class="header-main-click" style="flex:1; display:flex; align-items:center;">
                        <h4 class="section-title" style="margin:0"><i class="fas fa-layer-group" style="color:var(--neon)"></i> ${escapeHtml(
                          p.descripcion
                        )}</h4>
                        <span class="pill-outline" style="margin-left:15px">${
                          p.asignaciones.length
                        } tareas</span>
                        <div style="display:flex; gap:8px; margin-left:20px; align-items:center;">
                            ${avatars}
                        </div>
                    </div>
                    <div class="plan-actions" style="display: flex; gap: 10px; align-items: center;" onclick="event.stopPropagation()">
                        <button class="btn-tiny blue btn-edit-crew" title="Editar cuadrilla (quién está asignado)"><i class="fas fa-users"></i></button>
                        <button class="btn-tiny blue btn-add-items" title="Agregar tareas"><i class="fas fa-plus"></i> AGREGAR</button>
                        <button class="btn-tiny green btn-archive" title="Archivar plan"><i class="fas fa-archive"></i></button>
                        <button class="btn-tiny red btn-delete-plan" title="Eliminar plan"><i class="fas fa-trash"></i></button>
                    </div>
                </div>
                <div class="plan-body hidden" style="padding:10px"></div>
            `;

      const headerClick = card.querySelector('.header-main-click');
      const header = card.querySelector('.panel-header');
      const body = card.querySelector('.plan-body');

      headerClick.onclick = () => this.toggleAcordeon(header);

      card.querySelector('.btn-edit-crew').onclick = (e) => {
        e.stopPropagation();
        onAction('edit-crew', p);
      };
      card.querySelector('.btn-add-items').onclick = (e) => {
        e.stopPropagation();
        onAction('add-items', p);
      };
      card.querySelector('.btn-archive').onclick = (e) => {
        e.stopPropagation();
        onAction('archive-plan', p);
      };
      card.querySelector('.btn-delete-plan').onclick = (e) => {
        e.stopPropagation();
        onAction('delete-plan', p);
      };

      // Group by Project
      const projects = {};
      p.asignaciones.forEach((a) => {
        const projectName = a.item?.categoria?.proyecto?.nombre_pmc || 'Sin Proyecto';
        if (!projects[projectName]) projects[projectName] = [];
        projects[projectName].push(a);
      });

      Object.keys(projects)
        .sort()
        .forEach((projectName) => {
          const group = document.createElement('div');
          group.className = 'project-group';
          group.style.borderLeft = '2px solid var(--neon)';
          group.style.paddingLeft = '10px';
          group.style.marginBottom = '10px';
          group.innerHTML = `<div style="font-weight: 800; color: var(--neon); font-size: 0.8rem; margin-bottom: 5px;">${escapeHtml(
            projectName.toUpperCase()
          )}</div>`;

          projects[projectName].forEach((a) => {
            const row = document.createElement('div');
            row.className = 'split-row';
            const isVal = a.estado === 'VALIDADA';
            row.innerHTML = `
                        <div class="col-name">${escapeHtml(a.item.nombre)}</div>
                        <div class="col-actions">
                            <span class="status-${escapeHtml(a.estado)}">${escapeHtml(
                              a.estado.replace('ITEM_', '').replace('_TERRENO', '')
                            )}</span>
                            <div style="display:flex;gap:5px;">
                                <button class="btn-tiny blue btn-reassign" ${
                                  !isVal ? 'disabled' : ''
                                }><i class="fas fa-user-edit"></i></button>
                                <button class="btn-tiny red btn-delete-item" title="Eliminar tarea">X</button>
                            </div>
                        </div>
                    `;
            row.querySelector('.btn-reassign').onclick = () => onAction('reassign-item', a);
            row.querySelector('.btn-delete-item').onclick = () => onAction('delete-item', a);
            group.appendChild(row);
          });
          body.appendChild(group);
        });

      container.appendChild(card);
    });
  },

  renderValidacion(asigs, onAction) {
    const container = document.getElementById('por-validar-container');
    if (!container) return;
    container.innerHTML = asigs.length ? '' : '<p class="empty-msg">Limpio</p>';

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

    Object.keys(mp)
      .sort()
      .forEach((pn) => {
        const ph = document.createElement('div');
        ph.className = 'category-header color-0 collapsed';
        ph.innerHTML = `<span>${escapeHtml(pn)}</span>`;
        container.appendChild(ph);

        const pb = document.createElement('div');
        pb.className = 'item-sublist hidden';
        container.appendChild(pb);

        ph.onclick = () => this.toggleAcordeon(ph);

        Object.keys(mp[pn])
          .sort()
          .forEach((pm) => {
            const mh = document.createElement('div');
            mh.className = 'category-header color-1 collapsed';
            mh.style.marginLeft = '10px';
            mh.innerHTML = `<span>${escapeHtml(
              pm
            )}</span> <button class="btn-tiny green btn-validar-bloque">Validar PMC</button> <button class="btn-tiny red btn-rechazar-bloque">Rechazar PMC</button>`;
            pb.appendChild(mh);

            const mb = document.createElement('div');
            mb.className = 'item-sublist hidden';
            mb.style.marginLeft = '10px';
            pb.appendChild(mb);

            mh.onclick = (e) => {
              if (e.target.tagName !== 'BUTTON') this.toggleAcordeon(mh);
            };
            mh.querySelector('.btn-validar-bloque').onclick = () =>
              onAction('validar-bloque', mp[pn][pm]);
            mh.querySelector('.btn-rechazar-bloque').onclick = () =>
              onAction('rechazar-bloque', mp[pn][pm]);

            mp[pn][pm].forEach((a) => {
              const row = document.createElement('div');
              row.className = 'split-row';
              row.innerHTML = `
                        <div class="col-name">${escapeHtml(a.nombre)}</div>
                        <div class="col-actions">
                            <button class="btn-tiny green btn-val">Validar</button>
                            <button class="btn-tiny red btn-rech">Rechazar</button>
                        </div>
                    `;
              row.querySelector('.btn-val').onclick = () => onAction('validar-tarea', a);
              row.querySelector('.btn-rech').onclick = () => onAction('rechazar-tarea', a);
              mb.appendChild(row);

              const thumbs = document.createElement('div');
              thumbs.className = 'file-row-container';
              mb.appendChild(thumbs);

              onAction('load-thumbs', { asigId: a.id, container: thumbs });
            });
          });
      });
  },

  renderListos(asignaciones, onInforme) {
    const container = document.getElementById('planes-listos-container');
    if (!container) return;
    container.innerHTML = asignaciones.length
      ? ''
      : '<p class="empty-msg">No hay proyectos listos.</p>';

    const clean = (t) =>
      t
        ?.replace(
          /([\u2700-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDC00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF])/g,
          ''
        )
        .trim();

    const mp = {};
    asignaciones.forEach((a) => {
      const pn = clean(a.plan?.descripcion || 'Sin Plan');
      const pm = clean(a.categoria?.proyecto?.nombre_pmc || 'S/P');
      if (!mp[pn]) mp[pn] = { id: a.plan?.id, pros: {} };
      if (!mp[pn].pros[pm]) mp[pn].pros[pm] = [];
      mp[pn].pros[pm].push(a);
    });

    Object.keys(mp)
      .sort()
      .forEach((pn) => {
        const ph = document.createElement('div');
        ph.className = 'category-header color-0 collapsed';
        ph.style.display = 'flex';
        ph.style.justifyContent = 'space-between';
        ph.style.alignItems = 'center';
        const planId = mp[pn].id;
        ph.innerHTML = `<span>${escapeHtml(pn)}</span> ${
          planId
            ? `<button class="btn-tiny blue btn-informe" data-plan-id="${planId}"><i class="fas fa-file-word"></i> Informe</button>`
            : ''
        }`;
        container.appendChild(ph);
        const btnInforme = ph.querySelector('.btn-informe');
        if (btnInforme && onInforme) {
          btnInforme.onclick = (e) => {
            e.stopPropagation();
            onInforme(planId);
          };
        }

        const pb = document.createElement('div');
        pb.className = 'item-sublist hidden';
        container.appendChild(pb);

        ph.onclick = () => this.toggleAcordeon(ph);

        Object.keys(mp[pn].pros)
          .sort()
          .forEach((pm) => {
            const mh = document.createElement('div');
            mh.className = 'category-header color-1 collapsed';
            mh.style.marginLeft = '10px';
            mh.innerHTML = `<span>${escapeHtml(pm)}</span>`;
            pb.appendChild(mh);

            const mb = document.createElement('div');
            mb.className = 'item-sublist hidden';
            mb.style.marginLeft = '10px';
            pb.appendChild(mb);

            mh.onclick = () => this.toggleAcordeon(mh);

            mp[pn].pros[pm].forEach((a) => {
              const row = document.createElement('div');
              row.className = 'split-row';
              row.innerHTML = `<div class="col-name">${escapeHtml(a.nombre)}</div>`;
              mb.appendChild(row);
            });
          });
      });
  },

  renderCuarentena(fotos, onAction) {
    const container = document.getElementById('exif-container');
    if (!container) return;
    container.innerHTML = fotos.length ? '' : '<p class="empty-msg">Limpio</p>';

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

    Object.keys(mp)
      .sort()
      .forEach((pn) => {
        const ph = document.createElement('div');
        ph.className = 'category-header color-0 collapsed';
        ph.innerHTML = `<span>${escapeHtml(pn)}</span>`;
        container.appendChild(ph);

        const pb = document.createElement('div');
        pb.className = 'item-sublist hidden';
        container.appendChild(pb);

        ph.onclick = () => this.toggleAcordeon(ph);

        Object.keys(mp[pn])
          .sort()
          .forEach((pm) => {
            const mh = document.createElement('div');
            mh.className = 'category-header color-1 collapsed';
            mh.style.marginLeft = '10px';
            mh.innerHTML = `<span>${escapeHtml(pm)}</span>`;
            pb.appendChild(mh);

            const mb = document.createElement('div');
            mb.className = 'item-sublist hidden';
            mb.style.marginLeft = '10px';
            pb.appendChild(mb);

            mh.onclick = (e) => {
              if (e.target.tagName !== 'BUTTON') this.toggleAcordeon(mh);
            };

            mp[pn][pm].forEach((f) => {
              const row = document.createElement('div');
              row.className = 'file-row';
              const re = encodeURIComponent(f.ruta_foto_mala).replace(/'/g, '%27');
              row.innerHTML = `
                        <div class="file-thumb-container">
                            <img src="${ENVP}/api/common/view?path=${re}&thumb=1" class="file-thumb" onerror="this.onerror=null;this.src='${ENVP}/api/common/view?path=${re}'">
                        </div>
                        <div class="file-info"><div class="file-name">${escapeHtml(
                          f.item_nombre
                        )}</div><div class="file-name" style="font-size:0.7rem;opacity:0.6">${escapeHtml(
                          f.ruta_foto_mala.split('/').pop()
                        )}</div></div>
                        <div class="file-actions">
                            <button class="btn-tiny green" title="Resolver EXIF"><i class="fas fa-edit"></i></button>
                            <button class="btn-tiny red" title="Eliminar"><i class="fas fa-trash"></i></button>
                        </div>
                    `;
              row.querySelector('.btn-tiny.green').onclick = () =>
                onAction('abrir-modal', {
                  ruta: f.ruta_foto_mala,
                  nombre: f.ruta_foto_mala.split('/').pop(),
                });
              row.querySelector('.btn-tiny.red').onclick = () =>
                onAction('eliminar-foto', { ruta_foto_mala: f.ruta_foto_mala });
              mb.appendChild(row);
            });
          });
      });
  },

  populateFilters(projects) {
    const cSel = document.getElementById('filter-cliente');
    const zSel = document.getElementById('filter-zona-id');
    if (!cSel || !zSel) return;

    const clients = new Set();
    const zones = new Set();
    projects.forEach((p) => {
      if (p.cliente) clients.add(p.cliente.trim());
      const area = p.area || p.zona;
      if (area) zones.add(area.trim());
    });

    const curC = cSel.value;
    const curZ = zSel.value;

    cSel.innerHTML = '<option value="">Todo Cliente</option>';
    Array.from(clients)
      .sort()
      .forEach((c) => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = c;
        cSel.appendChild(opt);
      });
    if (curC) cSel.value = curC;

    zSel.innerHTML = '<option value="">ID o Comuna</option>';
    Array.from(zones)
      .sort()
      .forEach((z) => {
        const opt = document.createElement('option');
        opt.value = opt.textContent = z;
        zSel.appendChild(opt);
      });
    if (curZ) zSel.value = curZ;
  },
};
