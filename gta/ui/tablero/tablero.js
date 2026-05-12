// Tablero — Kanban de flujos cross-área (solo lectura)
//
// Foco: estado y tiempos. NO muestra contenido detallado de tareas; para
// eso el botón "Abrir tarea" navega a la pestaña Tareas con la tarea
// expandida.
window.Tablero = (() => {
    let _flujos = [];
    let _metricas = null;
    let _sesion = null;
    let _areas = [];
    let _flujosExpandidos = new Set();   // ids expandidos en el acordeón
    let _detalleCache = new Map();       // flujo_id → { flujo, eventos }

    // ── Init ────────────────────────────────────────────────────────────
    function init(sesion) {
        _sesion = sesion;
        // Arrancar siempre con todos los flujos colapsados (evita acordeones
        // "semi-abiertos" al volver a la pestaña sin contenido async cargado).
        _flujosExpandidos.clear();
        _detalleCache.clear();
        _cargarAreas();
        cargar();
    }

    async function _cargarAreas() {
        try {
            const resp = await window.fetchApi('/api/gta/areas').catch(() => null);
            _areas = resp?.items || [];
            _llenarSelectAreas();
        } catch (e) { /* silent */ }
    }

    function _llenarSelectAreas() {
        const sel = document.getElementById('filtro-area');
        if (!sel || !_areas.length) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Todas las áreas</option>' +
            _areas.filter(a => a.activo).map(a =>
                `<option value="${a.code}">${_esc(a.label)}</option>`
            ).join('');
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
            kanban.innerHTML = `<div class="gta-empty">Error al cargar flujos: ${_esc(e.message || e)}</div>`;
        }
    }

    // ── KPIs ────────────────────────────────────────────────────────────
    function _actualizarKpis() {
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = (v ?? '0'); };
        const m = _metricas || {};
        set('kpi-flujos-activos', m.flujos_activos);
        set('kpi-vencidas',       m.vencidas);
        set('kpi-por-vencer',     m.por_vencer);
        set('kpi-completados',    m.flujos_completados);
    }

    // ── Filtros ─────────────────────────────────────────────────────────
    function filtrar() {
        _renderKanban();
    }

    function _flujosFiltrados() {
        const area = document.getElementById('filtro-area')?.value || '';
        const estado = document.getElementById('filtro-estado')?.value || '';
        const q = (document.getElementById('filtro-busqueda')?.value || '').toLowerCase().trim();

        return _flujos.filter(f => {
            if (estado && f.estado !== estado) return false;
            if (q && !((f.titulo || '') + ' ' + (f.proceso_nombre || '')).toLowerCase().includes(q)) return false;
            if (area && f.paso_actual?.area_label) {
                // Filtro por área: el paso actual está en esa área
                const areaObj = _areas.find(a => a.code === area);
                if (areaObj && f.paso_actual.area_label !== areaObj.label) return false;
            }
            return true;
        });
    }

    // ── Kanban: agrupado por estado del flujo ──────────────────────────
    function _renderKanban() {
        const kanban = document.getElementById('tablero-kanban');
        if (!kanban) return;

        const flujos = _flujosFiltrados();
        if (!flujos.length) {
            kanban.innerHTML = `<div class="gta-empty">No hay flujos que cumplan los filtros.</div>`;
            return;
        }

        const grupos = {
            'activo':     { label: 'Activos',     icon: 'fa-bolt',  items: [] },
            'completado': { label: 'Completados', icon: 'fa-check', items: [] },
            'cancelado':  { label: 'Cancelados',  icon: 'fa-ban',   items: [] },
        };
        flujos.forEach(f => {
            (grupos[f.estado] || grupos['activo']).items.push(f);
        });

        const ordenCols = ['activo', 'completado', 'cancelado'];
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
        const pct = Number(f.avance_pct || 0);
        const total = Number(f.total || 0);
        const done = Number(f.cerradas || 0);
        const fecha = f.iniciado_at ? new Date(f.iniciado_at).toLocaleDateString('es-CL') : '';
        const dotColor = { rojo: 'gta-dot-red', amarillo: 'gta-dot-yellow', verde: 'gta-dot-green' }[f.salud_sla] || 'gta-dot-gray';
        const expandida = _flujosExpandidos.has(f.flujo_id);

        // Badges de alertas del flujo
        const badges = [];
        if (f.vencidas > 0) badges.push(`<span class="gta-badge-alert badge-danger" title="${f.vencidas} tarea(s) con SLA ya vencido">🔥 ${f.vencidas}</span>`);
        if (f.por_vencer > 0 && f.vencidas === 0) badges.push(`<span class="gta-badge-alert badge-warning" title="${f.por_vencer} tarea(s) cerca de vencer (≥70% del SLA consumido)">⏰ ${f.por_vencer}</span>`);
        if (f.devueltas > 0) badges.push(`<span class="gta-badge-alert badge-warning" title="${f.devueltas} tarea(s) devueltas esperando que el paso destino se vuelva a cerrar">↩ ${f.devueltas}</span>`);

        // Paso actual
        const pasoActual = f.paso_actual
            ? `<div class="gta-flujo-paso-actual">
                  <i class="fas fa-arrow-right"></i>
                  <span><strong>Paso ${f.paso_actual.paso_orden}:</strong> ${_esc(f.paso_actual.titulo)} <em>(${_esc(f.paso_actual.area_label || '')})</em></span>
               </div>`
            : '';

        return `
        <div class="gta-flujo-card ${expandida ? 'is-open' : ''}" data-flujo-id="${f.flujo_id}">
            <div class="gta-flujo-card-head-clickable" onclick="Tablero.toggleFlujo('${f.flujo_id}')">
                <div class="gta-flujo-card-head">
                    <span class="gta-dot ${dotColor}" title="Salud del SLA del flujo: verde = todo en plazo · amarillo = al menos una tarea cerca de vencer · rojo = al menos una vencida"></span>
                    <div class="gta-flujo-card-title">${_esc(f.titulo)}</div>
                    <i class="fas fa-chevron-${expandida ? 'up' : 'down'} gta-flujo-card-chevron"></i>
                </div>
                ${f.proceso_nombre ? `<div class="gta-flujo-card-proceso"><i class="fas fa-project-diagram"></i> ${_esc(f.proceso_nombre)}</div>` : ''}
                ${pasoActual}
                <div class="gta-flujo-card-meta">
                    <span><i class="fas fa-user"></i> ${_esc(f.iniciado_por || '-')}</span>
                    <span><i class="fas fa-calendar"></i> ${fecha}</span>
                </div>
                ${badges.length ? `<div class="gta-flujo-card-badges">${badges.join('')}</div>` : ''}
                <div class="gta-flujo-card-progress">
                    <div class="gta-flujo-progress-bar">
                        <div class="gta-flujo-progress-fill" style="width:${pct}%"></div>
                    </div>
                    <span class="gta-flujo-progress-label">${done}/${total} tareas — ${pct}%</span>
                </div>
            </div>
            <div class="gta-flujo-card-detalle" id="flujo-detalle-${f.flujo_id}">
                ${expandida ? '<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i></div>' : ''}
            </div>
        </div>`;
    }

    // ── Acordeón inline: expandir/colapsar el detalle del flujo ─────────
    async function toggleFlujo(flujoId) {
        if (_flujosExpandidos.has(flujoId)) {
            _flujosExpandidos.delete(flujoId);
            _renderKanban();
            return;
        }
        _flujosExpandidos.add(flujoId);
        _renderKanban();

        const cont = document.getElementById(`flujo-detalle-${flujoId}`);
        if (!cont) return;

        // Cache: si ya lo cargamos, lo pintamos inmediato; igual lo refrescamos en background
        if (_detalleCache.has(flujoId)) {
            const { flujo, eventos } = _detalleCache.get(flujoId);
            cont.innerHTML = _renderDetalleInline(flujo, eventos);
        }

        try {
            const [flujo, timelineResp] = await Promise.all([
                GtaApi.getFlujo(flujoId),
                GtaApi.getFlujoTimeline(flujoId).catch(() => ({ items: [] })),
            ]);
            const eventos = timelineResp.items || [];
            _detalleCache.set(flujoId, { flujo, eventos });
            // Solo actualizamos si la tarjeta sigue expandida
            if (_flujosExpandidos.has(flujoId)) {
                cont.innerHTML = _renderDetalleInline(flujo, eventos);
            }
        } catch (e) {
            cont.innerHTML = `<div class="gta-empty">Error al cargar detalle: ${_esc(e.message || e)}</div>`;
        }
    }

    function _renderDetalleInline(flujo, eventos) {
        const tareas = flujo.tareas || [];
        const inicio = flujo.iniciado_at ? new Date(flujo.iniciado_at).toLocaleString('es-CL') : '—';

        const cerradas = flujo.cerradas || 0;
        const total = flujo.total || 0;
        const enCurso = tareas.filter(t => t.estado === 'en_curso').length;
        const pendientes = tareas.filter(t => t.estado === 'pendiente').length;
        const bloqueadas = tareas.filter(t => t.estado === 'bloqueada').length;
        const esperando = tareas.filter(t => t.estado === 'esperando_quiebre').length;
        const devueltas = tareas.filter(t => t.estado === 'devuelta').length;
        const vencidas = tareas.filter(t => t.salud_sla === 'rojo').length;

        return `
        <div class="gta-flujo-summary">
            <div class="gta-flujo-summary-meta">
                <span><i class="fas fa-user"></i> Iniciado por <strong>${_esc(flujo.iniciado_por || '?')}</strong></span>
                <span><i class="fas fa-clock"></i> ${inicio}</span>
                <span><i class="fas fa-list-check"></i> ${cerradas}/${total} cerradas (${flujo.avance_pct || 0}%)</span>
            </div>
            <div class="gta-flujo-summary-counts">
                ${enCurso ? `<span class="gta-pill estado-en_curso">${enCurso} en curso</span>` : ''}
                ${pendientes ? `<span class="gta-pill estado-pendiente">${pendientes} pendiente${pendientes>1?'s':''}</span>` : ''}
                ${bloqueadas ? `<span class="gta-pill estado-bloqueada">${bloqueadas} bloqueada${bloqueadas>1?'s':''}</span>` : ''}
                ${esperando ? `<span class="gta-pill estado-esperando_quiebre">${esperando} esperando otra área</span>` : ''}
                ${devueltas ? `<span class="gta-pill estado-devuelta">${devueltas} devuelta${devueltas>1?'s':''}</span>` : ''}
                ${vencidas ? `<span class="gta-pill estado-vencida">${vencidas} vencida${vencidas>1?'s':''}</span>` : ''}
            </div>
        </div>

        <h4 class="gta-section-subtitle">Pipeline de tareas</h4>
        <div class="gta-pipeline">
            ${tareas.map(_renderTareaPipeline).join('')}
        </div>

        <h4 class="gta-section-subtitle" style="margin-top:24px;">Timeline</h4>
        <div class="gta-flujo-timeline">
            ${eventos.length
                ? eventos.map(_renderEvento).join('')
                : '<p class="gta-section-help">Sin eventos registrados todavía.</p>'}
        </div>
        `;
    }

    function _renderTareaPipeline(t) {
        const dotColor = { rojo: 'gta-dot-red', amarillo: 'gta-dot-yellow', verde: 'gta-dot-green', neutral: 'gta-dot-gray' }[t.salud_sla] || 'gta-dot-gray';
        const slaPct = t.sla_pct != null ? Math.min(t.sla_pct, 100) : null;
        const slaLabel = (t.sla_horas
            ? (slaPct != null ? `${slaPct}% del SLA (${t.sla_horas}h)` : `SLA: ${t.sla_horas}h`)
            : 'Sin SLA');

        const due = t.sla_due_at ? new Date(t.sla_due_at).toLocaleString('es-CL') : '';
        const cerrado = t.cerrado_at ? `Cerrada ${new Date(t.cerrado_at).toLocaleString('es-CL')}` : '';
        const responsable = t.responsable_username
            ? `<i class="fas fa-user"></i> ${_esc(t.responsable_username)}`
            : `<i class="fas fa-user-slash"></i> Sin asignar`;

        // Badges chicos por tarea
        const badges = [];
        if (t.comentarios_count > 0) badges.push(`<span class="gta-badge-alert badge-info" title="${t.comentarios_count} comentario(s) en el flujo">💬 ${t.comentarios_count}</span>`);

        return `
        <div class="gta-pipe-tarea sla-${t.salud_sla || 'neutral'}" data-tarea="${t.id}">
            <div class="gta-pipe-num">${t.paso_orden || '·'}</div>
            <div class="gta-pipe-body">
                <div class="gta-pipe-header">
                    <span class="gta-dot ${dotColor}" title="Salud del SLA del flujo: verde = todo en plazo · amarillo = al menos una tarea cerca de vencer · rojo = al menos una vencida"></span>
                    <h5>${_esc(t.titulo)}</h5>
                    <span class="gta-tarea-estado estado-${t.estado}">${_estadoLabel(t.estado)}</span>
                </div>
                <div class="gta-pipe-meta">
                    <span><i class="fas fa-layer-group"></i> ${_esc(t.area_label)}${t.subarea_code ? ' / ' + _esc(t.subarea_label || t.subarea_code) : ''}</span>
                    <span>${responsable}</span>
                    ${due ? `<span><i class="fas fa-hourglass-end"></i> Vence: ${due}</span>` : ''}
                    ${cerrado ? `<span><i class="fas fa-check"></i> ${cerrado}</span>` : ''}
                </div>
                ${slaPct != null ? `
                    <div class="gta-pipe-sla">
                        <div class="gta-pipe-sla-bar">
                            <div class="gta-pipe-sla-fill" style="width:${slaPct}%"></div>
                        </div>
                        <span class="gta-pipe-sla-label">${slaLabel}</span>
                    </div>` : ''}
                ${badges.length ? `<div class="gta-pipe-badges">${badges.join('')}</div>` : ''}
                ${(t.estado !== 'cerrada' && t.estado !== 'cancelada')
                    ? `<div class="gta-pipe-actions">
                        <button class="btn-sm btn-secondary" onclick="event.stopPropagation(); Tablero.abrirEnTareas(${t.id})">
                            <i class="fas fa-external-link-alt"></i> Abrir tarea
                        </button>
                       </div>`
                    : ''}
            </div>
        </div>`;
    }

    function _renderEvento(e) {
        const fecha = e.created_at ? new Date(e.created_at).toLocaleString('es-CL') : '';
        const icon = _eventoIcon(e.tipo);
        const cls = _eventoClass(e.tipo);
        return `
        <div class="gta-evento-item ${cls}">
            <div class="gta-evento-icon"><i class="fas ${icon}"></i></div>
            <div class="gta-evento-body">
                <div class="gta-evento-msg">${_esc(e.mensaje || _eventoLabel(e.tipo))}</div>
                <div class="gta-evento-meta">${_esc(e.actor || 'sistema')} · ${fecha}</div>
            </div>
        </div>`;
    }

    // ── Bridge a la pestaña Tareas ──────────────────────────────────────
    function abrirEnTareas(tareaId) {
        // Guardamos un pin para que la pestaña Tareas, al cargar, expanda esta tarea
        window.GtaCore = window.GtaCore || {};
        window.GtaCore.pendingExpandTarea = tareaId;
        cerrarDrawer();
        if (window.GtaCore.loadTab) {
            window.GtaCore.loadTab('tareas');
        } else {
            // Fallback: click en el botón del tab
            const btn = document.querySelector('[data-gta-tab="tareas"]');
            btn?.click();
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────────
    function _estadoLabel(e) {
        const labels = {
            pendiente: 'Pendiente', en_curso: 'En curso',
            bloqueada: 'Bloqueada', cerrada: 'Cerrada',
            cancelada: 'Cancelada', devuelta: 'Devuelta',
            esperando_quiebre: 'Esperando otra área',
        };
        return labels[e] || e;
    }

    function _eventoIcon(tipo) {
        const m = {
            flujo_iniciado: 'fa-flag',
            tarea_cerrada: 'fa-check',
            tarea_devuelta: 'fa-rotate-left',
            tarea_reabierta: 'fa-circle-play',
            quiebre_reportado: 'fa-flag-checkered',
            quiebre_resuelto: 'fa-handshake',
            flujo_completado: 'fa-trophy',
        };
        return m[tipo] || 'fa-circle-info';
    }

    function _eventoClass(tipo) {
        const m = {
            flujo_iniciado: 'evt-info',
            tarea_cerrada: 'evt-ok',
            tarea_devuelta: 'evt-warn',
            tarea_reabierta: 'evt-info',
            quiebre_reportado: 'evt-warn',
            quiebre_resuelto: 'evt-ok',
            flujo_completado: 'evt-ok',
        };
        return m[tipo] || '';
    }

    function _eventoLabel(tipo) {
        const m = {
            flujo_iniciado: 'Flujo iniciado',
            tarea_cerrada: 'Tarea cerrada',
            tarea_devuelta: 'Tarea devuelta',
            tarea_reabierta: 'Tarea reabierta',
            quiebre_reportado: 'Quiebre reportado',
            quiebre_resuelto: 'Quiebre resuelto',
            flujo_completado: 'Flujo completado',
        };
        return m[tipo] || tipo;
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    return {
        init, cargar, filtrar,
        toggleFlujo,
        abrirEnTareas,
    };
})();
