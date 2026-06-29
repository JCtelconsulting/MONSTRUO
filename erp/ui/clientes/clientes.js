// clientes.js
let allClients = [];
let activeClientId = null;

async function loadClients() {
    const tbody = document.getElementById('clientsTableBody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading-state"><i class="fas fa-circle-notch fa-spin"></i> Cargando clientes...</td></tr>';

    try {
        const data = await window.fetchApi('/api/collection/customer-status?limit=200');
        allClients = Array.isArray(data) ? data : [];
        renderClients(allClients);
    } catch (e) {
        console.error("Error loading clients:", e);
        tbody.innerHTML = '<tr><td colspan="5" class="error-msg">Error al cargar clientes</td></tr>';
    }
}

function renderClients(list) {
    const tbody = document.getElementById('clientsTableBody');
    if (!list || list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No se encontraron clientes</td></tr>';
        return;
    }

    tbody.innerHTML = list.map(c => {
        const hasDebt = c.status === 'DEBT';
        const debtClass = hasDebt ? 'status-anulada' : 'status-pagada'; // Reuse styling classes essentially
        const debtText = hasDebt ? formatCurrency(c.total_debt) : 'Al día';
        const badgeStyle = hasDebt ? 'background:var(--danger); color:#fff;' : 'background:#00cc66; color:#000;';

        return `
            <tr class="client-row">
                <td><span class="pill-status" style="${badgeStyle}">${hasDebt ? 'DEUDA' : 'OK'}</span></td>
                <td style="font-weight:600; color:var(--text-main);">${c.customer_name}</td>
                <td style="opacity:0.7;">${c.customer_id || '-'}</td>
                <td style="font-weight:bold; ${hasDebt ? 'color:#ff5555;' : ''}">${debtText}</td>
                <td style="text-align:right;">
                    <div class="action-buttons">
                        <button class="btn-secondary btn-icon" title="Reglas de Facturación" onclick="openBillingDrawer('${c.customer_id}', '${c.customer_name}')">
                            <i class="fas fa-file-invoice"></i>
                        </button>
                        <button class="btn-secondary btn-icon" title="Gestión de Cobranza" onclick="openCollectionDrawer('${c.customer_id}', '${c.customer_name}')">
                            <i class="fas fa-comment-dollar"></i>
                        </button>
                        <button class="btn-secondary btn-icon" title="Historial" onclick="openHistoryDrawer('${c.customer_id}', '${c.customer_name}')">
                            <i class="fas fa-history"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function filterClients() {
    const term = document.getElementById('clientSearch').value.toLowerCase();
    const filtered = allClients.filter(c =>
        (c.customer_name || '').toLowerCase().includes(term) ||
        (c.customer_id || '').toLowerCase().includes(term)
    );
    renderClients(filtered);
}

// --- DRAWER MANAGEMENT ---

function openDrawer(drawerId) {
    // Close others
    document.querySelectorAll('.drawer').forEach(d => d.classList.remove('open'));
    const drawer = document.getElementById(drawerId);
    if (drawer) drawer.classList.add('open');
}

function closeDrawer(drawerId) {
    const drawer = document.getElementById(drawerId);
    if (drawer) drawer.classList.remove('open');
}

// 1. BILLING DRAWER (Perfiles)
async function openBillingDrawer(id, name) {
    activeClientId = id;
    openDrawer('drawer-billing');

    // Set Header if possible, or just load
    const container = document.getElementById('billingProfilesList');
    container.innerHTML = '<div class="loading-small">Cargando perfiles...</div>';

    try {
        const profiles = await window.fetchApi(`/api/facturacion/perfiles?customer_id=${encodeURIComponent(id)}`);

        if (!profiles || profiles.length === 0) {
            container.innerHTML = `
                <div class="empty-list">No hay perfiles configurados.</div>
                <button class="btn-primary" style="margin-top:10px; width:100%;" onclick="createDefaultProfile('${id}')">
                    <i class="fas fa-plus"></i> Crear Perfil Base
                </button>
            `;
            return;
        }

        container.innerHTML = profiles.map(p => `
            <div class="profile-card">
                <div class="profile-header">
                    <span class="profile-title">${p.name}</span>
                    <span class="badge">${p.currency === 'UF' ? 'UF' : '$'}</span>
                </div>
                <div class="profile-body">
                    <div>Monto: ${p.currency} $${p.base_amount || 0}</div>
                    <div style="font-size:0.8rem; opacity:0.7;">${p.uf_rule}</div>
                </div>
                <div class="profile-actions">
                    <button class="btn-xs btn-primary" onclick="generateDraftFromProfile(${p.id})">
                        <i class="fas fa-magic"></i> Generar
                    </button>
                </div>
            </div>
        `).join('');

    } catch (e) {
        container.innerHTML = '<div class="error-msg">Error cargando perfiles</div>';
    }
}

// 2. COLLECTION DRAWER
async function openCollectionDrawer(id, name) {
    activeClientId = id;
    openDrawer('drawer-collection');

    document.getElementById('collectionStats').innerHTML = '<div class="loading-small">Cargando datos...</div>';
    document.getElementById('collectionLog').innerHTML = '';

    // Here we would fetch debt details + log
    // For now, re-using customer status debt logic visually
    // In real implementation we need an endpoint for collection history

    const clientData = allClients.find(c => c.customer_id === id);
    if (clientData) {
        const debtFormatted = formatCurrency(clientData.total_debt);
        document.getElementById('collectionStats').innerHTML = `
            <div class="kpi-card mini">
                <div class="kpi-val" style="font-size:1.5rem; color:${clientData.status === 'DEBT' ? 'var(--danger)' : '#00cc66'}">${debtFormatted}</div>
                <div class="kpi-lbl">Deuda Total</div>
            </div>
        `;
    }

    document.getElementById('collectionLog').innerHTML = '<div class="empty-list">Sin gestiones registradas (demo).</div>';
}

async function saveCollectionAction() {
    const note = document.getElementById('collectionNote').value;
    if (!note) return alert('Escribe una nota');

    // Mock save
    alert('Gestión guardada (simulación)');
    document.getElementById('collectionNote').value = '';
}

// 3. HISTORY DRAWER
async function openHistoryDrawer(id, name) {
    activeClientId = id;
    openDrawer('drawer-history');

    const container = document.getElementById('historyList');
    container.innerHTML = '<div class="loading-small">Cargando historial...</div>';

    try {
        const invoices = await window.fetchApi(`/api/sales/invoices?customer_id=${encodeURIComponent(id)}&limit=20`);

        if (!invoices || invoices.length === 0) {
            container.innerHTML = '<div class="empty-list">Sin comprobantes.</div>';
            return;
        }

        container.innerHTML = `
            <table class="erp-table mini">
                <thead><tr><th>Folio</th><th>Fecha</th><th>Monto</th><th>Estado</th></tr></thead>
                <tbody>
                    ${invoices.map(inv => `
                        <tr>
                            <td>#${inv.external_id || inv.id}</td>
                            <td>${formatDateShort(inv.issued_at || inv.created_at)}</td>
                            <td>${formatCurrency(inv.total_final)}</td>
                            <td><span class="badge badge-${inv.status.toLowerCase()}">${inv.status}</span></td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {
        container.innerHTML = '<div class="error-msg">Error cargando historial</div>';
    }
}

// Actions
async function generateDraftFromProfile(profileId) {
    if (!confirm('¿Generar borrador de factura para este perfil?')) return;

    try {
        const res = await window.fetchApi(`/api/facturacion/perfiles/${profileId}/generar`, {
            method: 'POST'
        });

        if (res.ok) {
            showToast('Borrador generado exitosamente', 'success');
            closeDrawer('drawer-billing');
        }
    } catch (e) {
        showToast('Error generando borrador', 'error');
        console.error(e);
    }
}

async function createDefaultProfile(customerId) {
    alert('Esta función abriría el modal de crear perfil (pendiente de implementación)');
}

// Utils
function formatCurrency(val) {
    return new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP', maximumFractionDigits: 0 }).format(val);
}
function formatDateShort(dateStr) {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('es-CL', { day: '2-digit', month: '2-digit' });
}

window.initClientes = function () {
    loadClients();
};
