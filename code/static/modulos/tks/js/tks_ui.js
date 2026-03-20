/**
 * Ticketera V3 — Capa UI
 * Renderizado puro: recibe datos, devuelve HTML.
 */
const TksUI = (() => {
    const WAITING_SUBESTADOS = Object.freeze(['pendiente_cliente', 'pendiente_compra', 'pendiente_tercero']);

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
        return { class: 'tks-sla-ok', label: `${Math.round(diffH)}h restantes` };
    }

    function catLabel(cat) {
        return { redes: 'Redes', sistemas: 'Sistemas', ejecucion: 'Ejecución', admin: 'Admin', general: 'General' }[cat] || escapeHtml(cat) || 'General';
    }

    function roleCapabilityLabel(role) {
        return {
            admin: 'Admin',
            encargado_mesa: 'Encargado Mesa',
            ops: 'Operaciones',
            redes: 'Redes',
            sistemas: 'Sistemas',
            implementaciones: 'Implementaciones',
            gerencia: 'Gerencia',
            finance: 'Finanzas',
            warehouse: 'Bodega'
        }[String(role || '').trim().toLowerCase()] || escapeHtml(role || '-');
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
        return { abierto: 'Abierto', en_progreso: 'En Progreso', resuelto: 'Resuelto', cerrado: 'Cerrado' }[s] || escapeHtml(s);
    }

    function normalizeSubestadoKey(value) {
        const normalized = String(value || '').trim().toLowerCase();
        if (normalized === 'triage' || normalized === 'nuevo') return 'recibido';
        return normalized;
    }

    function subestadoLabel(s) {
        const normalized = normalizeSubestadoKey(s);
        return {
            recibido: 'Recibido',
            asignado: 'Asignado',
            en_analisis: 'En análisis',
            pendiente_compra: 'Pendiente compra',
            pendiente_cliente: 'Pendiente cliente',
            pendiente_tercero: 'Pendiente tercero',
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
        return {
            disabled: 'Deshabilitado',
            dry_run: 'Simulación',
            live: 'Activo',
        }[normalized] || humanizeMachineText(value);
    }

    function channelLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
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
        return {
            ticket_channels_dispatch: 'Despacho de notificaciones de canales',
            ticket_email_incoming_poll: 'Lectura de correo entrante',
            ticket_email_reconcile: 'Conciliación de correo de tickets',
            jira_delta_sync_daily: 'Sincronización diaria Jira (delta)',
            jira_bootstrap_open: 'Carga inicial Jira (tickets abiertos)',
            compliance_export_run: 'Ejecución de exportación de cumplimiento',
            compliance_purge_run: 'Depuración de datos de cumplimiento',
            auto_reply_dispatch: 'Despacho de autorrespuestas',
            jobs_recover_stale: 'Recuperación de ejecuciones huérfanas',
        }[normalized] || humanizeMachineText(value);
    }

    function jiraRunTypeLabel(value) {
        const normalized = String(value || '').trim().toLowerCase();
        return {
            bootstrap: 'Carga inicial',
            delta: 'Sincronización delta',
            bootstrap_open: 'Carga inicial (abiertos)',
            delta_sync: 'Sincronización delta',
            daily: 'Ejecución diaria',
        }[normalized] || humanizeMachineText(value);
    }

    function parseEmailIdentity(raw) {
        const text = String(raw || '').trim();
        if (!text) return { name: '', email: '' };

        const angled = text.match(/^\s*"?([^"<]+?)"?\s*<\s*([^>]+)\s*>\s*$/);
        if (angled) {
            return { name: angled[1].trim(), email: angled[2].trim() };
        }

        const mail = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
        if (!mail) return { name: text, email: '' };

        const email = mail[0].trim();
        const name = text.replace(mail[0], '').replace(/[<>()"]/g, '').trim();
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

    function renderAssignmentTimeline(data) {
        const payload = data || {};
        const technicians = Array.isArray(payload.technicians) ? payload.technicians : [];
        const queue = Array.isArray(payload.queue) ? payload.queue : [];
        const scopeMode = String(payload.scope || '').trim().toLowerCase();
        const showQueue = scopeMode !== 'mine';
        const generatedAt = payload.generated_at || '';
        const referenceTs = toTs(generatedAt || payload?.range?.end_at || new Date().toISOString()) || Date.now();
        const dayStart = new Date(referenceTs);
        dayStart.setHours(0, 0, 0, 0);

        const laborStart = new Date(dayStart.getTime());
        laborStart.setHours(8, 0, 0, 0);
        const laborEnd = new Date(dayStart.getTime());
        laborEnd.setHours(18, 0, 0, 0);

        const extraBeforeHours = 0; 
        const extraAfterHours = 0;  
        const viewStartTs = laborStart.getTime() - (extraBeforeHours * 60 * 60 * 1000);
        const viewEndTs = laborEnd.getTime() + (extraAfterHours * 60 * 60 * 1000);
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

        const sortedTechnicians = [...technicians].sort((a, b) => {
            const aName = String(a?.username || '').trim().toLowerCase();
            const bName = String(b?.username || '').trim().toLowerCase();
            const aGeneral = aName === 'general';
            const bGeneral = bName === 'general';
            if (aGeneral !== bGeneral) return aGeneral ? -1 : 1;
            return aName.localeCompare(bName, 'es');
        });

        const laneHtml = sortedTechnicians.map((tech) => {
            const items = Array.isArray(tech.items) ? tech.items : [];
            const status = String(tech.status || '').trim().toLowerCase();
            const isAvailable = status === 'disponible';
            const techName = String(tech.username || '-');
            const roles = Array.isArray(tech.roles) ? tech.roles : [];
            const specialties = Array.isArray(tech.specialties) ? tech.specialties : [];
            const capabilitySource = roles.length > 0 ? roles : specialties;
            const techCapabilities = [];
            capabilitySource.forEach((capability) => {
                const label = roles.length > 0
                    ? roleCapabilityLabel(capability)
                    : catLabel(capability);
                if (label && !techCapabilities.includes(label)) techCapabilities.push(label);
            });
            const nextTicket = tech.next_queue_ticket || null;

            const blocks = [];
            items.forEach((item) => {
                const segments = Array.isArray(item.segments) ? item.segments : [];
                const itemCode = String(item.codigo || `#${item.ticket_id || '-'}`);
                const itemTitle = String(item.titulo || 'Sin título');
                const state = statusLabel(item.estado || '-');
                (segments || []).forEach((seg) => {
                    const segStart = toTs(seg.start_at);
                    const segEnd = toTs(seg.end_at);
                    if (!segStart || !segEnd) return;
                    const clippedStart = Math.max(segStart, viewStartTs);
                    const clippedEnd = Math.min(segEnd, viewEndTs);
                    if (clippedEnd <= clippedStart) return;
                    const left = ((clippedStart - viewStartTs) / viewSpan) * 100;
                    const width = Math.max(0.65, ((clippedEnd - clippedStart) / viewSpan) * 100);
                    const phaseKeyRaw = String(seg.phase || item.active_phase || '').trim().toLowerCase();
                    const phaseKey = ['asignado', 'en_progreso', 'resuelto'].includes(phaseKeyRaw) ? phaseKeyRaw : 'asignado';
                    const title = `${itemCode} · ${state} · ${phaseLabel(phaseKey)} · ${formatDateTimeShort(seg.start_at)} → ${formatDateTimeShort(seg.end_at)} · ${itemTitle}`;
                    blocks.push({
                        left,
                        width,
                        phaseKey,
                        itemCode,
                        title,
                    });
                });
            });

            blocks.sort((a, b) => (a.left - b.left) || (b.width - a.width));
            const blocksHtml = blocks.length
                ? blocks.map((block) => `<span class="tks-assign-slot tks-assign-seg-${escapeHtml(block.phaseKey)}" style="left:${block.left.toFixed(3)}%;width:${block.width.toFixed(3)}%" title="${escapeHtml(block.title)}"><span class="tks-assign-slot-label">${escapeHtml(block.itemCode)}</span></span>`).join('')
                : '<span class="tks-assign-row-empty">Sin actividad en este horario.</span>';

            const nextQueueHtml = nextTicket
                ? `<span class="tks-assign-next-inline">Siguiente sugerido: <strong>${escapeHtml(nextTicket.codigo || `#${nextTicket.ticket_id || '-'}`)}</strong></span>`
                : '<span class="tks-assign-next-inline empty">Sin ticket en cola sugerido.</span>';

            return `<article class="tks-assign-schedule-row">
                <div class="tks-assign-tech-col">
                    <div class="tks-assign-tech-name">${escapeHtml(techName)}</div>
                    <div class="tks-assign-tech-meta">${escapeHtml(techCapabilities.join(' + ') || 'Sin rol técnico')}</div>
                    <div class="tks-assign-tech-status ${isAvailable ? 'available' : 'busy'}">${isAvailable ? 'Disponible' : 'Ocupado'}</div>
                </div>
                <div class="tks-assign-track-col">
                    <div class="tks-assign-track-schedule">
                        ${tickLinesHtml}
                        ${blocksHtml}
                    </div>
                    <div class="tks-assign-row-foot">
                        <span>Tickets: ${escapeHtml(String(items.length || 0))}</span>
                        ${nextQueueHtml}
                    </div>
                </div>
            </article>`;
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
                        <span><strong>Día:</strong> ${escapeHtml(new Date(referenceTs).toLocaleDateString('es-CL'))}</span>
                        <span class="tks-sep">·</span>
                        <span><strong>Actualizado:</strong> ${escapeHtml(formatTimeOnly(generatedAt))}</span>
                    </div>
                </div>
            </div>

            <div class="tks-assign-ruler-hours">
                ${rulerHtml}
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
    function renderDashboard(stats, assignmentData = null) {
        const total = stats.total || 0;
        const abiertos = (stats.by_status?.abierto || 0) + (stats.by_status?.en_progreso || 0);
        const resueltos = (stats.by_status?.resuelto || 0) + (stats.by_status?.cerrado || 0);
        const criticas = stats.by_prio?.critica || 0;

        const onTime = stats.sla_compliance?.on_time || 0;
        const breached = stats.sla_compliance?.breached || 0;
        const slaTotal = onTime + breached;
        const slaPct = slaTotal > 0 ? Math.round((onTime / slaTotal) * 100) : 100;

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
    function renderTicketTable(items) {
        if (!items || items.length === 0) {
            return '<div class="tks-list-empty">Sin tickets</div>';
        }

        const rows = items.map(t => {
            const sla = slaStatus(t.vence_at);
            const slaClass = sla.class === 'tks-sla-breached'
                ? 'is-breached'
                : (sla.class === 'tks-sla-warning' ? 'is-warning' : 'is-ok');
            const clientNameRaw = decodeMimeEncodedString(t.cliente_nombre || '');
            let clientHtml = '<span class="tks-client-empty">-</span>';

            if (clientNameRaw && clientNameRaw !== 'Desconocido') {
                clientHtml = `<div class="tks-client-name">${escapeHtml(clientNameRaw)}</div>`;
            } else if (t.origen_email) {
                const originEmailJs = escapeJsSingleQuoted(t.origen_email);
                clientHtml = `<button class="tks-btn-link" onclick="TksMain.openAssociateClientModal('${originEmailJs}'); return false;">
                    <i class="fas fa-link"></i> Desconocido (Vincular)
                </button>`;
            }

            const subjectNormalized = sentenceCase(t.titulo);

            return `<tr class="tks-row" data-id="${t.id}">
                <td class="td-min"><span class="tks-codigo">${escapeHtml(t.codigo || `#${t.id}`)}</span></td>
                <td>
                    <div class="tks-ticket-title fade-overflow" title="${escapeHtml(t.titulo || 'Sin título')}">${escapeHtml(subjectNormalized)}</div>
                </td>
                <td>
                    ${clientHtml}
                    ${t.origen_email ? `<div class="tks-origin-email">${escapeHtml(t.origen_email)}</div>` : ''}
                </td>
                <td class="td-min"><span class="tks-cat-badge tks-cat-${escapeHtml(t.categoria || 'general')}">${catLabel(t.categoria)}</span></td>
                <td class="td-min"><span class="tks-sev tks-sev-${escapeHtml(t.severidad)}">${sevLabel(t.severidad)}</span></td>
                <td class="td-min"><span class="tks-status tks-status-${escapeHtml(t.estado)}">${statusLabel(t.estado)}</span></td>
                <td class="td-min tks-sla-cell ${slaClass}">
                    ${sla.class === 'tks-sla-breached' ? '<i class="fas fa-exclamation-triangle"></i>' : ''} 
                    ${sla.label}
                </td>
            </tr>`;
        }).join('');

        return `
        <div class="tks-table-wrapper">
            <table class="tks-table tks-list-table">
                <thead>
                    <tr>
                        <th class="tks-th-code">NRº de Ticket</th>
                        <th>Asunto</th>
                        <th>Cliente</th>
                        <th class="tks-th-cat">Categoria</th>
                        <th class="tks-th-sev">Severidad</th>
                        <th class="tks-th-status">Estado</th>
                        <th class="tks-th-sla">SLA</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    }

    // --- DETALLE ---
    function renderDetail(t, eventos = [], emails = [], ticketAttachments = [], permissions = {}) {
        if (!t) return '<div class="tks-detail-empty"><span>Selecciona un ticket</span></div>';

        const sla = slaStatus(t.vence_at);
        const canChangeStatus = permissions.canChangeStatus !== false;
        const canClaim = permissions.canClaim === true;
        const canAssignTicket = permissions.canAssignTicket === true;

        // Restore missing definitions
        const canParticipate = permissions.canParticipate === true;
        const blockedReason = String(permissions.blockedReason || '').trim();
        const roleKey = String(permissions.currentRole || '').trim().toLowerCase();

        const isGerenciaViewer = roleKey === 'gerencia';
        const status = String(t.estado || '').toLowerCase();
        const isClosed = status === 'cerrado';
        const isResolved = status === 'resuelto';

        // Regla: Si está CERRADO, nadie puede agregar notas ni responder.
        // Regla: Si está RESUELTO, no se puede responder correos (solo notas).
        const canAddInternalNote = permissions.canAddInternalNote === true && !isClosed;

        // Responder solo si no es Gerencia, tiene permisos y NO está resuelto/cerrado
        const canReplyComposer = (permissions.isAdmin !== true || canParticipate) && !isGerenciaViewer && !isClosed && !isResolved;
        const requestedComposerMode = String(permissions.composerMode || permissions.activeTab || 'note') === 'reply' ? 'reply' : 'note';
        const composerMode = canReplyComposer && requestedComposerMode === 'reply' ? 'reply' : 'note';
        const draft = permissions.draft || null;
        const draftMeta = permissions.draftMeta || {};
        const draftCanEdit = draftMeta.canEdit === true;
        const draftBlockedReason = String(draftMeta.blockedReason || blockedReason || '').trim();
        const canEditDraftNow = draftCanEdit;
        const draftVersion = Number(draft?.version || 1);
        const resolveAttachment = buildEmailAttachmentResolver(t.id, ticketAttachments);

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
        let resueltoCountdownHtml = '';
        if (currentEstado === 'resuelto' && resueltoAutoCloseHours > 0) {
            if (Number.isFinite(resolvedAnchorTs)) {
                const deadlineTs = resolvedAnchorTs + (resueltoAutoCloseHours * 60 * 60 * 1000);
                const pendingClose = deadlineTs <= Date.now();
                const countdownText = pendingClose
                    ? 'Cierre automático pendiente (se aplicará pronto)'
                    : `Cierre automático en ${formatCountdownRemaining(deadlineTs - Date.now())}`;
                resueltoCountdownHtml = `<div id="tks-resuelto-countdown"
                    class="tks-resuelto-countdown${pendingClose ? ' is-overdue' : ''}"
                    data-deadline="${escapeHtml(new Date(deadlineTs).toISOString())}">
                    ${escapeHtml(countdownText)}
                </div>`;
            } else {
                resueltoCountdownHtml = `<div id="tks-resuelto-countdown" class="tks-resuelto-countdown">
                    Cierre automático configurado: ${resueltoAutoCloseHours}h desde resolución.
                </div>`;
            }
        }
        const allowedNextSubestados = Array.isArray(workflow.allowed_next)
            ? workflow.allowed_next.map((v) => normalizeSubestadoKey(v)).filter(Boolean)
            : [];
        const waitingSubestadoSet = new Set(WAITING_SUBESTADOS);
        const showWaitingSubestados = currentEstado === 'en_progreso';
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
        const flowCandidates = allowedNextSubestados.filter(Boolean);
        const waitingCandidates = flowCandidates.filter((sub) => waitingSubestadoSet.has(sub));
        let selectableFlowCandidates = showWaitingSubestados
            ? flowCandidates
            : flowCandidates.filter((sub) => !waitingSubestadoSet.has(sub));
        // Flujo separado:
        // - Solo cerrar desde resuelto.
        // - Cerrado solo puede ofrecer reapertura a en_progreso.
        if (currentEstado === 'resuelto') {
            selectableFlowCandidates = selectableFlowCandidates.filter((sub) => sub === 'cerrado');
        } else if (currentEstado === 'cerrado') {
            selectableFlowCandidates = selectableFlowCandidates.filter((sub) => sub === 'en_progreso' || sub === 'reabierto');
        } else {
            selectableFlowCandidates = selectableFlowCandidates.filter((sub) => sub !== 'cerrado');
        }
        // Evita ofrecer un avance redundante a "en_progreso" cuando ya está en progreso
        // (excepto cuando se vuelve desde un subestado de espera).
        if (currentEstado === 'en_progreso' && !waitingSubestadoSet.has(currentSubestado)) {
            const filtered = selectableFlowCandidates.filter((sub) => sub !== 'en_progreso');
            if (filtered.length) selectableFlowCandidates = filtered;
        }
        const nonWaitingCandidates = selectableFlowCandidates.filter((sub) => !waitingSubestadoSet.has(sub));
        const flowPool = nonWaitingCandidates.length ? nonWaitingCandidates.filter(s => s !== 'asignado') : selectableFlowCandidates.filter(s => s !== 'asignado');
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

        let managementActions = '';
        if (canClaim) {
            managementActions += `<button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.takeTicket(${t.id})"><i class="fas fa-hand-paper"></i> Tomar ticket</button>`;
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
            const attachmentsHtml = (item.attachments || []).map((att) => {
                const attachmentId = resolveAttachment(att);
                const label = `${escapeHtml(att.filename || 'adjunto')} (${sizeLabel(att.size_bytes ?? att.size ?? 0)})`;
                if (attachmentId) {
                    const url = TksApi.getTicketAttachmentDownloadUrl(t.id, attachmentId);
                    return `<a class="tks-att-chip" href="${escapeHtml(url)}" target="_blank" rel="noopener">
                        <i class="fas fa-paperclip"></i> ${label}
                    </a>`;
                }
                return `<span class="tks-att-chip tks-att-chip-muted" title="Adjunto no disponible para descarga">
                    <i class="fas fa-paperclip"></i> ${label}
                </span>`;
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
                </section>
            </div>`;
        }

        const sidebarAttachments = (ticketAttachments || []).map((att) => {
            const downloadUrl = TksApi.getTicketAttachmentDownloadUrl(t.id, att.id);
            return `<a class="tks-side-attachment" href="${escapeHtml(downloadUrl)}" target="_blank" rel="noopener">
                <span class="name">${escapeHtml(att.filename || 'adjunto')}</span>
                <span class="size">${sizeLabel(att.size_bytes)}</span>
            </a>`;
        }).join('');

        const notePaneHtml = canAddInternalNote
            ? `<div class="tks-note-composer">
                <input type="text" id="tks-note-input" placeholder="Agregar nota interna..." onkeydown="if(event.key==='Enter')TksMain.addNote(${t.id})">
                <button class="tks-btn tks-btn-primary" onclick="TksMain.addNote(${t.id})"><i class="fas fa-paper-plane"></i> Guardar nota</button>
            </div>`
            : `<div class="tks-readonly-box">${escapeHtml(blockedReason || 'Solo lectura para notas internas.')}</div>`;

        const draftAttachmentsHtml = (draft?.attachments || []).map((att) => {
            const removeBtn = canEditDraftNow
                ? `<button class="tks-btn-icon-sm" title="Eliminar adjunto" onclick="TksMain.deleteDraftAttachment(${t.id}, ${Number(att.id)})"><i class="fas fa-trash"></i></button>`
                : '';
            return `<div class="tks-draft-attachment-row">
                <span><i class="fas fa-paperclip"></i> ${escapeHtml(att.filename || 'adjunto')} (${sizeLabel(att.size_bytes)})</span>
                ${removeBtn}
            </div>`;
        }).join('');
        const draftCcValue = draft ? String(draft?.cc_addrs || '') : notifyEmailsList.join(', ');
        const draftBccValue = String(draft?.bcc_addrs || '');

        let lockBoxHtml = '';
        if (draftBlockedReason) {
            lockBoxHtml = `<span class="tks-lock-label">${escapeHtml(draftBlockedReason)}</span>`;
        }

        const statusManagementHtml = canChangeStatus
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
                        <div class="tks-status-editor-hint">${currentEstado === 'resuelto'
                ? (resueltoAutoCloseHours > 0
                    ? `Seguimiento activo en resuelto. Cierre automático en ${resueltoAutoCloseHours}h; también puedes cerrar de inmediato al aprobar cliente.`
                    : 'Seguimiento activo en resuelto. Puedes cerrar al aprobar cliente o esperar cierre automático.')
                : currentEstado === 'cerrado'
                    ? 'Ticket cerrado. Solo se permite reapertura excepcional para continuar trabajo.'
                    : 'Usa este botón para avanzar el ticket en el flujo oficial.'}</div>
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
                    ` : '<div class="tks-status-editor-hint">Subestados de espera disponibles solo en estado En Progreso.</div>'}
                </div>
              `
            : `<div class="tks-readonly-box">${escapeHtml(blockedReason || 'Solo lectura para gestión de estado.')}</div>`;

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
                        <span class="tks-status-display tks-status-tone-${escapeHtml(t.estado)}">${statusLabel(t.estado)}</span>
                        ${resueltoCountdownHtml}
                    </div>
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
                    ${canAssociateClient ? `
                        <div class="tks-customer-link">
                            <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.openAssociateClientModal('${originEmailForJs}')">
                                <i class="fas fa-link"></i> Asociar correo a cliente
                            </button>
                        </div>
                    ` : ''}
                    ${assigneeControlHtml}
                </div>
            </div>`;

        return `
        <div class="tks-detail-header tks-detail-header-pro">
            <button class="tks-btn-icon-sm tks-detail-close" onclick="TksMain.closeDetail()" title="Volver a la lista">
                <i class="fas fa-times"></i>
            </button>
            <h2 class="tks-detail-title tks-detail-title-centered">${escapeHtml(t.titulo)}</h2>
        </div>

        <div class="tks-detail-layout">
            <section class="tks-detail-main-col">
                ${topCardsHtml}

                <div class="tks-feed-card">
                    <div class="tks-section-title"><i class="fas fa-stream"></i> Línea de tiempo</div>
                    <div id="tks-unified-feed" class="tks-unified-feed">
                        ${feedHtml || '<div class="tks-feed-empty">Sin actividad registrada.</div>'}
                    </div>
                </div>

                <div class="tks-composer-card">
                    <div class="tks-section-title"><i class="fas fa-comment-dots"></i> Comunicación</div>
                    <div class="tks-composer-mode-switch">
                        ${canAddInternalNote
                ? `<button class="tks-composer-mode-btn ${composerMode === 'note' ? 'active' : ''}" data-composer-mode="note" onclick="TksMain.switchComposerMode('note')">
                            <i class="fas fa-sticky-note"></i> Nota interna
                        </button>`
                : ''}
                        ${canReplyComposer
                ? `<button class="tks-composer-mode-btn ${composerMode === 'reply' ? 'active' : ''}" data-composer-mode="reply" onclick="TksMain.switchComposerMode('reply')">
                                <i class="fas fa-reply"></i> Responder cliente
                            </button>`
                : ''}
                    </div>

                    <div data-composer-pane="note" style="${composerMode === 'note' ? '' : 'display:none'}">
                        ${notePaneHtml}
                    </div>

                    ${canReplyComposer
                ? `<div data-composer-pane="reply" style="${composerMode === 'reply' ? '' : 'display:none'}">
                            <div class="tks-email-reply-card">
                                <div class="tks-email-reply-head">
                                    <strong>Correo al cliente (borrador persistente)</strong>
                                    ${lockBoxHtml}
                                </div>
                                ${draftBlockedReason && !draftCanEdit ? `<div class="tks-readonly-box">${escapeHtml(draftBlockedReason)}</div>` : ''}
                                <input type="hidden" id="tks-draft-version" value="${draftVersion}">
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
                                    <input class="tks-input" id="tks-draft-subject" value="${escapeHtml(draft?.subject || '')}" ${canEditDraftNow ? '' : 'readonly'}>
                                </div>
                                <div class="tks-form-group">
                                    <label>Descripción</label>
                                    <textarea class="tks-textarea tks-email-reply-input" id="tks-draft-body" rows="7" ${canEditDraftNow ? '' : 'readonly'}>${escapeHtml(draft?.body_text || '')}</textarea>
                                </div>
                                <div class="tks-form-group">
                                    <label>Adjuntos borrador</label>
                                    <div class="tks-draft-attachments">${draftAttachmentsHtml || '<div style="color:var(--tks-text-muted);font-size:0.8rem;">Sin adjuntos</div>'}</div>
                                </div>
                                <div class="tks-email-reply-actions">
                                    <input type="file" id="tks-draft-files" multiple class="tks-file-input" ${canEditDraftNow ? '' : 'disabled'}>
                                    <button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.uploadDraftAttachments(${t.id})" ${canEditDraftNow ? '' : 'disabled'}>
                                        <i class="fas fa-paperclip"></i> Subir adjuntos
                                    </button>
                                </div>
                                <div class="tks-email-reply-actions">
                                    <button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.saveEmailDraft(${t.id})" ${canEditDraftNow ? '' : 'disabled'}>
                                        <i class="fas fa-save"></i> Guardar borrador
                                    </button>
                                    <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.reviewSendDraft(${t.id})" ${canEditDraftNow ? '' : 'disabled'}>
                                        <i class="fas fa-paper-plane"></i> Revisar y enviar
                                    </button>
                                    <button class="tks-btn tks-btn-danger tks-btn-sm" onclick="TksMain.discardEmailDraft(${t.id})" ${canEditDraftNow ? '' : 'disabled'}>
                                        <i class="fas fa-trash"></i> Descartar
                                    </button>
                                </div>
                            </div>
                        </div>`
                : ''}
                </div>
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
    function renderKanban(kanban, options = {}) {
        const canDrag = options.canDrag === true;
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
                             draggable="${canDrag ? 'true' : 'false'}"
                             ${canDrag ? `ondragstart="TksMain.onDragStart(event, ${t.id})"` : ''}
                             onclick="TksMain.openDetail(${t.id})">
                            <div class="tks-kanban-card-title">${escapeHtml(t.titulo)}</div>
                            <div class="tks-kanban-card-meta">
                                <span class="tks-cat-badge tks-cat-${escapeHtml(t.categoria || 'general')}">${catLabel(t.categoria)}</span>
                                <span>${escapeHtml(t.asignado_a ? formatAssigneeDisplay(t.asignado_a) : '-')}</span>
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
                <td>${escapeHtml(jobTypeLabel(job))}</td>
                <td class="td-num">${Number(metrics.due_now || 0)}</td>
                <td class="td-num">${Number(metrics.stale_running || 0)}</td>
                <td class="td-num">${Number(metrics.created_last_hour || 0)}</td>
            </tr>
        `).join('');

        const channels = data?.channels || {};
        const adapters = channels.adapters || {};
        const adapterRows = Object.entries(adapters).map(([name, info]) => `
            <tr>
                <td>${escapeHtml(channelLabel(name))}</td>
                <td>${adapterModeLabel(info.mode)}</td>
                <td>${escapeHtml(info.provider || '-')}</td>
                <td>${info.configured ? 'Sí' : 'No'}</td>
            </tr>
        `).join('');

        const notifs = data?.channelNotifications?.items || [];
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

        const jiraRuns = data?.jiraRuns?.items || [];
        const jiraRows = jiraRuns.slice(0, 8).map(r => `
            <tr>
                <td>${escapeHtml(jiraRunTypeLabel(r.run_type || '-'))}</td>
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

    return {
        escapeHtml,
        escapeJsSingleQuoted,
        renderDashboard,
        renderAssignmentTimeline,
        renderTicketTable,
        renderDetail,
        renderKanban,
        renderOps,
        renderCreateModal,
        slaStatus,
        catLabel,
        statusLabel,
        sevLabel,
        renderCustomer360,
        renderAssociateClientModal,
    };
})();
