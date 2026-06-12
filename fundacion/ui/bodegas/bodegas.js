window.FundBodegas = (() => {
    function init(ctx)         { _renderHead(ctx?.sede); }
    function onSedeChange(s)   { _renderHead(s); }

    function _renderHead(sede) {
        const t = document.getElementById('bod-sede-title');
        const s = document.getElementById('bod-sede-subtitle');
        if (!sede) {
            if (t) t.textContent = 'Bodegas — sin sede seleccionada';
            if (s) s.textContent = 'Asigná una sede.';
            return;
        }
        if (t) t.textContent = `Bodegas — ${sede.nombre}`;
        if (s) s.textContent = sede.region || '';
    }

    return { init, onSedeChange };
})();
