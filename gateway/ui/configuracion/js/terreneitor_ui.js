// terreneitor_ui.js — Pestaña Terreneitor en Configuración
// Sub-secciones: Proyectos, Clientes, Parametrizaciones.
// Todo via el proxy /api/terreneitor/* (window.fetchApi).
// TODAS las interacciones (crear/editar/borrar/confirmar) usan MODALES.
// Cero prompt()/confirm()/alert() nativos.

(function () {
    'use strict';

    const TIPOS_PROYECTO = ['PMC', 'OBRA', 'SATLINK', 'DOMICILIO', 'LEVANTAMIENTO', 'INTERPOSTE'];
    const ESTADOS_PROYECTO = ['ACTIVO', 'PAUSADO', 'CERRADO'];

    let _activeSub = 'proyectos';
    let _paramTipoActivo = null;

    // Proyectos: cache + filtros (client-side)
    let _proyectos = [];
    let _filtroTexto = '';
    let _filtroCliente = '';
    let _filtroZona = '';
    let _filtroEstado = '';

    // Estructura de proyecto en edición
    let _estructuraProjectId = null;
    let _estructuraProjectName = '';

    // Resolvedor activo del modal de confirmación
    let _confirmResolver = null;
    // Callback activo del modal genérico
    let _modalOnSave = null;

    // Clientes (cache, usado como opciones de select en editar proyecto)
    let _clientesCache = [];

    // ── Helpers ──────────────────────────────────────────────────────────
    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function _toast(msg, kind) {
        if (window.showToast) window.showToast(msg, kind || 'success');
    }

    function _err(e) {
        _toast((e && e.message) ? e.message : String(e), 'error');
    }

    // ── MODAL GENÉRICO ───────────────────────────────────────────────────
    // openModal({title, fields:[{name,label,type:'text'|'select',value,options}], onSave})
    function openModal({ title, fields, onSave }) {
        const titleEl = document.getElementById('terrModalTitle');
        const bodyEl = document.getElementById('terrModalBody');
        if (!bodyEl) return;
        titleEl.textContent = title || 'Editar';

        bodyEl.innerHTML = (fields || []).map(f => {
            const id = `terrField_${f.name}`;
            if (f.type === 'select') {
                const opts = (f.options || []).map(o =>
                    `<option value="${_esc(o.value)}"${String(o.value) === String(f.value ?? '') ? ' selected' : ''}>${_esc(o.label)}</option>`
                ).join('');
                return `<div class="cfg-form-row">
                    <label class="cfg-label">${_esc(f.label || f.name)}</label>
                    <select id="${id}" data-field="${_esc(f.name)}" class="cfg-input input-dark">${opts}</select>
                </div>`;
            }
            return `<div class="cfg-form-row">
                <label class="cfg-label">${_esc(f.label || f.name)}</label>
                <input id="${id}" data-field="${_esc(f.name)}" type="text" class="cfg-input input-dark" value="${_esc(f.value ?? '')}">
            </div>`;
        }).join('');

        _modalOnSave = onSave;
        const overlay = document.getElementById('terrModal');
        overlay.classList.add('is-open');
        const first = bodyEl.querySelector('input,select');
        if (first) setTimeout(() => first.focus(), 0);
    }

    function closeModal() {
        const overlay = document.getElementById('terrModal');
        if (overlay) overlay.classList.remove('is-open');
        _modalOnSave = null;
    }

    async function _modalSubmit(ev) {
        ev.preventDefault();
        const bodyEl = document.getElementById('terrModalBody');
        const values = {};
        bodyEl.querySelectorAll('[data-field]').forEach(el => {
            values[el.getAttribute('data-field')] = (el.value ?? '').trim();
        });
        if (!_modalOnSave) { closeModal(); return; }
        try {
            await _modalOnSave(values);
            closeModal();
        } catch (e) {
            _err(e); // dejar el modal abierto
        }
    }

    // ── MODAL CONFIRMACIÓN ───────────────────────────────────────────────
    function confirmar(mensaje, opts) {
        opts = opts || {};
        const overlay = document.getElementById('terrConfirm');
        document.getElementById('terrConfirmTitle').textContent = opts.title || 'Confirmar';
        document.getElementById('terrConfirmMsg').textContent = mensaje || '¿Continuar?';
        const yes = document.getElementById('terrConfirmYes');
        if (yes) yes.classList.toggle('btn-danger', !!opts.danger);
        overlay.classList.add('is-open');
        return new Promise(resolve => { _confirmResolver = resolve; });
    }

    function _resolveConfirm(val) {
        const overlay = document.getElementById('terrConfirm');
        if (overlay) overlay.classList.remove('is-open');
        if (_confirmResolver) { _confirmResolver(val); _confirmResolver = null; }
    }

    // ── CLIENTES ─────────────────────────────────────────────────────────
    async function loadClientes() {
        const tbody = document.getElementById('terrClientesBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="2" class="cfg-table-empty">Cargando…</td></tr>';
        try {
            const clientes = await window.fetchApi('/api/terreneitor/clientes');
            _clientesCache = Array.isArray(clientes) ? clientes : [];
            if (!_clientesCache.length) {
                tbody.innerHTML = '<tr><td colspan="2" class="cfg-table-empty">No hay clientes.</td></tr>';
                return;
            }
            tbody.innerHTML = _clientesCache.map(c => `
                <tr>
                    <td>${_esc(c.nombre)}</td>
                    <td class="ta-right">
                        <button class="btn-primary" type="button" data-terr-cli-edit="${_esc(c.id)}" data-terr-cli-nombre="${_esc(c.nombre)}">Editar</button>
                        <button class="btn-secondary" type="button" data-terr-cli-del="${_esc(c.id)}" data-terr-cli-nombre="${_esc(c.nombre)}">Borrar</button>
                    </td>
                </tr>`).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="2" class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</td></tr>`;
        }
    }

    function nuevoCliente() {
        openModal({
            title: 'Nuevo cliente',
            fields: [{ name: 'nombre', label: 'Nombre del cliente', type: 'text', value: '' }],
            onSave: async (v) => {
                if (!v.nombre) throw new Error('El nombre es obligatorio');
                await window.fetchApi('/api/terreneitor/clientes', { method: 'POST', body: { nombre: v.nombre } });
                _toast('Cliente creado');
                await loadClientes();
            }
        });
    }

    function editarCliente(id, actual) {
        openModal({
            title: 'Editar cliente',
            fields: [{ name: 'nombre', label: 'Nombre del cliente', type: 'text', value: actual || '' }],
            onSave: async (v) => {
                if (!v.nombre) throw new Error('El nombre es obligatorio');
                await window.fetchApi(`/api/terreneitor/clientes/${encodeURIComponent(id)}`, { method: 'PATCH', body: { nombre: v.nombre } });
                _toast('Cliente actualizado');
                await loadClientes();
            }
        });
    }

    async function borrarCliente(id, nombre) {
        const ok = await confirmar(`¿Borrar el cliente "${nombre}"? (no afecta proyectos ni planes)`, { title: 'Borrar cliente', danger: true });
        if (!ok) return;
        try {
            await window.fetchApi(`/api/terreneitor/clientes/${encodeURIComponent(id)}`, { method: 'DELETE' });
            _toast('Cliente eliminado');
            await loadClientes();
        } catch (e) { _err(e); }
    }

    async function sincronizarClientes() {
        try {
            const r = await window.fetchApi('/api/terreneitor/clientes/sincronizar', { method: 'POST' });
            const n = (r && typeof r.agregados !== 'undefined') ? r.agregados : 0;
            _toast(`Sincronizado: ${n}`);
            await loadClientes();
        } catch (e) { _err(e); }
    }

    // ── PARAMETRIZACIONES ────────────────────────────────────────────────
    async function loadParametrizaciones() {
        const cont = document.getElementById('terrParamTipos');
        if (!cont) return;
        cont.innerHTML = '<div class="cfg-table-empty">Cargando…</div>';
        try {
            const plantillas = await window.fetchApi('/api/terreneitor/admin/plantillas');
            if (!Array.isArray(plantillas) || !plantillas.length) {
                cont.innerHTML = '<div class="cfg-table-empty">No hay tipos de trabajo.</div>';
                return;
            }
            cont.innerHTML = plantillas.map(p => {
                const n = Array.isArray(p.tareas) ? p.tareas.length : (p.tareas || 0);
                const active = (p.tipo === _paramTipoActivo) ? ' active' : '';
                return `<button class="btn-primary terr-param-tipo${active}" type="button" data-terr-param-tipo="${_esc(p.tipo)}" style="display:block;width:100%;text-align:left;margin-bottom:6px;">${_esc(p.tipo)} — ${_esc(n)} tareas</button>`;
            }).join('');
            const existe = plantillas.some(p => p.tipo === _paramTipoActivo);
            if (_paramTipoActivo && existe) {
                verTipo(_paramTipoActivo);
            } else {
                _paramTipoActivo = null;
                const right = document.getElementById('terrParamTareas');
                if (right) right.innerHTML = '<div class="cfg-table-empty">Elegí un tipo de trabajo.</div>';
            }
        } catch (e) {
            cont.innerHTML = `<div class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</div>`;
        }
    }

    async function verTipo(tipo) {
        _paramTipoActivo = tipo;
        document.querySelectorAll('#terrParamTipos .terr-param-tipo').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-terr-param-tipo') === tipo);
        });
        const cont = document.getElementById('terrParamTareas');
        if (!cont) return;
        cont.innerHTML = '<div class="cfg-table-empty">Cargando…</div>';
        try {
            const data = await window.fetchApi(`/api/terreneitor/admin/plantillas/${encodeURIComponent(tipo)}`);
            const tareas = (data && Array.isArray(data.tareas)) ? data.tareas : [];

            // Agrupar por grupo -> categoria (preservando orden de aparición)
            const grupos = {};
            tareas.forEach(t => {
                const g = t.grupo || '—';
                const c = t.categoria || '—';
                grupos[g] = grupos[g] || {};
                grupos[g][c] = grupos[g][c] || [];
                grupos[g][c].push(t);
            });

            let html = `
                <div class="cfg-panel-row" style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
                    <h4 class="cfg-subtitle" style="margin:0;">${_esc(tipo)}</h4>
                    <div class="cfg-toolbar" style="display:flex;gap:6px;flex-wrap:wrap;">
                        <button class="btn-secondary" type="button" id="terrParamRenameTipo">Renombrar tipo</button>
                        <button class="btn-primary" type="button" id="terrParamAddTarea">+ Agregar tarea</button>
                    </div>
                </div>`;

            if (!tareas.length) {
                html += '<div class="cfg-table-empty">No hay tareas para este tipo.</div>';
            } else {
                Object.keys(grupos).forEach(g => {
                    html += `<div style="margin-bottom:14px;">
                        <div style="display:flex;align-items:center;gap:8px;">
                            <strong>${_esc(g)}</strong>
                            <button class="btn-secondary" type="button" title="Renombrar grupo" data-terr-rename-grupo="${_esc(g)}"><i class="fas fa-pen"></i></button>
                        </div>`;
                    Object.keys(grupos[g]).forEach(c => {
                        html += `<div style="display:flex;align-items:center;gap:8px;margin:6px 0 4px 12px;color:var(--text-muted,#9aa);">
                            <span>${_esc(c)}</span>
                            <button class="btn-secondary" type="button" title="Renombrar categoría" data-terr-rename-cat="${_esc(c)}" data-terr-rename-cat-grupo="${_esc(g)}"><i class="fas fa-pen"></i></button>
                        </div>`;
                        html += '<div class="cfg-table-wrap"><table class="cfg-table"><tbody>';
                        grupos[g][c].forEach(t => {
                            html += `
                                <tr>
                                    <td>${_esc(t.item)}</td>
                                    <td class="ta-right">
                                        <button class="btn-primary" type="button" data-terr-tarea-edit="${_esc(t.id)}" data-terr-grupo="${_esc(t.grupo)}" data-terr-cat="${_esc(t.categoria)}" data-terr-item="${_esc(t.item)}">Editar</button>
                                        <button class="btn-secondary" type="button" data-terr-tarea-del="${_esc(t.id)}" data-terr-item="${_esc(t.item)}">Borrar</button>
                                    </td>
                                </tr>`;
                        });
                        html += '</tbody></table></div>';
                    });
                    html += '</div>';
                });
            }
            cont.innerHTML = html;
        } catch (e) {
            cont.innerHTML = `<div class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</div>`;
        }
    }

    function renombrarTipo() {
        const tipo = _paramTipoActivo;
        if (!tipo) return;
        openModal({
            title: 'Renombrar tipo',
            fields: [{ name: 'nuevo', label: 'Nuevo nombre del tipo', type: 'text', value: tipo }],
            onSave: async (v) => {
                if (!v.nuevo) throw new Error('El nombre es obligatorio');
                await window.fetchApi(`/api/terreneitor/admin/plantillas/${encodeURIComponent(tipo)}/renombrar`, { method: 'PATCH', body: { nuevo: v.nuevo } });
                _toast('Tipo renombrado');
                _paramTipoActivo = v.nuevo;
                await loadParametrizaciones();
            }
        });
    }

    function renombrarNodo(nivel, viejo, grupo) {
        const tipo = _paramTipoActivo;
        if (!tipo) return;
        openModal({
            title: nivel === 'grupo' ? 'Renombrar grupo' : 'Renombrar categoría',
            fields: [{ name: 'nuevo', label: 'Nuevo nombre', type: 'text', value: viejo }],
            onSave: async (v) => {
                if (!v.nuevo) throw new Error('El nombre es obligatorio');
                const body = { nivel, viejo, nuevo: v.nuevo };
                if (nivel === 'categoria') body.grupo = grupo;
                await window.fetchApi(`/api/terreneitor/admin/plantillas/${encodeURIComponent(tipo)}/renombrar-nodo`, { method: 'PATCH', body });
                _toast('Renombrado');
                await verTipo(tipo);
            }
        });
    }

    function agregarTarea() {
        const tipo = _paramTipoActivo;
        if (!tipo) return;
        openModal({
            title: 'Agregar tarea',
            fields: [
                { name: 'grupo', label: 'Grupo', type: 'text', value: '' },
                { name: 'categoria', label: 'Categoría', type: 'text', value: '' },
                { name: 'item', label: 'Tarea', type: 'text', value: '' },
            ],
            onSave: async (v) => {
                if (!v.item) throw new Error('La tarea es obligatoria');
                await window.fetchApi(`/api/terreneitor/admin/plantillas/${encodeURIComponent(tipo)}`, { method: 'POST', body: { grupo: v.grupo, categoria: v.categoria, item: v.item } });
                _toast('Tarea agregada');
                await verTipo(tipo);
                await loadParametrizaciones();
            }
        });
    }

    function editarTarea(id, grupo, categoria, item) {
        openModal({
            title: 'Editar tarea',
            fields: [
                { name: 'grupo', label: 'Grupo', type: 'text', value: grupo || '' },
                { name: 'categoria', label: 'Categoría', type: 'text', value: categoria || '' },
                { name: 'item', label: 'Tarea', type: 'text', value: item || '' },
            ],
            onSave: async (v) => {
                if (!v.item) throw new Error('La tarea es obligatoria');
                await window.fetchApi(`/api/terreneitor/admin/plantillas-tarea/${encodeURIComponent(id)}`, { method: 'PATCH', body: { grupo: v.grupo, categoria: v.categoria, item: v.item } });
                _toast('Tarea actualizada');
                if (_paramTipoActivo) await verTipo(_paramTipoActivo);
            }
        });
    }

    async function borrarTarea(id, item) {
        const ok = await confirmar(`¿Borrar la tarea "${item}"?`, { title: 'Borrar tarea', danger: true });
        if (!ok) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/plantillas-tarea/${encodeURIComponent(id)}`, { method: 'DELETE' });
            _toast('Tarea eliminada');
            if (_paramTipoActivo) await verTipo(_paramTipoActivo);
            await loadParametrizaciones();
        } catch (e) { _err(e); }
    }

    // ── PROYECTOS ────────────────────────────────────────────────────────
    function _uniq(arr) {
        return Array.from(new Set(arr.filter(x => x != null && String(x).trim() !== '')));
    }

    function _fillSelect(id, valores, placeholderTodos) {
        const sel = document.getElementById(id);
        if (!sel) return;
        const prev = sel.value;
        const opts = [`<option value="">${_esc(placeholderTodos)}</option>`]
            .concat(valores.map(v => `<option value="${_esc(v)}">${_esc(v)}</option>`));
        sel.innerHTML = opts.join('');
        if (prev && valores.map(String).includes(String(prev))) sel.value = prev;
    }

    function _renderProyectos() {
        const tbody = document.getElementById('terrProyectosBody');
        if (!tbody) return;
        const q = _filtroTexto.toLowerCase();
        const filtrados = _proyectos.filter(p => {
            if (_filtroCliente && String(p.cliente) !== _filtroCliente) return false;
            if (_filtroZona && String(p.zona) !== _filtroZona) return false;
            if (_filtroEstado && String(p.estado) !== _filtroEstado) return false;
            if (q) {
                const hay = [p.nombre_pmc, p.cliente, p.zona, p.estado]
                    .map(x => String(x || '').toLowerCase()).some(s => s.includes(q));
                if (!hay) return false;
            }
            return true;
        });
        if (!filtrados.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="cfg-table-empty">No hay proyectos que coincidan.</td></tr>';
            return;
        }
        tbody.innerHTML = filtrados.map(p => `
            <tr>
                <td>${_esc(p.nombre_pmc)}</td>
                <td>${_esc(p.cliente)}</td>
                <td>${_esc(p.zona)}</td>
                <td>${_esc(p.estado)}</td>
                <td class="ta-right">
                    <button class="btn-primary" type="button" data-terr-proy-edit="${_esc(p.id)}">Editar</button>
                    <button class="btn-secondary" type="button" data-terr-proy-del="${_esc(p.id)}" data-terr-proy-nombre="${_esc(p.nombre_pmc)}">Borrar</button>
                </td>
            </tr>`).join('');
    }

    async function loadProyectos() {
        const tbody = document.getElementById('terrProyectosBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="5" class="cfg-table-empty">Cargando…</td></tr>';
        try {
            const proyectos = await window.fetchApi('/api/terreneitor/admin/proyectos');
            _proyectos = Array.isArray(proyectos) ? proyectos : [];
            _fillSelect('terrFiltroCliente', _uniq(_proyectos.map(p => p.cliente)).sort(), 'Todos los clientes');
            _fillSelect('terrFiltroZona', _uniq(_proyectos.map(p => p.zona)).sort(), 'Todas las zonas');
            _fillSelect('terrFiltroEstado', ESTADOS_PROYECTO, 'Todos los estados');
            _renderProyectos();
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="5" class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</td></tr>`;
        }
    }

    function nuevoProyecto() {
        openModal({
            title: 'Nuevo proyecto',
            fields: [
                { name: 'tipo', label: 'Tipo de trabajo', type: 'select', value: 'PMC', options: TIPOS_PROYECTO.map(t => ({ value: t, label: t })) },
                { name: 'cliente', label: 'Cliente', type: 'text', value: '' },
                { name: 'zona', label: 'Zona', type: 'text', value: '' },
                { name: 'nombre', label: 'Nombre del proyecto', type: 'text', value: '' },
            ],
            onSave: async (v) => {
                const r = await window.fetchApi('/api/terreneitor/admin/proyectos', { method: 'POST', body: { cliente: v.cliente, zona: v.zona, tipo: v.tipo, nombre: v.nombre } });
                const nom = (r && r.nombre_pmc) ? r.nombre_pmc : (v.nombre || 'proyecto');
                _toast(`Proyecto creado: ${nom}`);
                await loadProyectos();
            }
        });
    }

    function editarProyecto(id) {
        const p = _proyectos.find(x => String(x.id) === String(id));
        if (!p) return;
        const clienteOptions = _uniq([p.cliente].concat(_clientesCache.map(c => c.nombre), _proyectos.map(x => x.cliente)))
            .map(n => ({ value: n, label: n }));
        openModal({
            title: 'Editar proyecto',
            fields: [
                { name: 'nombre', label: 'Nombre del proyecto', type: 'text', value: p.nombre_pmc || '' },
                { name: 'cliente', label: 'Cliente', type: 'select', value: p.cliente || '', options: clienteOptions },
                { name: 'zona', label: 'Zona', type: 'text', value: p.zona || '' },
                { name: 'estado', label: 'Estado', type: 'select', value: p.estado || 'ACTIVO', options: ESTADOS_PROYECTO.map(e => ({ value: e, label: e })) },
            ],
            onSave: async (v) => {
                if (v.estado && v.estado !== p.estado) {
                    await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(id)}/estado`, { method: 'PUT', body: { estado: v.estado } });
                }
                await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(id)}`, { method: 'PUT', body: { cliente: v.cliente, zona: v.zona, nombre: v.nombre } });
                _toast('Proyecto actualizado');
                await loadProyectos();
            },
        });
        // Botón "Editar estructura": inyectado dentro del body del modal genérico.
        const bodyEl = document.getElementById('terrModalBody');
        if (bodyEl) {
            const wrap = document.createElement('div');
            wrap.className = 'cfg-form-row';
            wrap.innerHTML = `<button type="button" class="btn-secondary" id="terrBtnEditarEstructura" style="width:100%;">Editar estructura (tareas de este proyecto)</button>`;
            bodyEl.appendChild(wrap);
            const b = wrap.querySelector('#terrBtnEditarEstructura');
            if (b) b.addEventListener('click', () => {
                closeModal();
                abrirEstructura(id, p.nombre_pmc);
            });
        }
    }

    async function borrarProyecto(id, nombre) {
        const ok = await confirmar(`¿Eliminar el proyecto "${nombre}"? Se borrarán también sus tareas y fotos. Esta acción NO se puede deshacer.`, { title: 'Borrar proyecto', danger: true });
        if (!ok) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(id)}`, { method: 'DELETE' });
            _toast('Proyecto eliminado');
            await loadProyectos();
        } catch (e) { _err(e); }
    }

    // ── ESTRUCTURA DE PROYECTO (por proyecto, no plantilla) ──────────────
    async function abrirEstructura(projectId, projectName) {
        _estructuraProjectId = projectId;
        _estructuraProjectName = projectName || '';
        const overlay = document.getElementById('terrEstructuraModal');
        const titleEl = document.getElementById('terrEstructuraTitle');
        if (titleEl) titleEl.textContent = `Estructura — ${projectName || ''}`.trim();
        if (overlay) overlay.classList.add('is-open');
        await _renderEstructura();
    }

    function cerrarEstructura() {
        const overlay = document.getElementById('terrEstructuraModal');
        if (overlay) overlay.classList.remove('is-open');
        _estructuraProjectId = null;
    }

    async function _renderEstructura() {
        const cont = document.getElementById('terrEstructuraBody');
        if (!cont || !_estructuraProjectId) return;
        cont.innerHTML = '<div class="cfg-table-empty">Cargando…</div>';
        try {
            const data = await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(_estructuraProjectId)}/structure`);
            const tree = (data && Array.isArray(data.tree)) ? data.tree : [];
            if (!tree.length) {
                cont.innerHTML = '<div class="cfg-table-empty">Este proyecto no tiene categorías ni tareas.</div>';
                return;
            }
            cont.innerHTML = tree.map(cat => {
                const items = (cat.items || []).map(it => {
                    const fotos = (it.photos > 0) ? ` <span style="color:var(--text-muted,#9aa);">(${_esc(it.photos)} foto${it.photos === 1 ? '' : 's'})</span>` : '';
                    return `<tr>
                        <td>${_esc(it.name)}${fotos}</td>
                        <td class="ta-right">
                            <button class="btn-primary" type="button" data-terr-item-edit="${_esc(it.id)}" data-terr-item-name="${_esc(it.name)}">Renombrar</button>
                            <button class="btn-secondary" type="button" data-terr-item-del="${_esc(it.id)}" data-terr-item-name="${_esc(it.name)}" data-terr-item-photos="${_esc(it.photos || 0)}">Borrar</button>
                        </td>
                    </tr>`;
                }).join('') || '<tr><td colspan="2" class="cfg-table-empty">Sin tareas.</td></tr>';
                return `<div style="margin-bottom:16px;">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                        <strong>${_esc(cat.name)}</strong>
                        <button class="btn-secondary" type="button" data-terr-cat-edit="${_esc(cat.id)}" data-terr-cat-name="${_esc(cat.name)}">Renombrar</button>
                        <button class="btn-secondary" type="button" data-terr-cat-del="${_esc(cat.id)}" data-terr-cat-name="${_esc(cat.name)}">Borrar categoría</button>
                    </div>
                    <div class="cfg-table-wrap"><table class="cfg-table"><tbody>${items}</tbody></table></div>
                </div>`;
            }).join('');
        } catch (e) {
            cont.innerHTML = `<div class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</div>`;
        }
    }

    function estrAgregarCatTarea() {
        if (!_estructuraProjectId) return;
        const pid = _estructuraProjectId;
        openModal({
            title: 'Agregar categoría/tarea',
            fields: [
                { name: 'categoria', label: 'Categoría', type: 'text', value: '' },
                { name: 'item', label: 'Tarea', type: 'text', value: '' },
            ],
            onSave: async (v) => {
                if (!v.categoria || !v.item) throw new Error('Categoría y tarea son obligatorias');
                await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(pid)}/items`, { method: 'POST', body: { category: v.categoria, item: v.item } });
                _toast('Agregado');
                await _renderEstructura();
            }
        });
    }

    function renombrarCategoria(catId, actual) {
        openModal({
            title: 'Renombrar categoría',
            fields: [{ name: 'nombre', label: 'Nombre de la categoría', type: 'text', value: actual || '' }],
            onSave: async (v) => {
                if (!v.nombre) throw new Error('El nombre es obligatorio');
                await window.fetchApi(`/api/terreneitor/admin/categorias/${encodeURIComponent(catId)}`, { method: 'PATCH', body: { nombre: v.nombre } });
                _toast('Categoría renombrada');
                await _renderEstructura();
            }
        });
    }

    async function borrarCategoria(catId, nombre) {
        const ok = await confirmar(`¿Borrar la categoría "${nombre}" y todas sus tareas?`, { title: 'Borrar categoría', danger: true });
        if (!ok) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/categorias/${encodeURIComponent(catId)}`, { method: 'DELETE' });
            _toast('Categoría eliminada');
            await _renderEstructura();
        } catch (e) { _err(e); }
    }

    function renombrarItem(itemId, actual) {
        openModal({
            title: 'Renombrar tarea',
            fields: [{ name: 'nombre', label: 'Nombre de la tarea', type: 'text', value: actual || '' }],
            onSave: async (v) => {
                if (!v.nombre) throw new Error('El nombre es obligatorio');
                await window.fetchApi(`/api/terreneitor/admin/items/${encodeURIComponent(itemId)}`, { method: 'PATCH', body: { nombre: v.nombre } });
                _toast('Tarea renombrada');
                await _renderEstructura();
            }
        });
    }

    async function borrarItem(itemId, nombre, photos) {
        let msg = `¿Borrar la tarea "${nombre}"?`;
        if (Number(photos) > 0) msg += ` Tiene ${photos} foto${Number(photos) === 1 ? '' : 's'} que también se borrarán.`;
        const ok = await confirmar(msg, { title: 'Borrar tarea', danger: true });
        if (!ok) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/items/${encodeURIComponent(itemId)}`, { method: 'DELETE' });
            _toast('Tarea eliminada');
            await _renderEstructura();
        } catch (e) { _err(e); }
    }

    // ── Carga de la sub-sección activa ───────────────────────────────────
    function loadActiveSub() {
        if (_activeSub === 'clientes') loadClientes();
        else if (_activeSub === 'parametrizaciones') loadParametrizaciones();
        else loadProyectos();
    }

    // ── Sub-tabs internas ────────────────────────────────────────────────
    function _initSubtabs() {
        const tabs = document.querySelectorAll('#pane-terreneitor .cfg-subtab');
        tabs.forEach(t => {
            t.addEventListener('click', () => {
                const target = t.getAttribute('data-terreneitor-sub');
                _activeSub = target;
                tabs.forEach(x => x.classList.toggle('active', x === t));
                document.querySelectorAll('#pane-terreneitor .cfg-terreneitor-subpane').forEach(p => {
                    p.hidden = (p.getAttribute('data-terreneitor-pane') !== target);
                });
                loadActiveSub();
            });
        });
    }

    // ── Modales: wiring (X, Cancelar, overlay, submit) ───────────────────
    function _initModales() {
        const form = document.getElementById('terrModalForm');
        if (form) form.addEventListener('submit', _modalSubmit);
        ['terrModalClose', 'terrModalCancel'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', closeModal);
        });
        const modalOverlay = document.getElementById('terrModal');
        if (modalOverlay) modalOverlay.addEventListener('click', (ev) => { if (ev.target === modalOverlay) closeModal(); });

        // Confirmación
        const yes = document.getElementById('terrConfirmYes');
        if (yes) yes.addEventListener('click', () => _resolveConfirm(true));
        ['terrConfirmNo', 'terrConfirmClose'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', () => _resolveConfirm(false));
        });
        const confOverlay = document.getElementById('terrConfirm');
        if (confOverlay) confOverlay.addEventListener('click', (ev) => { if (ev.target === confOverlay) _resolveConfirm(false); });

        // Estructura
        const estrAdd = document.getElementById('terrEstrAddCat');
        if (estrAdd) estrAdd.addEventListener('click', estrAgregarCatTarea);
        ['terrEstructuraClose', 'terrEstructuraCerrar'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', cerrarEstructura);
        });
        const estrOverlay = document.getElementById('terrEstructuraModal');
        if (estrOverlay) estrOverlay.addEventListener('click', (ev) => { if (ev.target === estrOverlay) cerrarEstructura(); });

        // Estructura: delegación de acciones dentro del body
        const estrBody = document.getElementById('terrEstructuraBody');
        if (estrBody) {
            estrBody.addEventListener('click', (ev) => {
                const el = ev.target.closest('button');
                if (!el || !estrBody.contains(el)) return;
                let v;
                if ((v = el.getAttribute('data-terr-cat-edit'))) return renombrarCategoria(v, el.getAttribute('data-terr-cat-name'));
                if ((v = el.getAttribute('data-terr-cat-del'))) return borrarCategoria(v, el.getAttribute('data-terr-cat-name'));
                if ((v = el.getAttribute('data-terr-item-edit'))) return renombrarItem(v, el.getAttribute('data-terr-item-name'));
                if ((v = el.getAttribute('data-terr-item-del'))) return borrarItem(v, el.getAttribute('data-terr-item-name'), el.getAttribute('data-terr-item-photos'));
            });
        }
    }

    // ── Filtros de proyectos ─────────────────────────────────────────────
    function _initFiltros() {
        const txt = document.getElementById('terrProyFiltro');
        if (txt) txt.addEventListener('input', () => { _filtroTexto = txt.value.trim(); _renderProyectos(); });
        const cli = document.getElementById('terrFiltroCliente');
        if (cli) cli.addEventListener('change', () => { _filtroCliente = cli.value; _renderProyectos(); });
        const zon = document.getElementById('terrFiltroZona');
        if (zon) zon.addEventListener('change', () => { _filtroZona = zon.value; _renderProyectos(); });
        const est = document.getElementById('terrFiltroEstado');
        if (est) est.addEventListener('change', () => { _filtroEstado = est.value; _renderProyectos(); });
    }

    // ── Listeners de botones (toolbar fija + delegación del pane) ─────────
    function _initButtons() {
        const byId = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', fn);
        };
        byId('terrBtnNuevoProyecto', nuevoProyecto);
        byId('terrBtnNuevoCliente', nuevoCliente);
        byId('terrBtnSincClientes', sincronizarClientes);

        const pane = document.getElementById('pane-terreneitor');
        if (!pane) return;
        pane.addEventListener('click', (ev) => {
            const el = ev.target.closest('button');
            if (!el || !pane.contains(el)) return;
            let v;
            if ((v = el.getAttribute('data-terr-cli-edit'))) return editarCliente(v, el.getAttribute('data-terr-cli-nombre'));
            if ((v = el.getAttribute('data-terr-cli-del'))) return borrarCliente(v, el.getAttribute('data-terr-cli-nombre'));

            if ((v = el.getAttribute('data-terr-param-tipo'))) return verTipo(v);
            if (el.id === 'terrParamAddTarea') return agregarTarea();
            if (el.id === 'terrParamRenameTipo') return renombrarTipo();
            if (el.hasAttribute('data-terr-rename-grupo')) return renombrarNodo('grupo', el.getAttribute('data-terr-rename-grupo'));
            if (el.hasAttribute('data-terr-rename-cat')) return renombrarNodo('categoria', el.getAttribute('data-terr-rename-cat'), el.getAttribute('data-terr-rename-cat-grupo'));
            if ((v = el.getAttribute('data-terr-tarea-edit'))) return editarTarea(v, el.getAttribute('data-terr-grupo'), el.getAttribute('data-terr-cat'), el.getAttribute('data-terr-item'));
            if ((v = el.getAttribute('data-terr-tarea-del'))) return borrarTarea(v, el.getAttribute('data-terr-item'));

            if ((v = el.getAttribute('data-terr-proy-edit'))) return editarProyecto(v);
            if ((v = el.getAttribute('data-terr-proy-del'))) return borrarProyecto(v, el.getAttribute('data-terr-proy-nombre'));
        });
    }

    // ── Init ─────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        const terrTab = document.querySelector('.tab-btn[data-target="pane-terreneitor"]');
        if (!terrTab) return;
        _initSubtabs();
        _initFiltros();
        _initModales();
        _initButtons();
        terrTab.addEventListener('click', () => { onShow(); });
    });

    function onShow() {
        loadActiveSub();
    }

    window.TerreneitorUI = {
        onShow,
        loadProyectos, loadClientes, loadParametrizaciones,
        verTipo, openModal, closeModal, confirmar,
        abrirEstructura,
    };
})();
