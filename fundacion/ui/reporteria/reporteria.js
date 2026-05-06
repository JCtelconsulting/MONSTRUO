window.FundReporteria = (() => {
    function init(ctx)        { _renderHead(ctx?.sede); }
    function onSedeChange(s)  { _renderHead(s); }

    function _renderHead(sede) {
        const t = document.getElementById('rep-sede-title');
        const s = document.getElementById('rep-sede-subtitle');
        if (!sede) {
            if (t) t.textContent = 'Reportería — sin sede';
            if (s) s.textContent = '';
            return;
        }
        if (t) t.textContent = `Reportería — ${sede.nombre}`;
        if (s) s.textContent = sede.region || '';
    }

    return { init, onSedeChange };
})();
