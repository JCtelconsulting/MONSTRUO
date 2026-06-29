// Cobranza Logic

let allDebtors = [];

async function loadDebtors() {
    console.log("Loading debtors...");
    const tbody = document.querySelector('#tabla-debtors');
    if (!tbody) return; // Guard if renamed

    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem;">Analizando deuda...</td></tr>';

    // Reset KPIs
    if (document.getElementById('totalDebt')) document.getElementById('totalDebt').innerText = '$0';
    if (document.getElementById('criticalDebt')) document.getElementById('criticalDebt').innerText = '$0';
    if (document.getElementById('debtorsCount')) document.getElementById('debtorsCount').innerText = '0';

    try {
        const data = await window.fetchApi('/api/collection/debtors?min_debt=1000');
        allDebtors = data || [];

        renderDebtors(allDebtors);
        updateKPIs(allDebtors);

    } catch (e) {
        console.error('Error loading debtors:', e);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem; color:var(--danger);">Error al cargar reporte de cobranza</td></tr>';
    }
}

// Expose globally for Tab Switcher
window.loadDebtors = loadDebtors;

function renderDebtors(debtors) {
    const tbody = document.getElementById('tabla-debtors');
    tbody.innerHTML = '';

    if (debtors.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:2rem; opacity:0.5;">No hay clientes con deuda vencida</td></tr>';
        return;
    }

    const fmt = (n) => `$${new Intl.NumberFormat('es-CL').format(n)}`;

    debtors.forEach(d => {
        const tr = document.createElement('tr');

        // Determine risk class
        let riskClass = 'risk-normal';
        if (d.risk_level === 'CRITICAL') riskClass = 'risk-critical';
        if (d.risk_level === 'WARNING') riskClass = 'risk-warning';

        tr.innerHTML = `
            <td>
                <span class="risk-dot ${riskClass}"></span>
                <b>${d.customer_id}</b>
            </td>
            <td style="text-align:right; font-weight:bold; font-size:1.05rem;">${fmt(d.total_debt)}</td>
            <td style="text-align:right; opacity:0.8;">${d.debt_current > 0 ? fmt(d.debt_current) : '-'}</td>
            <td style="text-align:right; ${(d.debt_30 > 0) ? 'color:#ffcc00; font-weight:bold;' : 'opacity:0.3;'}">
                ${d.debt_30 > 0 ? fmt(d.debt_30) : '-'}
            </td>
            <td style="text-align:right; ${(d.debt_60 > 0) ? 'color:var(--danger); font-weight:bold;' : 'opacity:0.3;'}">
                ${d.debt_60 > 0 ? fmt(d.debt_60) : '-'}
            </td>
            <td>
                <button class="btn-primary" style="padding:4px 10px; font-size:0.8rem;" onclick="openGestion('${d.customer_id}')">
                    <i class="fas fa-phone-alt"></i> Gestionar
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function updateKPIs(debtors) {
    let total = 0;
    let critical = 0;

    debtors.forEach(d => {
        total += d.total_debt;
        critical += d.debt_60;
    });

    const fmt = (n) => `$${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0, notation: "compact" }).format(n)}`;

    document.getElementById('totalDebt').innerText = fmt(total);
    document.getElementById('criticalDebt').innerText = fmt(critical);
    document.getElementById('debtorsCount').innerText = debtors.length;
}

function filterDebtors() {
    const search = document.getElementById('debtorSearch').value.toLowerCase();
    const risk = document.getElementById('riskFilter').value;

    const filtered = allDebtors.filter(d => {
        const matchName = d.customer_id.toLowerCase().includes(search);
        const matchRisk = (risk === 'ALL') || (d.risk_level === risk);
        return matchName && matchRisk;
    });

    renderDebtors(filtered);
}

function openGestion(customerId) {
    document.getElementById('modal-client-name').innerText = customerId;
    document.getElementById('actionNotes').value = ''; // Reset notes
    document.getElementById('modal-gestion').showModal();
}

async function guardarGestion() {
    const customerId = document.getElementById('modal-client-name').innerText;
    const type = document.getElementById('actionType').value;
    const notes = document.getElementById('actionNotes').value;

    if (!notes) {
        alert('Por favor agrega una nota o resumen de la gestión.');
        return;
    }

    try {
        const resp = await window.fetchApi('/api/collection/actions', {
            method: 'POST',
            body: JSON.stringify({
                customer_id: customerId,
                action_type: type,
                notes: notes,
                subject: document.getElementById('emailSubject') ? document.getElementById('emailSubject').value : "Aviso de Cobranza",
                committed_amount: 0,
                commitment_date: ""
            })
        });

        if (resp && resp.ok) {
            alert('Gestión registrada correctamente');
            document.getElementById('modal-gestion').close();
        } else {
            alert('Error al guardar gestión');
        }
    } catch (e) {
        console.error(e);
        alert('Error de conexión al guardar gestión');
    }
}

async function generarBorrador() {
    const customerId = document.getElementById('modal-client-name').innerText;

    // Change type to EMAIL automatically
    const sel = document.getElementById('actionType');
    sel.value = 'EMAIL';

    // Show loading?
    document.getElementById('actionNotes').value = "Generando borrador inteligente...";

    try {
        const resp = await window.fetchApi('/api/collection/generate-template', {
            method: 'POST',
            body: JSON.stringify({ customer_id: customerId })
        });

        if (resp) {
            document.getElementById('subject-container').style.display = 'block';
            document.getElementById('emailSubject').value = resp.subject;
            document.getElementById('actionNotes').value = resp.body;
        }
    } catch (e) {
        console.error(e);
        document.getElementById('actionNotes').value = "Error generando plantilla.";
    }
}

// Auto-load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(loadDebtors, 500));
} else {
    setTimeout(loadDebtors, 500);
}
