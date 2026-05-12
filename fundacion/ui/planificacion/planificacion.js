window.FundPlanificacion = (() => {
    let _ctx = null;
    let _cat = { niveles: [], dominios: [], competencias: [], bloqueTipos: [], clima: [] };
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
    let _currentNivelId = null;
    let _isBorrador = false;     // true cuando el editor muestra plan oficial NO guardado

    // Estado del calendario
    let _view = 'mes';
    let _cursor = new Date();
    let _selected = new Date();
    let _sesionesIdx = {};        // sesiones GUARDADAS (resumen para puntito/contador)
    let _planificacionIdx = {};   // días con PLAN OFICIAL (resumen)
    let _bloquesIdx = {};         // { 'YYYY-MM-DD': { status: 'sesion'|'plan', bloques: [...] } }

    async function init(ctx) {
        _ctx = ctx;
        _selected = new Date(); _selected.setHours(0, 0, 0, 0);
        _cursor = new Date(_selected);
        _initEventos();
        _renderHead();
        await _ensureCatalogos();
        _renderNivelSelector();
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
        document.getElementById('plan-btn-plan-oficial')?.addEventListener('click', _cargarPlanOficial);
        document.getElementById('plan-btn-guardar')?.addEventListener('click', _guardar);
        document.getElementById('plan-nivel')?.addEventListener('change', _onNivelChange);
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
        if (!_currentNivelId) {
            _sesionesIdx = {}; _planificacionIdx = {}; _bloquesIdx = {};
            return;
        }
        try {
            const data = await window.FundApi.getCalendarioBloques(
                _ctx.sede.id, _currentNivelId, _ymd(desde), _ymd(hasta)
            );
            _sesionesIdx = {};
            _planificacionIdx = {};
            _bloquesIdx = {};
            (data.items || []).forEach(d => {
                _bloquesIdx[d.fecha] = d;
                const bloquesTot = (d.bloques || []).length;
                const ejecutados = (d.bloques || []).filter(b => b.se_ejecuto).length;
                if (d.status === 'sesion') {
                    _sesionesIdx[d.fecha] = {
                        fecha: d.fecha,
                        clima_codigo: d.clima_codigo,
                        clima_nombre: d.clima_nombre,
                        clima_color: d.clima_color,
                        bloques_total: bloquesTot,
                        bloques_ejecutados: ejecutados,
                    };
                } else {
                    _planificacionIdx[d.fecha] = { fecha: d.fecha, bloques: bloquesTot };
                }
            });
        } catch (e) {
            console.error('[Planificación] error cargando índice', e);
            _sesionesIdx = {}; _planificacionIdx = {}; _bloquesIdx = {};
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
            const plan = _planificacionIdx[ymd];
            const det = _bloquesIdx[ymd];
            let dot = '';
            if (sesion) {
                const dotColor = sesion.clima_codigo ? _climaColor(sesion.clima_codigo) : '#4facfe';
                dot = `<span class="plan-cal-day-dot is-sesion" style="background:${dotColor}" title="${_esc(sesion.clima_nombre || 'Sesión guardada')}"></span>`;
            } else if (plan) {
                dot = `<span class="plan-cal-day-dot is-plan" title="Plan oficial"></span>`;
            }

            // Mini-eventos del día (top 3 bloques con hora + nombre)
            let eventos = '';
            if (det && det.bloques && det.bloques.length) {
                const statusCls = det.status === 'plan' ? 'is-plan' : 'is-sesion';
                eventos = det.bloques.slice(0, 3).map(b => {
                    const hora = b.hora_inicio ? b.hora_inicio.slice(0, 5) : '';
                    const nombre = b.nombre_actividad || b.bloque_nombre || '';
                    const color = b.bloque_color || '#4facfe';
                    return `<div class="plan-cal-day-evento ${statusCls}" style="border-left-color:${color}" title="${_esc(b.bloque_nombre || '')}${b.subtipo_nombre ? ' · ' + _esc(b.subtipo_nombre) : ''}: ${_esc(nombre)}">
                        ${hora ? `<span class="plan-cal-day-evento-hora">${hora}</span>` : ''}
                        <span class="plan-cal-day-evento-titulo">${_esc(nombre)}</span>
                    </div>`;
                }).join('');
                const extras = det.bloques.length - 3;
                if (extras > 0) eventos += `<div class="plan-cal-day-evento-mas">+${extras} más</div>`;
            }

            html += `
              <div class="${cls.join(' ')}" data-fecha="${ymd}">
                <div class="plan-cal-day-head">
                  <span class="plan-cal-day-num">${d.getDate()}</span>
                  ${dot}
                </div>
                <div class="plan-cal-day-eventos">${eventos}</div>
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

        // Llenar bloques usando el índice precargado (sin requests extra)
        Object.keys(_bloquesIdx).forEach(f => {
            const cont = body.querySelector(`[data-role="bloques-${f}"]`);
            if (!cont) return;
            const det = _bloquesIdx[f];
            const bloques = (det.bloques || []).slice(0, 5);
            if (!bloques.length) { cont.innerHTML = '<div class="plan-cal-semana-empty">—</div>'; return; }
            const statusCls = det.status === 'plan' ? 'is-plan' : 'is-sesion';
            cont.innerHTML = bloques.map(b => {
                const color = b.bloque_color || '#4facfe';
                return `<div class="plan-cal-semana-bloque ${statusCls}" style="border-left-color:${color}">
                  <span class="plan-cal-semana-hora">${b.hora_inicio ? b.hora_inicio.slice(0, 5) : ''}</span>
                  <span class="plan-cal-semana-titulo" title="${_esc(b.bloque_nombre || '')}">${_esc(b.nombre_actividad || b.bloque_nombre || '—')}</span>
                </div>`;
            }).join('');
        });

        body.querySelectorAll('.plan-cal-semana-col').forEach(el => {
            el.addEventListener('click', () => _selectFecha(el.dataset.fecha));
        });
    }

    function _renderDia() {
        const body = document.getElementById('plan-cal-body');
        if (!body) return;
        const ymd = _ymd(_cursor);
        const det = _bloquesIdx[ymd];
        if (!det || !det.bloques?.length) {
            body.innerHTML = '<div class="plan-cal-dia"><div class="plan-cal-dia-empty">Sin bloques planificados ni registrados para este día.</div></div>';
            _selected = new Date(_cursor);
            _refresh();
            return;
        }
        const statusCls = det.status === 'plan' ? 'is-plan' : 'is-sesion';
        const statusLabel = det.status === 'plan'
            ? '<span class="plan-cal-dia-banner is-plan">Mostrando plan oficial — aún no registrado</span>'
            : '<span class="plan-cal-dia-banner is-sesion">Sesión guardada</span>';
        body.innerHTML = `
            <div class="plan-cal-dia ${statusCls}">
                ${statusLabel}
                ${det.bloques.map(b => {
                    const hora = (b.hora_inicio && b.hora_fin) ? `${b.hora_inicio.slice(0,5)}–${b.hora_fin.slice(0,5)}` : (b.hora_inicio ? b.hora_inicio.slice(0,5) : '');
                    const color = b.bloque_color || '#4facfe';
                    const ejec = det.status === 'sesion'
                        ? (b.se_ejecuto ? '<span class="plan-bloque-status is-ok">✓ ejec.</span>' : '<span class="plan-bloque-status is-not-ok">✗ no ejec.</span>')
                        : '';
                    return `
                      <div class="plan-cal-dia-bloque" style="border-left-color:${color}">
                        <span class="plan-cal-dia-bloque-hora">${hora || '—'}</span>
                        <div>
                          <div class="plan-cal-dia-bloque-titulo">${_esc(b.nombre_actividad || b.bloque_nombre || '—')}</div>
                          <div class="plan-cal-dia-bloque-sub">${_esc(b.bloque_nombre || '')}${b.subtipo_nombre ? ' · ' + _esc(b.subtipo_nombre) : ''}</div>
                        </div>
                        <span>${ejec}</span>
                      </div>`;
                }).join('')}
            </div>`;
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
            const [niv, dom, comp, bt, cli] = await Promise.all([
                window.FundApi.getCatNiveles(),
                window.FundApi.getCatDominios(),
                window.FundApi.getCatCompetencias(),
                window.FundApi.getCatBloqueTipos(),
                window.FundApi.getCatClima(),
            ]);
            _cat.niveles = niv.items || [];
            _cat.dominios = dom.items || [];
            _cat.competencias = comp.items || [];
            _cat.bloqueTipos = bt.items || [];
            _cat.clima = cli.items || [];

            _compByDomain = _cat.dominios.map(d => ({
                dominio: d,
                competencias: _cat.competencias.filter(c => c.dominio_id === d.id),
            }));

            // Default al primer nivel (Prekinder-Kinder) si no hay uno seleccionado
            if (_currentNivelId == null && _cat.niveles.length) {
                const saved = localStorage.getItem('fund_plan_nivel_id');
                const found = saved && _cat.niveles.find(n => n.id === Number(saved));
                _currentNivelId = found ? Number(saved) : _cat.niveles[0].id;
            }
            _catLoaded = true;
        } catch (e) {
            console.error('[Planificación] error cargando catálogos', e);
            window.showToast?.('No se pudieron cargar los catálogos pedagógicos', 'error');
        }
    }

    function _renderNivelSelector() {
        const sel = document.getElementById('plan-nivel');
        if (!sel) return;
        sel.innerHTML = _cat.niveles.map(n =>
            `<option value="${n.id}" ${n.id === _currentNivelId ? 'selected' : ''}>${_esc(n.nombre)}</option>`
        ).join('');
    }

    async function _onNivelChange(ev) {
        _currentNivelId = Number(ev.target.value);
        localStorage.setItem('fund_plan_nivel_id', String(_currentNivelId));
        await _renderCalendar();
        await _refresh();
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
        _isBorrador = false;
        _updateEditorHeader();
        if (!_ctx?.sede?.id || !_currentNivelId) {
            _bloques = [];
            _resetMeta();
            _renderBloques();
            return;
        }
        await _ensureCatalogos();
        try {
            // 1) Intentar cargar sesión guardada
            const data = await window.FundApi.getSesionByFecha(_ctx.sede.id, fecha, _currentNivelId);
            _sesionMeta.clima_opcion_id = data.clima_opcion_id || null;
            _sesionMeta.situaciones_relevantes = data.situaciones_relevantes || '';
            _sesionMeta.estrategias_aplicadas = data.estrategias_aplicadas || '';
            _sesionMeta.notas = data.notas || '';
            _bloques = (data.bloques || []).map(_bloqueFromApi);
            _isBorrador = false;
        } catch (e) {
            // 2) Sin sesión guardada → intentar cargar plan oficial como borrador
            _resetMeta();
            _bloques = [];
            try {
                const plan = await window.FundApi.getPlanificacionOficial(_currentNivelId, fecha);
                _bloques = (plan.bloques || []).map((b, i) => _bloqueFromPlan(b, i));
                _isBorrador = true;
            } catch (_) {
                // Sin plan oficial tampoco → editor vacío
                _bloques = [];
                _isBorrador = false;
            }
        }
        _hydrateMeta();
        _renderBloques();
        _updateEditorHeader();
    }

    function _bloqueFromPlan(b, i) {
        return {
            _idx: ++_bloqueSeq,
            _open: i === 0,
            orden: b.orden,
            bloque_tipo_id: b.bloque_tipo_id,
            bloque_subtipo_id: b.bloque_subtipo_id,
            actividad_id: b.actividad_id || null,
            nombre_actividad: b.nombre_actividad || '',
            resultado_aprendizaje: b.resultado_aprendizaje || '',
            hora_inicio: b.hora_inicio || _horaSugerida(i, true),
            hora_fin:    b.hora_fin    || _horaSugerida(i, false),
            se_ejecuto: true,
            motivo_no_ejecucion: '',
            adaptacion: '',
            notas: '',
            competencias: b.competencias_ids || [],
            materiales: b.materiales_sugeridos ? [{
                product_id: null,
                nombre_libre: String(b.materiales_sugeridos).slice(0, 100),
                cantidad_solicitada: '',
                cantidad_usada: '',
            }] : [],
        };
    }

    function _updateEditorHeader() {
        const label = document.getElementById('plan-editor-fecha-label');
        if (label) {
            label.textContent = _selected.toLocaleDateString('es-CL', {
                weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
            });
        }
        const header = document.getElementById('plan-editor-header');
        if (!header) return;
        let badge = header.querySelector('.plan-editor-badge');
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'plan-editor-badge';
            header.querySelector('h4')?.appendChild(badge);
        }
        if (!_bloques.length) {
            badge.textContent = '';
            badge.className = 'plan-editor-badge';
        } else if (_isBorrador) {
            badge.textContent = 'Borrador del plan oficial (no guardado)';
            badge.className = 'plan-editor-badge is-borrador';
        } else {
            badge.textContent = 'Sesión guardada';
            badge.className = 'plan-editor-badge is-guardado';
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
            _open: false,
            orden: b.orden,
            bloque_tipo_id: b.bloque_tipo_id,
            bloque_subtipo_id: b.bloque_subtipo_id,
            actividad_id: b.actividad_id || null,
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
            actividad_id: preset?.actividad_id ?? null,
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

    async function _cargarPlanOficial() {
        if (!_currentNivelId) {
            window.showToast?.('Selecciona un nivel primero', 'warn');
            return;
        }
        if (_bloques.length && !confirm('Esto va a reemplazar los bloques actuales con el plan oficial. ¿Continuar?')) return;
        const fecha = _ymd(_selected);
        try {
            const plan = await window.FundApi.getPlanificacionOficial(_currentNivelId, fecha);
            _bloques = (plan.bloques || []).map((b, i) => ({
                _idx: ++_bloqueSeq,
                _open: i === 0,
                orden: b.orden,
                bloque_tipo_id: b.bloque_tipo_id,
                bloque_subtipo_id: b.bloque_subtipo_id,
                actividad_id: b.actividad_id || null,
                nombre_actividad: b.nombre_actividad || '',
                resultado_aprendizaje: b.resultado_aprendizaje || '',
                hora_inicio: b.hora_inicio || _horaSugerida(i, true),
                hora_fin:    b.hora_fin    || _horaSugerida(i, false),
                se_ejecuto: true,
                motivo_no_ejecucion: '',
                adaptacion: '',
                notas: '',
                competencias: b.competencias_ids || [],
                materiales: b.materiales_sugeridos ? [{
                    product_id: null,
                    nombre_libre: String(b.materiales_sugeridos).slice(0, 100),
                    cantidad_solicitada: '',
                    cantidad_usada: '',
                }] : [],
            }));
            _renderBloques();
            window.showToast?.(`Plan oficial cargado: ${plan.bloques?.length || 0} bloques`, 'success');
        } catch (e) {
            if (e?.status === 404 || /404|sin planificaci/i.test(e?.detail || e?.message || '')) {
                window.showToast?.('No hay plan oficial para este día y nivel', 'warn');
            } else {
                console.error('[Planificación] error cargando plan oficial', e);
                window.showToast?.('Error al cargar plan oficial', 'error');
            }
        }
    }

    function _horaSugerida(i, esInicio) {
        const inicios = ['15:30', '16:00', '17:00', '17:15', '17:45', '18:15'];
        const fines   = ['16:00', '17:00', '17:15', '17:45', '18:15', '18:30'];
        return (esInicio ? inicios : fines)[i] || '';
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

        // Actividad con autocomplete del catálogo
        _bindActividadAutocomplete(node, b, syncSummary);

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

    function _bindActividadAutocomplete(node, b, syncSummary) {
        const input = node.querySelector('[data-role="actividad"]');
        const suggest = node.querySelector('[data-role="actividad-suggest"]');
        const fuenteBadge = node.querySelector('[data-role="actividad-fuente"]');

        input.value = b.nombre_actividad || '';
        _toggleFuenteBadge(fuenteBadge, b.actividad_id);

        let debounce = null;
        let focusedIdx = -1;
        let lastResults = [];

        const close = () => { suggest.hidden = true; focusedIdx = -1; };
        const render = (items) => {
            if (!items.length) {
                suggest.innerHTML = '<div class="plan-actividad-item plan-actividad-empty"><span class="plan-actividad-item-meta">Sin coincidencias en el catálogo</span></div>';
                suggest.hidden = false;
                return;
            }
            suggest.innerHTML = items.map((a, i) => `
                <div class="plan-actividad-item ${i === focusedIdx ? 'is-focused' : ''}" data-idx="${i}">
                    <div class="plan-actividad-item-title">${_esc(a.nombre)}</div>
                    <div class="plan-actividad-item-meta">
                        <span>${_esc(a.bloque_tipo_nombre || '')}</span>
                        ${a.bloque_subtipo_nombre ? `<span>· ${_esc(a.bloque_subtipo_nombre)}</span>` : ''}
                        ${(a.competencias_codigos || []).map(c => `<span class="plan-actividad-item-comp">${_esc(c)}</span>`).join('')}
                        <span class="plan-actividad-item-uso">${a.veces_referenciada}×</span>
                    </div>
                </div>
            `).join('');
            suggest.hidden = false;
            suggest.querySelectorAll('.plan-actividad-item[data-idx]').forEach(el => {
                el.addEventListener('mousedown', (ev) => {
                    ev.preventDefault();  // antes del blur del input
                    _seleccionarActividad(b, lastResults[Number(el.dataset.idx)], input, fuenteBadge, syncSummary);
                    close();
                });
            });
        };

        const search = async () => {
            const q = input.value.trim();
            if (q.length < 2) { close(); return; }
            try {
                const data = await window.FundApi.getCatActividades({
                    q,
                    bloqueTipoId: b.bloque_tipo_id || undefined,
                    bloqueSubtipoId: b.bloque_subtipo_id || undefined,
                    limit: 15,
                });
                lastResults = data.items || [];
                focusedIdx = -1;
                render(lastResults);
            } catch (e) { /* silencioso */ }
        };

        input.addEventListener('input', () => {
            b.nombre_actividad = input.value;
            // Si el usuario cambia el texto, des-vincula del catálogo
            b.actividad_id = null;
            _toggleFuenteBadge(fuenteBadge, null);
            syncSummary();
            clearTimeout(debounce);
            debounce = setTimeout(search, 180);
        });
        input.addEventListener('focus', () => {
            if (input.value.trim().length >= 2) search();
        });
        input.addEventListener('blur', () => {
            setTimeout(close, 150);  // permite click en sugerencia
        });
        input.addEventListener('keydown', (ev) => {
            if (suggest.hidden) return;
            if (ev.key === 'ArrowDown') {
                ev.preventDefault();
                focusedIdx = Math.min(focusedIdx + 1, lastResults.length - 1);
                render(lastResults);
            } else if (ev.key === 'ArrowUp') {
                ev.preventDefault();
                focusedIdx = Math.max(focusedIdx - 1, 0);
                render(lastResults);
            } else if (ev.key === 'Enter' && focusedIdx >= 0) {
                ev.preventDefault();
                _seleccionarActividad(b, lastResults[focusedIdx], input, fuenteBadge, syncSummary);
                close();
            } else if (ev.key === 'Escape') {
                close();
            }
        });
    }

    function _seleccionarActividad(b, act, input, fuenteBadge, syncSummary) {
        if (!act) return;
        b.actividad_id = act.id;
        b.nombre_actividad = act.nombre;
        input.value = act.nombre;
        // Si la actividad trae competencias, las sumamos (no reemplazamos lo que ya hay)
        const compIds = act.competencias_ids || [];
        for (const id of compIds) {
            if (!b.competencias.includes(id)) b.competencias.push(id);
        }
        // Si el resultado de aprendizaje está vacío y la actividad tiene uno, lo prellenamos
        if (!b.resultado_aprendizaje && act.resultado_aprendizaje) {
            b.resultado_aprendizaje = act.resultado_aprendizaje;
            const ta = document.querySelector(`.plan-bloque[data-bloque-idx="${b._idx}"] [data-role="resultado"]`);
            if (ta) ta.value = act.resultado_aprendizaje;
        }
        _toggleFuenteBadge(fuenteBadge, b.actividad_id);
        syncSummary();
        // Re-renderizar competencias visualmente
        const node = document.querySelector(`.plan-bloque[data-bloque-idx="${b._idx}"]`);
        if (node) {
            const tipo = _cat.bloqueTipos.find(t => t.id === b.bloque_tipo_id);
            _refreshCompetencias(node, tipo, b);
        }
    }

    function _toggleFuenteBadge(badge, actividadId) {
        if (!badge) return;
        if (actividadId) {
            badge.textContent = '✓ del catálogo oficial';
            badge.classList.add('is-visible');
        } else {
            badge.textContent = '';
            badge.classList.remove('is-visible');
        }
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
            nivel_id: _currentNivelId,
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
                actividad_id: b.actividad_id || null,
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
