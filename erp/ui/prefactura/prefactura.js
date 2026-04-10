/**
 * PREFACTURA MODULE (Invoice Builder)
 * Handles Drag & Drop, Calculations, and Template Management
 */

let cartItems = [];
let availableProducts = [];
let availableTemplates = [];
let _allBodegaProductsCache = null;
let _ufCache = { value: null, ts: 0 };
let _customerPriceOverrides = {}; // sku -> {price, currency}

// Init Module
async function initFacturacionBuilder() {
    console.log("Iniciando Constructor de Facturas...");
    cartItems = [];
    renderInvoiceLines();

    await Promise.all([
        loadProducts(),
        loadCustomersBuilder()
    ]);

    initDragAndDrop();
    loadDefaults();
}

function loadDefaults() {
    // Set default date or other initial states if needed
    const currencySelect = document.getElementById('builder-currency');
    if (currencySelect) currencySelect.value = 'CLP';
}

async function getUfValue() {
    const now = Date.now();
    if (_ufCache.value && (now - _ufCache.ts) < 5 * 60 * 1000) return _ufCache.value;
    const data = await window.fetchApi('/api/facturacion/uf');
    const uf = data && data.uf ? parseFloat(data.uf) : null;
    if (uf && !isNaN(uf)) {
        _ufCache.value = uf;
        _ufCache.ts = now;
    }
    return _ufCache.value;
}

// --- 1. Catalog & Products ---

async function loadProducts(query = "") {
    const container = document.getElementById('productsList');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center; padding:20px; opacity:0.5;">Cargando...</div>';

    try {
        // Para que coincida con Bodega (inventario), traemos el listado completo
        // y filtramos en cliente. Esto evita que "no aparezcan" productos por límite/orden.
        const q = (query || "").trim().toLowerCase();
        const onlyServicesEl = document.getElementById('onlyServices');
        const onlyServices = !!(onlyServicesEl && onlyServicesEl.checked);

        // Si es "Solo servicios", usamos el catálogo de facturación (no depende de stock)
        // porque muchos servicios no aparecen en /production/products/stock (Laudus) y por lo tanto no existen en Bodega.
        if (onlyServices) {
            const quickAdd = document.getElementById('serviceQuickAdd');
            if (quickAdd) quickAdd.style.display = 'block';
            const data = await window.fetchApi(`/api/facturacion/servicios?q=${encodeURIComponent(q)}&limit=500`);
            const items = Array.isArray(data) ? data : [];

            const custSel = document.getElementById('builder-customer');
            const customerId = custSel ? (custSel.value || '').toString().trim() : '';

            // Apply customer template overrides if any (usually UF)
            const merged = items.map(p => {
                const ov = _customerPriceOverrides[(p.sku || '').toString().trim()];
                if (!ov) {
                    // Servicios: el precio del catálogo (ej: 999) no es confiable y suele variar por cliente.
                    // Preferimos que el usuario lo ajuste manualmente en la derecha.
                    return { ...p, price: 0, _price_hidden: true, _price_source: 'CATALOG' };
                }
                return {
                    ...p,
                    price: ov.price,
                    price_currency: ov.currency,
                    _price_hidden: false,
                    _price_source: 'TEMPLATE'
                };
            });

            availableProducts = merged;
            renderProducts(merged.slice(0, 200));
            return;
        }

        const quickAdd = document.getElementById('serviceQuickAdd');
        if (quickAdd) quickAdd.style.display = 'none';

        if (!_allBodegaProductsCache) {
            const res = await window.fetchApi(`/api/bodega/inventario_enriquecido?limit=3000`);
            _allBodegaProductsCache = Array.isArray(res) ? res : (res.items || []);
        }

        const filtered = _allBodegaProductsCache.filter(p => {
            if (!q) return true;
            const name = (p.name || p.nombre || "").toString().toLowerCase();
            const sku = (p.sku || "").toString().toLowerCase();
            const cat = (p.category || "").toString().toLowerCase();
            return name.includes(q) || sku.includes(q) || cat.includes(q);
        });

        availableProducts = filtered;
        renderProducts(filtered.slice(0, 200)); // UI: no renderizar 3000 cards
    } catch (e) {
        console.error("Error loading products:", e);
        container.innerHTML = '<div style="color:red; text-align:center;">Error al cargar</div>';
    }
}

function renderProducts(products) {
    const container = document.getElementById('productsList');
    if (!container) return;
    container.innerHTML = '';

    if (!products || products.length === 0) {
        container.innerHTML = '<div style="text-align:center; opacity:0.5;">No hay productos</div>';
        return;
    }

    products.forEach(p => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.draggable = true;

        const isService = !!p.is_service;

        // Data for Drag
        const unitPriceForAdd = (p._price_hidden && isService) ? 0 : (p.price || 0);
        const productData = JSON.stringify({
            sku: p.sku,
            description: p.name || p.description,
            unit_price: unitPriceForAdd,
            price_currency: p.price_currency || null
        });
        const category = (p.category || '').toString();
        const priceSource = (p._price_source || '').toString();

        // Show price in current builder currency if we know the product currency and UF
        const currSelect = document.getElementById('builder-currency');
        const builderCurr = currSelect ? currSelect.value : 'CLP';
        const priceCurr = (p.price_currency || 'CLP').toUpperCase();
        const priceLabel = (p._price_hidden && isService)
            ? `<span style="opacity:0.55;">—</span>`
            : (priceCurr === 'UF'
                ? `${(p.price || 0)} UF`
                : `$${formatMoney(p.price || 0)}`);

        card.innerHTML = `
            <div>
                <div style="display:flex; gap:8px; align-items:center;">
                    <h4 style="margin:0;">${p.name || 'Sin Nombre'}</h4>
                    ${isService ? `<span style="font-size:0.7rem; font-weight:800; padding:2px 8px; border-radius:999px; background:rgba(0,255,136,0.12); border:1px solid rgba(0,255,136,0.35); color:var(--neon);">SERVICIO</span>` : ''}
                    ${priceSource === 'TEMPLATE' ? `<span style="font-size:0.7rem; font-weight:800; padding:2px 8px; border-radius:999px; background:rgba(138,180,248,0.12); border:1px solid rgba(138,180,248,0.35); color:#8ab4f8;">PLANTILLA</span>` : ''}
                </div>
                <p style="margin-top:4px;">${p.sku}${category ? ` · <span style="opacity:0.7;">${category}</span>` : ''}</p>
            </div>
            <div class="product-price">${priceLabel}</div>
        `;

        // Drag Events
        card.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('application/json', productData);
            e.dataTransfer.effectAllowed = 'copy';
            card.style.opacity = '0.5';
        });

        card.addEventListener('dragend', () => {
            card.style.opacity = '1';
        });

        // Double click to add
        card.addEventListener('dblclick', () => {
            addItemToInvoice({
                sku: p.sku,
                description: p.name || p.description,
                unit_price: unitPriceForAdd,
                price_currency: p.price_currency || null,
                quantity: 1
            });
        });

        container.appendChild(card);
    });
}

function filterProducts() {
    const qInput = document.getElementById('productSearch');
    if (!qInput) return;
    const q = qInput.value;

    // Debounce could be added here
    if (q.length > 1 || q.length === 0) {
        loadProducts(q);
    }
}

window.createServiceAndAdd = async function () {
    const skuEl = document.getElementById('svc-sku');
    const nameEl = document.getElementById('svc-name');
    const priceEl = document.getElementById('svc-price');

    const sku = (skuEl && skuEl.value ? skuEl.value : '').trim();
    const name = (nameEl && nameEl.value ? nameEl.value : '').trim();
    const price = priceEl && priceEl.value ? parseFloat(priceEl.value) : 0;

    if (!sku) return alert("Ingrese SKU");
    if (!name) return alert("Ingrese nombre");

    try {
        const res = await window.fetchApi('/api/facturacion/servicios', {
            method: 'POST',
            body: { sku, name, price: isNaN(price) ? 0 : price }
        });
        const p = (res && res.product) ? res.product : { sku, name, price };

        addItemToInvoice({
            sku: p.sku,
            description: p.name || name,
            unit_price: p.price || price || 0,
            quantity: 1
        });

        if (skuEl) skuEl.value = '';
        if (nameEl) nameEl.value = '';
        if (priceEl) priceEl.value = '';

        const qInput = document.getElementById('productSearch');
        if (qInput) qInput.value = '';
        await loadProducts('');
    } catch (e) {
        console.error(e);
        alert("Error creando servicio: " + (e.message || e));
    }
};

window.syncServicesFromLaudus = async function () {
    try {
        await window.fetchApi('/api/facturacion/servicios/sync_laudus', { method: 'POST' });
        alert("Sync encolado. En 1-2 minutos deberían aparecer los servicios.");
        const qInput = document.getElementById('productSearch');
        const q = qInput ? qInput.value : '';
        await loadProducts(q);
    } catch (e) {
        console.error(e);
        alert("Error sincronizando desde Laudus: " + (e.message || e));
    }
};

// --- 2. Customers ---

async function loadCustomersBuilder() {
    const select = document.getElementById('builder-customer');
    if (!select) return;

    try {
        const customers = await window.fetchApi('/api/crm/customers?limit=100');
        select.innerHTML = '<option value="">Seleccionar Cliente...</option>';

        customers.forEach(c => {
            // Use external_id if available (Laudus), else ID or RUT
            const val = c.external_id || c.rut || c.id;
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = (c.name || 'Sin Nombre') + (c.fantasy_name ? ` (${c.fantasy_name})` : '');
            select.appendChild(opt);
        });
    } catch (e) {
        console.error("Error loading customers:", e);
        select.innerHTML = '<option>Error cargando clientes</option>';
    }
}

async function refreshCustomerPriceOverrides(customerId) {
    _customerPriceOverrides = {};
    const id = (customerId || '').toString().trim();
    if (!/^[0-9]+$/.test(id)) return;

    try {
        const list = await window.fetchApi(`/api/templates/?customer_id=${encodeURIComponent(id)}&include_global=false`);
        const templates = Array.isArray(list) ? list : [];
        if (!templates.length) return;

        // Prefer latest UF template if available, else latest any currency
        const ufTpl = templates.find(t => ((t.currency || '').toString().toUpperCase() === 'UF'));
        const chosen = ufTpl || templates[0];
        const tpl = await window.fetchApi(`/api/templates/${chosen.id}`);
        const currency = ((tpl && tpl.currency) ? tpl.currency : 'CLP').toString().toUpperCase();

        const items = (tpl && tpl.items && Array.isArray(tpl.items)) ? tpl.items : [];
        items.forEach(it => {
            const sku = (it.product_sku || it.sku || '').toString().trim();
            if (!sku) return;
            const price = parseFloat(it.unit_price || 0);
            _customerPriceOverrides[sku] = { price: isNaN(price) ? 0 : price, currency };
        });
    } catch (e) {
        console.warn("No se pudo cargar overrides de plantilla:", e);
    }
}

async function loadCustomerDefaults() {
    // Optional: Load customer specific rules or discounts
    const select = document.getElementById('builder-customer');
    if (select) {
        console.log("Customer selected:", select.value);
        await refreshCustomerPriceOverrides(select.value);
        loadTemplatesForCustomer(select.value);

        // If we are browsing services, refresh the left list so it shows UF from plantilla
        const onlyServicesEl = document.getElementById('onlyServices');
        if (onlyServicesEl && onlyServicesEl.checked) {
            const qInput = document.getElementById('productSearch');
            await loadProducts(qInput ? qInput.value : '');
        }
    }
}

// --- 2b. Templates / Pre-facturas ---

async function loadTemplatesForCustomer(customerId) {
    const sel = document.getElementById('builder-template');
    availableTemplates = [];
    if (!sel) return;

    sel.innerHTML = '<option value="" selected>Cargando...</option>';
    if (!customerId) {
        sel.innerHTML = '<option value="" selected>Seleccionar Plantilla...</option>';
        return;
    }

    try {
        const data = await window.fetchApi(`/api/templates/?customer_id=${encodeURIComponent(customerId)}&include_global=true`);
        availableTemplates = Array.isArray(data) ? data : [];

        sel.innerHTML = '<option value="" selected>Seleccionar Plantilla...</option>';
        availableTemplates.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            const scope = t.customer_id ? 'Cliente' : 'Global';
            opt.textContent = `${t.name} (${scope}, ${t.currency || 'CLP'})`;
            sel.appendChild(opt);
        });
    } catch (e) {
        console.error("Error loading templates:", e);
        sel.innerHTML = '<option value="" selected>Error cargando plantillas</option>';
    }
}

window.loadSelectedTemplate = async function () {
    const sel = document.getElementById('builder-template');
    if (!sel || !sel.value) return alert("Seleccione una plantilla");
    const id = sel.value;

    try {
        const tpl = await window.fetchApi(`/api/templates/${id}`);
        if (!tpl || !tpl.items) throw new Error("Plantilla inválida");

        // Set currency
        const currSelect = document.getElementById('builder-currency');
        if (currSelect && tpl.currency) currSelect.value = tpl.currency;

        // Load items into cart
        cartItems = (tpl.items || []).map(it => ({
            sku: it.product_sku,
            description: it.description || it.product_sku,
            quantity: parseFloat(it.quantity || 1),
            unit_price: parseFloat(it.unit_price || 0)
        }));
        renderInvoiceLines();

        // Set template name for easy re-save
        const nameInput = document.getElementById('template-name');
        if (nameInput) nameInput.value = tpl.name || '';

    } catch (e) {
        console.error(e);
        alert("Error al cargar plantilla: " + e.message);
    }
};

window.importLastLaudusTemplate = async function () {
    const custSelect = document.getElementById('builder-customer');
    if (!custSelect || !custSelect.value) return alert("Seleccione un Cliente");

    const customerId = (custSelect.value || '').toString().trim();
    if (!/^[0-9]+$/.test(customerId)) {
        return alert("El cliente seleccionado no tiene customerId de Laudus (external_id) numérico.");
    }

    let name = '';
    const nameInput = document.getElementById('template-name');
    if (nameInput && nameInput.value) name = nameInput.value.trim();
    if (!name) name = "Última factura Laudus";

    try {
        const res = await window.fetchApi('/api/templates/import_last_laudus', {
            method: 'POST',
            body: { customer_id: customerId, name: name }
        });

        if (!res || !res.template || !res.template.id) throw new Error("Respuesta inválida");

        await refreshCustomerPriceOverrides(customerId);
        await loadTemplatesForCustomer(customerId);

        const sel = document.getElementById('builder-template');
        if (sel) sel.value = res.template.id;

        // Auto-load to start from real prices immediately
        await window.loadSelectedTemplate();

        // Refresh left list if we are in services view
        const onlyServicesEl = document.getElementById('onlyServices');
        if (onlyServicesEl && onlyServicesEl.checked) {
            const qInput = document.getElementById('productSearch');
            await loadProducts(qInput ? qInput.value : '');
        }

        alert(`Plantilla importada desde Laudus: ${res.source_invoice_id || ''}`);
    } catch (e) {
        console.error(e);
        alert("Error importando desde Laudus: " + (e.message || e));
    }
};

// --- 3. Drag & Drop Logic ---

function initDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault(); // Necessary to allow dropping
        dropZone.classList.add('drag-over');
        e.dataTransfer.dropEffect = 'copy';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');

        const data = e.dataTransfer.getData('application/json');
        if (data) {
            try {
                const product = JSON.parse(data);
                addItemToInvoice({
                    ...product,
                    quantity: 1
                });
            } catch (err) {
                console.error("Invalid drop data", err);
            }
        }
    });
}

// --- 4. Cart / Invoice State ---

function addItemToInvoice(item) {
    (async () => {
        const currSelect = document.getElementById('builder-currency');
        const builderCurr = currSelect ? currSelect.value : 'CLP';
        const priceCurr = (item.price_currency || builderCurr || 'CLP').toUpperCase();

        let unitPrice = parseFloat(item.unit_price || 0);
        if (isNaN(unitPrice)) unitPrice = 0;

        // Normalize unit_price to builder currency
        if (priceCurr !== builderCurr) {
            const uf = await getUfValue();
            if (!uf) throw new Error("No se pudo obtener UF para convertir precios");

            if (priceCurr === 'UF' && builderCurr === 'CLP') unitPrice = unitPrice * uf;
            if (priceCurr === 'CLP' && builderCurr === 'UF') unitPrice = unitPrice / uf;
        }

        // Merge if same SKU and normalized unit price
        const existing = cartItems.find(i => i.sku === item.sku && i.unit_price == unitPrice);
        if (existing) {
            existing.quantity = parseFloat(existing.quantity) + parseFloat(item.quantity);
        } else {
            cartItems.push({
                sku: item.sku,
                description: item.description,
                unit_price: parseFloat(unitPrice),
                quantity: parseFloat(item.quantity)
            });
        }
        renderInvoiceLines();
    })().catch(e => {
        console.error(e);
        alert(e.message || 'Error agregando item');
    });
}

function renderInvoiceLines() {
    const container = document.getElementById('invoiceLines');
    const emptyMsg = document.querySelector('.empty-state-msg');

    if (!container) return;

    if (cartItems.length === 0) {
        container.innerHTML = '';
        if (emptyMsg) emptyMsg.style.display = 'block';
        recalcTotals();
        return;
    }

    if (emptyMsg) emptyMsg.style.display = 'none';
    container.innerHTML = '';

    cartItems.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'invoice-line';
        const lineTotal = item.quantity * item.unit_price;

        // Description, Qty, Unit, Total, Remove
        div.innerHTML = `
            <div>
                <div style="font-weight:bold; font-size:0.9rem;">${item.description}</div>
                <div style="font-size:0.75rem; opacity:0.6;">${item.sku}</div>
            </div>
            <input type="number" min="0.1" step="0.1" value="${item.quantity}" 
                   onchange="updateLine(${index}, 'quantity', this.value)">
                   
            <input type="number" min="0" step="1" value="${item.unit_price}" 
                   onchange="updateLine(${index}, 'unit_price', this.value)">
                   
            <div class="line-total">$${formatMoney(lineTotal)}</div>
            
            <button class="btn-remove-line" onclick="removeLine(${index})">
                <i class="fas fa-trash"></i>
            </button>
        `;
        container.appendChild(div);
    });

    recalcTotals();
}

window.updateLine = function (index, field, value) {
    cartItems[index][field] = parseFloat(value);
    renderInvoiceLines(); // Re-render to update totals
};

window.removeLine = function (index) {
    cartItems.splice(index, 1);
    renderInvoiceLines();
};

function recalcTotals() {
    const currencySelect = document.getElementById('builder-currency');
    const isUF = currencySelect && currencySelect.value === 'UF';

    let net = 0;
    cartItems.forEach(i => {
        net += (i.quantity * i.unit_price);
    });

    const tax = Math.round(net * 0.19);
    const total = net + tax;

    const elNeto = document.getElementById('total-neto');
    const elIva = document.getElementById('total-iva');
    const elFinal = document.getElementById('total-final');

    if (elNeto) elNeto.innerText = formatMoney(net, isUF ? 'UF' : 'CLP');
    if (elIva) elIva.innerText = formatMoney(tax, isUF ? 'UF' : 'CLP');
    if (elFinal) elFinal.innerText = formatMoney(total, isUF ? 'UF' : 'CLP');
}

function clearBuilder() {
    if (confirm("¿Limpiar todo?")) {
        cartItems = [];
        renderInvoiceLines();
    }
}

// --- 5. Actions: Save Template & Emit ---

window.saveTemplate = async function () {
    const nameInput = document.getElementById('template-name');
    const custSelect = document.getElementById('builder-customer');
    const currSelect = document.getElementById('builder-currency');

    if (!nameInput || !nameInput.value) return alert("Ingrese un nombre para la plantilla");
    if (cartItems.length === 0) return alert("Agregue productos");

    const payload = {
        name: nameInput.value,
        customer_id: custSelect ? custSelect.value : null,
        currency: currSelect ? currSelect.value : 'CLP',
        items: cartItems.map((i, idx) => ({
            sku: i.sku,
            description: i.description,
            quantity: i.quantity,
            unit_price: i.unit_price,
            sort_order: idx
        }))
    };

    try {
        await window.fetchApi('/api/templates/', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        alert("Plantilla guardada OK");
    } catch (e) {
        console.error(e);
        alert("Error al guardar plantilla");
    }
};

window.emitInvoice = async function () {
    const custSelect = document.getElementById('builder-customer');

    if (!custSelect || !custSelect.value) return alert("Seleccione un Cliente");
    if (cartItems.length === 0) return alert("Agregue productos");

    if (!confirm("¿Generar Borrador de Factura para este cliente?")) return;

    const currSelect = document.getElementById('builder-currency');
    const builderCurr = currSelect ? currSelect.value : 'CLP';

    let uf = null;
    if (builderCurr === 'UF') {
        uf = await getUfValue();
        if (!uf) return alert("No se pudo obtener UF para emitir en CLP");
    }

    const payload = {
        customer_id: custSelect.value, // Must match RUT or External ID used in backend
        type: 'FACTURA',
        items: cartItems.map(i => ({
            sku: i.sku,
            quantity: i.quantity,
            // Backend guarda CLP; si el builder está en UF, convertimos antes de enviar
            unit_price: (builderCurr === 'UF') ? (i.unit_price * uf) : i.unit_price
        }))
    };

    try {
        const data = await window.fetchApi('/api/sales/invoices', {
            method: 'POST',
            body: payload
        });

        alert(`Borrador generado: ID #${data.id}`);

        // Offer to save as template (pre-factura)
        try {
            const wants = confirm("¿Guardar esta pre-factura como plantilla para reutilizar?");
            if (wants) {
                const nameInput = document.getElementById('template-name');
                let tplName = (nameInput && nameInput.value) ? nameInput.value.trim() : '';
                if (!tplName) {
                    tplName = prompt("Nombre de la plantilla:", "Servicios Mensuales");
                }
                if (tplName) {
                    if (nameInput) nameInput.value = tplName;
                    await window.saveTemplate();
                    await loadTemplatesForCustomer(custSelect.value);
                }
            }
        } catch (e2) {
            console.warn("Template save offer failed:", e2);
        }

        // Clear
        cartItems = [];
        renderInvoiceLines();

        // Switch to Facturacion tab to see the new invoice
        if (window.switchTab) window.switchTab('facturacion');

    } catch (e) {
        console.error(e);
        alert("Error al emitir factura: " + e.message);
    }
};


// Utils
function formatMoney(amount, currency = 'CLP') {
    if (currency === 'UF') return amount.toFixed(2) + ' UF';
    return new Intl.NumberFormat('es-CL').format(Math.round(amount));
}

// Expose main init
window.initPrefactura = initFacturacionBuilder;
