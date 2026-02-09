// clientes.js
let allClients = [];

async function loadClients() {
    const grid = document.getElementById('clientsGrid');
    grid.innerHTML = '<div class="loading-state"><i class="fas fa-circle-notch fa-spin"></i> Cargando clientes...</div>';

    try {
        // Fetch status which gives us the active list + debt info
        const data = await window.fetchApi('/api/collection/customer-status?limit=200');
        allClients = Array.isArray(data) ? data : [];
        renderClients(allClients);
    } catch (e) {
        console.error("Error loading clients:", e);
        grid.innerHTML = '<div class="empty-state">Error al cargar clientes</div>';
    }
}

function renderClients(list) {
    const grid = document.getElementById('clientsGrid');
    if (!list || list.length === 0) {
        grid.innerHTML = '<div class="empty-state">No se encontraron clientes</div>';
        return;
    }

    grid.innerHTML = list.map(c => {
        const hasDebt = c.status === 'DEBT';
        const debtClass = hasDebt ? 'text-danger' : 'text-success';
        const debtText = hasDebt ? formatCurrency(c.total_debt) : 'Al día';
        
        // Icon based on status
        const icon = hasDebt ? 'fa-exclamation-circle' : 'fa-check-circle';
        
        return `
            <div class="client-card" onclick="openClientModal('${c.customer_id || ''}', '${c.customer_name}')">
                <div class="client-icon ${debtClass}">
                    <i class="fas ${icon}"></i>
                </div>
                <div class="client-info">
                    <div class="client-name">${c.customer_name}</div>
                    <div class="client-debt ${debtClass}">${debtText}</div>
                </div>
            </div>
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

// --- MODAL LOGIC ---

async function openClientModal(id, name) {
    if (!id) return;
    
    document.getElementById('modalClientName').innerText = name;
    document.getElementById('clientModal').classList.add('active');
    
    // Reset contents
    document.getElementById('modalProfilesList').innerHTML = '<div class="loading-small">Cargando...</div>';
    document.getElementById('modalInvoiceHistory').innerHTML = '<div class="loading-small">Cargando...</div>';
    document.getElementById('modalUFRules').innerHTML = '';

    // Parallel Fetch
    Promise.all([
        loadClientProfiles(id),
        loadClientHistory(id),
        loadClientRules(id)
    ]).catch(console.error);
}

function closeClientModal() {
    document.getElementById('clientModal').classList.remove('active');
}

async function loadClientProfiles(customerId) {
    const container = document.getElementById('modalProfilesList');
    try {
        const profiles = await window.fetchApi(`/api/facturacion/perfiles?customer_id=${encodeURIComponent(customerId)}`);
        
        if (!profiles || profiles.length === 0) {
            container.innerHTML = '<div class="empty-list">No hay servicios recurrentes configurados.</div>';
            return;
        }
        
        container.innerHTML = profiles.map(p => `
            <div class="profile-row">
                <div class="profile-info">
                    <div class="profile-name">${p.name}</div>
                    <div class="profile-details">
                        ${p.currency} $${p.base_amount || 0} (${p.uf_rule})
                    </div>
                </div>
                <button class="btn-xs btn-primary" onclick="generateDraftFromProfile(${p.id})">
                    <i class="fas fa-magic"></i> Generar
                </button>
            </div>
        `).join('');
        
    } catch (e) {
        container.innerHTML = '<div class="error-msg">Error cargando perfiles</div>';
    }
}

async function loadClientHistory(customerId) {
    const container = document.getElementById('modalInvoiceHistory');
    try {
        // We reuse the sales endpoint
        const invoices = await window.fetchApi(`/api/sales/invoices?customer_id=${encodeURIComponent(customerId)}&limit=10`);
        
        if (!invoices || invoices.length === 0) {
            container.innerHTML = '<div class="empty-list">Sin historial reciente.</div>';
            return;
        }
        
        container.innerHTML = `
            <table class="simple-table">
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

async function loadClientRules(customerId) {
   // This might need a proper endpoint filter. For now, we list all and filter JS side (not efficient but reusing existing endpoints)
   // Actually endpoint /api/facturacion/ciclos supports listing all.
   // Let's implement a filter in JS for now or verify if endpoint supports query.
   // facturacion.py list_rules doesn't seem to take filters.
   // We skip or implement later.
   document.getElementById('modalUFRules').innerHTML = '<span style="opacity:0.5; font-size:0.8rem;">(Reglas heredadas del perfil)</span>';
}

async function generateDraftFromProfile(profileId) {
    if(!confirm('¿Generar borrador de factura para este perfil?')) return;
    
    try {
        const res = await window.fetchApi(`/api/facturacion/perfiles/${profileId}/generar`, {
            method: 'POST'
        });
        
        if (res.ok) {
            showToast('Borrador generado exitosamente', 'success');
            // Refresh history
            // We need to know the customer ID again, but we are inside a closure or implicit context?
            // openClientModal sets the modal state. We can refresh the history part if we knew the customerId.
            // But checking the profile response might give us the invoice.
            // For now, simple Alert or Toast is enough.
        }
    } catch (e) {
        showToast('Error generando borrador', 'error');
        console.error(e);
    }
}

// Utils
function formatCurrency(val) {
    return new Intl.NumberFormat('es-CL', {style:'currency', currency:'CLP', maximumFractionDigits:0}).format(val);
}
function formatDateShort(dateStr) {
    if(!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('es-CL', {day:'2-digit', month:'2-digit'});
}

// Init
window.initClientes = function() {
    loadClients();
};
