/**
 * Ticketera V3 — Capa UI
 * Renderizado puro: recibe datos, devuelve HTML.
 */
const TksUI = (() => {

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

    function timeAgo(dateStr) {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now - d) / 1000);
        if (diff < 60) return 'ahora';
        if (diff < 3600) return `${Math.floor(diff / 60)}m`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
        return `${Math.floor(diff / 86400)}d`;
    }

    function slaStatus(venceAt) {
        if (!venceAt) return { class: '', label: '' };
        const now = new Date();
        const vence = new Date(venceAt);
        const diffH = (vence - now) / (1000 * 60 * 60);
        if (diffH < 0) return { class: 'tks-sla-breached', label: `⚠ VENCIDO (${Math.abs(Math.round(diffH))}h)` };
        if (diffH < 4) return { class: 'tks-sla-warning', label: `⏰ ${Math.round(diffH)}h restantes` };
        return { class: 'tks-sla-ok', label: `${Math.round(diffH)}h restantes` };
    }

    function catLabel(cat) {
        return { redes: 'Redes', sistemas: 'Sistemas', ejecucion: 'Ejecución', admin: 'Admin', general: 'General' }[cat] || escapeHtml(cat) || 'General';
    }

    function statusLabel(s) {
        return { abierto: 'Abierto', en_progreso: 'En Progreso', resuelto: 'Resuelto', cerrado: 'Cerrado' }[s] || escapeHtml(s);
    }

    function sevLabel(s) {
        return { critica: 'Crítica', alta: 'Alta', media: 'Media', baja: 'Baja' }[s] || escapeHtml(s);
    }

    function opsStatusLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
        return {
            pending: 'pendiente',
            dispatching: 'despachando',
            sent: 'enviado',
            failed: 'fallido',
            cancelled: 'cancelado',
            running: 'ejecutando',
            retry: 'reintento',
            completed: 'completado',
            completed_with_errors: 'completado con errores',
        }[normalized] || escapeHtml(value || '-');
    }

    function adapterModeLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
        return {
            disabled: 'deshabilitado',
            dry_run: 'simulación',
            live: 'activo',
        }[normalized] || escapeHtml(value || '-');
    }

    // --- DASHBOARD ---
    function renderDashboard(stats) {
        const total = stats.total || 0;
        const abiertos = (stats.by_status?.abierto || 0) + (stats.by_status?.en_progreso || 0);
        const resueltos = (stats.by_status?.resuelto || 0) + (stats.by_status?.cerrado || 0);
        const criticas = stats.by_prio?.critica || 0;

        const onTime = stats.sla_compliance?.on_time || 0;
        const breached = stats.sla_compliance?.breached || 0;
        const slaTotal = onTime + breached;
        const slaPct = slaTotal > 0 ? Math.round((onTime / slaTotal) * 100) : 100;

        // Pivot table
        let pivotRows = '';
        const pivot = stats.pivot_assignee || {};
        for (const [user, data] of Object.entries(pivot)) {
            pivotRows += `<tr>
                <td>${escapeHtml(user)}</td>
                <td class="td-num">${data.abierto || 0}</td>
                <td class="td-num">${data.en_progreso || 0}</td>
                <td class="td-num">${data.resuelto || 0}</td>
                <td class="td-num">${data.cerrado || 0}</td>
                <td class="td-num" style="font-weight:700">${data.total || 0}</td>
            </tr>`;
        }

        // By Category
        let catCards = '';
        const cats = stats.by_category || {};
        for (const [cat, count] of Object.entries(cats)) {
            catCards += `<div class="tks-stat-card" style="--card-accent: var(--tks-cat-${escapeHtml(cat)})">
                <span class="label">${catLabel(cat)}</span>
                <span class="value">${count}</span>
            </div>`;
        }

        return `
        <div class="tks-dashboard">
            <div class="tks-stats-row">
                <div class="tks-stat-card" style="--card-accent: var(--tks-accent)">
                    <span class="label">Tickets Totales</span>
                    <span class="value">${total}</span>
                </div>
                <div class="tks-stat-card" style="--card-accent: var(--tks-abierto)">
                    <span class="label">Activos</span>
                    <span class="value">${abiertos}</span>
                </div>
                <div class="tks-stat-card" style="--card-accent: var(--tks-cerrado)">
                    <span class="label">Resueltos</span>
                    <span class="value">${resueltos}</span>
                </div>
                <div class="tks-stat-card" style="--card-accent: var(--tks-critica)">
                    <span class="label">Críticas</span>
                    <span class="value">${criticas}</span>
                </div>
            </div>

            <div class="tks-sla-bar">
                <h4>📊 Cumplimiento SLA — ${slaPct}%</h4>
                <div class="sla-progress">
                    <div class="on-time" style="width:${slaPct}%"></div>
                    <div class="breached" style="width:${100 - slaPct}%"></div>
                </div>
                <div class="sla-labels">
                    <span>✅ A tiempo: ${onTime}</span>
                    <span>⚠ Vencidos: ${breached}</span>
                </div>
            </div>

            <div class="tks-stats-row">
                ${catCards}
            </div>

            <div class="tks-pivot-container">
                <h4>📋 Carga por Técnico</h4>
                <table class="tks-pivot-table">
                    <thead>
                        <tr>
                            <th>Técnico</th>
                            <th class="td-num">Abierto</th>
                            <th class="td-num">En Progreso</th>
                            <th class="td-num">Resuelto</th>
                            <th class="td-num">Cerrado</th>
                            <th class="td-num">Total</th>
                        </tr>
                    </thead>
                    <tbody>${pivotRows || '<tr><td colspan="6" style="text-align:center;color:var(--tks-text-muted)">Sin datos</td></tr>'}</tbody>
                </table>
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
    function renderTicketTable(items) {
        if (!items || items.length === 0) {
            return '<div style="padding:2rem;text-align:center;color:var(--tks-text-muted)">Sin tickets</div>';
        }

        const rows = items.map(t => {
            const sla = slaStatus(t.vence_at);
            const slaClass = sla.class === 'tks-sla-breached' ? 'color:var(--tks-critica)' : (sla.class === 'tks-sla-warning' ? 'color:var(--tks-alta)' : 'color:var(--tks-text-muted)');
            const clientNameRaw = decodeMimeEncodedString(t.cliente_nombre || '');
            let clientHtml = '<span style="color:var(--tks-text-muted)">-</span>';

            if (clientNameRaw && clientNameRaw !== 'Desconocido') {
                clientHtml = `<div style="font-weight:500;color:var(--tks-text-main)">${escapeHtml(clientNameRaw)}</div>`;
            } else if (t.origen_email) {
                clientHtml = `<button class="tks-btn-link" onclick="event.stopPropagation(); TksMain.openAssociateClientModal('${escapeHtml(t.origen_email)}')">
                    <i class="fas fa-link"></i> Desconocido (Vincular)
                </button>`;
            }

            return `<tr class="tks-row" data-id="${t.id}">
                <td class="td-min"><span class="tks-codigo">${escapeHtml(t.codigo || `#${t.id}`)}</span></td>
                <td>
                    <div style="font-weight:500;color:var(--tks-text-main)">${escapeHtml(t.titulo || 'Sin título')}</div>
                </td>
                <td>
                    ${clientHtml}
                    ${t.origen_email ? `<div style="font-size:0.75rem;color:var(--tks-text-muted)">${escapeHtml(t.origen_email)}</div>` : ''}
                </td>
                <td class="td-min"><span class="tks-cat-badge tks-cat-${escapeHtml(t.categoria || 'general')}">${catLabel(t.categoria)}</span></td>
                <td class="td-min"><span class="tks-sev tks-sev-${escapeHtml(t.severidad)}">${sevLabel(t.severidad)}</span></td>
                <td class="td-min"><span class="tks-status tks-status-${escapeHtml(t.estado)}">${statusLabel(t.estado)}</span></td>
                <td class="td-min" style="font-size:0.8rem;white-space:nowrap;${slaClass}">
                    ${sla.class === 'tks-sla-breached' ? '<i class="fas fa-exclamation-triangle"></i>' : ''} 
                    ${sla.label}
                </td>
                <td class="td-min" style="font-size:0.8rem;color:var(--tks-text-muted)">${timeAgo(t.created_at)}</td>
                <td class="td-min" style="text-align:right">
                    <button class="tks-btn-icon-sm" title="Ver detalle"><i class="fas fa-chevron-right"></i></button>
                </td>
            </tr>`;
        }).join('');

        return `
        <div class="tks-table-wrapper">
            <table class="tks-table tks-list-table">
                <thead>
                    <tr>
                        <th style="width:80px">ID</th>
                        <th>Asunto</th>
                        <th>Cliente</th>
                        <th style="width:100px">Cat</th>
                        <th style="width:90px">Sev</th>
                        <th style="width:100px">Estado</th>
                        <th style="width:120px">SLA</th>
                        <th style="width:100px">Creado</th>
                        <th style="width:40px"></th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    // --- DETALLE ---
    function renderDetail(t, eventos = [], emails = [], ticketAttachments = []) {
        if (!t) return '<div class="tks-detail-empty"><span>Selecciona un ticket</span></div>';

        const sla = slaStatus(t.vence_at);
        const hasClientEmail = !!(t.origen_email && String(t.origen_email).trim());
        const threadLabel = t.email_thread_id ? 'Se enviará en la misma cadena' : 'Sin hilo previo';

        let timelineHtml = '';
        for (const ev of eventos) {
            const isSystem = ev.usuario === 'system';
            timelineHtml += `<div class="tks-timeline-item ${isSystem ? 'system' : 'note'}">
                <div class="tks-timeline-time">${timeAgo(ev.creado_at)}</div>
                <div class="tks-timeline-event">${escapeHtml(ev.evento)}</div>
                <div class="tks-timeline-detail">${escapeHtml(ev.detalle)}</div>
                <div class="tks-timeline-user">${escapeHtml(ev.usuario)}</div>
            </div>`;
        }

        // Historial de Correos
        let emailsHtml = '';
        if (emails && emails.length > 0) {
            for (const em of emails) {
                const isIncoming = em.direction === 'incoming';
                const dirLabel = isIncoming ? '📥 Recibido' : '📤 Enviado';
                const dirClass = isIncoming ? 'tks-email-in' : 'tks-email-out';
                let attachmentsHtml = '';

                try {
                    const atts = JSON.parse(em.attachments_json || '[]');
                    if (atts.length > 0) {
                        attachmentsHtml = '<div class="tks-email-attachments">';
                        atts.forEach(a => {
                            // Link directo o placeholder. Como son archivos locales, quizás necesitemos una ruta de descarga.
                            // Por ahora, solo mostramos nombre y tamaño.
                            const sizeKb = Math.round((a.size || 0) / 1024);
                            attachmentsHtml += `<span class="tks-att-chip"><i class="fas fa-paperclip"></i> ${escapeHtml(a.filename || 'ajunto')} (${sizeKb}KB)</span>`;
                        });
                        attachmentsHtml += '</div>';
                    }
                } catch (e) { }

                emailsHtml += `
                <div class="tks-email-item ${dirClass}">
                    <div class="tks-email-header">
                        <span class="tks-email-dir">${dirLabel}</span>
                        <span class="tks-email-date">${timeAgo(em.created_at)}</span>
                    </div>
                    <div class="tks-email-subject">${escapeHtml(em.subject)}</div>
                    <div class="tks-email-body">${em.body_html}</div> <!-- Render HTML safely? Trusting backend cleaning -->
                    ${attachmentsHtml}
                    <div class="tks-email-meta">Sistema/Desconocido vs ${escapeHtml(em.from_addr || em.to_addr)}</div>
                </div>`;
            }
        } else {
            emailsHtml = '<div style="padding:1rem;color:var(--tks-text-muted);font-style:italic">No hay correos registrados.</div>';
        }

        const attachmentItems = (ticketAttachments || []).map(att => {
            const downloadUrl = TksApi.getTicketAttachmentDownloadUrl(t.id, att.id);
            const sizeKb = Math.max(0, Math.round(Number(att.size_bytes || 0) / 1024));
            return `<a class="tks-att-chip" href="${escapeHtml(downloadUrl)}" target="_blank" rel="noopener">
                <i class="fas fa-paperclip"></i> ${escapeHtml(att.filename || 'adjunto')} (${sizeKb}KB)
            </a>`;
        }).join('');

        return `
        <div class="tks-detail-header">
            <h2 class="tks-detail-title">${escapeHtml(t.titulo)}</h2>
            <div class="tks-detail-meta">
                <span class="tks-codigo">${escapeHtml(t.codigo || `#${t.id}`)}</span>
                <span class="separator"></span>
                <span class="tks-cat-badge tks-cat-${escapeHtml(t.categoria || 'general')}">${catLabel(t.categoria)}</span>
                <span class="separator"></span>
                <span class="tks-sev tks-sev-${escapeHtml(t.severidad)}">${sevLabel(t.severidad)}</span>
                <span class="separator"></span>
                <span class="tks-status tks-status-${escapeHtml(t.estado)}">${statusLabel(t.estado)}</span>
                <span class="separator"></span>
                <span class="tks-sla-indicator ${sla.class}">${sla.label}</span>
            </div>
        </div>

        <div class="tks-detail-actions">
            ${t.estado === 'abierto' ? `<button class="tks-btn tks-btn-warning tks-btn-sm" onclick="TksMain.changeStatus(${t.id},'en_progreso')"><i class="fas fa-play"></i> En Progreso</button>` : ''}
            ${t.estado === 'en_progreso' ? `<button class="tks-btn tks-btn-success tks-btn-sm" onclick="TksMain.changeStatus(${t.id},'resuelto')"><i class="fas fa-check"></i> Resolver</button>` : ''}
            ${t.estado !== 'cerrado' ? `<button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.changeStatus(${t.id},'cerrado')"><i class="fas fa-times"></i> Cerrar</button>` : ''}
            <button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.openReassign(${t.id})"><i class="fas fa-user-tag"></i> Reasignar</button>
        </div>

        <div class="tks-detail-body">
            <div class="tks-description-box">${escapeHtml(t.descripcion || 'Sin descripción')}</div>

            <div style="margin:0.8rem 0 1rem 0;">
                <div style="font-size:0.8rem;color:var(--tks-text-muted);margin-bottom:0.3rem;">Adjuntos del ticket</div>
                <div class="tks-email-attachments">
                    ${attachmentItems || '<span class="tks-att-chip" style="opacity:.7">Sin adjuntos</span>'}
                </div>
            </div>

            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.8rem;margin-bottom:1.5rem;font-size:0.85rem;">
                <div><strong style="color:var(--tks-text-muted)">Asignado:</strong> ${escapeHtml(t.asignado_a || 'Sin asignar')}</div>
                <div><strong style="color:var(--tks-text-muted)">Creador:</strong> ${escapeHtml(t.creador_id || '-')}</div>
                <div><strong style="color:var(--tks-text-muted)">Creado:</strong> ${timeAgo(t.created_at)}</div>
                <div><strong style="color:var(--tks-text-muted)">SLA:</strong> ${escapeHtml(t.sla_horas || '-')}h</div>
                ${t.origen_email ? `<div><strong style="color:var(--tks-text-muted)">Email cliente:</strong> ${escapeHtml(t.origen_email)}</div>` : ''}
                ${t.cliente_nombre ? `<div><strong style="color:var(--tks-text-muted)">Cliente:</strong> ${escapeHtml(t.cliente_nombre)}</div>` : ''}
            </div>
            
            <!-- TABS INTERNOS DEL DETALLE -->
            <div class="tks-detail-tabs">
                <button class="tks-detail-tab active" onclick="this.parentElement.nextElementSibling.querySelector('.tks-timeline-container').style.display='block';this.parentElement.nextElementSibling.querySelector('.tks-emails-container').style.display='none';this.parentElement.nextElementSibling.querySelector('.tks-customer-360-container').style.display='none';this.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active'));this.classList.add('active')">📜 Línea de tiempo</button>
                <button class="tks-detail-tab" onclick="this.parentElement.nextElementSibling.querySelector('.tks-timeline-container').style.display='none';this.parentElement.nextElementSibling.querySelector('.tks-emails-container').style.display='block';this.parentElement.nextElementSibling.querySelector('.tks-customer-360-container').style.display='none';this.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active'));this.classList.add('active')">📧 Historial Correos</button>
                <button class="tks-detail-tab" onclick="this.parentElement.nextElementSibling.querySelector('.tks-timeline-container').style.display='none';this.parentElement.nextElementSibling.querySelector('.tks-emails-container').style.display='none';this.parentElement.nextElementSibling.querySelector('.tks-customer-360-container').style.display='block';this.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active'));this.classList.add('active'); TksMain.loadCustomer360('${escapeHtml(t.customer_id || '')}', ${t.id})">🏢 Cliente 360°</button>
            </div>
            
            <div class="tks-detail-content-area">
                 <div class="tks-timeline-container">
                    <div class="tks-timeline">${timelineHtml || '<p style="color:var(--tks-text-muted)">Sin eventos</p>'}</div>
                 </div>
                 <div class="tks-emails-container" style="display:none">
                    ${emailsHtml}
                 </div>
                 <div class="tks-customer-360-container" style="display:none; padding:1rem">
                    <div class="tks-loading-spinner" id="tks-c360-loading">Cargando datos del cliente...</div>
                    <div id="tks-c360-content" style="display:none">
                        <!-- Content injected by TksMain.loadCustomer360 -->
                    </div>
                 </div>
            </div>

            ${hasClientEmail ? `
            <div class="tks-email-reply-card">
                <div class="tks-email-reply-head">
                    <strong>📧 Responder por correo</strong>
                    <span style="color:var(--tks-text-muted);font-size:0.75rem;">${escapeHtml(threadLabel)}</span>
                </div>
                <div style="font-size:0.8rem;color:var(--tks-text-muted);margin-bottom:0.5rem;">
                    Destinatario: ${escapeHtml(t.origen_email)}
                </div>
                <textarea class="tks-textarea tks-email-reply-input" id="tks-email-reply-input" rows="3"
                    placeholder="Escribe la respuesta al cliente..."
                    onkeydown="if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){TksMain.replyByEmail(${t.id})}"></textarea>
                
                <div style="margin-top:0.5rem;">
                    <label style="font-size:0.8rem;color:var(--tks-text-muted);display:block;margin-bottom:0.3rem;">Adjuntar archivos:</label>
                    <input type="file" id="tks-email-reply-files" multiple class="tks-file-input">
                </div>

                <div class="tks-email-reply-actions">
                    <span style="color:var(--tks-text-muted);font-size:0.72rem;">Ctrl+Enter para enviar</span>
                    <button id="tks-email-reply-send-btn" class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.replyByEmail(${t.id})">
                        <i class="fas fa-envelope"></i> Enviar correo
                    </button>
                </div>
            </div>
            ` : ''}
        </div>

        <div class="tks-add-note">
            <input type="text" id="tks-note-input" placeholder="Agregar nota..." onkeydown="if(event.key==='Enter')TksMain.addNote(${t.id})">
            <button class="tks-btn tks-btn-primary" onclick="TksMain.addNote(${t.id})"><i class="fas fa-paper-plane"></i></button>
        </div>`;
    }

    function renderCustomer360(data) {
        if (!data) return '<p>No se encontró información del cliente.</p>';

        const debtClass = data.status === 'DEBT' ? 'tks-sla-breached' : 'tks-sla-ok';
        const debtLabel = data.status === 'DEBT' ? 'Con Deuda' : 'Al Día';

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
                    <button class="tks-btn tks-btn-warning tks-btn-sm" onclick="TksMain.generatePaymentLink('${data.customer_id}', ${data.total_debt})">
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
    function renderKanban(kanban) {
        const cols = [
            { key: 'abierto', label: 'Abierto', color: 'var(--tks-abierto)' },
            { key: 'en_progreso', label: 'En Progreso', color: 'var(--tks-en_progreso)' },
            { key: 'resuelto', label: 'Resuelto', color: 'var(--tks-resuelto)' },
            { key: 'cerrado', label: 'Cerrado', color: 'var(--tks-cerrado)' },
        ];

        return `<div class="tks-kanban-board">${cols.map(col => {
            const items = kanban[col.key] || [];
            return `<div class="tks-kanban-col">
                <div class="tks-kanban-col-header">
                    <span class="tks-kanban-col-title"><span class="dot" style="background:${col.color}"></span>${col.label}</span>
                    <span class="tks-kanban-col-count">${items.length}</span>
                </div>
                <div class="tks-kanban-col-body" data-status="${col.key}">
                    ${items.map(t => `
                        <div class="tks-kanban-card" data-id="${t.id}" data-prio="${t.prioridad || 3}"
                             draggable="true"
                             ondragstart="TksMain.onDragStart(event, ${t.id})"
                             onclick="TksMain.openDetail(${t.id})">
                            <div class="tks-kanban-card-title">${escapeHtml(t.titulo)}</div>
                            <div class="tks-kanban-card-meta">
                                <span class="tks-cat-badge tks-cat-${escapeHtml(t.categoria || 'general')}">${catLabel(t.categoria)}</span>
                                <span>${escapeHtml(t.asignado_a || '-')}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>`;
        }).join('')}</div>`;
    }

    // --- OPS VIEW ---
    function renderOps(data) {
        const queue = data?.queue || {};
        const queueRows = Object.entries(queue.by_job_type || {}).map(([job, metrics]) => `
            <tr>
                <td>${escapeHtml(job)}</td>
                <td class="td-num">${Number(metrics.due_now || 0)}</td>
                <td class="td-num">${Number(metrics.stale_running || 0)}</td>
                <td class="td-num">${Number(metrics.created_last_hour || 0)}</td>
            </tr>
        `).join('');

        const channels = data?.channels || {};
        const adapters = channels.adapters || {};
        const adapterRows = Object.entries(adapters).map(([name, info]) => `
            <tr>
                <td>${escapeHtml(name)}</td>
                <td>${adapterModeLabel(info.mode)}</td>
                <td>${escapeHtml(info.provider || '-')}</td>
                <td>${info.configured ? 'Sí' : 'No'}</td>
            </tr>
        `).join('');

        const notifs = data?.channelNotifications?.items || [];
        const notifRows = notifs.slice(0, 10).map(n => `
            <tr>
                <td>${escapeHtml(n.codigo || `#${n.ticket_id}`)}</td>
                <td>${escapeHtml(n.channel || '-')}</td>
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

        const jiraRuns = data?.jiraRuns?.items || [];
        const jiraRows = jiraRuns.slice(0, 8).map(r => `
            <tr>
                <td>${escapeHtml(r.run_type || '-')}</td>
                <td>${opsStatusLabel(r.status)}</td>
                <td>${escapeHtml(r.started_at || '-')}</td>
                <td>${escapeHtml(r.ended_at || '-')}</td>
            </tr>
        `).join('');

        const kpis = data?.parallelKpi?.items || [];
        const kpi = kpis.length ? kpis[0] : null;
        const reconciliationOk = data?.reconciliation?.ok === true;
        const exportRuns = data?.complianceExportRuns?.items || [];
        const latestExport = exportRuns.length ? exportRuns[0] : null;

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
                    <span class="label">Reconciliación Jira</span>
                    <span class="value">${reconciliationOk ? 'OK' : 'ALERTA'}</span>
                </div>
            </div>

            <div class="tks-pivot-container">
                <h4>Salud de Cola</h4>
                <table class="tks-pivot-table">
                    <thead><tr><th>Tipo de trabajo</th><th class="td-num">Vencidos</th><th class="td-num">Huérfanos</th><th class="td-num">Creados 1h</th></tr></thead>
                    <tbody>${queueRows || '<tr><td colspan="4" style="text-align:center;color:var(--tks-text-muted)">Sin datos</td></tr>'}</tbody>
                </table>
            </div>

            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Canales</h4>
                <table class="tks-pivot-table">
                    <thead><tr><th>Canal</th><th>Modo</th><th>Proveedor</th><th>Configurado</th></tr></thead>
                    <tbody>${adapterRows || '<tr><td colspan="4" style="text-align:center;color:var(--tks-text-muted)">Sin adaptadores</td></tr>'}</tbody>
                </table>
            </div>

            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Notificaciones de Canal</h4>
                <table class="tks-pivot-table">
                    <thead><tr><th>Ticket</th><th>Canal</th><th>Estado</th><th>Intentos</th><th>Error</th><th>Acción</th></tr></thead>
                    <tbody>${notifRows || '<tr><td colspan="6" style="text-align:center;color:var(--tks-text-muted)">Sin notificaciones</td></tr>'}</tbody>
                </table>
            </div>

            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Paralelo Jira</h4>
                <div style="margin-bottom:0.6rem;color:var(--tks-text-muted);font-size:0.8rem;">
                    KPI diario: ${kpi ? `SLA ${Number(kpi.sla_compliance_pct || 0)}% | descuadre ${Number(kpi.mismatch_count || 0)}` : 'sin corte diario'}
                </div>
                <table class="tks-pivot-table">
                    <thead><tr><th>Tipo ejecución</th><th>Estado</th><th>Inicio</th><th>Fin</th></tr></thead>
                    <tbody>${jiraRows || '<tr><td colspan="4" style="text-align:center;color:var(--tks-text-muted)">Sin ejecuciones</td></tr>'}</tbody>
                </table>
            </div>

            <div class="tks-pivot-container" style="margin-top:1rem">
                <h4>Exportación Compliance</h4>
                <div style="color:var(--tks-text-muted);font-size:0.8rem;">
                    Última ejecución: ${latestExport ? `${opsStatusLabel(latestExport.status || '-')} | artefacto=${latestExport.artifact_exists ? 'sí' : 'no'}` : 'sin ejecuciones'}
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
                            <label>Severidad</label>
                            <select class="tks-select" id="tks-new-sev">
                                <option value="baja">🟢 Baja</option>
                                <option value="media" selected>🔵 Media</option>
                                <option value="alta">🟠 Alta</option>
                                <option value="critica">🔴 Crítica</option>
                            </select>
                        </div>
                        <div class="tks-form-group">
                            <label>Categoría (auto-detecta si vacío)</label>
                            <select class="tks-select" id="tks-new-cat">
                                <option value="">Auto-detectar</option>
                                <option value="redes">🌐 Redes</option>
                                <option value="sistemas">💻 Sistemas</option>
                                <option value="ejecucion">🔧 Ejecución</option>
                                <option value="admin">📋 Admin</option>
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

    return {
        renderDashboard,
        renderTicketTable,
        renderDetail,
        renderKanban,
        renderOps,
        renderCreateModal,
        timeAgo,
        slaStatus,
        catLabel,
        statusLabel,
        statusLabel,
        sevLabel,
        renderCustomer360,
    };
})();
