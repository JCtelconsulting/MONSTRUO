
async function loadSmtpConfig() {
    try {
        const data = await window.fetchApi('/api/config/smtp');
        if (data) {
            document.getElementById('smtpHost').value = data.smtp_host || '';
            document.getElementById('smtpPort').value = data.smtp_port || '';
            document.getElementById('smtpUser').value = data.smtp_user || '';
            document.getElementById('smtpPass').value = data.smtp_password || ''; // Will be masked if exists
        }
    } catch (e) {
        console.error("Error loading SMTP config", e);
    }
}

async function saveSmtpConfig() {
    const host = document.getElementById('smtpHost').value;
    const port = document.getElementById('smtpPort').value;
    const user = document.getElementById('smtpUser').value;
    const pass = document.getElementById('smtpPass').value;

    try {
        await window.fetchApi('/api/config/smtp', {
            method: 'POST',
            body: JSON.stringify({
                smtp_host: host,
                smtp_port: port,
                smtp_user: user,
                smtp_password: pass
            })
        });
        alert('Configuración guardada correctamente.');
    } catch (e) {
        console.error(e);
        alert('Error al guardar configuración.');
    }
}



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
    await loadSmtpConfig();
    await loadTopKPIs();
};

// Try to init immediately if elements exist
if (document.getElementById('kpi-sales')) {
    window.initResumen();
}
