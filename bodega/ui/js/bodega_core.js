// bodega_core.js - State & Orchestration (PROTECTED)
var BodegaCore = (function () {
    const TAB_ALIASES = {
        inventory: 'inventario',
        inventario: 'inventario',
        catalog: 'catalogo',
        catalogo: 'catalogo',
        pending: 'pendientes',
        pendientes: 'pendientes',
        analysis: 'analisis',
        analisis: 'analisis'
    };

    const TAB_DOM_IDS = {
        inventario: { tab: ['tab-inventario', 'tab-inventory'], view: ['view-inventario', 'view-inventory'] },
        catalogo: { tab: ['tab-catalogo', 'tab-catalog'], view: ['view-catalogo', 'view-catalog'] },
        pendientes: { tab: ['tab-pendientes', 'tab-pending'], view: ['view-pendientes', 'view-pending'] },
        analisis: { tab: ['tab-analisis', 'tab-analysis'], view: ['view-analisis', 'view-analysis'] }
    };

    let state = {
        categories: [],
        currentTab: 'inventario',
        currentCatId: null,
        currentCatParentId: null,
        unassignedGlobalCount: 0,
        unassignedByCat: {},
        categoryCounts: { total: {}, direct: {} },
        catalogItemsCache: null,
        currentCatalogItems: [],
        selectedCatItems: new Set(),
        expandedNodes: new Set(),
        invSearchTimer: null,
        catSearchTimer: null
    };

    function coerceId(id) {
        if (id === null || id === undefined) return id;
        if (typeof id === 'string' && id !== '' && !Number.isNaN(Number(id))) return Number(id);
        return id;
    }

    function getActiveBaseCatId() {
        return coerceId(state.currentCatParentId || state.currentCatId);
    }

    function parseUnassignedId(id) {
        if (typeof id !== 'string') return null;
        if (!id.startsWith('unassigned:')) return null;
        const raw = id.split(':')[1];
        return coerceId(raw);
    }

    function getItemCategoryIds(item) {
        const ids = Array.isArray(item.categoria_ids)
            ? item.categoria_ids
            : (item.categoria_id ? [item.categoria_id] : []);
        return ids.map(coerceId).filter(id => id !== null && id !== undefined && id !== '');
    }

    function ensureCategoryModalHelper() {
        if (typeof window.CategoryTreeSelector !== 'function') {
            alert('CategoryTreeSelector no está disponible.');
            return null;
        }
        if (!window.categoryModalHelper) {
            window.categoryModalHelper = new window.CategoryTreeSelector('modal-parent-tree-container', {
                allowCreate: false,
                deferInit: true,
                onSelect: (node) => {
                    const parentIdInput = document.getElementById('modal-cat-parent-id');
                    const parentNameInput = document.getElementById('modal-cat-parent-name');
                    if (parentIdInput) parentIdInput.value = node.id;
                    if (parentNameInput) parentNameInput.value = node.nombre;
                }
            });
        }
        return window.categoryModalHelper;
    }

    function openCreateCategoryModal() {
        const helper = ensureCategoryModalHelper();
        if (!helper) return;
        if (state.categories && state.categories.length > 0) {
            helper.setCategories(state.categories);
        }
        const baseId = getActiveBaseCatId();
        if (baseId) {
            const node = state.categories.find(c => coerceId(c.id) === coerceId(baseId));
            helper.lastSelectedNode = node || null;
        } else {
            helper.lastSelectedNode = null;
        }
        helper.showCreateForm();
    }

    function ensureAssignCategoryModalHelper() {
        if (typeof window.CategoryTreeSelector !== 'function') {
            alert('CategoryTreeSelector no está disponible.');
            return null;
        }
        if (!window.assignPickerTree) {
            window.assignPickerTree = new window.CategoryTreeSelector('assign-tree-container', {
                allowCreate: false,
                deferInit: true,
                onSelect: (node) => {
                    const idInput = document.getElementById('assign-cat-id');
                    const nameInput = document.getElementById('assign-cat-name');
                    if (idInput) idInput.value = node.id;
                    if (nameInput) nameInput.value = node.nombre;
                }
            });
        }
        return window.assignPickerTree;
    }

    function openAssignCategoryModal(item) {
        const modal = document.getElementById('modal-assign-category');
        if (!modal) return alert('Modal de asignación no encontrado.');
        const helper = ensureAssignCategoryModalHelper();
        if (!helper) return;

        const items = Array.isArray(item) ? item : [item || state.currentCatalogItem].filter(Boolean);
        if (!items || items.length === 0) return alert('Selecciona uno o más items.');

        const nameEl = document.getElementById('assign-item-name');
        if (nameEl) {
            if (items.length === 1) {
                const rawName = (items[0].nombre || items[0].name || '').toString();
                nameEl.value = rawName ? (rawName.charAt(0).toUpperCase() + rawName.slice(1).toLowerCase()) : `Item ${items[0].id}`;
            } else {
                nameEl.value = `${items.length} items seleccionados`;
            }
        }

        const idInput = document.getElementById('assign-cat-id');
        const nameInput = document.getElementById('assign-cat-name');
        if (idInput) idInput.value = '';
        if (nameInput) nameInput.value = '-- Selecciona una categoría --';

        if (state.categories && state.categories.length > 0) {
            helper.setCategories(state.categories);
        }

        let saveBtn = document.getElementById('btn-assign-category-save');
        const newBtn = saveBtn.cloneNode(true);
        saveBtn.parentNode.replaceChild(newBtn, saveBtn);
        saveBtn = newBtn;

        saveBtn.onclick = async () => {
            const catIdRaw = document.getElementById('assign-cat-id').value;
            if (!catIdRaw) return alert('Selecciona una categoría.');
            const catId = parseInt(catIdRaw, 10);
            if (Number.isNaN(catId)) return alert('Categoría inválida.');

            try {
                for (const it of items) {
                    const currentIds = getItemCategoryIds(it);
                    for (const cid of currentIds) {
                        if (cid !== catId) {
                            await window.fetchApi(`/api/catalogo/items/${it.id}/categorias/${cid}`, {
                                method: 'DELETE'
                            });
                        }
                    }
                    if (!currentIds.includes(catId)) {
                        await window.fetchApi(`/api/catalogo/items/${it.id}/categorias`, {
                            method: 'POST',
                            body: { categoria_id: catId }
                        });
                    }
                    await window.fetchApi(`/api/catalogo/items/${it.id}`, {
                        method: 'PATCH',
                        body: { categoria_id: catId }
                    });
                }
                alert(`Movidos ${items.length} item(s) a la categoría seleccionada.`);
                modal.close();
                loadCatItems();
                clearCatalogSelection();
            } catch (e) {
                alert(e.message || 'Error moviendo categoría');
            }
        };

        modal.showModal();
    }

    function toggleCatalogSelection(id, checked) {
        const itemId = coerceId(id);
        if (!state.selectedCatItems) state.selectedCatItems = new Set();
        if (checked) state.selectedCatItems.add(itemId);
        else state.selectedCatItems.delete(itemId);
        updateSelectAllState();
        if (window.BodegaUI && window.BodegaUI.updateCatalogBulkUI) {
            window.BodegaUI.updateCatalogBulkUI(state.selectedCatItems.size);
        }
    }

    function handleCatSearch(value) {
        clearTimeout(state.catSearchTimer);
        state.catSearchTimer = setTimeout(() => {
            state.lastCatQuery = (value || '').trim();
            loadCatItems();
        }, 250);
    }

    function clearCatalogSelection() {
        if (!state.selectedCatItems) state.selectedCatItems = new Set();
        state.selectedCatItems.clear();
        document.querySelectorAll('.cat-item-checkbox').forEach(c => c.checked = false);
        updateSelectAllState();
        if (window.BodegaUI && window.BodegaUI.updateCatalogBulkUI) {
            window.BodegaUI.updateCatalogBulkUI(0);
        }
    }

    function toggleAllCatalogSelection(checked) {
        if (!state.selectedCatItems) state.selectedCatItems = new Set();
        const items = state.currentCatalogItems || [];
        if (checked) {
            items.forEach(it => state.selectedCatItems.add(coerceId(it.id)));
        } else {
            state.selectedCatItems.clear();
        }
        document.querySelectorAll('.cat-item-checkbox').forEach(c => {
            c.checked = checked;
        });
        if (window.BodegaUI && window.BodegaUI.updateCatalogBulkUI) {
            window.BodegaUI.updateCatalogBulkUI(state.selectedCatItems.size);
        }
        updateSelectAllState();
    }

    function updateSelectAllState() {
        const selectAll = document.getElementById('cat-select-all');
        if (!selectAll) return;
        const items = state.currentCatalogItems || [];
        if (items.length === 0) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
            return;
        }
        const selectedSet = state.selectedCatItems || new Set();
        const selectedCount = items.filter(it => selectedSet.has(coerceId(it.id))).length;
        selectAll.checked = selectedCount > 0 && selectedCount === items.length;
        selectAll.indeterminate = selectedCount > 0 && selectedCount < items.length;
    }

    function openAssignCategoryModalForSelection() {
        const ids = Array.from(state.selectedCatItems || []);
        if (!ids || ids.length === 0) return alert('Selecciona items primero.');
        const items = ids.map(id => state.catalogItemsById ? state.catalogItemsById[id] : null).filter(Boolean);
        if (items.length === 0) return alert('No se encontraron items para asignar.');
        openAssignCategoryModal(items);
    }

    function computeCategoryCounts(items) {
        const parentById = {};
        state.categories.forEach(c => { parentById[coerceId(c.id)] = coerceId(c.parent_id); });

        const total = {};
        const direct = {};

        items.forEach(it => {
            const ids = getItemCategoryIds(it);
            if (ids.length === 0) return;

            // Direct counts
            ids.forEach(id => {
                if (!id) return;
                direct[id] = (direct[id] || 0) + 1;
            });

            // Total counts (ancestors + self) once per item
            const ancestorSet = new Set();
            ids.forEach(id => {
                let cur = id;
                const safety = new Set();
                while (cur !== null && cur !== undefined && cur !== '' && !safety.has(cur)) {
                    ancestorSet.add(cur);
                    safety.add(cur);
                    cur = parentById[cur];
                }
            });

            ancestorSet.forEach(id => {
                total[id] = (total[id] || 0) + 1;
            });
        });

        return { total, direct };
    }

    function normalizeTab(tab) {
        return TAB_ALIASES[tab] || tab;
    }

    function setActiveTab(tab) {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        const ids = TAB_DOM_IDS[tab] ? TAB_DOM_IDS[tab].tab : [];
        let activated = false;
        ids.forEach(id => {
            const btn = document.getElementById(id);
            if (btn) {
                btn.classList.add('active');
                activated = true;
            }
        });
        if (!activated) {
            const dataBtn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
            if (dataBtn) dataBtn.classList.add('active');
        }
    }

    function setActiveView(tab) {
        document.querySelectorAll('.view-section').forEach(v => v.classList.remove('active'));
        const ids = TAB_DOM_IDS[tab] ? TAB_DOM_IDS[tab].view : [];
        let activated = false;
        ids.forEach(id => {
            const view = document.getElementById(id);
            if (view) {
                view.classList.add('active');
                activated = true;
            }
        });
        if (!activated) {
            const view = document.getElementById(`view-${tab}`);
            if (view) view.classList.add('active');
        }
    }

    // --- INIT ---
    function init() {
        console.log("Initializing Bodega Core v8 (Modular)...");

        // Export Helpers for HTML Attributes
        window.switchTab = switchTab;
        window.handleSearchInput = handleSearchInput;
        window.viewKardex = viewKardex;
        window.closeKardex = closeKardex;
        if (!window.loadInventory) window.loadInventory = loadInventory;
        if (!window.loadPending) window.loadPending = loadPending;

        // Initial Load
        syncStockOnEnter();
        if (document.getElementById('invTable')) loadInventory();
        if (document.getElementById('tree-container')) loadTree();

        // Setup Search Delegate
        if (!window.__search_delegated) {
            window.__search_delegated = true;
            document.addEventListener('input', (e) => {
                if (e.target && e.target.id === 'inv-search') {
                    handleSearchInput(e.target);
                }
            });
        }
    }

    async function syncStockOnEnter() {
        let didWork = false;
        const stockDone = sessionStorage.getItem('bodega_stock_sync_done') === '1';
        try {
            if (!stockDone) {
                await window.fetchApi('/api/bodega/sync_stock', { method: 'POST' });
                sessionStorage.setItem('bodega_stock_sync_done', '1');
                didWork = true;
            }
        } catch (e) {
            console.warn('Stock sync skipped:', e.message);
        }
        if (didWork) {
            setTimeout(() => loadInventory(state.lastQuery || ''), 1500);
        }
    }

    // --- TABS ---
    function switchTab(tab, opts = {}) {
        const normalized = normalizeTab(tab);
        state.currentTab = normalized;

        if (!opts.skipLoad && typeof window.loadBodegaTab === 'function') {
            window.loadBodegaTab(normalized);
            return;
        }

        setActiveTab(normalized);
        setActiveView(normalized);

        if (normalized === 'inventario') loadInventory();
        if (normalized === 'catalogo') {
            loadTree();
            loadCatItems();
        }
        if (normalized === 'pendientes') loadPending();
    }

    function onTabLoaded(tab) {
        switchTab(tab, { skipLoad: true });
    }

    // --- INVENTORY LOGIC ---
    function handleSearchInput(el) {
        if (el) el.style.borderColor = '#6610f2';
        clearTimeout(state.invSearchTimer);
        state.invSearchTimer = setTimeout(() => {
            if (el) el.style.borderColor = '#28a745';
            loadInventory(el ? el.value : '');
        }, 300);
    }

    async function loadInventory(qOverride) {
        const searchBox = document.getElementById('inv-search');
        const q = (qOverride !== undefined && qOverride !== null) ? qOverride : (searchBox ? searchBox.value : '');
        state.lastQuery = q;

        if (window.BodegaUI) {
            const tbody = document.querySelector('#invTable tbody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="6">Cargando...</td></tr>';
        }

        try {
            // Always fetch full list; filter client-side for consistency
            const res = await window.fetchApi(`/api/bodega/inventario_enriquecido?limit=3000`);
            const items = Array.isArray(res) ? res : (res.items || []);
            const qNorm = (q || '').trim().toLowerCase();
            const filtered = qNorm
                ? items.filter(it => {
                    const name = (it.name || it.nombre || it.raw_nombre || it.sku || '').toString().toLowerCase();
                    return name.includes(qNorm);
                })
                : items;
            const stats = res.kpis || {};
            const totalItemsCount = items.length;
            const mappedCount = items.filter(it => it && it.item_id).length;

            if (window.BodegaUI) {
                window.BodegaUI.renderInventoryTable(filtered, {
                    total_items: stats.total_items || res.total || totalItemsCount,
                    mapped: stats.mapped || res.mapped_count || mappedCount
                });
            }
        } catch (e) {
            console.error("Error loading inventory", e);
        }
    }

    async function viewKardex(sku) {
        if (!sku) return;
        const panel = document.getElementById('kardex-drawer');
        const subtitle = document.getElementById('kardex-subtitle');
        if (subtitle) subtitle.textContent = `Movimientos recientes: ${sku}`;
        if (panel) panel.classList.add('open');

        try {
            const rows = await window.fetchApi(`/api/bodega/products/${encodeURIComponent(sku)}/kardex?limit=50`);
            if (window.BodegaUI) window.BodegaUI.renderKardexTable(rows || []);
        } catch (e) {
            if (window.BodegaUI) window.BodegaUI.renderKardexTable([], e.message);
        }
    }

    function closeKardex() {
        const panel = document.getElementById('kardex-drawer');
        if (panel) panel.classList.remove('open');
    }

    // --- TREE LOGIC ---
    async function loadTree() {
        try {
            const res = await window.fetchApi('/api/catalogo/categorias?include_hidden=true');
            const cats = (res && res.items) ? res.items : (Array.isArray(res) ? res : []);
            state.categories = cats;
            state.hasSubcategories = state.categories.some(c => c.parent_id);
            if (state.catalogItemsCache) {
                state.categoryCounts = computeCategoryCounts(state.catalogItemsCache);
            }
            const activeBaseId = getActiveBaseCatId();
            // Process tree structure
            const rootNodes = buildNodes(null, 0);
            const nodes = [];
            if (!state.hasSubcategories && state.unassignedGlobalCount && state.unassignedGlobalCount > 0) {
                nodes.push({
                    id: 'unassigned',
                    nombre: `SIN ASIGNAR (${state.unassignedGlobalCount})`,
                    parent_id: null,
                    depth: 0,
                    expanded: false,
                    children: [],
                    isVirtual: true
                });
            }
            nodes.push(...rootNodes);

            if (window.BodegaUI) {
                const container = document.getElementById('tree-container');
                window.BodegaUI.renderCategoryTree(container, nodes);
            }
        } catch (e) { console.error(e); }
    }

    function buildNodes(parentId, depth) {
        let nodes = [];
        const activeBaseId = getActiveBaseCatId();
        state.categories
            .filter(c => c.parent_id === parentId)
            .sort((a, b) => {
                if (depth === 0) {
                    const order = ["BODEGA", "ARRIENDO", "BAJAS"];
                    const aName = (a.nombre || "").toUpperCase();
                    const bName = (b.nombre || "").toUpperCase();
                    const aIdx = order.indexOf(aName);
                    const bIdx = order.indexOf(bName);
                    if (aIdx !== -1 || bIdx !== -1) {
                        return (aIdx === -1 ? 999 : aIdx) - (bIdx === -1 ? 999 : bIdx);
                    }
                }
                return (a.nombre || "").localeCompare(b.nombre || ""); // Default sort
            })
            .forEach(c => {
                const expanded = state.expandedNodes.has(c.id);
                let node = { ...c, depth: depth, expanded: expanded, children: [] };
                const catId = coerceId(c.id);
                const counts = state.categoryCounts || { total: {}, direct: {} };
                node.countTotal = counts.total[catId] || 0;
                node.countDirect = counts.direct[catId] || 0;

                // Check if it has children (raw check)
                const hasChildren = state.categories.some(x => x.parent_id === c.id);
                if (hasChildren) {
                    node.children = [true]; // Just marker
                    if (expanded) {
                        // Recursion
                        const children = buildNodes(c.id, depth + 1);
                        nodes.push(node);
                        const unassignedCountForCat = state.unassignedByCat ? state.unassignedByCat[c.id] : 0;
                        if (expanded && activeBaseId === c.id && unassignedCountForCat > 0) {
                            nodes.push({
                                id: `unassigned:${c.id}`,
                                nombre: `SIN ASIGNAR (${unassignedCountForCat})`,
                                parent_id: c.id,
                                depth: depth + 1,
                                expanded: false,
                                children: [],
                                isVirtual: true,
                                virtualType: 'unassigned'
                            });
                        }
                        nodes = nodes.concat(children);
                        return;
                    }
                }
                nodes.push(node);
            });
        return nodes;
    }

    function toggleExpand(e, id) {
        if (state.expandedNodes.has(id)) state.expandedNodes.delete(id);
        else state.expandedNodes.add(id);
        loadTree(); // Re-render
    }

    function selectCat(id) {
        const unassignedParent = parseUnassignedId(id);
        if (unassignedParent) {
            state.currentCatId = `unassigned:${unassignedParent}`;
            state.currentCatParentId = unassignedParent;
        } else {
            state.currentCatId = coerceId(id);
            state.currentCatParentId = null;
        }
        loadTree(); // Update active state
        loadCatItems();
    }

    function getDescendants(rootId) {
        if (rootId === 'unassigned') return new Set();
        const ids = new Set([coerceId(rootId)]);
        let changed = true;
        while (changed) {
            changed = false;
            state.categories.forEach(c => {
                const parentId = coerceId(c.parent_id);
                const id = coerceId(c.id);
                if (parentId && ids.has(parentId) && !ids.has(id)) {
                    ids.add(id);
                    changed = true;
                }
            });
        }
        return ids;
    }

    async function loadCatItems() {
        const tableBody = document.querySelector('#catItemsTable tbody');
        if (!tableBody) return;
        tableBody.innerHTML = '<tr><td colspan="5">Cargando...</td></tr>';
        try {
            const q = state.lastCatQuery || '';
            const url = `/api/catalogo/items?limit=10000&offset=0` + (q ? `&q=${encodeURIComponent(q)}` : '');
            const res = await window.fetchApi(url);
            let items = (res && res.items) ? res.items : [];
            state.catalogItemsCache = items;
            if (state.categories && state.categories.length > 0) {
                state.categoryCounts = computeCategoryCounts(items);
            }

            const unassignedGlobal = items.filter(it => {
                const ids = getItemCategoryIds(it);
                return ids.length === 0;
            });
            const prevUnassignedGlobal = state.unassignedGlobalCount;
            state.unassignedGlobalCount = unassignedGlobal.length;

            const baseCatId = getActiveBaseCatId();
            let unassignedInCategory = [];
            if (baseCatId) {
                const allowed = getDescendants(baseCatId);
                const descendantsOnly = new Set(allowed);
                descendantsOnly.delete(baseCatId);

                const totalInCat = items.filter(it => {
                    const ids = getItemCategoryIds(it);
                    return ids.some(id => allowed.has(id));
                });

                unassignedInCategory = totalInCat.filter(it => {
                    const ids = getItemCategoryIds(it);
                    return ids.includes(baseCatId) && !ids.some(id => descendantsOnly.has(id));
                });

                state.unassignedByCat = { [baseCatId]: unassignedInCategory.length };
            } else {
                state.unassignedByCat = {};
            }

            const prevUnassignedByCat = state._prevUnassignedByCat || {};
            const nextUnassignedByCat = state.unassignedByCat || {};
            state._prevUnassignedByCat = nextUnassignedByCat;

            const shouldRefreshTree = (state.currentTab === 'catalogo') && (
                prevUnassignedGlobal !== state.unassignedGlobalCount ||
                JSON.stringify(prevUnassignedByCat) !== JSON.stringify(nextUnassignedByCat)
            );
            if (state.currentTab === 'catalogo') {
                if (shouldRefreshTree) loadTree();
                else if (state.categoryCounts) loadTree();
            }

            if (state.currentCatId) {
                if (state.currentCatId === 'unassigned') {
                    items = unassignedGlobal;
                } else if (typeof state.currentCatId === 'string' && state.currentCatId.startsWith('unassigned:')) {
                    items = unassignedInCategory;
                } else {
                    const allowed = getDescendants(state.currentCatId);
                    items = items.filter(it => {
                        const ids = Array.isArray(it.categoria_ids) ? it.categoria_ids : (it.categoria_id ? [it.categoria_id] : []);
                        return ids.some(id => allowed.has(id));
                    });
                }
            }

            state.catalogItemsById = {};
            items.forEach(it => { state.catalogItemsById[it.id] = it; });
            if (window.BodegaUI) window.BodegaUI.renderCatalogItems(items);
        } catch (e) {
            tableBody.innerHTML = `<tr><td colspan="5" style="opacity:0.6">${e.message}</td></tr>`;
        }
    }

    // --- PENDING / DUPLICATES ---
    async function loadPending() {
        if (window.BodegaUI) {
            // Show loading state if needed
        }

        try {
            const res = await window.fetchApi(`/api/catalogo/pendientes_dashboard`);

            if (window.BodegaUI) {
                const dupContainer = document.getElementById('duplicates-section'); // Need to ensure exists or pass generic container
                // Ideally split duplicates and uncat logic.
                // For now, delegating Duplicate Render
                const container = document.getElementById('pendingList'); // Corrected ID
                if (container) {
                    container.innerHTML = '';
                    const dupSec = document.createElement('div');
                    dupSec.id = 'duplicates-section';
                    container.appendChild(dupSec);

                    window.BodegaUI.renderDuplicates(dupSec, res.duplicates);

                    // Uncategorized render... (Simplified for now)
                }
            }
        } catch (e) { console.error(e); }
    }

    // Actions delegate
    function runDuplicateScan() {
        if (!confirm("Escanear completo?")) return;
        window.fetchApi('/api/catalogo/sugerir_duplicados', { method: 'POST', body: { item_id: 0 } })
            .then(() => { alert("Iniciado"); setTimeout(loadPending, 2000); });
    }

    async function resolveDuplicate(caseId, action) {
        try {
            await window.fetchApi('/api/catalogo/resolver_duplicado', { method: 'POST', body: { case_id: caseId, action: action } });
            loadPending();
        } catch (e) { alert(e.message); }
    }

    async function resolveDuplicateVariant(caseId, catId, itemIds) {
        try {
            // 1. Mark as variant
            await window.fetchApi('/api/catalogo/resolver_duplicado', {
                method: 'POST',
                body: { case_id: caseId, action: 'mark_as_variant' }
            });

            // 2. Apply Category to both
            if (itemIds && itemIds.length > 0) {
                for (const iid of itemIds) {
                    try {
                        await window.fetchApi(`/api/catalogo/items/${iid}/categorias`, {
                            method: 'POST',
                            body: { categoria_id: catId }
                        });
                    } catch (err) { console.warn("Fallo categorizando variant", iid, err); }
                }
            }
            alert("Resuelto: Marcados como variantes y categorizados.");
            loadPending();
        } catch (e) { alert(e.message); }
    }

    // --- HELPERS ---
    function mapItem(id) { alert("Map Item " + id); }
    function createItemPrompt() { alert("Crear item manual aún no está conectado."); }
    function applyCat(itemId, catId, method) {
        // Logic to apply cat
        alert(`Applying Cat ${catId} to ${itemId}`);
    }

    function openCatalogDrawer(itemId) {
        const item = state.catalogItemsById ? state.catalogItemsById[itemId] : null;
        if (!item) return;
        state.currentCatalogItem = item;

        const panel = document.getElementById('catalog-drawer');
        const subtitle = document.getElementById('catalog-drawer-subtitle');
        const nameEl = document.getElementById('catalog-drawer-name');
        const metaEl = document.getElementById('catalog-drawer-meta');

        const rawName = (item.nombre || '').toString();
        const displayName = rawName ? (rawName.charAt(0).toUpperCase() + rawName.slice(1).toLowerCase()) : '-';
        const unidad = (item.unidad || '').toString().toLowerCase();
        const stockVal = (item.stock_current != null) ? item.stock_current : (item.stock || 0);
        const sku = item.sku_canonico || item.product_sku || item.sku || '';

        if (subtitle) subtitle.textContent = `ID ${item.id}`;
        if (nameEl) nameEl.textContent = displayName;
        if (metaEl) metaEl.textContent = `${unidad || 'sin unidad'} • stock ${stockVal}${sku ? ` • sku ${sku}` : ''}`;

        const btnKardex = document.getElementById('cat-action-kardex');
        const btnAdjust = document.getElementById('cat-action-adjust');
        const btnCategorize = document.getElementById('cat-action-categorize');
        const btnDetail = document.getElementById('cat-action-detail');

        if (btnKardex) {
            btnKardex.disabled = !sku;
            btnKardex.onclick = () => sku ? viewKardex(sku) : alert('Este item no tiene SKU asociado.');
        }
        if (btnAdjust) {
            btnAdjust.disabled = !sku;
            btnAdjust.onclick = () => adjustStockForItem(item);
        }
        if (btnCategorize) {
            btnCategorize.onclick = () => openAssignCategoryModal(item);
        }
        if (btnDetail) {
            btnDetail.onclick = () => showCatalogDetail(item);
        }

        if (panel) panel.classList.add('open');
    }

    function closeCatalogDrawer() {
        const panel = document.getElementById('catalog-drawer');
        if (panel) panel.classList.remove('open');
    }

    async function adjustStockForItem(item) {
        const sku = item.sku_canonico || item.product_sku || item.sku || '';
        if (!sku) {
            alert('Este item no tiene SKU asociado para ajustar stock.');
            return;
        }
        const qtyRaw = prompt('Cantidad a ajustar (positivo o negativo, permite decimales):', '1');
        if (qtyRaw == null || qtyRaw === '') return;
        const qty = parseFloat(qtyRaw);
        if (!Number.isFinite(qty)) {
            alert('Cantidad inválida.');
            return;
        }
        const reason = prompt('Motivo (PURCHASE, SALE, ADJUSTMENT):', 'ADJUSTMENT') || 'ADJUSTMENT';
        const reference = prompt('Referencia (opcional):', '') || '';

        try {
            await window.fetchApi('/api/bodega/adjust', {
                method: 'POST',
                body: { sku, quantity: qty, reason, reference }
            });
            alert('Stock ajustado.');
            loadCatItems();
        } catch (e) {
            alert(e.message || 'Error ajustando stock');
        }
    }

    async function addCategoryToItem(item) {
        const catIdRaw = prompt('ID de categoría a agregar:', '');
        if (!catIdRaw) return;
        const catId = parseInt(catIdRaw, 10);
        if (Number.isNaN(catId)) {
            alert('ID inválido.');
            return;
        }
        try {
            await window.fetchApi(`/api/catalogo/items/${item.id}/categorias`, {
                method: 'POST',
                body: { categoria_id: catId }
            });
            alert('Categoría agregada.');
            loadCatItems();
        } catch (e) {
            alert(e.message || 'Error agregando categoría');
        }
    }

    function showCatalogDetail(item) {
        const modal = document.getElementById('modal-dialog');
        const title = document.getElementById('modal-title');
        const content = document.getElementById('modal-content');
        if (!modal || !content || !title) return;
        title.textContent = 'Detalle de Item';
        content.innerHTML = `<pre style="white-space:pre-wrap; font-size:0.85rem;">${JSON.stringify(item, null, 2)}</pre>`;
        modal.showModal();
    }

    return {
        init,
        state,
        onTabLoaded,
        toggleExpand,
        selectCat,
        openCreateCategoryModal,
        openAssignCategoryModal,
        openAssignCategoryModalForSelection,
        toggleCatalogSelection,
        toggleAllCatalogSelection,
        updateSelectAllState,
        handleCatSearch,
        clearCatalogSelection,
        loadInventory,
        loadTree,
        loadPending,
        runDuplicateScan,
        resolveDuplicate,
        mapItem,
        createItemPrompt,
        applyCat,
        viewKardex,
        closeKardex,
        openCatalogDrawer,
        closeCatalogDrawer
    };
})();

// Initialize when ready
window.addEventListener('DOMContentLoaded', BodegaCore.init);
