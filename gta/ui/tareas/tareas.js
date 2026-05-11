// GTA — Tab Tareas (modelo área-céntrico)
window.Tareas = (() => {
    const ADMIN_ROLES = new Set(['admin']);

    let _sesion = null;
    let _vista = 'bandeja';      // bandeja | mias | colaboro
    let _areas = [];             // áreas completas del catálogo (para admin)
    let _subareas = [];
    let _areasUsuario = [];      // áreas que el usuario puede ver
    let _areaActiva = '';        // '' = todas; o area_code
    let _esAdmin = false;
    let _data = { bandeja: [], mias: [], colaboro: [], quiebres: [] };
    let _tareasExpandidas = new Set();
    let _miembrosCache = new Map();   // subarea_id → array de miembros (cache local)
    let _asignarPopover = null;       // popover de asignación abierto (si hay)

    // ── Init ──────────────────────────────────────────────────────────
    async function init(sesion) {
        _sesion = sesion;
        const role = String(_sesion?.role || '').toLowerCase();
        const roles = (_sesion?.roles || []).map(r => String(r).toLowerCase());
        _esAdmin = ADMIN_ROLES.has(role) || roles.some(r => ADMIN_ROLES.has(r));

        // Cada vez que se entra a la pestaña, las tareas arrancan colapsadas.
        // Si no, los acordeones quedaban "semi-abiertos" (HTML expandido pero
        // sin contenido async cargado) tras volver desde otra pestaña.
        _tareasExpandidas.clear();

        await cargarSubareasCatalogo();
        await cargarAreasUsuario();
        _renderAreasPills();
        await recargar();

        // Bridge desde el Tablero: si vino con un "abrir tarea X", lo intentamos.
        const pending = window.GtaCore?.pendingExpandTarea;
        if (pending) {
            window.GtaCore.pendingExpandTarea = null;
            await _intentarAbrirTareaPin(pending);
        }
    }

    async function _intentarAbrirTareaPin(tareaId) {
        // Buscar la tarea en alguna de las vistas; si no está, probar cargando otra
        const vistasAProbar = ['mias', 'bandeja', 'colaboro'];
        for (const v of vistasAProbar) {
            if (_vista !== v) {
                _vista = v;
                document.querySelectorAll('.gta-subtab').forEach(b => b.classList.remove('active'));
                document.querySelector(`[data-view="${v}"]`)?.classList.add('active');
                await recargar();
            }
            if (_buscarTarea(tareaId)) {
                _tareasExpandidas.add(tareaId);
                try {
                    const detalle = await GtaApi.getTareaArea(tareaId);
                    _mergeDetalle(detalle);
                } catch (e) { /* silent */ }
                _render();
                const tarea = _buscarTarea(tareaId);
                if (tarea?.flujo_id) {
                    _refrescarAdjuntos(tareaId);
                    _refrescarQuiebres(tareaId);
                    _refrescarComentarios(tareaId);
                }
                // Scroll a la tarea
                setTimeout(() => {
                    const card = document.querySelector(`[data-tarea-id="${tareaId}"]`)
                              || document.querySelector(`#form-tarea-${tareaId}`)?.closest('.gta-tarea-card');
                    card?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 100);
                return;
            }
        }
        // Si no la encontramos en ninguna vista, avisamos suave
        console.warn(`[Tareas] tarea ${tareaId} no aparece en ninguna vista del usuario actual`);
    }

    async function cargarSubareasCatalogo() {
        // Usamos /api/gta/areas (no /catalogo) porque devuelve label real
        // de áreas y subáreas. /catalogo solo trae los archivos.
        try {
            const r = await window.fetchApi('/api/gta/areas');
            _areas = r?.items || [];
            const subs = [];
            _areas.forEach(a => {
                (a.subareas || []).forEach(s => {
                    subs.push({
                        area_code: a.code,
                        area_label: a.label,
                        subarea_code: s.code,
                        subarea_label: s.label,
                    });
                });
            });
            _subareas = subs;
        } catch (e) {
            console.warn('[Tareas] no se pudo cargar áreas', e);
            _areas = [];
            _subareas = [];
        }
    }

    async function cargarAreasUsuario() {
        // Admin ve todas las áreas activas (incluso sin subáreas todavía).
        // Usuario común ve solo las áreas donde tiene membresía vigente (vía /membresias/mias).
        if (_esAdmin) {
            _areasUsuario = _areas.filter(a => a.activo).map(a => ({
                code: a.code, label: a.label,
            }));
            return;
        }
        try {
            const r = await GtaApi.getMisMembresias();
            const map = new Map();
            (r.items || []).forEach(m => {
                if (!map.has(m.area_code)) {
                    map.set(m.area_code, { code: m.area_code, label: m.area_label });
                }
            });
            _areasUsuario = Array.from(map.values());
        } catch (e) {
            console.warn('[Tareas] no se pudo cargar membresías', e);
            _areasUsuario = [];
        }
    }

    function _renderAreasPills() {
        const cont = document.getElementById('tareas-areas-pills');
        if (!cont) return;
        if (!_areasUsuario.length) {
            cont.innerHTML = '<span class="gta-section-help">No tenés áreas asignadas. Pedile al admin que te asigne membresía.</span>';
            return;
        }
        const pills = [];
        if (_esAdmin) {
            // Admin: pill "Todas" + N pills de áreas
            pills.push(`<button class="gta-area-pill ${_areaActiva === '' ? 'active' : ''}" data-area="" onclick="Tareas.filtrarArea('')">Todas</button>`);
        }
        _areasUsuario.forEach(a => {
            pills.push(`<button class="gta-area-pill ${_areaActiva === a.code ? 'active' : ''}" data-area="${_esc(a.code)}" onclick="Tareas.filtrarArea('${_esc(a.code)}')">${_esc(a.label)}</button>`);
        });
        cont.innerHTML = pills.join('');

        // Si no es admin, forzamos que el área activa sea una de las suyas.
        if (!_esAdmin && !_areasUsuario.some(a => a.code === _areaActiva)) {
            _areaActiva = _areasUsuario[0]?.code || '';
        }
    }

    async function filtrarArea(areaCode) {
        _areaActiva = areaCode || '';
        document.querySelectorAll('.gta-area-pill').forEach(b => {
            b.classList.toggle('active', (b.getAttribute('data-area') || '') === _areaActiva);
        });
        await recargar();
    }

    // ── Vistas ────────────────────────────────────────────────────────
    async function cambiarVista(vista, btnEl) {
        if (_vista === vista) return;
        _vista = vista;
        document.querySelectorAll('.gta-subtab').forEach(b => b.classList.remove('active'));
        if (btnEl) btnEl.classList.add('active');
        await recargar();
    }

    async function recargar() {
        const incluirCerradas = document.getElementById('incluir-cerradas')?.checked || false;
        const cont = document.getElementById('tareas-content');
        if (!cont) return;
        cont.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;

        try {
            let resp;
            if (_vista === 'bandeja') {
                resp = await GtaApi.getBandeja();
                _data.bandeja = resp.items || [];
            } else if (_vista === 'mias') {
                resp = await GtaApi.getMisTareas(incluirCerradas);
                _data.mias = resp.items || [];
            } else if (_vista === 'colaboro') {
                resp = await GtaApi.getDondeColaboro(incluirCerradas);
                _data.colaboro = resp.items || [];
            } else if (_vista === 'quiebres') {
                resp = await GtaApi.listarMisQuiebres();
                _data.quiebres = resp.items || [];
            }
            _refreshCounts();
            _render();
        } catch (e) {
            console.error('[Tareas] error cargando', e);
            cont.innerHTML = `<div class="gta-empty-state">
                <i class="fas fa-triangle-exclamation"></i>
                Error al cargar las tareas. ${_humanizeErr(e)}
            </div>`;
        }
    }

    function _refreshCounts() {
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = (v ?? '—'); };
        set('count-bandeja',  _data.bandeja?.length);
        set('count-mias',     _data.mias?.length);
        set('count-colaboro', _data.colaboro?.length);
        set('count-quiebres', _data.quiebres?.length);
    }

    function _render() {
        const cont = document.getElementById('tareas-content');
        if (!cont) return;
        let items = _data[_vista] || [];

        // Vista de quiebres: render distinto (no son tareas)
        if (_vista === 'quiebres') {
            if (!items.length) {
                cont.innerHTML = `<div class="gta-empty-state">
                    <i class="fas fa-circle-check"></i>
                    No tenés quiebres pendientes dirigidos a tu área.
                </div>`;
                return;
            }
            cont.innerHTML = items.map(_quiebreCardHtml).join('');
            return;
        }

        // Filtro de área: vacío = todas (solo admin); valor = filtrar por area_code
        if (_areaActiva) {
            items = items.filter(t => t.area_code === _areaActiva);
        }
        if (!items.length) {
            cont.innerHTML = `<div class="gta-empty-state">
                <i class="fas ${_vista === 'bandeja' ? 'fa-inbox' : 'fa-circle-check'}"></i>
                ${_emptyMsg(_vista)}
            </div>`;
            return;
        }
        cont.innerHTML = items.map(t => _cardHtml(t, _vista)).join('');
    }

    function _quiebreCardHtml(q) {
        const fecha = q.created_at ? new Date(q.created_at).toLocaleString() : '';
        const desdePaso = q.paso_orden ? `paso ${q.paso_orden}` : 'tarea';
        return `
            <div class="gta-quiebre-card">
                <div class="gta-quiebre-card-head">
                    <span class="gta-quiebre-area-badge"><i class="fas fa-flag"></i> ${_esc(q.area_label || q.area)}</span>
                    <span class="gta-quiebre-card-meta">
                        Reportado por <strong>${_esc(q.reportado_por || '?')}</strong>
                        desde ${desdePaso}
                        ${q.tarea_titulo ? `: "${_esc(q.tarea_titulo)}"` : ''}
                        · ${fecha}
                    </span>
                </div>
                ${q.proceso_nombre || q.flujo_titulo ? `
                    <div class="gta-quiebre-card-flujo">
                        <i class="fas fa-project-diagram"></i>
                        ${_esc(q.proceso_nombre || '')}${q.flujo_titulo ? ` — ${_esc(q.flujo_titulo)}` : ''}
                    </div>
                ` : ''}
                <div class="gta-quiebre-card-desc">${_esc(q.descripcion)}</div>
                <div class="gta-quiebre-card-actions">
                    <button class="btn-primary"
                            onclick="Tareas.resolverQuiebre(${q.id})">
                        <i class="fas fa-check"></i> Resolver
                    </button>
                </div>
            </div>
        `;
    }

    function _emptyMsg(vista) {
        if (vista === 'bandeja')  return 'No hay tareas sin responsable en tus áreas.';
        if (vista === 'mias')     return 'No tenés tareas asignadas.';
        if (vista === 'colaboro') return 'No estás colaborando en ninguna tarea.';
        return 'Sin tareas.';
    }

    // _cardHtml: tarjeta colapsada por default. Click despliega acordeón.
    // Click en el responsable abre dropdown de asignación (no expande el acordeón).
    function _cardHtml(t, vista) {
        const sinResp = !t.responsable_id;
        const myUsername = _sesion?.username || '';
        const soyResp = t.responsable_username === myUsername;
        const expandida = _tareasExpandidas.has(t.id);
        const sla = t.sla_due_at
            ? `<span class="gta-card-sla" title="Vence: ${_fmtFecha(t.sla_due_at)}"><i class="fas fa-clock"></i> ${_fmtFecha(t.sla_due_at)}</span>`
            : '';

        // Render del responsable: si es admin → siempre clickeable.
        // Si no es admin: clickeable solo si la tarea está sin responsable
        //   (para que pueda tomarla con un click). Si ya tiene responsable,
        //   solo se ve en read-only (no puede reasignar).
        const puedoCambiarResp = _esAdmin || sinResp;
        const respHtml = sinResp
            ? `<span class="gta-card-resp gta-resp-vacio ${puedoCambiarResp ? 'es-clickeable' : ''}"
                     ${puedoCambiarResp ? `onclick="event.stopPropagation(); Tareas.toggleAsignar(${t.id}, this)"` : ''}
                     title="${puedoCambiarResp ? 'Click para asignar' : 'Sin asignar'}">
                  <i class="fas fa-user-plus"></i> Sin asignar
              </span>`
            : `<span class="gta-card-resp ${puedoCambiarResp ? 'es-clickeable' : ''}"
                     ${puedoCambiarResp ? `onclick="event.stopPropagation(); Tareas.toggleAsignar(${t.id}, this)"` : ''}
                     title="${puedoCambiarResp ? 'Click para reasignar' : 'Responsable: ' + _esc(t.responsable_username)}">
                  <i class="fas fa-user"></i> ${_esc(t.responsable_username)}
              </span>`;

        return `
            <div class="gta-tarea-card ${sinResp ? 'sin-responsable' : ''} ${expandida ? 'is-open' : ''}"
                 data-tarea-id="${t.id}">
                <div class="gta-tarea-card-head" onclick="Tareas.toggleExpansion(${t.id})">
                    <div class="gta-tarea-card-head-left">
                        <i class="fas fa-chevron-right gta-card-chevron"></i>
                        <h3 class="gta-tarea-card-titulo">${_esc(t.titulo)}</h3>
                        ${t.tiene_avisos_pendientes ? `<span class="gta-card-aviso-badge" title="Hubo cambios en pasos anteriores después de tu cierre">⚠ Revisar</span>` : ''}
                    </div>
                    <div class="gta-tarea-card-head-right">
                        <span class="pill gta-prioridad-${t.prioridad}" title="Prioridad ${_esc(t.prioridad)}">${_esc(t.prioridad)}</span>
                        <span class="pill gta-estado-${t.estado}" title="Estado">${_esc(t.estado.replace('_', ' '))}</span>
                        <span class="gta-card-area" title="Área asignada"><i class="fas fa-folder"></i> ${_esc(t.area_label || '—')}${t.subarea_label ? ' / ' + _esc(t.subarea_label) : ''}</span>
                        ${respHtml}
                        ${sla}
                    </div>
                </div>
                <div class="gta-tarea-card-body" id="tarea-body-${t.id}">
                    ${expandida ? _cardBodyHtml(t, vista, soyResp) : ''}
                </div>
            </div>
        `;
    }

    // Cuerpo del acordeón: descripción + datos del flujo + formulario + acciones
    function _cardBodyHtml(t, vista, soyResp) {
        const datosFlujo = t.flujo?.datos_formulario || {};
        const camposProc = t.campos_formulario_proceso || [];
        const esBloqueada = t.estado === 'bloqueada';
        const esCerrada = t.estado === 'cerrada' || t.estado === 'cancelada' || t.estado === 'devuelta';
        const esEsperandoQuiebre = t.estado === 'esperando_quiebre';
        const editable = !esBloqueada && !esCerrada && !esEsperandoQuiebre && (soyResp || _esAdmin);
        const tieneFormulario = t.es_paso_inicial && camposProc.length > 0;

        // Banner si está bloqueada por dependencias del flujo
        let bannerBloq = '';
        if (esBloqueada) {
            const deps = (t.paso_depende_de || []).join(', ');
            bannerBloq = `
                <div class="gta-banner-bloqueada">
                    <i class="fas fa-lock"></i>
                    <span>Esta tarea espera a que se completen los pasos: <strong>${_esc(deps || '?')}</strong>. Lectura solamente hasta que se desbloquee.</span>
                </div>
            `;
        }
        // Banner si está esperando que otra área resuelva un quiebre
        if (esEsperandoQuiebre) {
            bannerBloq += `
                <div class="gta-banner-quiebre">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Esta tarea está <strong>esperando que otra área resuelva un quiebre</strong>. No se puede avanzar hasta que se resuelva. Mirá la sección "Quiebres del flujo" abajo.</span>
                </div>
            `;
        }

        // Avisos de revisión (placeholder, se llena async tras render)
        const avisosHtml = t.flujo_id && t.tiene_avisos_pendientes
            ? `<div id="avisos-tarea-${t.id}" class="gta-banner-aviso">
                   <em style="opacity:0.6;">Cargando avisos…</em>
               </div>`
            : '';

        // Descripción
        const descHtml = t.descripcion
            ? `<div class="gta-acc-section">
                  <h4 class="gta-acc-h4">Descripción</h4>
                  <div class="gta-acc-body">${_esc(t.descripcion)}</div>
              </div>`
            : '';

        // Datos del flujo (si NO es paso inicial, mostramos los datos del iniciador)
        let datosHtml = '';
        if (!t.es_paso_inicial && Object.keys(datosFlujo).length && camposProc.length) {
            datosHtml = `
                <div class="gta-acc-section">
                    <h4 class="gta-acc-h4">Datos del flujo (cargados por ${_esc(t.flujo?.titulo || 'el iniciador')})</h4>
                    <div class="gta-flujo-datos-box">
                        ${camposProc.map(c => {
                            const v = datosFlujo[c.key];
                            if (v == null || v === '') return '';
                            return `<div class="gta-flujo-dato">
                                <span class="gta-flujo-dato-label">${_esc(c.label)}:</span>
                                <span class="gta-flujo-dato-valor">${_esc(String(v))}</span>
                            </div>`;
                        }).filter(Boolean).join('') || '<em style="opacity:0.6;">El iniciador todavía no completó los datos.</em>'}
                    </div>
                </div>
            `;
        }

        // Formulario editable (paso 1 con campos)
        let formHtml = '';
        if (tieneFormulario) {
            formHtml = `
                <div class="gta-acc-section">
                    <h4 class="gta-acc-h4">Formulario del proceso ${editable ? '<span class="gta-acc-tag-editable">editable</span>' : '<span class="gta-acc-tag-readonly">solo lectura</span>'}</h4>
                    <div class="gta-acc-form-grid" id="form-tarea-${t.id}">
                        ${camposProc.map(c => _campoHtml(c, datosFlujo[c.key], editable, t.id)).join('')}
                    </div>
                </div>
            `;
        }

        // Acciones según vista y rol
        const acciones = [];
        if (!esCerrada) {
            if (sinRespOrLibre(t)) {
                if (vista === 'bandeja' || sinRespOrLibre(t)) {
                    acciones.push(`<button class="btn-primary gta-btn-tomar"
                        title="Asignarme esta tarea como responsable"
                        onclick="event.stopPropagation(); Tareas.tomar(${t.id})">
                        <i class="fas fa-hand-paper"></i> Tomar
                    </button>`);
                }
            }
            if (soyResp || _esAdmin) {
                if (tieneFormulario && editable) {
                    acciones.push(`<button class="btn-secondary"
                        title="Guardar lo que llevas sin cerrar la tarea"
                        onclick="event.stopPropagation(); Tareas.guardarBorrador(${t.id})">
                        <i class="fas fa-save"></i> Guardar borrador
                    </button>`);
                }
                if (soyResp) {
                    acciones.push(`<button class="btn-secondary"
                        title="Dejar de ser responsable y devolver la tarea a la bandeja"
                        onclick="event.stopPropagation(); Tareas.liberar(${t.id})">
                        <i class="fas fa-undo"></i> Soltar
                    </button>`);
                }
                if (!esBloqueada && !esEsperandoQuiebre) {
                    // Devolver: cualquier tarea de flujo en paso ≥ 2 puede
                    // devolver a un paso anterior. El modal elige el destino.
                    const hayDestinos = (t.paso_devolver_a_info || []).length > 0;
                    if (t.flujo_id && hayDestinos) {
                        acciones.push(`<button class="btn-danger"
                            title="Devolver esta tarea a un paso anterior para que su responsable corrija"
                            onclick="event.stopPropagation(); Tareas.devolver(${t.id})">
                            <i class="fas fa-undo-alt"></i> Devolver al paso…
                        </button>`);
                    }
                    acciones.push(`<button class="btn-primary"
                        title="Marcar la tarea como hecha y cerrarla (valida campos obligatorios)"
                        onclick="event.stopPropagation(); Tareas.completar(${t.id})">
                        <i class="fas fa-check"></i> Completar
                    </button>`);
                }
            }
        }

        // Adjuntos del flujo (sección colapsable, se rellena async tras render)
        const puedeSubir = t.flujo_id && !esCerrada;
        const adjuntosHtml = t.flujo_id ? `
            <div class="gta-acc-section">
                <h4 class="gta-acc-h4">Adjuntos del flujo</h4>
                <div id="adjuntos-tarea-${t.id}" class="gta-adjuntos-box">
                    <em style="opacity:0.6;">Cargando…</em>
                </div>
                ${puedeSubir ? `
                    <div class="gta-adjuntos-upload">
                        <input type="file" id="adjunto-input-${t.id}" style="display:none;"
                               onchange="Tareas.subirAdjunto(${t.id}, this)">
                        <button class="btn-secondary"
                                onclick="event.stopPropagation(); document.getElementById('adjunto-input-${t.id}').click()">
                            <i class="fas fa-paperclip"></i> Subir archivo
                        </button>
                    </div>
                ` : ''}
            </div>
        ` : '';

        // Quiebres del flujo (sección colapsable, se rellena async tras render)
        const quiebresHtml = t.flujo_id ? `
            <div class="gta-acc-section">
                <h4 class="gta-acc-h4">Quiebres del flujo</h4>
                <div id="quiebres-tarea-${t.id}" class="gta-quiebres-box">
                    <em style="opacity:0.6;">Cargando…</em>
                </div>
            </div>
        ` : '';

        // Comentarios libres del flujo (visibles a todos, cualquier responsable comenta)
        const puedeComentar = t.flujo_id && !esCerrada;
        const comentariosHtml = t.flujo_id ? `
            <div class="gta-acc-section">
                <h4 class="gta-acc-h4">Comentarios del flujo</h4>
                <div id="comentarios-tarea-${t.id}" class="gta-comentarios-box">
                    <em style="opacity:0.6;">Cargando…</em>
                </div>
                ${puedeComentar ? `
                    <div class="gta-comentario-form">
                        <textarea id="comentario-input-${t.id}" rows="2"
                                  placeholder="Escribir un comentario para el flujo (todos los responsables lo ven)…"></textarea>
                        <button class="btn-secondary"
                                onclick="event.stopPropagation(); Tareas.agregarComentario(${t.id})">
                            <i class="fas fa-comment"></i> Comentar
                        </button>
                    </div>
                ` : ''}
            </div>
        ` : '';

        return `
            ${bannerBloq}
            ${avisosHtml}
            ${descHtml}
            ${datosHtml}
            ${formHtml}
            ${adjuntosHtml}
            ${quiebresHtml}
            ${comentariosHtml}
            ${acciones.length ? `<div class="gta-acc-actions">${acciones.join('')}</div>` : ''}
        `;
    }

    function sinRespOrLibre(t) {
        return !t.responsable_id;
    }

    // Render de un campo del formulario inline en el acordeón
    function _campoHtml(c, valor, editable, tareaId) {
        const requerido = c.requerido !== false;
        const v = valor != null ? String(valor) : '';
        const disabled = editable ? '' : 'disabled';
        const dataAttrs = `data-tarea-id="${tareaId}" data-campo-key="${_esc(c.key)}" data-requerido="${requerido ? '1' : '0'}"`;
        // La ayuda va como placeholder dentro del input para que desaparezca
        // al escribir y no ensucie el formulario con texto extra debajo.
        const ph = c.ayuda ? `placeholder="${_esc(c.ayuda)}"` : '';

        let input;
        if (c.tipo === 'textarea') {
            input = `<textarea class="input-dark" rows="2" ${ph} ${disabled} ${dataAttrs}>${_esc(v)}</textarea>`;
        } else if (c.tipo === 'numero') {
            // Números no aceptan negativos. step=any permite decimales (ej: UF con coma).
            input = `<input type="number" class="input-dark" min="0" step="any" value="${_esc(v)}" ${ph} ${disabled} ${dataAttrs}>`;
        } else if (c.tipo === 'fecha') {
            // Las fechas no soportan placeholder real, no tiene sentido aplicarlo.
            input = `<input type="date" class="input-dark" value="${_esc(v)}" ${disabled} ${dataAttrs}>`;
        } else if (c.tipo === 'select') {
            // En selects, el placeholder se transmite via la opción "— Seleccionar —"
            // (que ya cumple el rol). Si hay ayuda específica, la usamos en el primer option.
            const phOpt = c.ayuda ? _esc(c.ayuda) : '— Seleccionar —';
            // Si tiene un campo dependiente, escuchamos cambios para refrescar
            // el campo hijo cuando este valor cambie.
            const onChange = `onchange="Tareas._onCampoSelectChange('${_esc(c.key)}', this.value, ${tareaId})"`;
            input = `<select class="input-dark" ${disabled} ${dataAttrs} ${onChange}>
                <option value="">${phOpt}</option>
                ${(c.opciones || []).map(o => `<option value="${_esc(o)}" ${o === v ? 'selected' : ''}>${_esc(o)}</option>`).join('')}
            </select>`;
        } else if (c.tipo === 'select_dependiente') {
            // Las opciones se calculan según el valor actual del campo padre.
            // Si el padre está vacío, mostramos un select deshabilitado con
            // mensaje de ayuda hasta que el usuario elija el padre.
            const padreKey = c.depende_de;
            const padreInput = padreKey
                ? document.querySelector(`#form-tarea-${tareaId} [data-campo-key="${padreKey}"]`)
                : null;
            const padreValor = padreInput ? padreInput.value : '';
            const opcionesHijo = (c.opciones_por_valor || {})[padreValor] || [];
            const phOpt = c.ayuda ? _esc(c.ayuda) : '— Seleccionar —';
            const noHayPadre = !padreValor;
            const sinOpciones = !opcionesHijo.length;

            let firstOpt;
            if (noHayPadre) {
                firstOpt = `Primero elegí ${_esc(c.depende_de_label || padreKey || 'el campo anterior')}`;
            } else if (sinOpciones) {
                firstOpt = 'Sin opciones disponibles para esta línea';
            } else {
                firstOpt = phOpt;
            }
            const dis = (disabled || noHayPadre || sinOpciones) ? 'disabled' : '';

            input = `<select class="input-dark" ${dis} ${dataAttrs} data-padre-key="${_esc(padreKey || '')}">
                <option value="">${firstOpt}</option>
                ${opcionesHijo.map(o => `<option value="${_esc(o)}" ${o === v ? 'selected' : ''}>${_esc(o)}</option>`).join('')}
            </select>`;
        } else {
            input = `<input type="text" class="input-dark" value="${_esc(v)}" ${ph} ${disabled} ${dataAttrs}>`;
        }

        return `
            <div class="gta-acc-campo">
                <label>${_esc(c.label)}${requerido ? ' <span class="gta-req">*</span>' : ''}</label>
                ${input}
            </div>
        `;
    }

    // ── Toggle del acordeón ───────────────────────────────────────────
    async function toggleExpansion(id) {
        if (_tareasExpandidas.has(id)) {
            _tareasExpandidas.delete(id);
            _render();
        } else {
            _tareasExpandidas.add(id);
            // Cargar el detalle completo de la tarea (incluye campos del flujo)
            try {
                const detalle = await GtaApi.getTareaArea(id);
                // Actualizar el item en _data con el detalle completo
                _mergeDetalle(detalle);
            } catch (e) {
                console.warn('[Tareas] no se pudo cargar detalle', e);
            }
            _render();
            // Tras render, si es tarea de flujo, llenamos secciones async
            const tarea = _buscarTarea(id);
            if (tarea?.flujo_id) {
                _refrescarAdjuntos(id);
                _refrescarQuiebres(id);
                _refrescarComentarios(id);
                if (tarea.tiene_avisos_pendientes) _refrescarAvisos(id);
            }
        }
    }

    function _buscarTarea(id) {
        for (const k of Object.keys(_data)) {
            const t = (_data[k] || []).find(x => x.id === id);
            if (t) return t;
        }
        return null;
    }

    function _mergeDetalle(detalle) {
        if (!detalle?.id) return;
        for (const k of Object.keys(_data)) {
            const idx = (_data[k] || []).findIndex(t => t.id === detalle.id);
            if (idx >= 0) {
                _data[k][idx] = { ..._data[k][idx], ...detalle };
            }
        }
    }

    // ── Acciones ──────────────────────────────────────────────────────
    async function tomar(id) {
        try {
            await GtaApi.tomarTareaArea(id);
            // Mantenemos la expansión si estaba abierta
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    async function liberar(id) {
        if (!confirm('¿Soltar esta tarea? Vuelve a la bandeja del área.')) return;
        try {
            await GtaApi.liberarTareaArea(id, null);
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Guardar borrador (datos parciales del formulario) ─────────────
    async function guardarBorrador(id) {
        const datos = _recolectarFormulario(id);
        if (datos === null) return;  // hubo error de UI
        try {
            await GtaApi.guardarBorradorTarea(id, datos);
            // Avisamos sin recargar para no cerrar el acordeón
            _flashMensaje(id, 'Borrador guardado.', 'ok');
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Adjuntos del flujo ────────────────────────────────────────────
    async function _refrescarAdjuntos(tareaId) {
        const cont = document.getElementById(`adjuntos-tarea-${tareaId}`);
        if (!cont) return;
        try {
            const resp = await GtaApi.listarAdjuntosTarea(tareaId);
            const items = resp.items || [];
            if (!items.length) {
                cont.innerHTML = '<em style="opacity:0.6;">Sin adjuntos todavía.</em>';
                return;
            }
            cont.innerHTML = items.map(a => {
                const fecha = a.created_at ? new Date(a.created_at).toLocaleString() : '';
                const peso = a.size_bytes != null ? `${(a.size_bytes/1024).toFixed(0)} KB` : '';
                return `
                    <div class="gta-adjunto-item">
                        <a href="${GtaApi.urlDescargarAdjunto(a.id)}" target="_blank" rel="noopener">
                            <i class="fas fa-file"></i> ${_esc(a.filename)}
                        </a>
                        <span class="gta-adjunto-meta">${peso} · ${_esc(a.subido_por_username || 'sistema')} · ${fecha}</span>
                        <button class="btn-icon btn-icon-danger" title="Borrar adjunto"
                                onclick="event.stopPropagation(); Tareas.borrarAdjunto(${tareaId}, ${a.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `;
            }).join('');
        } catch (e) {
            cont.innerHTML = `<em style="color:#c00;">Error al cargar adjuntos: ${_esc(_humanizeErr(e))}</em>`;
        }
    }

    async function subirAdjunto(tareaId, inputEl) {
        const file = inputEl.files?.[0];
        if (!file) return;
        try {
            await GtaApi.subirAdjuntoTarea(tareaId, file);
            inputEl.value = '';
            await _refrescarAdjuntos(tareaId);
        } catch (e) {
            alert(_humanizeErr(e));
            inputEl.value = '';
        }
    }

    async function borrarAdjunto(tareaId, adjId) {
        if (!confirm('¿Borrar este adjunto?')) return;
        try {
            await GtaApi.borrarAdjuntoTarea(tareaId, adjId);
            await _refrescarAdjuntos(tareaId);
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Avisos de revisión (cambios post-cierre) ──────────────────────
    async function _refrescarAvisos(tareaId) {
        const cont = document.getElementById(`avisos-tarea-${tareaId}`);
        if (!cont) return;
        try {
            const resp = await GtaApi.listarAvisosTarea(tareaId);
            const items = resp.items || [];
            if (!items.length) {
                cont.remove();
                // También limpiar badge en card colapsada
                const tarea = _buscarTarea(tareaId);
                if (tarea) tarea.tiene_avisos_pendientes = false;
                return;
            }
            cont.innerHTML = `
                <div class="gta-banner-aviso-head">
                    <i class="fas fa-exclamation-triangle"></i>
                    <strong>Hubo cambios en pasos anteriores después de tu cierre</strong>
                </div>
                <div class="gta-banner-aviso-list">
                    ${items.map(a => {
                        const fecha = a.created_at ? new Date(a.created_at).toLocaleString() : '';
                        const desde = a.por_tarea_paso
                            ? `paso ${a.por_tarea_paso} (${_esc(a.por_tarea_titulo || '')})`
                            : 'otro paso';
                        return `
                            <div class="gta-aviso-item">
                                <div class="gta-aviso-msg">
                                    <strong>${_esc(desde)}:</strong> ${_esc(a.motivo || 'modificación')}
                                    <span class="gta-aviso-meta"> · ${fecha}</span>
                                </div>
                                <button class="btn-sm btn-secondary"
                                        onclick="event.stopPropagation(); Tareas.marcarAvisoRevisado(${tareaId}, ${a.id})">
                                    <i class="fas fa-check"></i> Marcar revisado
                                </button>
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        } catch (e) {
            cont.innerHTML = `<em style="color:#c00;">Error al cargar avisos: ${_esc(_humanizeErr(e))}</em>`;
        }
    }

    async function marcarAvisoRevisado(tareaId, avisoId) {
        try {
            await GtaApi.marcarAvisoRevisado(tareaId, avisoId);
            await _refrescarAvisos(tareaId);
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Comentarios libres del flujo ──────────────────────────────────
    async function _refrescarComentarios(tareaId) {
        const cont = document.getElementById(`comentarios-tarea-${tareaId}`);
        if (!cont) return;
        try {
            const resp = await GtaApi.listarComentariosTarea(tareaId);
            const items = resp.items || [];
            if (!items.length) {
                cont.innerHTML = '<em style="opacity:0.6;">Sin comentarios todavía.</em>';
                return;
            }
            const meUser = (window.GtaCore?.session?.username) || '';
            cont.innerHTML = items.map(c => {
                const fecha = c.created_at ? new Date(c.created_at).toLocaleString() : '';
                const desdePaso = c.paso_orden ? `paso ${c.paso_orden}` : '';
                const puedeBorrar = c.autor === meUser || _esAdmin;
                return `
                    <div class="gta-comentario-item">
                        <div class="gta-comentario-head">
                            <strong>${_esc(c.autor || '?')}</strong>
                            <span class="gta-comentario-meta">${desdePaso ? `· ${desdePaso}` : ''} · ${fecha}</span>
                            ${puedeBorrar ? `
                                <button class="btn-icon btn-icon-danger" title="Borrar comentario"
                                        onclick="event.stopPropagation(); Tareas.borrarComentario(${tareaId}, ${c.id})">
                                    <i class="fas fa-trash"></i>
                                </button>` : ''}
                        </div>
                        <div class="gta-comentario-texto">${_esc(c.texto)}</div>
                    </div>
                `;
            }).join('');
        } catch (e) {
            cont.innerHTML = `<em style="color:#c00;">Error al cargar comentarios: ${_esc(_humanizeErr(e))}</em>`;
        }
    }

    async function agregarComentario(tareaId) {
        const input = document.getElementById(`comentario-input-${tareaId}`);
        const texto = (input?.value || '').trim();
        if (!texto) { input?.focus(); return; }
        try {
            await GtaApi.crearComentarioTarea(tareaId, texto);
            input.value = '';
            await _refrescarComentarios(tareaId);
        } catch (e) { alert(_humanizeErr(e)); }
    }

    async function borrarComentario(tareaId, comId) {
        if (!confirm('¿Borrar este comentario?')) return;
        try {
            await GtaApi.borrarComentarioTarea(tareaId, comId);
            await _refrescarComentarios(tareaId);
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Quiebres del flujo (reportar / listar) ────────────────────────
    async function _refrescarQuiebres(tareaId) {
        const cont = document.getElementById(`quiebres-tarea-${tareaId}`);
        if (!cont) return;
        try {
            const resp = await GtaApi.listarQuiebresTarea(tareaId);
            const items = resp.items || [];
            if (!items.length) {
                cont.innerHTML = '<em style="opacity:0.6;">Sin quiebres reportados en este flujo.</em>';
                return;
            }
            cont.innerHTML = items.map(q => {
                const fecha = q.created_at ? new Date(q.created_at).toLocaleString() : '';
                const resueltoBadge = q.estado === 'resuelto'
                    ? `<span class="gta-quiebre-badge gta-quiebre-badge-ok">resuelto</span>`
                    : `<span class="gta-quiebre-badge gta-quiebre-badge-open">abierto</span>`;
                const notaResol = q.nota_resolucion
                    ? `<div class="gta-quiebre-nota"><strong>Resolución:</strong> ${_esc(q.nota_resolucion)} <em>(${_esc(q.resuelto_por || '')})</em></div>`
                    : '';
                const desdePaso = q.paso_orden
                    ? `desde paso ${q.paso_orden}`
                    : '';
                return `
                    <div class="gta-quiebre-item">
                        <div class="gta-quiebre-head">
                            ${resueltoBadge}
                            <span class="gta-quiebre-area">→ ${_esc(q.area_label || q.area)}</span>
                            <span class="gta-quiebre-meta">${desdePaso} · ${_esc(q.reportado_por || '')} · ${fecha}</span>
                        </div>
                        <div class="gta-quiebre-desc">${_esc(q.descripcion)}</div>
                        ${notaResol}
                    </div>
                `;
            }).join('');
        } catch (e) {
            cont.innerHTML = `<em style="color:#c00;">Error al cargar quiebres: ${_esc(_humanizeErr(e))}</em>`;
        }
    }

    async function reportarQuiebre(tareaId) {
        // Cargar las áreas disponibles para esta tarea
        let areas = [];
        try {
            const resp = await GtaApi.areasDisponiblesQuiebre(tareaId);
            areas = resp.items || [];
        } catch (e) {
            alert(_humanizeErr(e));
            return;
        }
        if (!areas.length) {
            alert('No hay otras áreas en este flujo a las que reportar un quiebre.');
            return;
        }

        // Modal simple armado al vuelo
        const modal = document.createElement('div');
        modal.className = 'modal show gta-quiebre-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3><i class="fas fa-flag"></i> Reportar a otra área</h3>
                <p style="opacity:0.75;">La tarea queda en pausa hasta que esa área resuelva el quiebre.</p>
                <label style="display:block; margin:12px 0 4px;">Área destino</label>
                <select id="qkb-area" style="width:100%; padding:8px;">
                    ${areas.map(a => `<option value="${_esc(a.code)}">${_esc(a.label || a.code)}</option>`).join('')}
                </select>
                <label style="display:block; margin:12px 0 4px;">Descripción del quiebre</label>
                <textarea id="qkb-desc" rows="4" style="width:100%; padding:8px;"
                          placeholder="¿Qué necesitás de esa área? Sé específico."></textarea>
                <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:16px;">
                    <button class="btn-secondary" id="qkb-cancel">Cancelar</button>
                    <button class="btn-danger" id="qkb-ok"><i class="fas fa-flag"></i> Reportar</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const cleanup = () => modal.remove();
        modal.querySelector('#qkb-cancel').onclick = cleanup;
        modal.querySelector('#qkb-ok').onclick = async () => {
            const area = modal.querySelector('#qkb-area').value;
            const desc = modal.querySelector('#qkb-desc').value.trim();
            if (!desc) { alert('La descripción es obligatoria.'); return; }
            try {
                await GtaApi.reportarQuiebreTarea(tareaId, area, desc, null);
                cleanup();
                _tareasExpandidas.delete(tareaId);
                await recargar();
            } catch (e) { alert(_humanizeErr(e)); }
        };
    }

    async function resolverQuiebre(quiebreId) {
        const nota = (prompt('¿Cómo lo resolviste? (nota opcional para que vea el reportante)') ?? null);
        if (nota === null) return;  // canceló
        try {
            await GtaApi.resolverQuiebreTarea(quiebreId, nota);
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Devolver (rechazo de validación → reabre paso destino) ────────
    async function devolver(id) {
        const tarea = _buscarTarea(id);
        const destinos = tarea?.paso_devolver_a_info || [];
        if (!destinos.length) {
            alert('No hay pasos anteriores a los que devolver esta tarea.');
            return;
        }

        // Modal único: siempre selector de paso (cualquier paso anterior) + motivo
        const modal = document.createElement('div');
        modal.className = 'modal show gta-quiebre-modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3><i class="fas fa-undo-alt"></i> Devolver tarea al paso…</h3>
                <p style="opacity:0.75;">Esta tarea se pausa hasta que el paso destino se vuelva a cerrar. Los pasos cerrados intermedios siguen como están; si el responsable del destino modifica datos o adjuntos, esos pasos verán un aviso para revisar.</p>
                <label style="display:block; margin:12px 0 4px;">Devolver al paso</label>
                <select id="dev-destino" style="width:100%; padding:8px;">
                    ${destinos.map(d => `<option value="${d.orden}">Paso ${d.orden} — ${_esc(d.titulo)} (${_esc(d.area_code || '?')})</option>`).join('')}
                </select>
                <label style="display:block; margin:12px 0 4px;">¿Qué tiene que corregir?</label>
                <textarea id="dev-motivo" rows="4" style="width:100%; padding:8px;"
                          placeholder="Describe el problema lo más claro posible (qué dato/archivo está mal, qué falta, etc.)"></textarea>
                <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:16px;">
                    <button class="btn-secondary" id="dev-cancel">Cancelar</button>
                    <button class="btn-danger" id="dev-ok"><i class="fas fa-undo-alt"></i> Devolver</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const cleanup = () => modal.remove();
        modal.querySelector('#dev-cancel').onclick = cleanup;
        modal.querySelector('#dev-ok').onclick = async () => {
            const dest = parseInt(modal.querySelector('#dev-destino').value, 10);
            const motivo = modal.querySelector('#dev-motivo').value.trim();
            if (!motivo) { alert('El motivo es obligatorio.'); return; }
            try {
                await GtaApi.devolverTareaArea(id, motivo, dest);
                cleanup();
                _tareasExpandidas.delete(id);
                await recargar();
            } catch (e) { alert(_humanizeErr(e)); }
        };
    }

    // ── Completar (cerrar + validar obligatorios) ─────────────────────
    async function completar(id) {
        const datos = _recolectarFormulario(id, { validarRequeridos: true });
        if (datos === null) return;
        if (!confirm('¿Completar esta tarea? Una vez cerrada no se puede modificar.')) return;
        try {
            await GtaApi.cerrarTareaArea(id, '', datos);
            _tareasExpandidas.delete(id);
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // Lee los inputs del acordeón de una tarea y valida obligatorios si se pide.
    // Devuelve el dict de datos, o null si hubo error mostrado al usuario.
    function _recolectarFormulario(tareaId, opts = {}) {
        const validar = !!opts.validarRequeridos;
        const inputs = document.querySelectorAll(`#form-tarea-${tareaId} [data-campo-key]`);
        if (!inputs.length) return {};  // sin formulario, datos vacíos

        const datos = {};
        for (const el of inputs) {
            const key = el.getAttribute('data-campo-key');
            const requerido = el.getAttribute('data-requerido') === '1';
            const valor = (el.value || '').toString().trim();
            if (validar && requerido && !valor) {
                const lbl = el.previousElementSibling?.textContent?.replace('*', '').trim() || key;
                alert(`Falta completar: ${lbl}`);
                el.focus();
                return null;
            }
            if (valor) datos[key] = valor;
        }
        return datos;
    }

    // Flash chico de mensaje al guardar borrador
    function _flashMensaje(tareaId, msg, tipo) {
        const card = document.querySelector(`.gta-tarea-card[data-tarea-id="${tareaId}"]`);
        if (!card) { alert(msg); return; }
        const el = document.createElement('div');
        el.className = `gta-flash gta-flash-${tipo || 'ok'}`;
        el.textContent = msg;
        card.appendChild(el);
        setTimeout(() => el.remove(), 2500);
    }

    // ── Asignar/reasignar responsable (popover inline) ────────────────
    async function toggleAsignar(tareaId, anchorEl) {
        // Cerrar cualquier popover abierto antes
        if (_asignarPopover) {
            _asignarPopover.remove();
            _asignarPopover = null;
        }

        const tarea = _findTarea(tareaId);
        if (!tarea) return;

        // Cargar miembros de la subárea (cache)
        let miembros = _miembrosCache.get(tarea.subarea_id);
        if (!miembros) {
            try {
                const r = await window.fetchApi(`/api/gta/membresias/subarea/${tarea.subarea_id}`);
                miembros = r?.items || [];
                _miembrosCache.set(tarea.subarea_id, miembros);
            } catch (e) {
                alert('No se pudo cargar la lista de miembros del área.');
                return;
            }
        }

        // Construir popover
        const myUsername = _sesion?.username || '';
        const myMembership = miembros.find(m => m.username === myUsername);

        const opciones = [];
        // Opción "tomarla yo" si soy miembro y no soy ya el responsable
        if (myMembership && tarea.responsable_username !== myUsername) {
            opciones.push(`<button class="gta-pop-opt gta-pop-yo" onclick="Tareas._asignarA(${tareaId}, ${myMembership.usuario_id}, true)">
                <i class="fas fa-hand-paper"></i> Tomarla yo
            </button>`);
        }
        // Opciones para el resto de miembros (solo admin puede asignar a otros)
        if (_esAdmin) {
            const otros = miembros.filter(m => m.username !== myUsername);
            if (otros.length) {
                opciones.push('<div class="gta-pop-divider">Asignar a:</div>');
                otros.forEach(m => {
                    opciones.push(`<button class="gta-pop-opt" onclick="Tareas._asignarA(${tareaId}, ${m.usuario_id}, false)">
                        <i class="fas fa-user"></i> ${_esc(m.username)}
                    </button>`);
                });
            }
        }

        if (!opciones.length) {
            alert('No hay miembros en esta área. Pídele al admin que asigne membresías.');
            return;
        }

        const pop = document.createElement('div');
        pop.className = 'gta-asignar-popover';
        pop.innerHTML = opciones.join('');
        document.body.appendChild(pop);
        _asignarPopover = pop;

        // Posicionar bajo el anchor
        const rect = anchorEl.getBoundingClientRect();
        pop.style.top = `${rect.bottom + window.scrollY + 4}px`;
        pop.style.left = `${rect.left + window.scrollX}px`;

        // Cerrar al hacer click fuera
        setTimeout(() => {
            const close = (ev) => {
                if (pop.contains(ev.target)) return;
                pop.remove();
                _asignarPopover = null;
                document.removeEventListener('click', close, true);
            };
            document.addEventListener('click', close, true);
        }, 50);
    }

    async function _asignarA(tareaId, usuarioId, esTomarYo) {
        if (_asignarPopover) {
            _asignarPopover.remove();
            _asignarPopover = null;
        }
        try {
            if (esTomarYo) {
                await GtaApi.tomarTareaArea(tareaId);
            } else {
                await GtaApi.reasignarTareaArea(tareaId, { nuevo_usuario_id: usuarioId });
            }
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // Cuando cambia un campo select que tiene hijos dependientes, refrescamos
    // el campo hijo (rerender solo de ese input). Si el hijo tenía un valor
    // que ya no es válido para el nuevo valor del padre, lo limpiamos.
    function _onCampoSelectChange(padreKey, nuevoValor, tareaId) {
        const tarea = _findTarea(tareaId);
        if (!tarea) return;
        const camposProc = tarea.campos_formulario_proceso || [];
        const hijos = camposProc.filter(c => c.tipo === 'select_dependiente' && c.depende_de === padreKey);
        if (!hijos.length) return;

        for (const hijo of hijos) {
            const hijoSelect = document.querySelector(
                `#form-tarea-${tareaId} [data-campo-key="${hijo.key}"]`
            );
            if (!hijoSelect) continue;

            const opciones = (hijo.opciones_por_valor || {})[nuevoValor] || [];
            const valorActual = hijoSelect.value;
            const valorSigueValido = opciones.includes(valorActual);

            // Reconstruir <option>
            let firstOpt;
            if (!nuevoValor) {
                firstOpt = `Primero elegí ${_esc(hijo.depende_de_label || padreKey)}`;
            } else if (!opciones.length) {
                firstOpt = 'Sin opciones disponibles para esta línea';
            } else {
                firstOpt = hijo.ayuda || '— Seleccionar —';
            }
            const sel = (valorSigueValido && nuevoValor) ? valorActual : '';
            hijoSelect.innerHTML = `
                <option value="">${_esc(firstOpt)}</option>
                ${opciones.map(o => `<option value="${_esc(o)}" ${o === sel ? 'selected' : ''}>${_esc(o)}</option>`).join('')}
            `;
            hijoSelect.disabled = !nuevoValor || !opciones.length;
        }
    }

    function _findTarea(id) {
        for (const k of Object.keys(_data)) {
            const t = (_data[k] || []).find(x => x.id === id);
            if (t) return t;
        }
        return null;
    }


    // ── Nueva tarea ───────────────────────────────────────────────────
    function abrirNueva() {
        const sel = document.getElementById('nueva-tarea-subarea');
        if (sel) {
            sel.innerHTML = '<option value="">— Seleccionar —</option>';
            // Por ahora cargamos subáreas a partir del catálogo + un fetch a /membresias/mias
            // Preferimos las del usuario; si no tiene, mostramos todas.
            GtaApi.getMisMembresias().then(r => {
                const items = r.items || [];
                if (items.length) {
                    items.forEach(m => {
                        sel.innerHTML += `<option value="${m.subarea_id}">${_esc(m.area_label)} / ${_esc(m.subarea_label)}</option>`;
                    });
                } else {
                    // Fallback: pedir subáreas al backend (catálogo) — pero el catálogo
                    // no devuelve los IDs numéricos, así que sin membresía el modal queda
                    // limitado. El usuario puede pedir al admin que lo agregue.
                    sel.innerHTML += '<option value="" disabled>No tenés membresía en ninguna subárea — pedile al admin que te asigne</option>';
                }
            });
        }
        document.getElementById('nueva-tarea-titulo').value = '';
        document.getElementById('nueva-tarea-desc').value = '';
        document.getElementById('nueva-tarea-prioridad').value = 'media';
        document.getElementById('nueva-tarea-sla').value = '';
        document.getElementById('modal-nueva-tarea')?.classList.add('show');
    }

    function cerrarNueva() {
        document.getElementById('modal-nueva-tarea')?.classList.remove('show');
    }

    async function guardarNueva() {
        const subarea_id = parseInt(document.getElementById('nueva-tarea-subarea').value || '0', 10);
        const titulo = (document.getElementById('nueva-tarea-titulo').value || '').trim();
        const descripcion = (document.getElementById('nueva-tarea-desc').value || '').trim();
        const prioridad = document.getElementById('nueva-tarea-prioridad').value;
        const slaRaw = document.getElementById('nueva-tarea-sla').value;
        const sla_horas = slaRaw ? parseInt(slaRaw, 10) : null;

        if (!subarea_id) return alert('Seleccioná una subárea.');
        if (!titulo) return alert('El título es obligatorio.');

        try {
            await GtaApi.crearTareaArea({
                subarea_id, titulo, descripcion: descripcion || null,
                prioridad, sla_horas,
            });
            cerrarNueva();
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Agregar colaborador ───────────────────────────────────────────
    function abrirColab(tareaId) {
        document.getElementById('colab-tarea-id').value = tareaId;
        document.getElementById('colab-username').value = '';
        document.getElementById('colab-rol').value = 'ayuda';
        document.getElementById('colab-motivo').value = '';
        document.getElementById('modal-colab')?.classList.add('show');
    }

    function cerrarColab() {
        document.getElementById('modal-colab')?.classList.remove('show');
    }

    async function guardarColab() {
        const tareaId = parseInt(document.getElementById('colab-tarea-id').value, 10);
        const inputRaw = (document.getElementById('colab-username').value || '').trim();
        const rol = document.getElementById('colab-rol').value;
        const motivo = (document.getElementById('colab-motivo').value || '').trim();
        if (!inputRaw) return alert('El usuario es obligatorio.');

        // Resolver el input a usuario_id. Aceptamos:
        //   - ID numérico directo (ej: "24")
        //   - Username completo (ej: "fleon@wolf-industries.tech")
        //   - Prefijo del username (ej: "fleon" → matchea fleon@…)
        // Comparación case-insensitive porque los correos no son sensibles
        // a mayúsculas, y BD los guarda lowercase.
        const inputLower = inputRaw.toLowerCase();
        let usuario_id = null;
        if (/^\d+$/.test(inputRaw)) {
            usuario_id = parseInt(inputRaw, 10);
        } else {
            try {
                const r = await window.fetchApi('/api/config/gta/users');
                const items = r?.items || [];
                const exact = items.find(u => String(u.username || '').toLowerCase() === inputLower);
                if (exact) {
                    usuario_id = exact.id;
                } else {
                    // Prefijo único antes del @: si hay un solo match, lo aceptamos
                    const matches = items.filter(u => String(u.username || '').split('@')[0].toLowerCase() === inputLower);
                    if (matches.length === 1) usuario_id = matches[0].id;
                    else if (matches.length > 1) return alert('Hay más de un usuario con ese prefijo. Ingresá el correo completo.');
                }
            } catch (e) {
                return alert('No se pudo resolver el usuario: ' + _esc(_humanizeErr(e)));
            }
            if (!usuario_id) return alert(`No se encontró un usuario para "${inputRaw}".`);
        }

        if (!Number.isInteger(usuario_id) || usuario_id <= 0) {
            return alert('ID de usuario inválido.');
        }

        try {
            await GtaApi.agregarColaborador(tareaId, {
                usuario_id, rol, motivo: motivo || null,
            });
            cerrarColab();
            await abrirDetalle(tareaId);
        } catch (e) { alert(_humanizeErr(e)); }
    }

    async function quitarColab(tareaId, usuarioId, rol) {
        if (!confirm('¿Quitar a este colaborador?')) return;
        try {
            await GtaApi.quitarColaborador(tareaId, { usuario_id: usuarioId, rol });
            await abrirDetalle(tareaId);
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Helpers ───────────────────────────────────────────────────────
    function _esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function _fmtFecha(iso) {
        try {
            const d = new Date(iso);
            return d.toLocaleString('es-CL', {
                day: '2-digit', month: '2-digit', year: '2-digit',
                hour: '2-digit', minute: '2-digit',
            });
        } catch { return iso; }
    }

    function _humanizeErr(e) {
        if (!e) return 'Error desconocido';
        if (e.detail) return e.detail;
        if (e.message) return e.message;
        return String(e);
    }

    return {
        init, cambiarVista, recargar, filtrarArea,
        // Acciones del acordeón
        toggleExpansion, toggleAsignar, _asignarA, _onCampoSelectChange,
        tomar, liberar, completar, guardarBorrador, devolver,
        subirAdjunto, borrarAdjunto,
        reportarQuiebre, resolverQuiebre,
        agregarComentario, borrarComentario,
        marcarAvisoRevisado,
        // Nueva tarea (sigue siendo modal por ahora)
        abrirNueva, cerrarNueva, guardarNueva,
        // Colaboradores (siguen siendo modal — pendiente de mover al acordeón)
        abrirColab, cerrarColab, guardarColab, quitarColab,
    };
})();
