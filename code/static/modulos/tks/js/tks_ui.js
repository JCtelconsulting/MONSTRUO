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
                    <span class="label">Total Tickets</span>
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
                <h4>📊 SLA Compliance — ${slaPct}%</h4>
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

    // --- TICKET ITEM (LISTA) ---
    function renderTicketItem(t) {
        const sla = slaStatus(t.vence_at);
        return `<div class="tks-item" data-id="${t.id}" data-prio="${t.prioridad || 3}">
            <div class="tks-item-header">
                <span class="tks-item-title">${escapeHtml(t.titulo || 'Sin título')}</span>
                <span class="tks-status tks-status-${escapeHtml(t.estado)}">${statusLabel(t.estado)}</span>
            </div>
            <div class="tks-item-meta">
                <div class="tks-item-meta-left">
                    <span class="tks-codigo">${escapeHtml(t.codigo || `#${t.id}`)}</span>
                    <span class="tks-cat-badge tks-cat-${escapeHtml(t.categoria || 'general')}">${catLabel(t.categoria)}</span>
                    <span class="tks-sev tks-sev-${escapeHtml(t.severidad)}">${sevLabel(t.severidad)}</span>
                </div>
                <span class="tks-sla-indicator ${sla.class}">${sla.label}</span>
            </div>
        </div>`;
    }

    // --- DETALLE ---
    function renderDetail(t, eventos = [], emails = []) {
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
                    <div class="tks-email-meta">Unknown/System vs ${escapeHtml(em.from_addr || em.to_addr)}</div>
                </div>`;
            }
        } else {
            emailsHtml = '<div style="padding:1rem;color:var(--tks-text-muted);font-style:italic">No hay correos registrados.</div>';
        }

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
                <button class="tks-detail-tab active" onclick="this.parentElement.nextElementSibling.querySelector('.tks-timeline-container').style.display='block';this.parentElement.nextElementSibling.querySelector('.tks-emails-container').style.display='none';this.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active'));this.classList.add('active')">📜 Timeline</button>
                <button class="tks-detail-tab" onclick="this.parentElement.nextElementSibling.querySelector('.tks-timeline-container').style.display='none';this.parentElement.nextElementSibling.querySelector('.tks-emails-container').style.display='block';this.parentElement.querySelectorAll('button').forEach(b=>b.classList.remove('active'));this.classList.add('active')">📧 Historial Correos</button>
            </div>
            
            <div class="tks-detail-content-area">
                 <div class="tks-timeline-container">
                    <div class="tks-timeline">${timelineHtml || '<p style="color:var(--tks-text-muted)">Sin eventos</p>'}</div>
                 </div>
                 <div class="tks-emails-container" style="display:none">
                    ${emailsHtml}
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
        renderTicketItem,
        renderDetail,
        renderKanban,
        renderCreateModal,
        timeAgo,
        slaStatus,
        catLabel,
        statusLabel,
        sevLabel,
    };
})();
