// Facturación - Lógica Unificada (V2)
const TRADUCCIONES = { 'DRAFT': 'Borrador', 'ISSUED': 'Emitida', 'PAID': 'Pagada', 'VOID': 'Anulada' };
let allRules = [];
let _customerNameById = null;

async function loadCustomerMap() {
    if (_customerNameById) return _customerNameById;
    _customerNameById = {};
    try {
        const customers = await window.fetchApi('/api/crm/customers?limit=1000');
        if (Array.isArray(customers)) {
            customers.forEach(c => {
                const name = c.fantasy_name || c.name || c.legal_name || c.rut || '';
                const keys = [
                    c.external_id,
                    c.id,
                    c.rut
                ].map(v => (v || '').toString().trim()).filter(Boolean);
                keys.forEach(k => {
                    if (!_customerNameById[k]) _customerNameById[k] = name || k;
                });
            });
        }
    } catch (e) {
        console.warn('No se pudo cargar mapa de clientes', e);
    }
    return _customerNameById;
}

// Main Entry Point (Called by erp.html)
async function initFacturacion() {
    console.log("Iniciando Facturación Unificada...");
    await fetchInvoices();
    initCiclosBg(); // Background load
}

async function fetchInvoices() {
    const status = document.getElementById('erpStatus');
    const tbody = document.querySelector('#invoicesTable tbody');

    if (!tbody) {
        console.error('invoicesTable tbody no encontrado');
        return;
    }

    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:2rem;">Cargando...</td></tr>';

    try {
        let url = `/api/sales/invoices?limit=100`;
        if (status && status.value) url += `&status=${status.value}`;
        const data = await window.fetchApi(url);
        const customerMap = await loadCustomerMap();

        tbody.innerHTML = '';
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:2rem; opacity:0.5;">Sin registros</td></tr>';
            return;
        }

        data.forEach(inv => {
            const tr = document.createElement('tr');
            const estado = TRADUCCIONES[inv.status] || inv.status;
            let statusClass = `status-${estado.toLowerCase()}`;

            // Check for negative or NC
            const isNC = (inv.type === 'NC') || (inv.type === 'NOTA CREDITO') || (inv.total_final < 0);
            // User requested ALL positive visual numbers
            const totalDisplay = new Intl.NumberFormat('es-CL').format(Math.abs(inv.total_final || 0));

            // PDF Link: Prefer external_id for Laudus, else id
            const pdfId = inv.external_id || inv.id;

            // Color Logic
            let amountColor = 'white'; // Default (Issued)
            if (estado === 'Pagada' || estado === 'PAID') amountColor = 'var(--neon)'; // Green

            // If NC, row gets specific class
            if (isNC) {
                tr.classList.add('row-nc');
                amountColor = '#ff3333'; // Explicit Red (var(--danger))
            }

            const customerId = (inv.customer_id || '').toString().trim();
            const resolvedName = inv.customer_name || customerMap[customerId] || customerId || '-';
            const customerRef = resolvedName && customerId && resolvedName !== customerId
                ? `<div style="opacity:0.6; font-size:0.75rem;">${customerId}</div>`
                : '';

            tr.innerHTML = `
                <td><b style="color:var(--neon); font-family:monospace;">#${inv.id}</b></td>
                <td><span style="font-size:0.7rem; opacity:0.7;">${inv.origin || 'Monstruo'}</span></td>
                <td>
                    <div style="font-weight:600; font-size:0.95rem;">${resolvedName}</div>
                    ${customerRef}
                    ${isNC ? '<div style="display:inline-block; margin-top:4px; font-size:0.7rem; color:#fff; background:#ff3333; padding:2px 8px; border-radius:4px; font-weight:700; border:1px solid rgba(255,255,255,0.2);">NOTA CRÉDITO</div>' : ''}
                </td>
                <td><span class="pill-status ${statusClass}">${estado}</span></td>
                <td>
                    <b style="color:${amountColor}; font-size:1.1rem; text-shadow: 0 0 10px rgba(0,0,0,0.5);">
                        $${totalDisplay}
                    </b>
                </td>
                <td style="opacity:0.6;">${(inv.created_at || '').substring(0, 10)}</td>
                <td>
                     <button class="btn-icon" onclick="showInvoiceDetail('${inv.id}')"><i class="fas fa-eye"></i></button>
                     ${inv.origin === 'LAUDUS' ? `<button class="btn-icon" title="Ver PDF" onclick="window.open('/api/sales/laudus/invoices/${pdfId}/pdf')"><i class="fas fa-file-pdf"></i></button>` : ''}
                </td>
            `;
            tbody.appendChild(tr);
        });

        // Refresh rules just in case
        initCiclosBg();

    } catch (e) {
        console.error('Error cargando facturas:', e);
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:2rem; color:#ff3333;">Error al cargar facturas</td></tr>';
    }
}

// Expose main init
window.loadInvoices = initFacturacion; // Compatibility with erp.html
window.loadInvoicesOnly = fetchInvoices; // For Filter button

async function showInvoiceDetail(id) {
    const drawer = document.getElementById('invoice-drawer');
    const body = document.getElementById('drawer-invoice-body');
    const footerActions = document.getElementById('drawer-actions');
    document.getElementById('drawer-invoice-id').innerText = `#${id}`;

    drawer.classList.add('open');
    body.innerHTML = '<div style="text-align:center; padding:2rem; opacity:0.5;"><i class="fas fa-spinner fa-spin"></i> Cargando detalles...</div>';
    footerActions.innerHTML = '';

    try {
        const inv = await window.fetchApi(`/api/sales/invoices/${id}`);
        if (!inv) throw new Error("No se encontró la factura");
        const customerMap = await loadCustomerMap();
        const custId = (inv.customer_id || '').toString().trim();
        const custName = inv.customer_name || customerMap[custId] || custId || '-';

        const fmt = (n) => `$${new Intl.NumberFormat('es-CL').format(n || 0)}`;

        body.innerHTML = `
            <div class="detail-grid">
                <div class="detail-item">
                    <label>Cliente</label>
                    <div class="val" style="font-weight:bold;">
                        ${custName}
                        ${custName && custId && custName !== custId ? `<br><small style='opacity:0.6'>${custId}</small>` : ''}
                    </div>
                </div>
                <div class="detail-item">
                    <label>Estado</label>
                    <div class="val"><span class="pill-status status-${inv.status.toLowerCase()}">${TRADUCCIONES[inv.status] || inv.status}</span></div>
                </div>
                <div class="detail-item">
                    <label>Fecha Emisión</label>
                    <div class="val">${(inv.issued_at || inv.created_at || '').substring(0, 10)}</div>
                </div>
                <div class="detail-item">
                    <label>Origen</label>
                    <div class="val">${inv.origin || 'Monstruo'}</div>
                </div>
                <!-- Row 2 -->
                 <div class="detail-item">
                    <label>Condición Pago</label>
                    <div class="val">${inv.payment_term || 'Desconocido'}</div>
                </div>
                <div class="detail-item">
                    <label>Total Final</label>
                    <div class="val" style="font-size:1.5rem; color:var(--neon);">${fmt(inv.total_final)}</div>
                </div>
            </div>
            
            <h4 style="margin-top:20px; border-bottom:1px solid #444; padding-bottom:5px;">Items</h4>
            <div style="max-height: 250px; overflow-y: auto;">
                <table class="erp-table mini">
                    <thead>
                        <tr>
                            <th>Producto</th>
                            <th style="text-align:right">Cant</th>
                            <th style="text-align:right">Precio</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(inv.items || []).map(it => `
                            <tr>
                                <td>${it.product_sku || 'Item'}</td>
                                <td style="text-align:right">${it.quantity}</td>
                                <td style="text-align:right">${fmt(it.unit_price)}</td>
                            </tr>
                        `).join('')}
                        ${(!inv.items || inv.items.length === 0) ? '<tr><td colspan="3" style="text-align:center; opacity:0.5;">No hay items registrados</td></tr>' : ''}
                    </tbody>
                </table>
            </div>
            <div id="invoice-extra-panels" style="margin-top:18px;"></div>
        `;

        // Hide payment/void buttons for now as requested
        footerActions.innerHTML = '';

        if (inv.status === 'DRAFT') {
            footerActions.innerHTML = `
                <button class="btn-primary" onclick="emitirSII('${inv.id}')">
                    <i class="fas fa-file-signature"></i> Emitir SII (Laudus)
                </button>
            `;
        }

        // Dispatch + events (solo facturas locales)
        try {
            const isLocal = /^\d+$/.test(String(inv.id || '')) && (inv.origin !== 'LAUDUS');
            if (isLocal) {
                const [dispatches, events] = await Promise.all([
                    window.fetchApi(`/api/facturacion/invoices/${inv.id}/dispatches`),
                    window.fetchApi(`/api/facturacion/invoices/${inv.id}/events`)
                ]);

                const extra = document.getElementById('invoice-extra-panels');
                if (extra) {
                    const lastDisp = Array.isArray(dispatches) && dispatches.length ? dispatches[0] : null;
                    const lastEvents = Array.isArray(events) ? events.slice(0, 6) : [];

                    extra.innerHTML = `
                        <h4 style="margin-top:10px; border-bottom:1px solid #444; padding-bottom:5px;">Tracking</h4>
                        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
                            <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border); border-radius:10px; padding:12px;">
                                <div style="font-weight:800; margin-bottom:6px;">Envíos</div>
                                ${lastDisp ? `
                                    <div style="opacity:0.8; font-size:0.9rem;">
                                        <div><b>Estado:</b> ${lastDisp.status}</div>
                                        <div><b>TO:</b> ${(lastDisp.to_emails || '').replaceAll(',', ', ') || '-'}</div>
                                        <div><b>CC:</b> ${(lastDisp.cc_emails || '').replaceAll(',', ', ') || '-'}</div>
                                        <div><b>Último intento:</b> ${(lastDisp.updated_at || '').substring(0, 19)}</div>
                                        ${lastDisp.last_error ? `<div style="color:#ff6666; margin-top:6px;"><b>Error:</b> ${lastDisp.last_error}</div>` : ''}
                                    </div>
                                ` : `<div style="opacity:0.6;">Sin envíos registrados</div>`}
                            </div>
                            <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border); border-radius:10px; padding:12px;">
                                <div style="font-weight:800; margin-bottom:6px;">Eventos</div>
                                ${lastEvents.length ? `
                                    <div style="font-size:0.85rem; opacity:0.85; max-height:140px; overflow:auto;">
                                        ${lastEvents.map(e => `
                                            <div style="padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.06);">
                                                <div style="font-weight:700;">${e.event_type}</div>
                                                <div style="opacity:0.7;">${(e.created_at || '').substring(0, 19)} ${e.created_by ? '· ' + e.created_by : ''}</div>
                                            </div>
                                        `).join('')}
                                    </div>
                                ` : `<div style="opacity:0.6;">Sin eventos</div>`}
                            </div>
                        </div>
                    `;
                }
            }
        } catch (e) {
            console.warn("Tracking panels failed:", e);
        }
        /*
        if (inv.status === 'ISSUED') {
            footerActions.innerHTML = `
                <button class="btn-primary" onclick="alert('Funcionalidad de pago pendiente')"><i class="fas fa-cash-register"></i> Registrar Pago</button>
                <button class="btn-danger" onclick="alert('Funcionalidad de anulación pendiente')"><i class="fas fa-ban"></i> Anular</button>
            `;
        }
        */

    } catch (e) {
        body.innerHTML = `<div style="color:var(--neon-red); padding:2rem; text-align:center;">${e.message}</div>`;
    }
}

window.emitirSII = async function (invoiceId) {
    if (!invoiceId) return;
    if (!confirm("¿Emitir esta factura por SII a través de Laudus?")) return;

    let docTypeId = null;
    try {
        const docTypes = await window.fetchApi('/api/facturacion/laudus/doctypes');
        if (Array.isArray(docTypes) && docTypes.length) {
            const preview = docTypes.slice(0, 12).map(d => `${d.docTypeId}: ${d.name}`).join('\n');
            const defaultId = docTypes[0].docTypeId || '';
            const input = prompt(`DocTypes disponibles (muestra primeros):\n${preview}\n\nIngrese docTypeId:`, defaultId);
            if (input === null) return;
            docTypeId = parseInt(input, 10);
        }
    } catch (e) {
        console.warn("No se pudo listar docTypes:", e);
    }

    if (!docTypeId || isNaN(docTypeId)) {
        const input = prompt("Ingrese docTypeId (Laudus):", "0");
        if (input === null) return;
        docTypeId = parseInt(input, 10);
    }

    if (!docTypeId || isNaN(docTypeId) || docTypeId <= 0) return alert("docTypeId inválido");

    try {
        await window.fetchApi(`/api/facturacion/invoices/${invoiceId}/emitir_sii`, {
            method: 'POST',
            body: JSON.stringify({ doc_type_id: docTypeId })
        });
        alert("Factura emitida OK en Laudus");
        await fetchInvoices();
        await showInvoiceDetail(invoiceId);
    } catch (e) {
        console.error(e);
        alert("Error al emitir: " + (e.message || e));
    }
};

function closeInvoiceDrawer() {
    document.getElementById('invoice-drawer').classList.remove('open');
}

// --- CICLOS / RULES LOGIC (Merged) ---

async function initCiclosBg() {
    // Only if drawer exists (sanity check)
    if (!document.getElementById('rules-drawer')) return;

    await fetchUF();
    await loadRulesBg();
}

async function fetchUF() {
    try {
        const data = await window.fetchApi('/api/facturacion/uf');
        if (data && data.uf) {
            const fmt = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(data.uf);
            // Update mini display in header
            const mini = document.getElementById('uf-today-val-mini');
            if (mini) mini.innerText = fmt;
        }
    } catch (e) {
        console.error("Error fetching UF:", e);
    }
}

async function loadRulesBg() {
    try {
        const rules = await window.fetchApi('/api/facturacion/ciclos');
        allRules = rules || [];

        // Update badge in drawer
        const activeCount = allRules.filter(r => r.is_active).length;
        const badge = document.getElementById('active-rules-count-badge');
        if (badge) badge.innerText = `${activeCount} Activas`;

        renderRulesDrawer(allRules);

    } catch (e) {
        console.error("Error loading rules:", e);
    }
}

function renderRulesDrawer(rules) {
    const tbody = document.getElementById('tabla-ciclos-drawer');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (rules.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:1rem; opacity:0.5;">No hay reglas configuradas</td></tr>';
        return;
    }

    rules.forEach(r => {
        const tr = document.createElement('tr');

        let valorStr = "";
        if (r.currency === 'UF') {
            valorStr = `<b>${r.base_amount} UF</b> <small>(${r.uf_rule})</small>`;
        } else {
            valorStr = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(r.base_amount);
        }

        const customerLabel = r.customer_name || r.customer_id;
        const customerRef = (r.customer_name && r.customer_name !== r.customer_id)
            ? `<br><small style="opacity:0.6;">${r.customer_id}</small>`
            : '';

        tr.innerHTML = `
            <td><b>${customerLabel}</b>${customerRef}</td>
            <td>${r.frequency_months} mes(es)</td>
            <td>${valorStr}</td>
            <td style="text-align:right;">
                <button class="btn-icon" title="Editar" onclick="editRule('${r.customer_id}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon" title="Previsualizar" onclick="previewRule('${r.customer_id}')">
                    <i class="fas fa-eye"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Drawer Control
function openRulesDrawer() {
    loadRulesBg(); // Refresh
    document.getElementById('rules-drawer').classList.add('open');
}
function closeRulesDrawer() {
    document.getElementById('rules-drawer').classList.remove('open');
}

// Modal & Edit Logic

function openNewRuleModal() {
    document.getElementById('modal-rule-title').innerText = "Nueva Regla de Ciclo";
    document.getElementById('rule-customer-id').value = "";
    document.getElementById('rule-customer-id').disabled = false;
    document.getElementById('rule-description').value = "";
    document.getElementById('rule-base-amount').value = 0;
    document.getElementById('rule-currency').value = "CLP";
    document.getElementById('rule-frequency').value = 1;
    document.getElementById('rule-day').value = 5;
    document.getElementById('rule-auto-issue').checked = false;

    toggleUFRules();
    loadCustomers();
    document.getElementById('modal-rule').showModal();
}

async function loadCustomers() {
    const select = document.getElementById('rule-customer-id');
    if (select.options.length > 1) return;

    try {
        select.innerHTML = '<option value="" disabled selected>Cargando...</option>';
        const customers = await window.fetchApi('/api/crm/customers?limit=100');

        select.innerHTML = '<option value="" disabled selected>Seleccione Cliente</option>';
        if (customers && customers.length > 0) {
            customers.forEach(c => {
                const customerValue = (c.external_id || c.id || '').toString().trim();
                if (!customerValue) return;
                const customerName = c.fantasy_name || c.name || c.rut || customerValue;
                const customerRut = c.rut ? ` (${c.rut})` : '';
                const opt = document.createElement('option');
                opt.value = customerValue;
                opt.text = `${customerName}${customerRut}`;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Error loading customers:", e);
        select.innerHTML = '<option value="" disabled>Error al cargar</option>';
    }
}

function toggleUFRules() {
    const isUF = document.getElementById('rule-currency').value === 'UF';
    document.getElementById('uf-rules-container').style.display = isUF ? 'block' : 'none';
}

function toggleUFValue() {
    const type = document.getElementById('rule-uf-type').value;
    const needsVal = (type === 'VALOR_FIJO' || type === 'VALOR_CONTRATO');
    document.getElementById('uf-custom-value-group').style.display = needsVal ? 'block' : 'none';
}

async function saveRule() {
    const payload = {
        customer_id: document.getElementById('rule-customer-id').value,
        description: document.getElementById('rule-description').value,
        currency: document.getElementById('rule-currency').value,
        uf_rule: document.getElementById('rule-uf-type').value,
        uf_custom_value: parseFloat(document.getElementById('rule-uf-custom-val').value) || 0,
        base_amount: parseFloat(document.getElementById('rule-base-amount').value) || 0,
        frequency_months: parseInt(document.getElementById('rule-frequency').value) || 1,
        day_of_month: parseInt(document.getElementById('rule-day').value) || 5,
        is_active: true,
        auto_issue: document.getElementById('rule-auto-issue').checked
    };

    if (!payload.customer_id) {
        alert("El ID del cliente es obligatorio");
        return;
    }

    try {
        const resp = await window.fetchApi('/api/facturacion/ciclos', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (resp && resp.ok) {
            document.getElementById('modal-rule').close();
            loadRulesBg(); // Refresh drawer list
            alert("Regla guardada correctamente");
        } else {
            alert("Error al guardar la regla");
        }
    } catch (e) {
        console.error(e);
        alert("Error de conexión");
    }
}

async function editRule(cid) {
    const rule = allRules.find(r => r.customer_id === cid);
    if (!rule) return;

    document.getElementById('modal-rule-title').innerText = "Editar Regla: " + cid;

    await loadCustomers();
    document.getElementById('rule-customer-id').value = rule.customer_id;
    document.getElementById('rule-customer-id').disabled = true;
    document.getElementById('rule-description').value = rule.description || "";
    document.getElementById('rule-base-amount').value = rule.base_amount || 0;
    document.getElementById('rule-currency').value = rule.currency || "CLP";
    document.getElementById('rule-frequency').value = rule.frequency_months || 1;
    document.getElementById('rule-day').value = rule.day_of_month || 5;

    document.getElementById('rule-uf-type').value = rule.uf_rule || "VALOR_DIA";
    document.getElementById('rule-uf-custom-val').value = rule.uf_custom_value || 0;
    document.getElementById('rule-auto-issue').checked = !!rule.auto_issue;

    toggleUFRules();
    toggleUFValue();
    document.getElementById('modal-rule').showModal();
}

async function previewRule(cid) {
    const rule = allRules.find(r => r.customer_id === cid);
    if (!rule) return;

    try {
        const data = await window.fetchApi('/api/facturacion/ciclos/preview', {
            method: 'POST',
            body: JSON.stringify(rule)
        });

        if (data) {
            const fmt = (n) => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n);
            let msg = `Previsualización para ${cid}:\n\n`;
            msg += `Monto Base: ${rule.base_amount} ${rule.currency}\n`;
            if (data.uf_used) msg += `UF aplicada: ${fmt(data.uf_used)}\n`;
            msg += `Neto calculado: ${fmt(data.total_neto)}\n`;
            msg += `Total (IVA inc): ${fmt(data.total_final)}\n\n`;
            msg += `Glosa: ${data.glosa || '(Sin glosa)'}`;

            alert(msg);
        }
    } catch (e) {
        console.error(e);
        alert("Error al previsualizar regla");
    }
}

console.log('✅ facturacion.js (Unified) cargado');
