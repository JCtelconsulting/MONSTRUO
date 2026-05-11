window.FundPlanificacion = (() => {
    let _ctx = null;
    let _cat = { dominios: [], competencias: [], bloqueTipos: [], clima: [] };
    let _bloques = [];       // estado en memoria de la sesión actual
    let _sesionMeta = {      // metadata de cabecera
        clima_opcion_id: null,
        situaciones_relevantes: '',
        estrategias_aplicadas: '',
        notas: '',
    };
    let _catLoaded = false;
    let _saving = false;
    let _bloqueSeq = 0;      // contador interno para data-bloque-idx

    async function init(ctx) {
        _ctx = ctx;
        _initEventos();
        _setFechaHoy();
        _renderHead();
        await _ensureCatalogos();
        _renderClimaGrid();
        await _refresh();
    }

    async function onSedeChange(sede) {
        _ctx = { ..._ctx, sede };
        _renderHead();
        await _refresh();
    }

    function _initEventos() {
        const btnAdd = document.getElementById('plan-btn-add-bloque');
        if (btnAdd) btnAdd.addEventListener('click', () => _agregarBloque());

        const btnSug = document.getElementById('plan-btn-sugerir');
        if (btnSug) btnSug.addEventListener('click', _cargarPlantillaDelDia);

        const btnGuardar = document.getElementById('plan-btn-guardar');
        if (btnGuardar) btnGuardar.addEventListener('click', _guardar);

        const fecha = document.getElementById('plan-fecha');
        if (fecha) fecha.addEventListener('change', _refresh);

        ['plan-situaciones', 'plan-estrategias', 'plan-notas'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('input', () => {
                _sesionMeta.situaciones_relevantes = document.getElementById('plan-situaciones')?.value || '';
                _sesionMeta.estrategias_aplicadas = document.getElementById('plan-estrategias')?.value || '';
                _sesionMeta.notas = document.getElementById('plan-notas')?.value || '';
            });
        });
    }

    function _setFechaHoy() {
        const f = document.getElementById('plan-fecha');
        if (f && !f.value) f.value = new Date().toISOString().slice(0, 10);
    }

    function _renderHead() {
        const t = document.getElementById('plan-sede-title');
        const s = document.getElementById('plan-sede-subtitle');
        const shell = document.getElementById('plan-shell');
        const needs = document.getElementById('plan-needs-sede');
        if (!_ctx?.sede || !_ctx.sede.id) {
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
            <button type="button" class="plan-clima-opt" data-clima-id="${c.id}" style="--clima-c:${_esc(c.color || '#888')}">
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
        const fecha = document.getElementById('plan-fecha')?.value;
        const shell = document.getElementById('plan-shell');
        if (!_ctx?.sede?.id || !fecha) {
            _bloques = [];
            _resetMeta();
            _renderBloques();
            return;
        }
        await _ensureCatalogos();
        try {
            const data = await window.FundApi.getSesionByFecha(_ctx.sede.id, fecha);
            // poblar estado desde respuesta
            _sesionMeta.clima_opcion_id = data.clima_opcion_id || null;
            _sesionMeta.situaciones_relevantes = data.situaciones_relevantes || '';
            _sesionMeta.estrategias_aplicadas = data.estrategias_aplicadas || '';
            _sesionMeta.notas = data.notas || '';
            _bloques = (data.bloques || []).map(_bloqueFromApi);
        } catch (e) {
            // 404 = sesión no existe todavía, arrancamos vacío
            _bloques = [];
            _resetMeta();
        }
        _hydrateMeta();
        _renderBloques();
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
            { tipo: 'juegos_para_crecer',  sub: 'psicomotor', ini: '15:30', fin: '16:00' },
            { tipo: 'taller_socioemocional', sub: null,       ini: '16:00', fin: '17:00' },
            { tipo: 'colacion',            sub: null,         ini: '17:00', fin: '17:15' },
            { tipo: 'glifing',             sub: null,         ini: '17:15', fin: '17:45' },
            { tipo: 'juegos_para_crecer',  sub: 'sensorial',  ini: '17:45', fin: '18:15' },
            { tipo: 'juego_libre',         sub: null,         ini: '18:15', fin: '18:30' },
        ];
        for (const p of plantilla) {
            const t = tipo(p.tipo);
            _agregarBloque({
                bloque_tipo_id: t?.id || null,
                bloque_subtipo_id: subtipo(p.tipo, p.sub),
                hora_inicio: p.ini,
                hora_fin: p.fin,
            });
        }
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
        node.querySelector('[data-role="orden"]').textContent = b.orden;

        // selector de tipo
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
        });
        const tipoActual = _cat.bloqueTipos.find(t => t.id === b.bloque_tipo_id);
        _refreshSubtipo(node, tipoActual, b);

        // horas
        node.querySelector('[data-role="hora-inicio"]').value = b.hora_inicio || '';
        node.querySelector('[data-role="hora-fin"]').value = b.hora_fin || '';
        node.querySelector('[data-role="hora-inicio"]').addEventListener('change', e => b.hora_inicio = e.target.value);
        node.querySelector('[data-role="hora-fin"]').addEventListener('change', e => b.hora_fin = e.target.value);

        // se ejecutó
        const cbEjec = node.querySelector('[data-role="se-ejecuto"]');
        cbEjec.checked = b.se_ejecuto;
        const noEjecRow = node.querySelector('[data-role="no-ejec-row"]');
        noEjecRow.style.display = b.se_ejecuto ? 'none' : '';
        cbEjec.addEventListener('change', () => {
            b.se_ejecuto = cbEjec.checked;
            noEjecRow.style.display = b.se_ejecuto ? 'none' : '';
        });
        const inputMotivo = node.querySelector('[data-role="motivo"]');
        inputMotivo.value = b.motivo_no_ejecucion || '';
        inputMotivo.addEventListener('input', e => b.motivo_no_ejecucion = e.target.value);

        // eliminar
        node.querySelector('[data-role="del"]').addEventListener('click', () => {
            if (!confirm('¿Eliminar este bloque?')) return;
            _bloques = _bloques.filter(x => x._idx !== b._idx);
            _bloques.forEach((x, i) => x.orden = i + 1);
            _renderBloques();
        });

        // actividad / resultado / adaptación / notas
        const inputAct = node.querySelector('[data-role="actividad"]');
        inputAct.value = b.nombre_actividad || '';
        inputAct.addEventListener('input', e => b.nombre_actividad = e.target.value);

        const inputRes = node.querySelector('[data-role="resultado"]');
        inputRes.value = b.resultado_aprendizaje || '';
        inputRes.addEventListener('input', e => b.resultado_aprendizaje = e.target.value);

        const inputAdapt = node.querySelector('[data-role="adaptacion"]');
        inputAdapt.value = b.adaptacion || '';
        inputAdapt.addEventListener('input', e => b.adaptacion = e.target.value);

        // competencias (solo si permite_competencias)
        _refreshCompetencias(node, tipoActual, b);

        // materiales
        _refreshMateriales(node, b);
        node.querySelector('[data-role="add-material"]').addEventListener('click', () => {
            b.materiales.push({ product_id: null, nombre_libre: '', cantidad_solicitada: '', cantidad_usada: '' });
            _refreshMateriales(node, b);
        });

        return node;
    }

    function _refreshSubtipo(node, tipo, b) {
        const sel = node.querySelector('[data-role="subtipo"]');
        if (!tipo || !tipo.requiere_subtipo || !tipo.subtipos?.length) {
            sel.style.display = 'none';
            sel.innerHTML = '';
            b.bloque_subtipo_id = null;
            return;
        }
        sel.style.display = '';
        sel.innerHTML = `<option value="">— Subtipo —</option>` + tipo.subtipos.map(s =>
            `<option value="${s.id}" ${s.id === b.bloque_subtipo_id ? 'selected' : ''}>${_esc(s.nombre)}</option>`
        ).join('');
        sel.onchange = () => b.bloque_subtipo_id = sel.value ? Number(sel.value) : null;
    }

    function _refreshCompetencias(node, tipo, b) {
        const row = node.querySelector('[data-role="competencias-row"]');
        const cont = node.querySelector('[data-role="competencias"]');
        const resultadoRow = node.querySelector('[data-role="resultado-row"]');
        if (!tipo || !tipo.permite_competencias) {
            row.style.display = 'none';
            resultadoRow.style.display = 'none';
            b.competencias = [];
            return;
        }
        row.style.display = '';
        resultadoRow.style.display = '';
        cont.innerHTML = _cat.competencias.map(c => {
            const checked = b.competencias.includes(c.id) ? 'checked' : '';
            const sel = checked ? 'is-selected' : '';
            return `
              <label class="plan-comp-chip ${sel}" title="${_esc(c.descripcion)}" data-comp-id="${c.id}">
                <input type="checkbox" ${checked} />
                <span class="plan-comp-chip-code" style="color:${_esc(c.dominio_color || '#888')}">${_esc(c.codigo)}</span>
                <span class="plan-comp-chip-desc">${_esc(c.descripcion.slice(0, 50))}${c.descripcion.length > 50 ? '…' : ''}</span>
              </label>
            `;
        }).join('');
        cont.querySelectorAll('.plan-comp-chip').forEach(el => {
            el.addEventListener('click', (ev) => {
                ev.preventDefault();
                const cb = el.querySelector('input[type="checkbox"]');
                const id = Number(el.dataset.compId);
                cb.checked = !cb.checked;
                el.classList.toggle('is-selected', cb.checked);
                if (cb.checked) {
                    if (!b.competencias.includes(id)) b.competencias.push(id);
                } else {
                    b.competencias = b.competencias.filter(x => x !== id);
                }
            });
        });
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
        const fecha = document.getElementById('plan-fecha')?.value;
        if (!_ctx?.sede?.id || !fecha) {
            window.showToast?.('Selecciona sede y fecha primero', 'warn');
            return;
        }
        // Validación blanda: bloques sin tipo o con subtipo requerido y vacío
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
        if (btn) { btn.disabled = true; btn.classList.add('is-syncing'); }
        try {
            await window.FundApi.upsertSesion(payload);
            window.showToast?.('Sesión guardada', 'success');
            await _refresh();
        } catch (e) {
            console.error('[Planificación] error guardando', e);
            window.showToast?.('Error al guardar: ' + (e?.detail || e?.message || e), 'error');
        } finally {
            _saving = false;
            if (btn) { btn.disabled = false; btn.classList.remove('is-syncing'); }
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    return { init, onSedeChange };
})();
