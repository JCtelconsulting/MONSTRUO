window.FundPlanificacion = (() => {
    let _ctx = null;

    async function init(ctx) {
        _ctx = ctx;
        _renderHead();
        await _cargarTareas();
    }

    async function onSedeChange(sede) {
        _ctx = { ..._ctx, sede };
        _renderHead();
        await _cargarTareas();
    }

    function _renderHead() {
        const t = document.getElementById('plan-sede-title');
        const s = document.getElementById('plan-sede-subtitle');
        if (!_ctx || !_ctx.sede) {
            if (t) t.textContent = 'Planificación — sin sede seleccionada';
            if (s) s.textContent = 'Asigná una sede para ver las tareas.';
            return;
        }
        if (t) t.textContent = `Planificación — ${_ctx.sede.nombre}`;
        if (s) s.textContent = _ctx.sede.region || '';
    }

    async function _cargarTareas() {
        const tbody = document.getElementById('plan-tareas-body');
        if (!tbody) return;
        if (!_ctx?.sede) {
            tbody.innerHTML = '<tr><td colspan="5" class="fund-empty-row">Seleccioná una sede.</td></tr>';
            return;
        }
        tbody.innerHTML = '<tr><td colspan="5" class="fund-empty-row"><i class="fas fa-spinner fa-spin"></i> Cargando…</td></tr>';

        try {
            const tareas = await FundApi.listarTareas();
            const arr = Array.isArray(tareas) ? tareas : (tareas?.items || []);
            const sedeCode = _ctx.sede.code;
            const filtradas = arr.filter(t => !t.sede || t.sede === sedeCode);

            // KPIs
            const ahora = new Date();
            const en7 = new Date(); en7.setDate(en7.getDate() + 7);
            const hace30 = new Date(); hace30.setDate(hace30.getDate() - 30);
            const activas = filtradas.filter(t => t.estado !== 'completada' && t.estado !== 'cancelada');
            const vencen = activas.filter(t => {
                const d = t.fecha_fin ? new Date(t.fecha_fin) : (t.fecha_inicio ? new Date(t.fecha_inicio) : null);
                return d && d >= ahora && d <= en7;
            });
            const completadas = filtradas.filter(t => t.estado === 'completada' && t.updated_at && new Date(t.updated_at) >= hace30);
            _setKpi('plan-kpi-tareas', activas.length);
            _setKpi('plan-kpi-vencen', vencen.length);
            _setKpi('plan-kpi-completadas', completadas.length);

            const proximas = activas
                .slice()
                .sort((a, b) => new Date(a.fecha_inicio || 0) - new Date(b.fecha_inicio || 0))
                .slice(0, 20);

            if (!proximas.length) {
                tbody.innerHTML = '<tr><td colspan="5" class="fund-empty-row">Sin tareas próximas.</td></tr>';
                return;
            }
            tbody.innerHTML = proximas.map(t => `
                <tr>
                    <td>${_fmt(t.fecha_inicio)}</td>
                    <td>${_esc(t.titulo)}</td>
                    <td>${_esc(t.curso || '—')}</td>
                    <td>${_esc(t.asignado_a || '—')}</td>
                    <td><span class="tarea-tag">${_esc(t.estado || 'pendiente')}</span></td>
                </tr>
            `).join('');
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="5" class="fund-empty-row">Error: ${_esc(e?.detail || e?.message || e)}</td></tr>`;
        }
    }

    function _setKpi(id, v) { const el = document.getElementById(id); if (el) el.textContent = v ?? '—'; }
    function _fmt(iso) { if (!iso) return '—'; try { return new Date(iso).toLocaleDateString('es-CL'); } catch { return iso; } }
    function _esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

    return { init, onSedeChange };
})();
