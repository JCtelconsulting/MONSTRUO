// GTA UI v2 — helpers de renderizado compartidos entre tabs
window.GtaUi = (() => {

    const AREAS = {
        comercial:     { label: 'Comercial',      icon: 'fa-handshake' },
        preventa:      { label: 'Preventa',        icon: 'fa-search-dollar' },
        redes:         { label: 'Redes',           icon: 'fa-network-wired' },
        sistemas:      { label: 'Sistemas',        icon: 'fa-server' },
        finanzas:      { label: 'Finanzas',        icon: 'fa-file-invoice-dollar' },
        proveedores:   { label: 'Proveedores',     icon: 'fa-truck' },
        capital_humano:{ label: 'Capital Humano',  icon: 'fa-users' },
        bodega:        { label: 'Bodega',          icon: 'fa-warehouse' },
        ia:            { label: 'Especialista IA', icon: 'fa-robot' },
    };

    const TIPO_QUIEBRE = {
        sin_proceso:   { label: 'Sin proceso',   icon: 'fa-question-circle' },
        paso_bloqueado:{ label: 'Paso bloqueado', icon: 'fa-ban' },
        sla_vencido:   { label: 'SLA Vencido',   icon: 'fa-clock' },
    };

    function areaLabel(area) {
        return AREAS[area]?.label || area;
    }

    function areaIcon(area) {
        return AREAS[area]?.icon || 'fa-circle';
    }

    function semaforo(solicitud) {
        if (solicitud.estado === 'bloqueado') return 'rojo';
        if (solicitud.estado === 'completado' || solicitud.estado === 'cancelado') return 'verde';
        if (!solicitud.sla_horas || !solicitud.created_at) return '';
        const creado = new Date(solicitud.created_at);
        const vence  = new Date(creado.getTime() + solicitud.sla_horas * 3600000);
        const ahora  = new Date();
        const restPct = (vence - ahora) / (vence - creado) * 100;
        if (restPct <= 0)   return 'rojo';
        if (restPct <= 20)  return 'amarillo';
        return 'verde';
    }

    function tiempoRestante(solicitud) {
        if (!solicitud.sla_horas || !solicitud.created_at) return '';
        const creado = new Date(solicitud.created_at);
        const vence  = new Date(creado.getTime() + solicitud.sla_horas * 3600000);
        const diff   = vence - new Date();
        if (diff <= 0) return { texto: 'Vencida', clase: 'urgente' };
        const h = Math.floor(diff / 3600000);
        const m = Math.floor((diff % 3600000) / 60000);
        const texto = h > 48 ? `${Math.floor(h/24)}d restantes` : `${h}h ${m}m restantes`;
        return { texto, clase: h < 8 ? 'urgente' : h < 24 ? 'alerta' : '' };
    }

    function cardSolicitud(s) {
        const sem   = semaforo(s);
        const tiempo = tiempoRestante(s);
        return `
        <div class="gta-card semaforo-${sem}" onclick="GtaCore.abrirSolicitud(${s.id})">
            <div class="gta-card-titulo">${escHtml(s.titulo)}</div>
            <div class="gta-card-proceso">
                <i class="fas fa-sitemap"></i> ${escHtml(s.proceso_nombre || 'Sin proceso')}
            </div>
            <div class="gta-card-footer">
                <span class="gta-tag ${s.prioridad}">${s.prioridad || 'media'}</span>
                <span class="gta-tag estado-${s.estado}">${estadoLabel(s.estado)}</span>
                ${tiempo ? `<span class="gta-card-tiempo ${tiempo.clase}"><i class="fas fa-clock"></i>${tiempo.texto}</span>` : ''}
            </div>
        </div>`;
    }

    function procesoCard(p) {
        return `
        <div class="gta-proceso-card" onclick="GtaCore.seleccionarProceso(${p.id})">
            <div class="gta-proceso-card-icon"><i class="fas ${p.icono || 'fa-tasks'}"></i></div>
            <div class="gta-proceso-card-nombre">${escHtml(p.nombre)}</div>
            <div class="gta-proceso-card-desc">${escHtml(p.descripcion || '')}</div>
            <div class="gta-proceso-card-meta">
                <span class="gta-tag">${areaLabel(p.area)}</span>
                ${p.pasos_count ? `<span class="gta-tag"><i class="fas fa-list"></i> ${p.pasos_count} pasos</span>` : ''}
                ${p.sla_horas ? `<span class="gta-proceso-sla"><i class="fas fa-clock"></i> ${p.sla_horas}h SLA</span>` : ''}
            </div>
        </div>`;
    }

    function quiebreRow(q) {
        const tipo = TIPO_QUIEBRE[q.tipo] || { label: q.tipo, icon: 'fa-flag' };
        return `
        <div class="gta-quiebre-row" onclick="GtaCore.abrirQuiebre(${q.id})">
            <div class="gta-quiebre-icon ${q.tipo}"><i class="fas ${tipo.icon}"></i></div>
            <div class="gta-quiebre-body">
                <div class="gta-quiebre-titulo">${escHtml(q.descripcion)}</div>
                <div class="gta-quiebre-meta">
                    <span><i class="fas fa-building"></i> ${areaLabel(q.area)}</span>
                    <span><i class="fas fa-user"></i> ${escHtml(q.reportado_por)}</span>
                    <span><i class="fas fa-calendar"></i> ${fmtFecha(q.created_at)}</span>
                    <span class="gta-quiebre-badge ${q.tipo}">${tipo.label}</span>
                    ${q.estado === 'resuelto' ? '<span class="gta-quiebre-badge resuelto">Resuelto</span>' : ''}
                </div>
            </div>
            <div class="gta-quiebre-actions">
                ${q.estado !== 'resuelto' ? `<button class="btn-sm" onclick="event.stopPropagation(); GtaCore.resolverQuiebre(${q.id})">Resolver</button>` : ''}
            </div>
        </div>`;
    }

    function estadoLabel(e) {
        const m = { pendiente:'Pendiente', en_progreso:'En progreso', completado:'Completado', bloqueado:'Bloqueado', cancelado:'Cancelado' };
        return m[e] || e;
    }

    function fmtFecha(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            return d.toLocaleDateString('es-CL', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' });
        } catch { return iso; }
    }

    // Formato humano para SLA en HORAS LABORALES.
    //   Día laboral = 8 horas (jornada chilena estándar).
    //   Semana laboral = 5 días = 40 horas (no se usa para no inflar).
    // Hasta 1 día laboral muestra solo horas; arriba muestra "N días lab. (Mh)".
    function fmtSla(horas) {
        const h = Number(horas || 0);
        if (h <= 0) return '—';
        if (h < 8) return `${h}h`;
        const dias = Math.round(h / 8);
        return `${dias} día${dias === 1 ? '' : 's'} lab. (${h}h)`;
    }

    function escHtml(s) {
        return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function empty(msg = 'Sin registros') {
        return `<div class="gta-loading" style="padding:3rem;"><i class="fas fa-inbox" style="font-size:2rem;display:block;margin-bottom:12px;opacity:0.3;"></i>${msg}</div>`;
    }

    return { AREAS, TIPO_QUIEBRE, areaLabel, areaIcon, semaforo, tiempoRestante, cardSolicitud, procesoCard, quiebreRow, estadoLabel, fmtFecha, fmtSla, escHtml, empty };
})();
