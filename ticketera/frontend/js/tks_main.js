/**
 * Ticketera V3 — Controlador Principal
 * Orquesta estado, eventos, tabs, y comunicación entre API y UI.
 */
const TksMain = (() => {
    // ---- Estado ----
    let currentTab = 'dashboard';
    let selectedTicketId = null;
    let selectedTicket = null;
    let filters = { status: null, q: '', categoria: null, severidad: null, asignado_a: null };
    let notifCount = 0;
    let searchTimeout = null;
    let pollIntervalId = null;
    let isInitialized = false;
    let tabRequestToken = 0;
    let listRequestToken = 0;
    let detailRequestToken = 0;
    let panelAbortController = null;
    let listAbortController = null;
    let detailAbortController = null;
    let notifInFlight = false;
    let notifAbortController = null;
    const DEFAULT_LIST_LIMIT = 50;
    const CACHE_TTL_MS = 15000;
    const DEFAULT_TICKETERA_CATEGORIES = Object.freeze(['admin', 'ejecucion', 'general', 'redes', 'sistemas']);
    const cache = {
        dashboard: null,
        assignment: null,
        kanban: null,
        messages: null,
        ops: null,
        list: new Map(),
    };
    const ROLE_ADMIN = 'admin';
    const ROLE_MESA_MANAGER = 'encargado_mesa';
    const ROLE_TECH = new Set(['ops', 'redes', 'sistemas', 'implementaciones', ROLE_MESA_MANAGER]);
    const ROLE_GERENCIA = 'gerencia';
    const ROLE_MANAGEMENT = new Set([ROLE_ADMIN, ROLE_MESA_MANAGER]);
    const ROLE_DISPATCH = new Set(['ops', ROLE_MESA_MANAGER]);
    const ROLE_OPS_READ = new Set([ROLE_ADMIN]);
    const MAIN_STATUS_SEQUENCE = ['abierto', 'en_progreso', 'resuelto', 'cerrado'];
    let sessionCtx = {
        user: '',
        role: '',
        roles: [],
        canWrite: false,
        canCreate: false,
        canViewOps: false,
        canManageMessages: false,
        isTech: false,
        isScopedTech: false,
        isAdmin: false,
    };
    let detailActiveTab = 'note';
    let draftLockToken = '';
    let draftHeartbeatIntervalId = null;
    let currentDraftSnapshot = null;
    let currentDraftMeta = {
        canEdit: false,
        blockedReason: '',
        heartbeatSeconds: 60,
    };
    const AUTO_PROGRESS_DELAY_MS = 60000;
    let autoProgressTimeoutId = null;
    let currentWorkflow = null;
    let resueltoCountdownIntervalId = null;
    const ASSIGNEE_CACHE_TTL_MS = 120000;
    let assigneeDirectoryCache = { items: [], ts: 0 };
    let kanbanDragSourceStatus = '';
    let messageSettingsState = {
        categories: [...DEFAULT_TICKETERA_CATEGORIES],
        mailTemplates: [],
        routingRules: [],
        activeTemplateKey: '',
        editingRuleId: null,
    };

    // ---- Elementos clave ----
    function el(id) { return document.getElementById(id); }
    function isFresh(entry) {
        return !!entry && (Date.now() - entry.ts) < CACHE_TTL_MS;
    }
    function clearDataCache() {
        cache.dashboard = null;
        cache.assignment = null;
        cache.kanban = null;
        cache.messages = null;
        cache.ops = null;
        cache.list.clear();
    }

    function errorMessage(err) {
        return String(err?.message || 'Error inesperado');
    }

    function errorHtml(err) {
        return TksUI.escapeHtml(errorMessage(err));
    }

    function normalizeMessageSettingsData(rawData) {
        const data = rawData || {};
return {
            categories: Array.isArray(data?.categories) && data.categories.length
                ? data.categories
                : [...DEFAULT_TICKETERA_CATEGORIES],
            mail_templates: Array.isArray(data?.mail_templates) ? data.mail_templates : [],
            routing_rules: Array.isArray(data?.routing_rules) ? data.routing_rules : [],
        };
    }

    function hydrateMessageSettingsState(rawData) {
        const normalized = normalizeMessageSettingsData(rawData);
        messageSettingsState = {
            categories: [...normalized.categories],
            mailTemplates: normalized.mail_templates.map((item) => ({ ...item })),
            routingRules: normalized.routing_rules.map((item) => ({ ...item })),
            activeTemplateKey: '',
            editingRuleId: null,
        };
        return messageSettingsState;
    }

    function getMailTemplateByKey(templateKey) {
        const normalizedKey = String(templateKey || '').trim().toLowerCase();
        return messageSettingsState.mailTemplates.find((item) => String(item?.key || '').trim().toLowerCase() === normalizedKey) || null;
    }

    function mergeMailTemplateState(template) {
        if (!template || !template.key) return null;
        const normalizedKey = String(template.key || '').trim().toLowerCase();
        let mergedTemplate = null;
        messageSettingsState.mailTemplates = messageSettingsState.mailTemplates.map((item) => {
            if (String(item?.key || '').trim().toLowerCase() !== normalizedKey) return item;
            mergedTemplate = { ...item, ...template };
            return mergedTemplate;
        });
        if (!mergedTemplate) {
            mergedTemplate = { ...template };
            messageSettingsState.mailTemplates.push(mergedTemplate);
        }
        const nextData = normalizeMessageSettingsData(cache.messages?.data || {});
        let foundTemplate = false;
        nextData.mail_templates = (nextData.mail_templates || []).map((item) => {
            if (String(item?.key || '').trim().toLowerCase() !== normalizedKey) return item;
            foundTemplate = true;
return { ...item, ...mergedTemplate };
        });
        if (!foundTemplate) {
            nextData.mail_templates.push({ ...mergedTemplate });
        }
        cache.messages = { data: nextData, ts: Date.now() };
        return mergedTemplate;
    }

    function getEditingRoutingRule() {
        const targetId = Number(messageSettingsState.editingRuleId || 0);
        if (!targetId) return null;
        return messageSettingsState.routingRules.find((item) => Number(item?.id || 0) === targetId) || null;
    }

    function renderMessageSettings(container) {
        if (!container) return;
        container.innerHTML = `
            <div style="position: relative; padding-top: 0.5rem; overflow: visible;">
                ${TksUI.renderMessageTemplates(messageSettingsState, { editingRule: getEditingRoutingRule() })}
            </div>
        `;
    }

    function closeMailTemplateModal() {
        const modal = el('tks-template-editor-modal');
        if (modal) modal.remove();
        messageSettingsState.activeTemplateKey = '';
    }

    function closeAttachmentPreview() {
        const modal = el('tks-attachment-preview-modal');
        if (modal) modal.remove();
    }

    function openAttachmentPreview(ticketId, attachmentId, filename = '', contentType = '', sizeBytes = 0) {
        const targetTicketId = Number(ticketId || selectedTicketId || 0);
        const targetAttachmentId = Number(attachmentId || 0);
        if (!targetTicketId || !targetAttachmentId) {
            if (window.showToast) window.showToast('No se pudo abrir el adjunto seleccionado.', 'warning');
            return;
        }
        closeAttachmentPreview();
        document.body.insertAdjacentHTML(
            'beforeend',
            TksUI.renderAttachmentPreviewModal({
                ticketId: targetTicketId,
                attachmentId: targetAttachmentId,
                filename,
                content_type: contentType,
                size_bytes: Number(sizeBytes || 0),
            })
        );
        const modal = el('tks-attachment-preview-modal');
        if (modal) {
            modal.addEventListener('click', (event) => {
                if (event.target === modal) closeAttachmentPreview();
            });
        }
    }

    async function openMailTemplateModal(templateKey) {
        const normalizedKey = String(templateKey || '').trim().toLowerCase();
        const fallbackTemplate = getMailTemplateByKey(normalizedKey);
        if (!fallbackTemplate) {
            if (window.showToast) window.showToast('No se encontro la plantilla seleccionada.', 'warning');
            return;
        }
        let template = fallbackTemplate;
        try {
            const out = await TksApi.getMailTemplate(normalizedKey, { timeoutMs: 12000 });
            template = mergeMailTemplateState(out?.template || null) || fallbackTemplate;
        } catch (e) {
            if (window.showToast) {
                window.showToast(`No fue posible refrescar la plantilla. Se mostrara la version cargada: ${errorMessage(e)}`, 'warning');
            }
        }
        closeMailTemplateModal();
        messageSettingsState.activeTemplateKey = normalizedKey;
        document.body.insertAdjacentHTML('beforeend', TksUI.renderMailTemplateEditorModal(template));
        const modal = el('tks-template-editor-modal');
        if (modal) {
            modal.addEventListener('click', (event) => {
                if (event.target === modal) closeMailTemplateModal();
            });
        }
    }

    function escapeJsSingleQuoted(text) {
        if (typeof TksUI.escapeJsSingleQuoted === 'function') {
            return TksUI.escapeJsSingleQuoted(text);
        }
        return String(text == null ? '' : text)
            .replace(/\\/g, '\\\\')
            .replace(/'/g, "\\'")
            .replace(/\r/g, '\\r')
            .replace(/\n/g, '\\n')
            .replace(/<\/script/gi, '<\\/script');
    }

    function scopeAssignmentDataForSession(rawData) {
        const base = rawData || {};
        if (!sessionCtx.isScopedTech) {
            return base;
        }
        const me = normalizeUser(sessionCtx.user);
        const allTechs = Array.isArray(base.technicians) ? base.technicians : [];
        const mine = allTechs.filter((tech) => normalizeUser(tech?.username) === me);
return {
            ...base,
            technicians: mine,
            queue: [],
            scope: 'mine',
        };
    }

    function humanizeUsername(rawValue) {
        const raw = String(rawValue || '').trim();
        if (!raw) return '';
        const local = raw.includes('@') ? raw.split('@')[0] : raw;
        const clean = local.replace(/[._-]+/g, ' ').replace(/\s+/g, ' ').trim();
        if (!clean) return raw;
        return clean
            .split(' ')
            .filter(Boolean)
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join(' ');
    }

    function specialtyLabel(rawSpecialty) {
        const key = normalizeRole(rawSpecialty);
return {
            ops: 'Mesa',
            encargado_mesa: 'Encargado Mesa',
            redes: 'Redes',
            sistemas: 'Plataformas',
            implementaciones: 'Implementaciones',
            ejecucion: 'Ejecución',
            general: 'General',
            admin: 'Admin',
            finance: 'Finanzas',
            warehouse: 'Bodega',
            gerencia: 'Gerencia',
        }[key] || humanizeUsername(key);
    }

    function assigneeOptionLabel(item, options = {}) {
        const username = String(item?.username || '').trim();
        if (!username) return '';
        const roles = Array.isArray(item?.roles) ? item.roles.filter(Boolean) : [];
        const specialties = Array.isArray(item?.specialties) ? item.specialties.filter(Boolean) : [];
        const available = item?.isAvailable !== false;
        const includeAvailability = options.includeAvailability !== false;
        const explicitName = String(item?.display_name || item?.full_name || '').trim();
        let label = explicitName || humanizeUsername(username) || username;
        const capabilityKeys = roles.length > 0 ? roles : specialties;
        const capabilityLabels = [];
        capabilityKeys.forEach((specKey) => {
            const specLabel = specialtyLabel(specKey);
            if (specLabel && !capabilityLabels.includes(specLabel)) capabilityLabels.push(specLabel);
        });
        if (capabilityLabels.length > 0) {
            label += ` · ${capabilityLabels.join(' + ')}`;
        } else {
            label += ' · Sin rol técnico';
        }
        if (includeAvailability && !available) {
            label += ' · no disponible';
        }
        return label;
    }

    async function loadAssignableUsers(force = false) {
        const now = Date.now();
        if (!force && assigneeDirectoryCache.ts && (now - assigneeDirectoryCache.ts) < ASSIGNEE_CACHE_TTL_MS) {
            return assigneeDirectoryCache.items || [];
        }
        const out = await TksApi.listEspecialidades();
        const rows = Array.isArray(out?.items) ? out.items : [];
        const byUser = new Map();
        rows.forEach((row) => {
            const username = normalizeUser(row?.username);
            if (!username) return;
            const role = normalizeRole(row?.role);
            const secondaryRoles = normalizeRoles(row?.secondary_roles);
            const allRoles = normalizeRoles([role, ...secondaryRoles]);
            const specialty = normalizeRole(row?.specialty);
            if (allRoles.includes(ROLE_ADMIN) || specialty === ROLE_ADMIN) return;

            const current = byUser.get(username) || {
                username,
                role,
                roles: new Set(allRoles),
                display_name: String(row?.display_name || row?.full_name || '').trim() || humanizeUsername(username),
                specialties: new Set(),
                isAvailable: false,
            };
            allRoles.forEach((roleKey) => {
                if (roleKey) current.roles.add(roleKey);
            });
            if (!current.display_name) {
                const rowName = String(row?.display_name || row?.full_name || '').trim();
                current.display_name = rowName || humanizeUsername(username);
            }
            if (specialty && specialty !== ROLE_ADMIN) {
                current.specialties.add(specialty);
            }
            const isAvailable = Number(row?.is_available ?? 1) !== 0;
            current.isAvailable = current.isAvailable || isAvailable;
            byUser.set(username, current);
        });

        const users = Array.from(byUser.values()).map((entry) => ({
            username: entry.username,
            role: entry.role,
            roles: Array.from(entry.roles).sort((a, b) => a.localeCompare(b, 'es')),
            display_name: entry.display_name,
            isAvailable: entry.isAvailable,
            specialties: Array.from(entry.specialties).sort((a, b) => a.localeCompare(b, 'es')),
        })).sort((a, b) => {
            if (a.isAvailable !== b.isAvailable) return a.isAvailable ? -1 : 1;
            return String(a.display_name || a.username || '').localeCompare(String(b.display_name || b.username || ''), 'es');
        });

        assigneeDirectoryCache = { items: users, ts: now };
        return users;
    }

    function resetListFilters() {
        filters = {
            status: null,
            q: '',
            categoria: null,
            severidad: null,
            asignado_a: sessionCtx.isScopedTech ? (sessionCtx.user || null) : null,
        };
    }

    function stopDraftHeartbeat() {
        if (draftHeartbeatIntervalId) {
            clearInterval(draftHeartbeatIntervalId);
            draftHeartbeatIntervalId = null;
        }
    }

    function stopAutoProgressTimer() {
        if (autoProgressTimeoutId) {
            clearTimeout(autoProgressTimeoutId);
            autoProgressTimeoutId = null;
        }
    }

    function stopResueltoCountdown() {
        if (resueltoCountdownIntervalId) {
            clearInterval(resueltoCountdownIntervalId);
            resueltoCountdownIntervalId = null;
        }
    }

    function formatResueltoCountdown(msLike) {
        const safeMs = Math.max(0, Number(msLike || 0));
        const totalSeconds = Math.floor(safeMs / 1000);
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        if (days > 0) return `${days}d ${hours}h ${minutes}m`;
        if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
        if (minutes > 0) return `${minutes}m ${seconds}s`;
        return `${seconds}s`;
    }

    function updateResueltoCountdownLabel() {
        const countdownEl = el('tks-resuelto-countdown');
        if (!countdownEl) return false;
        const rawDeadline = String(countdownEl.dataset.deadline || '').trim();
        if (!rawDeadline) return false;
        const deadlineTs = Date.parse(rawDeadline);
        if (!Number.isFinite(deadlineTs)) return false;

        const remainingMs = deadlineTs - Date.now();
        if (remainingMs <= 0) {
            countdownEl.textContent = 'Cierre automático pendiente (se aplicará pronto)';
            countdownEl.classList.add('is-overdue');
            return true;
        }

        countdownEl.textContent = `Cierre automático en ${formatResueltoCountdown(remainingMs)}`;
        countdownEl.classList.remove('is-overdue');
        return true;
    }

    function startResueltoCountdown() {
        stopResueltoCountdown();
        if (!updateResueltoCountdownLabel()) return;
        resueltoCountdownIntervalId = setInterval(() => {
            if (currentTab !== 'lista' || !selectedTicketId) {
                stopResueltoCountdown();
                return;
            }
            if (!updateResueltoCountdownLabel()) {
                stopResueltoCountdown();
            }
        }, 1000);
    }

    function scrollTimelineToBottom() {
        const feed = el('tks-unified-feed');
        if (!feed) return;
        const jumpBottom = () => {
            feed.scrollTop = feed.scrollHeight;
        };
        jumpBottom();
        requestAnimationFrame(jumpBottom);
        setTimeout(jumpBottom, 40);
    }

    function resetDraftState() {
        stopAutoProgressTimer();
        stopResueltoCountdown();
        stopDraftHeartbeat();
        draftLockToken = '';
        currentDraftSnapshot = null;
        currentDraftMeta = {
            canEdit: false,
            blockedReason: '',
            heartbeatSeconds: 60,
        };
        currentWorkflow = null;
        detailActiveTab = 'note';
    }

    function scheduleAutoProgress(ticket, permissions, workflow = {}) {
        stopAutoProgressTimer();
        const ticketId = Number(ticket?.id || 0);
        if (!ticketId) return;
        if (!permissions || permissions.isAdmin || !permissions.isTech || !permissions.canParticipate) return;

        const currentSubestado = String(ticket?.subestado || workflow?.ticket?.subestado || '')
            .trim()
            .toLowerCase();
        if (currentSubestado !== 'asignado') return;

        const allowedNext = Array.isArray(workflow?.allowed_next)
            ? workflow.allowed_next.map((v) => String(v || '').trim().toLowerCase()).filter(Boolean)
            : [];
        if (!allowedNext.includes('en_progreso')) return;

        autoProgressTimeoutId = setTimeout(async () => {
            autoProgressTimeoutId = null;
            if (currentTab !== 'lista') return;
            if (!selectedTicketId || Number(selectedTicketId) !== ticketId) return;
            const liveSubestado = String(selectedTicket?.subestado || '').trim().toLowerCase();
            if (liveSubestado && liveSubestado !== 'asignado') return;
            await transitionSubestado(ticketId, 'en_progreso', { autoAdvance: true, silentError: true });
        }, AUTO_PROGRESS_DELAY_MS);
    }

    function normalizeRole(role) {
        return String(role || '').trim().toLowerCase();
    }

    function normalizeRoles(rawRoles, fallbackRole = null) {
        const out = [];
        const append = (value) => {
            const role = normalizeRole(value);
            if (!role) return;
            if (out.includes(role)) return;
            out.push(role);
        };

        if (Array.isArray(rawRoles)) {
            rawRoles.forEach(append);
        } else if (typeof rawRoles === 'string') {
            const text = rawRoles.trim();
            if (text.startsWith('[') && text.endsWith(']')) {
                try {
                    const parsed = JSON.parse(text);
                    if (Array.isArray(parsed)) parsed.forEach(append);
                } catch (e) {
                    text.split(',').forEach(append);
                }
            } else if (text) {
                text.split(',').forEach(append);
            }
        }

        append(fallbackRole);
        return out;
    }

    function normalizeUser(user) {
        return String(user || '').trim().toLowerCase();
    }

    function isTrashedTicket(ticket) {
        const raw = ticket?.is_trashed;
        if (typeof raw === 'boolean') return raw;
        if (typeof raw === 'number') return raw !== 0;
        return ['1', 'true', 't', 'yes', 'y', 'si', 'sí'].includes(String(raw || '').trim().toLowerCase());
    }

    function parseNotifyEmails(ticket) {
        const list = Array.isArray(ticket?.notify_emails_list)
            ? ticket.notify_emails_list
            : String(ticket?.notify_emails || '')
                .split(/[,\n;]+/)
                .map((value) => String(value || '').trim())
                .filter(Boolean);
        return Array.from(new Set(list));
    }

    function buildReplySubject(ticket) {
        const code = String(ticket?.codigo || `Ticket #${Number(ticket?.id || 0)}`).trim();
        const title = String(ticket?.titulo || '').trim();
        const base = title ? `[${code}] ${title}` : code;
        return /^re:/i.test(base) ? base : `Re: ${base}`;
    }

    function buildReplySnapshot(ticket) {
return {
            to_addr: String(ticket?.origen_email || '').trim(),
            cc_addrs: parseNotifyEmails(ticket).join(', '),
            bcc_addrs: '',
            subject: buildReplySubject(ticket),
            body_text: '',
        };
    }

    function ticketAllowsReplyStatus(ticket) {
        if (isTrashedTicket(ticket)) return false;
        const status = String(ticket?.estado || '').trim().toLowerCase();
        return status === 'abierto' || status === 'en_progreso';
    }

    function replyBlockedReason(ticket, permissions) {
        if (permissions?.canParticipate !== true) {
            return String(permissions?.blockedReason || '').trim();
        }
        if (isTrashedTicket(ticket)) {
            return 'El ticket está en papelera. Restáuralo para volver a intervenir.';
        }
        const status = String(ticket?.estado || '').trim().toLowerCase();
        if (!ticketAllowsReplyStatus(ticket)) {
            if (status === 'resuelto') {
                return 'El ticket está resuelto. Si necesitas escribir al cliente, vuelve el ticket a una etapa activa.';
            }
            if (status === 'cerrado') {
                return 'El ticket está cerrado. Reábrelo para responder al cliente.';
            }
            return 'El estado actual del ticket no permite responder al cliente.';
        }
        return '';
    }

    function isAdjacentStatusMove(sourceStatus, targetStatus) {
        const source = String(sourceStatus || '').trim().toLowerCase();
        const target = String(targetStatus || '').trim().toLowerCase();
        if (!source || !target || source === target) return true;
        const sourceIndex = MAIN_STATUS_SEQUENCE.indexOf(source);
        const targetIndex = MAIN_STATUS_SEQUENCE.indexOf(target);
        if (sourceIndex < 0 || targetIndex < 0) return false;
        return Math.abs(targetIndex - sourceIndex) === 1;
    }

    function deriveRoleCapabilities(rawRoles, fallbackRole = '') {
        const roles = normalizeRoles(rawRoles, fallbackRole);
        const role = roles[0] || normalizeRole(fallbackRole);
        const isAdmin = roles.some((item) => ROLE_MANAGEMENT.has(item));
        const isTech = roles.some((item) => ROLE_TECH.has(item));
        const isScopedTech = isTech && !isAdmin;
        const canViewOps = roles.some((item) => ROLE_OPS_READ.has(item));
        const canManageMessages = roles.some((item) => ROLE_MANAGEMENT.has(item));
        const canWrite = isAdmin || isTech;
return {
            role,
            roles,
            canWrite,
            canCreate: canWrite,
            canViewOps,
            canManageMessages,
            isTech,
            isScopedTech,
            isAdmin,
        };
    }

    function buildSessionContext(sessionPayload = {}) {
        const user = normalizeUser(sessionPayload.user);
return {
            user,
            ...deriveRoleCapabilities(sessionPayload.roles, sessionPayload.role),
        };
    }

    async function loadSessionContext() {
        try {
            const data = await fetchApi('/api/sesion');
            if (data && data.ok) {
                sessionCtx = buildSessionContext(data);
                return;
            }
        } catch (e) {
            // silent fallback
        }
        sessionCtx = buildSessionContext({});
    }

    function applyRoleView() {
        document.querySelectorAll('.tks-tab-btn').forEach(btn => {
            const tabKey = String(btn.dataset.tab || '').trim();
            if (tabKey === 'ops') {
                if (sessionCtx.canViewOps) {
                    btn.style.removeProperty('display');
                    btn.hidden = false;
                    return;
                }
                btn.remove();
                return;
            }
            if (tabKey === 'messages') {
                if (sessionCtx.canManageMessages) {
                    btn.style.removeProperty('display');
                    btn.hidden = false;
                    return;
                }
                btn.remove();
            }
        });
        const createBtn = el('tks-create-btn');
        if (createBtn) {
            createBtn.style.display = sessionCtx.canCreate ? '' : 'none';
        }
        const viewBadge = el('tks-view-badge');
        if (viewBadge) {
            const roleLabel = (sessionCtx.roles && sessionCtx.roles.length)
                ? sessionCtx.roles.map((r) => String(r || '').toUpperCase()).join(' + ')
                : (sessionCtx.role ? sessionCtx.role.toUpperCase() : 'LECTURA');
            const viewLabel = sessionCtx.role === ROLE_MESA_MANAGER
                ? 'Encargado Mesa'
                : sessionCtx.role === ROLE_GERENCIA
                    ? 'Gerencia (Lectura)'
                    : sessionCtx.isAdmin
                        ? 'Admin Gestión'
                        : sessionCtx.isTech
                            ? 'Técnico'
                            : 'Solo Lectura';
            viewBadge.textContent = `${viewLabel} · ${roleLabel}`;
        }
        if (sessionCtx.isScopedTech) {
            filters.asignado_a = sessionCtx.user || null;
        }
    }

    function buildParticipationBlockedReason({ role, isAdmin, isTech, isTrashed, isUnassigned, isMine, assigneeLabel = '' }) {
        if (isTrashed) {
            return 'Ticket en papelera: solo se permite restaurarlo.';
        }
        if (role === ROLE_GERENCIA) {
            return 'Gerencia: vista solo lectura en ticketera.';
        }
        if (isAdmin) {
            return 'Admin: puede gestionar y dejar nota interna, pero no responder correos.';
        }
        if (isTech && isUnassigned) {
            return 'Ticket sin asignar: toma el ticket para intervenir.';
        }
        if (isTech && assigneeLabel && !isMine) {
            return `Ticket asignado a ${assigneeLabel}.`;
        }
        return '';
    }

    function deriveTicketAccessContext(ticket) {
        const me = normalizeUser(sessionCtx.user);
        const assignee = normalizeUser(ticket?.asignado_a);
        const isTrashed = isTrashedTicket(ticket);
        const isUnassigned = !assignee;
        const isMine = !!assignee && assignee === me;
        const roleCaps = deriveRoleCapabilities(sessionCtx.roles, sessionCtx.role);
        const { role, roles, isAdmin, isTech } = roleCaps;
        const isDispatcher = isAdmin || roles.some((r) => ROLE_DISPATCH.has(r));
return {
            role,
            roles,
            isAdmin,
            isTech,
            isDispatcher,
            isTrashed,
            isUnassigned,
            isMine,
            assigneeLabel: ticket?.asignado_a || '',
        };
    }

    function deriveTicketActionPermissions(access, ticket) {
        const {
            isAdmin,
            isTech,
            isDispatcher,
            isTrashed,
            isUnassigned,
            isMine,
        } = access;
        const canReassign = isAdmin;
        const canTrash = isAdmin && !isTrashed;
        const canRestore = isAdmin && isTrashed;
        const canAssignTicket = !isTrashed && isDispatcher && (isAdmin || isMine || isUnassigned);
        const canClaim = !isTrashed && isTech && !isAdmin && isUnassigned;
        const canChangeStatus = !isTrashed && (isAdmin || (isTech && isMine));
        const canAddInternalNote = !isTrashed && (isAdmin || (isTech && isMine));
        const canParticipate = !isTrashed && isTech && isMine;
        const canReplyToClient = canParticipate && ticketAllowsReplyStatus(ticket);
return {
            canReassign,
            canAssignTicket,
            canClaim,
            canChangeStatus,
            canAddInternalNote,
            canParticipate,
            canReplyToClient,
            canTrash,
            canRestore,
        };
    }

    function ticketPermissions(ticket) {
        const access = deriveTicketAccessContext(ticket);
        const {
            role,
            isAdmin,
            isTech,
            isTrashed,
            isUnassigned,
            isMine,
            assigneeLabel,
        } = access;
        const actionPermissions = deriveTicketActionPermissions(access, ticket);
        const blockedReason = actionPermissions.canParticipate
            ? ''
            : buildParticipationBlockedReason({
                role,
                isAdmin,
                isTech,
                isTrashed,
                isUnassigned,
                isMine,
                assigneeLabel,
            });
return {
            ...actionPermissions,
            blockedReason,
            isAdmin,
            isTech,
            isTrashed,
            role,
        };
    }

    function scopeKanbanDataForSession(rawKanban) {
        const kanban = rawKanban || {};
        if (!sessionCtx.isScopedTech) {
            return kanban;
        }
        const me = normalizeUser(sessionCtx.user);
        const out = {
            abierto: [],
            en_progreso: [],
            resuelto: [],
            cerrado: [],
        };
        Object.keys(out).forEach((estado) => {
            const items = Array.isArray(kanban?.[estado]) ? kanban[estado] : [];
            out[estado] = items.filter((ticket) => normalizeUser(ticket?.asignado_a) === me);
        });
        return out;
    }

    // ---- INIT ----
    async function init() {
        if (isInitialized) return;
        isInitialized = true;

        await loadSessionContext();
        bindTabs();
        applyRoleView();
        const initialTab = 'dashboard';
        loadTab(initialTab);
        pollNotifications();
        if (pollIntervalId) clearInterval(pollIntervalId);
        pollIntervalId = setInterval(pollNotifications, 45000);

        // Deep Link: Abrir ticket si viene en query vars
        const urlParams = new URLSearchParams(window.location.search);
        const tid = urlParams.get('ticket_id');
        if (tid) {
            // Ir a pestaña lista y abrir detalle tras breve delay
            loadTab('lista');
            setTimeout(() => {
                // Ensure UI is ready
                if (el('tks-items-list')) {
                    openDetail(parseInt(tid));
                }
            }, 500);
        }
    }

    // ---- TABS ----
    function bindTabs() {
        document.querySelectorAll('.tks-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                loadTab(btn.dataset.tab);
            });
        });
    }

    function loadTab(tab, options = {}) {
        if (tab === 'ops' && !sessionCtx.canViewOps) {
            tab = 'lista';
        }
        if (tab === 'messages' && !sessionCtx.canManageMessages) {
            tab = 'lista';
        }
        const force = options.force === true;
        const content = el('tks-content');
        if (!force && tab === currentTab && content && content.dataset.loadedTab === tab) {
            return;
        }
        if (panelAbortController) {
            panelAbortController.abort();
            panelAbortController = null;
        }
        if (tab !== 'lista' && listAbortController) {
            listAbortController.abort();
            listAbortController = null;
        }
        if (tab !== 'lista' && detailAbortController) {
            detailAbortController.abort();
            detailAbortController = null;
        }
        if (tab !== 'lista') {
            selectedTicketId = null;
            selectedTicket = null;
            resetDraftState();
            stopAutoProgressTimer();
            ['tks-draft-review-modal', 'tks-reply-review-modal', 'tks-template-editor-modal'].forEach((modalId) => {
                const modal = el(modalId);
                if (modal) modal.remove();
            });
        }

        currentTab = tab;
        const token = ++tabRequestToken;
        if (tab !== 'lista' && searchTimeout) {
            clearTimeout(searchTimeout);
            searchTimeout = null;
        }
        document.querySelectorAll('.tks-tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));

        if (content) {
            content.dataset.loadedTab = tab;
        }
        if (tab === 'dashboard') loadDashboard(content, token);
        else if (tab === 'asignacion') loadAssignmentTimeline(content, token);
        else if (tab === 'lista') loadList(content, token);
        else if (tab === 'kanban') loadKanban(content, token);
        else if (tab === 'messages') loadMessageTemplates(content, token);
        else if (tab === 'ops') loadOps(content, token);
        else if (tab === 'reportes') loadArchivosReportes(content, token);
    }

    // ---- DASHBOARD ----
    async function loadDashboard(container, token) {
        if (!container) return;
        if (isFresh(cache.dashboard)) {
            const scopedAssignment = scopeAssignmentDataForSession(cache.dashboard.data?.assignment || null);
            container.innerHTML = TksUI.renderDashboard(
                cache.dashboard.data?.stats || {},
                scopedAssignment
            );
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:200px;margin:1.5rem"></div></div>';
        try {
            const [stats, assignmentRaw] = await Promise.all([
                TksApi.getStats({ signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getAssignmentTimeline(
                    { window_h: 72, limit: 500 },
                    { signal: controller.signal, timeoutMs: 12000 }
                ).catch(() => null),
            ]);
            const assignment = scopeAssignmentDataForSession(assignmentRaw);
            if (token !== tabRequestToken || currentTab !== 'dashboard') return;
            cache.dashboard = { data: { stats, assignment }, ts: Date.now() };
            if (assignment) {
                cache.assignment = { data: assignment, ts: Date.now() };
            }
            container.innerHTML = TksUI.renderDashboard(stats, assignment);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'dashboard') return;
            container.innerHTML = `<div class="tks-dashboard"><p style="color:red">Error cargando stats: ${errorHtml(e)}</p></div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    // ---- ASIGNACIÓN ----
    async function loadAssignmentTimeline(container, token) {
        if (!container) return;
        if (isFresh(cache.assignment)) {
            container.innerHTML = TksUI.renderAssignmentTimeline(scopeAssignmentDataForSession(cache.assignment.data));
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:240px;margin:1.5rem"></div></div>';
        try {
            const rawData = await TksApi.getAssignmentTimeline(
                { window_h: 72, limit: 500 },
                { signal: controller.signal, timeoutMs: 12000 }
            );
            const data = scopeAssignmentDataForSession(rawData);
            if (token !== tabRequestToken || currentTab !== 'asignacion') return;
            cache.assignment = { data, ts: Date.now() };
            container.innerHTML = TksUI.renderAssignmentTimeline(data);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'asignacion') return;
            container.innerHTML = `<div class="tks-dashboard"><p style="color:red">Error cargando asignación: ${errorHtml(e)}</p></div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    // ---- LISTA ----
    async function loadList(container, token) {
        if (!container) return;
        resetDraftState();
        if (sessionCtx.isScopedTech) {
            filters.asignado_a = sessionCtx.user || null;
            filters.q = '';
            filters.status = null;
            filters.categoria = null;
            filters.severidad = null;
        }
        const showListFilters = !sessionCtx.isScopedTech;
        const toolbarHtml = showListFilters
            ? `
                <div class="tks-toolbar">
                    <input class="tks-search" id="tks-search-input" placeholder="🔍 Buscar tickets por título, código o cliente..." value="${filters.q}">
                    <button class="tks-btn tks-btn-ghost tks-btn-icon" onclick="TksMain.refreshList()" title="Recargar"><i class="fas fa-sync-alt"></i></button>
                </div>
            `
            : `
                <div class="tks-toolbar">
                    <div class="tks-toolbar-note">
                        Mostrando solo tickets asignados a tu usuario
                    </div>
                    <button class="tks-btn tks-btn-ghost tks-btn-icon" onclick="TksMain.refreshList()" title="Recargar"><i class="fas fa-sync-alt"></i></button>
                </div>
            `;
        const statusFiltersHtml = showListFilters
            ? `
                <div class="tks-filter-row tks-filter-row--status" id="tks-filters">
                    <button class="tks-filter-chip ${!filters.status ? 'active' : ''}" data-filter-status="">Todos</button>
                    <button class="tks-filter-chip ${filters.status === 'abierto' ? 'active' : ''}" data-filter-status="abierto">Abiertos</button>
                    <button class="tks-filter-chip ${filters.status === 'en_progreso' ? 'active' : ''}" data-filter-status="en_progreso">En Progreso</button>
                    <button class="tks-filter-chip ${filters.status === 'resuelto' ? 'active' : ''}" data-filter-status="resuelto">Resueltos</button>
                    <button class="tks-filter-chip ${filters.status === 'papelera' ? 'active' : ''}" data-filter-status="papelera">Papelera</button>
                </div>
            `
            : '';
        const categoryFiltersHtml = showListFilters
            ? `
                <div class="tks-filter-row" id="tks-cat-filters">
                    <button class="tks-filter-chip ${!filters.categoria ? 'active' : ''}" data-filter-cat="">Todas las áreas</button>
                    <button class="tks-filter-chip ${filters.categoria === 'redes' ? 'active' : ''}" data-filter-cat="redes">🌐 Redes</button>
                    <button class="tks-filter-chip ${filters.categoria === 'sistemas' ? 'active' : ''}" data-filter-cat="sistemas">💻 Sistemas</button>
                    <button class="tks-filter-chip ${filters.categoria === 'ejecucion' ? 'active' : ''}" data-filter-cat="ejecucion">🔧 Ejecución</button>
                    <button class="tks-filter-chip ${filters.categoria === 'admin' ? 'active' : ''}" data-filter-cat="admin">📋 Admin</button>
                </div>
            `
            : '';
        container.innerHTML = `
        <div class="tks-list-layout">
            <div class="tks-list-panel" id="tks-list-panel">
                ${toolbarHtml}
                ${statusFiltersHtml}
                ${categoryFiltersHtml}
                <div class="tks-items-list" id="tks-items-list">
                    <div class="tks-skeleton tks-list-skeleton"></div>
                    <div class="tks-skeleton tks-list-skeleton"></div>
                    <div class="tks-skeleton tks-list-skeleton"></div>
                </div>
            </div>

            <div class="tks-full-detail-view" id="tks-detail-panel">
                <div class="tks-detail-empty"><span>Cargando ticket...</span></div>
            </div>
        </div>`;

        // Bind search
        const searchInput = el('tks-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    filters.q = searchInput.value.trim();
                    refreshList(token);
                }, 300);
            });
        }

        // Bind status filters
        const statusFilters = el('tks-filters');
        if (statusFilters) {
            statusFilters.querySelectorAll('.tks-filter-chip').forEach(chip => {
                chip.addEventListener('click', () => {
                    filters.status = chip.dataset.filterStatus || null;
                    statusFilters.querySelectorAll('.tks-filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    refreshList(token);
                });
            });
        }

        // Bind category filters
        const categoryFilters = el('tks-cat-filters');
        if (categoryFilters) {
            categoryFilters.querySelectorAll('.tks-filter-chip').forEach(chip => {
                chip.addEventListener('click', () => {
                    filters.categoria = chip.dataset.filterCat || null;
                    categoryFilters.querySelectorAll('.tks-filter-chip').forEach(c => c.classList.remove('active'));
                    chip.classList.add('active');
                    refreshList(token);
                });
            });
        }

        refreshList(token);
    }

    function renderListItems(listEl, items) {
        if (!items || items.length === 0) {
            listEl.innerHTML = '<div class="tks-list-empty">Sin tickets</div>';
            return;
        }

        // Usamos renderTicketTable en lugar de map(renderTicketItem)
        listEl.innerHTML = TksUI.renderTicketTable(items);

        // Bind events to table rows
        listEl.querySelectorAll('.tks-row').forEach(row => {
            row.addEventListener('click', (e) => {
                // Evitar si click en botón de acción (si hubiera)
                if (e.target.closest('button')) return;

                listEl.querySelectorAll('.tks-row').forEach(r => r.classList.remove('active'));
                row.classList.add('active');
                openDetail(parseInt(row.dataset.id));
            });
        });

        if (selectedTicketId) {
            const sel = listEl.querySelector(`.tks-row[data-id="${selectedTicketId}"]`);
            if (sel) sel.classList.add('active');
        }
    }

    async function refreshList(token = tabRequestToken) {
        const listEl = el('tks-items-list');
        if (!listEl || currentTab !== 'lista') return;
        const rawFilters = { ...filters, limit: DEFAULT_LIST_LIMIT };
        if (sessionCtx.isScopedTech) {
            rawFilters.asignado_a = sessionCtx.user || null;
            rawFilters.q = '';
            rawFilters.status = null;
            rawFilters.categoria = null;
            rawFilters.severidad = null;
        }
        const cacheKey = JSON.stringify(rawFilters);
        const listFilters = { ...rawFilters };
        const filterUnassigned = listFilters.asignado_a === '__unassigned__';
        if (filterUnassigned) {
            listFilters.asignado_a = null;
        }
        const cached = cache.list.get(cacheKey);
        if (isFresh(cached)) {
            renderListItems(listEl, cached.items);
            return;
        }

        const reqToken = ++listRequestToken;
        if (listAbortController) listAbortController.abort();
        const controller = new AbortController();
        listAbortController = controller;

        try {
            const data = await TksApi.listTickets(listFilters, { signal: controller.signal, timeoutMs: 10000 });
            if (token !== tabRequestToken || reqToken !== listRequestToken || currentTab !== 'lista') return;

            let items = data.items || [];
            if (filterUnassigned) {
                items = items.filter((t) => !String(t?.asignado_a || '').trim());
            }
            cache.list.set(cacheKey, { items, ts: Date.now() });
            if (cache.list.size > 20) {
                const latest = cache.list.get(cacheKey);
                cache.list.clear();
                cache.list.set(cacheKey, latest);
            }
            renderListItems(listEl, items);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || reqToken !== listRequestToken || currentTab !== 'lista') return;
            listEl.innerHTML = `<div class="tks-list-error">Error: ${errorHtml(e)}</div>`;
        } finally {
            if (listAbortController === controller) {
                listAbortController = null;
            }
        }
    }

    async function heartbeatDraftLock(ticketId) { }

    function startDraftHeartbeat(ticketId, heartbeatSeconds = 60) {
        stopDraftHeartbeat();
    }

    // ---- DETAIL ----
    function getCurrentDraftInputs() {
return {
            toInput: el('tks-draft-to'),
            ccInput: el('tks-draft-cc'),
            bccInput: el('tks-draft-bcc'),
            subjectInput: el('tks-draft-subject'),
            bodyInput: el('tks-draft-body'),
            fileInput: el('tks-draft-files'),
        };
    }

    function hasDraftFieldChanges(inputs, snapshot = {}) {
        const currentTo = String(inputs.toInput?.value || '').trim();
        const currentCc = String(inputs.ccInput?.value || '').trim();
        const currentBcc = String(inputs.bccInput?.value || '').trim();
        const currentSubject = String(inputs.subjectInput?.value || '').trim();
        const currentBody = String(inputs.bodyInput?.value || '');
        const snapTo = String(snapshot.to_addr || '').trim();
        const snapCc = String(snapshot.cc_addrs || '').trim();
        const snapBcc = String(snapshot.bcc_addrs || '').trim();
        const snapSubject = String(snapshot.subject || '').trim();
        const snapBody = String(snapshot.body_text || '');
        return (
            currentTo !== snapTo
            || currentCc !== snapCc
            || currentBcc !== snapBcc
            || currentSubject !== snapSubject
            || currentBody !== snapBody
        );
    }

    function hasPendingDetailChanges() {
        const noteInput = el('tks-note-input');
        if (noteInput && String(noteInput.value || '').trim()) {
            return true;
        }

        const inputs = getCurrentDraftInputs();
        if (inputs.fileInput && inputs.fileInput.files && inputs.fileInput.files.length > 0) {
            return true;
        }

        if (inputs.toInput || inputs.ccInput || inputs.bccInput || inputs.subjectInput || inputs.bodyInput) {
            return hasDraftFieldChanges(inputs, currentDraftSnapshot || {});
        }

        return false;
    }

    function resetDetailSelectionState() {
        stopAutoProgressTimer();
        resetDraftState();
        selectedTicketId = null;
        selectedTicket = null;
    }

    function clearDetailUiState() {
        const layout = document.querySelector('.tks-list-layout');
        if (layout) layout.classList.remove('detail-open');
        const panel = el('tks-detail-panel');
        if (panel) {
            panel.style.display = 'none';
            panel.innerHTML = '<div class="tks-detail-empty"><span>Selecciona un ticket</span></div>';
        }
        ['tks-draft-review-modal', 'tks-reply-review-modal', 'tks-template-editor-modal', 'tks-attachment-preview-modal'].forEach((modalId) => {
            const modal = el(modalId);
            if (modal) modal.remove();
        });
        const listPanel = el('tks-list-panel');
        if (listPanel) listPanel.style.display = '';
        document.querySelectorAll('.tks-row.active').forEach(r => r.classList.remove('active'));
    }

    function closeDetail(options = {}) {
        const silent = options.silent === true;
        const force = options.force === true;
        if (!force && !silent && currentTab === 'lista' && hasPendingDetailChanges()) {
            const ok = confirm('Hay cambios sin terminar en este ticket. ¿Cerrar de todas formas?');
            if (!ok) return;
        }
        if (detailAbortController) {
            detailAbortController.abort();
            detailAbortController = null;
        }
        clearDetailUiState();
        resetDetailSelectionState();
        if (!silent && currentTab === 'lista') {
            resetListFilters();
            loadTab('lista', { force: true });
        }
    }

    function renderDetailLoadingState(panel) {
        if (!panel) return;
        panel.innerHTML = `
            <div class="tks-detail-header">
                <button class="tks-btn-icon-sm tks-detail-close" onclick="TksMain.closeDetail()" title="Volver a la lista"><i class="fas fa-times"></i></button>
                <div class="tks-skeleton" style="height:30px;width:60%"></div>
            </div>
            <div style="padding:2rem"><div class="tks-loading-spinner">Cargando ticket...</div></div>
        `;
    }

    async function fetchDetailBundle(ticketId, options = {}) {
        const signal = options.signal;
        const timeoutMs = options.timeoutMs || 10000;
        const workflowPromise = TksApi.getTicketWorkflow(ticketId, { signal, timeoutMs })
            .catch((err) => {
                if (err?.name === 'AbortError') throw err;
return { allowed_next: [] };
            });
        const [ticket, eventosData, emailsData, attachmentsData, workflowData] = await Promise.all([
            TksApi.getTicket(ticketId, { signal, timeoutMs }),
            TksApi.getEventos(ticketId, { signal, timeoutMs }),
            TksApi.getTicketEmails(ticketId, { signal, timeoutMs }),
            TksApi.getTicketAttachments(ticketId, { signal, timeoutMs }),
            workflowPromise,
        ]);
return {
            ticket,
            eventos: eventosData.items || [],
            emails: emailsData.items || [],
            attachments: attachmentsData.items || [],
            workflow: workflowData || {},
        };
    }

    function buildDetailRenderState(ticket, workflow) {
        const permissions = ticketPermissions(ticket);
        currentWorkflow = workflow || {};
        currentDraftSnapshot = buildReplySnapshot(ticket);
        currentDraftMeta = {
            canEdit: permissions.canReplyToClient === true,
            blockedReason: replyBlockedReason(ticket, permissions),
            heartbeatSeconds: 60,
        };
        stopDraftHeartbeat();
return {
            permissions,
            draft: currentDraftSnapshot,
            draftMeta: currentDraftMeta,
        };
    }

    function renderDetailContent(panel, detailData, renderState) {
        if (!panel) return;
        const { ticket, eventos, emails, attachments, workflow } = detailData;
        const { permissions, draft, draftMeta } = renderState;
        panel.innerHTML = TksUI.renderDetail(
            ticket,
            eventos,
            emails,
            attachments,
            {
                ...permissions,
                currentUser: sessionCtx.user,
                currentRole: sessionCtx.role,
                composerMode: detailActiveTab,
                draft,
                draftMeta,
                hasDraftLockToken: !!draftLockToken,
                workflow,
            }
        );
    }

    function afterDetailRender(panel, ticket, permissions, options = {}) {
        hydrateAssigneePicker(ticket, permissions);
        bindReplyComposer();
        if (options.scrollToBottom) {
            scrollTimelineToBottom();
        }
        switchComposerMode(detailActiveTab);
        scheduleAutoProgress(ticket, permissions, currentWorkflow);
        startResueltoCountdown();
    }

    function prepareDetailView(ticketId, options = {}) {
        const preserveTab = options.preserveTab === true;
        const previousTicketId = selectedTicketId;
        if (previousTicketId && Number(previousTicketId) !== Number(ticketId)) {
            resetDraftState();
        }
        stopAutoProgressTimer();
        stopResueltoCountdown();
        selectedTicketId = ticketId;
        if (!preserveTab) {
            detailActiveTab = 'note';
        }

        const panel = el('tks-detail-panel');
        const layout = document.querySelector('.tks-list-layout');
        const listPanel = el('tks-list-panel');
        if (!panel) {
return { panel: null, reqToken: detailRequestToken };
        }

        if (layout) layout.classList.add('detail-open');
        if (listPanel) listPanel.style.display = 'none';
        panel.style.display = 'flex';

        if (detailAbortController) detailAbortController.abort();
        const controller = new AbortController();
        detailAbortController = controller;
        renderDetailLoadingState(panel);
return {
            panel,
            controller,
            reqToken: ++detailRequestToken,
        };
    }

    async function openDetail(ticketId, options = {}) {
        const detailView = prepareDetailView(ticketId, options);
        const { panel, controller, reqToken } = detailView;
        if (!panel || !controller) return;

        try {
            const detailData = await fetchDetailBundle(ticketId, { signal: controller.signal, timeoutMs: 10000 });
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId) return;
            selectedTicket = detailData.ticket;
            const renderState = buildDetailRenderState(detailData.ticket, detailData.workflow);
            renderDetailContent(panel, detailData, renderState);
            afterDetailRender(panel, detailData.ticket, renderState.permissions, { scrollToBottom: true });
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId) return;
            panel.innerHTML = `<div class="tks-detail-empty"><span style="color:red">Error: ${errorHtml(e)}</span></div>`;
        } finally {
            if (detailAbortController === controller) {
                detailAbortController = null;
            }
        }
    }

    /**
     * Refresca solo la línea de tiempo (eventos y correos) de un ticket abierto.
     * Útil para capturar cambios asíncronos en el backend (ej: correos de notificación).
     */
    async function refreshDetailFeed(ticketId) {
        if (!ticketId || currentTab !== 'lista' || Number(selectedTicketId) !== Number(ticketId)) return;

        try {
            const detailData = await fetchDetailBundle(ticketId, { timeoutMs: 5000 });
            if (Number(selectedTicketId) !== Number(ticketId)) return;
            selectedTicket = detailData.ticket;
            const renderState = buildDetailRenderState(detailData.ticket, detailData.workflow || currentWorkflow || {});
            const panel = el('tks-detail-panel');
            renderDetailContent(panel, detailData, renderState);
            afterDetailRender(panel, detailData.ticket, renderState.permissions, { scrollToBottom: false });
        } catch (e) {
            console.warn('[refreshDetailFeed] Failed:', e);
        }
    }

    // ---- ACTIONS ----
    function scheduleDetailFeedRefresh(ticketId, delayMs = 3000) {
        setTimeout(() => refreshDetailFeed(ticketId), delayMs);
    }

    async function changeStatus(ticketId, newStatus) {
        const perms = getSelectedTicketPermissions(ticketId);
        if (perms && !perms.canChangeStatus) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para cambiar estado', 'warning');
            return;
        }
        try {
            await TksApi.updateTicket(ticketId, { estado: newStatus });
            clearDataCache();
            if (window.showToast) window.showToast(`Estado cambiado a ${newStatus}`, 'success');
            refreshTicketAfterMutation(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
            if (currentTab === 'kanban') {
                loadTab('kanban', { force: true });
            }
        }
    }

    async function transitionSubestado(ticketId, toSubestado, options = {}) {
        const target = String(toSubestado || '').trim().toLowerCase();
        if (!target) return;
        const autoAdvance = options.autoAdvance === true;
        const silentError = options.silentError === true;
        const perms = getSelectedTicketPermissions(ticketId);
        if (perms && !perms.canChangeStatus) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para cambiar subestado', 'warning');
            return;
        }
        stopAutoProgressTimer();
        try {
            await TksApi.transitionTicket(ticketId, { to_subestado: target, motivo: 'gestion_ui' });
            clearDataCache();
            const labelTarget = target.replace(/_/g, ' ');
            if (window.showToast) {
                const msg = autoAdvance
                    ? `Subestado avanzado automáticamente a ${labelTarget}`
                    : `Subestado cambiado a ${labelTarget}`;
                window.showToast(msg, 'success');
            }
            refreshTicketAfterMutation(ticketId);
            if (currentTab === 'lista') {
                scheduleDetailFeedRefresh(ticketId);
            }
        } catch (e) {
            if (silentError) return;
            if (window.showToast) window.showToast(`Error cambiando subestado: ${e.message}`, 'error');
            if (!autoAdvance && selectedTicket && Number(selectedTicket.id) === Number(ticketId)) {
                scheduleAutoProgress(selectedTicket, ticketPermissions(selectedTicket), currentWorkflow || {});
            }
        }
    }

    async function addNote(ticketId) {
        const perms = selectedTicket && Number(selectedTicket.id) === Number(ticketId)
            ? ticketPermissions(selectedTicket)
            : null;
        if (perms && !perms.canAddInternalNote) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No puedes intervenir en este ticket', 'warning');
            return;
        }
        const input = el('tks-note-input');
        if (!input) return;
        const text = input.value.trim();
        if (!text) return;

        try {
            await TksApi.addEvento(ticketId, { evento: 'nota', detalle: text });
            clearDataCache();
            input.value = '';
            // Refrescar inmediatamente el detalle
            await openDetail(ticketId, { preserveTab: true });
            // Asegurar que bajamos el scroll para ver la nota recién puesta
            scrollTimelineToBottom();
        } catch (e) {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
        }
    }

    function getSelectedStatusValue() {
        const select = el('tks-status-next');
        if (!select) {
return { error: 'No se encontró el selector de estado' };
        }
        const nextStatus = String(select.value || '').trim();
        if (!nextStatus) {
return { error: 'Selecciona un estado destino' };
        }
return { value: nextStatus };
    }

    async function applyStatusChange(ticketId) {
        const statusResult = getSelectedStatusValue();
        if (statusResult.error) {
            if (window.showToast) window.showToast(statusResult.error, 'warning');
            return;
        }
        await changeStatus(ticketId, statusResult.value);
    }

    function parseNotifyEmailsInput(raw) {
        const tokens = String(raw || '')
            .split(/[,;\n]+/)
            .map((v) => String(v || '').trim().toLowerCase())
            .filter(Boolean);

        const valid = [];
        const invalid = [];
        const seen = new Set();
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

        tokens.forEach((email) => {
            if (!emailRegex.test(email)) {
                invalid.push(email);
                return;
            }
            if (seen.has(email)) return;
            seen.add(email);
            valid.push(email);
        });
return { valid, invalid };
    }

    function getNotifyEmailsPayload() {
        const input = el('tks-notify-emails');
        if (!input) {
return { error: 'No se encontró el campo de copiados' };
        }
        const raw = String(input.value || '').trim();
        const parsed = parseNotifyEmailsInput(raw);
        if (parsed.invalid.length > 0) {
return {
                error: `Correos inválidos: ${parsed.invalid.slice(0, 3).join(', ')}`,
            };
        }
return { value: parsed.valid };
    }

    async function saveNotifyEmails(ticketId) {
        const perms = getSelectedTicketPermissions(ticketId);
        if (perms && !perms.canChangeStatus) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para configurar copiados', 'warning');
            return;
        }

        const payload = getNotifyEmailsPayload();
        if (payload.error) {
            if (window.showToast) window.showToast(payload.error, 'warning');
            return;
        }

        try {
            await TksApi.updateTicket(ticketId, { notify_emails: payload.value });
            clearDataCache();
            if (window.showToast) {
                window.showToast(
                    payload.value.length
                        ? `Copiados actualizados (${payload.value.length})`
                        : 'Lista de copiados vaciada',
                    'success'
                );
            }
            refreshTicketAfterMutation(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`Error guardando copiados: ${e.message}`, 'error');
        }
    }

    function toggleAssigneePicker(forceOpen = null) {
        const select = el('tks-assignee-select');
        if (!select) return;
        try {
            select.focus();
            if (typeof select.showPicker === 'function') {
                select.showPicker();
            }
        } catch (e) {
            // navegadores sin showPicker: focus es suficiente
        }
    }

    function getAssigneePickerElements() {
return {
            pickerSelect: el('tks-assignee-select'),
            readonlyLabelEl: el('tks-assignee-readonly-label'),
        };
    }

    function renderAssigneePickerLoading(pickerSelect, currentAssignee, fallbackLabel) {
        if (!pickerSelect) return;
        pickerSelect.innerHTML = `<option value="${TksUI.escapeHtml(currentAssignee || '')}">${TksUI.escapeHtml(fallbackLabel)}</option>`;
        pickerSelect.disabled = true;
    }

    function buildAssigneeOptions(users, currentAssignee, currentLabel) {
        const options = [];
        const seen = new Set();
        options.push(`<option value="">Sin asignar</option>`);
        seen.add('');

        if (currentAssignee && !seen.has(currentAssignee)) {
            options.push(`<option value="${TksUI.escapeHtml(currentAssignee)}">${TksUI.escapeHtml(currentLabel)}</option>`);
            seen.add(currentAssignee);
        }

        users.forEach((item) => {
            const username = normalizeUser(item?.username);
            if (!username || seen.has(username)) return;
            seen.add(username);
            options.push(`<option value="${TksUI.escapeHtml(username)}">${TksUI.escapeHtml(assigneeOptionLabel(item) || humanizeUsername(username) || username)}</option>`);
        });

        return options;
    }

    async function hydrateAssigneePicker(ticket, permissions) {
        const canAssign = permissions?.canAssignTicket === true;
        const { pickerSelect, readonlyLabelEl } = getAssigneePickerElements();
        const ticketId = Number(ticket?.id || 0);
        if (!ticketId) return;
        if (!pickerSelect && !readonlyLabelEl) return;

        const currentAssignee = normalizeUser(ticket?.asignado_a);
        const fallbackLabel = humanizeUsername(ticket?.asignado_a) || 'Sin asignar';
        renderAssigneePickerLoading(pickerSelect, currentAssignee, fallbackLabel);

        try {
            const users = await loadAssignableUsers();
            if (currentTab !== 'lista' || Number(selectedTicketId) !== ticketId) return;

            const currentUserEntry = users.find((item) => normalizeUser(item?.username) === currentAssignee);
            const currentLabel = currentUserEntry
                ? assigneeOptionLabel(currentUserEntry, { includeAvailability: false })
                : fallbackLabel;
            if (readonlyLabelEl) {
                readonlyLabelEl.textContent = currentLabel || 'Sin asignar';
            }
            if (!canAssign || !pickerSelect) return;

            const options = buildAssigneeOptions(users, currentAssignee, currentLabel);
            pickerSelect.innerHTML = options.join('') || `<option value="${TksUI.escapeHtml(currentAssignee || '')}">${TksUI.escapeHtml(fallbackLabel)}</option>`;
            if (currentAssignee) {
                pickerSelect.value = currentAssignee;
            }
            pickerSelect.disabled = false;
        } catch (e) {
            if (pickerSelect) pickerSelect.disabled = false;
            if (window.showToast) window.showToast(`No se pudo cargar lista de técnicos: ${e.message}`, 'warning');
        }
    }

    function getAssigneeSelectionPayload() {
        const select = el('tks-assignee-select');
        if (!select) {
return { error: 'No se encontró el selector de asignación' };
        }
        const nextAssignee = normalizeUser(select.value || '');
        const currentAssignee = normalizeUser(selectedTicket?.asignado_a);
return {
            select,
            nextAssignee,
            currentAssignee,
            unchanged: currentAssignee === nextAssignee,
        };
    }

    async function applyAssigneeChange(ticketId) {
        const perms = getSelectedTicketPermissions(ticketId);
        if (perms && !perms.canAssignTicket) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para reasignar este ticket', 'warning');
            return;
        }

        const selection = getAssigneeSelectionPayload();
        if (selection.error) {
            if (window.showToast) window.showToast(selection.error, 'warning');
            return;
        }
        if (selection.unchanged) {
            return;
        }

        try {
            await TksApi.updateTicket(ticketId, { asignado_a: selection.nextAssignee || null });
            clearDataCache();
            const selectedLabel = String(selection.select.options?.[selection.select.selectedIndex]?.textContent || '').trim()
                || (humanizeUsername(selection.nextAssignee) || selection.nextAssignee);
            const msg = selection.nextAssignee ? `Ticket asignado a ${selectedLabel}` : 'Ticket desasignado';
            if (window.showToast) window.showToast(msg, 'success');
            refreshTicketAfterMutation(ticketId);
            if (currentTab === 'lista') {
                scheduleDetailFeedRefresh(ticketId);
            }
        } catch (e) {
            if (window.showToast) window.showToast(`Error reasignando ticket: ${e.message}`, 'error');
        }
    }

    function switchComposerMode(modeKey) {
        const panel = el('tks-detail-panel');
        if (!panel) return;
        const replyModeAvailable = !!panel.querySelector('[data-composer-mode="reply"]');
        detailActiveTab = (modeKey === 'reply' && replyModeAvailable) ? 'reply' : 'note';
        panel.querySelectorAll('[data-composer-mode]').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.composerMode === detailActiveTab);
        });
        panel.querySelectorAll('[data-composer-pane]').forEach((pane) => {
            pane.style.display = pane.dataset.composerPane === detailActiveTab ? '' : 'none';
        });
    }

    // Compatibilidad temporal con código legado que aún llama switchDetailTab.
    function switchDetailTab(tabKey) {
        switchComposerMode(tabKey);
    }

    function getDraftComposerElements() {
return {
            toInput: el('tks-draft-to'),
            ccInput: el('tks-draft-cc'),
            bccInput: el('tks-draft-bcc'),
            subjectInput: el('tks-draft-subject'),
            bodyInput: el('tks-draft-body'),
            filesInput: el('tks-draft-files'),
            fileList: el('tks-draft-file-list'),
        };
    }

    function renderReplyFileList() {
        const { filesInput, fileList } = getDraftComposerElements();
        if (!fileList) return;
        const files = Array.from(filesInput?.files || []);
        if (!files.length) {
            fileList.innerHTML = '<div style="color:var(--tks-text-muted);font-size:0.8rem;">Sin adjuntos seleccionados</div>';
            return;
        }
        fileList.innerHTML = files.map((file, index) => `
            <div class="tks-draft-attachment-row" style="display: flex; justify-content: space-between; align-items: center; padding: 4px; background: rgba(255,255,255,0.05); border-radius: 4px; margin-bottom: 4px;">
                <span><i class="fas fa-paperclip"></i> ${TksUI.escapeHtml(file.name || 'adjunto')} (${TksUI.formatFileSize(file.size)})</span>
                <button type="button" class="tks-btn-icon-sm" onclick="TksMain.deleteDraftAttachment(${index})" title="Quitar archivo" style="color: var(--kpi-red);"><i class="fas fa-times"></i></button>
            </div>
        `).join('');
    }

    let draftDataTransfer = null;
    function bindReplyComposer() {
        const { filesInput, bodyInput } = getDraftComposerElements();
        if (!filesInput) return;
        
        draftDataTransfer = new DataTransfer();
        // Si hay archivos iniciales, cargarlos
        if (filesInput.files) {
            Array.from(filesInput.files).forEach(f => draftDataTransfer.items.add(f));
        }

        filesInput.addEventListener('change', (e) => {
            Array.from(e.target.files).forEach(f => draftDataTransfer.items.add(f));
            filesInput.files = draftDataTransfer.files;
            renderReplyFileList();
        });

        if (bodyInput) {
            bodyInput.addEventListener('paste', (e) => {
                let added = false;
                Array.from(e.clipboardData.files).forEach(f => {
                    draftDataTransfer.items.add(f);
                    added = true;
                });
                if (added) {
                    filesInput.files = draftDataTransfer.files;
                    renderReplyFileList();
                    if (window.showToast) window.showToast('Imagen pegada como adjunto', 'success');
                }
            });

            bodyInput.addEventListener('dragover', (e) => e.preventDefault());
            bodyInput.addEventListener('drop', (e) => {
                e.preventDefault();
                let added = false;
                Array.from(e.dataTransfer.files).forEach(f => {
                    draftDataTransfer.items.add(f);
                    added = true;
                });
                if (added) {
                    filesInput.files = draftDataTransfer.files;
                    renderReplyFileList();
                    if (window.showToast) window.showToast('Archivo(s) agregado(s)', 'success');
                }
            });
        }
        
        renderReplyFileList();
    }

    function readDraftEditor(ticketId) {
        const { toInput, ccInput, bccInput, subjectInput, bodyInput } = getDraftComposerElements();
return {
            to_addr: toInput?.value?.trim() || '',
            cc_addrs: ccInput?.value?.trim() || '',
            bcc_addrs: bccInput?.value?.trim() || '',
            subject: subjectInput?.value?.trim() || '',
            body_text: bodyInput?.value || '',
            ticket_id: ticketId,
        };
    }

    async function acquireDraftLock(ticketId, force = false) {
        // Obsoleto por asignacion exclusiva de tickets
    }

    async function saveEmailDraft(ticketId, options = {}) {
        if (window.showToast) window.showToast('El flujo de borradores fue deshabilitado. Usa Enviar respuesta.', 'warning');
        return null;
    }

    async function uploadDraftAttachments(ticketId) {
        renderReplyFileList();
    }

    async function deleteDraftAttachment(index) {
        const { filesInput } = getDraftComposerElements();
        if (!filesInput || !draftDataTransfer) return;
        draftDataTransfer.items.remove(index);
        filesInput.files = draftDataTransfer.files;
        renderReplyFileList();
    }

    function closeDraftReviewModal() {
        const modal = el('tks-draft-review-modal');
        if (modal) modal.remove();
    }

    function validateDraftPayload(payload) {
        if (!payload.body_text.trim()) {
return { error: 'El mensaje del borrador está vacío' };
        }
        if (!payload.to_addr || !payload.to_addr.includes('@')) {
return { error: 'Correo destino inválido' };
        }
return { value: payload };
    }

    function buildDraftReviewModalHtml(ticketId, payload, attachments) {
        const ccPreview = String(payload.cc_addrs || '').trim();
        const bccPreview = String(payload.bcc_addrs || '').trim();
        const listItems = attachments.length
            ? attachments.map((att) => `<li>${TksUI.escapeHtml(att.name || 'adjunto')}</li>`).join('')
            : '<li>Sin adjuntos</li>';
        return `
            <div class="tks-modal-overlay open" id="tks-draft-review-modal">
                <div class="tks-modal tks-review-modal">
                    <div class="tks-modal-header">
                        <h3><i class="fas fa-paper-plane"></i> Confirmar envío</h3>
                        <button class="tks-modal-close" onclick="TksMain.closeDraftReviewModal()">&times;</button>
                    </div>
                    <div class="tks-modal-body">
                        <div class="tks-review-row">
                            <span class="tks-review-label">Para</span>
                            <span class="tks-review-value">${TksUI.escapeHtml(payload.to_addr)}</span>
                        </div>
                        <div class="tks-review-row">
                            <span class="tks-review-label">CC</span>
                            <span class="tks-review-value">${TksUI.escapeHtml(ccPreview || '-')}</span>
                        </div>
                        <div class="tks-review-row">
                            <span class="tks-review-label">CCO</span>
                            <span class="tks-review-value">${TksUI.escapeHtml(bccPreview || '-')}</span>
                        </div>
                        <div class="tks-review-row">
                            <span class="tks-review-label">Asunto</span>
                            <span class="tks-review-value">${TksUI.escapeHtml(payload.subject || '(sin asunto)')}</span>
                        </div>
                        <div class="tks-review-block">
                            <div class="tks-review-label">Descripción</div>
                            <div class="tks-review-body">${TksUI.escapeHtml(payload.body_text)}</div>
                        </div>
                        <div class="tks-review-block">
                            <div class="tks-review-label">Adjuntos (${attachments.length})</div>
                            <ul class="tks-review-list">${listItems}</ul>
                        </div>
                    </div>
                    <div class="tks-modal-footer">
                        <button class="tks-btn tks-btn-ghost" onclick="TksMain.closeDraftReviewModal()">Cancelar</button>
                        <button class="tks-btn tks-btn-primary" onclick="TksMain.confirmSendDraft(${Number(ticketId)})">
                            <i class="fas fa-envelope"></i> Confirmar envío
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    function openDraftReviewModal(ticketId) {
        const payloadResult = validateDraftPayload(readDraftEditor(ticketId));
        if (payloadResult.error) {
            if (window.showToast) window.showToast(payloadResult.error, 'warning');
            return;
        }

        closeDraftReviewModal();
        const { filesInput } = getDraftComposerElements();
        const attachments = Array.from(filesInput?.files || []);
        document.body.insertAdjacentHTML('beforeend', buildDraftReviewModalHtml(ticketId, payloadResult.value, attachments));
    }

    async function reviewSendDraft(ticketId) {
        openDraftReviewModal(ticketId);
    }

    function validateReplyPermissions(ticketId) {
        const ticket = selectedTicket && Number(selectedTicket?.id) === Number(ticketId) ? selectedTicket : null;
        const permissions = ticket ? ticketPermissions(ticket) : null;
        if (permissions && !permissions.canParticipate) {
return { error: permissions.blockedReason || 'No puedes responder este ticket' };
        }
        if (ticket && permissions && !permissions.canReplyToClient) {
return { error: replyBlockedReason(ticket, permissions) };
        }
return { ticket, permissions };
    }

    function buildReplyFormData(payload, files) {
        const formData = new FormData();
        formData.append('mensaje', payload.body_text);
        formData.append('asunto', payload.subject);
        formData.append('to_addr', payload.to_addr);
        formData.append('cc_addrs', payload.cc_addrs);
        formData.append('bcc_addrs', payload.bcc_addrs);
        files.forEach((file) => formData.append('files', file));
        return formData;
    }

    async function confirmSendDraft(ticketId) {
        const permissionCheck = validateReplyPermissions(ticketId);
        if (permissionCheck.error) {
            if (window.showToast) window.showToast(permissionCheck.error, 'warning');
            return;
        }

        const payloadResult = validateDraftPayload(readDraftEditor(ticketId));
        if (payloadResult.error) {
            if (window.showToast) window.showToast(payloadResult.error, 'warning');
            return;
        }

        const { filesInput } = getDraftComposerElements();
        const files = Array.from(filesInput?.files || []);
        const formData = buildReplyFormData(payloadResult.value, files);

        try {
            await TksApi.replyByEmail(ticketId, formData, { timeoutMs: 60000 });
            closeDraftReviewModal();
            clearDataCache();
            stopDraftHeartbeat();
            draftLockToken = '';
            detailActiveTab = 'reply';
            if (window.showToast) window.showToast('Correo enviado al cliente', 'success');
            refreshTicketAfterMutation(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`Error enviando correo: ${e.message}`, 'error');
        }
    }

    async function discardEmailDraft(ticketId) {
        if (window.showToast) window.showToast('El flujo de borradores fue deshabilitado.', 'warning');
    }

    async function replyByEmail(ticketId) {
        await reviewSendDraft(ticketId);
    }

    function openReassign(ticketId) {
        if (!sessionCtx.isAdmin) {
            if (window.showToast) window.showToast('Solo admin o encargado de mesa puede reasignar tickets', 'warning');
            return;
        }
        const user = prompt('Nombre de usuario para reasignar:');
        if (!user) return;
        TksApi.updateTicket(ticketId, { asignado_a: user.trim() }).then(() => {
            clearDataCache();
            if (window.showToast) window.showToast(`Reasignado a ${user}`, 'success');
            openDetail(ticketId, { preserveTab: true });
            refreshList();
        }).catch(e => {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
        });
    }

    function getSelectedTicketPermissions(ticketId) {
        return selectedTicket && Number(selectedTicket?.id) === Number(ticketId)
            ? ticketPermissions(selectedTicket)
            : null;
    }

    function refreshTicketAfterMutation(ticketId, options = {}) {
        const refreshKanban = options.refreshKanban === true;
        const preserveTab = options.preserveTab !== false;
        if (refreshKanban || currentTab === 'kanban') {
            loadTab('kanban', { force: true });
            return;
        }
        if (currentTab === 'lista') {
            refreshList();
            if (options.closeDetailOnList) {
                closeDetail({ silent: true, force: true });
                return;
            }
            if (preserveTab) {
                openDetail(ticketId, { preserveTab: true });
            }
            return;
        }
        loadTab(currentTab, { force: true });
    }

    async function takeTicket(ticketId) {
        const permissions = getSelectedTicketPermissions(ticketId);
        if (permissions && !permissions.canClaim) {
            if (window.showToast) window.showToast(permissions.blockedReason || 'No puedes tomar este ticket', 'warning');
            return;
        }
        try {
            await TksApi.claimTicket(ticketId);
            clearDataCache();
            if (window.showToast) window.showToast('Ticket tomado correctamente', 'success');
            refreshTicketAfterMutation(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`No se pudo tomar ticket: ${e.message}`, 'error');
        }
    }

    async function trashTicket(ticketId, options = {}) {
        const ticket = selectedTicket && Number(selectedTicket?.id) === Number(ticketId) ? selectedTicket : null;
        const permissions = ticket ? ticketPermissions(ticket) : null;
        if (permissions && !permissions.canTrash) {
            if (window.showToast) window.showToast('Solo admin o encargado de mesa puede enviar tickets a papelera', 'warning');
            return;
        }
        const skipPrompt = options.skipPrompt === true;
        const skipConfirm = options.skipConfirm === true;
        const defaultReason = typeof options.reason === 'string' ? options.reason : '';
        let reason = defaultReason;
        if (!skipPrompt) {
            const reasonInput = window.prompt('Motivo para mover a papelera (opcional):', ticket?.trash_reason || defaultReason);
            if (reasonInput === null) return;
            reason = reasonInput;
        }
        if (!skipConfirm) {
            const ok = window.confirm('Este ticket saldrá de la operación normal y quedará en la papelera. ¿Continuar?');
            if (!ok) return;
        }

        try {
            await TksApi.trashTicket(ticketId, { reason: reason.trim() });
            clearDataCache();
            if (window.showToast) window.showToast('Ticket enviado a papelera', 'success');
            const viewingTrash = currentTab === 'lista' && filters.status === 'papelera';
            refreshTicketAfterMutation(ticketId, {
                refreshKanban: options.refreshKanban === true,
                closeDetailOnList: !viewingTrash,
            });
        } catch (e) {
            if (window.showToast) window.showToast(`No se pudo mover a papelera: ${e.message}`, 'error');
        }
    }

    async function restoreTicket(ticketId) {
        const permissions = getSelectedTicketPermissions(ticketId);
        if (permissions && !permissions.canRestore) {
            if (window.showToast) window.showToast('Solo admin o encargado de mesa puede restaurar tickets', 'warning');
            return;
        }
        try {
            await TksApi.restoreTicket(ticketId);
            clearDataCache();
            if (window.showToast) window.showToast('Ticket restaurado desde papelera', 'success');
            refreshTicketAfterMutation(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`No se pudo restaurar ticket: ${e.message}`, 'error');
        }
    }

    // ---- KANBAN ----
    async function loadKanban(container, token) {
        if (!container) return;
        if (isFresh(cache.kanban)) {
            container.innerHTML = TksUI.renderKanban(
                scopeKanbanDataForSession(cache.kanban.data),
                { canDrag: sessionCtx.isAdmin, canTrash: sessionCtx.isAdmin }
            );
            bindKanbanDrop();
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-kanban-board"><div class="tks-skeleton" style="height:200px;flex:1"></div></div>';
        try {
            const data = await TksApi.getTablero({ signal: controller.signal, timeoutMs: 10000 });
            if (token !== tabRequestToken || currentTab !== 'kanban') return;
            container.innerHTML = TksUI.renderKanban(
                scopeKanbanDataForSession(data.kanban),
                { canDrag: sessionCtx.isAdmin, canTrash: sessionCtx.isAdmin }
            );
            bindKanbanDrop();
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'kanban') return;
            container.innerHTML = `<div style="padding:1rem;color:red">Error: ${errorHtml(e)}</div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    // ---- MENSAJES ----
    async function loadMessageTemplates(container, token) {
        if (!container) return;
        if (isFresh(cache.messages)) {
            hydrateMessageSettingsState(cache.messages.data);
            renderMessageSettings(container);
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:220px;"></div></div>';
        try {
            const data = await TksApi.getDomainTemplateSettings({ signal: controller.signal, timeoutMs: 12000 });
            if (token !== tabRequestToken || currentTab !== 'messages') return;
            cache.messages = { data, ts: Date.now() };
            hydrateMessageSettingsState(data);
            renderMessageSettings(container);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'messages') return;
            container.innerHTML = `<div class="tks-dashboard"><p style="color:red">Error cargando mensajes: ${errorHtml(e)}</p></div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    // ---- ARCHIVADOS Y REPORTES ----
    async function loadArchivosReportes(container, token) {
        if (!container) return;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:220px;"></div></div>';
        if (token !== tabRequestToken || currentTab !== 'reportes') return;
        container.innerHTML = TksUI.renderArchivosView();
        // Poblar select de clientes y luego cargar tickets
        window.cargarClientesSelect('tks-arch-filter-cliente').then(() => window.loadArchivados());
        window.cargarClientesSelect('tks-reporte-cliente-select');
    }

    // ---- OPS ----
    async function loadOps(container, token) {
        const renderOpsContainer = (data) => `
            <div class="tks-ops-toolbar" style="display:flex; justify-content:flex-end; gap:1rem; margin-bottom:1rem; padding: 0.5rem;">
                <button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.showConsole()">
                    <i class="fas fa-terminal"></i> Ver Consola de Estado
                </button>
            </div>
            <div style="position: relative; padding-top: 0.5rem; overflow: visible;">
                ${TksUI.renderOps(data)}
            </div>
        `;
        if (!container) return;
        if (isFresh(cache.ops)) {
            container.innerHTML = renderOpsContainer(cache.ops.data);
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:220px;"></div></div>';
        try {
            const settled = await Promise.allSettled([
                TksApi.getQueueHealth({ signal: controller.signal, timeoutMs: 12000 }),
                TksApi.getChannelsStatus({ signal: controller.signal, timeoutMs: 12000 }),
                TksApi.listChannelNotifications({ limit: 20 }, { signal: controller.signal, timeoutMs: 12000 }),
                TksApi.listComplianceExportRuns({ signal: controller.signal, timeoutMs: 12000 }),
            ]);
            if (token !== tabRequestToken || currentTab !== 'ops') return;

            const data = {
                queue: settled[0]?.status === 'fulfilled' ? settled[0].value : {},
                channels: settled[1]?.status === 'fulfilled' ? settled[1].value : {},
                channelNotifications: settled[2]?.status === 'fulfilled' ? settled[2].value : { items: [] },
                complianceExportRuns: settled[3]?.status === 'fulfilled' ? settled[3].value : { items: [] },
            };
            cache.ops = { data, ts: Date.now() };
            container.innerHTML = renderOpsContainer(data);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'ops') return;
            container.innerHTML = `<div class="tks-dashboard"><p style="color:red">Error cargando Operación: ${errorHtml(e)}</p></div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    async function showConsole() {
        const container = el('tks-content');
        if (!container) return;
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:200px;margin:1.5rem"></div></div>';
        try {
            const data = await window.fetchApi('/api/tks/ops/console');
            if (currentTab !== 'ops') return;
            container.innerHTML = TksUI.renderConsole(data);
        } catch (e) {
            container.innerHTML = `<div class="tks-card" style="color:red">Error cargando consola: ${e.message}</div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    async function refreshOps() {
        cache.ops = null;
        loadTab('ops', { force: true });
    }

    function readMessageTemplateEditor() {
return {
            subject_template: String(el('tks-template-editor-subject')?.value || '').trim(),
            body_template: String(el('tks-template-editor-body')?.value || ''),
        };
    }

    async function saveMessageTemplates() {
        const templateKey = String(messageSettingsState.activeTemplateKey || '').trim().toLowerCase();
        if (!templateKey) {
            if (window.showToast) window.showToast('Primero selecciona una plantilla.', 'warning');
            return;
        }
        const payload = readMessageTemplateEditor();
        try {
            const out = await TksApi.updateMailTemplate(templateKey, payload, { timeoutMs: 12000 });
            const updatedTemplate = mergeMailTemplateState(out?.template || null);
            if (updatedTemplate) {
                hydrateMessageSettingsState(cache.messages?.data || {});
            }
            closeMailTemplateModal();
            if (window.showToast) window.showToast('Plantilla guardada.', 'success');
            renderMessageSettings(el('tks-content'));
        } catch (e) {
            if (window.showToast) {
                window.showToast(`No fue posible guardar la plantilla: ${errorMessage(e)}`, 'error');
            }
        }
    }

    function readRoutingRuleEditor() {
return {
            id: Number(messageSettingsState.editingRuleId || 0) || null,
            match_type: String(el('tks-routing-match-type')?.value || 'email').trim(),
            match_value: String(el('tks-routing-match-value')?.value || '').trim(),
            categoria: String(el('tks-routing-categoria')?.value || '').trim(),
            is_active: el('tks-routing-is-active')?.checked !== false,
        };
    }

    function resetRoutingRuleForm() {
        messageSettingsState.editingRuleId = null;
        renderMessageSettings(el('tks-content'));
    }

    function editRoutingRule(ruleId) {
        messageSettingsState.editingRuleId = Number(ruleId || 0) || null;
        renderMessageSettings(el('tks-content'));
    }

    async function saveRoutingRule() {
        const payload = readRoutingRuleEditor();
        if (!payload.match_value) {
            if (window.showToast) window.showToast('Debes ingresar un correo o dominio para la regla.', 'warning');
            return;
        }
        if (!payload.categoria) {
            if (window.showToast) window.showToast('Debes seleccionar un área para la regla.', 'warning');
            return;
        }
        try {
            await TksApi.upsertRoutingRule(payload, { timeoutMs: 12000 });
            messageSettingsState.editingRuleId = null;
            cache.messages = null;
            if (window.showToast) window.showToast('Regla de enrutamiento guardada.', 'success');
            loadTab('messages', { force: true });
        } catch (e) {
            if (window.showToast) {
                window.showToast(`No fue posible guardar la regla: ${errorMessage(e)}`, 'error');
            }
        }
    }

    async function deleteRoutingRule(ruleId) {
        const normalizedId = Number(ruleId || 0);
        if (!normalizedId) return;
        if (!window.confirm('¿Eliminar esta regla de enrutamiento?')) return;
        try {
            await TksApi.deleteRoutingRule(normalizedId, { timeoutMs: 12000 });
            messageSettingsState.editingRuleId = null;
            cache.messages = null;
            if (window.showToast) window.showToast('Regla eliminada.', 'success');
            loadTab('messages', { force: true });
        } catch (e) {
            if (window.showToast) {
                window.showToast(`No fue posible eliminar la regla: ${errorMessage(e)}`, 'error');
            }
        }
    }

    async function retryChannel(notificationId) {
        const id = Number(notificationId || 0);
        if (!id) return;
        try {
            const idem = `ops-retry-${id}-${Date.now()}`;
            await TksApi.retryChannelNotification(id, { headers: { 'Idempotency-Key': idem } });
            if (window.showToast) window.showToast(`Reintento encolado para notificación #${id}`, 'success');
            refreshOps();
        } catch (e) {
            if (window.showToast) window.showToast(`Error en reintento de canal: ${e.message}`, 'error');
        }
    }

    async function recoverStaleJobs() {
        const raw = prompt('Minutos para considerar ejecución huérfana:', '20');
        if (raw == null) return;
        const staleMinutes = Math.max(1, Math.min(240, Number(raw) || 20));
        try {
            const out = await TksApi.recoverStaleJobs(staleMinutes);
            const recovered = Number(out?.recovered?.recovered || 0);
            if (window.showToast) window.showToast(`Recuperación de huérfanos ejecutada: ${recovered} trabajos`, 'success');
            refreshOps();
        } catch (e) {
            if (window.showToast) window.showToast(`Error al recuperar huérfanos: ${e.message}`, 'error');
        }
    }

    function onDragStart(event, ticketId, sourceStatus = '') {
        kanbanDragSourceStatus = String(sourceStatus || '').trim().toLowerCase();
        event.dataTransfer.setData('text/plain', ticketId);
        event.dataTransfer.setData('application/x-tks-status', kanbanDragSourceStatus);
        event.dataTransfer.effectAllowed = 'move';
    }

    function toggleKanbanDropState(target, active) {
        if (!target) return;
        target.classList.toggle('is-dragover', !!active);
    }

    function bindKanbanDrop() {
        if (!sessionCtx.isAdmin) return;
        document.querySelectorAll('.tks-kanban-col-body').forEach(col => {
            col.addEventListener('dragover', e => { e.preventDefault(); toggleKanbanDropState(col, true); });
            col.addEventListener('dragleave', () => { toggleKanbanDropState(col, false); });
            col.addEventListener('drop', async e => {
                e.preventDefault();
                toggleKanbanDropState(col, false);
                const ticketId = parseInt(e.dataTransfer.getData('text/plain'));
                const newStatus = col.dataset.status;
                const sourceStatus = String(
                    e.dataTransfer.getData('application/x-tks-status') || kanbanDragSourceStatus || ''
                ).trim().toLowerCase();
                if (!ticketId || !newStatus) return;
                if (!isAdjacentStatusMove(sourceStatus, newStatus)) {
                    if (window.showToast) {
                        window.showToast('Solo puedes avanzar o retroceder un estado a la vez en el Kanban.', 'warning');
                    }
                    return;
                }
                await changeStatus(ticketId, newStatus);
            });
        });
        const trashZone = document.querySelector('.tks-kanban-trash-zone');
        if (trashZone) {
            trashZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                toggleKanbanDropState(trashZone, true);
            });
            trashZone.addEventListener('dragleave', () => {
                toggleKanbanDropState(trashZone, false);
            });
            trashZone.addEventListener('drop', async (e) => {
                e.preventDefault();
                toggleKanbanDropState(trashZone, false);
                const ticketId = parseInt(e.dataTransfer.getData('text/plain'));
                if (!ticketId) return;
                await trashTicket(ticketId, {
                    skipPrompt: true,
                    reason: 'Movido a papelera desde Kanban',
                    refreshKanban: true,
                });
            });
        }
    }

    // ---- MODAL CREAR ----
    function openCreateModal() {
        if (!sessionCtx.canCreate) {
            if (window.showToast) window.showToast('Tu rol es de solo lectura para creación de tickets', 'warning');
            return;
        }
        const modal = el('tks-create-modal');
        if (modal) modal.classList.add('open');
    }

    function closeCreateModal() {
        const modal = el('tks-create-modal');
        if (modal) modal.classList.remove('open');
    }

    // ---- CLIENT ASSOCIATION ----
    let assocEmail = '';
    let assocSearchTimeout = null;
    let assocSearchAbortController = null;
    let assocSearchSeq = 0;

    function openAssociateClientModal(email) {
        assocEmail = email;
        const container = document.body;
        // Check if already exists, remove it
        const existing = el('tks-associate-modal');
        if (existing) existing.remove();

        const html = TksUI.renderAssociateClientModal(email);
        const wrapper = document.createElement('div');
        wrapper.innerHTML = html;
        container.appendChild(wrapper.firstElementChild);

        // Show immediate
        setTimeout(() => el('tks-associate-modal').classList.add('open'), 10);

        // Focus search
        setTimeout(() => {
            const input = el('tks-assoc-search');
            if (input) {
                input.focus();
                input.addEventListener('input', () => {
                    if (assocSearchTimeout) clearTimeout(assocSearchTimeout);
                    assocSearchTimeout = setTimeout(() => {
                        searchClients({ silent: true });
                    }, 140);
                });
            }
        }, 100);

        // Cargar listado base al abrir para selección rápida.
        setTimeout(() => {
            searchClients({ silent: true });
        }, 120);
    }

    function closeAssociateModal() {
        if (assocSearchTimeout) {
            clearTimeout(assocSearchTimeout);
            assocSearchTimeout = null;
        }
        if (assocSearchAbortController) {
            assocSearchAbortController.abort();
            assocSearchAbortController = null;
        }
        const modal = el('tks-associate-modal');
        if (modal) {
            modal.classList.remove('open');
            setTimeout(() => modal.remove(), 300);
        }
    }

    async function searchClients(options = {}) {
        const silent = options.silent === true;
        const input = el('tks-assoc-search');
        const resultsEl = el('tks-assoc-results');
        const countEl = el('tks-assoc-count');
        if (!resultsEl || !input) return;
        const q = input.value.trim();

        resultsEl.style.display = 'block';
        resultsEl.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--tks-text-muted)">Cargando clientes...</div>';
        if (countEl) countEl.textContent = 'Cargando...';

        if (assocSearchAbortController) assocSearchAbortController.abort();
        const controller = new AbortController();
        assocSearchAbortController = controller;
        const reqId = ++assocSearchSeq;

        try {
            const primaryQs = q ? `?q=${encodeURIComponent(q)}&limit=100` : '?limit=0';
            let data;
            try {
                data = await fetchApi(`/api/tks/customers/search${primaryQs}`, { signal: controller.signal, timeoutMs: 12000 });
            } catch (primaryErr) {
                // Compatibilidad: backend antiguo puede rechazar limit=0 con 422.
                const needsFallback = !q && String(primaryErr?.message || '').includes('greater_than_equal');
                if (!needsFallback) throw primaryErr;
                data = await fetchApi('/api/tks/customers/search?limit=100', { signal: controller.signal, timeoutMs: 12000 });
            }
            if (reqId !== assocSearchSeq) return;
            const items = data.items || [];

            if (items.length === 0) {
                resultsEl.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--tks-text-muted)">No se encontraron clientes</div>';
                if (countEl) countEl.textContent = '0 clientes';
                return;
            }

            resultsEl.innerHTML = items.map(c => `
                <div class="tks-assoc-item" onclick="TksMain.selectClient('${escapeJsSingleQuoted(c.id)}', '${escapeJsSingleQuoted(c.name)}')">
                    <div style="font-weight:600;color:var(--tks-text-main)">${TksUI.escapeHtml(c.name)}</div>
                    <div style="font-size:0.8rem;color:var(--tks-text-muted)">RUT: ${TksUI.escapeHtml(c.vat_id || 'N/A')}</div>
                </div>
            `).join('');

            // Add hover effect via JS/CSS or inline
            resultsEl.querySelectorAll('.tks-assoc-item').forEach(div => {
                div.addEventListener('mouseenter', () => div.style.background = 'rgba(255,255,255,0.05)');
                div.addEventListener('mouseleave', () => div.style.background = 'transparent');
            });
            if (countEl) countEl.textContent = `${items.length} cliente${items.length === 1 ? '' : 's'}`;

        } catch (e) {
            if (e?.name === 'AbortError') return;
            resultsEl.innerHTML = `<div style="padding:1rem;color:red">Error: ${errorHtml(e)}</div>`;
            if (countEl) countEl.textContent = 'Error de carga';
            if (!silent && window.showToast) window.showToast(`Error buscando clientes: ${e.message}`, 'error');
        } finally {
            if (assocSearchAbortController === controller) {
                assocSearchAbortController = null;
            }
        }
    }

    async function selectClient(custId, custName) {
        if (!confirm(`¿Vincular ${assocEmail} al cliente "${custName}"?`)) return;

        try {
            // 1. Asociar email globalmente
            await fetchApi('/api/tks/customers/associate-email', {
                method: 'POST',
                body: JSON.stringify({
                    email: assocEmail,
                    customer_id: custId,
                    customer_name: custName
                })
            });

            // 2. Si estamos en un ticket específico, actualizarlo de inmediato (incluso si no tiene email)
            if (cache.detail && cache.detail.id) {
                await fetchApi(`/api/tks/tickets/${cache.detail.id}`, {
                    method: 'PATCH',
                    body: JSON.stringify({
                        customer_id: custId,
                        cliente_nombre: custName
                    })
                });
            }

            if (window.showToast) window.showToast('Vinculación exitosa', 'success');
            closeAssociateModal();
            
            // Refrescar según donde estemos
            if (cache.detail && cache.detail.id) {
                showDetail(cache.detail.id);
            } else {
                refreshList();
            }
        } catch (e) {
            if (window.showToast) window.showToast(`Error vinculando: ${e.message}`, 'error');
        }
    }

    async function submitCreate() {
        if (!sessionCtx.canCreate) {
            if (window.showToast) window.showToast('No tienes permisos para crear tickets', 'warning');
            return;
        }
        const titulo = el('tks-new-titulo')?.value?.trim();
        if (!titulo) {
            if (window.showToast) window.showToast('El título es obligatorio', 'error');
            return;
        }

        const body = {
            titulo,
            descripcion: el('tks-new-desc')?.value || '',
            severidad: el('tks-new-sev')?.value || 'media',
            categoria: el('tks-new-cat')?.value || null,
            origen_email: el('tks-new-email')?.value?.trim() || null,
            cliente_nombre: el('tks-new-cliente')?.value?.trim() || null,
        };

        try {
            const ticket = await TksApi.createTicket(body);
            clearDataCache();
            closeCreateModal();
            if (window.showToast) window.showToast(`Ticket ${ticket.codigo} creado ✅`, 'success');
            loadTab('lista', { force: true });
            setTimeout(() => openDetail(ticket.id), 300);
        } catch (e) {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
        }
    }

    // ---- NOTIFICATIONS POLL ----
    async function pollNotifications() {
        if (document.hidden) return;
        if (notifInFlight) return;
        notifInFlight = true;
        const controller = new AbortController();
        notifAbortController = controller;
        try {
            const data = await TksApi.getNotificaciones({ signal: controller.signal, timeoutMs: 8000 });
            notifCount = data.total || 0;
            const badge = el('tks-notif-badge');
            if (badge) {
                badge.textContent = notifCount;
                badge.style.display = notifCount > 0 ? 'flex' : 'none';
            }
        } catch (e) {
            if (e?.name !== 'AbortError') {
                // silent
            }
        } finally {
            if (notifAbortController === controller) {
                notifAbortController = null;
            }
            notifInFlight = false;
        }
    }

    // ---- PUBLIC API ----
return {
        init,
        loadTab,
        openDetail,
        closeDetail,
        refreshList,
        openAttachmentPreview,
        closeAttachmentPreview,
        openMailTemplateModal,
        closeMailTemplateModal,
        saveMessageTemplates,
        saveRoutingRule,
        editRoutingRule,
        deleteRoutingRule,
        resetRoutingRuleForm,
        switchComposerMode,
        switchDetailTab,
        applyStatusChange,
        toggleAssigneePicker,
        applyAssigneeChange,
        saveNotifyEmails,
        changeStatus,
        transitionSubestado,
        addNote,
        replyByEmail,
        acquireDraftLock,
        saveEmailDraft,
        uploadDraftAttachments,
        deleteDraftAttachment,
        reviewSendDraft,
        confirmSendDraft,
        discardEmailDraft,
        closeDraftReviewModal,
        openReassign,
        takeTicket,
        trashTicket,
        restoreTicket,
        onDragStart,
        openCreateModal,
        closeCreateModal,
        submitCreate,
        retryChannel,
        refreshOps,
        showConsole,
        recoverStaleJobs,
        loadCustomer360,
        generatePaymentLink,
        openAssociateClientModal,
        closeAssociateModal,
        searchClients,
        selectClient,
    };
})();

async function loadCustomer360(customerId, ticketId) {
    const container = document.querySelector('.tks-customer-360-container');
    const loading = document.getElementById('tks-c360-loading');
    const content = document.getElementById('tks-c360-content');

    if (!container || !loading || !content) return;

    loading.style.display = 'block';
    content.style.display = 'none';
    content.innerHTML = '';

    if (!customerId) {
        loading.style.display = 'none';
        content.innerHTML = '<p style="color:var(--tks-text-muted); text-align:center; padding:2rem">Este ticket no está asociado a un cliente.</p>';
        content.style.display = 'block';
        return;
    }

    try {
        // En un escenario real, esto llamaría a /api/crm/customers/{id}
        // Simulamos respuesta por ahora o usamos un endpoint existente si hay
        // Como no tenemos un endpoint unificado de "Cliente 360", hacemos un fetch mock o partial

        // Intentamos usar el endpoint de cobros para tener info financiera
        // GET /api/cobranza/resumen-cliente/{rut} ?? No existe exacto.
        // Usaremos un mock por ahora basado en la info que tenemos.

        // TODO: Implementar endpoint real backend. Por ahora simulamos delay y data.
        await new Promise(r => setTimeout(r, 600));

        const mockData = {
            customer_id: customerId,
            customer_name: "Cliente " + customerId, // Placeholder
            status: Math.random() > 0.5 ? 'DEBT' : 'OK',
            total_debt: Math.floor(Math.random() * 500000),
            last_tickets: []
        };

        loading.style.display = 'none';
        content.innerHTML = TksUI.renderCustomer360(mockData);
        content.style.display = 'block';

    } catch (e) {
        loading.style.display = 'none';
        content.innerHTML = `<p style="color:red">Error cargando datos: ${errorHtml(e)}</p>`;
        content.style.display = 'block';
    }
}

async function generatePaymentLink(customerId, amount, triggerEl = null) {
    const btn = (triggerEl && typeof triggerEl.closest === 'function')
        ? triggerEl.closest('button')
        : null;
    if (!btn) {
        if (window.showToast) window.showToast('No se pudo identificar el botón de acción.', 'error');
        return;
    }
    const originalText = btn.innerHTML;
    const resultDiv = document.getElementById('payment-link-result');
    if (!resultDiv) {
        if (window.showToast) window.showToast('No se encontró el contenedor de resultado.', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generando...';
    resultDiv.style.display = 'none';

    try {
        const payload = { customer_id: customerId, amount: amount };
        const response = await window.fetchApi('/api/cobranza/payment-link', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        const paymentUrl = String(response?.payment_url || '').trim();
        const paymentUrlHtml = TksUI.escapeHtml(paymentUrl);
        const paymentUrlJs = escapeJsSingleQuoted(paymentUrl);
        const expiresLabel = response?.expires_at ? new Date(response.expires_at).toLocaleString() : '-';
        const expiresHtml = TksUI.escapeHtml(expiresLabel);

        resultDiv.innerHTML = `
            <div style="background:rgba(0,255,100,0.1); border:1px solid #00c851; padding:1rem; border-radius:6px; margin-top:1rem">
                <div style="font-weight:bold; color:#00c851; margin-bottom:0.5rem"><i class="fas fa-check-circle"></i> Link generado</div>
                <div style="display:flex; gap:0.5rem">
                    <input type="text" readonly value="${paymentUrlHtml}" style="flex:1; background:#111; border:1px solid #333; color:#eee; padding:4px; border-radius:4px" onclick="this.select()">
                    <button class="tks-btn tks-btn-sm" onclick="navigator.clipboard.writeText('${paymentUrlJs}')"><i class="fas fa-copy"></i></button>
                </div>
                <div style="font-size:0.75rem; opacity:0.7; margin-top:0.5rem">Expira: ${expiresHtml}</div>
            </div>
        `;
        resultDiv.style.display = 'block';

    } catch (e) {
        if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

// Attach to TksMain scope hack (since we are using IIFE above but these need to be accessible if not inside)
// Actually, better to put them INSIDE the IIFE or attach them to the returned object.
// We are replacing the RETURN block, so we can't easily append outside.
// Let's rewrite the replacement to be INSIDE the IIFE return.


// Auto-init on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    if (window.initLogout) window.initLogout();
    document.title = "Mesa de Ayuda | Monstruo";
    TksMain.init();
});

window.cargarClientesSelect = async function(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    try {
        const data = await fetchApi('/api/tks/customers/search?limit=500');
        const items = data?.items || [];
        const current = sel.value;
        sel.innerHTML = '<option value="">Todos los clientes</option>' +
            items.map(c => {
                const nombre = c.name || c.legal_name || c.id;
                return `<option value="${TksUI.escapeHtml(c.id)}">${TksUI.escapeHtml(nombre)}</option>`;
            }).join('');
        if (current) sel.value = current;
    } catch (e) {
        // silencioso — el select queda con solo la opción "Todos"
    }
};

window.loadArchivados = async function() {
    const listContainer = document.getElementById('tks-archivados-results-container');
    if (!listContainer) return;

    const cliente = (document.getElementById('tks-arch-filter-cliente')?.value || '').trim();
    const cat = (document.getElementById('tks-arch-filter-cat')?.value || '').trim();
    const estado = (document.getElementById('tks-arch-filter-estado')?.value || '').trim();
    const desde = (document.getElementById('tks-arch-filter-desde')?.value || '').trim();
    const hasta = (document.getElementById('tks-arch-filter-hasta')?.value || '').trim();

    listContainer.innerHTML = '<div style="text-align:center;padding:2rem"><i class="fas fa-circle-notch fa-spin"></i> Cargando...</div>';

    try {
        const params = new URLSearchParams({ limit: '200' });
        if (cliente) params.set('customer_id', cliente);
        if (cat) params.set('categoria', cat);
        if (estado) params.set('status', estado);
        if (desde) params.set('created_after', desde);
        if (hasta) params.set('created_before', hasta);
        // Si no hay filtro de estado, traemos cerrados y resueltos (excluye activos y papelera)
        if (!estado) params.set('status', 'cerrado,resuelto');

        const data = await fetchApi('/api/tks/tickets?' + params.toString());
        const items = data?.items || [];

        if (!items.length) {
            listContainer.innerHTML = '<p style="opacity:0.6;font-size:0.9rem;padding:1rem 0">No hay tickets archivados con los filtros seleccionados.</p>';
            return;
        }

        const esc = TksUI.escapeHtml.bind(TksUI);
        const rows = items.map(t => {
            const sinCliente = !t.customer_id && !t.cliente_nombre;
            const clienteLabel = t.cliente_nombre
                ? `<span>${esc(t.cliente_nombre)}</span>`
                : `<span style="opacity:0.5;font-style:italic">Sin asignar</span>`;
            const emailEsc = (t.origen_email || '').replace(/'/g, "\\'");
            const tituloEsc = (t.titulo || '').replace(/'/g, "\\'");
            const asignarBtn = sinCliente
                ? `<button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="window.abrirAsignarCliente(${t.id}, '${emailEsc}', '${tituloEsc}')">
                       <i class="fas fa-user-tag"></i> Asignar
                   </button>`
                : `<button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="window.abrirAsignarCliente(${t.id}, '${emailEsc}', '${tituloEsc}')">
                       <i class="fas fa-edit"></i>
                   </button>`;
            return `
            <tr>
                <td><span class="tks-code">${esc(t.codigo || '#' + t.id)}</span></td>
                <td><div class="tks-ticket-title fade-overflow" title="${esc(t.titulo || '')}" style="max-width:260px">${esc(t.titulo || '-')}</div></td>
                <td>${esc(t.estado || '-')}</td>
                <td>${esc(t.categoria || '-')}</td>
                <td>${clienteLabel}</td>
                <td>${esc(t.origen_email || '-')}</td>
                <td>${t.created_at ? t.created_at.slice(0,10) : '-'}</td>
                <td>${asignarBtn}</td>
            </tr>`;
        }).join('');

        listContainer.innerHTML = `
        <p style="font-size:0.85rem;opacity:0.6;margin-bottom:0.5rem">${items.length} ticket(s) encontrado(s)</p>
        <div class="tks-pivot-container">
            <table class="tks-pivot-table">
                <thead>
                    <tr>
                        <th>Código</th>
                        <th>Título</th>
                        <th>Estado</th>
                        <th>Área</th>
                        <th>Cliente</th>
                        <th>Email origen</th>
                        <th>Fecha</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
    } catch (e) {
        listContainer.innerHTML = `<p style="color:red">Error cargando archivados: ${e.message}</p>`;
    }
};

window.resetArchivadosFiltros = function() {
    ['tks-arch-filter-cliente','tks-arch-filter-cat','tks-arch-filter-estado',
     'tks-arch-filter-desde','tks-arch-filter-hasta'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    window.loadArchivados();
};

window.cerrarAsignarClienteModal = function() {
    const m = document.getElementById('tks-arch-asignar-modal');
    if (m) m.remove();
};

window.buscarClientesModal = async function() {
    const q = (document.getElementById('tks-arch-asignar-search')?.value || '').trim();
    const resultsEl = document.getElementById('tks-arch-asignar-results');
    const countEl = document.getElementById('tks-arch-asignar-count');
    if (!resultsEl) return;

    resultsEl.innerHTML = '<div style="padding:0.5rem;opacity:0.6"><i class="fas fa-circle-notch fa-spin"></i> Buscando...</div>';
    try {
        const qs = q ? `?q=${encodeURIComponent(q)}&limit=20` : '?limit=100';
        const data = await fetchApi('/api/tks/customers/search' + qs);
        const items = data?.items || [];
        if (countEl) countEl.textContent = `${items.length} cliente(s)`;
        if (!items.length) {
            resultsEl.innerHTML = '<div style="padding:0.5rem;opacity:0.6">Sin resultados</div>';
            return;
        }
        resultsEl.innerHTML = items.map(c => {
            const nombre = TksUI.escapeHtml(c.name || c.legal_name || c.id);
            const rut = c.vat_id ? `<span style="font-size:0.8rem;opacity:0.6"> · ${TksUI.escapeHtml(c.vat_id)}</span>` : '';
            return `<div class="tks-assoc-result-item" style="display:flex;justify-content:space-between;align-items:center;padding:0.5rem 0.75rem;border-bottom:1px solid var(--tks-border);cursor:pointer"
                        onmouseover="this.style.background='var(--tks-surface-hover)'" onmouseout="this.style.background=''"
                        onclick="window.confirmarAsignarCliente('${TksUI.escapeHtml(c.id)}', '${nombre}')">
                <span>${nombre}${rut}</span>
                <button class="tks-btn tks-btn-primary tks-btn-sm">Seleccionar</button>
            </div>`;
        }).join('');
    } catch (e) {
        resultsEl.innerHTML = `<div style="color:red;padding:0.5rem">Error: ${e.message}</div>`;
    }
};

window.confirmarAsignarCliente = async function(clienteId, clienteNombre) {
    const modal = document.getElementById('tks-arch-asignar-modal');
    if (!modal) return;
    const ticketId = modal.dataset.ticketId;
    const origenEmail = modal.dataset.origenEmail;

    try {
        await fetchApi(`/api/tks/tickets/${ticketId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ customer_id: clienteId, cliente_nombre: clienteNombre })
        });

        window.cerrarAsignarClienteModal();

        // Asociar masivamente otros tickets del mismo email/dominio
        if (origenEmail && origenEmail.includes('@')) {
            const dominio = origenEmail.split('@')[1];
            const bulkResult = await fetchApi('/api/tks/tickets/bulk-assign-customer', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ origen_email: origenEmail, customer_id: clienteId, customer_name: clienteNombre })
            });
            const totalExtra = (bulkResult?.updated || 0) - 1; // -1 porque el ticket actual ya fue asignado
            if (totalExtra > 0) {
                window.showToast && window.showToast(`${totalExtra} ticket(s) adicionales del mismo dominio también asignados a ${clienteNombre}`, 'info');
            }

            // Proponer crear regla de dominio para futuros tickets
            const crearRegla = window.confirm(
                `¿Crear regla automática para "@${dominio}"?\n\nFuturos tickets de ese dominio se asignarán automáticamente a ${clienteNombre}.`
            );
            if (crearRegla) {
                await fetchApi('/api/tks/settings/routing-rules', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        match_type: 'domain',
                        match_value: dominio,
                        customer_id: clienteId,
                        customer_name: clienteNombre,
                        categoria: '',
                        is_active: true
                    })
                });
                window.showToast && window.showToast(`Regla creada para @${dominio}`, 'success');
            }
        }

        window.showToast && window.showToast('Cliente asignado correctamente', 'success');
        window.loadArchivados();
    } catch (e) {
        window.showToast && window.showToast('Error asignando cliente: ' + e.message, 'error');
    }
};

window.abrirAsignarCliente = async function(ticketId, origenEmail, tituloTicket) {
    document.getElementById('tks-arch-asignar-modal')?.remove();
    document.body.insertAdjacentHTML('beforeend',
        TksUI.renderAsignarClienteModal(ticketId, origenEmail, tituloTicket)
    );
    const modal = document.getElementById('tks-arch-asignar-modal');
    modal.dataset.ticketId = ticketId;
    modal.dataset.origenEmail = origenEmail || '';
    modal.addEventListener('click', e => { if (e.target === modal) window.cerrarAsignarClienteModal(); });
    // Carga inicial con todos los clientes
    window.buscarClientesModal();
    document.getElementById('tks-arch-asignar-search')?.focus();
};

window.exportarReporteCliente = async function() {
    const sel = document.getElementById('tks-reporte-cliente-select');
    const cliente = (sel?.value || '').trim();
    const clienteNombre = sel?.options[sel.selectedIndex]?.text || cliente;
    const desde = (document.getElementById('tks-reporte-desde')?.value || '').trim();
    const hasta = (document.getElementById('tks-reporte-hasta')?.value || '').trim();
    const resultEl = document.getElementById('tks-reporte-resultado');

    if (!cliente) {
        if (resultEl) resultEl.innerHTML = '<p style="color:orange">Selecciona un cliente para generar el reporte.</p>';
        return;
    }
    if (resultEl) resultEl.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Generando...';

    try {
        const params = new URLSearchParams({ customer_id: cliente, limit: '500', status: 'cerrado,resuelto' });
        if (desde) params.set('created_after', desde);
        if (hasta) params.set('created_before', hasta);

        const data = await fetchApi('/api/tks/tickets?' + params.toString());
        const items = (data?.items || []).filter(t => ['cerrado','resuelto'].includes(t.estado));

        if (!items.length) {
            if (resultEl) resultEl.innerHTML = '<p style="opacity:0.6">Sin tickets para los filtros indicados.</p>';
            return;
        }

        const headers = ['Código','Título','Estado','Área','Cliente','Email Origen','Asignado a','Fecha Creación','Fecha Resolución'];
        const csvRows = [headers.join(',')];
        items.forEach(t => {
            csvRows.push([
                t.codigo || t.id,
                `"${(t.titulo||'').replace(/"/g,'""')}"`,
                t.estado || '',
                t.categoria || '',
                `"${(t.cliente_nombre||'').replace(/"/g,'""')}"`,
                t.origen_email || '',
                t.asignado_a || '',
                t.created_at ? t.created_at.slice(0,10) : '',
                t.resolved_at ? t.resolved_at.slice(0,10) : ''
            ].join(','));
        });

        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `reporte_${clienteNombre.replace(/\s+/g,'_')}_${desde||'inicio'}_${hasta||'hoy'}.csv`;
        a.click();
        URL.revokeObjectURL(url);

        if (resultEl) resultEl.innerHTML = `<p style="color:var(--tks-success)"><i class="fas fa-check"></i> ${items.length} tickets exportados.</p>`;
    } catch (e) {
        if (resultEl) resultEl.innerHTML = `<p style="color:red">Error generando reporte: ${e.message}</p>`;
    }
};
