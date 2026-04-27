(() => {
    const SEDES = [
        {
            id: 'la-pintana',
            nombre: 'La Pintana',
            rolEncargado: 'encargado_la_pintana',
            region: 'Región Metropolitana',
            responsable: 'Coordinación territorial',
            descripcion: 'Seguimiento operativo de talleres y compromisos comunitarios.',
            icono: 'fa-school',
            color: '#4facfe',
            aliases: ['la-pintana', 'lapintana', 'pintana', 'sede-la-pintana', 'metropolitana', 'rm', 'santiago'],
        },
        {
            id: 'maipu',
            nombre: 'Maipú',
            rolEncargado: 'encargado_maipu',
            region: 'Región Metropolitana',
            responsable: 'Encargada de sede',
            descripcion: 'Planificación académica y coordinación de actividades semanales.',
            icono: 'fa-chalkboard-user',
            color: '#61d1a7',
            aliases: ['maipu', 'sede-maipu'],
        },
        {
            id: 'llay-llay',
            nombre: 'Llay-Llay',
            rolEncargado: 'encargado_llay_llay',
            region: 'Región de Valparaíso',
            responsable: 'Coordinación local',
            descripcion: 'Cobertura territorial, agenda de terreno y soporte formativo.',
            icono: 'fa-route',
            color: '#9f7aea',
            aliases: ['llay-llay', 'llayllay', 'sede-llay-llay'],
        },
        {
            id: 'huechuraba',
            nombre: 'Huechuraba',
            rolEncargado: 'encargado_huechuraba',
            region: 'Región Metropolitana',
            responsable: 'Jefatura operativa',
            descripcion: 'Control de reportes, planificación y apoyo transversal.',
            icono: 'fa-building',
            color: '#f59e0b',
            aliases: ['huechuraba', 'sede-huechuraba'],
        },
        {
            id: 'renca',
            nombre: 'Renca',
            rolEncargado: 'encargado_renca',
            region: 'Región Metropolitana',
            responsable: 'Encargada de inventario',
            descripcion: 'Gestión de stock crítico y reposición de insumos clave.',
            icono: 'fa-boxes-stacked',
            color: '#14b8a6',
            aliases: ['renca', 'sede-renca'],
        },
        {
            id: 'lo-espejo',
            nombre: 'Lo Espejo',
            rolEncargado: 'encargado_lo_espejo',
            region: 'Región Metropolitana',
            responsable: 'Coordinador académico',
            descripcion: 'Ejecución de calendario de clases y hitos de comunidad.',
            icono: 'fa-calendar-check',
            color: '#ef5da8',
            aliases: ['lo-espejo', 'loespejo', 'sede-lo-espejo'],
        },
        {
            id: 'cerro-navia',
            nombre: 'Cerro Navia',
            rolEncargado: 'encargado_cerro_navia',
            region: 'Región Metropolitana',
            responsable: 'Encargada territorial',
            descripcion: 'Soporte de terreno, monitoreo de tareas y continuidad operativa.',
            icono: 'fa-people-group',
            color: '#60a5fa',
            aliases: ['cerro-navia', 'cerronavia', 'sede-cerro-navia'],
        },
    ];

    const CURSOS = [
        {
            id: 'prekinder-kinder',
            label: 'Prekinder y Kinder',
            aliases: ['prekinder-kinder', 'prekinder-y-kinder', 'prekinder', 'kinder', 'pre-kinder'],
        },
        {
            id: '1ro-2do-basico',
            label: '1ro y 2do básico',
            aliases: ['1ro-2do-basico', '1ro-y-2do-basico', '1ro-y-2do', '1ro-2do', '1-y-2', '1ro', '2do'],
        },
        {
            id: '3ro-4to-basico',
            label: '3ro y 4to básico',
            aliases: ['3ro-4to-basico', '3ro-y-4to-basico', '3ro-y-4to', '3ro-4to', '3-y-4', '3ro', '4to'],
        },
    ];

    const DEFAULT_CURSO_IDS = CURSOS.map((curso) => curso.id);

    const ACTIVIDADES_NO_CURSO = new Set([
        'viernes-comunidad',
        'viernes-de-comunidad',
        'comunidad',
        'hitos-celebraciones',
        'hitos-y-celebraciones',
        'celebraciones',
        'hitos',
        'rutina',
    ]);

    const FALLBACK_ROLE_LABELS = {
        monitora: 'Monitora Fundación',
        ejecutiva: 'Ejecutiva Fundación',
        fundacion: 'Fundación',
        encargado_la_pintana: 'Encargado La Pintana',
        encargado_maipu: 'Encargado Maipú',
        encargado_llay_llay: 'Encargado Llay-Llay',
        encargado_huechuraba: 'Encargado Huechuraba',
        encargado_renca: 'Encargado Renca',
        encargado_lo_espejo: 'Encargado Lo Espejo',
        encargado_cerro_navia: 'Encargado Cerro Navia',
    };

    const FALLBACK_FUNDACION_ROLES = Object.keys(FALLBACK_ROLE_LABELS);

    const INVENTARIO_BASE = {
        'la-pintana': [
            { item: 'Notebook terreno', categoria: 'Tecnología', stock: 5, min: 3, responsable: 'María R.' },
            { item: 'Proyector móvil', categoria: 'Equipamiento', stock: 2, min: 2, responsable: 'Carlos L.' },
            { item: 'Kit primeros auxilios', categoria: 'Seguridad', stock: 8, min: 4, responsable: 'Paula C.' },
            { item: 'Sillas plegables', categoria: 'Mobiliario', stock: 30, min: 15, responsable: 'Equipo sede' },
            { item: 'Insumos papelería', categoria: 'Insumos', stock: 12, min: 15, responsable: 'María R.' },
        ],
        maipu: [
            { item: 'Tablets educativas', categoria: 'Tecnología', stock: 9, min: 6, responsable: 'Jorge V.' },
            { item: 'Router 4G', categoria: 'Conectividad', stock: 2, min: 3, responsable: 'Jorge V.' },
            { item: 'Kits didácticos', categoria: 'Material pedagógico', stock: 14, min: 10, responsable: 'Andrea M.' },
            { item: 'Micrófonos inalámbricos', categoria: 'Audio', stock: 3, min: 2, responsable: 'Andrea M.' },
            { item: 'Cargadores universales', categoria: 'Tecnología', stock: 4, min: 5, responsable: 'Soporte TI' },
        ],
        'llay-llay': [
            { item: 'Pantalla portátil', categoria: 'Equipamiento', stock: 3, min: 2, responsable: 'Nicolás A.' },
            { item: 'Set cámaras web', categoria: 'Tecnología', stock: 6, min: 4, responsable: 'Nicolás A.' },
            { item: 'Archivadores', categoria: 'Insumos', stock: 21, min: 10, responsable: 'Rocío P.' },
            { item: 'Equipo audio sala', categoria: 'Audio', stock: 1, min: 1, responsable: 'Rocío P.' },
            { item: 'Sillas ergonométricas', categoria: 'Mobiliario', stock: 6, min: 4, responsable: 'Operaciones' },
        ],
        huechuraba: [
            { item: 'Servidores rack', categoria: 'Infraestructura', stock: 2, min: 1, responsable: 'TI Central' },
            { item: 'Licencias software', categoria: 'Digital', stock: 25, min: 20, responsable: 'TI Central' },
            { item: 'Maletas de terreno', categoria: 'Logística', stock: 7, min: 5, responsable: 'Operaciones' },
            { item: 'Puntos de red', categoria: 'Conectividad', stock: 10, min: 8, responsable: 'TI Central' },
            { item: 'Kits audiovisuales', categoria: 'Equipamiento', stock: 2, min: 3, responsable: 'Comunicaciones' },
        ],
        renca: [
            { item: 'Impresoras térmicas', categoria: 'Tecnología', stock: 4, min: 3, responsable: 'Marta C.' },
            { item: 'Etiquetas inventario', categoria: 'Insumos', stock: 40, min: 20, responsable: 'Marta C.' },
            { item: 'Lectores código QR', categoria: 'Tecnología', stock: 2, min: 2, responsable: 'Soporte Bodega' },
            { item: 'Mesas plegables', categoria: 'Mobiliario', stock: 9, min: 6, responsable: 'Soporte Bodega' },
            { item: 'Linternas recargables', categoria: 'Seguridad', stock: 3, min: 4, responsable: 'Equipo terreno' },
        ],
        'lo-espejo': [
            { item: 'Vehículo de apoyo (kits)', categoria: 'Logística', stock: 3, min: 2, responsable: 'Javier F.' },
            { item: 'Radios portátiles', categoria: 'Conectividad', stock: 5, min: 4, responsable: 'Javier F.' },
            { item: 'Uniformes', categoria: 'Vestuario', stock: 18, min: 10, responsable: 'Daniela H.' },
            { item: 'Botiquín ampliado', categoria: 'Seguridad', stock: 2, min: 3, responsable: 'Daniela H.' },
            { item: 'Cargadores móviles', categoria: 'Tecnología', stock: 8, min: 5, responsable: 'Equipo sede' },
        ],
        'cerro-navia': [
            { item: 'Kits lluvia', categoria: 'Vestuario', stock: 15, min: 8, responsable: 'Claudia S.' },
            { item: 'GPS terreno', categoria: 'Tecnología', stock: 4, min: 3, responsable: 'Claudia S.' },
            { item: 'Tablets registro', categoria: 'Tecnología', stock: 6, min: 5, responsable: 'Fernando T.' },
            { item: 'Chalecos reflectantes', categoria: 'Seguridad', stock: 11, min: 6, responsable: 'Fernando T.' },
            { item: 'Combos de herramientas', categoria: 'Operación', stock: 2, min: 3, responsable: 'Equipo operativo' },
        ],
    };

    const TASK_STATE_LABEL = {
        pendiente: 'Pendiente',
        en_progreso: 'En progreso',
        completada: 'Completada',
    };

    const MONTHS = [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
    ];

    const WEEK_DAYS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

    const state = {
        session: {
            user: '',
            role: '',
            roles: [],
            fundacionScope: {
                is_global: true,
                sedes: [],
                cursos: [],
            },
        },
        selectedSedeId: null,
        expandedSedeId: null,
        selectedCursoId: 'all',
        tasksBySede: {},
        inventoryBySede: INVENTARIO_BASE,
        calendarView: 'mes',
        calendarDate: new Date(),
        inventorySearch: '',
        usersAdmin: {
            allUsers: [],
            fundacionUsers: [],
            roleScopes: [],
            roleLabels: { ...FALLBACK_ROLE_LABELS },
            fundacionRoles: [...FALLBACK_FUNDACION_ROLES],
            hasAccess: true,
            editingUsername: '',
        },
    };

    const els = {
        status: document.getElementById('fund-status'),
        selector: document.getElementById('fund-sede-selector'),
        workspace: document.getElementById('fund-sede-workspace'),
        sedesGrid: document.getElementById('fund-sedes-grid'),
        sedeTitle: document.getElementById('fund-sede-title'),
        sedeSubtitle: document.getElementById('fund-sede-subtitle'),
        backBtn: document.getElementById('fund-back-to-sedes'),
        tabButtons: Array.from(document.querySelectorAll('.fund-tab')),
        tabPanels: {
            planificacion: document.getElementById('fund-tab-planificacion'),
            inventario: document.getElementById('fund-tab-inventario'),
            reportes: document.getElementById('fund-tab-reportes'),
        },
        calPrev: document.getElementById('fund-cal-prev'),
        calNext: document.getElementById('fund-cal-next'),
        calToday: document.getElementById('fund-cal-today'),
        calRange: document.getElementById('fund-cal-range'),
        calContainer: document.getElementById('fund-calendar-container'),
        calViewSwitch: Array.from(document.querySelectorAll('#fund-calendar-view-switch button')),
        nextTasksList: document.getElementById('fund-next-tasks-list'),
        cursoSelect: document.getElementById('fund-curso-select'),
        scopeHint: document.getElementById('fund-scope-hint'),
        inventoryBody: document.getElementById('fund-inventory-body'),
        inventorySearch: document.getElementById('fund-inventory-search'),
        kpiItems: document.getElementById('fund-kpi-items'),
        kpiCritical: document.getElementById('fund-kpi-critical'),
        kpiUnits: document.getElementById('fund-kpi-units'),
        reportActive: document.getElementById('fund-report-active'),
        reportCompleted: document.getElementById('fund-report-completed'),
        reportRate: document.getElementById('fund-report-rate'),
        reportTaskSummary: document.getElementById('fund-report-task-summary'),
        reportCriticalList: document.getElementById('fund-report-critical-list'),
        reportAgendaList: document.getElementById('fund-report-agenda-list'),
        usersAdmin: document.getElementById('fund-users-admin'),
        usersAdminStatus: document.getElementById('fund-users-admin-status'),
        usersBody: document.getElementById('fund-users-body'),
        usersRefreshBtn: document.getElementById('fund-users-refresh'),
        userNewBtn: document.getElementById('fund-user-new'),
        userModal: document.getElementById('fund-user-modal'),
        userModalTitle: document.getElementById('fund-user-modal-title'),
        userModalClose: document.getElementById('fund-user-modal-close'),
        userForm: document.getElementById('fund-user-form'),
        userUsername: document.getElementById('fund-user-username'),
        userPassword: document.getElementById('fund-user-password'),
        userActive: document.getElementById('fund-user-active'),
        userRoleOptions: document.getElementById('fund-user-role-options'),
        userCancel: document.getElementById('fund-user-cancel'),
    };

    document.addEventListener('DOMContentLoaded', init);

    async function init() {
        await loadSessionScope();
        renderSedeSelector();
        bindEvents();
        await bootstrapUsersAdmin();

        try {
            const apiTasks = await fetchTasksFromApi();
            hydrateTasksBySede(apiTasks);
            renderSedeSelector();
            setStatus('Fundación en línea: planificación e inventario por sede habilitados.');
        } catch (err) {
            hydrateTasksBySede([]);
            renderSedeSelector();
            const msg = err?.message || 'sin detalle';
            setStatus(`Fundación operativa con datos de demostración (${msg}).`);
        }

        if (state.selectedSedeId) {
            refreshSelectedSedeHeader();
            refreshWorkspace();
        }
    }

    function bindEvents() {
        if (els.backBtn) {
            els.backBtn.addEventListener('click', backToSedeSelector);
        }

        els.tabButtons.forEach((btn) => {
            btn.addEventListener('click', () => activateTab(btn.dataset.tabTarget || 'planificacion'));
        });

        if (els.calPrev) {
            els.calPrev.addEventListener('click', () => {
                if (state.calendarView === 'mes') {
                    state.calendarDate = addMonths(state.calendarDate, -1);
                } else if (state.calendarView === 'semana') {
                    state.calendarDate = addDays(state.calendarDate, -7);
                } else {
                    state.calendarDate = addDays(state.calendarDate, -1);
                }
                renderCalendar();
            });
        }

        if (els.calNext) {
            els.calNext.addEventListener('click', () => {
                if (state.calendarView === 'mes') {
                    state.calendarDate = addMonths(state.calendarDate, 1);
                } else if (state.calendarView === 'semana') {
                    state.calendarDate = addDays(state.calendarDate, 7);
                } else {
                    state.calendarDate = addDays(state.calendarDate, 1);
                }
                renderCalendar();
            });
        }

        if (els.calToday) {
            els.calToday.addEventListener('click', () => {
                state.calendarDate = new Date();
                renderCalendar();
            });
        }

        els.calViewSwitch.forEach((btn) => {
            btn.addEventListener('click', () => {
                state.calendarView = btn.dataset.calendarView || 'mes';
                els.calViewSwitch.forEach((b) => b.classList.toggle('active', b === btn));
                renderCalendar();
            });
        });

        if (els.inventorySearch) {
            els.inventorySearch.addEventListener('input', () => {
                state.inventorySearch = (els.inventorySearch.value || '').trim().toLowerCase();
                renderInventory();
                renderReports();
            });
        }

        if (els.cursoSelect) {
            els.cursoSelect.addEventListener('change', () => {
                state.selectedCursoId = els.cursoSelect.value || 'all';
                refreshWorkspace();
            });
        }

        if (els.usersRefreshBtn) {
            els.usersRefreshBtn.addEventListener('click', () => {
                refreshUsersAdminData(true);
            });
        }

        if (els.userNewBtn) {
            els.userNewBtn.addEventListener('click', () => {
                openUserModalForCreate();
            });
        }

        if (els.usersBody) {
            els.usersBody.addEventListener('click', (event) => {
                const btn = event.target.closest('button[data-action]');
                if (!btn) return;

                const action = btn.dataset.action || '';
                const username = btn.dataset.username || '';
                if (!username) return;

                if (action === 'edit') {
                    openUserModalForEdit(username);
                    return;
                }

                if (action === 'toggle') {
                    handleToggleUserActive(username);
                    return;
                }

                if (action === 'delete') {
                    handleDeleteUser(username);
                }
            });
        }

        if (els.userModalClose) {
            els.userModalClose.addEventListener('click', closeUserModal);
        }

        if (els.userCancel) {
            els.userCancel.addEventListener('click', closeUserModal);
        }

        if (els.userModal) {
            els.userModal.addEventListener('click', (event) => {
                if (event.target === els.userModal) {
                    closeUserModal();
                }
            });
        }

        if (els.userForm) {
            els.userForm.addEventListener('submit', handleUserFormSubmit);
        }
    }

    function renderSedeSelector() {
        if (!els.sedesGrid) return;

        const visibleSedes = getVisibleSedes();

        if (!visibleSedes.length) {
            els.sedesGrid.innerHTML = '<p style="color:var(--text-soft);">No tienes sedes asignadas para Fundación.</p>';
            if (els.workspace) {
                els.workspace.classList.add('hidden');
            }
            if (els.selector) {
                els.selector.classList.remove('hidden');
            }
            return;
        }

        const cards = visibleSedes.map((sede) => {
            const isExpanded = state.expandedSedeId === sede.id;
            const encargado = getSedeEncargadoDisplay(sede);
            const courseIds = getCourseIdsForSede(sede.id);
            const cursoButtons = courseIds.length
                ? courseIds.map((cursoId) => {
                    return `
                        <button class="fund-curso-chip" type="button" data-sede-id="${escapeHtml(sede.id)}" data-curso-id="${escapeHtml(cursoId)}">
                            ${escapeHtml(getCursoLabel(cursoId, cursoId))}
                        </button>
                    `;
                }).join('')
                : '<span class="fund-curso-empty">Sin cursos disponibles.</span>';

            return `
                <article class="fund-sede-item">
                    <button class="fund-sede-card ${isExpanded ? 'is-open' : ''}" type="button" data-sede-id="${escapeHtml(sede.id)}" aria-expanded="${isExpanded ? 'true' : 'false'}">
                        <h3>${escapeHtml(sede.nombre)}</h3>
                        <p class="fund-sede-meta">${escapeHtml(encargado)}</p>
                    </button>

                    <div class="fund-sede-accordion ${isExpanded ? 'open' : ''}">
                        <p class="fund-sede-accordion-title">Selecciona un curso</p>
                        <div class="fund-sede-cursos">
                            ${cursoButtons}
                        </div>
                    </div>
                </article>
            `;
        }).join('');

        els.sedesGrid.innerHTML = cards;

        els.sedesGrid.querySelectorAll('.fund-sede-card').forEach((btn) => {
            btn.addEventListener('click', () => {
                const sedeId = btn.dataset.sedeId;
                if (!sedeId) return;
                toggleSedeAccordion(sedeId);
            });
        });

        els.sedesGrid.querySelectorAll('.fund-curso-chip').forEach((btn) => {
            btn.addEventListener('click', (event) => {
                event.stopPropagation();
                const sedeId = btn.dataset.sedeId;
                const cursoId = btn.dataset.cursoId;
                if (!sedeId || !cursoId) return;
                selectSede(sedeId, { cursoId });
            });
        });
    }

    function toggleSedeAccordion(sedeId) {
        if (!canAccessSede(sedeId)) {
            setStatus('No tienes permisos para acceder a esta sede.');
            return;
        }

        state.expandedSedeId = state.expandedSedeId === sedeId ? null : sedeId;
        renderSedeSelector();
    }

    function selectSede(sedeId, options = {}) {
        if (!canAccessSede(sedeId)) {
            setStatus('No tienes permisos para acceder a esta sede.');
            return;
        }

        const sede = getSelectedSedeById(sedeId);
        if (!sede) return;

        const requestedCursoId = options?.cursoId || 'all';

        state.selectedSedeId = sedeId;
        state.expandedSedeId = null;
        state.selectedCursoId = requestedCursoId;
        state.calendarDate = new Date();
        state.calendarView = 'mes';
        state.inventorySearch = '';

        if (els.inventorySearch) {
            els.inventorySearch.value = '';
        }

        refreshSelectedSedeHeader();

        if (els.selector) {
            els.selector.classList.add('hidden');
        }

        if (els.workspace) {
            els.workspace.classList.remove('hidden');
        }

        populateCursoOptions();
        renderScopeHint();

        els.calViewSwitch.forEach((btn) => {
            btn.classList.toggle('active', (btn.dataset.calendarView || '') === 'mes');
        });

        activateTab('planificacion');
        renderCalendar();
        renderInventory();
        renderReports();
    }

    function backToSedeSelector() {
        state.selectedSedeId = null;
        state.expandedSedeId = null;
        state.selectedCursoId = 'all';

        if (els.workspace) {
            els.workspace.classList.add('hidden');
        }

        if (els.selector) {
            els.selector.classList.remove('hidden');
        }

        renderSedeSelector();
    }

    function refreshSelectedSedeHeader() {
        if (!state.selectedSedeId) return;
        const sede = getSelectedSedeById(state.selectedSedeId);
        if (!sede) return;

        const encargado = getSedeEncargadoDisplay(sede);

        if (els.sedeTitle) {
            els.sedeTitle.textContent = sede.nombre;
        }

        if (els.sedeSubtitle) {
            els.sedeSubtitle.textContent = `${sede.region} · Encargado: ${encargado}`;
        }
    }

    async function bootstrapUsersAdmin() {
        if (!els.usersAdmin || !els.usersBody) return;

        renderUserRoleOptions([]);
        setUsersAdminStatus('Cargando usuarios de Fundación...');
        await refreshUsersAdminData(false);
    }

    async function refreshUsersAdminData(showSuccessToast = false) {
        if (!els.usersBody) return;

        if (!window.fetchApi) {
            state.usersAdmin.hasAccess = false;
            state.usersAdmin.allUsers = [];
            state.usersAdmin.fundacionUsers = [];
            renderUsersAdmin();
            setUsersAdminStatus('No se pudo inicializar el cliente API para usuarios.');
            renderSedeSelector();
            refreshSelectedSedeHeader();
            return;
        }

        setUsersAdminLoading(true);
        setUsersAdminStatus('Cargando usuarios de Fundación...');

        try {
            const [usersRaw, roleScopesRaw] = await Promise.all([
                window.fetchApi('/api/admin/users'),
                window.fetchApi('/api/config/role-scopes').catch(() => null),
            ]);

            applyRoleScopes(Array.isArray(roleScopesRaw?.items) ? roleScopesRaw.items : []);

            const allUsers = Array.isArray(usersRaw?.items)
                ? usersRaw.items
                    .map((item) => normalizeUserForAdmin(item))
                    .filter((item) => Boolean(item.username))
                : [];

            state.usersAdmin.hasAccess = true;
            state.usersAdmin.allUsers = allUsers;
            state.usersAdmin.fundacionUsers = getFundacionUsers(allUsers);

            renderUsersAdmin();
            renderSedeSelector();
            refreshSelectedSedeHeader();
            setUsersAdminStatus(`Usuarios Fundación cargados: ${state.usersAdmin.fundacionUsers.length}.`);

            if (showSuccessToast && typeof window.showToast === 'function') {
                window.showToast('Usuarios Fundación actualizados.', 'success');
            }
        } catch (error) {
            if (isForbiddenError(error)) {
                state.usersAdmin.hasAccess = false;
                state.usersAdmin.allUsers = [];
                state.usersAdmin.fundacionUsers = [];
                renderUsersAdmin();
                renderSedeSelector();
                refreshSelectedSedeHeader();
                setUsersAdminStatus('Sin permiso admin.settings para gestionar usuarios.');
                return;
            }

            const detail = error?.message || 'sin detalle';
            setUsersAdminStatus(`Error cargando usuarios: ${detail}`);
            renderUsersAdmin();
            if (typeof window.showToast === 'function') {
                window.showToast(`No se pudo cargar usuarios: ${detail}`, 'warning');
            }
        } finally {
            setUsersAdminLoading(false);
        }
    }

    function applyRoleScopes(roleScopeItems) {
        const items = Array.isArray(roleScopeItems) ? roleScopeItems : [];
        const labels = { ...FALLBACK_ROLE_LABELS };

        items.forEach((item) => {
            const role = normalizeRoleValue(item?.role);
            if (!role) return;
            const label = String(item?.label || '').trim();
            if (label) labels[role] = label;
        });

        state.usersAdmin.roleScopes = items;
        state.usersAdmin.roleLabels = labels;

        const detectedFundacionRoles = extractFundacionRoles(items);
        state.usersAdmin.fundacionRoles = detectedFundacionRoles.length
            ? detectedFundacionRoles
            : [...FALLBACK_FUNDACION_ROLES];
    }

    function extractFundacionRoles(roleScopeItems) {
        const out = [];
        const seen = new Set();
        const explicitFundacionRoles = new Set(['monitora', 'ejecutiva', 'fundacion']);

        const pushRole = (rawRole) => {
            const role = normalizeRoleValue(rawRole);
            if (!role || seen.has(role)) return;
            seen.add(role);
            out.push(role);
        };

        roleScopeItems.forEach((item) => {
            const role = normalizeRoleValue(item?.role);
            if (!role) return;

            const permissions = Array.isArray(item?.permissions) ? item.permissions : [];
            const hasFundacionPermission = permissions.some((permission) => {
                const value = String(permission || '').trim().toLowerCase();
                return value.startsWith('fundacion:');
            });

            if (role.startsWith('encargado_') || explicitFundacionRoles.has(role) || hasFundacionPermission) {
                pushRole(role);
            }
        });

        FALLBACK_FUNDACION_ROLES.forEach(pushRole);
        return out;
    }

    function normalizeUserForAdmin(rawUser) {
        const username = String(rawUser?.username || '').trim();
        const role = normalizeRoleValue(rawUser?.role);
        const secondaryRolesRaw = Array.isArray(rawUser?.secondary_roles) ? rawUser.secondary_roles : [];
        const secondaryRoles = [...new Set(secondaryRolesRaw
            .map((value) => normalizeRoleValue(value))
            .filter((value) => Boolean(value) && value !== role))];

        return {
            ...rawUser,
            username,
            role,
            secondary_roles: secondaryRoles,
            is_active: Boolean(rawUser?.is_active),
        };
    }

    function getRoleLabel(role) {
        const normalized = normalizeRoleValue(role);
        if (!normalized) return 'Sin rol';
        return state.usersAdmin.roleLabels[normalized]
            || FALLBACK_ROLE_LABELS[normalized]
            || normalized.replace(/_/g, ' ');
    }

    function getUserRoleIds(user) {
        const roles = [];
        const push = (rawRole) => {
            const role = normalizeRoleValue(rawRole);
            if (!role || roles.includes(role)) return;
            roles.push(role);
        };

        push(user?.role);
        const secondary = Array.isArray(user?.secondary_roles) ? user.secondary_roles : [];
        secondary.forEach(push);
        return roles;
    }

    function isFundacionRole(role) {
        const normalized = normalizeRoleValue(role);
        if (!normalized) return false;
        if (normalized.startsWith('encargado_')) return true;
        return (state.usersAdmin.fundacionRoles || []).some((fundRole) => normalizeRoleValue(fundRole) === normalized);
    }

    function getFundacionUsers(users) {
        return (Array.isArray(users) ? users : [])
            .filter((user) => getUserRoleIds(user).some((role) => isFundacionRole(role)))
            .sort((a, b) => String(a.username || '').localeCompare(String(b.username || ''), 'es'));
    }

    function setUsersAdminStatus(message) {
        if (els.usersAdminStatus) {
            els.usersAdminStatus.textContent = message;
        }
    }

    function setUsersAdminLoading(isLoading) {
        const loading = Boolean(isLoading);
        if (els.usersRefreshBtn) els.usersRefreshBtn.disabled = loading;
        if (els.userNewBtn) els.userNewBtn.disabled = loading;
    }

    function renderUsersAdmin() {
        if (!els.usersBody) return;

        if (!state.usersAdmin.hasAccess) {
            els.usersBody.innerHTML = '<tr><td colspan="4">No tienes permisos para administrar usuarios desde Fundación.</td></tr>';
            return;
        }

        const users = state.usersAdmin.fundacionUsers || [];
        if (!users.length) {
            els.usersBody.innerHTML = '<tr><td colspan="4">No hay usuarios de Fundación registrados.</td></tr>';
            return;
        }

        els.usersBody.innerHTML = users.map((user) => {
            const roles = getUserRoleIds(user);
            const rolesHtml = roles.length
                ? `<div class="fund-user-roles">${roles.map((role) => `<span class="fund-user-role-pill">${escapeHtml(getRoleLabel(role))}</span>`).join('')}</div>`
                : '<span style="color:var(--text-soft);">Sin roles</span>';

            const isActive = Boolean(user.is_active);
            const statusLabel = isActive ? 'Activo' : 'Inactivo';
            const toggleLabel = isActive ? 'Desactivar' : 'Activar';
            const normalizedSessionUser = normalizeUsernameValue(state.session?.user || '');
            const normalizedRowUser = normalizeUsernameValue(user.username);
            const canDelete = normalizedSessionUser && normalizedSessionUser !== normalizedRowUser;

            return `
                <tr>
                    <td>${escapeHtml(user.username)}</td>
                    <td>${rolesHtml}</td>
                    <td>${statusLabel}</td>
                    <td>
                        <button class="fund-user-action" type="button" data-action="edit" data-username="${escapeHtml(user.username)}">Editar</button>
                        <button class="fund-user-action" type="button" data-action="toggle" data-username="${escapeHtml(user.username)}">${toggleLabel}</button>
                        ${canDelete ? `<button class="fund-user-action delete" type="button" data-action="delete" data-username="${escapeHtml(user.username)}">Eliminar</button>` : ''}
                    </td>
                </tr>
            `;
        }).join('');
    }

    function renderUserRoleOptions(selectedRoles = []) {
        if (!els.userRoleOptions) return;

        const selectedSet = new Set((Array.isArray(selectedRoles) ? selectedRoles : [])
            .map((role) => normalizeRoleValue(role))
            .filter(Boolean));

        const roles = (state.usersAdmin.fundacionRoles && state.usersAdmin.fundacionRoles.length)
            ? state.usersAdmin.fundacionRoles
            : [...FALLBACK_FUNDACION_ROLES];

        els.userRoleOptions.innerHTML = roles.map((role) => {
            const normalized = normalizeRoleValue(role);
            return `
                <label class="fund-user-role-option">
                    <input type="checkbox" value="${escapeHtml(normalized)}" ${selectedSet.has(normalized) ? 'checked' : ''}>
                    <span>${escapeHtml(getRoleLabel(normalized))}</span>
                </label>
            `;
        }).join('');
    }

    function openUserModalForCreate() {
        if (!state.usersAdmin.hasAccess) {
            setUsersAdminStatus('No tienes permisos para crear usuarios.');
            return;
        }

        state.usersAdmin.editingUsername = '';

        if (els.userModalTitle) {
            els.userModalTitle.textContent = 'Nuevo usuario Fundación';
        }
        if (els.userUsername) {
            els.userUsername.value = '';
            els.userUsername.disabled = false;
        }
        if (els.userPassword) {
            els.userPassword.value = '';
            els.userPassword.placeholder = 'Contraseña obligatoria';
        }
        if (els.userActive) {
            els.userActive.checked = true;
        }

        renderUserRoleOptions(['fundacion']);

        if (els.userModal) {
            els.userModal.classList.remove('hidden');
            els.userModal.setAttribute('aria-hidden', 'false');
        }
    }

    function openUserModalForEdit(username) {
        if (!state.usersAdmin.hasAccess) {
            setUsersAdminStatus('No tienes permisos para editar usuarios.');
            return;
        }

        const normalizedTarget = normalizeUsernameValue(username);
        const user = state.usersAdmin.allUsers.find((item) => normalizeUsernameValue(item.username) === normalizedTarget);
        if (!user) {
            setUsersAdminStatus('No se encontró el usuario seleccionado.');
            return;
        }

        state.usersAdmin.editingUsername = user.username;

        if (els.userModalTitle) {
            els.userModalTitle.textContent = `Editar usuario: ${user.username}`;
        }
        if (els.userUsername) {
            els.userUsername.value = user.username;
            els.userUsername.disabled = true;
        }
        if (els.userPassword) {
            els.userPassword.value = '';
            els.userPassword.placeholder = 'Dejar en blanco para mantener';
        }
        if (els.userActive) {
            els.userActive.checked = Boolean(user.is_active);
        }

        const selectedFundRoles = getUserRoleIds(user).filter((role) => isFundacionRole(role));
        renderUserRoleOptions(selectedFundRoles);

        if (els.userModal) {
            els.userModal.classList.remove('hidden');
            els.userModal.setAttribute('aria-hidden', 'false');
        }
    }

    function closeUserModal() {
        if (els.userModal) {
            els.userModal.classList.add('hidden');
            els.userModal.setAttribute('aria-hidden', 'true');
        }
        if (els.userForm) {
            els.userForm.reset();
        }
        state.usersAdmin.editingUsername = '';
    }

    async function handleUserFormSubmit(event) {
        event.preventDefault();

        if (!state.usersAdmin.hasAccess) {
            setUsersAdminStatus('No tienes permisos para guardar usuarios.');
            return;
        }

        const isEdit = Boolean(state.usersAdmin.editingUsername);
        const username = sanitizeUsernameInput(els.userUsername?.value || '');
        const password = String(els.userPassword?.value || '');
        const selectedFundRoles = getSelectedRolesFromModal();

        const existingUser = isEdit
            ? state.usersAdmin.allUsers.find((item) => normalizeUsernameValue(item.username) === normalizeUsernameValue(state.usersAdmin.editingUsername))
            : null;

        const rolePayload = buildRolePayload(existingUser, selectedFundRoles);
        if (!rolePayload) {
            alert('Debes seleccionar al menos un rol de Fundación.');
            return;
        }

        if (!isEdit && !username) {
            alert('Debes ingresar el nombre de usuario.');
            return;
        }

        if (!isEdit && !password.trim()) {
            alert('Debes ingresar la contraseña para crear el usuario.');
            return;
        }

        setUsersAdminLoading(true);

        try {
            if (isEdit) {
                if (!existingUser) {
                    throw new Error('No se encontró el usuario a editar.');
                }

                const body = {
                    role: rolePayload.role,
                    secondary_roles: rolePayload.secondary_roles,
                    is_active: Boolean(els.userActive?.checked),
                };
                if (password.trim()) {
                    body.password = password;
                }

                await window.fetchApi(`/api/admin/users/${encodeURIComponent(existingUser.username)}`, {
                    method: 'PATCH',
                    body,
                });
            } else {
                await window.fetchApi('/api/admin/users', {
                    method: 'POST',
                    body: {
                        username,
                        password,
                        role: rolePayload.role,
                        secondary_roles: rolePayload.secondary_roles,
                        allowed_modules: ['dashboard', 'fundacion'],
                        fundacion_scope: {
                            is_global: true,
                            sedes: [],
                            cursos: [],
                        },
                    },
                });
            }

            closeUserModal();
            await refreshUsersAdminData(false);

            if (typeof window.showToast === 'function') {
                window.showToast('Usuario Fundación guardado.', 'success');
            }
        } catch (error) {
            alert(`No se pudo guardar el usuario: ${error?.message || 'sin detalle'}`);
        } finally {
            setUsersAdminLoading(false);
        }
    }

    function getSelectedRolesFromModal() {
        if (!els.userRoleOptions) return [];
        const checks = Array.from(els.userRoleOptions.querySelectorAll('input[type="checkbox"]:checked'));
        return [...new Set(checks
            .map((check) => normalizeRoleValue(check.value))
            .filter(Boolean))];
    }

    function buildRolePayload(existingUser, selectedFundRoles) {
        const selected = [...new Set((Array.isArray(selectedFundRoles) ? selectedFundRoles : [])
            .map((role) => normalizeRoleValue(role))
            .filter(Boolean))];

        if (existingUser) {
            const existingRoles = getUserRoleIds(existingUser);
            const preservedNonFundRoles = existingRoles.filter((role) => !isFundacionRole(role));
            const combined = [...new Set([...selected, ...preservedNonFundRoles])];
            if (!combined.length) return null;

            const preferredPrimary = normalizeRoleValue(existingUser.role);
            const role = combined.includes(preferredPrimary) ? preferredPrimary : combined[0];
            const secondary = combined.filter((item) => item !== role);
            return { role, secondary_roles: secondary };
        }

        if (!selected.length) return null;
        return {
            role: selected[0],
            secondary_roles: selected.slice(1),
        };
    }

    async function handleToggleUserActive(username) {
        const normalized = normalizeUsernameValue(username);
        const user = state.usersAdmin.allUsers.find((item) => normalizeUsernameValue(item.username) === normalized);
        if (!user) return;

        try {
            await window.fetchApi(`/api/admin/users/${encodeURIComponent(user.username)}`, {
                method: 'PATCH',
                body: {
                    is_active: !Boolean(user.is_active),
                },
            });
            await refreshUsersAdminData(false);
            if (typeof window.showToast === 'function') {
                window.showToast(`Usuario ${user.username} actualizado.`, 'success');
            }
        } catch (error) {
            alert(`No se pudo actualizar estado: ${error?.message || 'sin detalle'}`);
        }
    }

    async function handleDeleteUser(username) {
        const normalized = normalizeUsernameValue(username);
        const user = state.usersAdmin.allUsers.find((item) => normalizeUsernameValue(item.username) === normalized);
        if (!user) return;

        const confirmed = window.confirm(`¿Eliminar usuario ${user.username}? Esta acción no se puede deshacer.`);
        if (!confirmed) return;

        try {
            await window.fetchApi(`/api/admin/users/${encodeURIComponent(user.username)}`, {
                method: 'DELETE',
            });
            await refreshUsersAdminData(false);
            if (typeof window.showToast === 'function') {
                window.showToast(`Usuario ${user.username} eliminado.`, 'success');
            }
        } catch (error) {
            alert(`No se pudo eliminar usuario: ${error?.message || 'sin detalle'}`);
        }
    }

    function getSedeEncargadoDisplay(sede) {
        const role = normalizeRoleValue(sede?.rolEncargado);
        if (!role) return 'Encargado: por definir';

        const assignedUsers = (state.usersAdmin.fundacionUsers || [])
            .filter((user) => Boolean(user.is_active) && getUserRoleIds(user).includes(role))
            .sort((a, b) => String(a.username || '').localeCompare(String(b.username || ''), 'es'));

        if (!assignedUsers.length) {
            return `Rol: ${getRoleLabel(role)}`;
        }

        if (assignedUsers.length === 1) {
            return `Encargado: ${assignedUsers[0].username}`;
        }

        return `Encargado: ${assignedUsers[0].username} (+${assignedUsers.length - 1})`;
    }

    function isForbiddenError(error) {
        const message = String(error?.message || '').toLowerCase();
        return message.includes('acceso denegado')
            || message.includes('permisos insuficientes')
            || message.includes('forbidden')
            || message.includes('403');
    }

    function normalizeRoleValue(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim()
            .replace(/[\s-]+/g, '_')
            .replace(/[^a-z0-9_]/g, '_')
            .replace(/_+/g, '_')
            .replace(/^_|_$/g, '');
    }

    function normalizeUsernameValue(value) {
        return String(value || '').trim().toLowerCase();
    }

    function sanitizeUsernameInput(value) {
        return String(value || '').trim();
    }

    function activateTab(targetTab) {
        const validTabs = ['planificacion', 'inventario', 'reportes'];
        const resolved = validTabs.includes(targetTab) ? targetTab : 'planificacion';

        els.tabButtons.forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.tabTarget === resolved);
        });

        Object.entries(els.tabPanels).forEach(([key, panel]) => {
            if (!panel) return;
            panel.classList.toggle('active', key === resolved);
        });

        if (resolved === 'inventario') {
            renderInventory();
        } else if (resolved === 'reportes') {
            renderReports();
        } else {
            renderCalendar();
        }

        renderScopeHint();
    }

    function renderCalendar() {
        if (!state.selectedSedeId || !els.calContainer || !els.calRange) return;

        const tasks = getTasksForSelectedSede();

        if (state.calendarView === 'dia') {
            renderDayCalendar(tasks);
        } else if (state.calendarView === 'semana') {
            renderWeekCalendar(tasks);
        } else {
            renderMonthCalendar(tasks);
        }

        renderUpcomingTasks(tasks);
    }

    function renderMonthCalendar(tasks) {
        const current = state.calendarDate;
        const year = current.getFullYear();
        const month = current.getMonth();

        const firstDay = new Date(year, month, 1);
        const start = startOfWeek(firstDay);
        const today = stripTime(new Date());

        const monthLabel = `${MONTHS[month]} ${year}`;
        els.calRange.textContent = `Vista mensual · ${monthLabel}`;

        const header = `
            <div class="fund-month-head">
                ${WEEK_DAYS.map((d) => `<span>${d}</span>`).join('')}
            </div>
        `;

        const cells = [];
        for (let i = 0; i < 42; i += 1) {
            const date = addDays(start, i);
            const iso = toISODate(date);
            const inMonth = date.getMonth() === month;
            const isToday = sameDate(date, today);
            const tasksOfDay = tasks.filter((t) => sameDate(t.start, date));

            const taskHtml = tasksOfDay.slice(0, 2)
                .map((t) => `<div class="fund-day-task" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</div>`)
                .join('');

            const more = tasksOfDay.length > 2
                ? `<div class="fund-day-task fund-day-task--more">+${tasksOfDay.length - 2} más</div>`
                : '';

            cells.push(`
                <article class="fund-day-cell ${inMonth ? '' : 'out-month'} ${isToday ? 'today' : ''}" data-date="${iso}">
                    <span class="fund-day-number">${date.getDate()}</span>
                    ${taskHtml}${more}
                </article>
            `);
        }

        els.calContainer.innerHTML = `${header}<div class="fund-calendar-grid--month">${cells.join('')}</div>`;
    }

    function renderWeekCalendar(tasks) {
        const today = stripTime(new Date());
        const weekStart = startOfWeek(state.calendarDate);
        const weekEnd = addDays(weekStart, 6);
        els.calRange.textContent = `Vista semanal · ${formatDateShort(weekStart)} al ${formatDateShort(weekEnd)}`;

        const days = [];
        for (let i = 0; i < 7; i += 1) {
            const date = addDays(weekStart, i);
            const dayTasks = tasks.filter((t) => sameDate(t.start, date));

            const items = dayTasks.length
                ? dayTasks.map((task) => {
                    return `
                        <li class="fund-task-item">
                            ${escapeHtml(task.title)}
                            <small>${escapeHtml(task.timeLabel)} · ${escapeHtml(task.estadoLabel)}</small>
                        </li>
                    `;
                }).join('')
                : '<li class="fund-task-item" style="background:rgba(255,255,255,.04);color:var(--text-soft);">Sin tareas</li>';

            days.push(`
                <article class="fund-week-day ${sameDate(date, today) ? 'today' : ''}">
                    <h5>${WEEK_DAYS[date.getDay()]} ${date.getDate()}/${date.getMonth() + 1}</h5>
                    <ul class="fund-task-list">${items}</ul>
                </article>
            `);
        }

        els.calContainer.innerHTML = `<div class="fund-calendar-grid--week">${days.join('')}</div>`;
    }

    function renderDayCalendar(tasks) {
        const current = stripTime(state.calendarDate);
        const dayTasks = tasks
            .filter((t) => sameDate(t.start, current))
            .sort((a, b) => a.start.getTime() - b.start.getTime());

        els.calRange.textContent = `Vista diaria · ${formatDateLong(current)}`;

        const items = dayTasks.length
            ? dayTasks.map((task) => {
                return `
                    <li class="fund-task-item">
                        ${escapeHtml(task.title)}
                        <small>${escapeHtml(task.timeLabel)} · ${escapeHtml(task.estadoLabel)} · ${escapeHtml(task.owner)}</small>
                    </li>
                `;
            }).join('')
            : '<li class="fund-task-item" style="background:rgba(255,255,255,.04);color:var(--text-soft);">No hay tareas para este día.</li>';

        els.calContainer.innerHTML = `
            <section class="fund-day-view">
                <h5>Agenda del día</h5>
                <ul class="fund-task-list">${items}</ul>
            </section>
        `;
    }

    function renderUpcomingTasks(tasks) {
        if (!els.nextTasksList) return;

        const now = new Date();
        const upcoming = tasks
            .filter((t) => t.start.getTime() >= now.getTime())
            .sort((a, b) => a.start.getTime() - b.start.getTime())
            .slice(0, 5);

        if (!upcoming.length) {
            els.nextTasksList.innerHTML = '<li>No hay tareas próximas para esta sede.</li>';
            return;
        }

        els.nextTasksList.innerHTML = upcoming.map((task) => {
            return `<li>${escapeHtml(task.title)} · ${escapeHtml(formatDateLong(task.start))} (${escapeHtml(task.estadoLabel)})</li>`;
        }).join('');
    }

    function renderInventory() {
        if (!state.selectedSedeId || !els.inventoryBody) return;

        const inventory = getInventoryForSelectedSede();
        const filtered = inventory.filter((item) => {
            if (!state.inventorySearch) return true;
            const haystack = `${item.item} ${item.categoria}`.toLowerCase();
            return haystack.includes(state.inventorySearch);
        });

        els.inventoryBody.innerHTML = filtered.map((item) => {
            const status = getStockStatus(item.stock, item.min);
            return `
                <tr>
                    <td>${escapeHtml(item.item)}</td>
                    <td>${escapeHtml(item.categoria)}</td>
                    <td>${item.stock}</td>
                    <td><span class="fund-stock-badge ${status.level}">${status.label}</span></td>
                    <td>${escapeHtml(item.responsable)}</td>
                </tr>
            `;
        }).join('');

        if (!filtered.length) {
            els.inventoryBody.innerHTML = '<tr><td colspan="5">Sin resultados para la búsqueda actual.</td></tr>';
        }

        const totalItems = filtered.length;
        const totalUnits = filtered.reduce((acc, item) => acc + Number(item.stock || 0), 0);
        const critical = filtered.filter((item) => getStockStatus(item.stock, item.min).level === 'critico').length;

        if (els.kpiItems) {
            els.kpiItems.textContent = String(totalItems);
        }

        if (els.kpiUnits) {
            els.kpiUnits.textContent = String(totalUnits);
        }

        if (els.kpiCritical) {
            els.kpiCritical.textContent = String(critical);
        }
    }

    function renderReports() {
        if (!state.selectedSedeId) return;

        const tasks = getTasksForSelectedSede();
        const inventory = getInventoryForSelectedSede();
        const filteredInventory = inventory.filter((item) => {
            if (!state.inventorySearch) return true;
            const haystack = `${item.item} ${item.categoria}`.toLowerCase();
            return haystack.includes(state.inventorySearch);
        });

        const completed = tasks.filter((t) => t.estado === 'completada').length;
        const active = tasks.length - completed;
        const completionRate = tasks.length ? Math.round((completed / tasks.length) * 100) : 0;

        if (els.reportActive) {
            els.reportActive.textContent = String(active);
        }

        if (els.reportCompleted) {
            els.reportCompleted.textContent = String(completed);
        }

        if (els.reportRate) {
            els.reportRate.textContent = `${completionRate}%`;
        }

        if (els.reportTaskSummary) {
            const byStatus = ['pendiente', 'en_progreso', 'completada'].map((statusKey) => {
                const count = tasks.filter((t) => t.estado === statusKey).length;
                return `<li>${TASK_STATE_LABEL[statusKey] || statusKey}: ${count}</li>`;
            }).join('');
            els.reportTaskSummary.innerHTML = byStatus;
        }

        if (els.reportCriticalList) {
            const riskyItems = filteredInventory
                .filter((item) => {
                    const level = getStockStatus(item.stock, item.min).level;
                    return level === 'critico' || level === 'bajo';
                })
                .slice(0, 6);

            els.reportCriticalList.innerHTML = riskyItems.length
                ? riskyItems.map((item) => {
                    const status = getStockStatus(item.stock, item.min);
                    return `<li>${escapeHtml(item.item)} · ${status.label} (${item.stock} unidades)</li>`;
                }).join('')
                : '<li>Sin riesgos de inventario para esta sede.</li>';
        }

        if (els.reportAgendaList) {
            const today = stripTime(new Date());
            const nextWeek = addDays(today, 7);
            const agenda = tasks
                .filter((t) => t.start >= today && t.start <= nextWeek)
                .sort((a, b) => a.start - b.start)
                .slice(0, 6);

            els.reportAgendaList.innerHTML = agenda.length
                ? agenda.map((task) => `<li>${escapeHtml(formatDateShort(task.start))}: ${escapeHtml(task.title)}</li>`).join('')
                : '<li>Sin actividades programadas para los próximos 7 días.</li>';
        }
    }

    async function fetchTasksFromApi() {
        if (!window.fetchApi) {
            throw new Error('fetchApi no disponible');
        }

        const response = await window.fetchApi('/api/fundacion/tareas', { timeoutMs: 9000 });
        if (!Array.isArray(response)) {
            return [];
        }

        return response;
    }

    function hydrateTasksBySede(rawTasks) {
        const buckets = {};

        SEDES.forEach((sede) => {
            buckets[sede.id] = [];
        });

        const normalizedApiTasks = Array.isArray(rawTasks)
            ? rawTasks
                .map((task) => normalizeApiTask(task))
                .filter(Boolean)
            : [];

        if (normalizedApiTasks.length) {
            normalizedApiTasks.forEach((task) => {
                const resolvedSede = resolveSedeFromTask(task);
                const targetSedeId = buckets[resolvedSede] ? resolvedSede : (SEDES[0]?.id || '');
                if (!targetSedeId) return;
                task.sedeId = targetSedeId;
                buckets[targetSedeId].push(task);
            });
        } else {
            SEDES.forEach((sede) => {
                buckets[sede.id] = generateMockTasksForSede(sede.id);
            });
        }

        Object.keys(buckets).forEach((key) => {
            buckets[key].sort((a, b) => a.start.getTime() - b.start.getTime());
        });

        state.tasksBySede = buckets;

        if (state.selectedSedeId) {
            populateCursoOptions();
        } else {
            renderSedeSelector();
        }
    }

    function normalizeApiTask(task) {
        if (!task || !task.fecha_inicio) return null;

        const start = new Date(task.fecha_inicio);
        if (Number.isNaN(start.getTime())) return null;

        const endRaw = task.fecha_fin ? new Date(task.fecha_fin) : null;
        const end = endRaw && !Number.isNaN(endRaw.getTime()) ? endRaw : start;

        const status = normalizeStatus(task.estado);
        const color = task.color || '#4facfe';
        const rawCurso = String(task.curso || task.categoria || task.categoria_madre || task.subcategoria || '').trim();
        const cursoId = resolveCursoIdFromRaw(rawCurso);
        const cursoLabel = cursoId ? getCursoLabel(cursoId, rawCurso || 'Sin curso') : '';

        return {
            id: task.id || `task-${Math.random().toString(36).slice(2)}`,
            title: String(task.titulo || 'Actividad Fundación'),
            owner: String(task.asignado_a || 'Sin asignar'),
            start,
            end,
            estado: status,
            estadoLabel: TASK_STATE_LABEL[status] || status,
            color,
            sede: String(task.sede || '').trim(),
            cursoId,
            cursoLabel,
            sedeHint: String(task.curso || task.categoria || task.categoria_madre || task.subcategoria || '').trim(),
            timeLabel: `${pad2(start.getHours())}:${pad2(start.getMinutes())}`,
        };
    }

    function normalizeStatus(status) {
        const raw = String(status || '').toLowerCase().trim();
        if (['completada', 'completo', 'done', 'finalizada'].includes(raw)) return 'completada';
        if (['en_progreso', 'en progreso', 'working', 'progreso'].includes(raw)) return 'en_progreso';
        return 'pendiente';
    }

    function resolveSedeFromTask(task) {
        const hints = [task?.sede, task?.sedeHint]
            .map((value) => normalizeScopeValue(value))
            .filter(Boolean);

        let matched = null;
        for (const hint of hints) {
            matched = SEDES.find((sede) => {
                const aliases = Array.isArray(sede.aliases) ? sede.aliases : [];
                return hint === sede.id
                    || aliases.includes(hint)
                    || hint.includes(sede.id)
                    || sede.id.includes(hint);
            });
            if (matched) break;
        }

        return matched ? matched.id : (SEDES[0]?.id || '');
    }

    function generateMockTasksForSede(sedeId) {
        const sede = getSelectedSedeById(sedeId);
        const base = stripTime(new Date());
        const availableCourseIds = getCourseIdsForSede(sedeId);
        const descriptors = [
            { offset: 0, hour: 9, title: 'Reunión de coordinación semanal', estado: 'en_progreso' },
            { offset: 1, hour: 11, title: 'Levantamiento de inventario crítico', estado: 'pendiente' },
            { offset: 2, hour: 15, title: 'Planificación de actividades comunitarias', estado: 'pendiente' },
            { offset: 4, hour: 10, title: 'Seguimiento de compromisos operativos', estado: 'completada' },
            { offset: 5, hour: 16, title: 'Reporte de avance regional', estado: 'pendiente' },
            { offset: 7, hour: 12, title: 'Capacitación de equipo sede', estado: 'pendiente' },
            { offset: 10, hour: 9, title: 'Mesa de trabajo intersede', estado: 'en_progreso' },
            { offset: 12, hour: 14, title: 'Actualización plan mensual', estado: 'pendiente' },
        ];

        return descriptors.map((descriptor, idx) => {
            const date = addDays(base, descriptor.offset);
            const start = new Date(date.getFullYear(), date.getMonth(), date.getDate(), descriptor.hour, 0, 0, 0);
            const end = new Date(start.getTime() + 60 * 60 * 1000);
            const cursoId = availableCourseIds[idx % availableCourseIds.length] || '1ro-2do-basico';
            const cursoLabel = getCursoLabel(cursoId, 'Curso');

            return {
                id: `${sedeId}-${idx + 1}`,
                title: `${descriptor.title} · ${cursoLabel}`,
                owner: sede?.responsable || 'Encargado/a sede',
                start,
                end,
                estado: descriptor.estado,
                estadoLabel: TASK_STATE_LABEL[descriptor.estado],
                color: sede?.color || '#4facfe',
                sede: sede?.id || sedeId,
                sedeId: sede?.id || sedeId,
                cursoId,
                cursoLabel,
                sedeHint: sede?.nombre || sedeId,
                timeLabel: `${pad2(start.getHours())}:${pad2(start.getMinutes())}`,
            };
        });
    }

    function getSelectedSedeById(sedeId) {
        return SEDES.find((s) => s.id === sedeId) || null;
    }

    function getTasksForSelectedSede() {
        if (!state.selectedSedeId) return [];

        const tasks = state.tasksBySede[state.selectedSedeId] || [];
        const allowedCourseIds = getAllowedCourseIds();
        let filtered = tasks;

        if (allowedCourseIds.length) {
            filtered = filtered.filter((task) => !task.cursoId || allowedCourseIds.includes(task.cursoId));
        }

        if (state.selectedCursoId && state.selectedCursoId !== 'all') {
            filtered = filtered.filter((task) => task.cursoId === state.selectedCursoId);
        }

        return filtered;
    }

    function getInventoryForSelectedSede() {
        if (!state.selectedSedeId) return [];
        return state.inventoryBySede[state.selectedSedeId] || [];
    }

    function getStockStatus(stock, min) {
        const qty = Number(stock || 0);
        const threshold = Number(min || 0);
        if (qty <= Math.max(1, Math.floor(threshold * 0.6))) {
            return { level: 'critico', label: 'Crítico' };
        }
        if (qty < threshold) {
            return { level: 'bajo', label: 'Bajo' };
        }
        return { level: 'ok', label: 'OK' };
    }

    function setStatus(message) {
        if (els.status) {
            els.status.textContent = message;
        }
    }

    async function loadSessionScope() {
        if (!window.fetchApi) return;

        try {
            const session = await window.fetchApi('/api/sesion', { timeoutMs: 9000 });
            if (!session || session.ok !== true) return;

            const roles = Array.isArray(session.roles) ? session.roles : [session.role].filter(Boolean);
            state.session = {
                user: String(session.user || ''),
                role: String(session.role || ''),
                roles,
                fundacionScope: normalizeScopePayload(session.fundacion_scope),
            };
        } catch (_) {
            // Mantener fallback abierto para no romper navegación en DEV.
        }
    }

    function normalizeScopePayload(rawScope) {
        const rawSedes = Array.isArray(rawScope?.sedes) ? rawScope.sedes : [];
        const rawCursos = Array.isArray(rawScope?.cursos) ? rawScope.cursos : [];

        const sedes = [...new Set(rawSedes.map((value) => resolveSedeIdFromRaw(value)).filter(Boolean))];
        const cursos = [...new Set(rawCursos.map((value) => resolveCursoIdFromRaw(value)).filter(Boolean))];

        const isGlobal = Boolean(rawScope?.is_global) || (!sedes.length && !cursos.length);
        return { is_global: isGlobal, sedes, cursos };
    }

    function getVisibleSedes() {
        const allowedSedes = getAllowedSedeIds();
        if (!allowedSedes.length) return SEDES;
        return SEDES.filter((sede) => allowedSedes.includes(sede.id));
    }

    function getAllowedSedeIds() {
        const scope = state.session?.fundacionScope;
        if (!scope || scope.is_global) return [];
        return scope.sedes || [];
    }

    function getAllowedCourseIds() {
        const scope = state.session?.fundacionScope;
        if (!scope || scope.is_global) return [];
        return scope.cursos || [];
    }

    function canAccessSede(sedeId) {
        const allowedSedes = getAllowedSedeIds();
        if (!allowedSedes.length) return true;
        return allowedSedes.includes(sedeId);
    }

    function populateCursoOptions() {
        if (!els.cursoSelect || !state.selectedSedeId) return;

        const courseIds = getCourseIdsForSede(state.selectedSedeId);
        const options = [];

        if (courseIds.length > 1) {
            options.push({ id: 'all', label: 'Todos los cursos' });
        }

        courseIds.forEach((courseId) => {
            options.push({ id: courseId, label: getCursoLabel(courseId, courseId) });
        });

        if (!options.length) {
            options.push({ id: 'all', label: 'Todos los cursos' });
        }

        const optionValues = options.map((option) => option.id);
        if (!optionValues.includes(state.selectedCursoId)) {
            state.selectedCursoId = options[0].id;
        }

        els.cursoSelect.innerHTML = options
            .map((option) => `<option value="${escapeHtml(option.id)}">${escapeHtml(option.label)}</option>`)
            .join('');
        els.cursoSelect.value = state.selectedCursoId;
    }

    function getCourseIdsForSede(sedeId) {
        const sedeTasks = state.tasksBySede[sedeId] || [];
        const idsFromTasks = [...new Set(sedeTasks.map((task) => task.cursoId).filter(Boolean))];
        const baseIds = idsFromTasks.length ? idsFromTasks : DEFAULT_CURSO_IDS;

        const allowedCourseIds = getAllowedCourseIds();
        const filteredByScope = allowedCourseIds.length
            ? baseIds.filter((id) => allowedCourseIds.includes(id))
            : baseIds;

        return filteredByScope.length ? filteredByScope : (allowedCourseIds.length ? allowedCourseIds : baseIds);
    }

    function getCursoLabel(cursoId, fallback = 'Curso') {
        if (!cursoId) return fallback;
        const match = CURSOS.find((curso) => curso.id === cursoId);
        return match ? match.label : fallback;
    }

    function resolveSedeIdFromRaw(rawSede) {
        const normalized = normalizeScopeValue(rawSede);
        if (!normalized) return '';

        const exact = SEDES.find((sede) => sede.id === normalized);
        if (exact) return exact.id;

        const byAlias = SEDES.find((sede) => {
            const aliases = Array.isArray(sede.aliases) ? sede.aliases : [];
            return aliases.some((alias) => normalized === alias || normalized.includes(alias) || alias.includes(normalized));
        });

        return byAlias ? byAlias.id : normalized;
    }

    function resolveCursoIdFromRaw(rawCurso) {
        const normalized = normalizeScopeValue(rawCurso);
        if (!normalized) return '';

        if (ACTIVIDADES_NO_CURSO.has(normalized)) {
            return '';
        }

        const exact = CURSOS.find((curso) => curso.id === normalized);
        if (exact) return exact.id;

        const byAlias = CURSOS.find((curso) => {
            const aliases = Array.isArray(curso.aliases) ? curso.aliases : [];
            return aliases.some((alias) => normalized === alias || normalized.includes(alias) || alias.includes(normalized));
        });

        return byAlias ? byAlias.id : normalized;
    }

    function normalizeScopeValue(value) {
        return String(value || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim()
            .replace(/[\/_]+/g, '-')
            .replace(/\s+/g, '-')
            .replace(/[^a-z0-9-]/g, '')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '');
    }

    function renderScopeHint() {
        if (!els.scopeHint) return;

        const chunks = [];
        const scope = state.session?.fundacionScope;
        if (scope && !scope.is_global) {
            if (scope.sedes.length) {
                chunks.push(`Sedes asignadas: ${scope.sedes.length}`);
            }
            if (scope.cursos.length) {
                chunks.push(`Cursos asignados: ${scope.cursos.length}`);
            }
        }

        if (state.selectedCursoId && state.selectedCursoId !== 'all') {
            chunks.push(`Curso activo: ${getCursoLabel(state.selectedCursoId, state.selectedCursoId)}`);
        }

        els.scopeHint.textContent = chunks.length ? chunks.join(' · ') : 'Acceso global de Fundación';
    }

    function refreshWorkspace() {
        renderScopeHint();
        renderCalendar();
        renderInventory();
        renderReports();
    }

    function startOfWeek(date) {
        const d = stripTime(date);
        const day = d.getDay();
        return addDays(d, -day);
    }

    function stripTime(date) {
        const d = new Date(date);
        d.setHours(0, 0, 0, 0);
        return d;
    }

    function addDays(date, days) {
        const d = new Date(date);
        d.setDate(d.getDate() + days);
        return d;
    }

    function addMonths(date, months) {
        const d = new Date(date);
        const currentDate = d.getDate();
        d.setDate(1);
        d.setMonth(d.getMonth() + months);
        const maxDay = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
        d.setDate(Math.min(currentDate, maxDay));
        return d;
    }

    function sameDate(a, b) {
        return a.getFullYear() === b.getFullYear()
            && a.getMonth() === b.getMonth()
            && a.getDate() === b.getDate();
    }

    function formatDateShort(date) {
        return `${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`;
    }

    function formatDateLong(date) {
        return `${WEEK_DAYS[date.getDay()]} ${pad2(date.getDate())} de ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
    }

    function toISODate(date) {
        return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
    }

    function pad2(value) {
        return String(value).padStart(2, '0');
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
})();