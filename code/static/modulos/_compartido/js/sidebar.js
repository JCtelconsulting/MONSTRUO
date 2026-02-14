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
                'redes': ['dashboard', 'tks'],
                'sistemas': ['dashboard', 'tks'],
                'implementaciones': ['dashboard', 'tks', 'pmo'],
                'gerencia': ['dashboard', 'pmo', 'erp', 'crm', 'ia', 'zabbix'],
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
    // NOTIFICACIONES IN-APP (Campanita)
    // ========================================================================
    (function initNotifications() {
        // Solo si hay usuario logueado (verificamos si existe btnLogout o who)
        if (!document.getElementById('btnLogout')) return;

        // En la página de ticketera ya existe un poll propio para evitar doble carga.
        const isTicketeraPage =
            window.location.pathname.includes('/modulos/tks/') ||
            window.location.hostname.startsWith('ticketera.');
        if (isTicketeraPage) return;

        const headerActions = document.querySelector('.header-actions');
        if (!headerActions) return;
        let notifInFlight = false;

        // Crear contenedor de notificaciones si no existe
        let notifContainer = document.getElementById('notif-container');
        if (!notifContainer) {
            notifContainer = document.createElement('div');
            notifContainer.id = 'notif-container';
            notifContainer.style.cssText = 'position:relative; margin-right:15px; cursor:pointer;';

            notifContainer.innerHTML = `
                <i class="fas fa-bell" style="font-size:1.2rem; color:rgba(255,255,255,0.7);"></i>
                <span id="notif-badge" style="
                    display:none; position:absolute; top:-5px; right:-5px; 
                    background:#ff4444; color:white; font-size:0.65rem; 
                    padding:2px 5px; border-radius:10px; font-weight:bold;
                    box-shadow:0 0 5px rgba(255,68,68,0.5);">0</span>
                <div id="notif-dropdown" style="
                    display:none; position:absolute; top:35px; right:0; 
                    width:320px; background:#1a1a1a; border:1px solid rgba(255,255,255,0.1); 
                    border-radius:8px; box-shadow:0 10px 30px rgba(0,0,0,0.5); z-index:1000;
                    overflow:hidden; max-height:400px; display:flex; flex-direction:column;">
                    <div style="padding:10px 15px; border-bottom:1px solid rgba(255,255,255,0.1); font-weight:bold; font-size:0.85rem; background:rgba(255,255,255,0.03);">
                        Notificaciones
                    </div>
                    <div id="notif-list" style="overflow-y:auto; max-height:350px;">
                        <div style="padding:20px; text-align:center; opacity:0.5; font-size:0.8rem;">Cargando...</div>
                    </div>
                </div>
            `;

            // Insertar antes del perfil/usuario
            const firstItem = headerActions.firstChild;
            headerActions.insertBefore(notifContainer, firstItem);

            // Toggle dropdown
            notifContainer.addEventListener('click', (e) => {
                e.stopPropagation();
                const dd = document.getElementById('notif-dropdown');
                const isHidden = dd.style.display === 'none';
                dd.style.display = isHidden ? 'block' : 'none';
                if (isHidden) markAsSeen();
            });

            // Cerrar al hacer click fuera
            document.addEventListener('click', () => {
                const dd = document.getElementById('notif-dropdown');
                if (dd) dd.style.display = 'none';
            });
        }

        async function checkNotifications() {
            if (document.hidden || notifInFlight) return;
            notifInFlight = true;
            try {
                const data = await window.fetchApi('/api/tks/notificaciones?limit=10', { timeoutMs: 8000 });
                // fetchApi already returns the parsed JSON or error object

                const items = data.items || [];
                const badge = document.getElementById('notif-badge');
                const list = document.getElementById('notif-list');

                // Update badge
                const unread = items.length; // Suponemos que la API devuelve solo pendientes/no leídas o filtramos
                if (unread > 0) {
                    badge.textContent = unread > 9 ? '9+' : unread;
                    badge.style.display = 'block';
                } else {
                    badge.style.display = 'none';
                }

                // Helper anti-XSS
                const escapeHtml = Str => {
                    if (!Str) return Str;
                    return String(Str)
                        .replace(/&/g, '&amp;')
                        .replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;')
                        .replace(/"/g, '&quot;')
                        .replace(/'/g, '&#039;');
                };

                // Update list content
                list.innerHTML = ''; // Limpiar lista
                if (items.length === 0) {
                    list.innerHTML = '<div style="padding:20px; text-align:center; opacity:0.5; font-size:0.8rem;">Sin notificaciones nuevas</div>';
                } else {
                    // Obtener URL base de Ticketera según entorno actual
                    const tksItem = menuItems.find(i => i.title === 'Ticketera');
                    let tksBaseUrl = tksItem ? tksItem.link : '/modulos/tks/tks.html';

                    items.forEach(n => {
                        // Construir URL de forma segura
                        // ticket_id como entero para evitar inyecciones en URL
                        const ticketId = parseInt(n.ticket_id, 10);
                        const sep = tksBaseUrl.includes('?') ? '&' : '?';
                        const targetUrl = `${tksBaseUrl}${sep}ticket_id=${ticketId}`;

                        const div = document.createElement('div');
                        div.className = 'notif-item';
                        div.style.cssText = 'padding:12px 15px; border-bottom:1px solid rgba(255,255,255,0.05); cursor:pointer; transition:background 0.2s;';

                        // Event listeners en lugar de onclick inline
                        div.addEventListener('click', () => { window.location.href = targetUrl; });
                        div.addEventListener('mouseenter', () => div.style.background = 'rgba(255,255,255,0.05)');
                        div.addEventListener('mouseleave', () => div.style.background = 'transparent');

                        // Escapado de HTML
                        const safeCode = escapeHtml(n.codigo || 'TK-????');
                        const safeTitle = escapeHtml(n.titulo);
                        const safeTime = new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                        const statusText = n.status === 'pending' ? '🔴 Nueva asignación' : 'Mensaje nuevo';

                        div.innerHTML = `
                            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                                <span style="font-size:0.75rem; color:#44ff88; font-weight:bold;">${safeCode}</span>
                                <span style="font-size:0.7rem; opacity:0.5;">${safeTime}</span>
                            </div>
                            <div style="font-size:0.85rem; line-height:1.3;">${safeTitle}</div>
                            <div style="font-size:0.75rem; opacity:0.7; margin-top:2px;">${statusText}</div>
                        `;

                        list.appendChild(div);
                    });
                }

            } catch (e) {
                console.warn('Error polling notifications:', e);
            } finally {
                notifInFlight = false;
            }
        }

        async function markAsSeen() {
            // Aquí idealmente llamaríamos a un endpoint PATCH /notificaciones/mark-seen
            // Por ahora solo ocultamos el badge visualmente hasta el próximo poll
            document.getElementById('notif-badge').style.display = 'none';
        }

        // Poll inicial y luego cada 60s
        checkNotifications();
        setInterval(checkNotifications, 60000);
    })();
});
