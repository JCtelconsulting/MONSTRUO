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
        ops: null,
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
        cache.ops = null;
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
        else if (tab === 'ops') loadOps(content, token);
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
            <div class="tks-detail-backdrop" id="tks-detail-backdrop" onclick="TksMain.closeDetail()"></div>
            <div class="tks-list-panel">
                <div class="tks-toolbar">
                    <input class="tks-search" id="tks-search-input" placeholder="🔍 Buscar tickets por título, código o cliente..." value="${filters.q}">
                    <button class="tks-btn tks-btn-ghost tks-btn-icon" onclick="TksMain.refreshList()" title="Recargar"><i class="fas fa-sync-alt"></i></button>
                </div>
                <!-- Filters Row (Status) -->
                <div class="tks-filter-row" id="tks-filters" style="padding-top:0.8rem">
                    <button class="tks-filter-chip ${!filters.status ? 'active' : ''}" data-filter-status="">Todos</button>
                    <button class="tks-filter-chip ${filters.status === 'abierto' ? 'active' : ''}" data-filter-status="abierto">Abiertos</button>
                    <button class="tks-filter-chip ${filters.status === 'en_progreso' ? 'active' : ''}" data-filter-status="en_progreso">En Progreso</button>
                    <button class="tks-filter-chip ${filters.status === 'resuelto' ? 'active' : ''}" data-filter-status="resuelto">Resueltos</button>
                </div>
                 <!-- Filters Row (Category) -->
                <div class="tks-filter-row" id="tks-cat-filters">
                    <button class="tks-filter-chip ${!filters.categoria ? 'active' : ''}" data-filter-cat="">Todas las áreas</button>
                    <button class="tks-filter-chip ${filters.categoria === 'redes' ? 'active' : ''}" data-filter-cat="redes">🌐 Redes</button>
                    <button class="tks-filter-chip ${filters.categoria === 'sistemas' ? 'active' : ''}" data-filter-cat="sistemas">💻 Sistemas</button>
                    <button class="tks-filter-chip ${filters.categoria === 'ejecucion' ? 'active' : ''}" data-filter-cat="ejecucion">🔧 Ejecución</button>
                    <button class="tks-filter-chip ${filters.categoria === 'admin' ? 'active' : ''}" data-filter-cat="admin">📋 Admin</button>
                </div>
                <div class="tks-items-list" id="tks-items-list">
                    <div class="tks-skeleton" style="height:60px;margin:1rem"></div>
                    <div class="tks-skeleton" style="height:60px;margin:1rem"></div>
                    <div class="tks-skeleton" style="height:60px;margin:1rem"></div>
                </div>
            </div>
            
            <!-- DRAWER DETALLE -->
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
    function closeDetail() {
        const panel = el('tks-detail-panel');
        const backdrop = el('tks-detail-backdrop');
        if (panel) panel.classList.remove('open');
        if (backdrop) backdrop.classList.remove('visible');

        // Deseleccionar
        document.querySelectorAll('.tks-row.active').forEach(r => r.classList.remove('active'));
        selectedTicketId = null;
    }

    async function openDetail(ticketId) {
        selectedTicketId = ticketId;
        const reqToken = ++detailRequestToken;
        const panel = el('tks-detail-panel');
        const backdrop = el('tks-detail-backdrop');
        if (!panel) return;

        // Show drawer immediately (loading state)
        panel.classList.add('open');
        if (backdrop) backdrop.classList.add('visible');

        if (detailAbortController) detailAbortController.abort();
        const controller = new AbortController();
        detailAbortController = controller;

        panel.innerHTML = `
            <div class="tks-detail-header">
                <button class="tks-btn-icon-sm" onclick="TksMain.closeDetail()" style="float:right"><i class="fas fa-times"></i></button>
                <div class="tks-skeleton" style="height:30px;width:60%"></div>
            </div>
            <div style="padding:2rem"><div class="tks-loading-spinner">Cargando ticket...</div></div>
        `;

        try {
            const [ticket, eventosData, emailsData, attachmentsData] = await Promise.all([
                TksApi.getTicket(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getEventos(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getTicketEmails(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
                TksApi.getTicketAttachments(ticketId, { signal: controller.signal, timeoutMs: 10000 }),
            ]);
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId) return;

            // Render detail but inject CLOSE BUTTON
            const html = TksUI.renderDetail(
                ticket,
                eventosData.items || [],
                emailsData.items || [],
                attachmentsData.items || []
            );

            // Hacky string injection to add Close Button to header if not present (TksUI could be updated, but this works for now)
            // or better: TksUI.renderDetail could accept a "closeAction"
            // Let's update TksUI.renderDetail signature or just prepend the button in the header.
            panel.innerHTML = html;

            // Add Close Button to header manually
            const header = panel.querySelector('.tks-detail-header');
            if (header) {
                const closeBtn = document.createElement('button');
                closeBtn.className = 'tks-btn-icon-sm';
                closeBtn.innerHTML = '<i class="fas fa-times"></i>';
                closeBtn.title = 'Cerrar pasarela';
                closeBtn.style.float = 'right';
                closeBtn.style.fontSize = '1.2rem';
                closeBtn.onclick = closeDetail;
                header.prepend(closeBtn);
            }

        } catch (e) {
            if (e?.name === 'AbortError') return;
            if (reqToken !== detailRequestToken || selectedTicketId !== ticketId) return;
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

    // ---- OPS ----
    async function loadOps(container, token) {
        const renderOpsContainer = (data) => `
            <div style="display:flex;justify-content:flex-end;gap:.5rem;margin:.5rem 0 1rem 0;">
                <button class="tks-btn tks-btn-ghost tks-btn-sm" onclick="TksMain.recoverStaleJobs()">Recuperar huérfanos</button>
                <button class="tks-btn tks-btn-primary tks-btn-sm" onclick="TksMain.refreshOps()">Actualizar</button>
            </div>
            ${TksUI.renderOps(data)}
        `;
        if (!container) return;
        if (isFresh(cache.ops)) {
            container.innerHTML = renderOpsContainer(cache.ops.data);
            return;
        }
        const controller = new AbortController();
        panelAbortController = controller;
        container.innerHTML = '<div class="tks-dashboard"><div class="tks-skeleton" style="height:220px;margin:1.5rem"></div></div>';
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
            container.innerHTML = `<div class="tks-dashboard"><p style="color:red">Error cargando Operación: ${e.message}</p></div>`;
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
            if (window.showToast) window.showToast(`Recover stale ejecutado: ${recovered} jobs`, 'success');
            refreshOps();
        } catch (e) {
            if (window.showToast) window.showToast(`Error al recuperar huérfanos: ${e.message}`, 'error');
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

    // ---- CLIENT ASSOCIATION ----
    let assocEmail = '';

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
            if (input) input.focus();
        }, 100);
    }

    function closeAssociateModal() {
        const modal = el('tks-associate-modal');
        if (modal) {
            modal.classList.remove('open');
            setTimeout(() => modal.remove(), 300);
        }
    }

    async function searchClients() {
        const q = el('tks-assoc-search').value.trim();
        const resultsEl = el('tks-assoc-results');
        if (!q || q.length < 2) {
            if (window.showToast) window.showToast('Escribe al menos 2 caracteres', 'warning');
            return;
        }

        resultsEl.style.display = 'block';
        resultsEl.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--tks-text-muted)">Buscando...</div>';

        try {
            const data = await fetchApi(`/api/tks/customers/search?q=${encodeURIComponent(q)}`);
            const items = data.items || [];

            if (items.length === 0) {
                resultsEl.innerHTML = '<div style="padding:1rem;text-align:center;color:var(--tks-text-muted)">No se encontraron clientes</div>';
                return;
            }

            resultsEl.innerHTML = items.map(c => `
                <div class="tks-assoc-item" onclick="TksMain.selectClient('${c.id}', '${escapeHtml(c.name).replace(/'/g, "\\'")}')" 
                     style="padding:0.8rem;border-bottom:1px solid var(--tks-border);cursor:pointer;transition:background 0.2s">
                    <div style="font-weight:600;color:var(--tks-text-main)">${escapeHtml(c.name)}</div>
                    <div style="font-size:0.8rem;color:var(--tks-text-muted)">RUT: ${escapeHtml(c.vat_id || 'N/A')}</div>
                </div>
            `).join('');

            // Add hover effect via JS/CSS or inline
            resultsEl.querySelectorAll('.tks-assoc-item').forEach(div => {
                div.addEventListener('mouseenter', () => div.style.background = 'rgba(255,255,255,0.05)');
                div.addEventListener('mouseleave', () => div.style.background = 'transparent');
            });

        } catch (e) {
            resultsEl.innerHTML = `<div style="padding:1rem;color:red">Error: ${e.message}</div>`;
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
        retryChannel,
        refreshOps,
        recoverStaleJobs,
        loadCustomer360,
        closeDetail,
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
        content.innerHTML = `<p style="color:red">Error cargando datos: ${e.message}</p>`;
        content.style.display = 'block';
    }
}

async function generatePaymentLink(customerId, amount) {
    const btn = event.target.closest('button');
    const originalText = btn.innerHTML;
    const resultDiv = document.getElementById('payment-link-result');

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generando...';
    resultDiv.style.display = 'none';

    try {
        const payload = { customer_id: customerId, amount: amount };
        const response = await window.fetchApi('/api/cobranza/payment-link', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        resultDiv.innerHTML = `
            <div style="background:rgba(0,255,100,0.1); border:1px solid #00c851; padding:1rem; border-radius:6px; margin-top:1rem">
                <div style="font-weight:bold; color:#00c851; margin-bottom:0.5rem"><i class="fas fa-check-circle"></i> Link generado</div>
                <div style="display:flex; gap:0.5rem">
                    <input type="text" readonly value="${response.payment_url}" style="flex:1; background:#111; border:1px solid #333; color:#eee; padding:4px; border-radius:4px" onclick="this.select()">
                    <button class="tks-btn tks-btn-sm" onclick="navigator.clipboard.writeText('${response.payment_url}')"><i class="fas fa-copy"></i></button>
                </div>
                <div style="font-size:0.75rem; opacity:0.7; margin-top:0.5rem">Expira: ${new Date(response.expires_at).toLocaleString()}</div>
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
