window.FundReporteria = (() => {
    let _ctx = null;
    let _esAdmin = false;
    let _dashboardCache = null;

    function init(ctx) {
        _ctx = ctx || {};
        _esAdmin = !!_ctx.esAdmin;
        _renderHead(_ctx.sede);

        const btn = document.getElementById('btn-sync-now');
        if (btn) {
            if (!_esAdmin) { btn.style.display = 'none'; }
            else { btn.addEventListener('click', _onClickSync); }
        }

        const sel = document.getElementById('rep-filtro-riesgo');
        if (sel) sel.addEventListener('change', () => _loadRiesgo(sel.value));

        _initRangoPed();
        _loadAll();
    }

    function _initRangoPed() {
        const hoy = new Date();
        const hace30 = new Date(); hace30.setDate(hace30.getDate() - 30);
        const desde = document.getElementById('rep-ped-desde');
        const hasta = document.getElementById('rep-ped-hasta');
        if (desde && !desde.value) desde.value = hace30.toISOString().slice(0, 10);
        if (hasta && !hasta.value) hasta.value = hoy.toISOString().slice(0, 10);
        const btn = document.getElementById('rep-ped-refresh');
        if (btn) btn.addEventListener('click', _loadPedagogicos);
        // Cargar al abrir cada accordion (solo la primera vez)
        document.querySelectorAll('.ped-card').forEach(card => {
            card.addEventListener('toggle', () => {
                if (card.open) _loadRep(card.dataset.rep);
            });
        });
    }

    function onSedeChange(sede) {
        _ctx = { ..._ctx, sede };
        _renderHead(sede);
        _loadAll();
    }

    function _renderHead(sede) {
        const t = document.getElementById('rep-sede-title');
        const s = document.getElementById('rep-sede-subtitle');
        if (sede && sede.id) {
            if (t) t.textContent = `Reportería — ${sede.nombre}`;
            if (s) s.textContent = sede.region || sede.code || '';
        } else {
            if (t) t.textContent = 'Reportería — todas las sedes';
            if (s) s.textContent = 'Vista global del programa';
        }
    }

    async function _loadAll() {
        await Promise.all([_loadDashboard(), _loadRiesgo(_currentRiesgo()), _loadPedagogicos()]);
    }

    function _rango() {
        return {
            desde: document.getElementById('rep-ped-desde')?.value || null,
            hasta: document.getElementById('rep-ped-hasta')?.value || null,
        };
    }

    async function _loadPedagogicos() {
        // Cargar todos los que estén abiertos
        const cards = document.querySelectorAll('.ped-card[open]');
        for (const c of cards) await _loadRep(c.dataset.rep);
    }

    async function _loadRep(rep) {
        const sedeId = _ctx?.sede?.id || null;
        const { desde, hasta } = _rango();
        try {
            switch (rep) {
                case 'cobertura':     return _renderCobertura(await window.FundApi.repCobertura(sedeId, desde, hasta));
                case 'competencias':  return _renderCompetencias(await window.FundApi.repCompetencias(sedeId, desde, hasta));
                case 'materiales':    return _renderMateriales(await window.FundApi.repMateriales(sedeId, desde, hasta));
                case 'adaptaciones':  return _renderAdaptaciones(await window.FundApi.repAdaptaciones(sedeId, desde, hasta));
                case 'clima':         return _renderClima(await window.FundApi.repClima(sedeId, desde, hasta));
                case 'actividad':     return _renderActividad(await window.FundApi.repActividadPeriodo(sedeId, desde, hasta));
            }
        } catch (e) {
            console.error(`[Reportería] error en ${rep}`, e);
        }
    }

    function _renderCobertura(data) {
        const tb = document.getElementById('rep-ped-cobertura');
        if (!tb) return;
        const items = data.items || [];
        if (!items.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-row">Sin datos para el rango seleccionado.</td></tr>'; return; }
        tb.innerHTML = items.map(r => `
            <tr>
                <td>${_esc(r.bloque_nombre)}</td>
                <td>${_esc(r.subtipo_nombre || '—')}</td>
                <td class="num pct-strong">${r.ejecutados}</td>
                <td class="num">${r.no_ejecutados}</td>
                <td class="num">${r.planificados}</td>
            </tr>`).join('');
    }

    function _renderCompetencias(data) {
        const tb = document.getElementById('rep-ped-competencias');
        if (!tb) return;
        const items = data.items || [];
        if (!items.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-row">Sin datos.</td></tr>'; return; }
        tb.innerHTML = items.map(r => `
            <tr>
                <td><span class="pill-riesgo bajo">${_esc(r.dominio_codigo)}</span> ${_esc(r.dominio_nombre)}</td>
                <td><strong>${_esc(r.competencia_codigo)}</strong></td>
                <td>${_esc(r.competencia_descripcion)}</td>
                <td class="num pct-strong">${r.veces_trabajada}</td>
                <td class="num">${r.planificada_no_ejecutada}</td>
            </tr>`).join('');
    }

    function _renderMateriales(data) {
        const tb = document.getElementById('rep-ped-materiales');
        if (!tb) return;
        const items = data.items || [];
        if (!items.length) { tb.innerHTML = '<tr><td colspan="6" class="empty-row">Sin datos.</td></tr>'; return; }
        tb.innerHTML = items.map(r => `
            <tr>
                <td>${_esc(r.material || '—')}</td>
                <td>${_esc(r.sku || '—')}</td>
                <td class="num">${r.total_solicitada ?? '—'}</td>
                <td class="num">${r.total_usada ?? '—'}</td>
                <td class="num">${r.diferencia ?? '—'}</td>
                <td class="num">${r.apariciones ?? 0}</td>
            </tr>`).join('');
    }

    function _renderAdaptaciones(data) {
        const tb = document.getElementById('rep-ped-adaptaciones');
        if (!tb) return;
        const items = data.items || [];
        if (!items.length) { tb.innerHTML = '<tr><td colspan="6" class="empty-row">Sin adaptaciones registradas.</td></tr>'; return; }
        tb.innerHTML = items.map(r => `
            <tr>
                <td>${_esc(r.fecha)}</td>
                <td>${_esc(r.sede_nombre)}</td>
                <td>${_esc(r.bloque_nombre)}</td>
                <td>${_esc(r.nombre_actividad || '—')}</td>
                <td>${r.se_ejecuto ? '<span class="pill-riesgo bajo">Sí</span>' : '<span class="pill-riesgo alto">No</span>'}</td>
                <td>${_esc(r.adaptacion || r.motivo_no_ejecucion || '—')}</td>
            </tr>`).join('');
    }

    function _renderClima(data) {
        const distrib = data.distribucion || [];
        const detalle = data.detalle || [];
        const dEl = document.getElementById('rep-ped-clima-distrib');
        if (dEl) {
            dEl.innerHTML = distrib.length
                ? distrib.map(c => `
                    <span class="ped-clima-chip">
                        <span class="ped-clima-chip-dot" style="background:${_esc(c.clima_color || '#888')}"></span>
                        ${_esc(c.clima_nombre)}
                        <span class="ped-clima-chip-n">${c.dias}</span>
                    </span>`).join('')
                : '<span class="reporteria-meta">Sin clima registrado en el rango.</span>';
        }
        const tb = document.getElementById('rep-ped-clima');
        if (!tb) return;
        if (!detalle.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-row">Sin datos.</td></tr>'; return; }
        tb.innerHTML = detalle.map(r => `
            <tr>
                <td>${_esc(r.fecha)}</td>
                <td>${_esc(r.sede_nombre)}</td>
                <td><span class="ped-clima-chip"><span class="ped-clima-chip-dot" style="background:${_esc(r.clima_color || '#888')}"></span>${_esc(r.clima_nombre || '—')}</span></td>
                <td>${_esc(r.situaciones_relevantes || '—')}</td>
                <td>${_esc(r.estrategias_aplicadas || '—')}</td>
            </tr>`).join('');
    }

    function _renderActividad(data) {
        const tb = document.getElementById('rep-ped-actividad');
        if (!tb) return;
        const items = data.items || [];
        if (!items.length) { tb.innerHTML = '<tr><td colspan="6" class="empty-row">Sin datos.</td></tr>'; return; }
        const meses = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
        tb.innerHTML = items.map(r => `
            <tr>
                <td>${_esc(r.sede_nombre)}</td>
                <td>${r.anio}</td>
                <td>${_esc(meses[r.mes_num - 1] || r.mes_num)}</td>
                <td class="num">${r.planificados}</td>
                <td class="num">${r.ejecutados}</td>
                <td class="num pct-strong">${_fmtPct(r.pct_ejecucion)}</td>
            </tr>`).join('');
    }

    function _currentRiesgo() {
        const sel = document.getElementById('rep-filtro-riesgo');
        return sel ? sel.value : 'alto';
    }

    async function _loadDashboard() {
        try {
            const data = await window.FundApi.getDashboard();
            _dashboardCache = data;
            _renderKpisGlobal(data);
            _renderTablaSedes(data.sedes || []);
            _renderUltimoSync(data.ultimo_sync);
        } catch (e) {
            console.error('[Reportería] error cargando dashboard', e);
            window.showToast?.('No se pudo cargar el dashboard', 'error');
        }
    }

    function _renderKpisGlobal(data) {
        const tot = data.totales || {};
        const riesgo = data.riesgo || {};
        const sedeId = _ctx?.sede?.id;
        const sedes = data.sedes || [];

        if (sedeId) {
            const fila = sedes.find(s => s.sede_id === sedeId);
            _setKpi('rep-kpi-alumnos', fila?.alumnos_total ?? 0);
            _setKpi('rep-kpi-activos', fila?.alumnos_activos ?? 0);
            _setKpi('rep-kpi-asistencia', _fmtPct(fila?.pct_asistencia_sede));
            _setKpi('rep-kpi-riesgo-alto', '—');
        } else {
            _setKpi('rep-kpi-alumnos', tot.alumnos_total ?? 0);
            _setKpi('rep-kpi-activos', tot.alumnos_activos ?? 0);
            _setKpi('rep-kpi-asistencia', _fmtPct(_pctGlobalDeSedes(sedes)));
            _setKpi('rep-kpi-riesgo-alto', riesgo.alto ?? 0);
        }
    }

    function _pctGlobalDeSedes(sedes) {
        let p = 0, total = 0;
        for (const s of sedes) {
            p += Number(s.p_total || 0);
            total += Number(s.contables_total || 0);
        }
        return total > 0 ? Math.round((1000 * p) / total) / 10 : null;
    }

    function _renderTablaSedes(sedes) {
        const tb = document.getElementById('rep-tabla-sedes');
        if (!tb) return;
        if (!sedes.length) {
            tb.innerHTML = '<tr><td colspan="6" class="empty-row">Sin sedes accesibles</td></tr>';
            return;
        }
        tb.innerHTML = sedes.map(s => {
            const cob = s.cupos ? Math.round(100 * (s.alumnos_activos || 0) / s.cupos) + '%' : '—';
            return `
              <tr>
                <td>${_esc(s.sede_nombre)}</td>
                <td class="num">${s.alumnos_total ?? 0}</td>
                <td class="num">${s.alumnos_activos ?? 0}</td>
                <td class="num">${s.cupos ?? '—'}</td>
                <td class="num">${cob}</td>
                <td class="num pct-strong">${_fmtPct(s.pct_asistencia_sede)}</td>
              </tr>`;
        }).join('');
    }

    function _renderUltimoSync(u) {
        const el = document.getElementById('rep-ultimo-sync');
        if (!el) return;
        if (!u) { el.textContent = 'Sin syncs todavía'; return; }
        const fecha = u.finished_at ? new Date(u.finished_at) : null;
        const cuando = fecha ? fecha.toLocaleString('es-CL') : '—';
        const labels = { ok: 'OK', error: 'Falló', partial: 'Parcial', running: 'En curso' };
        el.textContent = `Último sync: ${cuando} (${labels[u.status] || u.status})`;
    }

    async function _loadRiesgo(nivel) {
        const tb = document.getElementById('rep-tabla-riesgo');
        if (!tb) return;
        tb.innerHTML = '<tr><td colspan="7" class="empty-row">Cargando…</td></tr>';
        try {
            const filtros = { nivel_riesgo: nivel, matricula_activa: true };
            const sedeId = _ctx?.sede?.id;
            if (sedeId) filtros.sede_id = sedeId;
            const data = await window.FundApi.getReporteAlumnos(filtros);
            const items = data.items || [];
            const sedesNombres = {};
            for (const s of (_dashboardCache?.sedes || [])) sedesNombres[s.sede_id] = s.sede_nombre;

            if (!items.length) {
                tb.innerHTML = `<tr><td colspan="7" class="empty-row">Sin alumnos en riesgo ${_labelRiesgo(nivel)}.</td></tr>`;
                return;
            }
            tb.innerHTML = items.map(a => `
              <tr>
                <td>${_esc(sedesNombres[a.sede_id] || `#${a.sede_id}`)}</td>
                <td>${_esc(a.nombre_completo)}</td>
                <td>${_esc(a.curso_after || '—')}</td>
                <td>${_esc(a.plan || '—')}</td>
                <td>${_esc(a.gestora_a_cargo || '—')}</td>
                <td class="num pct-strong">${_fmtPct(a.pct_asistencia)}</td>
                <td class="num">${a.dias_presente ?? 0} / ${a.dias_contables ?? 0}</td>
              </tr>`).join('');
        } catch (e) {
            console.error('[Reportería] error cargando riesgo', e);
            tb.innerHTML = '<tr><td colspan="7" class="empty-row">Error cargando datos</td></tr>';
        }
    }

    async function _onClickSync() {
        const btn = document.getElementById('btn-sync-now');
        if (!btn || btn.classList.contains('is-syncing')) return;
        btn.classList.add('is-syncing');
        try {
            const res = await window.FundApi.syncSheets();
            const sedesOk = (res.sedes || []).filter(s => s.status === 'ok').length;
            const sedesErr = (res.sedes || []).filter(s => s.status === 'error').length;
            const totalAlumnos = (res.sedes || []).reduce((acc, s) => acc + (s.alumnos_creados || 0) + (s.alumnos_actualizados || 0), 0);
            const totalDias = (res.sedes || []).reduce((acc, s) => acc + (s.asistencias_insertadas || 0) + (s.asistencias_actualizadas || 0), 0);
            const tipo = res.status === 'ok' ? 'success' : (res.status === 'partial' ? 'warn' : 'error');
            window.showToast?.(`Sync ${res.status}: ${sedesOk}/${sedesOk + sedesErr} sedes, ${totalAlumnos} alumnos, ${totalDias} días`, tipo);
            await _loadAll();
        } catch (e) {
            console.error('[Reportería] error en sync', e);
            window.showToast?.('Sync falló: ' + (e.message || e), 'error');
        } finally {
            btn.classList.remove('is-syncing');
        }
    }

    function _setKpi(id, val) {
        const el = document.getElementById(id);
        if (el) el.textContent = (val === null || val === undefined) ? '—' : val;
    }

    function _fmtPct(v) {
        if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '—';
        return `${Number(v).toFixed(1)}%`;
    }

    function _labelRiesgo(n) {
        return { alto: 'alto', medio: 'medio', bajo: 'bajo', sin_datos: '(sin datos)' }[n] || n;
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    return { init, onSedeChange };
})();
