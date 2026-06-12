/**
 * Gestion de usuarios por roles (sin especialidades)
 */
const UsersUI = (() => {
    let _users = [];
    let _secondaryRolesDraft = [];
    let _tableActionsBound = false;
    let _roleScopes = new Map();
    let _roleScopeItems = [];
    let _allPermissions = [];      // [{id, label}] from API
    let _editingRole = null;       // role being edited in modal
    let _editingRolePerms = [];    // current draft permissions
    let _currentUsername = '';     // username del usuario logueado, resuelto en load()

    const MONSTRUO_ROLES = [
        { id: 'admin',            label: 'Admin (super)' },
        { id: 'encargado_mesa',   label: 'Encargado Mesa Ayuda' },
        { id: 'redes',            label: 'Redes' },
        { id: 'sistemas',         label: 'Sistemas' },
        { id: 'implementaciones', label: 'Implementaciones' },
        { id: 'gerencia',         label: 'Gerencia' },
        { id: 'ops',              label: 'Operaciones' },
        { id: 'finance',          label: 'Finanzas' },
        { id: 'warehouse',        label: 'Bodega' },
    ];

    const FUNDACION_ROLES = [
        { id: 'directora_social',          label: 'Directora Social' },
        { id: 'jefa_pedagogica',           label: 'Jefa Pedagógica' },
        { id: 'coordinadora_territorial',  label: 'Coordinadora Territorial' },
        { id: 'lider_educativo',           label: 'Líder Educativo' },
        { id: 'gestora_educativa',         label: 'Gestora Educativa' },
    ];

    const MONSTRUO_ROLE_IDS = new Set(MONSTRUO_ROLES.map(r => r.id));
    const FUNDACION_ROLE_IDS = new Set(FUNDACION_ROLES.map(r => r.id));

    // Compat: el resto del archivo aún referencia ROLE_OPTIONS para llenar
    // selects de rol primario. Combinamos ambos grupos en un único listado
    // ordenado (Monstruo primero, Fundación después).
    const ROLE_OPTIONS = [...MONSTRUO_ROLES, ...FUNDACION_ROLES];

    const ROLE_SCOPE_FALLBACK = {
        admin: {
            description: 'Control total de plataforma, seguridad y configuracion global.',
            permissions: ['Acceso total del sistema']
        },
        encargado_mesa: {
            description: 'Gestiona flujo de ticketera, asignacion, seguimiento y cumplimiento.',
            permissions: [
                'Dashboard: lectura',
                'Ticketera: lectura',
                'Ticketera: gestion operativa',
                'Ticketera: compliance y evidencias',
                'Auditoria: lectura'
            ]
        },
        ops: {
            description: 'Operacion tecnica transversal para atencion y despacho de tickets.',
            permissions: [
                'Dashboard: lectura',
                'Facturacion: lectura',
                'Facturacion: sincronizacion',
                'Bodega: lectura',
                'Ticketera: lectura',
                'Ticketera: gestion operativa',
                'CRM: lectura',
                'CRM: edicion',
                'Auditoria: lectura',
                'Configuracion administrativa'
            ]
        },
        redes: {
            description: 'Ejecucion tecnica en networking e incidencias de conectividad.',
            permissions: [
                'Dashboard: lectura',
                'Ticketera: lectura',
                'Ticketera: gestion operativa'
            ]
        },
        sistemas: {
            description: 'Ejecucion tecnica en servidores, plataformas y sistemas.',
            permissions: [
                'Dashboard: lectura',
                'Ticketera: lectura',
                'Ticketera: gestion operativa'
            ]
        },
        implementaciones: {
            description: 'Ejecucion de despliegues/proyectos con alcance tecnico.',
            permissions: [
                'Dashboard: lectura',
                'Ticketera: lectura',
                'Ticketera: gestion operativa',
                'PMO: lectura',
                'PMO: edicion'
            ]
        },
        finance: {
            description: 'Gestion financiera y cobranza con foco contable.',
            permissions: [
                'Dashboard: lectura',
                'Facturacion: lectura',
                'Facturacion: edicion',
                'Facturacion: anulacion',
                'Pagos: gestion',
                'CRM: lectura',
                'CRM: edicion',
                'Auditoria: exportacion'
            ]
        },
        warehouse: {
            description: 'Gestion operativa de inventario y movimientos de bodega.',
            permissions: [
                'Bodega: lectura',
                'Bodega: edicion'
            ]
        },
        gerencia: {
            description: 'Vision ejecutiva y lectura de indicadores/estado operacional.',
            permissions: [
                'Dashboard: lectura',
                'Ticketera: lectura',
                'PMO: lectura',
                'Finanzas: lectura',
                'Auditoria: lectura',
                'Reportes: lectura'
            ]
        },
        directora_social: {
            description: 'Dirección estratégica de la Fundación (super-scope a sedes).',
            permissions: [
                'Dashboard: lectura',
                'Fundacion: lectura',
                'Fundacion: escritura',
                'Auditoria: lectura'
            ]
        },
        jefa_pedagogica: {
            description: 'Lidera la línea pedagógica de la Fundación (super-scope a sedes).',
            permissions: [
                'Dashboard: lectura',
                'Fundacion: lectura',
                'Fundacion: escritura',
                'Auditoria: lectura'
            ]
        },
        coordinadora_territorial: {
            description: 'Coordina territorialmente las sedes (super-scope a sedes).',
            permissions: [
                'Dashboard: lectura',
                'Fundacion: lectura',
                'Fundacion: escritura',
                'Auditoria: lectura'
            ]
        },
        lider_educativo: {
            description: 'Responsable de una o más sedes; el alcance lo define la membresía.',
            permissions: [
                'Dashboard: lectura',
                'Fundacion: lectura',
                'Fundacion: escritura'
            ]
        },
        gestora_educativa: {
            description: 'Operación educativa dentro de su sede asignada.',
            permissions: [
                'Dashboard: lectura',
                'Fundacion: lectura',
                'Fundacion: escritura',
                'Auditoria: lectura'
            ]
        }
    };

    const MODULES = [
        { id: 'dashboard', label: 'Dashboard' },
        { id: 'tks', label: 'Ticketera' },
        { id: 'pmo', label: 'Proyectos (PMO)' },
        { id: 'erp', label: 'ERP & Finanzas' },
        { id: 'crm', label: 'CRM' },
        { id: 'bodega', label: 'Bodega' },
        { id: 'ia', label: 'IA (Ultron)' },
        { id: 'zabbix', label: 'Zabbix' },
        { id: 'fundacion', label: 'Fundación' },
        { id: 'terreneitor', label: 'Terreneitor' },
        { id: 'config', label: 'Configuracion' }
    ];

    const ROLE_ORDER = Object.freeze(
        ROLE_OPTIONS.reduce((acc, item, idx) => {
            acc[item.id] = idx;
            return acc;
        }, {})
    );

    const SCOPE_MODULE_ORDER = Object.freeze({
        acceso_total_del_sistema: 0,
        dashboard: 10,
        ticketera: 20,
        pmo: 30,
        crm: 40,
        bodega: 50,
        facturacion: 60,
        pagos: 70,
        finanzas: 80,
        auditoria: 90,
        reportes: 100,
        fundacion: 105,
        terreneitor: 107,
        configuracion_administrativa: 110,
    });

    const SCOPE_ACTION_ORDER = Object.freeze({
        lectura: 10,
        read: 10,
        sincronizacion: 20,
        sync: 20,
        gestion_operativa: 30,
        gestion: 35,
        write: 40,
        edicion: 40,
        compliance: 50,
        compliance_y_evidencias: 50,
        exportacion: 60,
        anulacion: 70,
    });

    const KNOWN_SCOPE_MODULES = new Set([
        'dashboard',
        'ticketera',
        'pmo',
        'crm',
        'bodega',
        'facturacion',
        'pagos',
        'finanzas',
        'auditoria',
        'reportes',
        'fundacion',
        'terreneitor',
        'configuracion_administrativa',
        'acceso_total_del_sistema',
    ]);

    function escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function encodeDataset(value) {
        return encodeURIComponent(String(value || ''));
    }

    function decodeDataset(value) {
        try {
            return decodeURIComponent(String(value || ''));
        } catch (_) {
            return String(value || '');
        }
    }

    function normalizeUsername(value) {
        return String(value || '').trim().toLowerCase();
    }

    function normalizeKey(value) {
        return String(value || '')
            .trim()
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .replace(/\s+/g, '_');
    }

    function roleLabel(role) {
        const normalized = normalizeKey(role);
        const item = ROLE_OPTIONS.find((r) => r.id === normalized);
        return item ? item.label : (normalized || '-');
    }

    function normalizeRoleList(primaryRole, secondaryRoles = []) {
        const out = [];
        const pushRole = (value) => {
            const role = normalizeKey(value);
            if (!role || out.includes(role)) return;
            out.push(role);
        };
        pushRole(primaryRole);
        if (Array.isArray(secondaryRoles)) {
            secondaryRoles.forEach(pushRole);
        }
        return out;
    }

    function permissionFallbackLabel(permission) {
        const normalized = normalizeKey(permission).replace(/_/g, ':');
        const map = {
            '*': 'Acceso total del sistema',
            'dashboard:read': 'Dashboard: lectura',
            'tickets:read': 'Ticketera: lectura',
            'tickets:write': 'Ticketera: gestion operativa',
            'tickets:compliance': 'Ticketera: compliance',
            'admin.settings': 'Configuracion administrativa',
            'audit:read': 'Auditoria: lectura',
            'audit:export': 'Auditoria: exportacion',
            'invoice:read': 'Facturacion: lectura',
            'invoice:write': 'Facturacion: edicion',
            'invoice:sync': 'Facturacion: sincronizacion',
            'invoice:void': 'Facturacion: anulacion',
            'payment:write': 'Pagos: gestion',
            'crm:read': 'CRM: lectura',
            'crm:write': 'CRM: edicion',
            'bodega:read': 'Bodega: lectura',
            'bodega:write': 'Bodega: edicion',
            'pmo:read': 'PMO: lectura',
            'pmo:write': 'PMO: edicion',
            'reports:read': 'Reportes: lectura',
            'fundacion:read': 'Fundacion: lectura',
            'fundacion:write': 'Fundacion: escritura',
            'finanzas:read': 'Finanzas: lectura'
        };
        if (map[normalized]) return map[normalized];
        if (!normalized) return '-';
        if (normalized.includes(':')) {
            const [prefix, action] = normalized.split(':', 2);
            return `${prefix.toUpperCase()}: ${action}`;
        }
        return normalized;
    }

    function parseScopeLabel(label) {
        const raw = String(label || '').trim();
        if (!raw) return { module: '', action: '' };
        if (raw.includes(':')) {
            const [modulePart, actionPart] = raw.split(':', 2);
            return {
                module: normalizeKey(modulePart),
                action: normalizeKey(actionPart),
            };
        }
        return {
            module: normalizeKey(raw),
            action: '',
        };
    }

    function compareScopeLabels(a, b) {
        const pa = parseScopeLabel(a);
        const pb = parseScopeLabel(b);
        const moduleRankA = Object.prototype.hasOwnProperty.call(SCOPE_MODULE_ORDER, pa.module)
            ? SCOPE_MODULE_ORDER[pa.module]
            : 999;
        const moduleRankB = Object.prototype.hasOwnProperty.call(SCOPE_MODULE_ORDER, pb.module)
            ? SCOPE_MODULE_ORDER[pb.module]
            : 999;
        if (moduleRankA !== moduleRankB) return moduleRankA - moduleRankB;

        const actionRankA = Object.prototype.hasOwnProperty.call(SCOPE_ACTION_ORDER, pa.action)
            ? SCOPE_ACTION_ORDER[pa.action]
            : 999;
        const actionRankB = Object.prototype.hasOwnProperty.call(SCOPE_ACTION_ORDER, pb.action)
            ? SCOPE_ACTION_ORDER[pb.action]
            : 999;
        if (actionRankA !== actionRankB) return actionRankA - actionRankB;

        return String(a || '').localeCompare(String(b || ''), 'es');
    }

    function setRoleScopes(items) {
        _roleScopes = new Map();
        _roleScopeItems = [];

        const list = Array.isArray(items) ? items : [];
        list.forEach((rawItem) => {
            const role = normalizeKey(rawItem?.role);
            if (!role) return;

            const permissions = [];
            const seen = new Set();
            const detail = Array.isArray(rawItem?.permissions_detail) ? rawItem.permissions_detail : [];
            if (detail.length > 0) {
                detail.forEach((entry) => {
                    const label = String(entry?.label || entry?.id || '').trim();
                    if (!label || seen.has(label)) return;
                    seen.add(label);
                    permissions.push(label);
                });
            } else {
                const rawPerms = Array.isArray(rawItem?.permissions) ? rawItem.permissions : [];
                rawPerms.forEach((perm) => {
                    const label = permissionFallbackLabel(perm);
                    if (!label || seen.has(label)) return;
                    seen.add(label);
                    permissions.push(label);
                });
            }

            const item = {
                role,
                label: String(rawItem?.label || roleLabel(role) || role).trim(),
                description: String(rawItem?.description || '').trim(),
                permissions: permissions.sort(compareScopeLabels)
            };
            _roleScopes.set(role, item);
            _roleScopeItems.push(item);
        });

        _roleScopeItems.sort((a, b) => {
            const ar = Object.prototype.hasOwnProperty.call(ROLE_ORDER, a.role) ? ROLE_ORDER[a.role] : 999;
            const br = Object.prototype.hasOwnProperty.call(ROLE_ORDER, b.role) ? ROLE_ORDER[b.role] : 999;
            if (ar !== br) return ar - br;
            return String(a.label || a.role).localeCompare(String(b.label || b.role), 'es');
        });
    }

    function fallbackRoleScopes() {
        return ROLE_OPTIONS.map((roleItem) => {
            const role = roleItem.id;
            const fallback = ROLE_SCOPE_FALLBACK[role] || {};
            const perms = Array.isArray(fallback.permissions) ? fallback.permissions : [];
            return {
                role,
                label: roleItem.label,
                description: String(fallback.description || 'Rol operativo de plataforma.'),
                permissions: perms.map((p) => String(p || '').trim()).filter(Boolean),
                permissions_detail: perms.map((p) => ({ id: normalizeKey(p).replace(/_/g, ':'), label: String(p || '').trim() }))
            };
        });
    }

    function renderRoleBadges(roleIds) {
        const roles = Array.isArray(roleIds) ? roleIds : [];
        if (!roles.length) return '<span class="cfg-muted">Sin roles</span>';
        return roles.map((role, idx) => {
            const label = escapeHtml(roleLabel(role));
            const toneClass = idx === 0 ? 'is-primary' : '';
            return `<span class="cfg-role-pill ${toneClass}">${label}</span>`;
        }).join('');
    }

    function scopeModuleClass(scopeLabel) {
        const module = parseScopeLabel(scopeLabel).module || 'default';
        const safe = String(module).replace(/[^a-z0-9_]/g, '_') || 'default';
        if (!KNOWN_SCOPE_MODULES.has(safe)) return 'scope-mod-default';
        return `scope-mod-${safe}`;
    }

    function renderScopePills(scopeLabels) {
        if (!Array.isArray(scopeLabels) || !scopeLabels.length) {
            return '<span class="cfg-muted">Sin permisos definidos</span>';
        }
        return `<div class="cfg-scope-list">${scopeLabels.map((scope) => `
            <span class="cfg-scope-pill ${scopeModuleClass(scope)}">${escapeHtml(scope)}</span>
        `).join('')}</div>`;
    }

    function renderRolesCell(roleIds) {
        return `
            <div class="cfg-profile-cell">
                <div class="cfg-profile-block">
                    <span class="cfg-profile-label">Roles</span>
                    <div class="cfg-profile-roles">${renderRoleBadges(roleIds)}</div>
                </div>
            </div>
        `;
    }

    function scopesForRoles(roleIds) {
        const roles = Array.isArray(roleIds) ? roleIds : [];
        const scopes = [];
        const seen = new Set();

        roles.forEach((roleId) => {
            const role = normalizeKey(roleId);
            const roleScope = _roleScopes.get(role);
            if (!roleScope || !Array.isArray(roleScope.permissions)) return;
            roleScope.permissions.forEach((label) => {
                const clean = String(label || '').trim();
                if (!clean || seen.has(clean)) return;
                seen.add(clean);
                scopes.push(clean);
            });
        });
        return scopes.sort(compareScopeLabels);
    }

    function renderRoleGuide() {
        const body = document.getElementById('cfgRoleGuideBody');
        if (!body) return;

        if (!_roleScopeItems.length) {
            body.innerHTML = '<div class="cfg-role-guide-empty">No se pudo cargar la matriz de alcances.</div>';
            return;
        }

        const monstruo = [];
        const fundacion = [];
        const otros = [];
        _roleScopeItems.forEach(item => {
            const id = String(item.role || '').toLowerCase();
            if (FUNDACION_ROLE_IDS.has(id))      fundacion.push(item);
            else if (MONSTRUO_ROLE_IDS.has(id))  monstruo.push(item);
            else                                  otros.push(item);
        });

        const renderItem = (item) => {
            const perms = Array.isArray(item.permissions) ? item.permissions : [];
            const encodedRole = encodeDataset(item.role);
            return `
                <article class="cfg-role-guide-row" data-role="${encodedRole}" title="Clic para editar permisos">
                    <div class="cfg-role-guide-head">
                        <div class="cfg-role-guide-title">
                            ${escapeHtml(item.label || roleLabel(item.role) || item.role)}
                            <span class="cfg-role-edit-hint"><i class="fas fa-pencil-alt"></i> editar</span>
                        </div>
                        <p class="cfg-role-guide-desc">${escapeHtml(item.description || 'Rol operativo de plataforma.')}</p>
                    </div>
                    <div class="cfg-role-guide-perms">${renderScopePills(perms)}</div>
                </article>
            `;
        };

        const renderGroup = (titulo, icon, items) => {
            if (!items.length) return '';
            return `
                <div class="cfg-role-group">
                    <h5 class="cfg-role-group-title"><i class="fas ${icon}"></i> ${escapeHtml(titulo)}</h5>
                    <div class="cfg-role-group-items">${items.map(renderItem).join('')}</div>
                </div>
            `;
        };

        body.innerHTML = [
            renderGroup('Monstruo', 'fa-server', monstruo),
            renderGroup('Fundación', 'fa-school', fundacion),
            renderGroup('Otros', 'fa-circle-question', otros),
        ].filter(Boolean).join('');

        body.querySelectorAll('.cfg-role-guide-row[data-role]').forEach((row) => {
            row.addEventListener('click', () => {
                const role = decodeDataset(row.dataset.role || '');
                if (role) openRolePermsModal(role);
            });
        });
    }

    function _getEffectivePermissions() {
        if (_allPermissions.length > 0) return _allPermissions;
        // fallback: build from PERMISSION_LABELS keys in users_ui
        return Object.keys({
            '*': 1, 'dashboard:read': 1, 'tickets:read': 1, 'tickets:write': 1,
            'tickets:compliance': 1, 'audit:read': 1, 'audit:export': 1,
            'invoice:read': 1, 'invoice:sync': 1, 'invoice:write': 1, 'invoice:void': 1,
            'payment:write': 1, 'crm:read': 1, 'crm:write': 1, 'bodega:read': 1,
            'bodega:write': 1, 'pmo:read': 1, 'pmo:write': 1, 'finanzas:read': 1,
            'reports:read': 1, 'fundacion:read': 1, 'fundacion:write': 1,
            'admin.settings': 1, 'zabbix:read': 1, 'ia:read': 1, 'gta:read': 1, 'gta:write': 1,
        }).map(id => ({ id, label: permissionFallbackLabel(id) }));
    }

    function openRolePermsModal(role) {
        const roleItem = _roleScopes.get(normalizeKey(role));
        if (!roleItem) return;

        _editingRole = role;
        _editingRolePerms = [...(roleItem.permissions || [])];

        const modal = document.getElementById('modalRolePerms');
        const title = document.getElementById('modalRolePermsTitle');
        const desc = document.getElementById('modalRolePermsDesc');
        const adminNotice = document.getElementById('modalRolePermsAdminNotice');
        const grid = document.getElementById('permGrid');
        if (!modal) return;

        title.textContent = `Permisos: ${roleItem.label || role}`;
        desc.textContent = roleItem.description || '';
        adminNotice.style.display = role === 'admin' ? 'block' : 'none';

        const allPerms = _getEffectivePermissions();
        grid.innerHTML = '';

        allPerms.forEach(({ id, label }) => {
            const isChecked = _editingRolePerms.includes(id);
            const isLocked = role === 'admin' && id === '*';

            const div = document.createElement('div');
            div.className = `perm-check-item${isChecked ? ' is-checked' : ''}`;
            div.innerHTML = `
                <input type="checkbox" ${isChecked ? 'checked' : ''} ${isLocked ? 'disabled' : ''}>
                <span class="perm-check-mark">${isChecked ? '✓' : ''}</span>
                <span class="perm-check-label">${escapeHtml(label || id)}</span>
            `;
            if (!isLocked) {
                div.addEventListener('click', () => {
                    const cb = div.querySelector('input');
                    cb.checked = !cb.checked;
                    if (cb.checked) {
                        if (!_editingRolePerms.includes(id)) _editingRolePerms.push(id);
                        div.classList.add('is-checked');
                        div.querySelector('.perm-check-mark').textContent = '✓';
                    } else {
                        _editingRolePerms = _editingRolePerms.filter(p => p !== id);
                        div.classList.remove('is-checked');
                        div.querySelector('.perm-check-mark').textContent = '';
                    }
                });
            }
            grid.appendChild(div);
        });

        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeRolePermsModal() {
        const modal = document.getElementById('modalRolePerms');
        if (!modal) return;
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
        _editingRole = null;
        _editingRolePerms = [];
    }

    async function saveRolePerms() {
        if (!_editingRole) return;
        const roleItem = _roleScopes.get(normalizeKey(_editingRole));
        const description = roleItem?.description || '';
        try {
            await window.fetchApi(`/api/config/role-scopes/${encodeURIComponent(_editingRole)}`, {
                method: 'PUT',
                body: { description, permissions: _editingRolePerms },
            });
            closeRolePermsModal();
            await load();
            if (window.showToast) window.showToast(`Permisos de "${_editingRole}" actualizados.`, 'success');
        } catch (err) {
            alert(`Error al guardar: ${err.message}`);
        }
    }

    function renderUserScopeGuide() {
        const body = document.getElementById('cfgUserScopesBody');
        if (!body) return;

        if (!_users.length) {
            body.innerHTML = '<div class="cfg-role-guide-empty">No hay usuarios registrados.</div>';
            return;
        }

        body.innerHTML = [..._users]
            .sort((a, b) => String(a?.username || '').localeCompare(String(b?.username || ''), 'es'))
            .map((user) => {
                const username = String(user?.username || '').trim();
                const roleIds = normalizeRoleList(user?.role, user?.secondary_roles);
                const scopes = scopesForRoles(roleIds);
                return `
                    <article class="cfg-user-scope-row">
                        <div class="cfg-user-scope-head">
                            <div class="cfg-user-scope-name">${escapeHtml(username)}</div>
                            <div class="cfg-profile-roles">${renderRoleBadges(roleIds)}</div>
                        </div>
                        <div class="cfg-user-scope-perms">${renderScopePills(scopes)}</div>
                    </article>
                `;
            })
            .join('');
    }

    function bindTableActions() {
        if (_tableActionsBound) return;
        const tbody = document.getElementById('tbodyUsers');
        if (!tbody) return;

        tbody.addEventListener('click', async (evt) => {
            const actionBtn = evt.target.closest('button[data-action]');
            if (!actionBtn) return;

            const action = String(actionBtn.dataset.action || '').trim();
            const username = decodeDataset(actionBtn.dataset.username || '');
            if (!username) return;

            if (action === 'edit') {
                openModal(username);
                return;
            }

            if (action === 'delete') {
                await deleteUser(username);
            }
        });

        _tableActionsBound = true;
    }

    function renderTable() {
        const tbody = document.getElementById('tbodyUsers');
        if (!tbody) return;

        if (!_users.length) {
            tbody.innerHTML = '<tr class="cfg-placeholder-row"><td colspan="4">No hay usuarios registrados</td></tr>';
            return;
        }

        const rows = [..._users]
            .sort((a, b) => String(a?.username || '').localeCompare(String(b?.username || ''), 'es'))
            .map((user) => {
                const username = String(user?.username || '').trim();
                const encodedUsername = encodeDataset(username);
                const statusBadge = user?.is_active
                    ? '<span class="cfg-state-pill is-active">Activo</span>'
                    : '<span class="cfg-state-pill is-inactive">Inactivo</span>';
                const roleIds = normalizeRoleList(user?.role, user?.secondary_roles);

                return `
                    <tr>
                        <td class="cfg-table-cell-strong">${escapeHtml(username)}</td>
                        <td>${renderRolesCell(roleIds)}</td>
                        <td>${statusBadge}</td>
                        <td class="ta-right">
                            <div class="cfg-action-group">
                                <button class="btn-icon-sm" data-action="edit" data-username="${encodedUsername}" title="Editar usuario">
                                    <i class="fas fa-edit"></i>
                                </button>
                                ${username !== _currentUsername
                        ? `<button class="btn-icon-sm btn-icon-danger" data-action="delete" data-username="${encodedUsername}" title="Eliminar usuario"><i class="fas fa-trash"></i></button>`
                        : '<span class="cfg-self-lock" title="No podés eliminarte a vos mismo"><i class="fas fa-lock"></i></span>'}
                            </div>
                        </td>
                    </tr>
                `;
            })
            .join('');

        tbody.innerHTML = rows;
    }

    async function load() {
        bindTableActions();

        try {
            const [usersData, scopesDataRaw, sesionData] = await Promise.all([
                window.fetchApi('/api/admin/users'),
                window.fetchApi('/api/config/role-scopes').catch(() => null),
                window.fetchApi('/api/sesion').catch(() => null),
            ]);

            // /api/sesion devuelve {user, role, roles, ...}. Tomamos `user`
            // (legacy) o `username` (algunos consumidores), lo que esté.
            _currentUsername = String(sesionData?.user || sesionData?.username || '');
            _users = Array.isArray(usersData?.items) ? usersData.items : [];
            const scopesItems = Array.isArray(scopesDataRaw?.items) && scopesDataRaw.items.length
                ? scopesDataRaw.items
                : fallbackRoleScopes();
            _allPermissions = Array.isArray(scopesDataRaw?.all_permissions) ? scopesDataRaw.all_permissions : [];
            setRoleScopes(scopesItems);

            renderTable();
            renderUserScopeGuide();
            renderRoleGuide();
        } catch (e) {
            console.error('Error loading users view', e);
            const tbody = document.getElementById('tbodyUsers');
            if (tbody) {
                tbody.innerHTML = `<tr class="cfg-placeholder-row error"><td colspan="4">Error: ${escapeHtml(e.message || 'No se pudo cargar')}</td></tr>`;
            }
            const userScopeBody = document.getElementById('cfgUserScopesBody');
            if (userScopeBody) {
                userScopeBody.innerHTML = '<div class="cfg-role-guide-empty">No se pudo cargar permisos por usuario.</div>';
            }
            const body = document.getElementById('cfgRoleGuideBody');
            if (body) {
                body.innerHTML = '<div class="cfg-role-guide-empty">No se pudo cargar la matriz de alcances.</div>';
            }
        }
    }

    function openModal(username = null) {
        const modal = document.getElementById('modalUser');
        const form = document.getElementById('formUser');
        const title = document.getElementById('modalUserTitle');
        const userInput = document.getElementById('inpUsername');
        const container = document.getElementById('containerModules');
        const secondaryContainer = document.getElementById('containerSecondaryRoles');

        form.reset();
        container.innerHTML = '';
        secondaryContainer.innerHTML = '';

        let userModules = [];

        if (username) {
            const user = _users.find((item) => item.username === username);
            if (!user) return;

            title.textContent = 'Editar Usuario';
            userInput.value = user.username;
            userInput.disabled = true;
            document.getElementById('chkActive').checked = user.is_active;
            document.getElementById('inpPassword').placeholder = '(Dejar en blanco para no cambiar)';
            form.dataset.mode = 'edit';
            userModules = user.allowed_modules || [];

            // Combinar rol primario y secundarios en el draft
            _secondaryRolesDraft = normalizeRoleList(user.role, user.secondary_roles);
        } else {
            title.textContent = 'Nuevo Usuario';
            userInput.value = '';
            userInput.disabled = false;
            document.getElementById('inpPassword').placeholder = 'Contrasena';
            document.getElementById('chkActive').checked = true;
            form.dataset.mode = 'create';
            userModules = ['dashboard'];
            _secondaryRolesDraft = [];
        }

        // Renderizar Módulos
        MODULES.forEach((mod) => {
            const checked = userModules.includes(mod.id);
            const div = document.createElement('div');
            div.className = 'cfg-check-item';

            const input = document.createElement('input');
            input.type = 'checkbox';
            input.id = `mod_${mod.id}`;
            input.value = mod.id;
            input.checked = checked;

            const label = document.createElement('label');
            label.textContent = mod.label;

            const mark = document.createElement('span');
            mark.className = 'cfg-check-mark';

            const syncCheckedState = () => {
                div.classList.toggle('is-checked', Boolean(input.checked));
                mark.textContent = input.checked ? '✓' : '';
            };
            syncCheckedState();
            input.addEventListener('change', syncCheckedState);
            const toggleModule = () => {
                input.checked = !input.checked;
                syncCheckedState();
            };
            div.addEventListener('click', (evt) => {
                if (evt.target === label) return;
                toggleModule();
            });
            label.addEventListener('click', (evt) => {
                evt.preventDefault();
                evt.stopPropagation();
                toggleModule();
            });

            div.appendChild(input);
            div.appendChild(label);
            div.appendChild(mark);
            container.appendChild(div);
        });

        const renderSecondaryRoleChecks = () => {
            secondaryContainer.innerHTML = '';

            ROLE_OPTIONS.forEach((item) => {
                const roleId = item.id;
                const selected = _secondaryRolesDraft.includes(roleId);
                const button = document.createElement('button');
                button.type = 'button';
                button.className = `role-square-btn ${selected ? 'is-selected' : ''}`;
                button.dataset.role = roleId;
                button.innerHTML = `
                        <span class="role-square-label">${item.label}</span>
                        <span class="role-square-mark">${selected ? '✓' : ''}</span>
                    `;
                button.onclick = () => {
                    if (_secondaryRolesDraft.includes(roleId)) {
                        _secondaryRolesDraft = _secondaryRolesDraft.filter((r) => r !== roleId);
                    } else {
                        _secondaryRolesDraft.push(roleId);
                    }
                    renderSecondaryRoleChecks();
                };
                secondaryContainer.appendChild(button);
            });
        };

        renderSecondaryRoleChecks();

        modal.classList.add('is-open');
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal() {
        const modal = document.getElementById('modalUser');
        if (!modal) return;
        modal.classList.remove('is-open');
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }

    async function saveUser(e) {
        e.preventDefault();

        const form = document.getElementById('formUser');
        const mode = form.dataset.mode;

        const username = String(document.getElementById('inpUsername').value || '').trim();
        const password = String(document.getElementById('inpPassword').value || '');
        const isActive = Boolean(document.getElementById('chkActive').checked);

        const allowedModules = [];
        const checks = document.getElementById('containerModules').querySelectorAll('input[type="checkbox"]');
        checks.forEach((check) => {
            if (check.checked) allowedModules.push(check.value);
        });

        // Mapear roles: el primero es 'role', el resto son 'secondary_roles'
        const allRoles = [..._secondaryRolesDraft];
        if (allRoles.length === 0) {
            alert('Debe seleccionar al menos un rol.');
            return;
        }

        const role = allRoles[0];
        const secondaryRoles = allRoles.slice(1);

        if (!username) {
            alert('El nombre de usuario es obligatorio');
            return;
        }

        try {
            if (mode === 'create') {
                if (!password) {
                    alert('Contrasena requerida para nuevo usuario');
                    return;
                }
                await window.fetchApi('/api/admin/users', {
                    method: 'POST',
                    body: { username, password, role, secondary_roles: secondaryRoles, allowed_modules: allowedModules }
                });
            } else {
                const body = { role, secondary_roles: secondaryRoles, is_active: isActive, allowed_modules: allowedModules };
                if (password) body.password = password;

                await window.fetchApi(`/api/admin/users/${encodeURIComponent(username)}`, {
                    method: 'PATCH',
                    body,
                });
            }

            closeModal();
            load();
            if (window.showToast) window.showToast('Usuario guardado correctamente', 'success');
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    async function deleteUser(username) {
        if (!confirm(`Estas SEGURO de eliminar a ${username}? Esta accion no se puede deshacer.`)) return;

        try {
            await window.fetchApi(`/api/admin/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
            load();
            if (window.showToast) window.showToast('Usuario eliminado', 'success');
        } catch (err) {
            alert(`Error: ${err.message}`);
        }
    }

    // Wire up role perms modal buttons once DOM is ready
    document.addEventListener('DOMContentLoaded', () => {
        const closeBtn = document.getElementById('btnCloseRolePermsModal');
        const cancelBtn = document.getElementById('btnCancelRolePerms');
        const saveBtn = document.getElementById('btnSaveRolePerms');
        const modal = document.getElementById('modalRolePerms');
        if (closeBtn) closeBtn.addEventListener('click', closeRolePermsModal);
        if (cancelBtn) cancelBtn.addEventListener('click', closeRolePermsModal);
        if (saveBtn) saveBtn.addEventListener('click', saveRolePerms);
        if (modal) {
            modal.addEventListener('click', (evt) => {
                if (evt.target === modal) closeRolePermsModal();
            });
        }
    });

    return {
        load,
        openModal,
        closeModal,
        saveUser,
        deleteUser,
        openRolePermsModal,
        closeRolePermsModal,
        saveRolePerms,
    };
})();

window.UsersUI = UsersUI;
