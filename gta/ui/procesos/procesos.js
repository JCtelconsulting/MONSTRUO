// Procesos — Biblioteca unificada de procesos del GTA
window.Procesos = (() => {
    let _procesos = [];
    let _areas = [];
    let _areaFiltro = '';
    let _procActivo = null;

    // ── Init ───────────────────────────────────────────────────────────
    async function init(sesion) {
        await _cargarAreas();
        await cargar();
    }

    async function _cargarAreas() {
        try {
            const resp = await window.fetchApi('/api/gta/areas');
            _areas = resp?.items || [];
        } catch (e) { _areas = []; }
    }

    async function cargar() {
        const cont = document.getElementById('procs-content');
        if (!cont) return;
        cont.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;
        try {
            const resp = await GtaApi.getProcesos('');
            _procesos = resp?.items || [];
            _renderPills();
            _render();
        } catch (e) {
            cont.innerHTML = `<div class="gta-empty">Error al cargar procesos: ${e.message || e}</div>`;
        }
    }

    function _renderPills() {
        const pills = document.getElementById('procs-area-pills');
        if (!pills) return;
        const counts = {};
        _procesos.forEach(p => { counts[p.area] = (counts[p.area] || 0) + 1; });
        const activas = _areas.filter(a => a.activo);
        const html = ['<button class="gta-area-pill active" data-area="" onclick="Procesos.filtrarArea(this)">Todas</button>'];
        activas.forEach(a => {
            const c = counts[a.code] || 0;
            html.push(`<button class="gta-area-pill" data-area="${a.code}" onclick="Procesos.filtrarArea(this)">${_esc(a.label)} <span class="gta-pill-count">${c}</span></button>`);
        });
        pills.innerHTML = html.join('');
        if (_areaFiltro) {
            pills.querySelectorAll('.gta-area-pill').forEach(b => {
                b.classList.toggle('active', b.dataset.area === _areaFiltro);
            });
        }
    }

    function filtrarArea(btn) {
        document.querySelectorAll('#procs-area-pills .gta-area-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _areaFiltro = btn.dataset.area || '';
        _render();
    }

    function _filtered() {
        return _procesos.filter(p => !_areaFiltro || p.area === _areaFiltro);
    }

    function _subareaLabel(areaCode, subCode) {
        if (!subCode) return '';
        const a = _areas.find(x => x.code === areaCode);
        const s = a?.subareas?.find(x => x.code === subCode);
        return s ? s.label : subCode;
    }

    function _areaLabel(code) {
        const a = _areas.find(x => x.code === code);
        return a ? a.label : code;
    }

    // ── Render principal: agrupado por área → subárea ─────────────────
    function _render() {
        const cont = document.getElementById('procs-content');
        const counter = document.getElementById('procs-counter');
        if (!cont) return;

        const list = _filtered();
        if (counter) counter.textContent = `${list.length} proceso${list.length === 1 ? '' : 's'}`;

        const porArea = {};
        list.forEach(p => {
            const a = p.area || '_';
            const s = p.subarea_code || '_';
            porArea[a] = porArea[a] || {};
            porArea[a][s] = porArea[a][s] || [];
            porArea[a][s].push(p);
        });

        // Si hay un filtro de área activo, solo muestra esa.
        // Si no, muestra todas las áreas activas (con o sin procesos).
        const activas = _areas.filter(a => a.activo);
        const orderedAreas = _areaFiltro
            ? [_areaFiltro]
            : (activas.length ? activas.map(a => a.code) : Object.keys(porArea).sort());

        // Meter cualquier área que esté en porArea pero no en orderedAreas
        Object.keys(porArea).forEach(c => {
            if (!orderedAreas.includes(c)) orderedAreas.push(c);
        });

        const html = orderedAreas.map(code => {
            const subgroups = porArea[code] || {};
            const subKeys = Object.keys(subgroups).sort((a, b) => {
                if (a === '_') return -1;
                if (b === '_') return 1;
                return a.localeCompare(b);
            });

            const blocks = subKeys.length ? subKeys.map(subCode => {
                const items = subgroups[subCode];
                const subTitle = subCode === '_' ? '' :
                    `<h5 class="gta-doc-subgroup-title"><i class="fas fa-folder"></i> ${_esc(_subareaLabel(code, subCode))} <span class="gta-pill-count">${items.length}</span></h5>`;
                return `
                    <div class="gta-doc-subgroup">
                        ${subTitle}
                        <div class="gta-doc-list">${items.map(_procRow).join('')}</div>
                    </div>
                `;
            }).join('') : '<p class="gta-section-help">Sin procesos cargados todavía.</p>';

            return `
                <div class="gta-doc-area">
                    <h4 class="gta-doc-area-title">
                        <i class="fas fa-layer-group"></i> ${_esc(_areaLabel(code))}
                    </h4>
                    ${blocks}
                </div>
            `;
        }).join('');

        cont.innerHTML = html || '<div class="gta-empty">Sin áreas activas.</div>';
    }

    function _procRow(p) {
        const tieneArchivo = !!p.tiene_archivo;
        const tieneDef = !!p.tiene_definicion;
        const quiebres = Number(p.quiebres_abiertos || 0);
        const flujos = Number(p.flujos_count || 0);
        return `
            <div class="gta-doc-row gta-proc-row" onclick="Procesos.abrir(${p.id})">
                <div class="gta-doc-icon"><i class="fas ${_esc(p.icono || 'fa-file')}"></i></div>
                <div class="gta-doc-info">
                    <div class="gta-doc-name">${_esc(p.nombre)}</div>
                    <div class="gta-doc-meta">
                        ${tieneArchivo ? '<span class="gta-proc-badge has-file" title="Tiene archivo descriptivo"><i class="fas fa-file"></i> Doc</span>' : ''}
                        ${tieneDef ? '<span class="gta-proc-badge has-def" title="Tiene definición ejecutable"><i class="fas fa-cogs"></i> Ejecutable</span>' : ''}
                        ${quiebres ? `<span class="gta-proc-badge has-quiebre" title="${quiebres} quiebres abiertos"><i class="fas fa-flag"></i> ${quiebres}</span>` : ''}
                        ${flujos ? `<span class="gta-proc-badge"><i class="fas fa-list-check"></i> ${flujos}</span>` : ''}
                        ${p.descripcion ? `<span class="gta-proc-desc">${_esc(p.descripcion).slice(0, 80)}${p.descripcion.length > 80 ? '…' : ''}</span>` : ''}
                    </div>
                </div>
                <i class="fas fa-chevron-right" style="color:var(--text-soft); opacity:0.5;"></i>
            </div>
        `;
    }

    // ── Modal detalle (vista + edición) ───────────────────────────────
    let _modoEdit = false;
    let _pasosEdit = [];
    let _camposFormEdit = [];

    async function abrir(procId) {
        _modoEdit = false;
        const modal = document.getElementById('modal-proceso');
        const body = document.getElementById('proc-modal-body');
        const footer = document.getElementById('proc-modal-footer');
        document.getElementById('proc-modal-titulo').textContent = 'Cargando...';
        document.getElementById('proc-modal-eyebrow').textContent = `Proceso #${procId}`;
        body.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i></div>`;
        footer.innerHTML = '';
        modal.classList.add('is-open');

        try {
            const proc = await GtaApi.getProceso(procId);
            _procActivo = proc;
            _renderModal(proc);
        } catch (e) {
            body.innerHTML = `<div class="gta-empty">Error al cargar el proceso.</div>`;
        }
    }

    function cerrarModal() {
        document.getElementById('modal-proceso')?.classList.remove('is-open');
        _procActivo = null;
        _modoEdit = false;
        _pasosEdit = [];
    }

    function entrarModoEdicion() {
        if (!_procActivo) return;
        _modoEdit = true;
        _pasosEdit = (_procActivo.pasos_definicion || []).map((p, i) => ({
            orden: p.orden || (i + 1),
            titulo: p.titulo || p.nombre || '',
            descripcion: p.descripcion || '',
            area_code: p.area_code || p.area || '',
            subarea_code: p.subarea_code || null,
            sla_horas: p.sla_horas || 24,
            depende_de: Array.isArray(p.depende_de) ? p.depende_de : [],
            // Por default los pasos son bloqueantes (los que dependen de él
            // esperan a que se cierre). Marcarlo como false permite que los
            // siguientes corran en paralelo sin esperar a éste.
            bloqueante: p.bloqueante !== false,
        }));
        _camposFormEdit = _normalizarCamposForm(_procActivo.campos_formulario);
        _renderModal(_procActivo);
    }

    function salirModoEdicion() {
        _modoEdit = false;
        _pasosEdit = [];
        _renderModal(_procActivo);
    }

    function _renderModal(p) {
        document.getElementById('proc-modal-titulo').textContent = p.nombre || 'Proceso';
        const breadcrumb = `${_areaLabel(p.area)}${p.subarea_code ? ' / ' + _subareaLabel(p.area, p.subarea_code) : ''} · v${p.version || 1}`;
        document.getElementById('proc-modal-eyebrow').textContent = breadcrumb;

        if (_modoEdit) {
            _renderModalEdit(p);
        } else {
            _renderModalView(p);
        }
    }

    function _renderModalView(p) {
        const pasos = p.pasos_definicion || [];
        const flujos = p.flujos || [];
        const quiebres = p.quiebres || [];
        const comentarios = p.comentarios || [];
        const m = p.metricas || {};

        const estadoBadge = _estadoBadge(p.estado);

        const pasosHtml = pasos.length ? `
            <div class="gta-pipeline" style="margin-top:8px;">
                ${pasos.map((paso, idx) => `
                    <div class="gta-pipe-tarea sla-cyan">
                        <div class="gta-pipe-num">${paso.orden || (idx + 1)}</div>
                        <div class="gta-pipe-body">
                            <div class="gta-pipe-header">
                                <h5>${_esc(paso.titulo || paso.nombre || 'Paso ' + (idx + 1))}</h5>
                            </div>
                            ${paso.descripcion ? `<p class="gta-pipe-desc">${_esc(paso.descripcion)}</p>` : ''}
                            <div class="gta-pipe-meta">
                                <span><i class="fas fa-layer-group"></i> ${_esc(_areaLabel(paso.area_code || paso.area || '-'))}${paso.subarea_code ? ' / ' + _esc(_subareaLabel(paso.area_code || paso.area, paso.subarea_code)) : ''}</span>
                                <span><i class="fas fa-clock"></i> ${paso.sla_horas || 0}h</span>
                                ${(paso.depende_de || []).length ? `<span><i class="fas fa-link"></i> Depende de: ${paso.depende_de.join(', ')}</span>` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        ` : `
            <div class="gta-empty-pasos">
                <i class="fas fa-stream"></i>
                <p><strong>Este proceso no tiene pasos definidos todavía.</strong></p>
                <p class="gta-section-help">Apretá <em>Editar</em> para construir la fuente de la verdad.</p>
            </div>
        `;

        const flujosHtml = flujos.length ? flujos.map(f => `
            <div class="gta-doc-row" style="cursor:default;">
                <div class="gta-doc-icon"><i class="fas fa-list-check"></i></div>
                <div class="gta-doc-info">
                    <div class="gta-doc-name">${_esc(f.titulo)}</div>
                    <div class="gta-doc-meta">
                        <span class="gta-tarea-estado estado-${f.estado}">${f.estado}</span>
                        <span><i class="fas fa-user"></i> ${_esc(f.iniciado_por)}</span>
                        <span><i class="fas fa-list"></i> ${f.completadas}/${f.total_tareas}</span>
                    </div>
                </div>
            </div>
        `).join('') : '<p class="gta-section-help">No se ha ejecutado todavía.</p>';

        const quiebresHtml = quiebres.length ? quiebres.map(q => `
            <div class="gta-doc-row" style="cursor:default;">
                <div class="gta-doc-icon" style="background:rgba(255,51,51,0.1); color:var(--danger);"><i class="fas fa-flag"></i></div>
                <div class="gta-doc-info">
                    <div class="gta-doc-name">${_esc(q.descripcion).slice(0, 80)}</div>
                    <div class="gta-doc-meta">
                        <span class="gta-tarea-estado estado-${q.estado === 'abierto' ? 'vencida' : 'completada'}">${q.estado}</span>
                        <span><i class="fas fa-layer-group"></i> ${_esc(_areaLabel(q.area))}</span>
                        <span><i class="fas fa-user"></i> ${_esc(q.reportado_por)}</span>
                    </div>
                </div>
            </div>
        `).join('') : '<p class="gta-section-help">Sin quiebres registrados.</p>';

        const comentariosHtml = comentarios.length ? comentarios.map(c => `
            <div class="gta-evento-item">
                <div class="gta-evento-icon"><i class="fas ${c.tipo === 'cambio' ? 'fa-pen' : c.tipo === 'decision' ? 'fa-gavel' : 'fa-comment'}"></i></div>
                <div class="gta-evento-body">
                    <div class="gta-evento-msg">${_esc(c.texto)}</div>
                    <div class="gta-evento-meta">${_esc(c.autor)} · ${new Date(c.created_at).toLocaleString('es-CL')}</div>
                </div>
            </div>
        `).join('') : '<p class="gta-section-help">Sin notas todavía.</p>';

        const iniciarBtn = pasos.length && p.estado === 'activo'
            ? `<button class="btn-primary" onclick="Procesos.iniciarFlujo(${p.id})"><i class="fas fa-rocket"></i> Iniciar flujo</button>`
            : '';

        const guiaSection = p.archivo_path
            ? `<div class="gta-guia-ref">
                  <div class="gta-guia-ref-head">
                    <span class="gta-guia-eyebrow"><i class="fas fa-paperclip"></i> Guía original</span>
                    <span class="gta-section-help" style="font-size:0.78rem;">Documento de referencia que se usó para construir esta definición. <strong>No es la fuente de la verdad</strong> — los pasos lo son.</span>
                  </div>
                  <div class="gta-guia-ref-actions">
                    <button class="btn-secondary" onclick="Procesos.abrirDocPreview('${_esc(p.archivo_path)}')">
                        <i class="fas fa-eye"></i> Ver
                    </button>
                    <a href="/api/gta/catalogo/download?path=${encodeURIComponent(p.archivo_path)}" class="btn-secondary" download>
                        <i class="fas fa-download"></i> Descargar
                    </a>
                  </div>
                  <div class="gta-guia-path"><code>${_esc(p.archivo_path)}</code></div>
              </div>`
            : `<p class="gta-section-help">Sin guía de referencia adjunta.</p>`;

        const body = document.getElementById('proc-modal-body');
        body.innerHTML = `
            <div class="gta-flujo-summary">
                <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px;">
                    ${estadoBadge}
                </div>
                <div><strong>${_esc(p.descripcion || 'Sin descripción')}</strong></div>
                ${iniciarBtn ? `<div style="margin-top:10px;">${iniciarBtn}</div>` : ''}
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:18px;">
                <i class="fas fa-bullseye"></i> Fuente de la verdad — pasos del proceso
            </h4>
            ${pasosHtml}

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-chart-line"></i> Métricas
            </h4>
            <div class="gta-flujo-summary">
                <div style="display:flex; gap:14px; flex-wrap:wrap; font-size:0.85rem; color:var(--text-soft);">
                    <span><i class="fas fa-clock"></i> SLA esperado: ${m.sla_horas_total || 0}h</span>
                    <span><i class="fas fa-stopwatch"></i> Promedio real: ${m.prom_horas != null ? Math.round(m.prom_horas) + 'h' : '—'}</span>
                    <span><i class="fas fa-list-check"></i> Flujos completados: ${m.flujos_completados || 0}</span>
                </div>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-list-check"></i> Flujos ejecutados (${flujos.length})
            </h4>
            <div>${flujosHtml}</div>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-flag"></i> Quiebres registrados (${quiebres.length})
            </h4>
            <div>${quiebresHtml}</div>
            <button class="btn-secondary" style="margin-top:8px;" onclick="Procesos.abrirQuiebre(${p.id})">
                <i class="fas fa-flag"></i> Reportar nuevo quiebre
            </button>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-comments"></i> Notas y decisiones
            </h4>
            <div class="gta-flujo-timeline">${comentariosHtml}</div>
            <div style="margin-top:10px; display:flex; gap:8px;">
                <input type="text" id="proc-comentario-texto" class="input-dark" placeholder="Agregar nota...">
                <button class="btn-secondary" onclick="Procesos.agregarNota()">
                    <i class="fas fa-plus"></i> Agregar
                </button>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:28px; opacity:0.75;">
                <i class="fas fa-paperclip"></i> Guía de referencia
            </h4>
            ${guiaSection}
        `;

        const footer = document.getElementById('proc-modal-footer');
        footer.innerHTML = `
            <button class="btn-secondary" onclick="Procesos.cerrarModal()">Cerrar</button>
            <button class="btn-primary" onclick="Procesos.entrarModoEdicion()">
                <i class="fas fa-pen"></i> Editar
            </button>
        `;
    }

    function _estadoBadge(estado) {
        const e = (estado || 'activo').toLowerCase();
        const map = {
            borrador: '<span class="gta-tarea-estado estado-pendiente"><i class="fas fa-pencil"></i> Borrador</span>',
            activo:   '<span class="gta-tarea-estado estado-completada"><i class="fas fa-check-circle"></i> Activo</span>',
            archivado:'<span class="gta-tarea-estado estado-vencida" style="opacity:0.6;"><i class="fas fa-archive"></i> Archivado</span>',
        };
        return map[e] || `<span class="gta-tarea-estado">${_esc(e)}</span>`;
    }

    function _renderModalEdit(p) {
        const activas = _areas.filter(a => a.activo);
        const subareasDelArea = (() => {
            const a = _areas.find(x => x.code === (p._editArea ?? p.area));
            return (a?.subareas || []).filter(s => s.activo);
        })();

        const estadoActual = (p.estado || 'activo').toLowerCase();

        const body = document.getElementById('proc-modal-body');
        body.innerHTML = `
            <div class="field">
                <label>Nombre del proceso *</label>
                <input type="text" id="ed-nombre" class="input-dark" value="${_esc(p.nombre || '')}">
            </div>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <div class="field" style="flex:1;">
                    <label>Área *</label>
                    <select id="ed-area" class="input-dark" onchange="Procesos._refreshSubareas()">
                        ${activas.map(a => `<option value="${a.code}" ${p.area === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('')}
                    </select>
                </div>
                <div class="field" style="flex:1;">
                    <label>Subárea (opcional)</label>
                    <select id="ed-subarea" class="input-dark">
                        <option value="">— Sin subárea —</option>
                        ${subareasDelArea.map(s => `<option value="${s.code}" ${p.subarea_code === s.code ? 'selected' : ''}>${_esc(s.label)}</option>`).join('')}
                    </select>
                </div>
                <div class="field" style="flex:1;">
                    <label>Estado</label>
                    <select id="ed-estado" class="input-dark">
                        <option value="borrador" ${estadoActual === 'borrador' ? 'selected' : ''}>Borrador</option>
                        <option value="activo" ${estadoActual === 'activo' ? 'selected' : ''}>Activo</option>
                        <option value="archivado" ${estadoActual === 'archivado' ? 'selected' : ''}>Archivado</option>
                    </select>
                </div>
            </div>
            <div class="field" style="margin-top:10px;">
                <label>Descripción breve</label>
                <textarea id="ed-desc" class="input-dark" rows="2">${_esc(p.descripcion || '')}</textarea>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:18px;">
                <i class="fas fa-bullseye"></i> Pasos — fuente de la verdad
            </h4>
            <p class="gta-section-help">
                Arrastrá los pasos por el ícono <i class="fas fa-grip-vertical"></i> para reordenarlos.
                Cada paso detona una tarea para el área/subárea indicada cuando se ejecuta el flujo.
                Las dependencias usan el número de orden (ej: <code>1,2</code>).
                Marcá <strong>bloqueante</strong> si los pasos siguientes deben esperar a que se cierre.
            </p>
            <div id="ed-pasos" class="gta-flujo-tareas-edit"></div>
            <button class="btn-secondary" onclick="Procesos._agregarPasoEdit()" style="margin-top:8px;">
                <i class="fas fa-plus"></i> Agregar paso
            </button>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-clipboard-list"></i> Formulario al iniciar el flujo
            </h4>
            <p class="gta-section-help">
                Datos que se piden al apretar <em>Iniciar flujo</em>. Si un campo está marcado
                como obligatorio, el flujo no arranca sin completarlo.
            </p>
            <div id="ed-campos-form" class="gta-campos-form-edit"></div>
            <button class="btn-secondary" onclick="Procesos._agregarCampoForm()" style="margin-top:8px;">
                <i class="fas fa-plus"></i> Agregar campo
            </button>
        `;
        _renderPasosEdit();
        _renderCamposFormEdit();

        const footer = document.getElementById('proc-modal-footer');
        footer.innerHTML = `
            <button class="btn-secondary" onclick="Procesos.salirModoEdicion()">Cancelar</button>
            <button class="btn-primary" onclick="Procesos.guardarEdicion()">
                <i class="fas fa-save"></i> Guardar cambios
            </button>
        `;
    }

    function _refreshSubareas() {
        const areaCode = document.getElementById('ed-area')?.value || '';
        const a = _areas.find(x => x.code === areaCode);
        const subs = (a?.subareas || []).filter(s => s.activo);
        const subSel = document.getElementById('ed-subarea');
        if (!subSel) return;
        subSel.innerHTML = '<option value="">— Sin subárea —</option>' +
            subs.map(s => `<option value="${s.code}">${_esc(s.label)}</option>`).join('');
    }

    function _renderPasosEdit() {
        const cont = document.getElementById('ed-pasos');
        if (!cont) return;
        const activas = _areas.filter(a => a.activo);
        cont.innerHTML = _pasosEdit.map((t, idx) => {
            const area = _areas.find(a => a.code === t.area_code);
            const subs = (area?.subareas || []).filter(s => s.activo);
            return `
            <div class="gta-paso-edit-row" draggable="true" data-idx="${idx}"
                 ondragstart="Procesos._dragStart(event, ${idx})"
                 ondragover="Procesos._dragOver(event)"
                 ondragleave="Procesos._dragLeave(event)"
                 ondrop="Procesos._drop(event, ${idx})"
                 ondragend="Procesos._dragEnd(event)">
                <div class="gta-paso-edit-handle" title="Arrastrar para reordenar">
                    <i class="fas fa-grip-vertical"></i>
                </div>
                <div class="gta-paso-edit-num">#${t.orden}</div>
                <div class="gta-paso-edit-fields">
                    <input type="text" class="input-dark" placeholder="Título del paso *"
                           value="${_esc(t.titulo)}" oninput="Procesos._setPasoEdit(${idx}, 'titulo', this.value)">
                    <textarea class="input-dark" rows="2" placeholder="Instrucciones / descripción para quien recibe la tarea (opcional)"
                              oninput="Procesos._setPasoEdit(${idx}, 'descripcion', this.value)">${_esc(t.descripcion || '')}</textarea>
                    <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <select class="input-dark" style="flex:2; min-width:140px;" onchange="Procesos._setPasoArea(${idx}, this.value)">
                            <option value="">— Área *</option>
                            ${activas.map(a => `<option value="${a.code}" ${t.area_code === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('')}
                        </select>
                        <select class="input-dark" style="flex:2; min-width:140px;" onchange="Procesos._setPasoEdit(${idx}, 'subarea_code', this.value || null)">
                            <option value="">— Subárea (opcional) —</option>
                            ${subs.map(s => `<option value="${s.code}" ${t.subarea_code === s.code ? 'selected' : ''}>${_esc(s.label)}</option>`).join('')}
                        </select>
                        <input type="number" class="input-dark" min="1" max="999" style="width:80px;"
                               value="${t.sla_horas}" placeholder="SLA h"
                               oninput="Procesos._setPasoEdit(${idx}, 'sla_horas', parseInt(this.value, 10) || 24)"
                               title="SLA en horas">
                        <input type="text" class="input-dark" placeholder="Depende de #"
                               value="${(t.depende_de || []).join(',')}" style="width:110px;"
                               oninput="Procesos._setDepsEdit(${idx}, this.value)"
                               title="Números de paso de los que depende, separados por coma (ej: 1,2)">
                    </div>
                    <label class="gta-paso-edit-bloqueante" title="Si está marcado, los pasos que dependan de éste esperan a que se cierre antes de empezar.">
                        <input type="checkbox" ${t.bloqueante !== false ? 'checked' : ''}
                               onchange="Procesos._setPasoEdit(${idx}, 'bloqueante', this.checked)">
                        <span>Bloqueante (los siguientes esperan a que se cierre)</span>
                    </label>
                </div>
                <button class="btn-sm btn-danger" onclick="Procesos._quitarPasoEdit(${idx})" title="Quitar paso">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        }).join('');
    }

    function _agregarPasoEdit() {
        _pasosEdit.push({
            orden: _pasosEdit.length + 1,
            titulo: '',
            descripcion: '',
            area_code: '',
            subarea_code: null,
            sla_horas: 24,
            depende_de: [],
            bloqueante: true,   // por default los pasos bloquean a sus siguientes
        });
        _renderPasosEdit();
    }

    function _setPasoEdit(idx, k, v) {
        if (_pasosEdit[idx]) _pasosEdit[idx][k] = v;
    }

    function _setPasoArea(idx, areaCode) {
        // Cambiar de área resetea la subárea (las subáreas son hijas del área)
        if (!_pasosEdit[idx]) return;
        _pasosEdit[idx].area_code = areaCode;
        _pasosEdit[idx].subarea_code = null;
        _renderPasosEdit();
    }

    function _setDepsEdit(idx, raw) {
        if (!_pasosEdit[idx]) return;
        _pasosEdit[idx].depende_de = (raw || '').split(',').map(s => parseInt(s.trim(), 10)).filter(Boolean);
    }
    function _quitarPasoEdit(idx) {
        _pasosEdit.splice(idx, 1);
        _pasosEdit.forEach((p, i) => p.orden = i + 1);
        _renderPasosEdit();
    }

    // ── Drag & Drop de pasos ─────────────────────────────────────────────
    let _dragSrcIdx = null;

    function _dragStart(ev, idx) {
        _dragSrcIdx = idx;
        ev.dataTransfer.effectAllowed = 'move';
        // Hack para Firefox: setData es obligatorio o el drag no se inicia
        try { ev.dataTransfer.setData('text/plain', String(idx)); } catch {}
        ev.currentTarget.classList.add('is-dragging');
    }

    function _dragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = 'move';
        ev.currentTarget.classList.add('is-drag-over');
    }

    function _dragLeave(ev) {
        ev.currentTarget.classList.remove('is-drag-over');
    }

    function _drop(ev, dstIdx) {
        ev.preventDefault();
        ev.currentTarget.classList.remove('is-drag-over');
        if (_dragSrcIdx === null || _dragSrcIdx === dstIdx) return;
        const moved = _pasosEdit.splice(_dragSrcIdx, 1)[0];
        _pasosEdit.splice(dstIdx, 0, moved);
        _pasosEdit.forEach((p, i) => p.orden = i + 1);
        _dragSrcIdx = null;
        _renderPasosEdit();
    }

    function _dragEnd(ev) {
        ev.currentTarget.classList.remove('is-dragging');
        document.querySelectorAll('.gta-paso-edit-row.is-drag-over')
            .forEach(el => el.classList.remove('is-drag-over'));
        _dragSrcIdx = null;
    }

    // ── Edición de campos del formulario obligatorio ─────────────────────

    function _renderCamposFormEdit() {
        const cont = document.getElementById('ed-campos-form');
        if (!cont) return;
        if (!_camposFormEdit.length) {
            cont.innerHTML = '<p class="gta-section-help" style="opacity:0.6;">Sin campos definidos. El flujo arranca sin pedir datos.</p>';
            return;
        }

        // Lista de campos tipo select para el dropdown "depende de"
        const camposSelect = _camposFormEdit
            .map((c, i) => ({ ...c, idx: i }))
            .filter(c => c.tipo === 'select' && c.key);

        cont.innerHTML = _camposFormEdit.map((c, idx) => {
            // Header: etiqueta, key, tipo
            const headerHtml = `
                <div style="display:flex; gap:8px;">
                    <input type="text" class="input-dark" placeholder="Etiqueta visible *" style="flex:2;"
                           value="${_esc(c.label || '')}"
                           oninput="Procesos._setCampoForm(${idx}, 'label', this.value)">
                    <input type="text" class="input-dark" placeholder="key (snake_case)" style="flex:1;"
                           value="${_esc(c.key || '')}"
                           oninput="Procesos._setCampoForm(${idx}, 'key', this.value.replace(/[^a-z0-9_]/gi, '_').toLowerCase())">
                    <select class="input-dark" style="width:170px;"
                            onchange="Procesos._setCampoTipo(${idx}, this.value)">
                        <option value="texto" ${c.tipo === 'texto' ? 'selected' : ''}>Texto</option>
                        <option value="textarea" ${c.tipo === 'textarea' ? 'selected' : ''}>Texto largo</option>
                        <option value="numero" ${c.tipo === 'numero' ? 'selected' : ''}>Número</option>
                        <option value="fecha" ${c.tipo === 'fecha' ? 'selected' : ''}>Fecha</option>
                        <option value="select" ${c.tipo === 'select' ? 'selected' : ''}>Lista</option>
                        <option value="select_dependiente" ${c.tipo === 'select_dependiente' ? 'selected' : ''}>Lista dependiente</option>
                    </select>
                </div>
            `;

            // Bloque específico por tipo
            let bloqueTipo = '';
            if (c.tipo === 'select') {
                bloqueTipo = `
                    <input type="text" class="input-dark" placeholder="Opciones separadas por coma (ej: si,no,n/a)" style="margin-top:6px;"
                           value="${_esc((c.opciones || []).join(','))}"
                           oninput="Procesos._setCampoOpciones(${idx}, this.value)">
                `;
            } else if (c.tipo === 'select_dependiente') {
                // Selector de campo padre
                const padreSelect = `
                    <select class="input-dark" style="margin-top:6px;"
                            onchange="Procesos._setCampoDependeDe(${idx}, this.value)">
                        <option value="">— Depende de qué campo —</option>
                        ${camposSelect.map(p => `<option value="${_esc(p.key)}" ${c.depende_de === p.key ? 'selected' : ''}>${_esc(p.label || p.key)} (${_esc(p.key)})</option>`).join('')}
                    </select>
                `;

                // Editor de opciones por valor del padre
                let opcionesPorValorHtml = '';
                if (c.depende_de) {
                    const padre = _camposFormEdit.find(x => x.key === c.depende_de);
                    const valoresPadre = (padre?.opciones || []);
                    if (!valoresPadre.length) {
                        opcionesPorValorHtml = `
                            <p class="gta-section-help" style="margin-top:6px; opacity:0.7;">
                                El campo padre <code>${_esc(c.depende_de)}</code> no tiene opciones aún.
                                Agregalas primero al padre y vuelve aquí.
                            </p>
                        `;
                    } else {
                        opcionesPorValorHtml = `
                            <div style="margin-top:6px;">
                                <p class="gta-section-help" style="margin:0 0 6px 0;">
                                    Opciones disponibles según el valor del padre:
                                </p>
                                ${valoresPadre.map(val => `
                                    <div style="display:flex; gap:8px; margin-bottom:4px; align-items:center;">
                                        <span style="min-width:160px; font-size:12px; color:var(--text-soft); font-weight:600;">${_esc(val)}:</span>
                                        <input type="text" class="input-dark" style="flex:1;"
                                               placeholder="Servicios para esta línea, separados por coma"
                                               value="${_esc(((c.opciones_por_valor || {})[val] || []).join(','))}"
                                               oninput="Procesos._setCampoOpcionesPorValor(${idx}, '${_esc(val).replace(/'/g, '&#39;')}', this.value)">
                                    </div>
                                `).join('')}
                            </div>
                        `;
                    }
                }

                bloqueTipo = padreSelect + opcionesPorValorHtml;
            }

            return `
                <div class="gta-campo-form-row">
                    <div class="gta-campo-form-num">#${idx + 1}</div>
                    <div class="gta-campo-form-fields">
                        ${headerHtml}
                        ${bloqueTipo}
                        <input type="text" class="input-dark" placeholder="Texto de ayuda (opcional)" style="margin-top:6px;"
                               value="${_esc(c.ayuda || '')}"
                               oninput="Procesos._setCampoForm(${idx}, 'ayuda', this.value)">
                        <label class="gta-paso-edit-bloqueante" style="margin-top:4px;">
                            <input type="checkbox" ${c.requerido !== false ? 'checked' : ''}
                                   onchange="Procesos._setCampoForm(${idx}, 'requerido', this.checked)">
                            <span>Obligatorio (no deja completar la tarea sin este dato)</span>
                        </label>
                    </div>
                    <button class="btn-sm btn-danger" onclick="Procesos._quitarCampoForm(${idx})" title="Quitar campo">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
        }).join('');
    }

    function _agregarCampoForm() {
        const n = _camposFormEdit.length + 1;
        _camposFormEdit.push({
            key: `campo_${n}`,
            label: '',
            tipo: 'texto',
            opciones: [],
            requerido: true,
            ayuda: '',
        });
        _renderCamposFormEdit();
    }

    function _setCampoForm(idx, k, v) {
        if (_camposFormEdit[idx]) _camposFormEdit[idx][k] = v;
    }

    function _setCampoTipo(idx, tipo) {
        if (!_camposFormEdit[idx]) return;
        const c = _camposFormEdit[idx];
        c.tipo = tipo;
        // Inicializar campos auxiliares según el tipo nuevo
        if (tipo === 'select' && !Array.isArray(c.opciones)) {
            c.opciones = [];
        }
        if (tipo === 'select_dependiente') {
            if (!c.depende_de) c.depende_de = '';
            if (!c.opciones_por_valor) c.opciones_por_valor = {};
        }
        _renderCamposFormEdit();
    }

    function _setCampoOpciones(idx, raw) {
        if (!_camposFormEdit[idx]) return;
        _camposFormEdit[idx].opciones = (raw || '').split(',').map(s => s.trim()).filter(Boolean);
        // Si hay hijos dependientes que apuntaban a este campo, re-renderizar
        // para que sus mapas de opciones_por_valor se actualicen visualmente.
        _renderCamposFormEdit();
    }

    function _setCampoDependeDe(idx, padreKey) {
        if (!_camposFormEdit[idx]) return;
        _camposFormEdit[idx].depende_de = padreKey;
        // Inicializar opciones_por_valor con las opciones del padre, vacías
        if (padreKey) {
            const padre = _camposFormEdit.find(c => c.key === padreKey);
            const valores = padre?.opciones || [];
            const actual = _camposFormEdit[idx].opciones_por_valor || {};
            const nuevo = {};
            for (const v of valores) {
                nuevo[v] = actual[v] || [];
            }
            _camposFormEdit[idx].opciones_por_valor = nuevo;
        }
        _renderCamposFormEdit();
    }

    function _setCampoOpcionesPorValor(idx, valorPadre, raw) {
        if (!_camposFormEdit[idx]) return;
        if (!_camposFormEdit[idx].opciones_por_valor) _camposFormEdit[idx].opciones_por_valor = {};
        _camposFormEdit[idx].opciones_por_valor[valorPadre] = (raw || '')
            .split(',').map(s => s.trim()).filter(Boolean);
    }

    function _quitarCampoForm(idx) {
        _camposFormEdit.splice(idx, 1);
        _renderCamposFormEdit();
    }

    async function guardarEdicion() {
        if (!_procActivo) return;
        const nombre = document.getElementById('ed-nombre').value.trim();
        const area = document.getElementById('ed-area').value;
        const subareaCode = document.getElementById('ed-subarea')?.value || null;
        const desc = document.getElementById('ed-desc').value.trim();
        const estado = document.getElementById('ed-estado')?.value || 'activo';

        if (!nombre || !area) {
            alert('Nombre y área son obligatorios');
            return;
        }

        // Filtramos pasos sin título o área (incompletos no se guardan).
        // Reordenamos por si quedó algún hueco después del drag&drop.
        const pasos = _pasosEdit
            .filter(p => p.titulo && p.area_code)
            .map((p, i) => ({
                orden: i + 1,
                titulo: p.titulo,
                descripcion: p.descripcion || '',
                area_code: p.area_code,
                subarea_code: p.subarea_code || null,
                sla_horas: p.sla_horas || 24,
                depende_de: Array.isArray(p.depende_de) ? p.depende_de : [],
                bloqueante: p.bloqueante !== false,
            }));

        // Filtramos campos sin label
        const camposForm = (_camposFormEdit || [])
            .filter(c => c.label && c.label.trim())
            .map((c, i) => {
                const base = {
                    key: (c.key || `campo_${i + 1}`).trim() || `campo_${i + 1}`,
                    label: c.label.trim(),
                    tipo: c.tipo || 'texto',
                    opciones: Array.isArray(c.opciones) ? c.opciones.filter(Boolean) : [],
                    requerido: c.requerido !== false,
                    ayuda: (c.ayuda || '').trim(),
                };
                if (c.tipo === 'select_dependiente') {
                    base.depende_de = (c.depende_de || '').trim();
                    base.opciones_por_valor = c.opciones_por_valor || {};
                }
                return base;
            });

        try {
            await GtaApi.actualizarProceso(_procActivo.id, {
                nombre,
                area,
                subarea_code: subareaCode,
                descripcion: desc,
                estado,
                pasos_definicion: JSON.stringify(pasos),
                campos_formulario: JSON.stringify(camposForm),
            });
            _modoEdit = false;
            _pasosEdit = [];
            _camposFormEdit = [];
            await abrir(_procActivo.id);
            await cargar();
        } catch (e) {
            alert('Error: ' + (e.detail || e.message || e));
        }
    }

    async function agregarNota() {
        const inp = document.getElementById('proc-comentario-texto');
        const texto = inp?.value.trim();
        if (!texto || !_procActivo) return;
        try {
            await GtaApi.agregarComentarioProc(_procActivo.id, { texto, tipo: 'nota' });
            inp.value = '';
            await abrir(_procActivo.id);
        } catch (e) {
            alert('Error: ' + (e.message || e));
        }
    }

    // ── Modal Quiebre ─────────────────────────────────────────────────
    function abrirQuiebre(procId) {
        document.getElementById('quiebre-proc-id').value = procId;
        document.getElementById('quiebre-proc-desc').value = '';
        const proc = _procActivo;
        if (proc) {
            document.getElementById('quiebre-proc-info').innerHTML =
                `Proceso: <strong>${_esc(proc.nombre)}</strong>`;
        }
        const sel = document.getElementById('quiebre-proc-area');
        sel.innerHTML = _areas.filter(a => a.activo)
            .map(a => `<option value="${a.code}" ${proc?.area === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('');
        document.getElementById('modal-quiebre-proc').classList.add('is-open');
    }

    function cerrarQuiebre() {
        document.getElementById('modal-quiebre-proc')?.classList.remove('is-open');
    }

    async function guardarQuiebre() {
        const procId = parseInt(document.getElementById('quiebre-proc-id').value, 10);
        const descripcion = document.getElementById('quiebre-proc-desc').value.trim();
        const area = document.getElementById('quiebre-proc-area').value;
        const tipo = document.getElementById('quiebre-proc-tipo').value;
        if (!descripcion || !area) {
            alert('Completa descripción y área');
            return;
        }
        try {
            await GtaApi.reportarQuiebreProc(procId, { descripcion, area, tipo });
            cerrarQuiebre();
            await abrir(procId);
            await cargar();
        } catch (e) {
            alert('Error: ' + (e.message || e));
        }
    }

    // ── Iniciar flujo desde proceso ───────────────────────────────────
    let _iniciarProcId = null;

    function iniciarFlujo(procId) {
        // Modal simple: solo título + descripción. Los campos del formulario
        // los pide la TAREA del paso 1 al cerrarla, no el inicio del flujo.
        _iniciarProcId = procId;
        const proc = _procActivo && _procActivo.id === procId ? _procActivo : _procesos.find(p => p.id === procId);

        const m = document.getElementById('modal-iniciar-flujo');
        if (!m) return;

        document.getElementById('iniciar-flujo-titulo-proceso').textContent = proc?.nombre || 'Proceso';
        document.getElementById('iniciar-flujo-campos').innerHTML = `
            <p class="gta-section-help" style="margin-top:8px;">
                Al iniciar, se va a generar la primera tarea asignada a vos.
                Los datos del proceso se completan al <strong>cerrar</strong> esa tarea,
                y recién ahí se desbloquean las áreas siguientes.
            </p>
        `;
        document.getElementById('iniciar-flujo-titulo').value = '';
        m.classList.add('is-open');
    }

    function cerrarIniciarFlujo() {
        document.getElementById('modal-iniciar-flujo')?.classList.remove('is-open');
        _iniciarProcId = null;
    }

    async function confirmarIniciarFlujo() {
        if (!_iniciarProcId) return;
        const titulo = (document.getElementById('iniciar-flujo-titulo').value || '').trim();
        if (!titulo) return alert('El título del flujo es obligatorio.');

        try {
            await GtaApi.crearFlujo({
                proceso_id: _iniciarProcId,
                titulo,
                datos_formulario: {},  // se llenan al cerrar la tarea del paso 1
            });
            cerrarIniciarFlujo();
            cerrarModal();
            // Después de iniciar, llevamos al usuario a la pestaña Tareas:
            // ahí va a ver el paso 1 ya asignado a él en "Mis tareas".
            await window.GtaCore.loadTab('tareas');
        } catch (e) {
            alert('Error al iniciar flujo: ' + (e.detail || e.message || e));
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    // ── Campos del formulario obligatorio al iniciar el flujo ────────────
    function _normalizarCamposForm(raw) {
        if (Array.isArray(raw)) return raw.map(_normalizarCampo);
        if (typeof raw === 'string' && raw.trim()) {
            try { return (JSON.parse(raw) || []).map(_normalizarCampo); }
            catch { return []; }
        }
        return [];
    }
    function _normalizarCampo(c, i) {
        return {
            key: c.key || `campo_${i + 1}`,
            label: c.label || c.titulo || `Campo ${i + 1}`,
            tipo: c.tipo || 'texto',  // texto | numero | fecha | select
            opciones: Array.isArray(c.opciones) ? c.opciones : [],
            requerido: c.requerido !== false,
            ayuda: c.ayuda || '',
        };
    }

    // ── Preview de documento (guía del proceso) ─────────────────────────
    async function abrirDocPreview(path) {
        const m = document.getElementById('modal-doc-preview');
        const body = document.getElementById('doc-preview-body');
        const title = document.getElementById('doc-preview-title');
        const footer = document.getElementById('doc-preview-footer');
        if (!m || !body) return;

        m.classList.add('is-open');
        const filename = String(path).split('/').pop() || path;
        if (title) title.textContent = filename;
        body.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando documento…</div>`;
        if (footer) {
            footer.innerHTML = `
                <a href="/api/gta/catalogo/download?path=${encodeURIComponent(path)}" class="btn-secondary" download>
                    <i class="fas fa-download"></i> Descargar
                </a>
                <button class="btn-secondary" onclick="Procesos.cerrarDocPreview()">Cerrar</button>
            `;
        }

        try {
            const meta = await GtaApi.getPreviewMeta(path);
            if (meta.mode === 'iframe') {
                const url = `/api/gta/catalogo/download?path=${encodeURIComponent(path)}`;
                body.innerHTML = `<iframe src="${url}" style="width:100%; height:75vh; border:0; background:#fff;"></iframe>`;
            } else if (meta.mode === 'image') {
                const url = `/api/gta/catalogo/download?path=${encodeURIComponent(path)}`;
                body.innerHTML = `<div style="text-align:center;"><img src="${url}" style="max-width:100%; height:auto; border-radius:8px;"></div>`;
            } else if (meta.mode === 'text') {
                const data = await GtaApi.getPreviewText(path);
                const truncMsg = data.truncated
                    ? `<div class="gta-section-help" style="margin-bottom:10px;"><i class="fas fa-scissors"></i> Documento muy largo, se muestra el inicio (${data.text.length}/${data.total_chars} caracteres). Descargá para ver completo.</div>`
                    : '';
                body.innerHTML = `
                    ${truncMsg}
                    <pre class="gta-doc-preview-text">${_esc(data.text || '(documento vacío)')}</pre>
                `;
            } else {
                body.innerHTML = `
                    <div class="gta-empty" style="padding:40px 20px;">
                        <i class="fas fa-file-circle-question" style="font-size:32px; opacity:0.4;"></i>
                        <p style="margin-top:10px;">No podemos previsualizar este tipo de archivo en el navegador.</p>
                        <p class="gta-section-help">Usá "Descargar" abajo para abrirlo localmente.</p>
                    </div>
                `;
            }
        } catch (e) {
            body.innerHTML = `<div class="gta-empty">Error al cargar preview: ${_esc(e.detail || e.message || e)}</div>`;
        }
    }

    function cerrarDocPreview() {
        document.getElementById('modal-doc-preview')?.classList.remove('is-open');
    }

    return {
        init, cargar, filtrarArea,
        abrir, cerrarModal,
        entrarModoEdicion, salirModoEdicion, guardarEdicion,
        _refreshSubareas, _agregarPasoEdit, _setPasoEdit, _setPasoArea,
        _setDepsEdit, _quitarPasoEdit,
        _dragStart, _dragOver, _dragLeave, _drop, _dragEnd,
        _agregarCampoForm, _setCampoForm, _setCampoTipo, _setCampoOpciones,
        _setCampoDependeDe, _setCampoOpcionesPorValor, _quitarCampoForm,
        abrirQuiebre, cerrarQuiebre, guardarQuiebre,
        iniciarFlujo, cerrarIniciarFlujo, confirmarIniciarFlujo, agregarNota,
        abrirDocPreview, cerrarDocPreview,
    };
})();
