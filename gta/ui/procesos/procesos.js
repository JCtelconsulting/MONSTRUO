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
            area_code: p.area_code || p.area || '',
            sla_horas: p.sla_horas || 24,
            depende_de: p.depende_de || [],
        }));
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

        const archivoSection = p.archivo_path
            ? `<a href="/api/gta/catalogo/download?path=${encodeURIComponent(p.archivo_path)}" class="btn-secondary" download>
                <i class="fas fa-download"></i> Descargar documento
               </a>`
            : `<span class="gta-section-help">Sin documento adjunto.</span>`;

        const pasosHtml = pasos.length ? `
            <div class="gta-pipeline" style="margin-top:8px;">
                ${pasos.map((paso, idx) => `
                    <div class="gta-pipe-tarea sla-cyan">
                        <div class="gta-pipe-num">${paso.orden || (idx + 1)}</div>
                        <div class="gta-pipe-body">
                            <div class="gta-pipe-header">
                                <h5>${_esc(paso.titulo || paso.nombre || 'Paso ' + (idx + 1))}</h5>
                            </div>
                            <div class="gta-pipe-meta">
                                <span><i class="fas fa-layer-group"></i> ${_esc(_areaLabel(paso.area_code || paso.area || '-'))}${paso.subarea_code ? ' / ' + _esc(paso.subarea_code) : ''}</span>
                                <span><i class="fas fa-clock"></i> ${paso.sla_horas || 0}h</span>
                                ${(paso.depende_de || []).length ? `<span><i class="fas fa-link"></i> Depende de: ${paso.depende_de.join(', ')}</span>` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
        ` : `<p class="gta-section-help">Sin definición ejecutable.</p>`;

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

        const iniciarBtn = pasos.length
            ? `<button class="btn-primary" onclick="Procesos.iniciarFlujo(${p.id})"><i class="fas fa-rocket"></i> Iniciar flujo</button>`
            : '';

        const body = document.getElementById('proc-modal-body');
        body.innerHTML = `
            <div class="gta-flujo-summary">
                <div><strong>${_esc(p.descripcion || 'Sin descripción')}</strong></div>
                <div style="margin-top:8px; display:flex; gap:10px; flex-wrap:wrap;">
                    ${archivoSection}
                    ${iniciarBtn}
                </div>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:18px;">⚙️ Definición ejecutable</h4>
            ${pasosHtml}

            <h4 class="gta-section-subtitle" style="margin-top:24px;">📊 Métricas</h4>
            <div class="gta-flujo-summary">
                <div style="display:flex; gap:14px; flex-wrap:wrap; font-size:0.85rem; color:var(--text-soft);">
                    <span><i class="fas fa-clock"></i> SLA esperado: ${m.sla_horas_total || 0}h</span>
                    <span><i class="fas fa-stopwatch"></i> Promedio real: ${m.prom_horas != null ? Math.round(m.prom_horas) + 'h' : '—'}</span>
                    <span><i class="fas fa-list-check"></i> Flujos completados: ${m.flujos_completados || 0}</span>
                </div>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">📋 Flujos ejecutados (${flujos.length})</h4>
            <div>${flujosHtml}</div>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">🚨 Quiebres registrados (${quiebres.length})</h4>
            <div>${quiebresHtml}</div>
            <button class="btn-secondary" style="margin-top:8px;" onclick="Procesos.abrirQuiebre(${p.id})">
                <i class="fas fa-flag"></i> Reportar nuevo quiebre
            </button>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">📝 Notas y decisiones</h4>
            <div class="gta-flujo-timeline">${comentariosHtml}</div>
            <div style="margin-top:10px; display:flex; gap:8px;">
                <input type="text" id="proc-comentario-texto" class="input-dark" placeholder="Agregar nota...">
                <button class="btn-secondary" onclick="Procesos.agregarNota()">
                    <i class="fas fa-plus"></i> Agregar
                </button>
            </div>
        `;

        const footer = document.getElementById('proc-modal-footer');
        footer.innerHTML = `
            <button class="btn-secondary" onclick="Procesos.cerrarModal()">Cerrar</button>
            <button class="btn-primary" onclick="Procesos.entrarModoEdicion()">
                <i class="fas fa-pen"></i> Editar
            </button>
        `;
    }

    function _renderModalEdit(p) {
        const activas = _areas.filter(a => a.activo);
        const subareasDelArea = (() => {
            const a = _areas.find(x => x.code === (p._editArea ?? p.area));
            return (a?.subareas || []).filter(s => s.activo);
        })();

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
            </div>
            <div class="field" style="margin-top:10px;">
                <label>Descripción breve</label>
                <textarea id="ed-desc" class="input-dark" rows="2">${_esc(p.descripcion || '')}</textarea>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:18px;">Pasos del proceso</h4>
            <p class="gta-section-help">Cada paso necesita título y área. Las dependencias usan el número de orden (ej: <code>1,2</code>).</p>
            <div id="ed-pasos" class="gta-flujo-tareas-edit"></div>
            <button class="btn-secondary" onclick="Procesos._agregarPasoEdit()" style="margin-top:8px;">
                <i class="fas fa-plus"></i> Agregar paso
            </button>
        `;
        _renderPasosEdit();

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
        cont.innerHTML = _pasosEdit.map((t, idx) => `
            <div class="gta-tarea-edit-row">
                <div class="gta-tarea-edit-num">#${t.orden}</div>
                <div class="gta-tarea-edit-fields">
                    <input type="text" class="input-dark" placeholder="Título del paso"
                           value="${_esc(t.titulo)}" oninput="Procesos._setPasoEdit(${idx}, 'titulo', this.value)">
                    <div style="display:flex; gap:8px; margin-top:6px;">
                        <select class="input-dark" style="flex:1;" onchange="Procesos._setPasoEdit(${idx}, 'area_code', this.value)">
                            <option value="">— Área —</option>
                            ${activas.map(a => `<option value="${a.code}" ${t.area_code === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('')}
                        </select>
                        <input type="number" class="input-dark" min="1" max="999" style="width:90px;"
                               value="${t.sla_horas}" placeholder="SLA h"
                               oninput="Procesos._setPasoEdit(${idx}, 'sla_horas', parseInt(this.value, 10) || 24)">
                        <input type="text" class="input-dark" placeholder="Depende de"
                               value="${(t.depende_de || []).join(',')}" style="width:120px;"
                               oninput="Procesos._setDepsEdit(${idx}, this.value)">
                    </div>
                </div>
                <button class="btn-sm btn-danger" onclick="Procesos._quitarPasoEdit(${idx})">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `).join('');
    }

    function _agregarPasoEdit() {
        _pasosEdit.push({
            orden: _pasosEdit.length + 1,
            titulo: '', area_code: '', sla_horas: 24, depende_de: [],
        });
        _renderPasosEdit();
    }

    function _setPasoEdit(idx, k, v) {
        if (_pasosEdit[idx]) _pasosEdit[idx][k] = v;
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

    async function guardarEdicion() {
        if (!_procActivo) return;
        const nombre = document.getElementById('ed-nombre').value.trim();
        const area = document.getElementById('ed-area').value;
        const desc = document.getElementById('ed-desc').value.trim();
        if (!nombre || !area) {
            alert('Nombre y área son obligatorios');
            return;
        }
        const pasos = _pasosEdit.filter(p => p.titulo && p.area_code);
        try {
            await GtaApi.actualizarProceso(_procActivo.id, {
                nombre, area, descripcion: desc,
                pasos_definicion: JSON.stringify(pasos),
            });
            _modoEdit = false;
            _pasosEdit = [];
            await abrir(_procActivo.id);
            await cargar();
        } catch (e) {
            alert('Error: ' + (e.message || e));
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
    async function iniciarFlujo(procId) {
        const titulo = prompt('Título del flujo (ej: "Cliente ABC Corp"):');
        if (!titulo || !titulo.trim()) return;
        try {
            const flujo = await GtaApi.crearFlujo({
                proceso_id: procId,
                titulo: titulo.trim(),
            });
            cerrarModal();
            await window.GtaCore.loadTab('tablero');
            setTimeout(() => {
                if (window.Tablero?.abrirFlujo) window.Tablero.abrirFlujo(flujo.id);
            }, 400);
        } catch (e) {
            alert('Error al iniciar flujo: ' + (e.message || e));
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    return {
        init, cargar, filtrarArea,
        abrir, cerrarModal,
        entrarModoEdicion, salirModoEdicion, guardarEdicion,
        _refreshSubareas, _agregarPasoEdit, _setPasoEdit, _setDepsEdit, _quitarPasoEdit,
        abrirQuiebre, cerrarQuiebre, guardarQuiebre,
        iniciarFlujo, agregarNota,
    };
})();
