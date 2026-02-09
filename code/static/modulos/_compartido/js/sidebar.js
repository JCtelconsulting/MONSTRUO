// sidebar.js - Unified Navigation for Monstruo
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('dynamic-sidebar');
    if (!sidebar) return; // Silent return if not present (e.g. login page)
    if (window.__sidebar_inited) return; // Prevent double init
    window.__sidebar_inited = true;

    const body = document.body;
    const STORAGE_KEY = 'monstruo_sidebar_collapsed';
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === '1') {
        body.classList.add('sidebar-collapsed');
    } else if (stored === '0') {
        body.classList.remove('sidebar-collapsed');
    }

    const isProdHost = window.location.hostname.endsWith('.telconsulting.cl');
    const menuItems = isProdHost ? [
        { label: 'Dashboard', icon: 'fas fa-chart-pie', link: 'https://login.telconsulting.cl/dashboard', title: 'Dashboard' },
        { label: 'Proyectos (PMO)', icon: 'fas fa-helmet-safety', link: 'https://pmo.telconsulting.cl', title: 'Oficina Técnica' },
        { label: 'ERP & Finanzas', icon: 'fas fa-file-invoice-dollar', link: 'https://erp.telconsulting.cl', title: 'ERP & Finanzas' },
        { label: 'CRM', icon: 'fas fa-id-card', link: 'https://crm.telconsulting.cl', title: 'CRM (Clientes)' },
        { label: 'Bodega', icon: 'fas fa-warehouse', link: 'https://bodega.telconsulting.cl', title: 'Bodega (WMS)' },
        { label: 'TKs', icon: 'fas fa-ticket-alt', link: 'https://ticketera.telconsulting.cl', title: 'Ticketera' },
        { label: 'IA (ULTRON)', icon: 'fas fa-robot', link: 'https://ia.telconsulting.cl', title: 'Asistente IA' },
        { label: 'Zabbix', icon: 'fas fa-signal', link: 'https://zabbix.telconsulting.cl', title: 'Monitoreo' },
        { label: 'Configuración', icon: 'fas fa-cog', link: 'https://config.telconsulting.cl', title: 'Configuración' }
    ] : [
        { label: 'Dashboard', icon: 'fas fa-chart-pie', link: '/modulos/dashboard/dashboard.html', title: 'Dashboard' },
        { label: 'Proyectos (PMO)', icon: 'fas fa-helmet-safety', link: '/modulos/pmo/dashboard.html', title: 'Oficina Técnica' },
        { label: 'ERP & Finanzas', icon: 'fas fa-file-invoice-dollar', link: '/modulos/erp/erp.html', title: 'ERP & Finanzas' },
        { label: 'CRM', icon: 'fas fa-id-card', link: '/modulos/crm/crm.html', title: 'CRM (Clientes)' },
        { label: 'Bodega', icon: 'fas fa-warehouse', link: '/modulos/bodega/bodega.html', title: 'Bodega (WMS)' },
        { label: 'TKs', icon: 'fas fa-ticket-alt', link: '/modulos/tks/tks.html', title: 'Ticketera' },
        { label: 'IA (ULTRON)', icon: 'fas fa-robot', link: '/modulos/ultron/ultron.html', title: 'Asistente IA' },
        { label: 'Zabbix', icon: 'fas fa-signal', link: '/modulos/zabbix/zabbix.html', title: 'Monitoreo' },
        { label: 'Configuración', icon: 'fas fa-cog', link: '/modulos/configuracion/configuracion.html', title: 'Configuración' }
    ];

    const currentPath = window.location.pathname;
    const currentHost = window.location.hostname;
    let html = '';

    menuItems.forEach(item => {
        let isActive = false;
        if (isProdHost) {
            const targetUrl = new URL(item.link);
            if (item.label === 'Dashboard') {
                isActive = currentHost === targetUrl.hostname && currentPath.startsWith('/dashboard');
            } else {
                isActive = currentHost === targetUrl.hostname;
            }
        } else {
            if (item.link === '/modulos/dashboard/dashboard.html' && (currentPath === '/' || currentPath === '/index.html' || currentPath.includes('dashboard.html') || currentPath.includes('inicio.html'))) {
                isActive = true;
            } else if (item.link !== '/modulos/dashboard/dashboard.html' && currentPath.includes(item.link.replace(/\?.*$/, ''))) {
                isActive = true;
            }
            if (item.label === 'Bodega' && currentPath.includes('catalogo.html')) {
                isActive = true;
            }
        }

        html += `
            <a href="${item.link}" class="side-link ${isActive ? 'active' : ''}" title="${item.title}">
                <i class="${item.icon}"></i> <span>${item.label}</span>
            </a>
        `;
    });

    sidebar.innerHTML = html;

    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn && !window.__sidebar_toggle_bound) {
        toggleBtn.addEventListener('click', () => {
            body.classList.toggle('sidebar-collapsed');
            localStorage.setItem(STORAGE_KEY, body.classList.contains('sidebar-collapsed') ? '1' : '0');
        });
        window.__sidebar_toggle_bound = true;
    }

    // Auto-init for current page if not SPA (hard reload)
    const p = window.location.pathname;
    if (p.includes('bodega.html') && window.initBodega) window.initBodega();
});

// Global navigation handler if we were using SPA, but effectively we just need to know
// if we have to init things. For now, we rely on the script being loaded.
// But wait, if sidebar.js runs DOMContentLoaded, and bodega.sj runs... wait.
// bodega.js exposes window.initBodega.
// If we browse to /modulos/bodega.html directly, sidebar.js runs.
// We should check if we are in that page.
