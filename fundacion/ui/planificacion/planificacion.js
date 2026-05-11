window.FundPlanificacion = (() => {
    let _ctx = null;
    let _cat = { dominios: [], competencias: [], bloqueTipos: [], clima: [] };
    let _compByDomain = [];
    let _bloques = [];
    let _sesionMeta = {
        clima_opcion_id: null,
        situaciones_relevantes: '',
        estrategias_aplicadas: '',
        notas: '',
    };
    let _catLoaded = false;
    let _saving = false;
    let _bloqueSeq = 0;

    // Estado del calendario
    let _view = 'mes';            // 'mes' | 'semana' | 'dia'
    let _cursor = new Date();     // fecha "ancla" del período visible
    let _selected = new Date();   // día seleccionado para el editor
    let _sesionesIdx = {};        // { 'YYYY-MM-DD': { bloques_total, bloques_ejecutados, clima_codigo, clima_nombre } }

    async function init(ctx) {
        _ctx = ctx;
        _selected = new Date(); _selected.setHours(0, 0, 0, 0);
        _cursor = new Date(_selected);
        _initEventos();
        _renderHead();
        await _ensureCatalogos();
        _renderClimaGrid();
        await _renderCalendar();
        await _refresh();
    }

    async function onSedeChange(sede) {
        _ctx = { ..._ctx, sede };
        _renderHead();
        await _renderCalendar();
        await _refresh();
    }

    function _initEventos() {
        document.getElementById('plan-btn-add-bloque')?.addEventListener('click', () => _agregarBloque({ open: true }));
        document.getElementById('plan-btn-sugerir')?.addEventListener('click', _cargarPlantillaDelDia);
        document.getElementById('plan-btn-guardar')?.addEventListener('click', _guardar);
        document.getElementById('plan-btn-collapse-all')?.addEventListener('click', () => _toggleAll(false));
        document.getElementById('plan-btn-expand-all')?.addEventListener('click', () => _toggleAll(true));

        // Calendario
        document.getElementById('plan-cal-prev')?.addEventListener('click', () => _nav(-1));
        document.getElementById('plan-cal-next')?.addEventListener('click', () => _nav(+1));
        document.getElementById('plan-cal-today')?.addEventListener('click', _goToday);
        document.querySelectorAll('.plan-cal-view-btn').forEach(btn => {
            btn.addEventListener('click', () => _setView(btn.dataset.view));
        });

        ['plan-situaciones', 'plan-estrategias', 'plan-notas'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('input', () => {
                _sesionMeta.situaciones_relevantes = document.getElementById('plan-situaciones')?.value || '';
                _sesionMeta.estrategias_aplicadas = document.getElementById('plan-estrategias')?.value || '';
                _sesionMeta.notas = document.getElementById('plan-notas')?.value || '';
            });
        });
    }

    function _ymd(d) {
        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        const dd = String(d.getDate()).padStart(2, '0');
        return `${yyyy}-${mm}-${dd}`;
    }

    function _sameDay(a, b) {
        return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
    }

    function _rangoVisible() {
        // Devuelve {desde, hasta} del período visible según _view
        const d = new Date(_cursor);
        if (_view === 'mes') {
            const desde = new Date(d.getFullYear(), d.getMonth(), 1);
            const hasta = new Date(d.getFullYear(), d.getMonth() + 1, 0);
            return { desde, hasta };
        }
        if (_view === 'semana') {
            const dow = d.getDay() === 0 ? 6 : d.getDay() - 1;  // lunes = 0
            const desde = new Date(d); desde.setDate(d.getDate() - dow);
            const hasta = new Date(desde); hasta.setDate(desde.getDate() + 6);
            return { desde, hasta };
        }
        return { desde: new Date(d), hasta: new Date(d) };
    }

    async function _renderCalendar() {
        _updateNavTitle();
        if (!_ctx?.sede?.id) {
            const body = document.getElementById('plan-cal-body');
            if (body) body.innerHTML = '';
            return;
        }
        await _loadSesionesIdx();
        if (_view === 'mes') _renderMes();
        else if (_view === 'semana') _renderSemana();
        else _renderDia();
    }

    function _updateNavTitle() {
        const t = document.getElementById('plan-cal-title');
        if (!t) return;
        const fmtMes = (d) => d.toLocaleDateString('es-CL', { month: 'long', year: 'numeric' });
        const fmtDia = (d) => d.toLocaleDateString('es-CL', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
        if (_view === 'mes') {
            t.textContent = fmtMes(_cursor);
        } else if (_view === 'semana') {
            const { desde, hasta } = _rangoVisible();
            const di = desde.toLocaleDateString('es-CL', { day: 'numeric', month: 'short' });
            const dh = hasta.toLocaleDateString('es-CL', { day: 'numeric', month: 'short', year: 'numeric' });
            t.textContent = `${di} – ${dh}`;
        } else {
            t.textContent = fmtDia(_cursor);
        }
    }

    async function _loadSesionesIdx() {
        const { desde, hasta } = _rangoVisible();
        try {
            const data = await window.FundApi.listSesiones(_ctx.sede.id, _ymd(desde), _ymd(hasta));
            _sesionesIdx = {};
            (data.items || []).forEach(s => {
                _sesionesIdx[s.fecha] = s;
            });
        } catch (e) {
            console.error('[Planificación] error cargando índice de sesiones', e);
            _sesionesIdx = {};
        }
    }

    function _renderMes() {
        const body = document.getElementById('plan-cal-body');
        if (!body) return;
        const y = _cursor.getFullYear(), m = _cursor.getMonth();
        const primero = new Date(y, m, 1);
        const ultimo = new Date(y, m + 1, 0);
        const dowPrimero = primero.getDay() === 0 ? 6 : primero.getDay() - 1;
        const inicio = new Date(primero); inicio.setDate(1 - dowPrimero);
        const cantSem = Math.ceil((dowPrimero + ultimo.getDate()) / 7);
        const totalCells = cantSem * 7;

        const dows = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
        const hoy = new Date(); hoy.setHours(0, 0, 0, 0);

        let html = '<div class="plan-cal-mes">';
        html += '<div class="plan-cal-mes-dow">' + dows.map(d => `<div>${d}</div>`).join('') + '</div>';
        html += '<div class="plan-cal-mes-grid">';
        for (let i = 0; i < totalCells; i++) {
            const d = new Date(inicio); d.setDate(inicio.getDate() + i);
            const ymd = _ymd(d);
            const sesion = _sesionesIdx[ymd];
            const isOut = d.getMonth() !== m;
            const isToday = _sameDay(d, hoy);
            const isSelected = _sameDay(d, _selected);
            const cls = ['plan-cal-day'];
            if (isOut) cls.push('is-out');
            if (isToday) cls.push('is-today');
            if (isSelected) cls.push('is-selected');
            const dotColor = sesion?.clima_codigo ? _climaColor(sesion.clima_codigo) : null;
            const dot = sesion ? `<span class="plan-cal-day-dot" style="background:${dotColor || '#4facfe'}" title="${_esc(sesion.clima_nombre || 'Sesión registrada')}"></span>` : '';
            const count = sesion?.bloques_total ? `<span class="plan-cal-day-count">${sesion.bloques_ejecutados}/${sesion.bloques_total}</span>` : '';
            html += `
              <div class="${cls.join(' ')}" data-fecha="${ymd}">
                <div class="plan-cal-day-head">
                  <span class="plan-cal-day-num">${d.getDate()}</span>
                </div>
                <div class="plan-cal-day-marks">${dot}${count}</div>
              </div>`;
        }
        html += '</div></div>';
        body.innerHTML = html;
        body.querySelectorAll('.plan-cal-day').forEach(el => {
            el.addEventListener('click', () => _selectFecha(el.dataset.fecha));
        });
    }

    function _renderSemana() {
        const body = document.getElementById('plan-cal-body');
        if (!body) return;
        const { desde } = _rangoVisible();
        const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
        const dows = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
        let html = '<div class="plan-cal-semana">';
        for (let i = 0; i < 7; i++) {
            const d = new Date(desde); d.setDate(desde.getDate() + i);
            const ymd = _ymd(d);
            const isToday = _sameDay(d, hoy);
            const isSelected = _sameDay(d, _selected);
            const cls = ['plan-cal-semana-col'];
            if (isToday) cls.push('is-today');
            if (isSelected) cls.push('is-selected');
            html += `
              <div class="${cls.join(' ')}" data-fecha="${ymd}">
                <div class="plan-cal-semana-head">${dows[i]} ${d.getDate()}</div>
                <div class="plan-cal-semana-body" data-role="bloques-${ymd}"></div>
              </div>`;
        }
        html += '</div>';
        body.innerHTML = html;

        // Cargar bloques en paralelo para cada día con sesión
        const fechas = Object.keys(_sesionesIdx);
        for (const f of fechas) {
            const cont = body.querySelector(`[data-role="bloques-${f}"]`);
            if (!cont) continue;
            window.FundApi.getSesionByFecha(_ctx.sede.id, f).then(data => {
                const bloques = (data.bloques || []).slice(0, 4);
                if (!bloques.length) { cont.innerHTML = '<div class="plan-cal-semana-empty">—</div>'; return; }
                cont.innerHTML = bloques.map(b => `
                    <div class="plan-cal-semana-bloque">
                      <span class="plan-cal-semana-hora">${b.hora_inicio ? b.hora_inicio.slice(0, 5) : ''}</span>
                      <span class="plan-cal-semana-titulo">${_esc(b.nombre_actividad || b.bloque_tipo_nombre || '—')}</span>
                    </div>
                `).join('');
            }).catch(() => { cont.innerHTML = '<div class="plan-cal-semana-empty">—</div>'; });
        }

        body.querySelectorAll('.plan-cal-semana-col').forEach(el => {
            el.addEventListener('click', () => _selectFecha(el.dataset.fecha));
        });
    }

    function _renderDia() {
        const body = document.getElementById('plan-cal-body');
        if (!body) return;
        const ymd = _ymd(_cursor);
        body.innerHTML = '<div class="plan-cal-dia" id="plan-cal-dia-cont"><div class="plan-cal-dia-empty">Cargando…</div></div>';
        const cont = body.querySelector('#plan-cal-dia-cont');
        window.FundApi.getSesionByFecha(_ctx.sede.id, ymd).then(data => {
            const bloques = data.bloques || [];
            if (!bloques.length) { cont.innerHTML = '<div class="plan-cal-dia-empty">Sin bloques registrados para este día.</div>'; return; }
            cont.innerHTML = bloques.map(b => {
                const hora = (b.hora_inicio && b.hora_fin) ? `${b.hora_inicio.slice(0,5)}–${b.hora_fin.slice(0,5)}` : '';
                return `
                  <div class="plan-cal-dia-bloque">
                    <span class="plan-cal-dia-bloque-hora">${hora || '—'}</span>
                    <div>
                      <div class="plan-cal-dia-bloque-titulo">${_esc(b.nombre_actividad || b.bloque_tipo_nombre || '—')}</div>
                      <div class="plan-cal-dia-bloque-sub">${_esc(b.bloque_tipo_nombre)}${b.bloque_subtipo_nombre ? ' · ' + _esc(b.bloque_subtipo_nombre) : ''}</div>
                    </div>
                    <span>${b.se_ejecuto ? '<span class="plan-bloque-status is-ok">✓</span>' : '<span class="plan-bloque-status is-not-ok">✗</span>'}</span>
                  </div>`;
            }).join('');
        }).catch(() => { cont.innerHTML = '<div class="plan-cal-dia-empty">Sin bloques registrados para este día.</div>'; });
        // Asegurar que _selected coincida con cursor en vista día
        _selected = new Date(_cursor);
        _refresh();
    }

    function _climaColor(codigo) {
        const c = (_cat.clima || []).find(x => x.codigo === codigo);
        return c?.color || '#4facfe';
    }

    function _setView(view) {
        if (_view === view) return;
        _view = view;
        document.querySelectorAll('.plan-cal-view-btn').forEach(b => {
            b.classList.toggle('is-active', b.dataset.view === view);
        });
        _renderCalendar();
    }

    function _nav(delta) {
        const d = new Date(_cursor);
        if (_view === 'mes') d.setMonth(d.getMonth() + delta);
        else if (_view === 'semana') d.setDate(d.getDate() + 7 * delta);
        else d.setDate(d.getDate() + delta);
        _cursor = d;
        _renderCalendar();
    }

    function _goToday() {
        _cursor = new Date(); _cursor.setHours(0, 0, 0, 0);
        _selected = new Date(_cursor);
        _renderCalendar();
        _refresh();
    }

    function _selectFecha(ymd) {
        const [y, m, d] = ymd.split('-').map(Number);
        _selected = new Date(y, m - 1, d);
        if (_view === 'mes') {
            // marcar el día seleccionado sin recargar todo
            document.querySelectorAll('.plan-cal-day').forEach(el => {
                el.classList.toggle('is-selected', el.dataset.fecha === ymd);
            });
        } else if (_view === 'semana') {
            document.querySelectorAll('.plan-cal-semana-col').forEach(el => {
                el.classList.toggle('is-selected', el.dataset.fecha === ymd);
            });
        }
        _refresh();
    }

    function _renderHead() {
        const t = document.getElementById('plan-sede-title');
        const s = document.getElementById('plan-sede-subtitle');
        const shell = document.getElementById('plan-shell');
        const needs = document.getElementById('plan-needs-sede');
        if (!_ctx?.sede?.id) {
            if (t) t.textContent = 'Planificación — selecciona una sede';
            if (s) s.textContent = '';
            if (shell) shell.style.display = 'none';
            if (needs) needs.style.display = '';
            return;
        }
        if (t) t.textContent = `Planificación — ${_ctx.sede.nombre}`;
        if (s) s.textContent = 'Registro diario de bloques y clima';
        if (shell) shell.style.display = '';
        if (needs) needs.style.display = 'none';
    }

    async function _ensureCatalogos() {
        if (_catLoaded) return;
        try {
            const [dom, comp, bt, cli] = await Promise.all([
                window.FundApi.getCatDominios(),
                window.FundApi.getCatCompetencias(),
                window.FundApi.getCatBloqueTipos(),
                window.FundApi.getCatClima(),
            ]);
            _cat.dominios = dom.items || [];
            _cat.competencias = comp.items || [];
            _cat.bloqueTipos = bt.items || [];
            _cat.clima = cli.items || [];

            // agrupar competencias por dominio en el orden correcto
            _compByDomain = _cat.dominios.map(d => ({
                dominio: d,
                competencias: _cat.competencias.filter(c => c.dominio_id === d.id),
            }));
            _catLoaded = true;
        } catch (e) {
            console.error('[Planificación] error cargando catálogos', e);
            window.showToast?.('No se pudieron cargar los catálogos pedagógicos', 'error');
        }
    }

    function _renderClimaGrid() {
        const grid = document.getElementById('plan-clima-grid');
        if (!grid) return;
        grid.innerHTML = _cat.clima.map(c => `
            <button type="button" class="plan-clima-opt" data-clima-id="${c.id}">
                <i class="fa-solid ${_esc(c.icono || 'fa-circle')}" style="color:${_esc(c.color || '#888')}"></i>
                <span>${_esc(c.nombre)}</span>
            </button>
        `).join('');
        grid.querySelectorAll('.plan-clima-opt').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = Number(btn.dataset.climaId);
                _sesionMeta.clima_opcion_id = (_sesionMeta.clima_opcion_id === id) ? null : id;
                _marcarClimaSeleccionado();
            });
        });
    }

    function _marcarClimaSeleccionado() {
        document.querySelectorAll('.plan-clima-opt').forEach(b => {
            const id = Number(b.dataset.climaId);
            b.classList.toggle('is-selected', id === _sesionMeta.clima_opcion_id);
        });
    }

    async function _refresh() {
        const fecha = _ymd(_selected);
        _updateEditorHeader();
        if (!_ctx?.sede?.id) {
            _bloques = [];
            _resetMeta();
            _renderBloques();
            return;
        }
        await _ensureCatalogos();
        try {
            const data = await window.FundApi.getSesionByFecha(_ctx.sede.id, fecha);
            _sesionMeta.clima_opcion_id = data.clima_opcion_id || null;
            _sesionMeta.situaciones_relevantes = data.situaciones_relevantes || '';
            _sesionMeta.estrategias_aplicadas = data.estrategias_aplicadas || '';
            _sesionMeta.notas = data.notas || '';
            _bloques = (data.bloques || []).map(_bloqueFromApi);
        } catch (e) {
            _bloques = [];
            _resetMeta();
        }
        _hydrateMeta();
        _renderBloques();
    }

    function _updateEditorHeader() {
        const label = document.getElementById('plan-editor-fecha-label');
        if (label) {
            label.textContent = _selected.toLocaleDateString('es-CL', {
                weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
            });
        }
    }

    function _resetMeta() {
        _sesionMeta = { clima_opcion_id: null, situaciones_relevantes: '', estrategias_aplicadas: '', notas: '' };
    }

    function _hydrateMeta() {
        const sit = document.getElementById('plan-situaciones');
        const est = document.getElementById('plan-estrategias');
        const not = document.getElementById('plan-notas');
        if (sit) sit.value = _sesionMeta.situaciones_relevantes || '';
        if (est) est.value = _sesionMeta.estrategias_aplicadas || '';
        if (not) not.value = _sesionMeta.notas || '';
        _marcarClimaSeleccionado();
    }

    function _bloqueFromApi(b) {
        return {
            _idx: ++_bloqueSeq,
            _open: false,  // los bloques existentes arrancan colapsados (legibilidad)
            orden: b.orden,
            bloque_tipo_id: b.bloque_tipo_id,
            bloque_subtipo_id: b.bloque_subtipo_id,
            nombre_actividad: b.nombre_actividad || '',
            resultado_aprendizaje: b.resultado_aprendizaje || '',
            hora_inicio: b.hora_inicio || '',
            hora_fin: b.hora_fin || '',
            se_ejecuto: b.se_ejecuto !== false,
            motivo_no_ejecucion: b.motivo_no_ejecucion || '',
            adaptacion: b.adaptacion || '',
            notas: b.notas || '',
            competencias: (b.competencias || []).map(c => c.id),
            materiales: (b.materiales || []).map(m => ({
                product_id: m.product_id || null,
                nombre_libre: m.nombre_libre || m.product_name || '',
                cantidad_solicitada: m.cantidad_solicitada ?? '',
                cantidad_usada: m.cantidad_usada ?? '',
            })),
        };
    }

    function _agregarBloque(preset) {
        const tipoDefault = _cat.bloqueTipos[0];
        _bloques.push({
            _idx: ++_bloqueSeq,
            _open: preset?.open !== false,
            orden: _bloques.length + 1,
            bloque_tipo_id: preset?.bloque_tipo_id ?? (tipoDefault?.id || null),
            bloque_subtipo_id: preset?.bloque_subtipo_id ?? null,
            nombre_actividad: preset?.nombre_actividad ?? '',
            resultado_aprendizaje: '',
            hora_inicio: preset?.hora_inicio ?? '',
            hora_fin: preset?.hora_fin ?? '',
            se_ejecuto: true,
            motivo_no_ejecucion: '',
            adaptacion: '',
            notas: '',
            competencias: [],
            materiales: [],
        });
        _renderBloques();
    }

    function _cargarPlantillaDelDia() {
        if (_bloques.length && !confirm('Esto va a reemplazar los bloques actuales por la plantilla estándar. ¿Continuar?')) return;
        _bloques = [];
        const tipo = (codigo) => _cat.bloqueTipos.find(t => t.codigo === codigo);
        const subtipo = (tipoCodigo, subCodigo) => {
            const t = tipo(tipoCodigo);
            return t?.subtipos?.find(s => s.codigo === subCodigo)?.id || null;
        };
        const plantilla = [
            { tipo: 'juegos_para_crecer',   sub: 'psicomotor', ini: '15:30', fin: '16:00' },
            { tipo: 'taller_socioemocional',sub: null,         ini: '16:00', fin: '17:00' },
            { tipo: 'colacion',             sub: null,         ini: '17:00', fin: '17:15' },
            { tipo: 'glifing',              sub: null,         ini: '17:15', fin: '17:45' },
            { tipo: 'juegos_para_crecer',   sub: 'sensorial',  ini: '17:45', fin: '18:15' },
            { tipo: 'juego_libre',          sub: null,         ini: '18:15', fin: '18:30' },
        ];
        plantilla.forEach((p, i) => {
            const t = tipo(p.tipo);
            _agregarBloque({
                bloque_tipo_id: t?.id || null,
                bloque_subtipo_id: subtipo(p.tipo, p.sub),
                hora_inicio: p.ini,
                hora_fin: p.fin,
                open: i === 0,  // solo el primero abierto
            });
        });
    }

    function _toggleAll(open) {
        _bloques.forEach(b => b._open = open);
        document.querySelectorAll('.plan-bloque').forEach(d => d.open = open);
    }

    function _renderBloques() {
        const cont = document.getElementById('plan-bloques-lista');
        if (!cont) return;
        if (!_bloques.length) {
            cont.innerHTML = '<p class="plan-bloques-empty">Sin bloques cargados. Usa "Plantilla del día" o "Agregar bloque".</p>';
            return;
        }
        cont.innerHTML = '';
        for (const b of _bloques) cont.appendChild(_buildBloqueEl(b));
    }

    function _buildBloqueEl(b) {
        const tpl = document.getElementById('tpl-bloque');
        const node = tpl.content.firstElementChild.cloneNode(true);
        node.dataset.bloqueIdx = b._idx;
        node.open = !!b._open;
        node.addEventListener('toggle', () => { b._open = node.open; });

        // Summary
        const sumOrden = node.querySelector('[data-role="orden-label"]');
        if (sumOrden) sumOrden.textContent = b.orden;

        const sumTipo = node.querySelector('[data-role="tipo-label"]');
        const sumSub  = node.querySelector('[data-role="subtipo-label"]');
        const sumHora = node.querySelector('[data-role="hora-label"]');
        const sumAct  = node.querySelector('[data-role="actividad-label"]');
        const sumStat = node.querySelector('[data-role="status-label"]');

        function syncSummary() {
            const tipo = _cat.bloqueTipos.find(t => t.id === b.bloque_tipo_id);
            const sub = (tipo?.subtipos || []).find(s => s.id === b.bloque_subtipo_id);
            if (sumTipo) sumTipo.textContent = tipo?.nombre || '—';
            if (sumSub)  sumSub.textContent  = sub?.nombre || '';
            if (sumHora) sumHora.textContent = (b.hora_inicio && b.hora_fin) ? `${b.hora_inicio}–${b.hora_fin}` : '';
            if (sumAct)  sumAct.textContent  = b.nombre_actividad ? `· ${b.nombre_actividad}` : '';
            if (sumStat) {
                if (b.se_ejecuto) {
                    sumStat.textContent = '✓ ejecutado';
                    sumStat.className = 'plan-bloque-status is-ok';
                } else {
                    sumStat.textContent = '✗ no ejec.';
                    sumStat.className = 'plan-bloque-status is-not-ok';
                }
            }
        }

        // Selector de tipo
        const selTipo = node.querySelector('[data-role="tipo"]');
        selTipo.innerHTML = _cat.bloqueTipos.map(t =>
            `<option value="${t.id}" ${t.id === b.bloque_tipo_id ? 'selected' : ''}>${_esc(t.nombre)}</option>`
        ).join('');
        selTipo.addEventListener('change', () => {
            b.bloque_tipo_id = Number(selTipo.value);
            b.bloque_subtipo_id = null;
            const tipo = _cat.bloqueTipos.find(t => t.id === b.bloque_tipo_id);
            _refreshSubtipo(node, tipo, b);
            _refreshCompetencias(node, tipo, b);
            syncSummary();
        });

        // Subtipo
        const tipoActual = _cat.bloqueTipos.find(t => t.id === b.bloque_tipo_id);
        _refreshSubtipo(node, tipoActual, b, syncSummary);

        // Horas
        const inIni = node.querySelector('[data-role="hora-inicio"]');
        const inFin = node.querySelector('[data-role="hora-fin"]');
        inIni.value = b.hora_inicio || '';
        inFin.value = b.hora_fin || '';
        inIni.addEventListener('change', e => { b.hora_inicio = e.target.value; syncSummary(); });
        inFin.addEventListener('change', e => { b.hora_fin = e.target.value; syncSummary(); });

        // Ejecutado
        const cbEjec = node.querySelector('[data-role="se-ejecuto"]');
        cbEjec.checked = b.se_ejecuto;
        const noEjecRow = node.querySelector('[data-role="no-ejec-row"]');
        noEjecRow.style.display = b.se_ejecuto ? 'none' : '';
        cbEjec.addEventListener('change', () => {
            b.se_ejecuto = cbEjec.checked;
            noEjecRow.style.display = b.se_ejecuto ? 'none' : '';
            syncSummary();
        });
        const inputMotivo = node.querySelector('[data-role="motivo"]');
        inputMotivo.value = b.motivo_no_ejecucion || '';
        inputMotivo.addEventListener('input', e => b.motivo_no_ejecucion = e.target.value);

        // Eliminar bloque (stop propagation para no toggle el details)
        const btnDel = node.querySelector('[data-role="del"]');
        btnDel.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            if (!confirm('¿Eliminar este bloque?')) return;
            _bloques = _bloques.filter(x => x._idx !== b._idx);
            _bloques.forEach((x, i) => x.orden = i + 1);
            _renderBloques();
        });

        // Actividad
        const inputAct = node.querySelector('[data-role="actividad"]');
        inputAct.value = b.nombre_actividad || '';
        inputAct.addEventListener('input', e => { b.nombre_actividad = e.target.value; syncSummary(); });

        // Resultado de aprendizaje
        const inputRes = node.querySelector('[data-role="resultado"]');
        inputRes.value = b.resultado_aprendizaje || '';
        inputRes.addEventListener('input', e => b.resultado_aprendizaje = e.target.value);

        // Adaptación
        const inputAdapt = node.querySelector('[data-role="adaptacion"]');
        inputAdapt.value = b.adaptacion || '';
        inputAdapt.addEventListener('input', e => b.adaptacion = e.target.value);

        // Competencias (agrupadas por dominio)
        _refreshCompetencias(node, tipoActual, b);

        // Materiales
        _refreshMateriales(node, b);
        node.querySelector('[data-role="add-material"]').addEventListener('click', () => {
            b.materiales.push({ product_id: null, nombre_libre: '', cantidad_solicitada: '', cantidad_usada: '' });
            _refreshMateriales(node, b);
        });

        syncSummary();
        return node;
    }

    function _refreshSubtipo(node, tipo, b, onChange) {
        const ctrl = node.querySelector('[data-role="subtipo-control"]');
        const sel = node.querySelector('[data-role="subtipo"]');
        if (!tipo || !tipo.requiere_subtipo || !tipo.subtipos?.length) {
            if (ctrl) ctrl.style.display = 'none';
            sel.innerHTML = '';
            b.bloque_subtipo_id = null;
            return;
        }
        if (ctrl) ctrl.style.display = '';
        sel.innerHTML = `<option value="">— Subtipo —</option>` + tipo.subtipos.map(s =>
            `<option value="${s.id}" ${s.id === b.bloque_subtipo_id ? 'selected' : ''}>${_esc(s.nombre)}</option>`
        ).join('');
        sel.onchange = () => {
            b.bloque_subtipo_id = sel.value ? Number(sel.value) : null;
            if (onChange) onChange();
        };
    }

    function _refreshCompetencias(node, tipo, b) {
        const row = node.querySelector('[data-role="competencias-row"]');
        const cont = node.querySelector('[data-role="competencias"]');
        const counter = node.querySelector('[data-role="comp-counter"]');
        const resultadoRow = node.querySelector('[data-role="resultado-row"]');
        if (!tipo || !tipo.permite_competencias) {
            row.style.display = 'none';
            resultadoRow.style.display = 'none';
            b.competencias = [];
            return;
        }
        row.style.display = '';
        resultadoRow.style.display = '';

        // render por dominio
        cont.innerHTML = _compByDomain.map(grp => {
            const dotColor = _esc(grp.dominio.color || '#888');
            const chips = grp.competencias.map(c => {
                const isSel = b.competencias.includes(c.id);
                return `
                  <label class="plan-comp-chip ${isSel ? 'is-selected' : ''}"
                         title="${_esc(c.descripcion)}" data-comp-id="${c.id}">
                    <input type="checkbox" ${isSel ? 'checked' : ''} />
                    <span class="plan-comp-chip-code" style="color:${dotColor}">${_esc(c.codigo)}</span>
                  </label>
                `;
            }).join('');
            return `
              <div class="plan-comp-domain">
                <div class="plan-comp-domain-head">
                  <span class="plan-comp-domain-dot" style="background:${dotColor}"></span>
                  <span class="plan-comp-domain-name">${_esc(grp.dominio.nombre)}</span>
                  <span class="plan-comp-domain-count">${grp.competencias.length}</span>
                </div>
                <div class="plan-comp-chips">${chips}</div>
              </div>
            `;
        }).join('');

        cont.querySelectorAll('.plan-comp-chip').forEach(el => {
            el.addEventListener('click', (ev) => {
                ev.preventDefault();
                const id = Number(el.dataset.compId);
                const cb = el.querySelector('input[type="checkbox"]');
                cb.checked = !cb.checked;
                el.classList.toggle('is-selected', cb.checked);
                if (cb.checked) {
                    if (!b.competencias.includes(id)) b.competencias.push(id);
                } else {
                    b.competencias = b.competencias.filter(x => x !== id);
                }
                _updateCounter(counter, b.competencias.length);
            });
        });
        _updateCounter(counter, b.competencias.length);
    }

    function _updateCounter(el, n) {
        if (!el) return;
        el.textContent = n > 0 ? `${n} seleccionada${n > 1 ? 's' : ''}` : 'Ninguna seleccionada';
    }

    function _refreshMateriales(node, b) {
        const cont = node.querySelector('[data-role="materiales"]');
        cont.innerHTML = '';
        const tpl = document.getElementById('tpl-material');
        b.materiales.forEach((m, idx) => {
            const row = tpl.content.firstElementChild.cloneNode(true);
            const inNom = row.querySelector('[data-role="nombre"]');
            const inSol = row.querySelector('[data-role="qsol"]');
            const inUsa = row.querySelector('[data-role="qusa"]');
            inNom.value = m.nombre_libre || '';
            inSol.value = m.cantidad_solicitada ?? '';
            inUsa.value = m.cantidad_usada ?? '';
            inNom.addEventListener('input', e => m.nombre_libre = e.target.value);
            inSol.addEventListener('input', e => m.cantidad_solicitada = e.target.value);
            inUsa.addEventListener('input', e => m.cantidad_usada = e.target.value);
            row.querySelector('[data-role="del-mat"]').addEventListener('click', () => {
                b.materiales.splice(idx, 1);
                _refreshMateriales(node, b);
            });
            cont.appendChild(row);
        });
    }

    async function _guardar() {
        if (_saving) return;
        const fecha = _ymd(_selected);
        if (!_ctx?.sede?.id || !fecha) {
            window.showToast?.('Selecciona sede y fecha primero', 'warn');
            return;
        }
        for (const b of _bloques) {
            if (!b.bloque_tipo_id) {
                window.showToast?.(`Bloque #${b.orden} sin tipo`, 'error');
                return;
            }
            const tipo = _cat.bloqueTipos.find(t => t.id === b.bloque_tipo_id);
            if (tipo?.requiere_subtipo && !b.bloque_subtipo_id) {
                window.showToast?.(`Bloque "${tipo.nombre}" (#${b.orden}) necesita un subtipo`, 'error');
                return;
            }
        }

        const payload = {
            sede_id: _ctx.sede.id,
            fecha,
            clima_opcion_id: _sesionMeta.clima_opcion_id || null,
            situaciones_relevantes: _sesionMeta.situaciones_relevantes || null,
            estrategias_aplicadas: _sesionMeta.estrategias_aplicadas || null,
            notas: _sesionMeta.notas || null,
            cerrado: false,
            bloques: _bloques.map(b => ({
                orden: b.orden,
                bloque_tipo_id: b.bloque_tipo_id,
                bloque_subtipo_id: b.bloque_subtipo_id || null,
                nombre_actividad: b.nombre_actividad || null,
                resultado_aprendizaje: b.resultado_aprendizaje || null,
                hora_inicio: b.hora_inicio || null,
                hora_fin: b.hora_fin || null,
                se_ejecuto: !!b.se_ejecuto,
                motivo_no_ejecucion: b.motivo_no_ejecucion || null,
                adaptacion: b.adaptacion || null,
                notas: b.notas || null,
                competencias: b.competencias || [],
                materiales: (b.materiales || []).map(m => ({
                    product_id: m.product_id || null,
                    nombre_libre: m.nombre_libre || null,
                    cantidad_solicitada: m.cantidad_solicitada === '' ? null : Number(m.cantidad_solicitada),
                    cantidad_usada: m.cantidad_usada === '' ? null : Number(m.cantidad_usada),
                })).filter(m => m.product_id || (m.nombre_libre && m.nombre_libre.trim())),
            })),
        };

        _saving = true;
        const btn = document.getElementById('plan-btn-guardar');
        if (btn) { btn.disabled = true; }
        try {
            await window.FundApi.upsertSesion(payload);
            window.showToast?.('Sesión guardada', 'success');
            await _refresh();
            await _renderCalendar();  // refrescar marcas del calendario
        } catch (e) {
            console.error('[Planificación] error guardando', e);
            window.showToast?.('Error al guardar: ' + (e?.detail || e?.message || e), 'error');
        } finally {
            _saving = false;
            if (btn) { btn.disabled = false; }
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    return { init, onSedeChange };
})();
