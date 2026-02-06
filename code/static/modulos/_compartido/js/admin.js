// ========================= admin.js (Restored for Monstruo) =========================
document.addEventListener('DOMContentLoaded', () => {
    console.log('Admin JS Loaded');
    try {
        const stored = localStorage.getItem('monstruo_sidebar_collapsed');
        if (stored === '1') document.body.classList.add('sidebar-collapsed');
        if (stored === '0') document.body.classList.remove('sidebar-collapsed');
    } catch (e) { }

    // 1. Sidebar Toggle
    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn && !window.__sidebar_toggle_bound) {
        toggleBtn.addEventListener('click', () => {
            document.body.classList.toggle('sidebar-collapsed');
            try {
                localStorage.setItem('monstruo_sidebar_collapsed', document.body.classList.contains('sidebar-collapsed') ? '1' : '0');
            } catch (e) { }
        });
        window.__sidebar_toggle_bound = true;
    }

    // 2. Active Link Highlighting (Based on URL)
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.side-link');

    navLinks.forEach((link) => {
        // Simple check: if href matches current path
        const href = link.getAttribute('href');
        if (href && (currentPath === href || currentPath.endsWith(href))) {
            link.classList.add('active');
        } else {
            // Remove active from others (in case hardcoded in HTML)
            link.classList.remove('active');
        }
    });

    // 3. Navigation and Data Loading hooks
    navLinks.forEach((btn) => {
        // Detect current page from URL to trigger specific loads
        // (MPA style: load on DOMContentLoaded based on path)
    });

    // Auto-load based on path
    if (window.location.pathname.includes('/inicio.html')) {
        loadDashboardResumen();
    }
    if (window.location.pathname.includes('/modulos/tks.html')) {
        loadTKsList();
    }
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
