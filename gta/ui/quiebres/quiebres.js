// Quiebres — bandeja de procesos rotos
window.Quiebres = (() => {
    let _datos = [];

    function init() {
        cargar();
    }

    async function cargar() {
        const lista = document.getElementById('quiebres-lista');
        if (!lista) return;
        lista.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;
        try {
            const estado = document.getElementById('quiebres-filtro-estado')?.value ?? 'abierto';
            const params = estado ? `?estado=${estado}` : '';
            const data = await GtaApi.getQuiebres(params);
            _datos = Array.isArray(data) ? data : [];
            filtrar();
        } catch (e) {
            lista.innerHTML = GtaUi.empty('Error al cargar los quiebres.');
        }
    }

    function filtrar() {
        const lista  = document.getElementById('quiebres-lista');
        if (!lista) return;
        const tipo   = document.getElementById('quiebres-filtro-tipo')?.value || '';
        const area   = document.getElementById('quiebres-filtro-area')?.value || '';
        const estado = document.getElementById('quiebres-filtro-estado')?.value ?? 'abierto';

        let filtrado = _datos;
        if (tipo)   filtrado = filtrado.filter(q => q.tipo === tipo);
        if (area)   filtrado = filtrado.filter(q => q.area === area);
        if (estado) filtrado = filtrado.filter(q => q.estado === estado);

        if (!filtrado.length) {
            lista.innerHTML = GtaUi.empty('Sin quiebres para este filtro. ¡Todo en orden!');
            return;
        }
        lista.innerHTML = filtrado.map(q => GtaUi.quiebreRow(q)).join('');
    }

    return { init, cargar, filtrar };
})();
