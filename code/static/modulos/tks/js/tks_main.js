/**
 * Ticketera V3 — Controlador Principal
 * Orquesta estado, eventos, tabs, y comunicación entre API y UI.
 */
const TksMain = (() => {
    // ---- Estado ----
    let currentTab = 'dashboard';
    let selectedTicketId = null;
    let filters = { status: null, q: '', categoria: null, severidad: null };
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
    const cache = {
        dashboard: null,
        kanban: null,
        list: new Map(),
    };

    // ---- Elementos clave ----
    function el(id) { return document.getElementById(id); }
    function isFresh(entry) {
        return !!entry && (Date.now() - entry.ts) < CACHE_TTL_MS;
    }
    function clearDataCache() {
        cache.dashboard = null;
        cache.kanban = null;
        cache.list.clear();
    }

    // ---- INIT ----
    async function init() {
        if (isInitialized) return;
        isInitialized = true;

        bindTabs();
        loadTab('dashboard');
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
        else if (tab === 'lista') loadList(content, token);
        else if (tab === 'kanban') loadKanban(content, token);
    }

    // ---- DASHBOARD ----
    async function loadDashboard(container, token) {
        if (!container) return;
        if (isFresh(cache.dashboard)) {
            container.innerHTML = TksUI.renderDashboard(cache.dashboard.data);
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:200px;margin:1.5rem"></div></div>';
        try {
            const stats = await TksApi.getStats({ signal: controller.signal, timeoutMs: 10000 });
            if (token !== tabRequestToken || currentTab !== 'dashboard') return;
            cache.dashboard = { data: stats, ts: Date.now() };
            container.innerHTML = TksUI.renderDashboard(stats);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'dashboard') return;
            container.innerHTML = `<div class="tks-dashboard"><p style="color:red">Error cargando stats: ${e.message}</p></div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    // ---- LISTA ----
    async function loadList(container, token) {
        if (!container) return;
        container.innerHTML = `
        <div class="tks-list-layout">
            <div class="tks-list-panel">
                <div class="tks-toolbar">
                    <input class="tks-search" id="tks-search-input" placeholder="🔍 Buscar tickets..." value="${filters.q}">
                    <button class="tks-btn tks-btn-primary tks-btn-icon" onclick="TksMain.openCreateModal()" title="Nuevo Ticket"><i class="fas fa-plus"></i></button>
                </div>
                <div class="tks-filter-row" id="tks-filters">
                    <button class="tks-filter-chip ${!filters.status ? 'active' : ''}" data-filter-status="">Todos</button>
                    <button class="tks-filter-chip ${filters.status === 'abierto' ? 'active' : ''}" data-filter-status="abierto">Abierto</button>
                    <button class="tks-filter-chip ${filters.status === 'en_progreso' ? 'active' : ''}" data-filter-status="en_progreso">En Progreso</button>
                    <button class="tks-filter-chip ${filters.status === 'resuelto' ? 'active' : ''}" data-filter-status="resuelto">Resuelto</button>
                    <button class="tks-filter-chip ${filters.status === 'cerrado' ? 'active' : ''}" data-filter-status="cerrado">Cerrado</button>
                </div>
                <div class="tks-filter-row" id="tks-cat-filters">
                    <button class="tks-filter-chip ${!filters.categoria ? 'active' : ''}" data-filter-cat="">Todas</button>
                    <button class="tks-filter-chip ${filters.categoria === 'redes' ? 'active' : ''}" data-filter-cat="redes">🌐 Redes</button>
                    <button class="tks-filter-chip ${filters.categoria === 'sistemas' ? 'active' : ''}" data-filter-cat="sistemas">💻 Sistemas</button>
                    <button class="tks-filter-chip ${filters.categoria === 'ejecucion' ? 'active' : ''}" data-filter-cat="ejecucion">🔧 Ejecución</button>
                    <button class="tks-filter-chip ${filters.categoria === 'admin' ? 'active' : ''}" data-filter-cat="admin">📋 Admin</button>
                </div>
                <div class="tks-items-list" id="tks-items-list">
                    <div class="tks-skeleton" style="height:60px;margin:0.5rem"></div>
                    <div class="tks-skeleton" style="height:60px;margin:0.5rem"></div>
                    <div class="tks-skeleton" style="height:60px;margin:0.5rem"></div>
                </div>
            </div>
            <div class="tks-detail-panel" id="tks-detail-panel">
                <div class="tks-detail-empty"><span>Selecciona un ticket</span></div>
            </div>
        </div>`;

        // Bind search
        const searchInput = el('tks-search-input');
        searchInput.addEventListener('input', () => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                filters.q = searchInput.value.trim();
                refreshList(token);
            }, 300);
        });

        // Bind status filters
        el('tks-filters').querySelectorAll('.tks-filter-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                filters.status = chip.dataset.filterStatus || null;
                el('tks-filters').querySelectorAll('.tks-filter-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                refreshList(token);
            });
        });

        // Bind category filters
        el('tks-cat-filters').querySelectorAll('.tks-filter-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                filters.categoria = chip.dataset.filterCat || null;
                el('tks-cat-filters').querySelectorAll('.tks-filter-chip').forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                refreshList(token);
            });
        });

        refreshList(token);
    }

    function renderListItems(listEl, items) {
        if (!items || items.length === 0) {
            listEl.innerHTML = '<div style="padding:2rem;text-align:center;color:var(--tks-text-muted)">Sin tickets</div>';
            return;
        }

        listEl.innerHTML = items.map(t => TksUI.renderTicketItem(t)).join('');

        listEl.querySelectorAll('.tks-item').forEach(item => {
            item.addEventListener('click', () => {
                listEl.querySelectorAll('.tks-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                openDetail(parseInt(item.dataset.id));
            });
        });

        if (selectedTicketId) {
            const sel = listEl.querySelector(`.tks-item[data-id="${selectedTicketId}"]`);
            if (sel) sel.classList.add('active');
        }
    }

    async function refreshList(token = tabRequestToken) {
        const listEl = el('tks-items-list');
        if (!listEl || currentTab !== 'lista') return;
        const listFilters = { ...filters, limit: DEFAULT_LIST_LIMIT };
        const cacheKey = JSON.stringify(listFilters);
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

            const items = data.items || [];
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
            listEl.innerHTML = `<div style="padding:1rem;color:red">Error: ${e.message}</div>`;
        } finally {
            if (listAbortController === controller) {
                listAbortController = null;
            }
        }
    }

    // ---- DETAIL ----
    async function openDetail(ticketId) {
        selectedTicketId = ticketId;
        const reqToken = ++detailRequestToken;
        const panel = el('tks-detail-panel');
        if (!panel) return;
        if (detailAbortController) detailAbortController.abort();
        const controller = new AbortController();
        detailAbortController = controller;

        panel.classList.add('open');
        panel.innerHTML = '<div class="tks-detail-empty"><div class="tks-skeleton" style="height:200px;width:80%;margin:2rem auto"></div></div>';

        try {
            const [ticket, eventosData, emailsData] = await Promise.all([
                TksApi.getTicket(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getEventos(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getTicketEmails(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
            ]);
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId || currentTab !== 'lista') return;
            panel.innerHTML = TksUI.renderDetail(ticket, eventosData.items || [], emailsData.items || []);
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId || currentTab !== 'lista') return;
            panel.innerHTML = `<div class="tks-detail-empty"><span style="color:red">Error: ${e.message}</span></div>`;
        } finally {
            if (detailAbortController === controller) {
                detailAbortController = null;
            }
        }
    }

    // ---- ACTIONS ----
    async function changeStatus(ticketId, newStatus) {
        try {
            await TksApi.updateTicket(ticketId, { estado: newStatus });
            clearDataCache();
            if (window.showToast) window.showToast(`Estado cambiado a ${newStatus}`, 'success');
            if (currentTab === 'lista') {
                refreshList();
                openDetail(ticketId);
            } else {
                loadTab(currentTab, { force: true });
            }
        } catch (e) {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
        }
    }

    async function addNote(ticketId) {
        const input = el('tks-note-input');
        if (!input) return;
        const text = input.value.trim();
        if (!text) return;

        try {
            await TksApi.addEvento(ticketId, { evento: 'nota', detalle: text });
            clearDataCache();
            input.value = '';
            openDetail(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
        }
    }

    async function replyByEmail(ticketId) {
        const input = el('tks-email-reply-input');
        if (!input) return;
        const mensaje = input.value.trim();
        if (!mensaje) {
            if (window.showToast) window.showToast('Escribe un mensaje antes de enviar el correo', 'warning');
            return;
        }

        const fileInput = el('tks-email-reply-files');
        const files = fileInput ? fileInput.files : [];

        const sendBtn = el('tks-email-reply-send-btn');
        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.style.opacity = '0.7';
            sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
        }

        try {
            let body;
            // Si hay archivos, usar FormData
            if (files.length > 0) {
                body = new FormData();
                body.append('mensaje', mensaje);
                for (let i = 0; i < files.length; i++) {
                    body.append('files', files[i]);
                }
            } else {
                // Modo compatible anterior o Form Data simple
                body = new FormData();
                body.append('mensaje', mensaje);
            }

            const result = await TksApi.replyByEmail(ticketId, body, { timeoutMs: 60000 });
            clearDataCache();
            input.value = '';
            if (fileInput) fileInput.value = '';

            if (window.showToast) {
                if (result?.duplicate_skipped) {
                    window.showToast('Se evitó un correo duplicado; ya estaba enviado o en proceso', 'info');
                } else {
                    window.showToast('Correo enviado al cliente', 'success');
                }
            }
            openDetail(ticketId);
        } catch (e) {
            if (window.showToast) window.showToast(`Error enviando correo: ${e.message}`, 'error');
        } finally {
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.style.opacity = '';
                sendBtn.innerHTML = '<i class="fas fa-envelope"></i> Enviar correo';
            }
        }
    }

    function openReassign(ticketId) {
        const user = prompt('Nombre de usuario para reasignar:');
        if (!user) return;
        TksApi.updateTicket(ticketId, { asignado_a: user.trim() }).then(() => {
            clearDataCache();
            if (window.showToast) window.showToast(`Reasignado a ${user}`, 'success');
            openDetail(ticketId);
            refreshList();
        }).catch(e => {
            if (window.showToast) window.showToast(`Error: ${e.message}`, 'error');
        });
    }

    // ---- KANBAN ----
    async function loadKanban(container, token) {
        if (!container) return;
        if (isFresh(cache.kanban)) {
            container.innerHTML = TksUI.renderKanban(cache.kanban.data);
            bindKanbanDrop();
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-kanban-board"><div class="tks-skeleton" style="height:200px;flex:1"></div></div>';
        try {
            const data = await TksApi.getTablero({ signal: controller.signal, timeoutMs: 10000 });
            if (token !== tabRequestToken || currentTab !== 'kanban') return;
            cache.kanban = { data: data.kanban, ts: Date.now() };
            container.innerHTML = TksUI.renderKanban(data.kanban);
            bindKanbanDrop();
        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (token !== tabRequestToken || currentTab !== 'kanban') return;
            container.innerHTML = `<div style="padding:1rem;color:red">Error: ${e.message}</div>`;
        } finally {
            if (panelAbortController === controller) {
                panelAbortController = null;
            }
        }
    }

    function onDragStart(event, ticketId) {
        event.dataTransfer.setData('text/plain', ticketId);
        event.dataTransfer.effectAllowed = 'move';
    }

    function bindKanbanDrop() {
        document.querySelectorAll('.tks-kanban-col-body').forEach(col => {
            col.addEventListener('dragover', e => { e.preventDefault(); col.style.background = 'rgba(99,102,241,0.06)'; });
            col.addEventListener('dragleave', () => { col.style.background = ''; });
            col.addEventListener('drop', async e => {
                e.preventDefault();
                col.style.background = '';
                const ticketId = parseInt(e.dataTransfer.getData('text/plain'));
                const newStatus = col.dataset.status;
                if (!ticketId || !newStatus) return;
                await changeStatus(ticketId, newStatus);
            });
        });
    }

    // ---- MODAL CREAR ----
    function openCreateModal() {
        const modal = el('tks-create-modal');
        if (modal) modal.classList.add('open');
    }

    function closeCreateModal() {
        const modal = el('tks-create-modal');
        if (modal) modal.classList.remove('open');
    }

    async function submitCreate() {
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
        changeStatus,
        addNote,
        replyByEmail,
        openReassign,
        onDragStart,
        openCreateModal,
        closeCreateModal,
        submitCreate,
    };
})();

// Auto-init on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    if (window.initLogout) window.initLogout();
    document.title = "Mesa de Ayuda | Monstruo";
    TksMain.init();
});
