// Tablero — Kanban por área
window.Tablero = (() => {
    let _datos = [];
    let _sesion = null;

    const AREAS_ORDER = ['comercial','preventa','redes','sistemas','finanzas','proveedores','capital_humano','bodega','ia'];

    function init(sesion) {
        _sesion = sesion;
        cargar();
    }

    async function cargar() {
        const kanban = document.getElementById('tablero-kanban');
        if (!kanban) return;
        kanban.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;

        try {
            const [stats, solicitudes] = await Promise.all([
                GtaApi.getStats(),
                GtaApi.getSolicitudes('?estado=pendiente,en_progreso,bloqueado'),
            ]);
            _datos = Array.isArray(solicitudes) ? solicitudes : [];
            _actualizarKpis(stats);
            _renderKanban(_datos);
        } catch (e) {
            kanban.innerHTML = GtaUi.empty('Error al cargar el tablero.');
        }
    }

    function filtrar() {
        const area      = document.getElementById('filtro-area')?.value || '';
        const prioridad = document.getElementById('filtro-prioridad')?.value || '';
        let filtrado = _datos;
        if (area)      filtrado = filtrado.filter(s => s.area === area);
        if (prioridad) filtrado = filtrado.filter(s => s.prioridad === prioridad);
        _renderKanban(filtrado);
    }

    function _actualizarKpis(stats) {
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? '0'; };
        set('kpi-total',       stats.total || 0);
        set('kpi-en-progreso', stats.en_progreso || 0);
        set('kpi-vencidas',    stats.bloqueadas || 0);
        set('kpi-completadas', stats.completadas_hoy || 0);
    }

    function _renderKanban(datos) {
        const kanban = document.getElementById('tablero-kanban');
        if (!kanban) return;

        // Agrupar por área
        const porArea = {};
        AREAS_ORDER.forEach(a => { porArea[a] = []; });
        datos.forEach(s => {
            if (porArea[s.area] !== undefined) porArea[s.area].push(s);
            else porArea[s.area] = [s];
        });

        // Sólo mostrar áreas con tareas (o todas si es admin)
        const role = (_sesion?.role || '').toLowerCase();
        const esAdmin = role === 'admin' || role === 'gerencia';
        const mostrar = esAdmin
            ? AREAS_ORDER
            : AREAS_ORDER.filter(a => porArea[a]?.length > 0);

        if (!mostrar.length) {
            kanban.innerHTML = GtaUi.empty('No hay solicitudes activas.');
            return;
        }

        kanban.innerHTML = mostrar.map(area => {
            const items = porArea[area] || [];
            return `
            <div class="gta-kanban-col" data-area="${area}">
                <div class="gta-kanban-col-header">
                    <div class="gta-area-icon"><i class="fas ${GtaUi.areaIcon(area)}"></i></div>
                    <div class="gta-kanban-col-title">${GtaUi.areaLabel(area)}</div>
                    <div class="gta-kanban-col-count">${items.length}</div>
                </div>
                ${items.length
                    ? items.map(s => GtaUi.cardSolicitud(s)).join('')
                    : `<div style="color:var(--text-soft);font-size:0.78rem;text-align:center;padding:1.5rem 0;opacity:0.5;">Sin solicitudes</div>`
                }
            </div>`;
        }).join('');
    }

    return { init, cargar, filtrar };
})();
