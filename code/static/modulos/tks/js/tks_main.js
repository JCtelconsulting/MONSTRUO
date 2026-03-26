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
            sistemas: 'Sistemas',
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

    function replyBlockedReason(ticket, permissions) {
        if (permissions?.canParticipate !== true) {
            return String(permissions?.blockedReason || '').trim();
        }
        const status = String(ticket?.estado || '').trim().toLowerCase();
        if (status !== 'en_progreso') {
            return 'Para responder el ticket al cliente, debes pasarlo primero a estado En Progreso';
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

    function buildSessionContext(sessionPayload = {}) {
        const roles = normalizeRoles(sessionPayload.roles, sessionPayload.role);
        const role = roles[0] || '';
        const user = normalizeUser(sessionPayload.user);
        const isAdmin = roles.some((item) => ROLE_MANAGEMENT.has(item));
        const isTech = roles.some((item) => ROLE_TECH.has(item));
        const isScopedTech = isTech && !isAdmin;
        const canViewOps = roles.some((item) => ROLE_OPS_READ.has(item));
        const canManageMessages = roles.some((item) => ROLE_MANAGEMENT.has(item));
        const canWrite = isAdmin || isTech;
        return {
            user,
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

    function ticketPermissions(ticket) {
        const role = normalizeRole(sessionCtx.role);
        const roles = normalizeRoles(sessionCtx.roles, role);
        const me = normalizeUser(sessionCtx.user);
        const assignee = normalizeUser(ticket?.asignado_a);
        const isUnassigned = !assignee;
        const isMine = !!assignee && assignee === me;
        console.log('[DEBUG] computing permissions', {
            user: sessionCtx.user,
            roles: sessionCtx.roles,
            roleArg: role,
            ticketAssignee: ticket?.asignado_a,
            me,
            assignee,
            isMine
        });
        const isAdmin = roles.some((r) => ROLE_MANAGEMENT.has(r));
        const isTech = roles.some((r) => ROLE_TECH.has(r));
        const isDispatcher = isAdmin || roles.some((r) => ROLE_DISPATCH.has(r));
        const canReassign = isAdmin;
        const canAssignTicket = isDispatcher && (isAdmin || isMine || isUnassigned);
        const canClaim = isTech && !isAdmin && isUnassigned;
        const canChangeStatus = isAdmin || (isTech && isMine);
        const canAddInternalNote = isAdmin || (isTech && isMine);
        const canParticipate = isTech && isMine;
        console.log('[DEBUG] permissions result', { isTech, isMine, canParticipate, roles, ROLE_TECH: Array.from(ROLE_TECH) });
        let blockedReason = '';
        if (!canParticipate) {
            if (role === ROLE_GERENCIA) {
                blockedReason = 'Gerencia: vista solo lectura en ticketera.';
            } else if (isAdmin) {
                blockedReason = 'Admin: puede gestionar y dejar nota interna, pero no responder correos.';
            } else if (isTech && isUnassigned) {
                blockedReason = 'Ticket sin asignar: toma el ticket para intervenir.';
            } else if (isTech && assignee && !isMine) {
                blockedReason = `Ticket asignado a ${ticket.asignado_a}.`;
            }
        }
        return {
            canReassign,
            canAssignTicket,
            canClaim,
            canChangeStatus,
            canAddInternalNote,
            canParticipate,
            blockedReason,
            isAdmin,
            isTech,
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
    function hasPendingDetailChanges() {
        const noteInput = el('tks-note-input');
        if (noteInput && String(noteInput.value || '').trim()) {
            return true;
        }

        const toInput = el('tks-draft-to');
        const ccInput = el('tks-draft-cc');
        const bccInput = el('tks-draft-bcc');
        const subjectInput = el('tks-draft-subject');
        const bodyInput = el('tks-draft-body');
        const fileInput = el('tks-draft-files');

        if (fileInput && fileInput.files && fileInput.files.length > 0) {
            return true;
        }

        if (toInput || ccInput || bccInput || subjectInput || bodyInput) {
            const snapshot = currentDraftSnapshot || {};
            const currentTo = String(toInput?.value || '').trim();
            const currentCc = String(ccInput?.value || '').trim();
            const currentBcc = String(bccInput?.value || '').trim();
            const currentSubject = String(subjectInput?.value || '').trim();
            const currentBody = String(bodyInput?.value || '');
            const snapTo = String(snapshot.to_addr || '').trim();
            const snapCc = String(snapshot.cc_addrs || '').trim();
            const snapBcc = String(snapshot.bcc_addrs || '').trim();
            const snapSubject = String(snapshot.subject || '').trim();
            const snapBody = String(snapshot.body_text || '');
            if (
                currentTo !== snapTo
                || currentCc !== snapCc
                || currentBcc !== snapBcc
                || currentSubject !== snapSubject
                || currentBody !== snapBody
            ) {
                return true;
            }
        }

        return false;
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
        const layout = document.querySelector('.tks-list-layout');
        if (layout) layout.classList.remove('detail-open');
        const panel = el('tks-detail-panel');
        if (panel) {
            panel.style.display = 'none';
            panel.innerHTML = '<div class="tks-detail-empty"><span>Selecciona un ticket</span></div>';
        }
        ['tks-draft-review-modal', 'tks-reply-review-modal', 'tks-template-editor-modal'].forEach((modalId) => {
            const modal = el(modalId);
            if (modal) modal.remove();
        });
        const listPanel = el('tks-list-panel');
        if (listPanel) listPanel.style.display = '';

        stopAutoProgressTimer();
        document.querySelectorAll('.tks-row.active').forEach(r => r.classList.remove('active'));
        resetDraftState();
        selectedTicketId = null;
        selectedTicket = null;
        if (!silent && currentTab === 'lista') {
            resetListFilters();
            loadTab('lista', { force: true });
        }
    }

    async function openDetail(ticketId, options = {}) {
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
        const reqToken = ++detailRequestToken;
        const panel = el('tks-detail-panel');
        const layout = document.querySelector('.tks-list-layout');
        const listPanel = el('tks-list-panel');
        if (!panel) return;

        if (layout) layout.classList.add('detail-open');
        if (listPanel) listPanel.style.display = 'none';
        panel.style.display = 'flex';

        if (detailAbortController) detailAbortController.abort();
        const controller = new AbortController();
        detailAbortController = controller;

        panel.innerHTML = `
            <div class="tks-detail-header">
                <button class="tks-btn-icon-sm tks-detail-close" onclick="TksMain.closeDetail()" title="Volver a la lista"><i class="fas fa-times"></i></button>
                <div class="tks-skeleton" style="height:30px;width:60%"></div>
            </div>
            <div style="padding:2rem"><div class="tks-loading-spinner">Cargando ticket...</div></div>
        `;

        try {
            const workflowPromise = TksApi.getTicketWorkflow(ticketId, { signal: controller.signal, timeoutMs: 10000 })
                .catch((err) => {
                    if (err?.name === 'AbortError') throw err;
                    return { allowed_next: [] };
                });
            const [ticket, eventosData, emailsData, attachmentsData, workflowData] = await Promise.all([
                TksApi.getTicket(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getEventos(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getTicketEmails(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getTicketAttachments(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                workflowPromise,
            ]);
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId) return;
            selectedTicket = ticket;
            currentWorkflow = workflowData || {};
            const permissions = ticketPermissions(ticket);
            currentDraftSnapshot = buildReplySnapshot(ticket);
            currentDraftMeta = {
                canEdit: permissions.canParticipate === true && String(ticket?.estado || '').trim().toLowerCase() === 'en_progreso',
                blockedReason: replyBlockedReason(ticket, permissions),
                heartbeatSeconds: 60,
            };
            stopDraftHeartbeat();

            const html = TksUI.renderDetail(
                ticket,
                eventosData.items || [],
                emailsData.items || [],
                attachmentsData.items || [],
                {
                    ...permissions,
                    currentUser: sessionCtx.user,
                    currentRole: sessionCtx.role,
                    composerMode: detailActiveTab,
                    draft: currentDraftSnapshot,
                    draftMeta: currentDraftMeta,
                    hasDraftLockToken: !!draftLockToken,
                    workflow: currentWorkflow,
                }
            );
            panel.innerHTML = html;
            hydrateAssigneePicker(ticket, permissions);
            bindReplyComposer();
            scrollTimelineToBottom();
            switchComposerMode(detailActiveTab);
            scheduleAutoProgress(ticket, permissions, currentWorkflow);
            startResueltoCountdown();
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
            const [eventosData, emailsData, attachmentsData] = await Promise.all([
                TksApi.getEventos(ticketId, { timeoutMs: 5000 }),
                TksApi.getTicketEmails(ticketId, { timeoutMs: 5000 }),
                TksApi.getTicketAttachments(ticketId, { timeoutMs: 5000 }),
            ]);

            // Re-renderizamos el detalle completo para mantener la consistencia del estado
            // pero preservando el modo del composer si el usuario estaba escribiendo (aunque openDetail ya lo hace).
            // Si el ticket cambió (ej: ya no es el mismo ID), abortamos.
            if (Number(selectedTicketId) !== Number(ticketId)) return;

            // Actualizamos la variable global 'selectedTicket' por si cambió algo en el refresh
            // Aunque aquí solo pedimos eventos/emails, es mejor re-pedir el ticket completo si queremos
            // que los badges de estado/asignado también se actualicen.
            const ticket = await TksApi.getTicket(ticketId, { timeoutMs: 5000 });
            selectedTicket = ticket;

            const permissions = ticketPermissions(ticket);
            currentDraftSnapshot = buildReplySnapshot(ticket);
            currentDraftMeta = {
                canEdit: permissions.canParticipate === true && String(ticket?.estado || '').trim().toLowerCase() === 'en_progreso',
                blockedReason: replyBlockedReason(ticket, permissions),
                heartbeatSeconds: 60,
            };
            const html = TksUI.renderDetail(
                ticket,
                eventosData.items || [],
                emailsData.items || [],
                attachmentsData.items || [],
                {
                    ...permissions,
                    currentUser: sessionCtx.user,
                    currentRole: sessionCtx.role,
                    composerMode: detailActiveTab,
                    draft: currentDraftSnapshot,
                    draftMeta: currentDraftMeta,
                    hasDraftLockToken: !!draftLockToken,
                    workflow: currentWorkflow,
                }
            );

            const panel = el('tks-detail-panel');
            if (panel) {
                panel.innerHTML = html;
                hydrateAssigneePicker(ticket, permissions);
                bindReplyComposer();
                // No scrolleamos obligatoriamente al final para no molestar si el usuario está leyendo arriba,
                // a menos que sea un refresh provocado por una acción propia.
            }
        } catch (e) {
            console.warn('[refreshDetailFeed] Failed:', e);
        }
    }

    // ---- ACTIONS ----
    async function changeStatus(ticketId, newStatus) {
        const perms = selectedTicket && Number(selectedTicket.id) === Number(ticketId)
            ? ticketPermissions(selectedTicket)
            : null;
        if (perms && !perms.canChangeStatus) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para cambiar estado', 'warning');
            return;
        }
        try {
            await TksApi.updateTicket(ticketId, { estado: newStatus });
            clearDataCache();
            if (window.showToast) window.showToast(`Estado cambiado a ${newStatus}`, 'success');
            if (currentTab === 'lista') {
                refreshList();
                openDetail(ticketId, { preserveTab: true });
            } else {
                loadTab(currentTab, { force: true });
            }
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
        const perms = selectedTicket && Number(selectedTicket.id) === Number(ticketId)
            ? ticketPermissions(selectedTicket)
            : null;
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
            if (currentTab === 'lista') {
                refreshList();
                openDetail(ticketId, { preserveTab: true });
                // Gatillar un segundo refresco tras 3 segundos para capturar correos asíncronos
                setTimeout(() => refreshDetailFeed(ticketId), 3000);
            } else {
                loadTab(currentTab, { force: true });
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

    async function applyStatusChange(ticketId) {
        const select = el('tks-status-next');
        if (!select) {
            if (window.showToast) window.showToast('No se encontró el selector de estado', 'warning');
            return;
        }
        const nextStatus = String(select.value || '').trim();
        if (!nextStatus) {
            if (window.showToast) window.showToast('Selecciona un estado destino', 'warning');
            return;
        }
        await changeStatus(ticketId, nextStatus);
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

    async function saveNotifyEmails(ticketId) {
        const perms = selectedTicket && Number(selectedTicket.id) === Number(ticketId)
            ? ticketPermissions(selectedTicket)
            : null;
        if (perms && !perms.canChangeStatus) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para configurar copiados', 'warning');
            return;
        }

        const input = el('tks-notify-emails');
        if (!input) return;
        const raw = String(input.value || '').trim();
        const parsed = parseNotifyEmailsInput(raw);
        if (parsed.invalid.length > 0) {
            if (window.showToast) window.showToast(`Correos inválidos: ${parsed.invalid.slice(0, 3).join(', ')}`, 'warning');
            return;
        }

        try {
            await TksApi.updateTicket(ticketId, { notify_emails: parsed.valid });
            clearDataCache();
            if (window.showToast) {
                window.showToast(
                    parsed.valid.length
                        ? `Copiados actualizados (${parsed.valid.length})`
                        : 'Lista de copiados vaciada',
                    'success'
                );
            }
            openDetail(ticketId, { preserveTab: true });
            refreshList();
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

    async function hydrateAssigneePicker(ticket, permissions) {
        const canAssign = permissions?.canAssignTicket === true;
        const pickerSelect = el('tks-assignee-select');
        const readonlyLabelEl = el('tks-assignee-readonly-label');
        const ticketId = Number(ticket?.id || 0);
        if (!ticketId) return;
        if (!pickerSelect && !readonlyLabelEl) return;

        const currentAssignee = normalizeUser(ticket?.asignado_a);
        const fallbackLabel = humanizeUsername(ticket?.asignado_a) || 'Sin asignar';
        if (pickerSelect) {
            pickerSelect.innerHTML = `<option value="${TksUI.escapeHtml(currentAssignee || '')}">${TksUI.escapeHtml(fallbackLabel)}</option>`;
            pickerSelect.disabled = true;
        }

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

            const options = [];
            const seen = new Set();

            // Siempre permitir la opción de desasignar
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

    async function applyAssigneeChange(ticketId) {
        const perms = selectedTicket && Number(selectedTicket.id) === Number(ticketId)
            ? ticketPermissions(selectedTicket)
            : null;
        if (perms && !perms.canAssignTicket) {
            if (window.showToast) window.showToast(perms.blockedReason || 'No tienes permiso para reasignar este ticket', 'warning');
            return;
        }

        const select = el('tks-assignee-select');
        if (!select) return;
        const nextAssignee = normalizeUser(select.value || '');
        // Eliminada restricción que impide desasignar (nextAssignee === '')

        const currentAssignee = normalizeUser(selectedTicket?.asignado_a);
        if (currentAssignee === nextAssignee) {
            return;
        }

        try {
            await TksApi.updateTicket(ticketId, { asignado_a: nextAssignee || null });
            clearDataCache();
            const selectedLabel = String(select.options?.[select.selectedIndex]?.textContent || '').trim() || (humanizeUsername(nextAssignee) || nextAssignee);
            const msg = nextAssignee ? `Ticket asignado a ${selectedLabel}` : 'Ticket desasignado';
            if (window.showToast) window.showToast(msg, 'success');
            if (currentTab === 'lista') {
                refreshList();
                openDetail(ticketId, { preserveTab: true });
                // Gatillar un segundo refresco para capturar el correo de asignación asíncrono
                setTimeout(() => refreshDetailFeed(ticketId), 3000);
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

    function renderReplyFileList() {
        const input = el('tks-draft-files');
        const list = el('tks-draft-file-list');
        if (!list) return;
        const files = Array.from(input?.files || []);
        if (!files.length) {
            list.innerHTML = '<div style="color:var(--tks-text-muted);font-size:0.8rem;">Sin adjuntos seleccionados</div>';
            return;
        }
        list.innerHTML = files.map((file) => `
            <div class="tks-draft-attachment-row">
                <span><i class="fas fa-paperclip"></i> ${TksUI.escapeHtml(file.name || 'adjunto')}</span>
            </div>
        `).join('');
    }

    function bindReplyComposer() {
        const input = el('tks-draft-files');
        if (!input) return;
        input.addEventListener('change', renderReplyFileList);
        renderReplyFileList();
    }

    function readDraftEditor(ticketId) {
        return {
            to_addr: el('tks-draft-to')?.value?.trim() || '',
            cc_addrs: el('tks-draft-cc')?.value?.trim() || '',
            bcc_addrs: el('tks-draft-bcc')?.value?.trim() || '',
            subject: el('tks-draft-subject')?.value?.trim() || '',
            body_text: el('tks-draft-body')?.value || '',
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

    async function deleteDraftAttachment(ticketId, attachmentId) {
        if (window.showToast) window.showToast('Los adjuntos ahora se envían directamente desde el selector local.', 'warning');
    }

    function closeDraftReviewModal() {
        const modal = el('tks-draft-review-modal');
        if (modal) modal.remove();
    }

    function openDraftReviewModal(ticketId) {
        const payload = readDraftEditor(ticketId);
        if (!payload.body_text.trim()) {
            if (window.showToast) window.showToast('El mensaje del borrador está vacío', 'warning');
            return;
        }
        if (!payload.to_addr || !payload.to_addr.includes('@')) {
            if (window.showToast) window.showToast('Correo destino inválido', 'warning');
            return;
        }

        closeDraftReviewModal();
        const attachments = Array.from(el('tks-draft-files')?.files || []);
        const ccPreview = String(payload.cc_addrs || '').trim();
        const bccPreview = String(payload.bcc_addrs || '').trim();
        const listItems = attachments.length
            ? attachments.map((att) => `<li>${TksUI.escapeHtml(att.name || 'adjunto')}</li>`).join('')
            : '<li>Sin adjuntos</li>';
        const html = `
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
        document.body.insertAdjacentHTML('beforeend', html);
    }

    async function reviewSendDraft(ticketId) {
        openDraftReviewModal(ticketId);
    }

    async function confirmSendDraft(ticketId) {
        const ticket = selectedTicket && Number(selectedTicket?.id) === Number(ticketId) ? selectedTicket : null;
        const permissions = ticket ? ticketPermissions(ticket) : null;
        if (permissions && !permissions.canParticipate) {
            if (window.showToast) window.showToast(permissions.blockedReason || 'No puedes responder este ticket', 'warning');
            return;
        }
        if (ticket && String(ticket.estado || '').trim().toLowerCase() !== 'en_progreso') {
            if (window.showToast) window.showToast('Para responder el ticket al cliente, debes pasarlo primero a estado En Progreso', 'warning');
            return;
        }

        const payload = readDraftEditor(ticketId);
        const filesInput = el('tks-draft-files');
        const files = Array.from(filesInput?.files || []);
        const formData = new FormData();
        formData.append('mensaje', payload.body_text);
        formData.append('asunto', payload.subject);
        formData.append('to_addr', payload.to_addr);
        formData.append('cc_addrs', payload.cc_addrs);
        formData.append('bcc_addrs', payload.bcc_addrs);
        files.forEach((file) => formData.append('files', file));

        try {
            await TksApi.replyByEmail(ticketId, formData, { timeoutMs: 60000 });
            closeDraftReviewModal();
            clearDataCache();
            stopDraftHeartbeat();
            draftLockToken = '';
            detailActiveTab = 'reply';
            if (window.showToast) window.showToast('Correo enviado al cliente', 'success');
            openDetail(ticketId, { preserveTab: true });
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

    async function takeTicket(ticketId) {
        try {
            await TksApi.claimTicket(ticketId);
            clearDataCache();
            if (window.showToast) window.showToast('Ticket tomado correctamente', 'success');
            if (currentTab === 'lista') {
                refreshList();
                openDetail(ticketId, { preserveTab: true });
            }
        } catch (e) {
            if (window.showToast) window.showToast(`No se pudo tomar ticket: ${e.message}`, 'error');
        }
    }

    // ---- KANBAN ----
    async function loadKanban(container, token) {
        if (!container) return;
        if (isFresh(cache.kanban)) {
            container.innerHTML = TksUI.renderKanban(
                scopeKanbanDataForSession(cache.kanban.data),
                { canDrag: sessionCtx.isAdmin }
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
                { canDrag: sessionCtx.isAdmin }
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

    // ---- OPS ----
    async function loadOps(container, token) {
        const renderOpsContainer = (data) => `
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
                TksApi.listJiraRuns({ limit: 10 }, { signal: controller.signal, timeoutMs: 12000 }),
                TksApi.getJiraReconciliationDaily({ signal: controller.signal, timeoutMs: 12000 }),
                TksApi.listParallelKpiDaily({ signal: controller.signal, timeoutMs: 12000 }),
                TksApi.listComplianceExportRuns({ signal: controller.signal, timeoutMs: 12000 }),
            ]);
            if (token !== tabRequestToken || currentTab !== 'ops') return;

            const data = {
                queue: settled[0]?.status === 'fulfilled' ? settled[0].value : {},
                channels: settled[1]?.status === 'fulfilled' ? settled[1].value : {},
                channelNotifications: settled[2]?.status === 'fulfilled' ? settled[2].value : { items: [] },
                jiraRuns: settled[3]?.status === 'fulfilled' ? settled[3].value : { items: [] },
                reconciliation: settled[4]?.status === 'fulfilled' ? settled[4].value : {},
                parallelKpi: settled[5]?.status === 'fulfilled' ? settled[5].value : { items: [] },
                complianceExportRuns: settled[6]?.status === 'fulfilled' ? settled[6].value : { items: [] },
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

    function bindKanbanDrop() {
        if (!sessionCtx.isAdmin) return;
        document.querySelectorAll('.tks-kanban-col-body').forEach(col => {
            col.addEventListener('dragover', e => { e.preventDefault(); col.style.background = 'rgba(99,102,241,0.06)'; });
            col.addEventListener('dragleave', () => { col.style.background = ''; });
            col.addEventListener('drop', async e => {
                e.preventDefault();
                col.style.background = '';
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
            await fetchApi('/api/tks/customers/associate-email', {
                method: 'POST',
                body: JSON.stringify({
                    email: assocEmail,
                    customer_id: custId,
                    customer_name: custName
                })
            });

            if (window.showToast) window.showToast('Vinculación exitosa', 'success');
            closeAssociateModal();
            refreshList(); // Reload list to see changes
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
        onDragStart,
        openCreateModal,
        closeCreateModal,
        submitCreate,
        retryChannel,
        refreshOps,
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
