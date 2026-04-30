// Catálogo — grid de procesos disponibles
window.Catalogo = (() => {
    let _datos = [];
    let _areaFiltro = '';

    function init() {
        cargar();
    }

    async function cargar() {
        const grid = document.getElementById('catalogo-grid');
        if (!grid) return;
        grid.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando catálogo...</div>`;
        try {
            const data = await GtaApi.getProcesos('?estado=activo');
            _datos = Array.isArray(data) ? data : [];
            _render(_datos);
        } catch (e) {
            grid.innerHTML = GtaUi.empty('Error al cargar el catálogo.');
        }
    }

    function filtrar(texto) {
        const q = (texto || '').toLowerCase();
        const filtrado = _datos.filter(p =>
            (!_areaFiltro || p.area === _areaFiltro) &&
            (!q || p.nombre.toLowerCase().includes(q) || (p.descripcion || '').toLowerCase().includes(q))
        );
        _render(filtrado);
    }

    function filtrarArea(btn) {
        document.querySelectorAll('.gta-area-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _areaFiltro = btn.dataset.area || '';
        filtrar(document.getElementById('catalogo-search')?.value || '');
    }

    function _render(lista) {
        const grid = document.getElementById('catalogo-grid');
        if (!grid) return;
        if (!lista.length) {
            grid.innerHTML = GtaUi.empty('No hay procesos disponibles para este filtro.');
            return;
        }
        grid.innerHTML = lista.map(p => GtaUi.procesoCard(p)).join('');
    }

    return { init, cargar, filtrar, filtrarArea };
})();
