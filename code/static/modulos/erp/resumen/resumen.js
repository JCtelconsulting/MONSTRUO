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

// Expose globally
window.initResumen = async function () {
    console.log("Initializing Resumen...");
    await loadTopKPIs();
};

// Try to init immediately if elements exist
if (document.getElementById('kpi-sales')) {
    window.initResumen();
}
