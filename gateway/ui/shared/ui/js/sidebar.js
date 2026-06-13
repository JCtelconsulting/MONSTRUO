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

    const toggleBtn = document.getElementById('sidebar-toggle');
    if (toggleBtn && !window.__sidebar_toggle_bound) {
        toggleBtn.addEventListener('click', () => {
            body.classList.toggle('sidebar-collapsed');
            try {
                localStorage.setItem(STORAGE_KEY, body.classList.contains('sidebar-collapsed') ? '1' : '0');
            } catch (e) { }
        });
        window.__sidebar_toggle_bound = true;
    }

    const isProdHost = window.location.hostname.endsWith('.telconsulting.cl');
    const localServiceUrl = (port, path = '/') => {
        const protocol = window.location.protocol || 'http:';
        const host = window.location.hostname || '127.0.0.1';
        return `${protocol}//${host}:${port}${path}`;
    };
    const envPrefix = isProdHost ? (window.getEnvPrefix ? window.getEnvPrefix() : (window.location.pathname.startsWith('/dev') ? '/dev' : '')) : '';

    const menuItems = isProdHost ? [
        { id: 'dashboard', label: 'Dashboard', icon: 'fas fa-chart-pie', link: `https://login.telconsulting.cl${envPrefix}/dashboard`, title: 'Dashboard' },
        { id: 'tks', label: 'TKs', icon: 'fas fa-ticket-alt', link: `https://ticketera.telconsulting.cl${envPrefix}/`, title: 'Ticketera' },
        { id: 'gta', label: 'GTA', icon: 'fas fa-tasks', link: `https://login.telconsulting.cl${envPrefix}/gta`, title: 'Gestión de Tareas Automatizadas' },
        { id: 'fundacion', label: 'Fundación', icon: 'fas fa-hands-helping', link: `https://login.telconsulting.cl${envPrefix}/fundacion`, title: 'Fundación' },
        { id: 'pmo', label: 'Proyectos (PMO)', icon: 'fas fa-helmet-safety', link: `https://pmo.telconsulting.cl${envPrefix}/`, title: 'Oficina Técnica' },
        { id: 'erp', label: 'ERP & Finanzas', icon: 'fas fa-file-invoice-dollar', link: `https://erp.telconsulting.cl${envPrefix}/`, title: 'ERP & Finanzas' },
        { id: 'crm', label: 'CRM', icon: 'fas fa-id-card', link: `https://crm.telconsulting.cl${envPrefix}/`, title: 'CRM (Clientes)' },
        { id: 'bodega', label: 'Bodega', icon: 'fas fa-warehouse', link: `https://bodega.telconsulting.cl${envPrefix}/`, title: 'Bodega (WMS)' },
        { id: 'ia', label: 'IA (ULTRON)', icon: 'fas fa-robot', link: `https://ia.telconsulting.cl${envPrefix}/`, title: 'Asistente IA' },
        { id: 'zabbix', label: 'Zabbix', icon: 'fas fa-signal', link: `https://zabbix.telconsulting.cl${envPrefix}/`, title: 'Monitoreo' },
        { id: 'terreneitor', label: 'Terreneitor', icon: 'fas fa-camera', link: `https://terreneitor.telconsulting.cl${envPrefix}/`, title: 'Terreneitor (Informes de Terreno)' },
        { id: 'config', label: 'Configuración', icon: 'fas fa-cog', link: `https://config.telconsulting.cl${envPrefix}/`, title: 'Configuración' },
    ] : [
        { id: 'dashboard', label: 'Dashboard', icon: 'fas fa-chart-pie', link: localServiceUrl(9001, '/dashboard'), title: 'Dashboard' },
        { id: 'tks', label: 'TKs', icon: 'fas fa-ticket-alt', link: localServiceUrl(9005), title: 'Ticketera' },
        { id: 'gta', label: 'GTA', icon: 'fas fa-tasks', link: localServiceUrl(9012, '/'), title: 'Gestión de Tareas Automatizadas' },
        { id: 'fundacion', label: 'Fundación', icon: 'fas fa-hands-helping', link: localServiceUrl(9001, '/fundacion'), title: 'Fundación' },
        { id: 'pmo', label: 'Proyectos (PMO)', icon: 'fas fa-helmet-safety', link: localServiceUrl(9009, '/'), title: 'Oficina Técnica' },
        { id: 'erp', label: 'ERP & Finanzas', icon: 'fas fa-file-invoice-dollar', link: localServiceUrl(9006), title: 'ERP & Finanzas' },
        { id: 'crm', label: 'CRM', icon: 'fas fa-id-card', link: localServiceUrl(9008), title: 'CRM (Clientes)' },
        { id: 'bodega', label: 'Bodega', icon: 'fas fa-warehouse', link: localServiceUrl(9007), title: 'Bodega (WMS)' },
        { id: 'ia', label: 'IA (ULTRON)', icon: 'fas fa-robot', link: localServiceUrl(9010, '/'), title: 'Asistente IA' },
        { id: 'zabbix', label: 'Zabbix', icon: 'fas fa-signal', link: localServiceUrl(9011, '/'), title: 'Monitoreo' },
        { id: 'terreneitor', label: 'Terreneitor', icon: 'fas fa-camera', link: localServiceUrl(8005, '/'), title: 'Terreneitor (Informes de Terreno)' },
        { id: 'config', label: 'Configuración', icon: 'fas fa-cog', link: localServiceUrl(9001, '/configuracion'), title: 'Configuración' },
    ];

    const currentPath = window.location.pathname;
    const currentHost = window.location.hostname;
    const currentModule = (document.body?.dataset?.currentModule || '').trim().toLowerCase();
    const enabledModules = String(document.body?.dataset?.enabledModules || '')
        .split(',')
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean);

    (async () => {
        let allowed = [];
        try {
            const data = await window.fetchApi('/api/sesion');
            if (data.ok) {
                allowed = data.allowed_modules || [];

                const whoEl = document.getElementById('who');
                if (whoEl) {
                    const userName = data.user || 'Usuario';
                    const userRole = (data.role || 'user').toUpperCase();
                    let displayName = userName;
                    if (userName.includes('@')) {
                        displayName = userName.split('@')[0].replace('.', ' ');
                        displayName = displayName.replace(/\b\w/g, l => l.toUpperCase());
                    }

                    whoEl.innerHTML = `
                        <div style="font-size: 0.85rem; font-weight: 700;">${displayName}</div>
                        <div style="font-size: 0.72rem; opacity: 0.7; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px;">${userRole}</div>
                    `;
                    whoEl.style.opacity = '1';
                    whoEl.title = userName;
                }
            } else {
                console.warn('Sesión API respondió con error:', data.detail);
            }
        } catch (e) {
            console.warn('Sidebar session check failed', e);
        }

        // Fallback: Si no hay módulos del backend, usar los declarados en el HTML
        if (allowed.length === 0 && enabledModules.length > 0) {
            console.log("Usando fallback de enabledModules:", enabledModules);
            allowed = enabledModules;
        }

        // Lógica simplificada: Confiar 100% en allowed_modules del backend
        let visibleItems = menuItems.filter((item) => {
            return allowed.includes('*') || allowed.includes(item.id);
        });


        let activeItemId = currentModule || '';
        if (!activeItemId) {
            if (isProdHost) {
                const currentNormalized = currentPath.replace(/\/+$/, '') || '/';
                for (const item of visibleItems) {
                    try {
                        const targetUrl = new URL(item.link);
                        const targetNormalized = targetUrl.pathname.replace(/\/+$/, '') || '/';
                        const sameHost = currentHost === targetUrl.hostname;
                        const matchesPath = currentNormalized === targetNormalized
                            || currentNormalized.startsWith(`${targetNormalized}/`);
                        if (sameHost && matchesPath) {
                            activeItemId = item.id;
                            break;
                        }
                    } catch (e) { }
                }
            } else {
                const cleanPath = currentPath.replace(/^\/dev(?=\/|$)/, '');
                for (const item of visibleItems) {
                    const itemPath = item.link.replace(/\?.*$/, '');
                    const isDashboardMatch = item.link.includes('dashboard.html')
                        && (cleanPath === '/' || cleanPath === '/index.html' || cleanPath.includes('dashboard.html') || cleanPath.includes('inicio.html'));
                    const isModuleMatch = !item.link.includes('dashboard.html') && cleanPath.includes(itemPath);
                    const isBodegaCatalogMatch = item.label === 'Bodega' && cleanPath.includes('catalogo.html');
                    if (isDashboardMatch || isModuleMatch || isBodegaCatalogMatch) {
                        activeItemId = item.id;
                        break;
                    }
                }
            }
        }

        sidebar.innerHTML = visibleItems.map(item => `
            <a href="${item.link}" class="side-link ${item.id === activeItemId ? 'active' : ''}" data-module-id="${item.id}" title="${item.title}">
                <i class="${item.icon}"></i> <span>${item.label}</span>
            </a>
        `).join('');

        const activeLinks = sidebar.querySelectorAll('.side-link.active');
        if (activeLinks.length > 1) {
            activeLinks.forEach(link => link.classList.remove('active'));
            const canonicalActive = activeItemId
                ? sidebar.querySelector(`.side-link[data-module-id="${activeItemId}"]`)
                : null;
            if (canonicalActive) canonicalActive.classList.add('active');
        }
    })();

    const headerActions = document.querySelector('.header-actions');
    if (headerActions) {
        let footerContainer = headerActions.querySelector('.footer-buttons-container');
        if (!footerContainer) {
            footerContainer = document.createElement('div');
            footerContainer.className = 'footer-buttons-container';
        }

        let whoEl = headerActions.querySelector('#who');
        if (!whoEl) {
            whoEl = document.createElement('span');
            whoEl.id = 'who';
            whoEl.className = 'pill shell-who-pill';
            whoEl.textContent = 'Usuario';
        }
        whoEl.classList.add('pill', 'shell-who-pill');
        whoEl.removeAttribute('style');
        headerActions.insertBefore(whoEl, headerActions.firstChild);

        let btnAccount = headerActions.querySelector('#btn-open-change-password');
        if (!btnAccount) {
            btnAccount = document.createElement('button');
            btnAccount.id = 'btn-open-change-password';
            btnAccount.innerHTML = '<i class="fas fa-key"></i> <span>Cuenta</span>';
        }
        btnAccount.className = 'btn-account';
        btnAccount.title = 'Cambiar Contraseña';

        let btnLogout = headerActions.querySelector('#btnLogout');
        if (!btnLogout) {
            btnLogout = document.createElement('button');
            btnLogout.id = 'btnLogout';
            btnLogout.innerHTML = '<i class="fas fa-sign-out-alt"></i> <span>Salir</span>';
        }
        if (btnAccount.parentElement !== footerContainer) footerContainer.appendChild(btnAccount);
        if (btnLogout) {
            btnLogout.classList.add('btn-logout');
            if (btnLogout.parentElement !== footerContainer) footerContainer.appendChild(btnLogout);
        }
        if (footerContainer.parentElement !== headerActions) headerActions.appendChild(footerContainer);

        if (typeof window.initModal === 'function') window.initModal();
        if (typeof window.initLogout === 'function') window.initLogout();

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

            footerContainer.insertBefore(btnEnv, footerContainer.firstChild);
        }
    }

    const p = window.location.pathname;
    if (p.includes('bodega.html') && window.initBodega) window.initBodega();
});
