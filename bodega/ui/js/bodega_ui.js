// bodega_ui.js - Render Logic (EDITABLE BY AI)
(function () {
    function formatStock(value) {
        const num = Number(value);
        if (Number.isNaN(num)) return value ?? '-';
        if (Number.isInteger(num)) return String(num);
        return num.toFixed(2).replace(/\.00$/, '');
    }

    function formatCategoryRoute(route) {
        if (!route) return '';
        const normalized = route
            .toString()
            .replace(/[\\/]+/g, ' > ')
            .replace(/\s*>\s*/g, ' > ')
            .replace(/\s+/g, ' ')
            .trim();
        const segments = normalized.split(' > ').map(seg => seg.trim()).filter(Boolean);
        const fmtSegments = segments.map(seg => {
            const words = seg.split(/\s+/);
            return words.map(word => {
                if (!word) return word;
                const isUpper = word === word.toUpperCase();
                const hasDigit = /\d/.test(word);
                if ((isUpper && word.length <= 3) || (isUpper && hasDigit)) {
                    return word;
                }
                const lower = word.toLowerCase();
                return lower.charAt(0).toUpperCase() + lower.slice(1);
            }).join(' ');
        });
        return fmtSegments.join(' > ');
    }

    window.BodegaUI = {
        // --- TREE RENDERER ---
        renderCategoryTree: function (container, nodes) {
            if (!container) return;
            container.innerHTML = '';

            // Helper recursive (or flat loop if pre-flattened)
            // Assuming nodes are flat list with depth, ordered.
            if (!nodes || nodes.length === 0) {
                container.innerHTML = '<div style="padding:10px; opacity:0.5">Sin categorías</div>';
                return;
            }

            nodes.forEach(node => {
                const el = document.createElement('div');
                el.className = 'tree-node';
                el.dataset.depth = String(node.depth || 0);
                if (node.isVirtual) el.classList.add('virtual');
                if (node.id === window.BodegaCore.state.currentCatId) el.classList.add('active');

                const row = document.createElement('div');
                row.className = 'tree-item';
                row.classList.add(`depth-${node.depth || 0}`);
                row.style.paddingLeft = `${8 + (node.depth * 16)}px`;
                row.onclick = () => window.BodegaCore.selectCat(node.id);

                const iconSpan = document.createElement('span');
                iconSpan.className = 'tree-icon';
                if (node.children && node.children.length > 0) {
                    iconSpan.innerHTML = node.expanded ? '▾' : '▸';
                    iconSpan.onclick = (e) => {
                        e.stopPropagation();
                        window.BodegaCore.toggleExpand(e, node.id);
                    };
                } else {
                    iconSpan.innerHTML = '•';
                    iconSpan.style.opacity = '0.5';
                }

                const nameSpan = document.createElement('span');
                nameSpan.className = 'tree-label';
                const baseLabel = formatCategoryRoute(node.nombre || '');
                const hasCount = typeof node.countTotal === 'number' && !node.isVirtual;
                nameSpan.innerText = hasCount ? `${baseLabel} (${node.countTotal})` : baseLabel;

                row.appendChild(iconSpan);
                row.appendChild(nameSpan);
                el.appendChild(row);
                container.appendChild(el);
            });
        },

        // --- INVENTORY RENDERER ---
        renderInventoryTable: function (items, kpis) {
            const tbody = document.querySelector('#invTable tbody');
            const kpiTotal = document.getElementById('kpi-total');
            const kpiMapped = document.getElementById('kpi-mapped');

            if (kpiTotal) kpiTotal.innerHTML = `${kpis.total_items || 0}`;
            if (kpiMapped) kpiMapped.textContent = kpis.mapped || '-';

            if (!tbody) return;
            tbody.innerHTML = '';

            if (items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="opacity:0.5; padding:1rem; text-align:center;">Sin resultados</td></tr>`;
                return;
            }

            items.forEach(item => {
                const tr = document.createElement('tr');
                // Status Color
                const isMapped = !!item.item_id;
                const statusColor = isMapped ? '#28a745' : '#dc3545';
                const statusIcon = isMapped ? 'link' : 'unlink';
                const sku = item.sku || item.product_sku || item.item_sku || '';

                const displayName = (item.raw_nombre || item.nombre || item.name || item.sku || 'N/A').toString().toLowerCase();
                const displaySub = `${item.raw_marca || item.marca || ''} ${item.raw_modelo || ''}`.trim().toLowerCase();
                const stockVal = (item.stock != null) ? item.stock : (item.stock_current != null ? item.stock_current : 0);

                const cats = Array.isArray(item.categorias) ? item.categorias : [];
                const catLabels = cats
                    .map(c => (c && c.ruta ? c.ruta : (c && c.nombre ? c.nombre : '')))
                    .filter(Boolean);
                const formattedRoutes = catLabels
                    .map(formatCategoryRoute)
                    .filter(Boolean);
                const uniqueRoutes = [];
                const seenRoutes = new Set();
                formattedRoutes.forEach(route => {
                    const key = route.toLowerCase();
                    if (!seenRoutes.has(key)) {
                        seenRoutes.add(key);
                        uniqueRoutes.push(route);
                    }
                });
                const lowerRoutes = uniqueRoutes.map(route => route.toLowerCase());
                const filteredRoutes = uniqueRoutes.filter((route, idx) => {
                    const key = route.toLowerCase();
                    return !lowerRoutes.some((other, j) => j !== idx && other.startsWith(`${key} > `));
                });
                const catText = filteredRoutes.length > 0
                    ? filteredRoutes.join(' • ')
                    : '--';

                tr.innerHTML = `
                    <td>
                        <div style="display:flex; align-items:center; gap:10px;">
                            ${item.image_url
                        ? `<img src="${item.image_url}" style="width:40px; height:40px; object-fit:cover; border-radius:4px;">`
                        : `<div style="width:40px; height:40px; background:rgba(255,255,255,0.1); border-radius:4px; display:flex; align-items:center; justify-content:center; opacity:0.5;"><i class="fas fa-image"></i></div>`
                    }
                            <div>
                                <div style="font-weight:bold; color:#fff">${displayName}</div>
                                <div style="font-size:0.8em; opacity:0.7">${displaySub}</div>
                            </div>
                        </div>
                    </td>
                    <td>${formatStock(stockVal)}</td>
                    <td style="opacity:0.85; font-size:0.85rem;">${catText}</td>
                    <td><span class="badge" style="background:${statusColor}"><i class="fas fa-${statusIcon}"></i></span></td>
                    <td>
                        ${isMapped
                        ? `<button class="btn-icon" onclick="window.BodegaCore.mapItem(${item.item_id})"><i class="fas fa-edit"></i></button>`
                        : `<span style="opacity:0.4">--</span>`
                    }
                        ${sku ? `<button class="btn-icon" title="Ver Kardex" onclick="window.BodegaCore.viewKardex('${sku}')"><i class="fas fa-list"></i></button>` : ''}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        },

        renderKardexTable: function (rows, error) {
            const tbody = document.querySelector('#kardexTable tbody');
            if (!tbody) return;
            tbody.innerHTML = '';

            if (error) {
                tbody.innerHTML = `<tr><td colspan="5" style="opacity:0.6; padding:1rem; text-align:center;">${error}</td></tr>`;
                return;
            }

            if (!rows || rows.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" style="opacity:0.5; padding:1rem; text-align:center;">Sin movimientos</td></tr>`;
                return;
            }

            rows.forEach(r => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${(r.created_at || '').toString().replace('T', ' ').slice(0, 19)}</td>
                    <td>${r.type || ''}</td>
                    <td>${r.quantity}</td>
                    <td>${r.user_id || ''}</td>
                    <td>${r.reference || ''}</td>
                `;
                tbody.appendChild(tr);
            });
        },

        renderCatalogItems: function (items) {
            const tbody = document.querySelector('#catItemsTable tbody');
            if (!tbody) return;
            tbody.innerHTML = '';
            if (!items || items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" style="opacity:0.5; padding:1rem; text-align:center;">Sin items</td></tr>`;
                return;
            }
            if (window.BodegaCore && window.BodegaCore.state) {
                window.BodegaCore.state.currentCatalogItems = items;
            }
            const selectedSet = (window.BodegaCore && window.BodegaCore.state && window.BodegaCore.state.selectedCatItems)
                ? window.BodegaCore.state.selectedCatItems
                : new Set();
            items.forEach(it => {
                const tr = document.createElement('tr');
                const name = (it.nombre || '').toString().toLowerCase();
                const stockVal = (it.stock_current != null) ? it.stock_current : (it.stock || 0);
                const safeName = name ? (name.charAt(0).toUpperCase() + name.slice(1)) : '';
                const checked = selectedSet.has(it.id) ? 'checked' : '';
                tr.innerHTML = `
                    <td style="text-align:center;">
                        <input type="checkbox" class="cat-item-checkbox" data-id="${it.id}" ${checked}
                            onchange="window.BodegaCore && window.BodegaCore.toggleCatalogSelection(${it.id}, this.checked)">
                    </td>
                    <td>${it.id}</td>
                    <td>${safeName}</td>
                    <td>${formatStock(stockVal)}</td>
                    <td>
                        <button class="btn-icon" title="Acciones" onclick="window.BodegaCore && window.BodegaCore.openCatalogDrawer(${it.id})">
                            <i class="fas fa-ellipsis-h"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            if (window.BodegaUI && window.BodegaUI.injectionCatalogBulkBar) {
                window.BodegaUI.injectionCatalogBulkBar();
            }
            if (window.BodegaCore && window.BodegaCore.state && window.BodegaCore.state.selectedCatItems) {
                const count = window.BodegaCore.state.selectedCatItems.size || 0;
                if (window.BodegaUI && window.BodegaUI.updateCatalogBulkUI) {
                    window.BodegaUI.updateCatalogBulkUI(count);
                }
            }
            if (window.BodegaCore && window.BodegaCore.updateSelectAllState) {
                window.BodegaCore.updateSelectAllState();
            }
        },

        // --- DUPLICATE CARDS RENDERER ---
        renderDuplicates: function (container, duplicates) {
            container.innerHTML = ''; // Clear previous

            if (!duplicates || duplicates.length === 0) {
                container.innerHTML = `
                    <div style="display:flex; align-items:center; gap:10px; opacity:0.7; margin-bottom:2rem;">
                         <i class="fas fa-check-circle" style="color:#28a745"></i> No hay duplicados pendientes. 
                         <button class="btn-primary" onclick="window.BodegaCore.runDuplicateScan()">Escanear Ahora</button>
                    </div>`;
                return;
            }

            duplicates.forEach(d => {
                const card = document.createElement('div');
                card.className = 'dup-card';
                card.style = `
                    background: rgba(255,255,255,0.05); 
                    border: 1px solid rgba(255,255,255,0.1); 
                    border-radius: 8px; 
                    padding: 15px; 
                    margin-bottom: 20px;
                `;

                card.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <strong style="font-size:1.1rem;">${d.reason}</strong>
                        <span style="opacity:0.7">Score: ${(d.score * 100).toFixed(0)}%</span>
                    </div>
                    <div style="display:flex; gap:20px; align-items:center;">
                         <div style="flex:1; display:flex; gap:10px; align-items:center;">
                             <div style="font-weight:bold; color:#0dcaf0;">A: ${d.nombre_a}</div>
                             <div style="font-weight:bold; color:#d63384;">B: ${d.nombre_b}</div>
                         </div>
                         <button class="btn-primary" onclick='window.BodegaUI.openResolveDuplicateModal(${JSON.stringify(d).replace(/'/g, "&#39;")})'>
                            <i class="fas fa-balance-scale"></i> Resolver
                         </button>
                    </div>
                `;
                container.appendChild(card);
            });

            // Inject Bulk Bar logic delegate
            window.BodegaUI.injectionBulkBar();
        },

        injectionBulkBar: function () {
            let bulkBar = document.getElementById('bulk-action-bar');
            if (!bulkBar) {
                bulkBar = document.createElement('div');
                bulkBar.id = 'bulk-action-bar';
                bulkBar.style = `
                    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
                    background: #1a1f2b; border: 1px solid #6610f2; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
                    padding: 15px 25px; border-radius: 50px; display: none; align-items: center; gap: 15px; z-index: 9999;
                    width: 90%; max-width: 600px;
                `;
                bulkBar.innerHTML = `
                    <div style="font-weight:bold; color:#fff; white-space:nowrap;">
                        <span id="bulk-count">0</span> Seleccionados
                    </div>
                    <input type="text" id="bulk-instruction" placeholder="Instrucción para todos..." 
                            style="background:rgba(0,0,0,0.3); border:1px solid #444; color:#fff; border-radius:20px; padding:8px 15px; flex:1;">
                    <button class="btn-primary" style="background:#6610f2; border-radius:20px;" onclick="window.BodegaAI.processBulkInstructions()">
                        <i class="fas fa-magic"></i> Procesar
                    </button>
                    <button class="btn-success" style="background:#198754; border-radius:20px; margin-left:10px;" onclick="window.BodegaAI.processBulkInstructions(true)">
                        <i class="fas fa-robot"></i> Auto-Pilot
                    </button>
                    <button style="background:none; border:none; color:#aaa; cursor:pointer;" onclick="window.BodegaAI.clearBulkSelection()">
                        <i class="fas fa-times"></i>
                    </button>
                `;
                document.body.appendChild(bulkBar);
            }
        },

        updateBulkUI: function (count) {
            const bar = document.getElementById('bulk-action-bar');
            const countSpan = document.getElementById('bulk-count');
            if (bar && countSpan) {
                if (count > 0) {
                    bar.style.display = 'flex';
                    countSpan.innerText = count;
                } else {
                    bar.style.display = 'none';
                }
            }
        },

        injectionCatalogBulkBar: function () {
            let bulkBar = document.getElementById('bulk-cat-bar');
            if (!bulkBar) {
                bulkBar = document.createElement('div');
                bulkBar.id = 'bulk-cat-bar';
                bulkBar.style = `
                    position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
                    background: #1a1f2b; border: 1px solid #00f3ff; box-shadow: 0 10px 30px rgba(0,0,0,0.8);
                    padding: 12px 20px; border-radius: 50px; display: none; align-items: center; gap: 12px; z-index: 9999;
                    width: 90%; max-width: 560px;
                `;
                bulkBar.innerHTML = `
                    <div style="font-weight:bold; color:#fff; white-space:nowrap;">
                        <span id="bulk-cat-count">0</span> seleccionados
                    </div>
                    <button class="btn-primary" style="background:#00f3ff; border-radius:20px; color:#000;"
                        onclick="window.BodegaCore && window.BodegaCore.openAssignCategoryModalForSelection()">
                        <i class="fas fa-tags"></i> Asignar categoría
                    </button>
                    <button class="btn-secondary" style="border-radius:20px;"
                        onclick="window.BodegaCore && window.BodegaCore.clearCatalogSelection()">
                        <i class="fas fa-times"></i>
                    </button>
                `;
                document.body.appendChild(bulkBar);
            }
        },

        updateCatalogBulkUI: function (count) {
            const bar = document.getElementById('bulk-cat-bar');
            const countSpan = document.getElementById('bulk-cat-count');
            if (bar && countSpan) {
                if (count > 0) {
                    bar.style.display = 'flex';
                    countSpan.innerText = count;
                } else {
                    bar.style.display = 'none';
                }
            }
        },

        openResolveDuplicateModal: function (data) {
            // data: { case_id, nome_a, nome_b, ... }
            const modal = document.getElementById('modal-resolve-dup');
            if (!modal) return;

            // Setup content
            const setupItem = (prefix, id, name) => {
                const container = document.getElementById(prefix);
                if (!container) return;
                container.querySelector('.dup-name').innerText = name;
                container.querySelector('small') ? container.querySelector('small').innerText = `ID: ${id}` : null;
                // Try fetch details to get image? For now we assume we might need to fetch item details or it was passed?
                // The dashboard endpoint returns minimal info. We should fetch fresh info for images.
                // Async lazy load
                window.fetchApi(`/api/catalogo/items?limit=1&q=${encodeURIComponent(name)}`) // Imprecise but works for now or better fetch by ID if we had endpoint
                    .then(res => {
                        const item = res.items.find(i => i.id == id);
                        const imgEl = container.querySelector('img');
                        if (item && item.image_url) {
                            imgEl.src = item.image_url;
                            imgEl.style.display = 'block';
                        } else {
                            imgEl.style.display = 'none';
                            container.querySelector('.dup-img').innerHTML = '<i class="fas fa-image" style="font-size:2rem; opacity:0.3"></i>';
                        }
                    });
            };

            setupItem('dup-item-a', data.id_a, data.nombre_a);
            setupItem('dup-item-b', data.id_b, data.nombre_b);

            // Bind Buttons
            document.getElementById('btn-keep-a').onclick = async () => {
                await window.BodegaCore.resolveDuplicate(data.case_id, 'keep_a');
                modal.close();
            };
            document.getElementById('btn-keep-b').onclick = async () => {
                await window.BodegaCore.resolveDuplicate(data.case_id, 'keep_b');
                modal.close();
            };
            document.getElementById('btn-ignore-dup').onclick = async () => {
                await window.BodegaCore.resolveDuplicate(data.case_id, 'ignore');
                modal.close();
            };

            // Variant Logic
            const variantContainer = document.getElementById('variant-selector-container');
            variantContainer.style.display = 'none';

            document.getElementById('btn-mark-variant').onclick = () => {
                variantContainer.style.display = 'block';
                // Init Tree
                if (!window.variantTree) {
                    window.variantTree = new CategoryTreeSelector('variant-tree-root', {
                        onSelect: (node) => { window.variantSelectedNode = node; }
                    });
                }
            };

            document.getElementById('btn-confirm-variant').onclick = async () => {
                if (!window.variantSelectedNode) return alert("Selecciona una categoría para las variantes.");

                // Call specialized logic in Core
                await window.BodegaCore.resolveDuplicateVariant(data.case_id, window.variantSelectedNode.id, [data.id_a, data.id_b]);
                modal.close();
            };

            modal.showModal();
        }
    };
    console.log("✅ BodegaUI Loaded (Full Render Logic)");
})();
