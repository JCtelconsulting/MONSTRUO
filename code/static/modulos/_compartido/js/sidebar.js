// sidebar.js - Navegación Unificada para Monstruo (v3 - Subdominios + Prefijo Entorno)
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('dynamic-sidebar');
    if (!sidebar) return;
    if (window.__sidebar_inited) return;
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
    // Detectar prefijo de entorno (/prod o /dev) desde la URL actual
    const envPrefix = isProdHost ? (window.location.pathname.startsWith('/dev') ? '/dev' : '/prod') : '';

    // En produccion: cada modulo tiene su propio subdominio
    // En local: rutas relativas sin subdominio
    const menuItems = isProdHost ? [
        { id: 'dashboard', label: 'Dashboard', icon: 'fas fa-chart-pie', link: `https://login.telconsulting.cl${envPrefix}/dashboard`, title: 'Dashboard' },
        { id: 'pmo', label: 'Proyectos (PMO)', icon: 'fas fa-helmet-safety', link: `https://pmo.telconsulting.cl${envPrefix}/`, title: 'Oficina Técnica' },
        { id: 'erp', label: 'ERP & Finanzas', icon: 'fas fa-file-invoice-dollar', link: `https://erp.telconsulting.cl${envPrefix}/`, title: 'ERP & Finanzas' },
        { id: 'crm', label: 'CRM', icon: 'fas fa-id-card', link: `https://crm.telconsulting.cl${envPrefix}/`, title: 'CRM (Clientes)' },
        { id: 'bodega', label: 'Bodega', icon: 'fas fa-warehouse', link: `https://bodega.telconsulting.cl${envPrefix}/`, title: 'Bodega (WMS)' },
        { id: 'tks', label: 'TKs', icon: 'fas fa-ticket-alt', link: `https://ticketera.telconsulting.cl${envPrefix}/`, title: 'Ticketera' },
        { id: 'ia', label: 'IA (ULTRON)', icon: 'fas fa-robot', link: `https://ia.telconsulting.cl${envPrefix}/`, title: 'Asistente IA' },
        { id: 'zabbix', label: 'Zabbix', icon: 'fas fa-signal', link: `https://zabbix.telconsulting.cl${envPrefix}/`, title: 'Monitoreo' },
        { id: 'config', label: 'Configuración', icon: 'fas fa-cog', link: `https://config.telconsulting.cl${envPrefix}/`, title: 'Configuración' }
    ] : [
        { id: 'dashboard', label: 'Dashboard', icon: 'fas fa-chart-pie', link: '/modulos/dashboard/dashboard.html', title: 'Dashboard' },
        { id: 'pmo', label: 'Proyectos (PMO)', icon: 'fas fa-helmet-safety', link: '/modulos/pmo/pmo.html', title: 'Oficina Técnica' },
        { id: 'erp', label: 'ERP & Finanzas', icon: 'fas fa-file-invoice-dollar', link: '/modulos/erp/erp.html', title: 'ERP & Finanzas' },
        { id: 'crm', label: 'CRM', icon: 'fas fa-id-card', link: '/modulos/crm/crm.html', title: 'CRM (Clientes)' },
        { id: 'bodega', label: 'Bodega', icon: 'fas fa-warehouse', link: '/modulos/bodega/bodega.html', title: 'Bodega (WMS)' },
        { id: 'tks', label: 'TKs', icon: 'fas fa-ticket-alt', link: '/modulos/tks/tks.html', title: 'Ticketera' },
        { id: 'ia', label: 'IA (ULTRON)', icon: 'fas fa-robot', link: '/modulos/ultron/ultron.html', title: 'Asistente IA' },
        { id: 'zabbix', label: 'Zabbix', icon: 'fas fa-signal', link: '/modulos/zabbix/zabbix.html', title: 'Monitoreo' },
        { id: 'config', label: 'Configuración', icon: 'fas fa-cog', link: '/modulos/configuracion/configuracion.html', title: 'Configuración' }
    ];

    const currentPath = window.location.pathname;
    const currentHost = window.location.hostname;

    // FETCH SESSION & FILTER
    // Hacemos el sidebar rendering async para esperar la sesion
    (async () => {
        let allowed = [];
        let role = '';
        try {
            const data = await window.fetchApi('/api/sesion');
            if (data.ok) {
                allowed = data.allowed_modules || [];
                role = data.role;

                // Actualizar info de usuario en sidebar
                const whoEl = document.getElementById('who');
                if (whoEl) {
                    const userName = data.user || 'Usuario';
                    const userRole = (data.role || 'user').toUpperCase();
                    // Limpieza simple del nombre (ej. juan.lopez@... -> Juan Lopez)
                    let displayName = userName;
                    if (userName.includes('@')) {
                        displayName = userName.split('@')[0].replace('.', ' ');
                        displayName = displayName.replace(/\b\w/g, l => l.toUpperCase()); // Capitalize
                    }

                    whoEl.textContent = `${displayName} (${userRole})`;
                    whoEl.style.opacity = '1';
                    whoEl.style.fontWeight = '600';
                    whoEl.title = userName; // Tooltip con email original
                }
            }
        } catch (e) {
            console.warn("Sidebar session check failed", e);
        }

        // Fallback por Rol si allowed esta vacio (retro-compatibilidad o usuarios no migrados)
        // Ojo: Si el usuario guardó una lista vacia, significa que NO TIENE acceso a nada.
        // Pero para evitar bloqueos accidentales durante la migracion, si es [] y el rol tiene permisos, usamos el rol.
        // MEJORA: Si allowed es null/undefined se usa el rol. Si es [], es acceso restringido.
        if (!allowed || allowed.length === 0) {
            const ROLE_MAP = {
                'admin': ['*'],
                'encargado_mesa': ['dashboard', 'tks', 'config'],
                'redes': ['dashboard', 'tks'],
                'sistemas': ['dashboard', 'tks'],
                'implementaciones': ['dashboard', 'tks', 'pmo'],
                'gerencia': ['dashboard', 'tks', 'pmo', 'erp', 'crm', 'ia', 'zabbix'],
                'ops': ['dashboard', 'tks', 'crm', 'bodega', 'zabbix', 'config'],
                'finance': ['dashboard', 'erp', 'crm'],
                'warehouse': ['bodega']
            };
            // Si data.allowed_modules venia null (no migrado), usamos map.
            // Si venia [], es que se guardo vacio. Pero por seguridad ahora, asumimos rol si vacio.
            allowed = ROLE_MAP[role] || ['dashboard'];
        }

        // Si sigue vacio (ej. logout), mostrar solo dashboard o nada?
        // Si es login page, sidebar suele no estar.

        let html = '';

        menuItems.forEach(item => {
            // Filter logic
            if (allowed.includes('*') || allowed.includes(item.id)) {
                // Render logic (same as before)
                let isActive = false;
                if (isProdHost) {
                    try {
                        const targetUrl = new URL(item.link);
                        if (item.label === 'Dashboard') {
                            isActive = currentHost === targetUrl.hostname && currentPath.includes('/dashboard');
                        } else {
                            isActive = currentHost === targetUrl.hostname;
                        }
                    } catch (e) { }
                } else {
                    const cleanPath = currentPath.replace(/^\/(prod|dev)/, '');
                    const itemPath = item.link.replace(/\?.*$/, '');
                    if (item.link.includes('dashboard.html') && (cleanPath === '/' || cleanPath === '/index.html' || cleanPath.includes('dashboard.html') || cleanPath.includes('inicio.html'))) {
                        isActive = true;
                    } else if (!item.link.includes('dashboard.html') && cleanPath.includes(itemPath)) {
                        isActive = true;
                    }
                    if (item.label === 'Bodega' && cleanPath.includes('catalogo.html')) {
                        isActive = true;
                    }
                }

                html += `
                    <a href="${item.link}" class="side-link ${isActive ? 'active' : ''}" title="${item.title}">
                        <i class="${item.icon}"></i> <span>${item.label}</span>
                    </a>
                `;
            }
        });

        sidebar.innerHTML = html;
    })();

    // --- ESTANDARIZAR FOOTER DEL SIDEBAR (todos los módulos) ---
    const headerActions = document.querySelector('.header-actions');
    if (headerActions) {
        // Crear footer-buttons-container si no existe
        let footerContainer = headerActions.querySelector('.footer-buttons-container');
        if (!footerContainer) {
            footerContainer = document.createElement('div');
            footerContainer.className = 'footer-buttons-container';

            // Crear #who si no existe
            let whoEl = headerActions.querySelector('#who');
            if (!whoEl) {
                whoEl = document.createElement('span');
                whoEl.id = 'who';
                whoEl.className = 'pill';
                whoEl.style.cssText = 'display:block; margin-bottom:10px; font-size:0.8rem; opacity:0.7;';
                whoEl.textContent = 'Usuario';
                headerActions.insertBefore(whoEl, headerActions.firstChild);
            }

            // Crear btn-open-change-password si no existe
            let btnAccount = headerActions.querySelector('#btn-open-change-password');
            if (!btnAccount) {
                btnAccount = document.createElement('button');
                btnAccount.id = 'btn-open-change-password';
                btnAccount.className = 'btn-account';
                btnAccount.title = 'Cambiar Contraseña';
                btnAccount.innerHTML = '<i class="fas fa-key"></i> <span>Cuenta</span>';
            }

            // Mover btnLogout existente dentro del container
            const btnLogout = headerActions.querySelector('#btnLogout');

            footerContainer.appendChild(btnAccount);
            if (btnLogout) footerContainer.appendChild(btnLogout);

            headerActions.appendChild(footerContainer);
        }

        // --- BOTÓN DE CAMBIO DE ENTORNO (solo en producción) ---
        if (isProdHost && !footerContainer.querySelector('.btn-env')) {
            const isDev = envPrefix === '/dev';
            const btnEnv = document.createElement('button');
            btnEnv.className = 'btn-env';
            btnEnv.title = isDev ? 'Volver a Producción' : 'Ir a Desarrollo';
            btnEnv.innerHTML = isDev
                ? '<i class="fas fa-server"></i> <span>VOLVER A PROD</span>'
                : '<i class="fas fa-flask"></i> <span>IR A DEV</span>';
            btnEnv.addEventListener('click', () => {
                window.location.assign(isDev ? '/prod/' : '/dev/');
            });

            // Inyectar estilos del botón
            if (!document.getElementById('btn-env-styles')) {
                const style = document.createElement('style');
                style.id = 'btn-env-styles';
                style.textContent = `
                    .btn-env {
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        gap: 8px;
                        font-weight: 800;
                        text-transform: uppercase;
                        padding: 12px;
                        border-radius: 8px;
                        cursor: pointer;
                        transition: 0.2s;
                        font-size: 0.8rem;
                        background: transparent;
                        white-space: nowrap;
                        width: 100%;
                        font-family: var(--font-main);
                        letter-spacing: 0.5px;
                        border: 1px solid ${isDev ? 'var(--danger)' : 'var(--info)'} !important;
                        color: ${isDev ? 'var(--danger)' : 'var(--info)'} !important;
                    }
                    .btn-env:hover {
                        background: ${isDev ? 'var(--danger)' : 'var(--info)'} !important;
                        color: ${isDev ? '#fff' : '#000'} !important;
                        box-shadow: 0 0 20px ${isDev ? 'rgba(255,51,51,0.4)' : 'rgba(0,243,255,0.4)'};
                    }
                    body.sidebar-collapsed .btn-env {
                        width: 42px;
                        height: 42px;
                        padding: 0;
                        border-radius: 10px;
                        font-size: 1rem;
                    }
                    body.sidebar-collapsed .btn-env span {
                        display: none;
                    }
                `;
                document.head.appendChild(style);
            }

            // Insertar como PRIMER hijo del footer-buttons-container
            footerContainer.insertBefore(btnEnv, footerContainer.firstChild);
        }
    }

    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn && !window.__sidebar_toggle_bound) {
        toggleBtn.addEventListener('click', () => {
            body.classList.toggle('sidebar-collapsed');
            localStorage.setItem(STORAGE_KEY, body.classList.contains('sidebar-collapsed') ? '1' : '0');
        });
        window.__sidebar_toggle_bound = true;
    }

    // Auto-init para paginas que no son SPA
    const p = window.location.pathname;
    if (p.includes('bodega.html') && window.initBodega) window.initBodega();

    // ========================================================================
    // NOTIFICACIONES IN-APP (ELIMINADO A PEDIDO DEL USUARIO)
    // ========================================================================
    /*
    (function initNotifications() {
        // ... logic removed ...
    })();
    */
});
