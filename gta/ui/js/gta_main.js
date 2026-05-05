// GTA Main v5 — controlador principal (modelo de procesos unificados + flujos)
window.GtaCore = (() => {
    let _currentTab = null;
    let _loadedResources = new Set();
    let _sesion = null;

    // ── Init ──────────────────────────────────────────────────────────────
    async function init() {
        try {
            const data = await window.fetchApi('/api/sesion');
            if (data && data.ok) _sesion = data;
        } catch (e) { /* sin sesión */ }

        await loadTab('tablero');
    }

    function getSesion() { return _sesion; }

    function isAdmin() {
        const role = String(_sesion?.role || '').toLowerCase();
        const username = String(_sesion?.username || '');
        return role === 'admin' || role === 'gerencia' || username === 'sistemas@telconsulting.cl';
    }

    // ── Tabs ──────────────────────────────────────────────────────────────
    async function loadTab(tabName, triggerEl) {
        if (_currentTab === tabName) return;
        _currentTab = tabName;

        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        const btn = triggerEl || document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
        if (btn) btn.classList.add('active');

        const container = document.getElementById('tab-content');
        if (!container) return;
        container.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;

        try {
            const resp = await fetch(`${tabName}/${tabName}.html`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            container.innerHTML = await resp.text();

            // Cache-busting compartido: inyectado por gateway al servir el HTML padre.
            // Ver plataforma/core/version.py.
            const v = window.ASSET_VERSION || 'dev';
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

            const inits = {
                tablero: window.Tablero,
                procesos: window.Procesos,
            };
            if (inits[tabName]?.init) inits[tabName].init(_sesion);
        } catch (e) {
            console.error('Error cargando tab', tabName, e);
            container.innerHTML = '<div class="gta-empty">Error al cargar la pestaña.</div>';
        }
    }

    return { init, loadTab, getSesion, isAdmin };
})();
