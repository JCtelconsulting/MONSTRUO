// ========================= admin.js (Restored for Monstruo) =========================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Admin JS Loaded');
    // Sidebar render/collapse/active now belongs to sidebar.js.

    // Auto-load based on path
    if (window.location.pathname.includes('/inicio.html')) {
        loadDashboardResumen();
    }
    // Ticketera ahora se renderiza con su propia app (tks_main.js / tks_ui.js).
    // No inyectar tabla legacy desde admin.js para evitar duplicados y errores falsos de API.
});

// --- DATA LOADERS ---

async function loadDashboardResumen() {
    // Only if we are on a page with dashboard grid
    const grid = document.querySelector('.monstruo-dashboard-grid');
    if (!grid) return;

    try {
        const data = await window.fetchApi('/api/resumen');
        // Update cards if elements exist (placeholder logic)
        // Ejemplo: si existiera un elemento id="resumen-ops"
        console.log('Resumen cargado:', data);
    } catch (e) {
        console.warn('No se pudo cargar resumen:', e);
    }
}

async function loadTKsList() {
    const container = document.querySelector('.section-block .empty-state');
    // Or specific container if defined
    const section = document.querySelector('.section-block');
    if (!section) return;

    // Create table container if not exists
    let tableContainer = document.getElementById('tks-table-container');
    if (!tableContainer) {
        tableContainer = document.createElement('div');
        tableContainer.id = 'tks-table-container';
        tableContainer.style.marginTop = '2rem';
        section.appendChild(tableContainer);
    }

    try {
        const tks = await window.fetchApi('/api/tks');
        if (!Array.isArray(tks) || tks.length === 0) {
            tableContainer.innerHTML = '<div class="empty-state">No hay TKs activos.</div>';
            return;
        }

        // Render Table
        let html = `
        <table style="width:100%; border-collapse: collapse; color: var(--text-main);">
            <thead>
                <tr style="border-bottom: 1px solid var(--panel-strong); text-align:left;">
                    <th style="padding:10px;">ID</th>
                    <th style="padding:10px;">Titulo</th>
                    <th style="padding:10px;">Estado</th>
                    <th style="padding:10px;">Fecha</th>
                    <th style="padding:10px;">Prioridad</th>
                </tr>
            </thead>
            <tbody>
        `;
        tks.forEach(tk => {
            const color = tk.estado === 'ABIERTO' ? 'var(--kpi-red)' : (tk.estado === 'EN PROGRESO' ? 'var(--kpi-orange)' : 'var(--kpi-green)');
            html += `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                    <td style="padding:10px;">#${tk.id}</td>
                    <td style="padding:10px;">${tk.titulo}</td>
                    <td style="padding:10px;"><span style="color:${color}; font-weight:bold; font-size:0.8em; border:1px solid ${color}; padding:2px 6px; border-radius:4px;">${tk.estado}</span></td>
                    <td style="padding:10px;">${tk.fecha}</td>
                    <td style="padding:10px;">${tk.prioridad}</td>
                </tr>
            `;
        });
        html += '</tbody></table>';

        // Hide default empty state if present
        if (container) container.style.display = 'none';

        tableContainer.innerHTML = html;

    } catch (e) {
        tableContainer.innerHTML = `<div class="empty-state error">Falta informacion: API no disponible (${e.message})</div>`;
    }
}
