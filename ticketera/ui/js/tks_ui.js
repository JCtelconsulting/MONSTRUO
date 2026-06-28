/**
 * Ticketera V3 — Capa UI
 * Renderizado puro: recibe datos, devuelve HTML.
 */
const TksUI = (() => {
    const WAITING_SUBESTADOS = Object.freeze(['pendiente_cliente', 'pendiente_compra', 'pendiente_tercero', 'pendiente_gerencia']);

    // --- Helpers ---
    function escapeHtml(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function escapeJsSingleQuoted(text) {
        if (text == null) return '';
        return String(text)
            .replace(/\\/g, "\\\\")
            .replace(/'/g, "\\'")
            .replace(/\r/g, "\\r")
            .replace(/\n/g, "\\n")
            .replace(/<\/script/gi, "<\\/script");
    }

    function slaStatus(venceAt) {
        if (!venceAt) return { class: '', label: '' };
        const now = new Date();
        const vence = new Date(venceAt);
        const diffH = (vence - now) / (1000 * 60 * 60);
        if (diffH < 0) return { class: 'tks-sla-breached', label: `⚠ VENCIDO (${Math.abs(Math.round(diffH))}h)` };
        if (diffH < 4) return { class: 'tks-sla-warning', label: `⏰ ${Math.round(diffH)}h restantes` };
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { class: 'tks-sla-ok', label: `${Math.round(diffH)}h restantes` };
    }

    const CATEGORY_LABELS = Object.freeze({
        redes: 'Redes',
        sistemas: 'Sistemas',
        ejecucion: 'Ejecución',
        admin: 'Admin',
        general: 'General',
        bodega: 'Bodega',
        gerencia: 'Gerencia',
    });

    const ROLE_CAPABILITY_LABELS = Object.freeze({
        admin: 'Admin',
        encargado_mesa: 'Encargado Mesa',
        ops: 'Operaciones',
        redes: 'Redes',
        sistemas: 'Sistemas',
        implementaciones: 'Implementaciones',
        gerencia: 'Gerencia',
        finance: 'Finanzas',
        warehouse: 'Bodega',
    });

    function catLabel(cat) {
        return CATEGORY_LABELS[cat] || escapeHtml(cat) || 'General';
    }

    function roleCapabilityLabel(role) {
        return ROLE_CAPABILITY_LABELS[String(role || '').trim().toLowerCase()] || escapeHtml(role || '-');
    }

    function formatAssigneeDisplay(rawValue) {
        const raw = String(rawValue || '').trim();
        if (!raw) return 'Sin asignar';
        const local = raw.includes('@') ? raw.split('@')[0] : raw;
        const clean = local.replace(/[._-]+/g, ' ').replace(/\s+/g, ' ').trim();
        if (!clean) return raw;
        return clean
            .split(' ')
            .filter(Boolean)
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join(' ');
    }

    function statusLabel(s) {
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { abierto: 'Abierto', en_progreso: 'En Progreso', resuelto: 'Resuelto', cerrado: 'Cerrado', papelera: 'Papelera' }[s] || subestadoLabel(s);
    }

    function ticketDisplayStatusKey(ticket) {
        const raw = String(ticket?.display_estado || '').trim().toLowerCase();
        if (raw) return raw;
        const trashed = ticket?.is_trashed === true || String(ticket?.is_trashed || '').trim().toLowerCase() === 'true' || String(ticket?.is_trashed || '').trim() === '1';
        if (trashed) return 'papelera';
        return String(ticket?.estado || '').trim().toLowerCase();
    }

    function normalizeSubestadoKey(value) {
        const normalized = String(value || '').trim().toLowerCase();
        if (normalized === 'triage' || normalized === 'nuevo') return 'recibido';
        return normalized;
    }

    function subestadoLabel(s) {
        const normalized = normalizeSubestadoKey(s);
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            recibido: 'Recibido',
            asignado: 'Asignado',
            en_analisis: 'En análisis',
            pendiente_compra: 'Pendiente compra',
            pendiente_cliente: 'Pendiente cliente',
            pendiente_tercero: 'Pendiente tercero',
            pendiente_gerencia: 'Pendiente aprobación',
            pendiente_aprobacion_1: 'Pendiente aprobación 1',
            pendiente_aprobacion_2: 'Pendiente aprobación 2',
            aprobado: 'Aprobado',
            rechazado: 'Rechazado',
            en_ejecucion: 'En ejecución',
            en_validacion: 'En validación',
            reabierto: 'Reabierto',
            en_progreso: 'En progreso',
            resuelto: 'Resuelto',
            cerrado: 'Cerrado',
        }[normalized] || escapeHtml(s || '-');
    }

    function sevLabel(s) {
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { critica: 'Crítica', alta: 'Alta', media: 'Media', baja: 'Baja' }[s] || escapeHtml(s);
    }

    function sentenceCase(text) {
        const value = String(text || '').trim();
        if (!value) return '-';
        return value.charAt(0).toUpperCase() + value.slice(1);
    }

    function humanizeMachineText(value) {
        const raw = String(value || '').trim();
        if (!raw) return '-';
        const normalized = raw
            .replace(/[_-]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim()
            .toLowerCase();
        const dictionary = {
            queue: 'cola',
            job: 'trabajo',
            jobs: 'trabajos',
            channel: 'canal',
            channels: 'canales',
            notification: 'notificación',
            notifications: 'notificaciones',
            dispatch: 'despacho',
            recover: 'recuperación',
            stale: 'huérfano',
            running: 'ejecutando',
            failed: 'fallido',
            pending: 'pendiente',
            created: 'creado',
            daily: 'diario',
            sync: 'sincronización',
            export: 'exportación',
            compliance: 'cumplimiento',
            incoming: 'entrante',
            outgoing: 'saliente',
            email: 'correo',
            poll: 'lectura',
            retry: 'reintento',
            retries: 'reintentos',
        };
        const translated = normalized
            .split(' ')
            .map((token) => dictionary[token] || token)
            .join(' ');
        return sentenceCase(translated);
    }

    function opsStatusLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            pending: 'Pendiente',
            dispatching: 'Despachando',
            sent: 'Enviado',
            failed: 'Fallido',
            cancelled: 'Cancelado',
            running: 'Ejecutando',
            retry: 'Reintento',
            completed: 'Completado',
            completed_with_errors: 'Completado con errores',
            queued: 'En cola',
            in_progress: 'En progreso',
            success: 'Exitoso',
            error: 'Error',
            done: 'Finalizado',
        }[normalized] || humanizeMachineText(value);
    }

    function adapterModeLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            disabled: 'Deshabilitado',
            dry_run: 'Simulación',
            live: 'Activo',
        }[normalized] || humanizeMachineText(value);
    }

    function channelLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            whatsapp: 'WhatsApp',
            '3cx': '3CX',
            email: 'Correo',
            sms: 'SMS',
            teams: 'Microsoft Teams',
            slack: 'Slack',
        }[normalized] || humanizeMachineText(value);
    }

    function jobTypeLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            ticket_channels_dispatch: 'Despacho de notificaciones de canales',
            ticket_email_incoming_poll: 'Lectura de correo entrante',
            ticket_email_reconcile: 'Conciliación de correo de tickets',
            compliance_export_run: 'Ejecución de exportación de cumplimiento',
            compliance_purge_run: 'Depuración de datos de cumplimiento',
            auto_reply_dispatch: 'Despacho de autorrespuestas',
            jobs_recover_stale: 'Recuperación de ejecuciones huérfanas',
        }[normalized] || humanizeMachineText(value);
    }

    function parseEmailIdentity(raw) {
        const text = String(raw || '').trim();
        if (!text) return { name: '', email: '' };

        const angled = text.match(/^\s*"?([^"<]+?)"?\s*<\s*([^>]+)\s*>\s*$/);
        if (angled) {
        
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { name: angled[1].trim(), email: angled[2].trim() };
        }

        const mail = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
        if (!mail) return { name: text, email: '' };

        const email = mail[0].trim();
        const name = text.replace(mail[0], '').replace(/[<>()"]/g, '').trim();
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { name, email };
    }

    function identityHtml(raw) {
        const parsed = parseEmailIdentity(raw);
        if (parsed.name && parsed.email) {
            return `${escapeHtml(parsed.name)} <span class="tks-email-addr">&lt;${escapeHtml(parsed.email)}&gt;</span>`;
        }
        return escapeHtml(parsed.email || parsed.name || '-');
    }

    function identityListHtml(raw) {
        const tokens = String(raw || '')
            .split(/[,\n;]+/)
            .map((v) => String(v || '').trim())
            .filter(Boolean);
        if (!tokens.length) return '-';
        return tokens.map((token) => identityHtml(token)).join(', ');
    }

    function parseAttachmentsJson(rawValue) {
        if (!rawValue) return [];
        if (Array.isArray(rawValue)) return rawValue;
        try {
            const parsed = JSON.parse(rawValue);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function normalizePath(rawPath) {
        return String(rawPath || '')
            .trim()
            .replace(/\\/g, '/')
            .replace(/\/+/g, '/')
            .toLowerCase();
    }

    function sizeLabel(bytesLike) {
        const bytes = Number(bytesLike || 0);
        const kb = Math.max(0, Math.round(bytes / 1024));
        return `${kb}KB`;
    }

    function formatCountdownRemaining(msLike) {
        const safeMs = Math.max(0, Number(msLike || 0));
        const totalSeconds = Math.floor(safeMs / 1000);
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        if (days > 0) return `${days}d ${hours}h ${minutes}m`;
        if (hours > 0) return `${hours}h ${minutes}m`;
        if (minutes > 0) return `${minutes}m ${seconds}s`;
        return `${seconds}s`;
    }

    function buildEmailAttachmentResolver(ticketId, ticketAttachments = []) {
        const bySha = new Map();
        const byPath = new Map();
        const byName = new Map();

        (ticketAttachments || []).forEach((att) => {
            const id = Number(att?.id || 0);
            if (!id) return;

            const sha = String(att?.sha256 || '').trim().toLowerCase();
            if (sha && !bySha.has(sha)) bySha.set(sha, id);

            const path = normalizePath(att?.file_path || att?.path || '');
            if (path && !byPath.has(path)) byPath.set(path, id);

            const name = String(att?.filename || '').trim().toLowerCase();
            if (!name) return;
            const size = Number(att?.size_bytes ?? att?.size ?? 0);
            const key = `${name}::${size > 0 ? size : '?'}`;
            if (!byName.has(key)) byName.set(key, id);
        });

        return (mailAttachment) => {
            const directId = Number(mailAttachment?.attachment_id || mailAttachment?.id || 0);
            if (directId) return directId;

            const sha = String(mailAttachment?.sha256 || '').trim().toLowerCase();
            if (sha && bySha.has(sha)) return bySha.get(sha);

            const path = normalizePath(mailAttachment?.path || mailAttachment?.file_path || '');
            if (path && byPath.has(path)) return byPath.get(path);

            const name = String(mailAttachment?.filename || '').trim().toLowerCase();
            if (!name) return null;

            const size = Number(mailAttachment?.size_bytes ?? mailAttachment?.size ?? 0);
            const key = `${name}::${size > 0 ? size : '?'}`;
            if (byName.has(key)) return byName.get(key);

            for (const [candidate, attachmentId] of byName.entries()) {
                if (candidate.startsWith(`${name}::`)) return attachmentId;
            }

            return null;
        };
    }

    function attachmentContentType(att) {
        const explicit = String(att?.content_type || att?.mime_type || '').trim().toLowerCase();
        if (explicit) return explicit;
        const filename = String(att?.filename || '').trim().toLowerCase();
        if (!filename.includes('.')) return 'application/octet-stream';
        const ext = filename.split('.').pop();
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            jpg: 'image/jpeg',
            jpeg: 'image/jpeg',
            png: 'image/png',
            gif: 'image/gif',
            webp: 'image/webp',
            bmp: 'image/bmp',
            svg: 'image/svg+xml',
            pdf: 'application/pdf',
            txt: 'text/plain',
            log: 'text/plain',
            csv: 'text/csv',
            json: 'application/json',
            mp4: 'video/mp4',
            webm: 'video/webm',
            mp3: 'audio/mpeg',
            wav: 'audio/wav',
        }[ext] || 'application/octet-stream';
    }

    function attachmentPreviewKind(att) {
        const contentType = attachmentContentType(att);
        if (contentType.startsWith('image/')) return 'image';
        if (contentType === 'application/pdf') return 'pdf';
        if (contentType.startsWith('text/') || contentType === 'application/json') return 'text';
        if (contentType.startsWith('video/')) return 'video';
        if (contentType.startsWith('audio/')) return 'audio';
        return 'file';
    }

    function attachmentKindLabel(att) {
        const kind = attachmentPreviewKind(att);
        if (kind === 'image') return 'IMG';
        if (kind === 'pdf') return 'PDF';
        if (kind === 'text') return 'TXT';
        if (kind === 'video') return 'VIDEO';
        if (kind === 'audio') return 'AUDIO';
        const filename = String(att?.filename || '').trim();
        if (filename.includes('.')) {
            return filename.split('.').pop().slice(0, 5).toUpperCase();
        }
        return 'FILE';
    }

    function attachmentIconClass(att) {
        const kind = attachmentPreviewKind(att);
        if (kind === 'image') return 'fa-file-image';
        if (kind === 'pdf') return 'fa-file-pdf';
        if (kind === 'text') return 'fa-file-lines';
        if (kind === 'video') return 'fa-file-video';
        if (kind === 'audio') return 'fa-file-audio';
        return 'fa-file';
    }

    function attachmentCanInlinePreview(att) {
        const kind = attachmentPreviewKind(att);
        return kind === 'image' || kind === 'pdf' || kind === 'text';
    }

    function normalizeInlineContentId(value) {
        return String(value || '')
            .trim()
            .toLowerCase()
            .replace(/^cid:/, '')
            .replace(/[<>]/g, '');
    }

    function emailBodyReferencesAttachment(ticketId, bodyHtml, attachmentId, contentId = '') {
        const htmlValue = String(bodyHtml || '').trim().toLowerCase();
        if (!htmlValue) return false;

        const normalizedAttachmentId = Number(attachmentId || 0);
        if (normalizedAttachmentId > 0) {
            const inlinePath = `attachments/${normalizedAttachmentId}/download?inline=1`;
            const ticketInlinePath = `/tickets/${Number(ticketId)}/attachments/${normalizedAttachmentId}/download?inline=1`;
            if (htmlValue.includes(inlinePath) || htmlValue.includes(ticketInlinePath)) return true;
        }

        const normalizedCid = normalizeInlineContentId(contentId);
        return normalizedCid ? htmlValue.includes(`cid:${normalizedCid}`) : false;
    }

    function shouldHideInlineAttachmentFromList(ticketId, bodyHtml, mailAttachment, attachmentId) {
        const disposition = String(mailAttachment?.disposition || '').trim().toLowerCase();
        const isInline = Boolean(mailAttachment?.is_inline)
            || Boolean(normalizeInlineContentId(mailAttachment?.content_id))
            || disposition.includes('inline');
        if (!isInline) return false;
        return emailBodyReferencesAttachment(ticketId, bodyHtml, attachmentId, mailAttachment?.content_id);
    }

    function renderAttachmentCard(ticketId, attachmentId, attachment, options = {}) {
        const compact = options.compact === true;
        const filename = String(attachment?.filename || 'adjunto').trim() || 'adjunto';
        const contentType = attachmentContentType(attachment);
        const inlineUrl = attachmentId ? TksApi.getTicketAttachmentInlineUrl(ticketId, attachmentId) : '';
        const classes = [
            'tks-attachment-card',
            compact ? 'compact' : '',
            attachmentId ? '' : 'is-disabled',
            attachmentPreviewKind(attachment) === 'image' ? 'is-image' : '',
        ].filter(Boolean).join(' ');
        const showImageThumb = attachmentId && !compact && attachmentPreviewKind(attachment) === 'image';
        let thumbHtml = '';
        if (!compact) {
            thumbHtml = showImageThumb
                ? `<div class="tks-attachment-thumb">
                        <img src="${escapeHtml(inlineUrl)}" alt="${escapeHtml(filename)}" loading="lazy">
                   </div>`
                : `<div class="tks-attachment-thumb is-generic">
                        <i class="fas ${attachmentIconClass(attachment)}"></i>
                        <span>${escapeHtml(attachmentKindLabel(attachment))}</span>
                   </div>`;
        }
        
        const compactIcon = compact ? `<i class="fas ${attachmentIconClass(attachment)} tks-compact-icon"></i>` : '';
        
        const metaHtml = `
            <div class="tks-attachment-meta">
                <span class="tks-attachment-name">${compactIcon} ${escapeHtml(filename)}</span>
                <span class="tks-attachment-sub">${sizeLabel(attachment?.size_bytes ?? attachment?.size ?? 0)} · ${escapeHtml(attachmentCanInlinePreview(attachment) ? 'Vista previa' : 'Abrir archivo')}</span>
            </div>
        `;
        if (!attachmentId) {
            return `<div class="${classes}" title="Adjunto histórico sin archivo asociado">${thumbHtml}${metaHtml}</div>`;
        }
        return `<button
            class="${classes}"
            type="button"
            onclick="TksMain.openAttachmentPreview(${Number(ticketId)}, ${Number(attachmentId)}, '${escapeJsSingleQuoted(filename)}', '${escapeJsSingleQuoted(contentType)}', ${Number(attachment?.size_bytes ?? attachment?.size ?? 0)})"
        >${thumbHtml}${metaHtml}</button>`;
    }

    function renderAttachmentPreviewModal(attachment) {
        const ticketId = Number(attachment?.ticketId || 0);
        const attachmentId = Number(attachment?.attachmentId || 0);
        const filename = String(attachment?.filename || 'adjunto').trim() || 'adjunto';
        const contentType = attachmentContentType(attachment);
        const kind = attachmentPreviewKind({ content_type: contentType, filename });
        const inlineUrl = attachmentId ? TksApi.getTicketAttachmentInlineUrl(ticketId, attachmentId) : '';
        const downloadUrl = attachmentId ? TksApi.getTicketAttachmentDownloadUrl(ticketId, attachmentId) : '';
        let previewHtml = `
            <div class="tks-attachment-preview-empty">
                <i class="fas ${attachmentIconClass({ content_type: contentType, filename })}"></i>
                <p>Este tipo de archivo no tiene vista previa inline.</p>
            </div>
        `;
        if (kind === 'image') {
            previewHtml = `<img class="tks-attachment-preview-image" src="${escapeHtml(inlineUrl)}" alt="${escapeHtml(filename)}">`;
        } else if (kind === 'pdf' || kind === 'text') {
            previewHtml = `<iframe class="tks-attachment-preview-frame" src="${escapeHtml(inlineUrl)}" title="${escapeHtml(filename)}"></iframe>`;
        }
        return `
        <div class="tks-modal-overlay open" id="tks-attachment-preview-modal">
            <div class="tks-modal tks-attachment-preview-modal">
                <div class="tks-modal-header">
                    <h3>${escapeHtml(filename)}</h3>
                    <button class="tks-modal-close" type="button" onclick="TksMain.closeAttachmentPreview()">&times;</button>
                </div>
                <div class="tks-modal-body">
                    <div class="tks-attachment-preview-meta">
                        <span>${escapeHtml(contentType)}</span>
                        <span>${sizeLabel(attachment?.size_bytes ?? attachment?.size ?? 0)}</span>
                    </div>
                    <div class="tks-attachment-preview-stage">
                        ${previewHtml}
                    </div>
                </div>
                <div class="tks-modal-footer">
                    <button class="tks-btn tks-btn-ghost" type="button" onclick="TksMain.closeAttachmentPreview()">Cerrar</button>
                    ${downloadUrl ? `<a class="tks-btn tks-btn-primary" href="${escapeHtml(downloadUrl)}" download rel="noopener">Descargar</a>` : ''}
                </div>
            </div>
        </div>`;
    }

    function toTs(value) {
        const ts = Date.parse(String(value || ''));
        return Number.isFinite(ts) ? ts : 0;
    }

    function formatDateTimeShort(value) {
        const ts = toTs(value);
        if (!ts) return '-';
        try {
            return new Date(ts).toLocaleString('es-CL', {
                day: '2-digit',
                month: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (e) {
            return String(value || '-');
        }
    }

    function formatExactDateTime(value) {
        const ts = toTs(value);
        if (!ts) return '-';
        try {
            const d = new Date(ts);
            const formatter = new Intl.DateTimeFormat('es-CL', {
                timeZone: 'America/Santiago',
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
            const parts = formatter.formatToParts(d);
            const p = {};
            parts.forEach(part => p[part.type] = part.value);
            return `${p.day}-${p.month}-${p.year} ${p.hour}:${p.minute}`;
        } catch (e) {
            return String(value || '-');
        }
    }

    function formatTimeOnly(value) {
        const ts = toTs(value);
        if (!ts) return '';
        try {
            const d = new Date(ts);
            return d.toLocaleTimeString('es-CL', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: false
            });
        } catch (e) {
            return '';
        }
    }

    function formatMinutesLabel(minutesLike) {
        const minutes = Math.max(0, Number(minutesLike || 0));
        if (minutes < 60) return `${Math.round(minutes)}m`;
        const h = Math.floor(minutes / 60);
        const m = Math.round(minutes % 60);
        if (h < 24) return `${h}h ${m}m`;
        const d = Math.floor(h / 24);
        const rh = h % 24;
        return `${d}d ${rh}h`;
    }

    function phaseLabel(phase) {
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            asignado: 'Asignado',
            en_progreso: 'En progreso',
            resuelto: 'Resuelto',
        }[String(phase || '').trim().toLowerCase()] || 'Sin fase';
    }

    function formatHourLabel(hourLike) {
        const hour = Math.max(0, Math.min(23, Number(hourLike || 0)));
        return `${String(hour).padStart(2, '0')}:00`;
    }

    function buildTimelineAxisFromRange(startTs, endTs) {
        const viewStartTs = startTs;
        const viewEndTs = endTs;
        const viewSpan = Math.max(1, viewEndTs - viewStartTs);
        const spanDays = viewSpan / (24 * 3600 * 1000);

        // Ticks cada 3 horas, alineados a múltiplos de 3 (0, 3, 6, 9, 12, 15, 18, 21)
        const ticks = [];
        const d = new Date(viewStartTs);
        // Redondear hacia arriba al próximo múltiplo de 3h
        const h0 = d.getHours();
        const nextMult3 = Math.ceil(h0 / 3) * 3;
        d.setHours(nextMult3, 0, 0, 0);
        while (d.getTime() <= viewEndTs) {
            const label = `${String(d.getHours()).padStart(2,'0')}:00`;
            ticks.push({ ts: d.getTime(), label });
            d.setHours(d.getHours() + 3);
        }

        const tickLinesHtml = ticks.map(t => {
            const leftPct = ((t.ts - viewStartTs) / viewSpan) * 100;
            return `<span class="tks-assign-grid-line labor" style="left:${leftPct.toFixed(3)}%"></span>`;
        }).join('');

        const rulerHtml = ticks.map(t => {
            const leftPct = ((t.ts - viewStartTs) / viewSpan) * 100;
            return `<span class="tks-assign-ruler-tick labor" style="--tick-left:${leftPct.toFixed(3)}%; left:${leftPct.toFixed(3)}%">${escapeHtml(t.label)}</span>`;
        }).join('');

        return { viewStartTs, viewEndTs, viewSpan, tickLinesHtml, rulerHtml };
    }

    function buildTimelineAxis(dayStart) {
        const viewStartTs = dayStart.getTime() + (8 * 60 * 60 * 1000); // 8:00
        const viewEndTs = dayStart.getTime() + (18 * 60 * 60 * 1000); // 18:00
        const viewSpan = Math.max(1, viewEndTs - viewStartTs);

        const hourTicks = [];
        for (let h = 8; h <= 18; h += 1) {
            const ts = dayStart.getTime() + (h * 60 * 60 * 1000);
            const leftPct = ((ts - viewStartTs) / viewSpan) * 100;
            hourTicks.push({ hour: h, leftPct, isLabor: true });
        }

        const tickLinesHtml = hourTicks
            .map((tick) => `<span class="tks-assign-grid-line ${tick.isLabor ? 'labor' : 'extra'}" style="left:${tick.leftPct.toFixed(3)}%"></span>`)
            .join('');

        const rulerHtml = hourTicks
            .map((tick) => {
                const showLabel = (tick.hour % 2 === 0) || tick.hour === 8 || tick.hour === 18;
                if (!showLabel) return '';
                return `<span class="tks-assign-ruler-tick ${tick.isLabor ? 'labor' : 'extra'}" style="--tick-left:${tick.leftPct.toFixed(3)}%; left:${tick.leftPct.toFixed(3)}%">${escapeHtml(formatHourLabel(tick.hour))}</span>`;
            })
            .join('');

    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { viewStartTs, viewEndTs, viewSpan, tickLinesHtml, rulerHtml };
    }

    function renderTechnicianLane(tech, viewStartTs, viewEndTs, viewSpan) {
        const items = Array.isArray(tech.items) ? tech.items : [];
        const status = String(tech.status || '').trim().toLowerCase();
        const techName = String(tech.username || '-');
        const roles = Array.isArray(tech.roles) ? tech.roles : [];
        const specialties = Array.isArray(tech.specialties) ? tech.specialties : [];
        const capabilitySource = roles.length > 0 ? roles : specialties;
        const techCapabilities = [];
        const isAvailable = status === 'disponible';
        
        capabilitySource.forEach((capability) => {
            const label = roles.length > 0 ? roleCapabilityLabel(capability) : catLabel(capability);
            if (label && !techCapabilities.includes(label)) techCapabilities.push(label);
        });

        const nextTicket = tech.next_queue_ticket || null;
        
        // 1. Agrupar segmentos por Ticket
        const ticketGroups = new Map();
        items.forEach(item => {
            const code = String(item.codigo || `#${item.ticket_id || '-'}`);
            if (!ticketGroups.has(code)) {
                ticketGroups.set(code, {
                    code,
                    title: String(item.titulo || 'Sin título'),
                    estado: item.estado,
                    segments: []
                });
            }
            const segments = Array.isArray(item.segments) ? item.segments : [];
            segments.forEach(seg => {
                const start = toTs(seg.start_at);
                const end = toTs(seg.end_at);
                if (!start || !end) return;
                const clippedStart = Math.max(start, viewStartTs);
                const clippedEnd = Math.min(end, viewEndTs);
                if (clippedEnd <= clippedStart) return;
                
                ticketGroups.get(code).segments.push({
                    start: clippedStart,
                    end: clippedEnd,
                    phase: String(seg.phase || item.active_phase || 'asignado').toLowerCase()
                });
            });
        });

        // 2. Packing: Asignar tickets a filas (max 5)
        const rows = [[], [], [], [], []];
        const htmlGroups = [];

        Array.from(ticketGroups.values()).forEach(group => {
            if (!group.segments.length) return;
            
            const minStart = Math.min(...group.segments.map(s => s.start));
            const maxEnd = Math.max(...group.segments.map(s => s.end));
            
            let rowIndex = -1;
            for (let i = 0; i < rows.length; i++) {
                const overlap = rows[i].some(r => minStart < r.end && maxEnd > r.start);
                if (!overlap) { rowIndex = i; break; }
            }
            
            if (rowIndex !== -1) {
                rows[rowIndex].push({ start: minStart, end: maxEnd });
                
                const groupLeft = ((minStart - viewStartTs) / viewSpan) * 100;
                const groupWidth = ((maxEnd - minStart) / viewSpan) * 100;
                const top = 8 + (rowIndex * 40);
                const totalDuration = maxEnd - minStart;
                
                // Generar segmentos internos (franjas de color)
                const segmentsHtml = group.segments.map(seg => {
                    const segWidth = ((seg.end - seg.start) / totalDuration) * 100;
                    return `<div class="tks-assign-ticket-segment tks-assign-seg-${escapeHtml(seg.phase)}" style="width:${segWidth.toFixed(3)}%"></div>`;
                }).join('');

                const fullTitle = `${group.code} · ${statusLabel(group.estado)} · ${group.title}`;
                
                htmlGroups.push(`
                    <div class="tks-assign-ticket-group" 
                         style="left:${groupLeft.toFixed(3)}%; width:${groupWidth.toFixed(3)}%; top:${top}px" 
                         title="${escapeHtml(fullTitle)}">
                        ${segmentsHtml}
                        <span class="tks-assign-group-label">${escapeHtml(group.code)}</span>
                    </div>
                `);
            }
        });

        const blocksHtml = htmlGroups.length ? htmlGroups.join('') : '<span class="tks-assign-row-empty">Sin actividad en este horario.</span>';
        const trackHeight = Math.max(48, 8 + (rows.filter(r => r.length > 0).length * 40));

        const nextQueueHtml = nextTicket
            ? `<span class="tks-assign-next-inline">Siguiente sugerido: <strong>${escapeHtml(nextTicket.codigo || `#${nextTicket.ticket_id || '-'}`)}</strong></span>`
            : '<span class="tks-assign-next-inline empty">Sin ticket en cola sugerido.</span>';
return `
            <article class="tks-assign-schedule-row">
                <div class="tks-assign-tech-col">
                    <div class="tks-assign-tech-name">${escapeHtml(techName)}</div>
                    <div class="tks-assign-tech-meta">${escapeHtml(techCapabilities.join(' + ') || 'Sin rol técnico')}</div>
                    <div class="tks-assign-tech-status ${isAvailable ? 'available' : 'busy'}">${isAvailable ? 'Disponible' : 'Ocupado'}</div>
                </div>
                <div class="tks-assign-track-col">
                    <div class="tks-assign-track-schedule" style="height:${trackHeight}px">
                        <!-- TICK LINES WILL BE INJECTED EXTERNALLY OR OMITTED HERE;
                             We'll assume the timeline wrapper provides them as background, 
                             but original code had tickLinesHtml repeated here -->
                        ${blocksHtml}
                    </div>
                    <div class="tks-assign-row-foot">
                        <span>Tickets: ${escapeHtml(String(items.length || 0))}</span>
                        ${nextQueueHtml}
                    </div>
                </div>
            </article>`;
    }

    function renderAssignmentTimeline(data) {
        const payload = data || {};
        const technicians = Array.isArray(payload.technicians) ? payload.technicians : [];
        const queue = Array.isArray(payload.queue) ? payload.queue : [];
        const scopeMode = String(payload.scope || '').trim().toLowerCase();
        const showQueue = scopeMode !== 'mine';
        const generatedAt = payload.generated_at || '';

        // Ventana visible: últimas 24h desde ahora
        const rangeEndTs = toTs(payload?.range?.end_at || generatedAt || new Date().toISOString()) || Date.now();
        const fullRangeStartTs = toTs(payload?.range?.start_at || '') || (rangeEndTs - 24 * 3600 * 1000);
        const rangeStartTs = Math.max(fullRangeStartTs, rangeEndTs - 24 * 3600 * 1000);
        const axis = buildTimelineAxisFromRange(rangeStartTs, rangeEndTs);

        const sortedTechnicians = [...technicians].sort((a, b) => {
            const aName = String(a?.username || '').trim().toLowerCase();
            const bName = String(b?.username || '').trim().toLowerCase();
            const aGeneral = aName === 'general';
            const bGeneral = bName === 'general';
            if (aGeneral !== bGeneral) return aGeneral ? -1 : 1;
            return aName.localeCompare(bName, 'es');
        });

        const laneHtml = sortedTechnicians.map((tech) => {
            // We inject the tickLinesHtml directly into the lane output here
            let techHtml = renderTechnicianLane(tech, axis.viewStartTs, axis.viewEndTs, axis.viewSpan);
            techHtml = techHtml = techHtml.replace(/<!-- TICK LINES WILL BE INJECTED EXTERNALLY[\s\S]*?repeated here -->/, axis.tickLinesHtml);
            return techHtml;
        }).join('');

        const queueHtml = queue.length
            ? queue.map((q) => `<div class="tks-assign-queue-item">
                    <div class="tks-assign-queue-code">${escapeHtml(q.codigo || `#${q.ticket_id || '-'}`)}</div>
                    <div class="tks-assign-queue-title">${escapeHtml(q.titulo || 'Sin título')}</div>
                    <div class="tks-assign-queue-meta">${escapeHtml(catLabel(q.categoria || 'general'))} · Espera ${escapeHtml(formatMinutesLabel(q.waiting_minutes || 0))}</div>
                </div>`).join('')
            : '<div class="tks-assign-empty-lane">No hay tickets en cola sin asignar.</div>';

        return `<div class="tks-assign-view">
            <div class="tks-assign-head">
                <div>
                    <h3><i class="fas fa-users-cog"></i> Asignación Técnica</h3>
                    <div class="tks-assign-head-meta-new">
                        <span><strong>Desde:</strong> ${escapeHtml(new Date(rangeStartTs).toLocaleDateString('es-CL'))}</span>
                        <span class="tks-sep">·</span>
                        <span><strong>Actualizado:</strong> ${escapeHtml(formatExactDateTime(generatedAt))}</span>
                    </div>
                </div>
            </div>

            <div class="tks-assign-ruler-hours">
                ${axis.rulerHtml}
            </div>

            <div class="tks-assign-lanes">
                ${laneHtml || '<div class="tks-assign-empty-lane">No hay técnicos configurados.</div>'}
            </div>

            ${showQueue
                ? `<section class="tks-assign-queue">
                    <h4><i class="fas fa-inbox"></i> Cola sin asignar</h4>
                    <div class="tks-assign-queue-list">${queueHtml}</div>
                </section>`
                : ''}
        </div>`;
    }

    // --- DASHBOARD ---
    function formatSlaTargetLabel(totalMinutes) {
        const safeMinutes = Math.max(0, Number(totalMinutes || 0));
        if (!safeMinutes) return '-';
        if (safeMinutes === 60) return '1h';
        if (safeMinutes < 60) return `${safeMinutes}m`;
        const hours = safeMinutes / 60;
        return `${String(hours).replace(/\.0$/, '')}h`;
    }

    function renderHistoricalMetricCard(label, metric, targetMinutes) {
        const total = Number(metric?.total || 0);
        const onTime = Number(metric?.on_time || 0);
        const late = Number(metric?.late || 0);
        const pendingBreached = Number(metric?.pending_breached || 0);
        const compliancePct = Math.round(Number(metric?.compliance_pct || 0));
        return `
            <div class="tks-history-metric">
                <span class="tks-history-metric-label">${escapeHtml(label)}</span>
                <strong class="tks-history-metric-value">${total ? `${compliancePct}%` : '-'}</strong>
                <span class="tks-history-metric-sub">Objetivo ${escapeHtml(formatSlaTargetLabel(targetMinutes))}</span>
                <span class="tks-history-metric-foot">${onTime}/${total} en tiempo · ${late} tardíos · ${pendingBreached} pendientes vencidos</span>
            </div>
        `;
    }

    function renderHistoricalWindow(windowData) {
        if (!windowData?.metrics) {
            return `
                <article class="tks-history-card">
                    <div class="tks-history-card-head">
                        <div>
                            <span class="tks-history-card-kicker">Informe histórico</span>
                            <h4>${escapeHtml(windowData?.label || 'Sin periodo')}</h4>
                        </div>
                        <span class="tks-history-card-meta">Sin datos</span>
                    </div>
                    <div class="tks-feed-empty">No fue posible cargar este tramo.</div>
                </article>
            `;
        }
        const metrics = windowData.metrics || {};
        const hist = metrics.historical_sla || {};
        const targets = metrics.targets || {};
        return `
            <article class="tks-history-card">
                <div class="tks-history-card-head">
                    <div>
                        <span class="tks-history-card-kicker">Informe histórico</span>
                        <h4>${escapeHtml(windowData.label || 'Periodo')}</h4>
                    </div>
                    <span class="tks-history-card-meta">${Number(metrics.total || 0)} tickets</span>
                </div>
                <div class="tks-history-metric-grid">
                    ${renderHistoricalMetricCard('Auto-respuesta', hist.auto_reply, targets.auto_reply_minutes)}
                    ${renderHistoricalMetricCard('Asignación', hist.assignment, targets.assignment_minutes)}
                    ${renderHistoricalMetricCard('Resolución', hist.resolution, targets.resolution_minutes)}
                </div>
            </article>
        `;
    }

    function buildDashboardSummary(stats = {}) {
        const total = stats.total || 0;
        const activos = (stats.by_status?.abierto || 0) + (stats.by_status?.en_progreso || 0);
        const resueltos = (stats.by_status?.resuelto || 0) + (stats.by_status?.cerrado || 0);
        const criticas = stats.by_prio?.critica || 0;
        const onTime = stats.sla_compliance?.on_time || 0;
        const breached = stats.sla_compliance?.breached || 0;
        const slaTotal = onTime + breached;
        const slaPct = slaTotal > 0 ? Math.round((onTime / slaTotal) * 100) : 100;
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            total,
            activos,
            resueltos,
            criticas,
            onTime,
            breached,
            slaPct,
        };
    }

    function renderDashboardStats(summary) {
        return `
            <div class="tks-stats-row">
                <div class="tks-stat-card" style="--card-accent: var(--tks-abierto)">
                    <span class="label">Activos</span>
                    <span class="value">${summary.activos}</span>
                </div>
                <div class="tks-stat-card" style="--card-accent: var(--tks-cerrado)">
                    <span class="label">Resueltos</span>
                    <span class="value">${summary.resueltos}</span>
                </div>
                <div class="tks-stat-card" style="--card-accent: var(--tks-accent)">
                    <span class="label">Tickets Totales</span>
                    <span class="value">${summary.total}</span>
                </div>
            </div>
        `;
    }

    function renderDashboardSla(summary) {
        return `
            <div class="tks-sla-bar">
                <h4>📊 Cumplimiento SLA — ${summary.slaPct}%</h4>
                <div class="sla-progress">
                    <div class="on-time" style="width:${summary.slaPct}%"></div>
                    <div class="breached" style="width:${100 - summary.slaPct}%"></div>
                </div>
                <div class="sla-labels">
                    <span>✅ A tiempo: ${summary.onTime}</span>
                    <span>⚠ Vencidos: ${summary.breached}</span>
                </div>
            </div>
        `;
    }

    function renderDashboard(stats, assignmentData = null, historicalData = []) {
        const summary = buildDashboardSummary(stats);
        const historicalHtml = Array.isArray(historicalData) && historicalData.length
            ? `<div class="tks-history-grid">${historicalData.map((item) => renderHistoricalWindow(item)).join('')}</div>`
            : '';

        return `
        <div class="tks-dashboard">
            ${renderDashboardStats(summary)}
            ${historicalHtml}
            <div class="tks-dashboard-assignment">
                ${renderAssignmentTimeline(assignmentData || {})}
            </div>
        </div>`;
    }

    // --- UTILS ---
    function decodeMimeEncodedString(str) {
        if (!str) return '';
        // 1. Intentar decodificar headers MIME estándar (=?UTF-8?Q?...?=)
        let decoded = str.replace(/=\?UTF-8\?Q\?(.+?)\?=/gi, (match, p1) => {
            try {
                let hex = p1.replace(/_/g, ' ');
                hex = hex.replace(/=([0-9A-F]{2})/yi, '%$1');
                return decodeURIComponent(hex);
            } catch (e) {
                return match;
            }
        });

        // 2. Si quedan secuencias Quoted-Printable "crudas" (ej: Juan L=C3=B3pez), intentamos decodificarlas
        // Buscamos si hay al menos un patrón =XX donde XX es hex
        if (decoded.match(/=[0-9A-F]{2}/i)) {
            try {
                // Reemplazamos todos los =XX por %XX para que decodeURIComponent lo entienda
                // Asumimos UTF-8 ("Juan L=C3=B3pez" -> "Juan L%C3%B3pez" -> "Juan López")
                let candidate = decoded.replace(/=([0-9A-F]{2})/gi, '%$1');
                let tryDecoded = decodeURIComponent(candidate);
                if (tryDecoded !== candidate) {
                    decoded = tryDecoded;
                }
            } catch (e) {
                // Si falla (secuencia inválida), devolvemos lo que teníamos
            }
        }

        return decoded;
    }

    // --- TICKET TABLE (LISTA) ---
    function buildTicketRowViewModel(ticket) {
        const displayStatus = ticketDisplayStatusKey(ticket);
        const sla = displayStatus === 'papelera'
            ? { class: '', label: 'Archivado' }
            : slaStatus(ticket.vence_at);
        const slaClass = sla.class === 'tks-sla-breached'
            ? 'is-breached'
            : (sla.class === 'tks-sla-warning' ? 'is-warning' : 'is-ok');
        const clientNameRaw = decodeMimeEncodedString(ticket.cliente_nombre || '');
        const subjectNormalized = sentenceCase(ticket.titulo);
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
            ticket,
            displayStatus,
            sla,
            slaClass,
            clientNameRaw,
            subjectNormalized,
        };
    }

    function renderTicketClientCell(ticket, viewModel) {
        if (viewModel.clientNameRaw && viewModel.clientNameRaw !== 'Desconocido') {
            return `<div class="tks-client-cell"><div class="tks-client-name">${escapeHtml(viewModel.clientNameRaw)}</div></div>`;
        }
        if (ticket.origen_email) {
            const originEmailJs = escapeJsSingleQuoted(ticket.origen_email);
            return `<div class="tks-client-cell is-unknown"><button class="tks-btn-link tks-btn-link-compact" onclick="TksMain.openAssociateClientModal('${originEmailJs}'); return false;"><i class="fas fa-link"></i><span>Desconocido</span><span class="tks-btn-link-sep">·</span><span>Vincular</span></button></div>`;
        }
        return '<div class="tks-client-cell"><span class="tks-client-empty">-</span></div>';
    }

    function renderTicketRow(ticket) {
        const viewModel = buildTicketRowViewModel(ticket);
        return `<tr class="tks-row" data-id="${ticket.id}">
            <td class="td-min"><span class="tks-codigo">${escapeHtml(ticket.codigo || `#${ticket.id}`)}</span></td>
            <td>
                <div class="tks-ticket-title fade-overflow" title="${escapeHtml(ticket.titulo || 'Sin título')}">${escapeHtml(viewModel.subjectNormalized)}</div>
            </td>
            <td>
                ${renderTicketClientCell(ticket, viewModel)}
                ${ticket.origen_email ? `<div class="tks-origin-email">${escapeHtml(ticket.origen_email)}</div>` : ''}
            </td>
            <td class="td-min"><span class="tks-cat-badge tks-cat-${escapeHtml(ticket.categoria || 'general')}">${catLabel(ticket.categoria)}</span></td>
            <td class="td-min"><span class="tks-status tks-status-${escapeHtml(viewModel.displayStatus)}">${statusLabel(viewModel.displayStatus)}</span></td>
            <td class="td-min tks-sla-cell ${viewModel.slaClass}">
                ${viewModel.sla.class === 'tks-sla-breached' ? '<i class="fas fa-exclamation-triangle"></i>' : ''}
                ${viewModel.sla.label}
            </td>
        </tr>`;
    }

    function renderTicketTable(items) {
        if (!items || items.length === 0) {
            return '<div class="tks-list-empty">Sin tickets</div>';
        }

        const rows = items.map((ticket) => renderTicketRow(ticket)).join('');

        return `
        <div class="tks-table-wrapper">
            <table class="tks-table tks-list-table">
                <thead>
                    <tr>
                        <th class="tks-th-code">NRº de Ticket</th>
                        <th>Asunto</th>
                        <th>Cliente</th>
                        <th class="tks-th-cat">Categoria</th>
                        <th class="tks-th-status">Estado</th>
                        <th class="tks-th-sla">SLA</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    // --- DETALLE ---
    // --- DETAIL VIEW HELPERS ---
    function buildResueltoCountdownHtml(currentEstado, resueltoAutoCloseHours, resolvedAnchorTs) {
        if (currentEstado !== 'resuelto' || resueltoAutoCloseHours <= 0) return '';
        
        if (Number.isFinite(resolvedAnchorTs)) {
            const deadlineTs = resolvedAnchorTs + (resueltoAutoCloseHours * 60 * 60 * 1000);
            const pendingClose = deadlineTs <= Date.now();
            const countdownText = pendingClose
                ? 'Cierre automático pendiente (se aplicará pronto)'
                : `Cierre automático en ${formatCountdownRemaining(deadlineTs - Date.now())}`;
            return `<div id="tks-resuelto-countdown"
                class="tks-resuelto-countdown${pendingClose ? ' is-overdue' : ''}"
                data-deadline="${escapeHtml(new Date(deadlineTs).toISOString())}">
                ${escapeHtml(countdownText)}
            </div>`;
        }
        
        return `<div id="tks-resuelto-countdown" class="tks-resuelto-countdown">
            Cierre automático configurado: ${resueltoAutoCloseHours}h desde resolución.
        </div>`;
    }

    function buildFlowActionData(currentEstado, currentSubestado, waitingSubestadoSet, selectableFlowCandidates, showWaitingSubestados, waitingCandidates) {
        if (currentEstado === 'en_progreso' && !waitingSubestadoSet.has(currentSubestado)) {
            const filtered = selectableFlowCandidates.filter((sub) => sub !== 'en_progreso');
            if (filtered.length) selectableFlowCandidates = filtered;
        }
        const nonWaitingCandidates = selectableFlowCandidates.filter((sub) => !waitingSubestadoSet.has(sub));
        const flowPool = nonWaitingCandidates.length ? nonWaitingCandidates.filter(s => s !== 'asignado') : selectableFlowCandidates.filter(s => s !== 'asignado');
        
        const flowPriorityByCurrent = {
            recibido: ['asignado', 'en_progreso'],
            asignado: ['en_progreso'],
            pendiente_cliente: ['en_progreso', 'asignado'],
            pendiente_compra: ['en_progreso', 'asignado'],
            pendiente_tercero: ['en_progreso', 'asignado'],
            en_analisis: ['pendiente_aprobacion_1', 'asignado', 'en_progreso'],
            pendiente_aprobacion_1: ['pendiente_aprobacion_2'],
            pendiente_aprobacion_2: ['aprobado'],
            aprobado: ['en_ejecucion', 'en_progreso'],
            en_ejecucion: ['en_validacion'],
            en_validacion: ['resuelto', 'en_progreso', 'asignado'],
            en_progreso: ['resuelto'],
            resuelto: ['cerrado'],
            cerrado: ['en_progreso'],
            reabierto: ['en_progreso', 'asignado'],
        };
        const genericFlowPriority = [
            'asignado',
            'en_progreso',
            'pendiente_aprobacion_1',
            'pendiente_aprobacion_2',
            'aprobado',
            'en_ejecucion',
            'en_validacion',
            'resuelto',
            'reabierto',
        ];

        const preferredOrder = [
            ...(flowPriorityByCurrent[currentSubestado] || []),
            ...genericFlowPriority,
            ...flowPool,
        ].filter((value, idx, arr) => value && arr.indexOf(value) === idx);
        
        const nextFlowSubestado = preferredOrder.find((sub) => flowPool.includes(sub)) || '';
        const flowActionLabel = (currentEstado === 'cerrado' && (nextFlowSubestado === 'en_progreso' || nextFlowSubestado === 'reabierto'))
            ? 'Reabrir TK (pasar a En Progreso)'
            : (currentEstado === 'resuelto' && nextFlowSubestado === 'cerrado')
                ? 'Cerrar de inmediato (cliente aprobó)'
                : `Avanzar a ${subestadoLabel(nextFlowSubestado)}`;
        
        selectableFlowCandidates = selectableFlowCandidates.filter(s => s !== 'asignado');
        const waitingSubestadoActions = showWaitingSubestados
            ? waitingCandidates.filter((sub) => sub !== currentSubestado)
            : [];
            
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { nextFlowSubestado, flowActionLabel, selectableFlowCandidates, waitingSubestadoActions };
    }
    function buildFlowCandidates(currentEstado, workflow, waitingSubestadoSet, showWaitingSubestados) {
        const allowedNextSubestados = Array.isArray(workflow.allowed_next)
            ? workflow.allowed_next.map((v) => normalizeSubestadoKey(v)).filter(Boolean)
            : [];
            
        const flowCandidates = allowedNextSubestados.filter(Boolean);
        const waitingCandidates = flowCandidates.filter((sub) => waitingSubestadoSet.has(sub));
        let selectableFlowCandidates = showWaitingSubestados
            ? flowCandidates
            : flowCandidates.filter((sub) => !waitingSubestadoSet.has(sub));
            
        if (currentEstado === 'resuelto') {
            selectableFlowCandidates = selectableFlowCandidates.filter((sub) => sub === 'cerrado');
        } else if (currentEstado === 'cerrado') {
            selectableFlowCandidates = selectableFlowCandidates.filter((sub) => sub === 'en_progreso' || sub === 'reabierto');
        } else {
            selectableFlowCandidates = selectableFlowCandidates.filter((sub) => sub !== 'cerrado');
        }
    
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return { flowCandidates, waitingCandidates, selectableFlowCandidates };
    }

    function buildHeaderHtml(t) {
        return `
        <div class="tks-detail-header tks-detail-header-pro">
            <button class="tks-btn-icon-sm tks-detail-close" onclick="TksMain.closeDetail()" title="Volver a la lista">
                <i class="fas fa-times"></i>
            </button>
            <h2 class="tks-detail-title tks-detail-title-centered">${escapeHtml(t.titulo)}</h2>
        </div>`;
    }

    function renderTimelineEvents(unifiedFeed, resolveAttachment) {
        return unifiedFeed.map((item) => {
            if (item.kind === 'event') {
                const systemBadgeMap = {
                    'creación': 'Creación',
                    'creacion': 'Creación',
                    'cambio_estado': 'Cambio de estado',
                    'cambio de estado': 'Cambio de estado',
                    'transicion': 'Transición',
                    'transition': 'Transición',
                    'asignacion': 'Asignación',
                    'assignment': 'Asignación',
                    'reasignacion': 'Reasignación',
                    'reassignment': 'Reasignación',
                    'escalamiento': 'Escalamiento',
                    'auto_reply': 'Auto-respuesta',
                    'comment': 'Sistema',
                    'sistema': 'Sistema',
                };
                const rawEvento = String(item.evento || '').trim();
                const kindLabel = item.isSystem
                    ? (systemBadgeMap[rawEvento.toLowerCase()] || rawEvento || 'Sistema')
                    : 'Nota interna';
                const eventTypeClass = item.isSystem ? 'system' : 'note';

                const actorName = item.usuario === 'system' ? '' : formatAssigneeDisplay(item.usuario);

                let cleanDetail = String(item.detalle || '');
                if (item.isSystem && cleanDetail.includes('|')) {
                    cleanDetail = cleanDetail.split('|')[0].trim();
                }
                if (item.isSystem) {
                    cleanDetail = cleanDetail
                        .replace(/^Avanza a:\s*/i, '')
                        .replace(/^Fase:\s*/i, '')
                        .replace(/^Reasignado de.*?\s*a\s*/i, '');
                    cleanDetail = cleanDetail.trim();
                }

                const isShortDetail = cleanDetail.length > 0 && cleanDetail.length < 25;
                const detailMarkup = item.isSystem
                    ? (cleanDetail ? `<span class="tks-feed-sys-detail${isShortDetail ? ' short' : ''}">${escapeHtml(cleanDetail)}</span>` : '')
                    : `<span class="tks-feed-note-detail">${escapeHtml(cleanDetail)}</span>`;

                return `
                <article class="tks-feed-item ${eventTypeClass}">
                    <div class="tks-feed-head">
                        <div class="tks-feed-head-side tks-feed-actor">${escapeHtml(actorName)}</div>
                        <div class="tks-feed-head-center"><span class="tks-feed-badge">${escapeHtml(kindLabel)}</span></div>
                        <div class="tks-feed-head-side tks-feed-time right">${formatExactDateTime(feedTimestamp(item))}</div>
                    </div>
                    <div class="tks-feed-content">
                        ${detailMarkup}
                    </div>
                </article>`;
            } else {
                const incoming = item.direction === 'incoming';
                const tag = incoming ? 'Mensaje del cliente' : 'Respuesta técnica';
                const typeClass = incoming ? 'mail-in' : 'mail-out';
                const senderName = incoming ? formatIdentity(item.from_addr || '') : 'Sistema';
                const attachList = Array.isArray(item.attachments) ? item.attachments : [];
                const attachmentsHtml = attachList.length
                    ? attachList.map((a) => {
                        const info = resolveAttachment(a);
                        if (!info.isDownloadable) {
                            return `<div class="tks-inline-attach-pill"><i class="fas fa-image"></i> ${escapeHtml(info.name)}</div>`;
                        }
                        return `
                        <button class="tks-attachment-pill" type="button" onclick="TksMain.openAttachmentPreview(${info.id})">
                            <i class="fas fa-paperclip"></i> ${escapeHtml(info.name)}
                            <span class="tks-attachment-meta">${formatFileSize(info.size)}</span>
                        </button>`;
                    }).join('')
                    : '';
                return `
                <article class="tks-feed-item ${typeClass}">
                    <div class="tks-feed-head">
                        <div class="tks-feed-head-side tks-feed-actor">${escapeHtml(senderName)}</div>
                        <div class="tks-feed-head-center"><span class="tks-feed-badge">${tag}</span></div>
                        <div class="tks-feed-head-side tks-feed-time right">${formatExactDateTime(feedTimestamp(item))}</div>
                    </div>
                    <div class="tks-feed-content">
                        <h4 class="tks-feed-title">${escapeHtml(item.subject || '(sin asunto)')}</h4>
                        <div class="tks-feed-mail-meta">
                             <div class="tks-feed-mail-line"><strong>${incoming ? 'Para:' : 'Enviado a:'}</strong> ${identityListHtml(item.to_addr || '')}</div>
                            ${item.cc_addrs ? `<div class="tks-feed-mail-line"><strong>CC:</strong> ${identityListHtml(item.cc_addrs || '')}</div>` : ''}
                            ${item.bcc_addrs ? `<div class="tks-feed-mail-line"><strong>CCO:</strong> ${identityListHtml(item.bcc_addrs || '')}</div>` : ''}
                        </div>
                        <div class="tks-email-body">${item.body_html || '<span style="opacity:.7">(sin contenido)</span>'}</div>
                        ${attachmentsHtml ? `<div class="tks-email-attachments">${attachmentsHtml}</div>` : ''}
                    </div>
                </article>`;
            }
        }).join('');
    }

    function parseUnifiedFeed(eventos, emails) {
        const eventItems = (eventos || []).map((ev) => {
            const isManualSystem = String(ev?.is_system || "false") === "true";
            const eventType = String(ev?.event_type || "").trim();
            const phaseLabelStr = String(ev?.phase_label || "").trim();
            const detailStr = String(ev?.detail || "").trim();
            
            let resolvedLabel = "";
            if (eventType === "phase_change" && phaseLabelStr) {
                resolvedLabel = `Fase: ${phaseLabelStr}`;
            } else if (eventType === "transition" && detailStr) {
                const parts = detailStr.split("->").map(s => s.trim());
                if (parts.length === 2 && parts[1]) {
                    resolvedLabel = `Avanza a: ${parts[1].replace(/_/g, ' ')}`;
                } else {
                    resolvedLabel = detailStr;
                }
            }
            
        
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
                kind: 'event',
                created_at: ev.created_at || ev.creado_at || "",
                evento: resolvedLabel || String(ev?.event_type || "").trim(),
                detalle: ev.detalle || ev.detail || "",
                usuario: ev.usuario || ev.actor || "-",
                isSystem: String(ev.usuario || ev.actor || "").trim().toLowerCase() === "system" || isManualSystem || ["transition","approval","email","asignacion","cambio_estado"].includes(eventType),
            };
        });

        const emailItems = (emails || []).map((em) => ({
            kind: 'email',
            event_at: em.event_at || '',
            created_at: em.created_at || '',
            direction: em.direction === 'incoming' ? 'incoming' : 'outgoing',
            subject: em.subject || '',
            body_html: em.body_html || '',
            from_addr: em.from_addr || '',
            to_addr: em.to_addr || '',
            cc_addrs: em.cc_addrs || '',
            bcc_addrs: em.bcc_addrs || '',
            attachments: parseAttachmentsJson(em.attachments_json),
        }));

        const feedTimestamp = (item) => item.event_at || item.created_at;
        return [...eventItems, ...emailItems].sort((a, b) => toTs(feedTimestamp(a)) - toTs(feedTimestamp(b)));
    }

    function renderFeedEvent(item) {
        const systemBadgeMap = {
            'creación': 'Creación',
            'creacion': 'Creación',
            'cambio_estado': 'Cambio de estado',
            'cambio de estado': 'Cambio de estado',
            'transicion': 'Transición',
            'transition': 'Transición',
            'asignacion': 'Asignación',
            'assignment': 'Asignación',
            'reasignacion': 'Reasignación',
            'reassignment': 'Reasignación',
            'escalamiento': 'Escalamiento',
            'auto_reply': 'Auto-respuesta',
            'comment': 'Sistema',
            'sistema': 'Sistema',
        };
        const rawEvento = String(item.evento || '').trim();
        const kindLabel = item.isSystem ? (systemBadgeMap[rawEvento.toLowerCase()] || rawEvento || 'Sistema') : 'Nota interna';
        const eventTypeClass = item.isSystem ? 'system' : 'note';
        const actorName = item.usuario === 'system' ? '' : formatAssigneeDisplay(item.usuario);

        let cleanDetail = String(item.detalle || '');
        if (item.isSystem && cleanDetail.includes('|')) cleanDetail = cleanDetail.split('|')[0].trim();
        if (item.isSystem) cleanDetail = cleanDetail.replace(/_/g, ' ');

        const feedTimestamp = (item) => item.event_at || item.created_at;

        return `<article class="tks-feed-item tks-feed-item-event ${eventTypeClass}">
            <div class="tks-feed-item-head compact">
                <div class="tks-feed-head-side tks-feed-actor">${item.isSystem ? '' : escapeHtml(actorName)}</div>
                <div class="tks-feed-head-center"><span class="tks-feed-badge">${kindLabel}</span></div>
                <div class="tks-feed-head-side tks-feed-time right">${formatExactDateTime(feedTimestamp(item))}</div>
            </div>
            <div class="tks-feed-content ${item.isSystem ? 'system-movement' : ''}">
                ${item.isSystem
                ? `<div class="tks-feed-system-line" style="text-align:center">${escapeHtml(cleanDetail)}</div>`
                : `<h4 class="tks-feed-title">${escapeHtml(item.evento)}</h4>
                       <div class="tks-feed-detail">${escapeHtml(item.detalle)}</div>`
            }
            </div>
        </article>`;
    }

    function renderFeedEmail(item, ticketId, resolveAttachment, ticketAttachmentById) {
        const incoming = item.direction === 'incoming';
        const tag = incoming ? 'Correo entrante' : 'Correo saliente';
        const attachmentsHtml = (item.attachments || []).filter((att) => {
            const attachmentId = resolveAttachment(att);
            return !shouldHideInlineAttachmentFromList(ticketId, item.body_html, att, attachmentId);
        }).map((att) => {
            const attachmentId = resolveAttachment(att);
            const attachmentMeta = attachmentId ? (ticketAttachmentById.get(Number(attachmentId)) || att) : att;
            return renderAttachmentCard(ticketId, attachmentId, attachmentMeta, { compact: true });
        }).join('');

        const rawSender = incoming ? (parseEmailIdentity(item.from_addr).name || item.from_addr) : (parseEmailIdentity(item.from_addr || 'Soporte').name || 'Soporte');
        const senderName = formatAssigneeDisplay(decodeMimeEncodedString(rawSender));
        const feedTimestamp = (item) => item.event_at || item.created_at;

        return `<article class="tks-feed-item tks-feed-item-email ${incoming ? 'incoming' : 'outgoing'}">
            <div class="tks-feed-item-head compact">
                <div class="tks-feed-head-side tks-feed-actor">${escapeHtml(senderName)}</div>
                <div class="tks-feed-head-center"><span class="tks-feed-badge">${tag}</span></div>
                <div class="tks-feed-head-side tks-feed-time right">${formatExactDateTime(feedTimestamp(item))}</div>
            </div>
            <div class="tks-feed-content">
                <h4 class="tks-feed-title">${escapeHtml(item.subject || '(sin asunto)')}</h4>
                <div class="tks-feed-mail-meta">
                     <div class="tks-feed-mail-line"><strong>${incoming ? 'Para:' : 'Enviado a:'}</strong> ${identityListHtml(item.to_addr || '')}</div>
                    ${item.cc_addrs ? `<div class="tks-feed-mail-line"><strong>CC:</strong> ${identityListHtml(item.cc_addrs || '')}</div>` : ''}
                    ${item.bcc_addrs ? `<div class="tks-feed-mail-line"><strong>CCO:</strong> ${identityListHtml(item.bcc_addrs || '')}</div>` : ''}
                </div>
                <div class="tks-email-body">${item.body_html || '<span style="opacity:.7">(sin contenido)</span>'}</div>
                ${attachmentsHtml ? `<div class="tks-email-attachments">${attachmentsHtml}</div>` : ''}
            </div>
        </article>`;
    }

    function buildFeedHtml(unifiedFeed, t, canAddInternalNote, resolveAttachment, ticketAttachmentById) {
        let feedHtml = '';
        if (unifiedFeed.length) {
            feedHtml = unifiedFeed.map(item => {
                if (item.kind === 'event') return renderFeedEvent(item);
                return renderFeedEmail(item, t.id, resolveAttachment, ticketAttachmentById);
            }).join('');
        }
        if (canAddInternalNote) {
            feedHtml += `
                <div class="tks-feed-note-inline">
                    <input type="text" id="tks-detail-inline-note" class="tks-input tks-input-sm" placeholder="Añadir nota interna rápida (Enter para guardar)..." onkeydown="if(event.key==='Enter') TksMain.addNote(${t.id})">
                    <button class="tks-btn-icon-sm" onclick="TksMain.addNote(${t.id})" title="Guardar nota"><i class="fas fa-paper-plane"></i></button>
                </div>`;
        }
        return feedHtml;
    }

    function buildComposerHtml(t, composerMode, canAddInternalNote, canOpenReplyAction, canReplyComposer, draftBlockedReason, notePaneHtml, draft, draftCcValue, draftBccValue, canEditDraftNow) {
        return `
        <div class="tks-composer-card">
            <div class="tks-section-title"><i class="fas fa-comment-dots"></i> Comunicación</div>
            <div class="tks-composer-mode-switch">
                ${canAddInternalNote
            ? `<button class="tks-composer-mode-btn ${composerMode === 'note' ? 'active' : ''}" data-composer-mode="note" onclick="TksMain.switchComposerMode('note')">
                        <i class="fas fa-sticky-note"></i> Nota interna
                    </button>`
            : ''}
                ${canOpenReplyAction
            ? (canReplyComposer
            ? `<button class="tks-composer-mode-btn ${composerMode === 'reply' ? 'active' : ''}" data-composer-mode="reply" onclick="TksMain.switchComposerMode('reply')">
                            <i class="fas fa-reply"></i> Responder cliente
                        </button>`
            : `<button class="tks-composer-mode-btn" type="button" disabled title="${escapeHtml(draftBlockedReason || 'Disponible mientras el ticket esté activo')}">
                            <i class="fas fa-reply"></i> Responder cliente
                        </button>`)
            : ''}
            </div>

            <div data-composer-pane="note" style="${composerMode === 'note' ? '' : 'display:none'}">
                ${notePaneHtml}
            </div>

            ${canReplyComposer
            ? `<div data-composer-pane="reply" style="${composerMode === 'reply' ? '' : 'display:none'}">
                        <div class="tks-email-reply-card">
                            <div class="tks-email-reply-head">
                                <strong>Correo al cliente (envío directo)</strong>
                            </div>
                            <div class="tks-form-group">
                                <label>Para</label>
                                <input class="tks-input" id="tks-draft-to" value="${escapeHtml(draft?.to_addr || t.origen_email || '')}" ${canEditDraftNow ? '' : 'readonly'}>
                            </div>
                            <div class="tks-form-row tks-draft-copy-row">
                                <div class="tks-form-group">
                                    <label>CC</label>
                                    <input class="tks-input" id="tks-draft-cc" placeholder="correo1@empresa.cl, correo2@empresa.cl" value="${escapeHtml(draftCcValue)}" ${canEditDraftNow ? '' : 'readonly'}>
                                </div>
                                <div class="tks-form-group">
                                    <label>CCO</label>
                                    <input class="tks-input" id="tks-draft-bcc" placeholder="correo1@empresa.cl, correo2@empresa.cl" value="${escapeHtml(draftBccValue)}" ${canEditDraftNow ? '' : 'readonly'}>
                                </div>
                            </div>
                            <div class="tks-form-group">
                                <label>Asunto</label>
                                <input class="tks-input" id="tks-draft-subject" value="${escapeHtml(draft?.subject || '')}" readonly>
                            </div>
                            <div class="tks-form-group">
                                <label>Descripción</label>
                                <textarea class="tks-textarea tks-email-reply-input" id="tks-draft-body" rows="7" ${canEditDraftNow ? '' : 'readonly'}>${escapeHtml(draft?.body_text || '')}</textarea>
                                ${canEditDraftNow ? '<div class="tks-reply-paste-hint">Puedes pegar capturas directamente en este campo y se adjuntarán al correo.</div>' : ''}
                            </div>
                            <div class="tks-form-group">
                                <label>Adjuntos</label>
                                <input type="file" id="tks-draft-files" multiple class="tks-file-input" ${canEditDraftNow ? '' : 'disabled'}>
                                <div class="tks-draft-attachments" id="tks-draft-file-list">
                                    <div style="color:var(--tks-text-muted);font-size:0.8rem;">Sin adjuntos seleccionados</div>
                                </div>
                            </div>
                            <div class="tks-email-reply-actions">
                                <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.replyByEmail(${t.id})" ${canEditDraftNow ? '' : 'disabled'}>
                                    <i class="fas fa-paper-plane"></i> Revisar y enviar
                                </button>
                            </div>
                        </div>
                    </div>`
            : ''}
        </div>`;
    }

    function renderDetail(t, eventos = [], emails = [], ticketAttachments = [], permissions = {}) {
        if (!t) return '<div class="tks-detail-empty"><span>Selecciona un ticket</span></div>';

        const sla = slaStatus(t.vence_at);
        const canChangeStatus = permissions.canChangeStatus !== false;
        const canClaim = permissions.canClaim === true;
        const canAssignTicket = permissions.canAssignTicket === true;
        const canTrash = permissions.canTrash === true;
        const canRestore = permissions.canRestore === true;

        // Restore missing definitions
        const canParticipate = permissions.canParticipate === true;
        const blockedReason = String(permissions.blockedReason || '').trim();
        const roleKey = String(permissions.currentRole || '').trim().toLowerCase();

        const isGerenciaViewer = roleKey === 'gerencia';
        const status = String(t.estado || '').toLowerCase();
        const displayStatus = ticketDisplayStatusKey(t);
        const isTrashed = displayStatus === 'papelera';
        const isClosed = status === 'cerrado' || isTrashed;
        const isResolved = status === 'resuelto';

        // Regla: Si está CERRADO, nadie puede agregar notas ni responder.
        // Regla: Si está RESUELTO, no se puede responder correos (solo notas).
        const canAddInternalNote = permissions.canAddInternalNote === true && !isClosed;

        const canOpenReplyAction = canParticipate && !isGerenciaViewer;
        const canReplyComposer = permissions.canReplyToClient === true;
        const requestedComposerMode = String(permissions.composerMode || permissions.activeTab || 'note') === 'reply' ? 'reply' : 'note';
        const composerMode = canReplyComposer && requestedComposerMode === 'reply' ? 'reply' : 'note';
        const draft = permissions.draft || null;
        const draftMeta = permissions.draftMeta || {};
        const draftBlockedReason = String(draftMeta.blockedReason || blockedReason || '').trim();
        const canEditDraftNow = canReplyComposer && draftMeta.canEdit === true;
        const resolveAttachment = buildEmailAttachmentResolver(t.id, ticketAttachments);
        const ticketAttachmentById = new Map((ticketAttachments || []).map((att) => [Number(att?.id || 0), att]));

        const clientNameRaw = decodeMimeEncodedString(t.cliente_nombre || '').trim();
        const clientName = clientNameRaw || 'Desconocido';
        const customerId = String(t.customer_id || '').trim();
        const originEmail = String(t.origen_email || '').trim();
        const notifyEmailsCsv = String(t.notify_emails || '').trim();
        const notifyEmailsList = Array.isArray(t.notify_emails_list)
            ? t.notify_emails_list
            : notifyEmailsCsv.split(/[,\n;]+/).map((v) => String(v || '').trim()).filter(Boolean);
        const isUnknownClient = clientName.toLowerCase() === 'desconocido';
        const canAssociateClient = isUnknownClient && !!originEmail;
        const originEmailForJs = escapeJsSingleQuoted(originEmail);
        const workflow = permissions.workflow || {};
        const resueltoAutoCloseHours = Number(workflow?.resuelto_auto_close_hours || 0);
        const currentEstado = String(t.estado || '').trim().toLowerCase();
        const currentSubestado = normalizeSubestadoKey(t.subestado || workflow?.ticket?.subestado || 'recibido');
        const resolvedAnchorIso = String(t.resolved_at || t.updated_at || '').trim();
        const resolvedAnchorTs = Date.parse(resolvedAnchorIso);
        
        const resueltoCountdownHtml = buildResueltoCountdownHtml(currentEstado, resueltoAutoCloseHours, resolvedAnchorTs);

        const waitingSubestadoSet = new Set(WAITING_SUBESTADOS);
        const showWaitingSubestados = currentEstado === 'en_progreso';
        const { flowCandidates: _fc, waitingCandidates, selectableFlowCandidates: _initSelectable } = buildFlowCandidates(
            currentEstado, 
            workflow, 
            waitingSubestadoSet, 
            showWaitingSubestados
        );
        let selectableFlowCandidates = _initSelectable;

        const { nextFlowSubestado, flowActionLabel, selectableFlowCandidates: finalSelectableFlowCandidates, waitingSubestadoActions } = buildFlowActionData(
            currentEstado, currentSubestado, waitingSubestadoSet, selectableFlowCandidates, showWaitingSubestados, waitingCandidates
        );
        selectableFlowCandidates = finalSelectableFlowCandidates;

        let managementActions = '';
        if (canClaim) {
            managementActions += `<button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.takeTicket(${t.id})"><i class="fas fa-hand-paper"></i> Tomar ticket</button>`;
        }
        if (canTrash) {
            managementActions += `<button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.trashTicket(${t.id})"><i class="fas fa-trash-alt"></i> Enviar a papelera</button>`;
        }
        if (canRestore) {
            managementActions += `<button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.restoreTicket(${t.id})"><i class="fas fa-trash-restore"></i> Restaurar</button>`;
        }

        const filteredEvents = (eventos || []).filter((ev) => {
                const rawEvent = String(ev?.evento || ev?.event_type || '').trim().toLowerCase().replace(/\s+/g, '_');
            const rawDetail = String(ev?.detalle || ev?.detail || '').trim().toLowerCase();
            if (rawEvent.startsWith('correo')) return false;
            if (rawEvent === 'transicion') return false;
            if (rawEvent.includes('adjunto_incoming')) return false;
            if (rawDetail.startsWith('respuesta enviada a ')) return false;
            if (rawDetail.startsWith('se guardaron') && rawDetail.includes('adjunto')) return false;
            return true;
        });

        const eventItems = filteredEvents.map((ev) => {
            const eventType = String(ev?.event_type || "").trim().toLowerCase();
            const rawEv = String(ev?.evento || "").trim().toLowerCase();
            const isManualSystem = ["transicion", "asignacion", "cambio_estado", "reasignacion", "escalamiento"].includes(rawEv);

            const fallbackLabelByType = {
                transition: "Cambio de estado",
                status_change: "Cambio de estado",
                assignment: "Asignación",
                asignacion: "Asignación",
                reassignment: "Reasignación",
                reasignacion: "Reasignación",
                escalation: "Escalamiento",
                email: "Correo",
                attachment: "Adjunto",
            };

            const resolvedLabel = String(ev?.evento || ev?.event_label || "").trim() || (fallbackLabelByType[eventType] || "");

        
    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
                kind: "event",
                event_at: ev.event_at || "",
                created_at: ev.created_at || ev.creado_at || "",
                evento: resolvedLabel || String(ev?.event_type || "").trim(),
                detalle: ev.detalle || ev.detail || "",
                usuario: ev.usuario || ev.actor || "-",
                isSystem: String(ev.usuario || ev.actor || "").trim().toLowerCase() === "system" || isManualSystem || ["transition","approval","email","asignacion","cambio_estado"].includes(eventType),
            };
        });

        const emailItems = (emails || []).map((em) => ({
            kind: 'email',
            event_at: em.event_at || '',
            created_at: em.created_at || '',
            direction: em.direction === 'incoming' ? 'incoming' : 'outgoing',
            subject: em.subject || '',
            body_html: em.body_html || '',
            from_addr: em.from_addr || '',
            to_addr: em.to_addr || '',
            cc_addrs: em.cc_addrs || '',
            bcc_addrs: em.bcc_addrs || '',
            attachments: parseAttachmentsJson(em.attachments_json),
        }));

        const feedTimestamp = (item) => item.event_at || item.created_at;
        const unifiedFeed = [...eventItems, ...emailItems].sort((a, b) => toTs(feedTimestamp(a)) - toTs(feedTimestamp(b)));

        const feedHtml = unifiedFeed.map((item) => {
            if (item.kind === 'event') {
                const systemBadgeMap = {
                    'creación': 'Creación',
                    'creacion': 'Creación',
                    'cambio_estado': 'Cambio de estado',
                    'cambio de estado': 'Cambio de estado',
                    'transicion': 'Transición',
                    'transition': 'Transición',
                    'asignacion': 'Asignación',
                    'assignment': 'Asignación',
                    'reasignacion': 'Reasignación',
                    'reassignment': 'Reasignación',
                    'escalamiento': 'Escalamiento',
                    'auto_reply': 'Auto-respuesta',
                    'comment': 'Sistema',
                    'sistema': 'Sistema',
                };
                const rawEvento = String(item.evento || '').trim();
                const kindLabel = item.isSystem
                    ? (systemBadgeMap[rawEvento.toLowerCase()] || rawEvento || 'Sistema')
                    : 'Nota interna';
                const eventTypeClass = item.isSystem ? 'system' : 'note';

                const actorName = item.usuario === 'system' ? '' : formatAssigneeDisplay(item.usuario);

                // Para eventos de sistema: limpiar el detalle (sin prefijos, sin lo que va después de "|")
                let cleanDetail = String(item.detalle || '');
                if (item.isSystem && cleanDetail.includes('|')) {
                    cleanDetail = cleanDetail.split('|')[0].trim();
                }
                if (item.isSystem) {
                    cleanDetail = cleanDetail.replace(/_/g, ' ');
                }

                return `<article class="tks-feed-item tks-feed-item-event ${eventTypeClass}">
                    <div class="tks-feed-item-head compact">
                        <div class="tks-feed-head-side tks-feed-actor">${item.isSystem ? '' : escapeHtml(actorName)}</div>
                        <div class="tks-feed-head-center"><span class="tks-feed-badge">${kindLabel}</span></div>
                        <div class="tks-feed-head-side tks-feed-time right">${formatExactDateTime(feedTimestamp(item))}</div>
                    </div>
                    <div class="tks-feed-content ${item.isSystem ? 'system-movement' : ''}">
                        ${item.isSystem
                        ? `<div class="tks-feed-system-line" style="text-align:center">${escapeHtml(cleanDetail)}</div>`
                        : `<h4 class="tks-feed-title">${escapeHtml(item.evento)}</h4>
                               <div class="tks-feed-detail">${escapeHtml(item.detalle)}</div>`
                    }
                    </div>
                </article>`;
            }

            const incoming = item.direction === 'incoming';
            const tag = incoming ? 'Correo entrante' : 'Correo saliente';
            const attachmentsHtml = (item.attachments || []).filter((att) => {
                const attachmentId = resolveAttachment(att);
                return !shouldHideInlineAttachmentFromList(t.id, item.body_html, att, attachmentId);
            }).map((att) => {
                const attachmentId = resolveAttachment(att);
                const attachmentMeta = attachmentId ? (ticketAttachmentById.get(Number(attachmentId)) || att) : att;
                return renderAttachmentCard(t.id, attachmentId, attachmentMeta, { compact: true });
            }).join('');

            const rawSender = incoming ? (parseEmailIdentity(item.from_addr).name || item.from_addr) : (parseEmailIdentity(item.from_addr || 'Soporte').name || 'Soporte');
            const senderName = formatAssigneeDisplay(decodeMimeEncodedString(rawSender));

            return `<article class="tks-feed-item tks-feed-item-email ${incoming ? 'incoming' : 'outgoing'}">
                <div class="tks-feed-item-head compact">
                    <div class="tks-feed-head-side tks-feed-actor">${escapeHtml(senderName)}</div>
                    <div class="tks-feed-head-center"><span class="tks-feed-badge">${tag}</span></div>
                    <div class="tks-feed-head-side tks-feed-time right">${formatExactDateTime(feedTimestamp(item))}</div>
                </div>
                <div class="tks-feed-content">
                    <h4 class="tks-feed-title">${escapeHtml(item.subject || '(sin asunto)')}</h4>
                    <div class="tks-feed-mail-meta">
                         <div class="tks-feed-mail-line"><strong>${incoming ? 'Para:' : 'Enviado a:'}</strong> ${identityListHtml(item.to_addr || '')}</div>
                        ${item.cc_addrs ? `<div class="tks-feed-mail-line"><strong>CC:</strong> ${identityListHtml(item.cc_addrs || '')}</div>` : ''}
                        ${item.bcc_addrs ? `<div class="tks-feed-mail-line"><strong>CCO:</strong> ${identityListHtml(item.bcc_addrs || '')}</div>` : ''}
                    </div>
                    <div class="tks-email-body">${item.body_html || '<span style="opacity:.7">(sin contenido)</span>'}</div>
                    ${attachmentsHtml ? `<div class="tks-email-attachments">${attachmentsHtml}</div>` : ''}
                </div>
            </article>`;
        }).join('');

        // Botones de Decisión de Gerencia (Aprobar/Rechazar). Se definen ACÁ ARRIBA para que
        // estén disponibles tanto en la vista reducida de gerencia (return temprano de abajo)
        // como en el flujo normal (admin). Antes vivían más abajo y eran inalcanzables para
        // el rol gerencia por el return temprano → Diego nunca veía cómo aprobar/rechazar.
        const gerenciaApprovalHtml = (!isTrashed && t.subestado === 'pendiente_gerencia' && (isGerenciaViewer || roleKey === 'admin'))
            ? `
                <div class="tks-status-editor tks-status-editor-v2" style="border:1px solid var(--tks-accent);border-radius:10px;padding:0.75rem;margin-top:0.5rem">
                    <label class="tks-status-editor-label"><i class="fas fa-user-tie"></i> Decisión de Gerencia</label>
                    <textarea id="tks-gerencia-note" rows="2" placeholder="Nota (opcional)..." style="width:100%;margin:0.4rem 0;background:var(--tks-bg-secondary);border:1px solid var(--tks-border);border-radius:8px;color:var(--tks-text);padding:0.5rem;font-family:inherit"></textarea>
                    <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
                        <button class="tks-btn tks-btn-primary" onclick="window.tksGerenciaDecision(${t.id}, 'aprobado')"><i class="fas fa-check"></i> Aprobar</button>
                        <button class="tks-btn tks-btn-ghost" style="color:var(--tks-danger)" onclick="window.tksGerenciaDecision(${t.id}, 'rechazado')"><i class="fas fa-times"></i> Rechazar</button>
                    </div>
                    <div class="tks-status-editor-hint">Solo gerencia/admin puede decidir. Aprobar o rechazar devuelve el ticket a En progreso y registra la nota.</div>
                </div>
              `
            : '';

        if (isGerenciaViewer) {
            return `
            <div class="tks-detail-header tks-detail-header-pro">
                <button class="tks-btn-icon-sm tks-detail-close" onclick="TksMain.closeDetail()" title="Volver a la lista">
                    <i class="fas fa-times"></i>
                </button>
                <h2 class="tks-detail-title tks-detail-title-centered">${escapeHtml(t.titulo)}</h2>
            </div>

            <div class="tks-detail-layout">
                <section class="tks-detail-main-col">
                    <div class="tks-feed-card">
                        <div class="tks-section-title"><i class="fas fa-stream"></i> Línea de tiempo</div>
                        <div id="tks-unified-feed" class="tks-unified-feed">
                            ${feedHtml || '<div class="tks-feed-empty">Sin actividad registrada.</div>'}
                        </div>
                    </div>
                    ${gerenciaApprovalHtml}
                </section>
            </div>`;
        }

        const sidebarAttachments = (ticketAttachments || []).map((att) =>
            renderAttachmentCard(t.id, Number(att?.id || 0), att, { compact: true })
        ).join('');

        const notePaneHtml = canAddInternalNote
            ? `<div class="tks-note-composer">
                <input type="text" id="tks-note-input" placeholder="Agregar nota interna..." onkeydown="if(event.key==='Enter')TksMain.addNote(${t.id})">
                <button class="tks-btn tks-btn-primary" onclick="TksMain.addNote(${t.id})"><i class="fas fa-paper-plane"></i> Guardar nota</button>
            </div>`
            : `<div class="tks-readonly-box">${escapeHtml(blockedReason || 'Solo lectura para notas internas.')}</div>`;

        const draftCcValue = draft ? String(draft?.cc_addrs || '') : notifyEmailsList.join(', ');
        const draftBccValue = String(draft?.bcc_addrs || '');

        const trashInfoHtml = isTrashed
            ? `<div class="tks-trash-info">
                <strong>En papelera</strong>
                <span>${escapeHtml(String(t.trash_reason || '').trim() || 'Sin motivo informado')}</span>
                <small>${escapeHtml(t.trashed_by ? `Movido por ${t.trashed_by}` : 'Sin actor registrado')}${t.trashed_at ? ` · ${formatExactDateTime(t.trashed_at)}` : ''}</small>
            </div>`
            : '';

        const statusManagementHtml = !isTrashed && canChangeStatus
            ? `
                <div class="tks-status-editor tks-status-editor-v2">
                    <div class="tks-flow-advance-wrap">
                        <label class="tks-status-editor-label">Flujo principal</label>
                        ${nextFlowSubestado
                ? `<button class="tks-status-quick-btn tks-flow-advance-btn"
                                   onclick="TksMain.transitionSubestado(${t.id}, '${escapeJsSingleQuoted(nextFlowSubestado)}')">
                                <i class="fas fa-forward"></i> ${flowActionLabel}
                           </button>`
                : '<div class="tks-feed-empty">No hay un siguiente paso directo disponible.</div>'}
                        
                        <div class="tks-status-editor-hint" style="display:none;"></div>
                    </div>
                    ${showWaitingSubestados ? `
                        <div class="tks-subestado-wait-wrap">
                            <label class="tks-status-editor-label">Subestados de espera</label>
                            <div class="tks-subestado-wait-grid">
                                ${waitingSubestadoActions.length
                    ? waitingSubestadoActions.map((sub) => {
                        const safeJs = escapeJsSingleQuoted(sub);
                        return `<button class="tks-status-quick-btn tks-subestado-wait-btn"
                                            onclick="TksMain.transitionSubestado(${t.id}, '${safeJs}')">
                                            <i class="fas fa-hourglass-half"></i> Marcar ${subestadoLabel(sub)}
                                        </button>`;
                    }).join('')
                    : '<div class="tks-feed-empty">Sin subestados de espera disponibles.</div>'}
                            </div>
                        </div>
                    ` : ''}
                </div>
              `
            : `<div class="tks-readonly-box">${escapeHtml(isTrashed ? 'El ticket está en papelera. Restáuralo para retomar flujo, asignación o correo.' : (blockedReason || 'Solo lectura para gestión de estado.'))}</div>`;

        const assigneeFallbackLabel = formatAssigneeDisplay(t.asignado_a || '');
        const assigneeControlHtml = canAssignTicket
            ? `
                <div class="tks-assignee-control in-customer">
                    <label class="tks-status-editor-label">Persona asignada</label>
                    <select class="tks-select" id="tks-assignee-select" onchange="TksMain.applyAssigneeChange(${t.id})">
                        <option value="${escapeHtml(String(t.asignado_a || '').trim().toLowerCase())}">${escapeHtml(assigneeFallbackLabel)}</option>
                    </select>
                    <div class="tks-status-editor-hint">Selecciona una persona y se reasigna de inmediato.</div>
                </div>
            `
            : `
                <div class="tks-assignee-control readonly in-customer">
                    <label class="tks-status-editor-label">Persona asignada</label>
                    <div class="tks-assignee-readonly" id="tks-assignee-readonly-label">${escapeHtml(assigneeFallbackLabel)}</div>
                </div>
            `;

        const topCardsHtml = `
            <div class="tks-detail-top-cards">
                <div class="tks-side-card tks-top-card">
                    <h4><i class="fas fa-tasks"></i> Estado y gestión</h4>
                    <div class="tks-status-summary tks-status-summary-listy">
                        <span class="tks-status-summary-label">Estado actual</span>
                        <span class="tks-status-display tks-status-tone-${escapeHtml(displayStatus)}">${statusLabel(displayStatus)}</span>
                        ${resueltoCountdownHtml}
                    </div>
                    ${trashInfoHtml}
                    ${statusManagementHtml}
                    ${managementActions ? `
                        <div class="tks-status-actions-wrap">
                            <div class="tks-status-actions-title">Acciones</div>
                            <div class="tks-side-actions">${managementActions}</div>
                        </div>
                    ` : ''}
                </div>

                <div class="tks-side-card tks-top-card">
                    <h4><i class="fas fa-paperclip"></i> Adjuntos del ticket</h4>
                    <div class="tks-side-attachments">
                        ${sidebarAttachments || '<div class="tks-feed-empty">Sin adjuntos</div>'}
                    </div>
                </div>

                <div class="tks-side-card tks-top-card">
                    <h4><i class="fas fa-user"></i> Cliente</h4>
                    <div class="tks-customer-mini">
                        <div><span>Nombre</span><strong>${escapeHtml(clientName)}</strong></div>
                        <div><span>Email</span><strong>${escapeHtml(originEmail || '-')}</strong></div>
                        <div><span>ID Cliente</span><strong>${escapeHtml(customerId || 'Sin asociar')}</strong></div>
                    </div>
                    <div class="tks-customer-link" style="margin-top: 0.5rem;">
                        <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.openAssociateClientModal('${originEmailForJs}')">
                            <i class="fas fa-link"></i> ${customerId ? 'Cambiar Cliente' : 'Vincular Cliente'}
                        </button>
                    </div>
                    ${assigneeControlHtml}
                </div>
            </div>`;

        const composerHtml = buildComposerHtml(t, composerMode, canAddInternalNote, canOpenReplyAction, canReplyComposer, draftBlockedReason, notePaneHtml, draft, draftCcValue, draftBccValue, canEditDraftNow);

        return `
        ${buildHeaderHtml(t)}

        <div class="tks-detail-layout">
            <section class="tks-detail-main-col">
                ${topCardsHtml}

                <div class="tks-feed-card">
                    <div class="tks-section-title"><i class="fas fa-stream"></i> Línea de tiempo</div>
                    <div id="tks-unified-feed" class="tks-unified-feed">
                        ${feedHtml || '<div class="tks-feed-empty">Sin actividad registrada.</div>'}
                    </div>
                </div>

                ${composerHtml}

                ${gerenciaApprovalHtml}
            </section>
        </div>`;
    }

    function renderCustomer360(data) {
        if (!data) return '<p>No se encontró información del cliente.</p>';

        const debtClass = data.status === 'DEBT' ? 'tks-sla-breached' : 'tks-sla-ok';
        const debtLabel = data.status === 'DEBT' ? 'Con Deuda' : 'Al Día';
        const customerIdJs = escapeJsSingleQuoted(data.customer_id);

        return `
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:1.5rem">
            <!-- Info General -->
            <div class="card" style="padding:1rem">
                <h4 style="margin-top:0"><i class="fas fa-id-card"></i> ${escapeHtml(data.customer_name)}</h4>
                <div style="font-size:0.9rem; line-height:1.6">
                    <div><strong>ID:</strong> ${escapeHtml(data.customer_id)}</div>
                    <div><strong>Estado Pago:</strong> <span class="${debtClass}" style="padding:2px 6px; border-radius:4px; font-size:0.8em">${debtLabel}</span></div>
                    <div><strong>Deuda Total:</strong> $${new Intl.NumberFormat('es-CL').format(data.total_debt)}</div>
                </div>
                ${data.total_debt > 0 ? `
                <div style="margin-top:1rem">
                    <button class="tks-btn tks-btn-warning tks-btn-sm" onclick="TksMain.generatePaymentLink('${customerIdJs}', ${data.total_debt}, this)">
                        <i class="fas fa-link"></i> Generar Link de Pago
                    </button>
                </div>
                ` : ''}
            </div>

            <!-- Acciones / Historial (Placeholder) -->
            <div class="card" style="padding:1rem; opacity:0.7">
                <h4 style="margin-top:0"><i class="fas fa-history"></i> Historial Reciente</h4>
                <p style="font-size:0.85rem">Próximamente: Lista de últimos 5 tickets y facturas.</p>
            </div>
        </div>
        <div id="payment-link-result" style="margin-top:1rem; display:none"></div>
        `;
    }

    // --- KANBAN ---
    function buildKanbanColumns(kanban) {
        return [
            { key: 'abierto', label: 'Abierto', color: 'var(--tks-abierto)', items: kanban['abierto'] || [] },
            { key: 'en_progreso', label: 'En Progreso', color: 'var(--tks-en_progreso)', items: kanban['en_progreso'] || [] },
            { key: 'resuelto', label: 'Resuelto', color: 'var(--tks-resuelto)', items: kanban['resuelto'] || [] },
            { key: 'cerrado', label: 'Cerrado', color: 'var(--tks-cerrado)', items: kanban['cerrado'] || [] },
        ];
    }

    function renderKanbanCard(t, colKey, canDrag) {
        const dragAttr = canDrag ? 'draggable="true"' : 'draggable="false"';
        const dragEvent = canDrag ? `ondragstart="TksMain.onDragStart(event, ${t.id}, '${escapeJsSingleQuoted(colKey)}')"` : '';
        const badgeClass = `tks-cat-${escapeHtml(t.categoria || 'general')}`;
        const badgeLabel = catLabel(t.categoria);
        const assignee = escapeHtml(t.asignado_a ? formatAssigneeDisplay(t.asignado_a) : '-');

        return `
            <div class="tks-kanban-card" data-id="${t.id}" data-prio="${t.prioridad || 3}"
                 ${dragAttr} ${dragEvent}
                 onclick="TksMain.openDetail(${t.id})">
                <div class="tks-kanban-card-title">${escapeHtml(t.titulo)}</div>
                <div class="tks-kanban-card-meta">
                    <span class="tks-cat-badge ${badgeClass}">${badgeLabel}</span>
                    <span>${assignee}</span>
                </div>
            </div>
        `;
    }

    function renderKanbanColumn(col, canDrag) {
        return `
            <div class="tks-kanban-col">
                <div class="tks-kanban-col-header">
                    <span class="tks-kanban-col-title"><span class="dot" style="background:${col.color}"></span>${col.label}</span>
                    <span class="tks-kanban-col-count">${col.items.length}</span>
                </div>
                <div class="tks-kanban-col-body" data-status="${col.key}">
                    ${col.items.map(t => renderKanbanCard(t, col.key, canDrag)).join('')}
                </div>
            </div>
        `;
    }

    function renderKanbanTrashZone() {
        return `
            <div class="tks-kanban-trash-zone" data-drop-target="trash">
                <div class="tks-kanban-trash-icon"><i class="fas fa-trash-alt"></i></div>
                <div class="tks-kanban-trash-copy">
                    <strong>Papelera</strong>
                    <span>Arrastra aquí tickets basura o repetidos para sacarlos de operación.</span>
                </div>
            </div>
        `;
    }

    function renderKanban(kanban, options = {}) {
        const canDrag = options.canDrag === true;
        const canTrash = options.canTrash === true;
        const columns = buildKanbanColumns(kanban);

        const boardHtml = `<div class="tks-kanban-board">${columns.map(col => renderKanbanColumn(col, canDrag)).join('')}</div>`;
        const trashHtml = canTrash ? renderKanbanTrashZone() : '';

        return `<div class="tks-kanban-wrap">${boardHtml}${trashHtml}</div>`;
    }

    // --- OPS VIEW ---
    function renderOpsQueueHealth(queue) {
        const queueRows = Object.entries(queue.by_job_type || {}).map(([job, metrics]) => `
            <tr>
                <td>${escapeHtml(jobTypeLabel(job))}</td>
                <td class="td-num">${Number(metrics.due_now || 0)}</td>
                <td class="td-num">${Number(metrics.stale_running || 0)}</td>
                <td class="td-num">${Number(metrics.created_last_hour || 0)}</td>
            </tr>
        `).join('');

        return `
            <div class="tks-pivot-container">
                <h4>Salud de Cola</h4>
                <table class="tks-pivot-table">
                    <thead><tr><th>Tipo de trabajo</th><th class="td-num">Vencidos</th><th class="td-num">Huérfanos</th><th class="td-num">Creados 1h</th></tr></thead>
                    <tbody>${queueRows || '<tr><td colspan="4" style="text-align:center;color:var(--tks-text-muted)">Sin datos</td></tr>'}</tbody>
                </table>
            </div>
        `;
    }

    function renderOpsChannels(channels) {
        const adapters = channels.adapters || {};
        const adapterRows = Object.entries(adapters).map(([name, info]) => `
            <tr>
                <td>${escapeHtml(channelLabel(name))}</td>
                <td>${adapterModeLabel(info.mode)}</td>
                <td>${escapeHtml(info.provider || '-')}</td>
                <td>${info.configured ? 'Sí' : 'No'}</td>
            </tr>
        `).join('');

        return `
            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Canales</h4>
                <table class="tks-pivot-table">
                    <thead><tr><th>Canal</th><th>Modo</th><th>Proveedor</th><th>Configurado</th></tr></thead>
                    <tbody>${adapterRows || '<tr><td colspan="4" style="text-align:center;color:var(--tks-text-muted)">Sin adaptadores</td></tr>'}</tbody>
                </table>
            </div>
        `;
    }

    function renderOpsNotifications(notifs) {
        const notifRows = notifs.slice(0, 10).map(n => `
            <tr>
                <td>${escapeHtml(n.codigo || `#${n.ticket_id}`)}</td>
                <td>${escapeHtml(channelLabel(n.channel || '-'))}</td>
                <td>${opsStatusLabel(n.status)}</td>
                <td>${Number(n.attempt_count || 0)}/${Number(n.max_attempts || 0)}</td>
                <td>${escapeHtml(n.last_error || '')}</td>
                <td>
                    ${n.status === 'failed' || n.status === 'pending'
                ? `<button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.retryChannel(${Number(n.id)})">Reintentar</button>`
                : '-'}
                </td>
            </tr>
        `).join('');

        return `
            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Notificaciones de Canal</h4>
                <table class="tks-pivot-table">
                    <thead><tr><th>Ticket</th><th>Canal</th><th>Estado</th><th>Intentos</th><th>Error</th><th>Acción</th></tr></thead>
                    <tbody>${notifRows || '<tr><td colspan="6" style="text-align:center;color:var(--tks-text-muted)">Sin notificaciones</td></tr>'}</tbody>
                </table>
            </div>
        `;
    }

    function renderOpsCompliance(exportRuns) {
        const latestExport = exportRuns.length ? exportRuns[0] : null;
        const latestExportStatus = latestExport ? opsStatusLabel(latestExport.status || '-') : 'Sin ejecuciones';

        return `
            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Exportación Compliance</h4>
                <div style="color:var(--tks-text-muted);font-size:0.8rem;">
                    Última ejecución: ${latestExport ? `${opsStatusLabel(latestExport.status || '-')} | artefacto=${latestExport.artifact_exists ? 'sí' : 'no'}` : 'sin ejecuciones'}
                </div>
            </div>
        `;
    }

    function renderOps(data) {
        const queue = data?.queue || {};
        const channels = data?.channels || {};
        const notifs = data?.channelNotifications?.items || [];
        const exportRuns = data?.complianceExportRuns?.items || [];

        const latestExport = exportRuns.length ? exportRuns[0] : null;
        const latestExportStatus = latestExport ? opsStatusLabel(latestExport.status || '-') : 'Sin ejecuciones';

        return `
        <div class="tks-dashboard">
            <div class="tks-stats-row">
                <div class="tks-stat-card">
                    <span class="label">Cola vencida ahora</span>
                    <span class="value">${Number(queue.totals?.due_now || 0)}</span>
                </div>
                <div class="tks-stat-card">
                    <span class="label">Ejecuciones huérfanas</span>
                    <span class="value">${Number(queue.totals?.stale_running || 0)}</span>
                </div>
                <div class="tks-stat-card">
                    <span class="label">Trabajos última hora</span>
                    <span class="value">${Number(queue.totals?.created_last_hour || 0)}</span>
                </div>
                <div class="tks-stat-card">
                    <span class="label">Exportación compliance</span>
                    <span class="value">${escapeHtml(latestExportStatus)}</span>
                </div>
            </div>
            ${renderOpsQueueHealth(queue)}
            ${renderOpsChannels(channels)}
            ${renderOpsNotifications(notifs)}
            ${renderOpsCompliance(exportRuns)}
        </div>
        `;
    }

    // --- MESSAGE TEMPLATES ---
    function buildCategoryOptionsHtml(categories, editingRule) {
        return categories.map((cat) => {
            const selected = String(editingRule?.categoria || categories[0] || 'general') === String(cat) ? ' selected' : '';
            return `<option value="${escapeHtml(cat)}"${selected}>${escapeHtml(cat)}</option>`;
        }).join('');
    }

    function renderMailTemplateCards(mailTemplates) {
        if (!mailTemplates.length) {
            return '<div class="tks-feed-empty">No hay plantillas disponibles.</div>';
        }
        return mailTemplates.map((template) => `
            <button class="tks-template-card" type="button" onclick="TksMain.openMailTemplateModal('${escapeJsSingleQuoted(template.key || '')}')">
                <span class="tks-template-card-label">${escapeHtml(template.label || template.key || 'Plantilla')}</span>
                <span class="tks-template-card-desc">${escapeHtml(template.description || '')}</span>
                <span class="tks-template-card-subject">${escapeHtml(template.subject_template || '') || 'Sin asunto'}</span>
                <span class="tks-template-card-meta">${template.uses_default_subject || template.uses_default_body ? 'Usando base actual del sistema' : 'Plantilla personalizada'}</span>
            </button>
        `).join('');
    }

    function renderRoutingRulesTableRows(routingRules) {
        if (!routingRules.length) {
            return `<tr><td colspan="6" style="text-align:center;color:var(--tks-text-muted)">Sin reglas configuradas</td></tr>`;
        }
        return routingRules.map((rule) => {
            const clientLabel = rule.customer_name ? `${escapeHtml(rule.customer_name)} <span style="opacity:0.6;font-size:0.8em">(${escapeHtml(rule.customer_id)})</span>` : '-';
            return `
            <tr>
                <td>${escapeHtml(rule.match_type === 'domain' ? 'Dominio' : 'Correo')}</td>
                <td>${escapeHtml(rule.match_value || '-')}</td>
                <td>${escapeHtml(catLabel(rule.categoria || 'general'))}</td>
                <td>${clientLabel}</td>
                <td>${rule.is_active ? 'Activa' : 'Inactiva'}</td>
                <td class="td-actions">
                    <button class="tks-btn tks-btn-ghost tks-btn-sm" type="button" onclick="TksMain.editRoutingRule(${Number(rule.id)})">
                        Editar
                    </button>
                    <button class="tks-btn tks-btn-danger tks-btn-sm" type="button" onclick="TksMain.deleteRoutingRule(${Number(rule.id)})">
                        Eliminar
                    </button>
                </td>
            </tr>
        `;
        }).join('');
    }

    function renderRoutingRuleForm(editingRule, categoryOptions, editing) {
        return `
            <div class="tks-settings-routing-grid">
                <div class="tks-form-group">
                    <label>Tipo</label>
                    <select id="tks-routing-match-type" class="tks-select">
                        <option value="email"${String(editingRule?.match_type || 'email') === 'email' ? ' selected' : ''}>Correo exacto</option>
                        <option value="domain"${String(editingRule?.match_type || '') === 'domain' ? ' selected' : ''}>Dominio</option>
                    </select>
                </div>

                <div class="tks-form-group">
                    <label>Valor</label>
                    <input
                        id="tks-routing-match-value"
                        class="tks-input"
                        type="text"
                        value="${escapeHtml(editingRule?.match_value || '')}"
                        placeholder="cliente@empresa.cl o empresa.cl"
                    >
                </div>

                <div class="tks-form-group">
                    <label>Área / Categoría</label>
                    <select id="tks-routing-categoria" class="tks-select">
                        <option value="">Automática / Sin especificar</option>
                        ${categoryOptions}
                    </select>
                </div>

                <div class="tks-form-group">
                    <label>Nombre Cliente (Referencia)</label>
                    <input
                        id="tks-routing-customer-name"
                        class="tks-input"
                        type="text"
                        value="${escapeHtml(editingRule?.customer_name || '')}"
                        placeholder="Transportes XYZ"
                    >
                </div>

                <div class="tks-form-group" style="align-self: flex-end; padding-bottom: 4px;">
                    ${editing ? `<button class="tks-btn tks-btn-ghost" type="button" onclick="TksMain.editRoutingRule(null);" style="margin-right: 0.5rem;">Cancelar</button>` : ''}
                    <button class="tks-btn tks-btn-primary" type="button" onclick="TksMain.saveRoutingRule()">
                        <i class="fas fa-save"></i> ${editing ? 'Actualizar regla' : 'Guardar regla'}
                    </button>
                </div>
            </div>
        `;
    }

    function renderMessageTemplates(data, options = {}) {
        const categories = Array.isArray(data?.categories) && data.categories.length
            ? data.categories
            : ['admin', 'ejecucion', 'general', 'redes', 'sistemas'];
        const mailTemplates = Array.isArray(data?.mailTemplates) ? data.mailTemplates : [];
        const routingRules = Array.isArray(data?.routingRules) ? data.routingRules : [];
        const editingRule = options?.editingRule || null;
        const editing = Boolean(editingRule && editingRule.id);

        const categoryOptions = buildCategoryOptionsHtml(categories, editingRule);
        const templateCards = renderMailTemplateCards(mailTemplates);
        const routingRows = renderRoutingRulesTableRows(routingRules);
        const routingForm = renderRoutingRuleForm(editingRule, categoryOptions, editing);

        return `
        <div class="tks-settings-shell">
            <section class="tks-settings-panel">
                <div class="tks-settings-head">
                    <div>
                        <h3>Plantillas de Correo</h3>
                        <p>Administra desde Ticketera el correo automático de acuse al cliente y los mensajes automáticos.</p>
                    </div>
                    <span class="tks-settings-scope">Admin / Encargado Mesa</span>
                </div>

                <div class="tks-settings-note">
                    <strong>Plantillas disponibles:</strong>
                    auto-respuesta, aviso nuevo TK mesa, asignacion de especialista, notificacion de especialista y cierre de TK.
                    Al abrir una plantilla, el editor carga el contenido actual efectivo del sistema, aunque no exista una version guardada en DB.
                </div>

                <div class="tks-template-card-grid">${templateCards}</div>
            </section>

            <section class="tks-settings-panel">
                <div class="tks-settings-head">
                    <div>
                        <h3>Enrutamiento y Asociación de Clientes</h3>
                        <p>Define a qué área y cliente cae un ticket cuando entra por un remitente o dominio específico.</p>
                    </div>
                    <span class="tks-settings-scope">Admin / Encargado Mesa</span>
                </div>

                ${routingForm}

                <div class="tks-pivot-container" style="margin-top:1rem">
                    <table class="tks-pivot-table">
                        <thead>
                            <tr>
                                <th>Tipo</th>
                                <th>Valor</th>
                                <th>Área</th>
                                <th>Cliente</th>
                                <th>Estado</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>${routingRows}</tbody>
                    </table>
                </div>
            </section>
        </div>
        `;
    }

    function renderAsignarClienteModal(ticketId, origenEmail, tituloTicket) {
        return `
        <div class="tks-modal-overlay open" id="tks-arch-asignar-modal">
            <div class="tks-modal">
                <div class="tks-modal-header">
                    <h3><i class="fas fa-user-tag"></i> Asignar Cliente</h3>
                    <button class="tks-modal-close" type="button" onclick="window.cerrarAsignarClienteModal()">&times;</button>
                </div>
                <div class="tks-modal-body">
                    <div class="tks-settings-note" style="margin-bottom:1rem">
                        <strong>${escapeHtml(tituloTicket || '')}</strong>
                        ${origenEmail ? `<br><span style="opacity:0.7;font-size:0.85rem"><i class="fas fa-envelope"></i> ${escapeHtml(origenEmail)}</span>` : ''}
                    </div>
                    <div class="tks-form-group">
                        <label>Buscar cliente</label>
                        <div style="display:flex;gap:.5rem">
                            <input id="tks-arch-asignar-search" class="tks-input" type="text"
                                placeholder="Nombre o RUT..."
                                onkeydown="if(event.key==='Enter') window.buscarClientesModal()">
                            <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="window.buscarClientesModal()">
                                <i class="fas fa-search"></i>
                            </button>
                        </div>
                    </div>
                    <div id="tks-arch-asignar-results" style="max-height:280px;overflow-y:auto;margin-top:0.5rem"></div>
                </div>
                <div class="tks-modal-footer" style="justify-content:space-between;align-items:center">
                    <div id="tks-arch-asignar-count" style="font-size:.82rem;color:var(--tks-text-muted)"></div>
                    <button class="tks-btn tks-btn-ghost" type="button" onclick="window.cerrarAsignarClienteModal()">Cancelar</button>
                </div>
            </div>
        </div>`;
    }

    function renderArchivosView() {
        return `
        <div class="tks-settings-shell">
            <section class="tks-settings-panel">
                <div class="tks-settings-head">
                    <div>
                        <h3>Tickets Archivados</h3>
                        <p>Todos los tickets cerrados y resueltos. Asigna clientes para construir el historial y habilitar reportes.</p>
                    </div>
                    <span class="tks-settings-scope">Admin / Encargado Mesa</span>
                </div>

                <div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1rem;align-items:flex-end">
                    <div class="tks-form-group" style="margin:0;min-width:200px">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Cliente</label>
                        <select class="tks-select" id="tks-arch-filter-cliente" style="min-width:200px" onchange="window.loadArchivados()">
                            <option value="">Todos los clientes</option>
                        </select>
                    </div>
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Categoría</label>
                        <select class="tks-select" id="tks-arch-filter-cat" style="min-width:140px" onchange="window.loadArchivados()">
                            <option value="">Todas</option>
                            <option value="redes">Redes</option>
                            <option value="sistemas">Sistemas</option>
                            <option value="ejecucion">Ejecución</option>
                            <option value="admin">Admin</option>
                            <option value="general">General</option>
                            <option value="bodega">Bodega</option>
                            <option value="gerencia">Gerencia</option>
                            <option value="implementaciones">Implementaciones</option>
                        </select>
                    </div>
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Estado</label>
                        <select class="tks-select" id="tks-arch-filter-estado" style="min-width:130px" onchange="window.loadArchivados()">
                            <option value="">Todos</option>
                            <option value="cerrado">Cerrado</option>
                            <option value="resuelto">Resuelto</option>
                        </select>
                    </div>
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Desde</label>
                        <input type="date" class="tks-input" id="tks-arch-filter-desde" style="min-width:140px" onchange="window.loadArchivados()">
                    </div>
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Hasta</label>
                        <input type="date" class="tks-input" id="tks-arch-filter-hasta" style="min-width:140px" onchange="window.loadArchivados()">
                    </div>
                    <button class="tks-btn tks-btn-ghost" onclick="window.resetArchivadosFiltros()" style="align-self:flex-end">
                        Limpiar
                    </button>
                </div>

                <div id="tks-archivados-results-container">
                    <div style="text-align:center;padding:2rem"><i class="fas fa-circle-notch fa-spin"></i> Cargando archivados...</div>
                </div>
            </section>

            <section class="tks-settings-panel">
                <div class="tks-settings-head">
                    <div>
                        <h3>Reportes por cliente</h3>
                        <p>Cada cliente en una línea: tickets activos, creados este mes y cerrados. Haz clic en "Ver reporte" para el detalle de ese cliente.</p>
                    </div>
                    <button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="window.cargarResumenClientes()"><i class="fas fa-sync"></i> Actualizar</button>
                </div>
                <div id="tks-clientes-resumen-container">
                    <div style="text-align:center;padding:1.5rem"><i class="fas fa-circle-notch fa-spin"></i> Cargando resumen...</div>
                </div>

                <div class="tks-settings-head" style="margin-top:1.75rem;border-top:1px solid var(--tks-border);padding-top:1.25rem">
                    <div>
                        <h3>Reporte general por período</h3>
                        <p>Tickets atendidos (resueltos/cerrados) agrupados por día, semana o mes. Déjalo en "Todos los clientes" o filtra por uno.</p>
                    </div>
                </div>
                <div style="display:flex;gap:0.75rem;flex-wrap:wrap;align-items:flex-end">
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Agrupar por</label>
                        <select class="tks-select" id="tks-atendidos-period" style="min-width:120px" onchange="window.generarReporteAtendidos()">
                            <option value="day">Día</option>
                            <option value="week">Semana</option>
                            <option value="month" selected>Mes</option>
                        </select>
                    </div>
                    <div class="tks-form-group" style="margin:0;min-width:200px">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Cliente</label>
                        <select class="tks-select" id="tks-atendidos-cliente" style="min-width:200px" onchange="window.generarReporteAtendidos()">
                            <option value="">Todos los clientes</option>
                        </select>
                    </div>
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Desde</label>
                        <input type="date" class="tks-input" id="tks-atendidos-desde" style="min-width:140px" onchange="window.generarReporteAtendidos()">
                    </div>
                    <div class="tks-form-group" style="margin:0">
                        <label style="font-size:0.8rem;margin-bottom:0.25rem;display:block">Hasta</label>
                        <input type="date" class="tks-input" id="tks-atendidos-hasta" style="min-width:140px" onchange="window.generarReporteAtendidos()">
                    </div>
                </div>
                <div id="tks-atendidos-resultado" style="margin-top:1rem"></div>
            </section>
        </div>
        `;
    }

    function renderMailTemplateEditorModal(template) {
        const subjectValue = String(template?.subject_template || '');
        const bodyValue = String(template?.body_template || '');
        const usesDefault = template?.uses_default_subject || template?.uses_default_body;
        return `
        <div class="tks-modal-overlay open" id="tks-template-editor-modal">
            <div class="tks-modal tks-template-editor-modal">
                <div class="tks-modal-header">
                    <h3>${escapeHtml(template?.label || 'Editar plantilla')}</h3>
                    <button class="tks-modal-close" type="button" onclick="TksMain.closeMailTemplateModal()">&times;</button>
                </div>
                <div class="tks-modal-body">
                    <p class="tks-settings-hint">${escapeHtml(template?.description || '')}</p>
                    ${usesDefault ? '<div class="tks-settings-note">Se esta mostrando la base actual del sistema. Si guardas cambios, esta plantilla quedara personalizada.</div>' : ''}
                    <div class="tks-settings-note">
                        <strong>Placeholders disponibles:</strong>
                        <code>{{customer_name}}</code>,
                        <code>{{customer_email}}</code>,
                        <code>{{ticket_code}}</code>,
                        <code>{{ticket_title}}</code>,
                        <code>{{ticket_category}}</code>,
                        <code>{{ticket_severity}}</code>,
                        <code>{{ticket_assignee}}</code>,
                        <code>{{assignee_name}}</code>,
                        <code>{{sla_summary}}</code>,
                        <code>{{auto_close_hours}}</code>.
                    </div>
                    <div class="tks-form-group">
                        <label>Asunto</label>
                        <input id="tks-template-editor-subject" class="tks-input" type="text" value="${escapeHtml(subjectValue)}">
                    </div>
                    <div class="tks-form-group">
                        <label>Cuerpo</label>
                        <textarea id="tks-template-editor-body" class="tks-textarea tks-settings-textarea" rows="12">${escapeHtml(bodyValue)}</textarea>
                    </div>
                </div>
                <div class="tks-modal-footer">
                    <button class="tks-btn tks-btn-ghost" type="button" onclick="TksMain.closeMailTemplateModal()">Cancelar</button>
                    <button class="tks-btn tks-btn-primary" type="button" onclick="TksMain.saveMessageTemplates()">
                        <i class="fas fa-save"></i> Guardar plantilla
                    </button>
                </div>
            </div>
        </div>
        `;
    }

    // --- MODAL NUEVO TICKET ---
    function renderCreateModal() {
        return `<div class="tks-modal-overlay" id="tks-create-modal">
            <div class="tks-modal">
                <div class="tks-modal-header">
                    <h3><i class="fas fa-plus-circle"></i> Nuevo Ticket</h3>
                    <button class="tks-modal-close" onclick="TksMain.closeCreateModal()">&times;</button>
                </div>
                <div class="tks-modal-body">
                    <div class="tks-form-group">
                        <label>Título</label>
                        <input type="text" class="tks-input" id="tks-new-titulo" placeholder="Describe el problema...">
                    </div>
                    <div class="tks-form-group">
                        <label>Descripción</label>
                        <textarea class="tks-textarea" id="tks-new-desc" rows="4" placeholder="Detalle del ticket..."></textarea>
                    </div>
                    <div class="tks-form-row">
                        <div class="tks-form-group">
                            <label>Categoría (auto-detecta si vacío)</label>
                            <select class="tks-select" id="tks-new-cat">
                                <option value="">Auto-detectar</option>
                                <option value="redes">🌐 Redes</option>
                                <option value="sistemas">💻 Sistemas</option>
                                <option value="ejecucion">🔧 Ejecución</option>
                                <option value="admin">📋 Admin</option>
                                <option value="bodega">📦 Bodega</option>
                                <option value="gerencia">👔 Gerencia</option>
                            </select>
                        </div>
                    </div>
                    <div class="tks-form-row">
                        <div class="tks-form-group">
                            <label>Email Cliente (opcional)</label>
                            <input type="email" class="tks-input" id="tks-new-email" placeholder="cliente@empresa.cl">
                        </div>
                        <div class="tks-form-group">
                            <label>Nombre Cliente (opcional)</label>
                            <input type="text" class="tks-input" id="tks-new-cliente" placeholder="Nombre del cliente">
                        </div>
                    </div>
                </div>
                <div class="tks-modal-footer">
                    <button class="tks-btn tks-btn-ghost" onclick="TksMain.closeCreateModal()">Cancelar</button>
                    <button class="tks-btn tks-btn-primary" onclick="TksMain.submitCreate()"><i class="fas fa-ticket-alt"></i> Crear Ticket</button>
                </div>
            </div>
        </div>`;
    }

    function renderAssociateClientModal(email) {
        return `<div class="tks-modal-overlay" id="tks-associate-modal">
            <div class="tks-modal">
                <div class="tks-modal-header">
                    <h3><i class="fas fa-link"></i> Vincular Cliente</h3>
                    <button class="tks-modal-close" onclick="TksMain.closeAssociateModal()">&times;</button>
                </div>
                <div class="tks-modal-body">
                    <div class="tks-form-group">
                        <label>Email detectado</label>
                        <input class="tks-input" type="text" value="${escapeHtml(email || '')}" readonly>
                    </div>
                    <div class="tks-form-group">
                        <label>Buscar cliente</label>
                        <div style="display:flex;gap:.5rem;align-items:center;">
                            <input id="tks-assoc-search" class="tks-input" type="text" placeholder="Nombre, RUT o ID cliente (vacío = lista base)" onkeydown="if(event.key==='Enter'){TksMain.searchClients()}">
                            <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.searchClients()">
                                <i class="fas fa-search"></i> Buscar
                            </button>
                        </div>
                    </div>
                    <div id="tks-assoc-results" class="tks-assoc-results"></div>
                </div>
                <div class="tks-modal-footer" style="justify-content:space-between;align-items:center;">
                    <div id="tks-assoc-count" style="font-size:.82rem;color:var(--tks-text-muted);">0 clientes</div>
                    <button class="tks-btn tks-btn-ghost" onclick="TksMain.closeAssociateModal()">Cerrar</button>
                </div>
            </div>
        </div>`;
    }


    function renderConsole(data) {
        if (!data.ok) return `<div class="tks-card"><p>Error cargando consola: ${data.detail || 'Error desconocido'}</p></div>`;

        const health = data.health || {};
        const audit = data.audit || [];
        const failedJobs = data.failed_jobs || [];

        return `
            <div class="tks-ops-header" style="margin-bottom: 2rem;">
                <h2 style="margin:0"><i class="fas fa-terminal"></i> Consola de Estado - Ticketera</h2>
                <div style="font-size:0.85rem;opacity:0.7">Sincronizado: ${formatExactDateTime(data.timestamp)}</div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="border-left: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Tickets Abiertos</div>
                    <div style="font-size:2rem; font-weight:700">${health.total_tickets_open}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Notificaciones Pendientes</div>
                    <div style="font-size:2rem; font-weight:700">${health.pending_notifications}</div>
                </div>
                <div class="tks-card" style="border-left: 4px solid ${health.failed_jobs_count > 0 ? 'var(--tks-danger)' : 'var(--tks-success)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7">Jobs Fallidos</div>
                    <div style="font-size:2rem; font-weight:700">${health.failed_jobs_count}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 2fr 1fr; gap: 1.5rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-history"></i> Actividad Reciente (Auditoría)</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        <table class="tks-table" style="font-size: 0.85rem">
                            <thead>
                                <tr>
                                    <th>Fecha</th>
                                    <th>Actor</th>
                                    <th>Acción</th>
                                    <th>Objetivo</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${audit.map(a => `
                                    <tr>
                                        <td style="white-space:nowrap">${formatDateTimeShort(a.timestamp)}</td>
                                        <td style="font-weight:600">${escapeHtml(a.actor)}</td>
                                        <td><span class="pill pill-sm">${escapeHtml(a.action)}</span></td>
                                        <td>${escapeHtml(a.target || '-')}</td>
                                    </tr>
                                `).join('') || '<tr><td colspan="4" style="text-align:center">Sin actividad registrada</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0; color:var(--tks-danger)"><i class="fas fa-exclamation-triangle"></i> Fallos Técnicos</h4>
                    <div style="max-height: 500px; overflow-y: auto;">
                        ${failedJobs.map(j => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem">
                                <div style="display:flex; justify-content:space-between; margin-bottom:4px">
                                    <strong style="color:var(--tks-warning)">${escapeHtml(j.job_type)}</strong>
                                    <span style="opacity:0.6">${formatDateTimeShort(j.updated_at)}</span>
                                </div>
                                <div style="color:var(--tks-danger); font-family:monospace; font-size:0.75rem">${escapeHtml(j.error_message)}</div>
                                <div style="font-size:0.7rem; opacity:0.5; margin-top:4px">Intentos: ${j.retries_count}</div>
                            </div>
                        `).join('') || '<div style="text-align:center; padding: 2rem; opacity:0.5">No hay fallos recientes detectados</div>'}
                    </div>
                </div>
            </div>
        `;
    }


    function renderMonthlyReport(data) {
        if (!data || !data.totals) return '<div class="tks-card"><p>No hay datos suficientes para generar el reporte.</p></div>';

        const totals = data.totals;
        const byCustomer = data.by_customer || [];
        const byCategory = data.by_category || [];
        const sla = data.sla || {};
        
        const slaPct = sla.total_resueltos > 0 
            ? Math.round((sla.a_tiempo / sla.total_resueltos) * 100) 
            : 100;

        return `
            <div class="tks-report-header" style="margin-bottom: 2rem; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h2 style="margin:0"><i class="fas fa-chart-bar"></i> Informe Mensual de Actividad</h2>
                    <div style="font-size:0.9rem;opacity:0.7">Período: ${data.period} | Generado: ${formatExactDateTime(data.generated_at)}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1.5rem; margin-bottom: 2rem;">
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-info)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Creados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.creados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-success)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Tickets Terminados</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.terminados}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid var(--tks-warning)">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Pendientes del Mes</div>
                    <div style="font-size:2.5rem; font-weight:700">${totals.pendientes}</div>
                </div>
                <div class="tks-card" style="text-align:center; border-top: 4px solid ${slaPct >= 80 ? 'var(--tks-success)' : 'var(--tks-danger)'}">
                    <div style="font-size:0.8rem; text-transform:uppercase; opacity:0.7; margin-bottom:0.5rem">Cumplimiento SLA</div>
                    <div style="font-size:2.5rem; font-weight:700">${slaPct}%</div>
                    <div style="font-size:0.7rem; opacity:0.6">${sla.a_tiempo} de ${sla.total_resueltos} a tiempo</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-users"></i> Top Clientes (Volumen)</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Cliente</th>
                                <th style="text-align:right">Tickets</th>
                                <th style="width: 100px"></th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCustomer.map(c => {
                                const pct = Math.round((c.total / totals.creados) * 100);
                                return `
                                    <tr>
                                        <td>${escapeHtml(c.nombre)}</td>
                                        <td style="text-align:right; font-weight:600">${c.total}</td>
                                        <td>
                                            <div style="height:6px; width:100%; background:rgba(255,255,255,0.1); border-radius:3px; overflow:hidden;">
                                                <div style="height:100%; width:${pct}%; background:var(--tks-info);"></div>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('') || '<tr><td colspan="3" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                </div>

                <div class="tks-card">
                    <h4 style="margin-top:0"><i class="fas fa-tags"></i> Distribución por Área</h4>
                    <table class="tks-table" style="font-size: 0.9rem">
                        <thead>
                            <tr>
                                <th>Categoría</th>
                                <th style="text-align:right">Tickets</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${byCategory.map(c => `
                                <tr>
                                    <td><span class="pill pill-sm">${catLabel(c.cat)}</span></td>
                                    <td style="text-align:right; font-weight:600">${c.total}</td>
                                </tr>
                            `).join('') || '<tr><td colspan="2" style="text-align:center">No hay datos</td></tr>'}
                        </tbody>
                    </table>
                    
                    <div style="margin-top:2rem; padding:1.5rem; background:rgba(0,0,0,0.2); border-radius:8px; border:1px solid rgba(255,255,255,0.05)">
                        <h5 style="margin:0 0 1rem 0">Resumen Ejecutivo</h5>
                        <p style="font-size:0.85rem; line-height:1.5; opacity:0.8; margin:0">
                            Durante el período <strong>${data.period}</strong> se gestionaron un total de <strong>${totals.creados}</strong> tickets nuevos. 
                            La tasa de resolución dentro del mes fue del <strong>${Math.round((totals.terminados/totals.creados)*100)}%</strong>, 
                            manteniendo un nivel de servicio (SLA) del <strong>${slaPct}%</strong>.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    return {
        escapeHtml,
        escapeJsSingleQuoted,
        renderDashboard,
        renderAssignmentTimeline,
        renderTicketTable,
        renderDetail,
        renderKanban,
        renderMessageTemplates,
        renderArchivosView,
        renderAsignarClienteModal,
        renderMailTemplateEditorModal,
        renderAttachmentPreviewModal,
        renderOps,
        renderCreateModal,
        slaStatus,
        catLabel,
        statusLabel,
        sevLabel,
        renderCustomer360,
        renderAssociateClientModal,
        renderConsole,
        renderMonthlyReport,
    };
})();
