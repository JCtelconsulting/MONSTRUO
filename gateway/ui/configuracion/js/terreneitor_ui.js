// terreneitor_ui.js — Pestaña Terreneitor en Configuración
// Sub-secciones: Proyectos, Clientes, Parametrizaciones.
// Todo via el proxy /api/terreneitor/* (window.fetchApi).

(function () {
    'use strict';

    const TIPOS_PROYECTO = ['PMC', 'OBRA', 'SATLINK', 'DOMICILIO', 'LEVANTAMIENTO', 'INTERPOSTE'];

    let _activeSub = 'proyectos';
    let _paramTipoActivo = null;

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

    // ── CLIENTES ─────────────────────────────────────────────────────────
    async function loadClientes() {
        const tbody = document.getElementById('terrClientesBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="2" class="cfg-table-empty">Cargando…</td></tr>';
        try {
            const clientes = await window.fetchApi('/api/terreneitor/clientes');
            if (!Array.isArray(clientes) || !clientes.length) {
                tbody.innerHTML = '<tr><td colspan="2" class="cfg-table-empty">No hay clientes.</td></tr>';
                return;
            }
            tbody.innerHTML = clientes.map(c => `
                <tr>
                    <td>${_esc(c.nombre)}</td>
                    <td class="ta-right">
                        <button class="btn-primary" type="button" data-terr-cli-edit="${_esc(c.id)}" data-terr-cli-nombre="${_esc(c.nombre)}">Editar</button>
                        <button class="btn-primary" type="button" data-terr-cli-del="${_esc(c.id)}" data-terr-cli-nombre="${_esc(c.nombre)}">Borrar</button>
                    </td>
                </tr>`).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="2" class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</td></tr>`;
        }
    }

    async function nuevoCliente() {
        const nombre = prompt('Nombre del cliente:');
        if (nombre === null) return;
        const n = nombre.trim();
        if (!n) return;
        try {
            await window.fetchApi('/api/terreneitor/clientes', { method: 'POST', body: { nombre: n } });
            _toast('Cliente creado');
            await loadClientes();
        } catch (e) { _err(e); }
    }

    async function editarCliente(id, actual) {
        const nombre = prompt('Nuevo nombre del cliente:', actual || '');
        if (nombre === null) return;
        const n = nombre.trim();
        if (!n) return;
        try {
            await window.fetchApi(`/api/terreneitor/clientes/${encodeURIComponent(id)}`, { method: 'PATCH', body: { nombre: n } });
            _toast('Cliente actualizado');
            await loadClientes();
        } catch (e) { _err(e); }
    }

    async function borrarCliente(id, nombre) {
        if (!confirm(`¿Eliminar el cliente "${nombre}"?`)) return;
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
            if (_paramTipoActivo) verTipo(_paramTipoActivo);
        } catch (e) {
            cont.innerHTML = `<div class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</div>`;
        }
    }

    async function verTipo(tipo) {
        _paramTipoActivo = tipo;
        // Resaltar el tipo activo
        document.querySelectorAll('#terrParamTipos .terr-param-tipo').forEach(b => {
            b.classList.toggle('active', b.getAttribute('data-terr-param-tipo') === tipo);
        });
        const cont = document.getElementById('terrParamTareas');
        if (!cont) return;
        cont.innerHTML = '<div class="cfg-table-empty">Cargando…</div>';
        try {
            const data = await window.fetchApi(`/api/terreneitor/admin/plantillas/${encodeURIComponent(tipo)}`);
            const tareas = (data && Array.isArray(data.tareas)) ? data.tareas : [];

            // Agrupar por grupo -> categoria
            const grupos = {};
            tareas.forEach(t => {
                const g = t.grupo || '—';
                const c = t.categoria || '—';
                grupos[g] = grupos[g] || {};
                grupos[g][c] = grupos[g][c] || [];
                grupos[g][c].push(t);
            });

            let html = `
                <div class="cfg-panel-row" style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                    <h4 class="cfg-subtitle" style="margin:0;">${_esc(tipo)}</h4>
                    <button class="btn-primary" type="button" id="terrParamAddTarea">+ Agregar tarea</button>
                </div>`;

            if (!tareas.length) {
                html += '<div class="cfg-table-empty">No hay tareas para este tipo.</div>';
            } else {
                Object.keys(grupos).forEach(g => {
                    html += `<div style="margin-bottom:14px;"><strong>${_esc(g)}</strong>`;
                    Object.keys(grupos[g]).forEach(c => {
                        html += `<div style="margin:6px 0 4px 12px;color:var(--text-muted,#9aa);">${_esc(c)}</div>`;
                        html += '<div class="cfg-table-wrap"><table class="cfg-table"><tbody>';
                        grupos[g][c].forEach(t => {
                            html += `
                                <tr>
                                    <td>${_esc(t.item)}</td>
                                    <td class="ta-right">
                                        <button class="btn-primary" type="button" data-terr-tarea-edit="${_esc(t.id)}" data-terr-grupo="${_esc(t.grupo)}" data-terr-cat="${_esc(t.categoria)}" data-terr-item="${_esc(t.item)}">Editar</button>
                                        <button class="btn-primary" type="button" data-terr-tarea-del="${_esc(t.id)}" data-terr-item="${_esc(t.item)}">Borrar</button>
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

    async function agregarTarea() {
        if (!_paramTipoActivo) return;
        const grupo = prompt('Grupo:');
        if (grupo === null) return;
        const categoria = prompt('Categoría:');
        if (categoria === null) return;
        const item = prompt('Ítem (tarea):');
        if (item === null) return;
        const body = { grupo: grupo.trim(), categoria: categoria.trim(), item: item.trim() };
        if (!body.item) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/plantillas/${encodeURIComponent(_paramTipoActivo)}`, { method: 'POST', body });
            _toast('Tarea agregada');
            await verTipo(_paramTipoActivo);
            await loadParametrizaciones();
        } catch (e) { _err(e); }
    }

    async function editarTarea(id, grupo, categoria, item) {
        const g = prompt('Grupo:', grupo || '');
        if (g === null) return;
        const c = prompt('Categoría:', categoria || '');
        if (c === null) return;
        const i = prompt('Ítem (tarea):', item || '');
        if (i === null) return;
        const body = { grupo: g.trim(), categoria: c.trim(), item: i.trim() };
        if (!body.item) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/plantillas-tarea/${encodeURIComponent(id)}`, { method: 'PATCH', body });
            _toast('Tarea actualizada');
            await verTipo(_paramTipoActivo);
        } catch (e) { _err(e); }
    }

    async function borrarTarea(id, item) {
        if (!confirm(`¿Eliminar la tarea "${item}"?`)) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/plantillas-tarea/${encodeURIComponent(id)}`, { method: 'DELETE' });
            _toast('Tarea eliminada');
            await verTipo(_paramTipoActivo);
            await loadParametrizaciones();
        } catch (e) { _err(e); }
    }

    // ── PROYECTOS ────────────────────────────────────────────────────────
    async function loadProyectos() {
        const tbody = document.getElementById('terrProyectosBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="5" class="cfg-table-empty">Cargando…</td></tr>';
        try {
            const proyectos = await window.fetchApi('/api/terreneitor/admin/proyectos');
            if (!Array.isArray(proyectos) || !proyectos.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="cfg-table-empty">No hay proyectos.</td></tr>';
                return;
            }
            tbody.innerHTML = proyectos.map(p => `
                <tr>
                    <td>${_esc(p.nombre_pmc)}</td>
                    <td>${_esc(p.cliente)}</td>
                    <td>${_esc(p.zona)}</td>
                    <td>${_esc(p.estado)}</td>
                    <td class="ta-right">
                        <button class="btn-primary" type="button" data-terr-proy-interposte="${_esc(p.id)}" data-terr-proy-nombre="${_esc(p.nombre_pmc)}">Interposte</button>
                        <button class="btn-primary" type="button" data-terr-proy-del="${_esc(p.id)}" data-terr-proy-nombre="${_esc(p.nombre_pmc)}">Borrar</button>
                    </td>
                </tr>`).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="5" class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</td></tr>`;
        }
    }

    async function nuevoProyecto() {
        const tipo = prompt(`Tipo de trabajo (${TIPOS_PROYECTO.join(' / ')}):`);
        if (tipo === null) return;
        const t = tipo.trim().toUpperCase();
        if (!t) return;
        const cliente = prompt('Cliente:');
        if (cliente === null) return;
        const zona = prompt('Zona:');
        if (zona === null) return;
        const nombre = prompt('Nombre del proyecto:');
        if (nombre === null) return;
        const body = { cliente: cliente.trim(), zona: zona.trim(), tipo: t, nombre: nombre.trim() };
        try {
            const r = await window.fetchApi('/api/terreneitor/admin/proyectos', { method: 'POST', body });
            const nom = (r && r.nombre_pmc) ? r.nombre_pmc : (body.nombre || 'proyecto');
            _toast(`Proyecto creado: ${nom}`);
            await loadProyectos();
        } catch (e) { _err(e); }
    }

    async function agregarInterposte(id, nombre) {
        if (!confirm(`¿Agregar interposte al proyecto "${nombre}"?`)) return;
        try {
            const r = await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(id)}/agregar-interposte`, { method: 'POST' });
            const n = (r && typeof r.items_agregados !== 'undefined') ? r.items_agregados : '';
            _toast(`Interposte agregado${n !== '' ? `: ${n} ítems` : ''}`);
            await loadProyectos();
        } catch (e) { _err(e); }
    }

    async function borrarProyecto(id, nombre) {
        if (!confirm(`¿Eliminar el proyecto "${nombre}"? Esta acción no se puede deshacer.`)) return;
        if (!confirm(`Confirma de nuevo: se eliminará "${nombre}" definitivamente.`)) return;
        try {
            await window.fetchApi(`/api/terreneitor/admin/proyectos/${encodeURIComponent(id)}`, { method: 'DELETE' });
            _toast('Proyecto eliminado');
            await loadProyectos();
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

    // ── Listeners de botones / acciones (delegación) ─────────────────────
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
            if ((v = el.getAttribute('data-terr-tarea-edit'))) return editarTarea(v, el.getAttribute('data-terr-grupo'), el.getAttribute('data-terr-cat'), el.getAttribute('data-terr-item'));
            if ((v = el.getAttribute('data-terr-tarea-del'))) return borrarTarea(v, el.getAttribute('data-terr-item'));

            if ((v = el.getAttribute('data-terr-proy-interposte'))) return agregarInterposte(v, el.getAttribute('data-terr-proy-nombre'));
            if ((v = el.getAttribute('data-terr-proy-del'))) return borrarProyecto(v, el.getAttribute('data-terr-proy-nombre'));
        });
    }

    // ── Init ─────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        const terrTab = document.querySelector('.tab-btn[data-target="pane-terreneitor"]');
        if (!terrTab) return;
        _initSubtabs();
        _initButtons();
        terrTab.addEventListener('click', () => { onShow(); });
    });

    // Carga la sub-sección actualmente activa (llamado al mostrar la pestaña)
    function onShow() {
        loadActiveSub();
    }

    window.TerreneitorUI = {
        onShow,
        loadProyectos, loadClientes, loadParametrizaciones,
        verTipo,
    };
})();
