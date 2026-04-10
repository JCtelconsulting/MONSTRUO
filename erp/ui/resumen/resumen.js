async function loadTopKPIs() {
    try {
        const data = await window.fetchApi('/api/sales/kpis');
        if (data) {
            const fmt = (n) => `$${new Intl.NumberFormat('es-CL', { maximumFractionDigits: 0, notation: "compact" }).format(n)}`;

            document.getElementById('kpi-sales').innerText = fmt(data.sales_month);
            document.getElementById('kpi-debt').innerText = fmt(data.debt_overdue);
            document.getElementById('kpi-cash').innerText = fmt(data.collected_month);
        }
    } catch (e) {
        console.error("Error loading KPIs", e);
    }
}

function formatCurrency(value) {
    return new Intl.NumberFormat('es-CL', {
        style: 'currency',
        currency: 'CLP',
        maximumFractionDigits: 0
    }).format(Number(value || 0));
}

function renderCustomerDebtList(rows) {
    const container = document.getElementById('customerDebtList');
    if (!container) return;

    if (!rows || rows.length === 0) {
        container.innerHTML = '<div class="debt-empty">No hay clientes para mostrar.</div>';
        return;
    }

    const html = rows.map((row) => {
        const hasDebt = Number(row.total_debt || 0) > 0;
        const statusClass = hasDebt ? 'debt' : 'ok';
        const amountText = hasDebt ? formatCurrency(row.total_debt) : 'Al día';
        return `
            <div class="debt-row">
                <span class="status-square ${statusClass}" title="${hasDebt ? 'Con deuda' : 'Al día'}"></span>
                <span class="debt-customer" title="${row.customer_name || 'Sin nombre'}">${row.customer_name || 'Sin nombre'}</span>
                <span class="debt-amount ${statusClass}">${amountText}</span>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

async function loadCustomerDebtStatus() {
    try {
        const data = await window.fetchApi('/api/collection/customer-status?limit=120');
        renderCustomerDebtList(Array.isArray(data) ? data : []);
    } catch (e) {
        console.error("Error loading customer debt status", e);
        const container = document.getElementById('customerDebtList');
        if (container) container.innerHTML = '<div class="debt-empty">No se pudo cargar el estado de clientes.</div>';
    }
}

// Expose globally
window.initResumen = async function () {
    console.log("Initializing Resumen...");
    await loadTopKPIs();
    await loadCustomerDebtStatus();
};

// Try to init immediately if elements exist
if (document.getElementById('kpi-sales')) {
    window.initResumen();
}
