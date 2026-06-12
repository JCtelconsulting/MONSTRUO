// Fundación — controlador principal (estructura canónica del design system)
window.FundCore = (() => {
    const ADMIN_ROLES = new Set(['admin', 'directora_social', 'jefa_pedagogica', 'coordinadora_territorial']);

    let _currentTab = null;
    let _loadedResources = new Set();
    let _sesion = null;
    let _sedes = [];          // sedes accesibles para el usuario
    let _esAdmin = false;
    let _selectedSedeId = null;

    // ── Init ──────────────────────────────────────────────────────────
    async function init() {
        try {
            const data = await window.fetchApi('/api/sesion');
            if (data && data.ok) _sesion = data;
        } catch (e) { /* sin sesión, dejar continuar al render — el backend rechazará */ }

        // El indicador "es admin" del cliente es informativo; el backend
        // siempre tiene la última palabra (doble candado).
        const role = String(_sesion?.role || '').toLowerCase();
        const roles = (_sesion?.roles || []).map(r => String(r).toLowerCase());
        _esAdmin = ADMIN_ROLES.has(role) || roles.some(r => ADMIN_ROLES.has(r));

        await _cargarSedes();
        _renderSedeSelector();
        _toggleConfigTab();

        // Restaurar sede seleccionada de localStorage (si está en las accesibles)
        const stored = localStorage.getItem('fund.selectedSedeId');
        const storedNum = stored ? parseInt(stored, 10) : null;
        if (storedNum && _sedes.some(s => s.id === storedNum)) {
            _selectedSedeId = storedNum;
        } else if (_sedes.length > 0) {
            _selectedSedeId = _sedes[0].id;
        }
        _syncSelector();

        await loadTab('planificacion');
    }

    function getSesion()      { return _sesion; }
    function isAdmin()        { return _esAdmin; }
    function getSedes()       { return _sedes; }
    function getSelectedSede() {
        return _sedes.find(s => s.id === _selectedSedeId) || null;
    }

    async function _cargarSedes() {
        try {
            const r = await FundApi.getSedesAccesibles();
            _sedes = r.items || [];
            _esAdmin = !!r.es_admin;
        } catch (e) {
            console.error('[Fundación] error cargando sedes', e);
            _sedes = [];
        }
    }

    function _renderSedeSelector() {
        const sel = document.getElementById('fund-sede-select');
        const lock = document.getElementById('fund-sede-lock');
        if (!sel) return;
        if (!_sedes.length) {
            sel.innerHTML = '<option value="">— Sin sedes asignadas —</option>';
            sel.disabled = true;
            if (lock) lock.hidden = false;
            return;
        }
        sel.innerHTML = _sedes.map(s => `<option value="${s.id}">${_esc(s.nombre)}</option>`).join('');
        sel.disabled = false;

        // Bloqueo: si el usuario no es admin Y solo tiene una sede, queda fija.
        const blocked = !_esAdmin && _sedes.length === 1;
        sel.disabled = blocked;
        if (lock) lock.hidden = !blocked;

        sel.onchange = () => {
            _selectedSedeId = parseInt(sel.value, 10) || null;
            if (_selectedSedeId) localStorage.setItem('fund.selectedSedeId', String(_selectedSedeId));
            // Notificar al tab activo
            const tabMod = _tabModule(_currentTab);
            if (tabMod && typeof tabMod.onSedeChange === 'function') {
                tabMod.onSedeChange(getSelectedSede());
            }
        };
    }

    function _syncSelector() {
        const sel = document.getElementById('fund-sede-select');
        if (sel && _selectedSedeId) sel.value = String(_selectedSedeId);
    }

    function _toggleConfigTab() {
        const btn = document.querySelector('.tab-btn[data-tab="configuracion"]');
        if (btn) btn.hidden = !_esAdmin;
    }

    // ── Tabs ──────────────────────────────────────────────────────────
    async function loadTab(tabName, triggerEl) {
        if (_currentTab === tabName) return;

        // Bloqueo: no-admin no puede entrar a configuracion (doble candado UI)
        if (tabName === 'configuracion' && !_esAdmin) {
            console.warn('[Fundación] tab configuracion bloqueado para rol no-admin');
            return;
        }

        _currentTab = tabName;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        const btn = triggerEl || document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
        if (btn) btn.classList.add('active');

        const container = document.getElementById('tab-content');
        if (!container) return;
        container.innerHTML = `<div class="fund-loading"><i class="fas fa-spinner fa-spin"></i> Cargando…</div>`;

        try {
            const v = window.ASSET_VERSION || 'dev';
            const resp = await fetch(`${tabName}/${tabName}.html?v=${v}`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            container.innerHTML = await resp.text();

            if (!_loadedResources.has(`css-${tabName}`)) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = `${tabName}/${tabName}.css?v=${v}`;
                document.head.appendChild(link);
                _loadedResources.add(`css-${tabName}`);
            }

            if (!_loadedResources.has(`js-${tabName}`)) {
                const script = document.createElement('script');
                script.src = `${tabName}/${tabName}.js?v=${v}`;
                document.body.appendChild(script);
                _loadedResources.add(`js-${tabName}`);
                await new Promise(r => { script.onload = r; script.onerror = r; });
            }

            const tabMod = _tabModule(tabName);
            if (tabMod && typeof tabMod.init === 'function') {
                tabMod.init({
                    sesion: _sesion,
                    sedes: _sedes,
                    sede: getSelectedSede(),
                    esAdmin: _esAdmin,
                });
            }
        } catch (e) {
            console.error('[Fundación] error cargando tab', tabName, e);
            container.innerHTML = `<div class="fund-empty"><i class="fas fa-triangle-exclamation"></i> Error al cargar.</div>`;
        }
    }

    function _tabModule(tabName) {
        const map = {
            planificacion: window.FundPlanificacion,
            bodegas:       window.FundBodegas,
            reporteria:    window.FundReporteria,
            configuracion: window.FundConfiguracion,
        };
        return map[tabName] || null;
    }

    function _esc(s) {
        if (s == null) return '';
        return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    return { init, loadTab, getSesion, isAdmin, getSedes, getSelectedSede };
})();
