// Tablero — Kanban de flujos cross-área
window.Tablero = (() => {
    let _flujos = [];
    let _metricas = null;
    let _sesion = null;
    let _areas = [];
    let _flujoActivo = null;  // detalle abierto
    let _tareasLibres = [];

    // ── Init ────────────────────────────────────────────────────────────
    function init(sesion) {
        _sesion = sesion;
        cargar();
        _cargarAreas();
    }

    async function _cargarAreas() {
        try {
            const resp = await window.fetchApi('/api/config/gta/areas').catch(() => null);
            _areas = resp?.items || [];
            _llenarSelectAreas();
        } catch (e) { /* silent */ }
    }

    function _llenarSelectAreas() {
        const sel = document.getElementById('filtro-area');
        if (!sel || !_areas.length) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Todas las áreas</option>' +
            _areas.filter(a => a.activo).map(a => `<option value="${a.code}">${_esc(a.label)}</option>`).join('');
        sel.value = current;
    }

    async function cargar() {
        const kanban = document.getElementById('tablero-kanban');
        if (!kanban) return;
        kanban.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando flujos...</div>`;
        try {
            const [resp, metricas] = await Promise.all([
                GtaApi.listarFlujos(),
                GtaApi.getMetricas().catch(() => null),
            ]);
            _flujos = resp.items || [];
            _metricas = metricas;
            _actualizarKpis();
            _renderKanban();
        } catch (e) {
            kanban.innerHTML = GtaUi.empty('Error al cargar flujos: ' + (e.message || e));
        }
    }

    // ── KPIs ────────────────────────────────────────────────────────────
    function _actualizarKpis() {
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v ?? '0'; };
        const t = _metricas?.totales || {};
        const porValidar = _flujos.reduce((acc, f) => acc + (f._tareas_por_validar || 0), 0);
        const vencidas = (_metricas?.por_persona || []).reduce((acc, p) => acc + (Number(p.vencidas) || 0), 0);
        set('kpi-activos',     t.activos || _flujos.filter(f => f.estado === 'activo').length);
        set('kpi-por-validar', porValidar);
        set('kpi-vencidos',    vencidas);
        set('kpi-completados', t.completados || 0);
    }

    // ── Filtros ─────────────────────────────────────────────────────────
    function filtrar() {
        _renderKanban();
    }

    function _flujosFiltrados() {
        const area = document.getElementById('filtro-area')?.value || '';
        const estado = document.getElementById('filtro-estado')?.value || '';
        const q = (document.getElementById('filtro-busqueda')?.value || '').toLowerCase();

        return _flujos.filter(f => {
            if (estado && f.estado !== estado) return false;
            if (q && !(f.titulo || '').toLowerCase().includes(q)) return false;
            // Filtro por área: el flujo tiene tareas del área? (requiere getFlujo, lo aproximamos)
            // Si tenemos info por área, lo aplicamos; sino lo dejamos pasar
            return true;
        });
    }

    // ── Kanban: agrupado por estado ────────────────────────────────────
    function _renderKanban() {
        const kanban = document.getElementById('tablero-kanban');
        if (!kanban) return;

        const flujos = _flujosFiltrados();
        if (!flujos.length) {
            kanban.innerHTML = GtaUi.empty('No hay flujos. Crea uno con "Nuevo flujo".');
            return;
        }

        // Agrupar por estado del flujo
        const grupos = {
            'borrador':   { label: 'Borrador',   icon: 'fa-pen',           items: [] },
            'activo':     { label: 'Activos',    icon: 'fa-bolt',          items: [] },
            'vencido':    { label: 'Vencidos',   icon: 'fa-triangle-exclamation', items: [] },
            'completado': { label: 'Completados', icon: 'fa-check',        items: [] },
            'cancelado':  { label: 'Cancelados', icon: 'fa-ban',           items: [] },
        };
        flujos.forEach(f => {
            (grupos[f.estado] || grupos['activo']).items.push(f);
        });

        const ordenCols = ['activo', 'borrador', 'vencido', 'completado', 'cancelado'];
        const cols = ordenCols.filter(k => grupos[k].items.length > 0);

        kanban.innerHTML = cols.map(estado => {
            const g = grupos[estado];
            return `
            <div class="gta-flujo-col" data-estado="${estado}">
                <div class="gta-flujo-col-header">
                    <i class="fas ${g.icon}"></i>
                    <span class="gta-flujo-col-title">${g.label}</span>
                    <span class="gta-flujo-col-count">${g.items.length}</span>
                </div>
                <div class="gta-flujo-col-body">
                    ${g.items.map(_cardFlujo).join('')}
                </div>
            </div>`;
        }).join('');
    }

    function _cardFlujo(f) {
        const pct = Number(f.pct_completado || 0);
        const total = Number(f.total_tareas || 0);
        const done = Number(f.completadas || 0);
        const fechaCreado = f.created_at ? new Date(f.created_at).toLocaleDateString('es-CL') : '';
        return `
        <div class="gta-flujo-card" onclick="Tablero.abrirFlujo(${f.id})">
            <div class="gta-flujo-card-title">${_esc(f.titulo)}</div>
            <div class="gta-flujo-card-meta">
                <span><i class="fas fa-user"></i> ${_esc(f.iniciado_por || '-')}</span>
                <span><i class="fas fa-calendar"></i> ${fechaCreado}</span>
            </div>
            <div class="gta-flujo-card-progress">
                <div class="gta-flujo-progress-bar">
                    <div class="gta-flujo-progress-fill" style="width:${pct}%"></div>
                </div>
                <span class="gta-flujo-progress-label">${done}/${total} tareas — ${pct}%</span>
            </div>
        </div>`;
    }

    // ── Drawer detalle de flujo ─────────────────────────────────────────
    async function abrirFlujo(flujoId) {
        const drawer = document.getElementById('flujo-drawer');
        const overlay = document.getElementById('flujo-drawer-overlay');
        const body = document.getElementById('flujo-drawer-body');

        document.getElementById('flujo-drawer-titulo').textContent = 'Cargando...';
        document.getElementById('flujo-drawer-codigo').textContent = `Flujo #${flujoId}`;
        body.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i></div>`;
        drawer.classList.add('open');
        overlay.classList.add('open');

        try {
            const flujo = await GtaApi.getFlujo(flujoId);
            const eventos = await GtaApi.getEventosFlujo(flujoId).catch(() => []);
            _flujoActivo = flujo;
            _renderDrawer(flujo, eventos);
        } catch (e) {
            body.innerHTML = GtaUi.empty('Error al cargar el flujo: ' + (e.message || e));
        }
    }

    function cerrarDrawer() {
        document.getElementById('flujo-drawer')?.classList.remove('open');
        document.getElementById('flujo-drawer-overlay')?.classList.remove('open');
        _flujoActivo = null;
    }

    function _renderDrawer(flujo, eventos) {
        const body = document.getElementById('flujo-drawer-body');
        document.getElementById('flujo-drawer-titulo').textContent = flujo.titulo || 'Flujo';
        document.getElementById('flujo-drawer-codigo').textContent =
            `Flujo #${flujo.id} · ${(flujo.estado || '').toUpperCase()}`;

        const tareas = flujo.tareas || [];
        const resumen = flujo.resumen || {};
        const esIniciador = (flujo.iniciado_por === _sesion?.username);

        body.innerHTML = `
        <div class="gta-flujo-summary">
            <div><strong>${_esc(flujo.descripcion || 'Sin descripción')}</strong></div>
            <div style="margin-top:10px; display:flex; gap:14px; flex-wrap:wrap; font-size:0.82rem; color:var(--text-soft);">
                <span><i class="fas fa-user"></i> Iniciado por: ${_esc(flujo.iniciado_por)}</span>
                <span><i class="fas fa-clock"></i> SLA total: ${flujo.sla_horas_total || 0}h</span>
                <span><i class="fas fa-list-check"></i> ${resumen.completadas || 0}/${resumen.total_tareas || 0} tareas (${resumen.pct_completado || 0}%)</span>
                ${resumen.vencidas ? `<span style="color:var(--danger);"><i class="fas fa-triangle-exclamation"></i> ${resumen.vencidas} vencidas</span>` : ''}
            </div>
        </div>

        <h4 class="gta-section-subtitle" style="margin-top:18px;">Pipeline de tareas</h4>
        <div class="gta-pipeline">
            ${tareas.map(t => _renderTareaPipeline(t, esIniciador)).join('')}
        </div>

        <h4 class="gta-section-subtitle" style="margin-top:24px;">Timeline</h4>
        <div class="gta-flujo-timeline">
            ${(eventos || []).slice(0, 30).map(_renderEvento).join('') ||
              '<p class="gta-section-help">Sin eventos todavía.</p>'}
        </div>
        `;
    }

    function _renderTareaPipeline(t, esIniciador) {
        const sla = t.sla || {};
        const color = sla.color || 'gray';
        const pct = Number(sla.pct || 0);
        const username = _sesion?.username;
        const esAsignado = (t.asignado_a === username);
        const esJefe = false; // se maneja en el backend; en UI solo iniciador puede validar
        const dependeDe = (t.depende_de || []);

        // Botones según estado y rol
        let acciones = '';
        if (esAsignado && (t.estado === 'lista' || t.estado === 'en_progreso')) {
            acciones += `<button class="btn-sm btn-primary" onclick="Tablero.completarTarea(${t.id})">
                            <i class="fas fa-check"></i> Marcar como hecha
                         </button>`;
            acciones += `<button class="btn-sm btn-secondary" onclick="Tablero.abrirAyuda(${t.id})">
                            <i class="fas fa-hands-helping"></i> Pedir ayuda
                         </button>`;
        }
        if (esIniciador && t.estado === 'por_validar') {
            acciones += `<button class="btn-sm btn-primary" onclick="Tablero.validarTarea(${t.id}, true)">
                            <i class="fas fa-check-double"></i> Validar
                         </button>`;
            acciones += `<button class="btn-sm btn-danger" onclick="Tablero.validarTarea(${t.id}, false)">
                            <i class="fas fa-rotate-left"></i> Rechazar
                         </button>`;
        }

        const pctLabel = sla.minutos_total > 0 ? `${pct}% — ${_minToHum(sla.minutos_consumidos)} / ${_minToHum(sla.minutos_total)}` : 'Sin SLA';

        return `
        <div class="gta-pipe-tarea sla-${color}" data-tarea="${t.id}">
            <div class="gta-pipe-num">${t.orden}</div>
            <div class="gta-pipe-body">
                <div class="gta-pipe-header">
                    <h5>${_esc(t.titulo)}</h5>
                    <span class="gta-tarea-estado estado-${t.estado}">${_estadoLabel(t.estado)}</span>
                </div>
                <div class="gta-pipe-meta">
                    <span><i class="fas fa-layer-group"></i> ${_areaLabel(t.area_code)}${t.subarea_code ? ' / ' + _esc(t.subarea_code) : ''}</span>
                    <span><i class="fas fa-user"></i> ${_esc(t.asignado_a || 'Sin asignar')}</span>
                    ${dependeDe.length ? `<span><i class="fas fa-link"></i> Depende de: ${dependeDe.join(', ')}</span>` : ''}
                </div>
                <div class="gta-pipe-sla">
                    <div class="gta-pipe-sla-bar">
                        <div class="gta-pipe-sla-fill" style="width:${Math.min(pct, 100)}%"></div>
                    </div>
                    <span class="gta-pipe-sla-label">${pctLabel}</span>
                    ${sla.esta_pausada ? '<span class="gta-tag prioridad-baja">PAUSADA</span>' : ''}
                </div>
                ${acciones ? `<div class="gta-pipe-actions">${acciones}</div>` : ''}
            </div>
        </div>`;
    }

    function _renderEvento(e) {
        const fecha = e.created_at ? new Date(e.created_at).toLocaleString('es-CL') : '';
        const icon = _eventoIcon(e.tipo);
        return `
        <div class="gta-evento-item">
            <div class="gta-evento-icon"><i class="fas ${icon}"></i></div>
            <div class="gta-evento-body">
                <div class="gta-evento-msg">${_esc(e.mensaje || e.tipo)}</div>
                <div class="gta-evento-meta">${_esc(e.actor || 'sistema')} · ${fecha}</div>
            </div>
        </div>`;
    }

    // ── Acciones sobre tareas ───────────────────────────────────────────
    async function completarTarea(tareaId) {
        if (!confirm('¿Marcar esta tarea como hecha? El iniciador del flujo deberá validarla después.')) return;
        try {
            await GtaApi.completarTarea(tareaId, {});
            await abrirFlujo(_flujoActivo.id);
            cargar();
        } catch (e) {
            alert('Error: ' + (e.message || e));
        }
    }

    async function validarTarea(tareaId, aceptada) {
        const comentario = aceptada ? '' : (prompt('Motivo del rechazo:') || '');
        if (!aceptada && !comentario) return;
        try {
            await GtaApi.validarTarea(tareaId, { aceptada, comentario });
            await abrirFlujo(_flujoActivo.id);
            cargar();
        } catch (e) {
            alert('Error: ' + (e.message || e));
        }
    }

    // ── Pedir ayuda ─────────────────────────────────────────────────────
    function abrirAyuda(tareaId) {
        document.getElementById('ayuda-tarea-id').value = tareaId;
        const sel = document.getElementById('ayuda-area');
        sel.innerHTML = _areas.filter(a => a.activo && !a.es_externa)
            .map(a => `<option value="${a.code}">${_esc(a.label)}</option>`).join('');
        document.getElementById('ayuda-mensaje').value = '';
        document.getElementById('ayuda-bloquea-sla').checked = false;
        document.getElementById('modal-pedir-ayuda').classList.add('is-open');
    }

    function cerrarModalAyuda() {
        document.getElementById('modal-pedir-ayuda')?.classList.remove('is-open');
    }

    async function enviarAyuda() {
        const tareaId = parseInt(document.getElementById('ayuda-tarea-id').value, 10);
        const area = document.getElementById('ayuda-area').value;
        const mensaje = document.getElementById('ayuda-mensaje').value.trim();
        const bloquea = document.getElementById('ayuda-bloquea-sla').checked;
        if (!area || !mensaje) {
            alert('Completa área y mensaje');
            return;
        }
        try {
            await GtaApi.pedirAyuda(tareaId, { pedido_a_area: area, mensaje, bloquea_sla: bloquea });
            cerrarModalAyuda();
            await abrirFlujo(_flujoActivo.id);
        } catch (e) {
            alert('Error: ' + (e.message || e));
        }
    }

    // ── Nuevo flujo libre ──────────────────────────────────────────────
    function abrirNuevoFlujo() {
        _tareasLibres = [];
        document.getElementById('nuevo-flujo-titulo').value = '';
        document.getElementById('nuevo-flujo-descripcion').value = '';
        agregarTareaLibre();
        document.getElementById('modal-nuevo-flujo').classList.add('is-open');
    }

    function cerrarNuevoFlujo() {
        document.getElementById('modal-nuevo-flujo')?.classList.remove('is-open');
    }

    function agregarTareaLibre() {
        _tareasLibres.push({
            orden: _tareasLibres.length + 1,
            titulo: '',
            area_code: '',
            sla_horas: 24,
            depende_de: [],
        });
        _renderTareasLibres();
    }

    function _renderTareasLibres() {
        const cont = document.getElementById('nuevo-flujo-tareas');
        if (!cont) return;
        const areas = _areas.filter(a => a.activo && !a.es_externa);
        cont.innerHTML = _tareasLibres.map((t, idx) => `
            <div class="gta-tarea-edit-row" data-idx="${idx}">
                <div class="gta-tarea-edit-num">#${t.orden}</div>
                <div class="gta-tarea-edit-fields">
                    <input type="text" class="input-dark" placeholder="Título de la tarea"
                           value="${_esc(t.titulo)}" oninput="Tablero._setTareaCampo(${idx}, 'titulo', this.value)">
                    <div style="display:flex; gap:8px; margin-top:6px;">
                        <select class="input-dark" style="flex:1;" onchange="Tablero._setTareaCampo(${idx}, 'area_code', this.value)">
                            <option value="">— Área —</option>
                            ${areas.map(a => `<option value="${a.code}" ${t.area_code === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('')}
                        </select>
                        <input type="number" class="input-dark" min="1" max="999" style="width:90px;"
                               value="${t.sla_horas}" placeholder="SLA h"
                               oninput="Tablero._setTareaCampo(${idx}, 'sla_horas', parseInt(this.value, 10) || 24)">
                        <input type="text" class="input-dark" placeholder="Depende de (ej: 1,2)"
                               value="${(t.depende_de || []).join(',')}" style="width:140px;"
                               oninput="Tablero._setDependeDe(${idx}, this.value)">
                    </div>
                </div>
                <button class="btn-sm btn-danger" onclick="Tablero._quitarTarea(${idx})" title="Eliminar">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `).join('');
    }

    function _setTareaCampo(idx, campo, valor) {
        if (_tareasLibres[idx]) _tareasLibres[idx][campo] = valor;
    }

    function _setDependeDe(idx, raw) {
        if (!_tareasLibres[idx]) return;
        const deps = (raw || '').split(',').map(s => parseInt(s.trim(), 10)).filter(Boolean);
        _tareasLibres[idx].depende_de = deps;
    }

    function _quitarTarea(idx) {
        _tareasLibres.splice(idx, 1);
        _tareasLibres.forEach((t, i) => t.orden = i + 1);
        _renderTareasLibres();
    }

    async function crearFlujoLibre() {
        const titulo = document.getElementById('nuevo-flujo-titulo').value.trim();
        const descripcion = document.getElementById('nuevo-flujo-descripcion').value.trim();
        if (!titulo) { alert('El título es requerido'); return; }
        if (!_tareasLibres.length) { alert('Agrega al menos una tarea'); return; }
        const invalidas = _tareasLibres.filter(t => !t.titulo.trim() || !t.area_code);
        if (invalidas.length) {
            alert('Cada tarea necesita título y área');
            return;
        }
        try {
            const flujo = await GtaApi.crearFlujo({
                titulo, descripcion,
                pasos_libres: _tareasLibres,
            });
            cerrarNuevoFlujo();
            await cargar();
            await abrirFlujo(flujo.id);
        } catch (e) {
            alert('Error al crear flujo: ' + (e.message || e));
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────
    function _areaLabel(code) {
        const a = _areas.find(x => x.code === code);
        return a ? _esc(a.label) : _esc(code || '-');
    }

    function _estadoLabel(e) {
        const labels = {
            pendiente: 'Pendiente', lista: 'Lista', en_progreso: 'En progreso',
            por_validar: 'Por validar', completada: 'Completada',
            ayuda_pedida: 'Ayuda pedida', vencida: 'Vencida', cancelada: 'Cancelada',
        };
        return labels[e] || e;
    }

    function _eventoIcon(tipo) {
        const m = {
            iniciado: 'fa-flag', tarea_lista: 'fa-circle-play',
            ejecutor_completo: 'fa-check', validada: 'fa-check-double',
            rechazada: 'fa-rotate-left', ayuda_pedida: 'fa-hands-helping',
            ayuda_respondida: 'fa-reply', sla_warn_70: 'fa-clock',
            sla_warn_85: 'fa-triangle-exclamation', sla_vencida: 'fa-fire',
            flujo_completado: 'fa-trophy',
        };
        return m[tipo] || 'fa-circle-info';
    }

    function _minToHum(min) {
        if (!min || min < 1) return '0min';
        if (min < 60) return `${Math.round(min)}min`;
        const h = Math.floor(min / 60);
        const r = Math.round(min % 60);
        return r ? `${h}h ${r}min` : `${h}h`;
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    return {
        init, cargar, filtrar,
        abrirFlujo, cerrarDrawer,
        completarTarea, validarTarea,
        abrirAyuda, cerrarModalAyuda, enviarAyuda,
        abrirNuevoFlujo, cerrarNuevoFlujo, agregarTareaLibre, crearFlujoLibre,
        _setTareaCampo, _setDependeDe, _quitarTarea,
    };
})();
