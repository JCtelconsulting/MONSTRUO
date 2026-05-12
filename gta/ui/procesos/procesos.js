// Procesos — Biblioteca unificada de procesos del GTA
window.Procesos = (() => {
    const ADMIN_ROLES = new Set(['admin']);

    let _procesos = [];
    let _areas = [];
    let _areasUsuario = [];   // áreas visibles según membresías (o todas si admin)
    let _areaFiltro = '';
    let _procActivo = null;
    let _sesion = null;
    let _esAdmin = false;

    // Editor visual del diagrama (modo "Editar visual" — separado del modo
    // "Editar" tradicional con lista). Estado independiente.
    let _modoEditDiag = false;
    let _pasosEditDiag = [];

    // Estado del drag de cajas en el diagrama (modo edición)
    let _dragState = null;
    // Layout del último diagrama renderizado, lo necesitan los handlers de
    // drag para mapear coordenadas de cursor a (columna, fila).
    let _diagLayout = null;

    // ── Init ───────────────────────────────────────────────────────────
    async function init(sesion) {
        _sesion = sesion;
        const role = String(_sesion?.role || '').toLowerCase();
        const roles = (_sesion?.roles || []).map(r => String(r).toLowerCase());
        _esAdmin = ADMIN_ROLES.has(role) || roles.some(r => ADMIN_ROLES.has(r));

        await _cargarAreas();
        await _cargarAreasUsuario();
        await cargar();
    }

    async function _cargarAreas() {
        try {
            const resp = await window.fetchApi('/api/gta/areas');
            _areas = resp?.items || [];
        } catch (e) { _areas = []; }
    }

    async function _cargarAreasUsuario() {
        // Misma lógica que la pestaña Tareas:
        //   admin → todas las áreas activas (de _areas)
        //   usuario común → solo áreas con membresía vigente
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
            console.warn('[Procesos] no se pudo cargar membresías', e);
            _areasUsuario = [];
        }
    }

    async function cargar() {
        const cont = document.getElementById('procs-content');
        if (!cont) return;
        cont.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;
        try {
            const resp = await GtaApi.getProcesos('');
            _procesos = resp?.items || [];
            _renderPills();
            _render();
        } catch (e) {
            cont.innerHTML = `<div class="gta-empty">Error al cargar procesos: ${e.message || e}</div>`;
        }
    }

    function _renderPills() {
        const pills = document.getElementById('procs-area-pills');
        if (!pills) return;
        if (!_areasUsuario.length) {
            pills.innerHTML = '<span class="gta-section-help">No tenés áreas asignadas. Pídele al admin que te asigne membresía.</span>';
            return;
        }
        const html = [];
        if (_esAdmin) {
            html.push(`<button class="gta-area-pill ${_areaFiltro === '' ? 'active' : ''}" data-area="" onclick="Procesos.filtrarArea(this)">Todas</button>`);
        }
        _areasUsuario.forEach(a => {
            html.push(`<button class="gta-area-pill ${_areaFiltro === a.code ? 'active' : ''}" data-area="${a.code}" onclick="Procesos.filtrarArea(this)">${_esc(a.label)}</button>`);
        });
        pills.innerHTML = html.join('');

        // Si no es admin, forzamos que el área activa sea una de las suyas
        if (!_esAdmin && !_areasUsuario.some(a => a.code === _areaFiltro)) {
            _areaFiltro = _areasUsuario[0]?.code || '';
        }
    }

    function filtrarArea(btn) {
        document.querySelectorAll('#procs-area-pills .gta-area-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _areaFiltro = btn.dataset.area || '';
        _render();
    }

    function _filtered() {
        return _procesos.filter(p => !_areaFiltro || p.area === _areaFiltro);
    }

    function _subareaLabel(areaCode, subCode) {
        if (!subCode) return '';
        const a = _areas.find(x => x.code === areaCode);
        const s = a?.subareas?.find(x => x.code === subCode);
        return s ? s.label : subCode;
    }

    // ── Render de pasos: diagrama swimlanes ────────────────────────────

    // Diagrama tipo swimlanes verticales: una columna por área, cada paso en
    // su carril, flechas SVG conectando según depende_de. SVG + CSS puro, sin
    // librerías. Diseñado para parecerse al ejemplo de Visio del usuario.
    function _renderPasosDiagrama(pasos) {
        if (!pasos.length && !_modoEditDiag) return '';
        // Si estamos en modo edición y no hay pasos, igual mostramos las
        // columnas de áreas disponibles (con botón "+") para que el usuario
        // pueda agregar el primer paso desde acá.

        // Áreas únicas presentes en este proceso, ordenadas por el campo
        // 'orden' del catálogo gta.areas (no por aparición). Así el orden
        // visual sigue una secuencia lógica del negocio configurable desde
        // un solo lugar (admin de áreas), en vez de depender de qué paso
        // toca cuál área primero.
        const areasUsadas = new Set(pasos.map(p => p.area_code || p.area || '-'));
        const areasOrden = _areas
            .slice()
            .sort((a, b) => (a.orden || 999) - (b.orden || 999))
            .map(a => a.code)
            .filter(c => areasUsadas.has(c));
        // Fallback defensivo: si alguna área usada no está en _areas
        // (raro — sería un area_code huérfano), agregarla al final.
        for (const c of areasUsadas) {
            if (!areasOrden.includes(c)) areasOrden.push(c);
        }

        // Cada paso queda en su carril. Para el layout vertical, ordenamos
        // los pasos por orden; cada uno ocupa una "fila" del diagrama.
        const sorted = pasos.slice().sort((a, b) => (a.orden || 0) - (b.orden || 0));

        // Dimensiones
        const colW = 180;          // ancho de columna
        const rowH = 90;           // alto de cada fila
        const headerH = 36;        // alto del header de área
        const padTop = 16;
        const boxW = 150;          // ancho de la caja del paso
        const boxH = 60;           // alto de la caja
        const numCols = areasOrden.length;
        const numRows = sorted.length;
        const totalW = numCols * colW + 20;
        // En modo edición agregamos espacio extra abajo para los botones +.
        const extraEditH = _modoEditDiag ? 40 : 0;
        const totalH = headerH + padTop + numRows * rowH + 20 + extraEditH;

        // Posición de cada paso: (col, row) → centro de la caja
        const posPaso = {};
        sorted.forEach((p, i) => {
            const colIdx = areasOrden.indexOf(p.area_code || p.area || '-');
            const cx = colIdx * colW + colW / 2;
            const cy = headerH + padTop + i * rowH + boxH / 2;
            posPaso[p.orden] = { cx, cy, paso: p };
        });

        // SVG: headers de columna, swimlanes verticales, cajas, flechas
        const headers = areasOrden.map((a, idx) => `
            <g>
                <rect x="${idx * colW}" y="0" width="${colW}" height="${headerH}"
                      fill="rgba(0, 243, 255, 0.08)" stroke="rgba(0, 243, 255, 0.3)"></rect>
                <text x="${idx * colW + colW / 2}" y="${headerH / 2 + 5}"
                      text-anchor="middle" fill="#e6edf7" font-size="13" font-weight="700">${_esc(_areaLabel(a))}</text>
            </g>
        `).join('');

        const swimlanes = areasOrden.map((_, idx) => `
            <line x1="${(idx + 1) * colW}" y1="${headerH}" x2="${(idx + 1) * colW}" y2="${totalH - 10}"
                  stroke="rgba(255, 255, 255, 0.08)" stroke-dasharray="4 4"></line>
        `).join('');

        // Cajas con texto en wrap. En modo vista: click → detalle.
        // En modo edición: click → editor del paso, y aparece × en la esquina.
        const cajas = sorted.map(p => {
            const pos = posPaso[p.orden];
            const x = pos.cx - boxW / 2;
            const y = pos.cy - boxH / 2;
            const titulo = (p.titulo || 'Sin título');
            // En vista: click → detalle. En edición: mousedown empieza
            // posible drag; si no hubo movimiento, _dragEnd ejecuta el editor.
            const cursor = _modoEditDiag ? 'move' : 'pointer';
            const onEvent = _modoEditDiag
                ? `onmousedown="Procesos._diagDragStart(${p.orden}, evt)"`
                : `onclick="Procesos.abrirDetallePaso(${p.orden})"`;
            const btnEliminar = _modoEditDiag
                ? `<g class="gta-flow-step-del" onmousedown="event.stopPropagation();" onclick="event.stopPropagation(); Procesos._eliminarPasoDiag(${p.orden})" style="cursor:pointer;">
                       <circle cx="${x + boxW - 8}" cy="${y + 8}" r="10" fill="rgba(255, 51, 51, 0.85)"></circle>
                       <text x="${x + boxW - 8}" y="${y + 12}" text-anchor="middle" fill="#fff" font-size="13" font-weight="700">×</text>
                   </g>`
                : '';
            // Handle de conexión: círculo en el borde inferior central. Drag
            // desde acá crea una flecha (dependencia) hacia otra caja.
            const connectHandle = _modoEditDiag
                ? `<g class="gta-flow-connect-handle"
                      onmousedown="event.stopPropagation(); Procesos._diagConectarStart(${p.orden}, evt)"
                      style="cursor:crosshair;">
                       <circle cx="${pos.cx}" cy="${y + boxH}" r="6" fill="rgba(0, 243, 255, 0.85)" stroke="#fff" stroke-width="1.5">
                           <title>Arrastrá hasta otra caja para conectar</title>
                       </circle>
                   </g>`
                : '';
            return `
                <g class="gta-flow-step" data-paso-orden="${p.orden}"
                   ${onEvent} style="cursor:${cursor};">
                    <rect x="${x}" y="${y}" width="${boxW}" height="${boxH}"
                          rx="8" fill="rgba(0, 243, 255, 0.15)" stroke="rgba(0, 243, 255, 0.6)" stroke-width="1.5"></rect>
                    <foreignObject x="${x + 6}" y="${y + 6}" width="${boxW - 12}" height="${boxH - 12}" pointer-events="none">
                        <div xmlns="http://www.w3.org/1999/xhtml"
                             style="width:100%; height:100%; display:flex; align-items:center; justify-content:center;
                                    text-align:center; color:#e6edf7; font-size:11px; line-height:1.25;
                                    overflow:hidden; word-wrap:break-word; hyphens:auto;">
                            ${_esc(titulo)}
                        </div>
                    </foreignObject>
                    ${btnEliminar}
                    ${connectHandle}
                </g>
            `;
        }).join('');

        // En modo edición: botón "+" debajo de cada columna para agregar
        // un paso en esa área.
        const botonesAgregar = _modoEditDiag ? areasOrden.map((areaCode, idx) => {
            const cx = idx * colW + colW / 2;
            const cy = totalH - 14;
            return `
                <g class="gta-flow-add" onclick="Procesos._agregarPasoDiag('${_esc(areaCode)}')" style="cursor:pointer;">
                    <circle cx="${cx}" cy="${cy}" r="14" fill="rgba(0, 255, 65, 0.18)" stroke="rgba(0, 255, 65, 0.6)" stroke-width="1.5"></circle>
                    <text x="${cx}" y="${cy + 5}" text-anchor="middle" fill="#00ff41" font-size="20" font-weight="700">+</text>
                </g>
            `;
        }).join('') : '';

        // Routing de flechas: salir por el lateral del origen y entrar por
        // el lateral del destino, con la vertical pasando por el canal entre
        // columnas. Evita cruzar cajas intermedias en filas adyacentes.
        // (Si origen y destino están en la misma columna, sale por abajo y
        // entra por arriba — línea recta vertical.)
        const flechas = sorted.flatMap(p => {
            const deps = p.depende_de || [];
            return deps.map(depOrden => {
                const desde = posPaso[depOrden];
                const hasta = posPaso[p.orden];
                if (!desde || !hasta) return '';

                const desdeCol = areasOrden.indexOf(desde.paso.area_code || desde.paso.area || '-');
                const hastaCol = areasOrden.indexOf(hasta.paso.area_code || hasta.paso.area || '-');
                let pathD, sx, sy, ex, ey;

                if (desdeCol === hastaCol) {
                    // Misma columna: línea vertical recta del bottom del origen al top del destino
                    sx = desde.cx;
                    sy = desde.cy + boxH / 2;
                    ex = hasta.cx;
                    ey = hasta.cy - boxH / 2;
                    pathD = `M ${sx} ${sy} L ${ex} ${ey}`;
                } else {
                    // Columnas distintas: salida lateral del origen, vertical en el canal
                    // entre columnas, llegada lateral al destino.
                    const aDerecha = hastaCol > desdeCol;
                    sx = desde.cx + (aDerecha ? boxW / 2 : -boxW / 2);
                    sy = desde.cy;
                    ex = hasta.cx + (aDerecha ? -boxW / 2 : boxW / 2);
                    ey = hasta.cy;
                    const midX = (desde.cx + hasta.cx) / 2;
                    pathD = `M ${sx} ${sy} L ${midX} ${sy} L ${midX} ${ey} L ${ex} ${ey}`;
                }
                // En modo edición: flecha clickeable (eliminar) + handles en los
                // extremos para drag (reasignar origen/destino).
                if (_modoEditDiag) {
                    return `
                        <path d="${pathD}" stroke="rgba(0, 243, 255, 0.5)" stroke-width="1.5" fill="none" marker-end="url(#flowarrow)"></path>
                        <path d="${pathD}" stroke="transparent" stroke-width="14" fill="none" style="cursor:pointer;"
                              onclick="Procesos._diagEliminarDep(${depOrden}, ${p.orden})">
                            <title>Click para eliminar esta dependencia</title>
                        </path>
                        <circle class="gta-flow-arrow-handle" cx="${sx}" cy="${sy}" r="5"
                                fill="rgba(0, 255, 65, 0.85)" stroke="#fff" stroke-width="1"
                                onmousedown="event.stopPropagation(); Procesos._diagFlechaDragStart(${depOrden}, ${p.orden}, 'start', evt)"
                                style="cursor:move;">
                            <title>Arrastrá para cambiar el origen</title>
                        </circle>
                        <circle class="gta-flow-arrow-handle" cx="${ex}" cy="${ey}" r="5"
                                fill="rgba(255, 200, 80, 0.85)" stroke="#fff" stroke-width="1"
                                onmousedown="event.stopPropagation(); Procesos._diagFlechaDragStart(${depOrden}, ${p.orden}, 'end', evt)"
                                style="cursor:move;">
                            <title>Arrastrá para cambiar el destino</title>
                        </circle>
                    `;
                }
                return `<path d="${pathD}" stroke="rgba(0, 243, 255, 0.5)" stroke-width="1.5" fill="none" marker-end="url(#flowarrow)"></path>`;
            });
        }).join('');

        // Guardar layout para que los handlers de drag sepan dónde está cada
        // columna y fila en coordenadas del SVG.
        _diagLayout = { colW, rowH, headerH, padTop, boxW, boxH, areasOrden, totalH };

        // SVG con viewBox + width 100% para que ocupe todo el ancho del
        // contenedor manteniendo proporciones. Las cajas crecen visualmente
        // si la ventana es muy ancha (mejor legibilidad en pantallas grandes).
        const cls = _modoEditDiag ? 'gta-flow-diagram editing' : 'gta-flow-diagram';
        return `
            <div class="${cls}" style="margin-top:8px;">
                <svg viewBox="0 0 ${totalW} ${totalH}" xmlns="http://www.w3.org/2000/svg"
                     preserveAspectRatio="xMidYMid meet"
                     style="width:100%; height:auto; display:block; background:rgba(0,0,0,0.15); border-radius:8px;">
                    <defs>
                        <marker id="flowarrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(0, 243, 255, 0.7)"/>
                        </marker>
                    </defs>
                    ${swimlanes}
                    ${headers}
                    ${flechas}
                    ${cajas}
                    ${botonesAgregar}
                </svg>
            </div>
        `;
    }

    function _areaLabel(code) {
        const a = _areas.find(x => x.code === code);
        return a ? a.label : code;
    }

    // ── Render principal: agrupado por área → subárea ─────────────────
    function _render() {
        const cont = document.getElementById('procs-content');
        if (!cont) return;

        const list = _filtered();

        const porArea = {};
        list.forEach(p => {
            const a = p.area || '_';
            const s = p.subarea_code || '_';
            porArea[a] = porArea[a] || {};
            porArea[a][s] = porArea[a][s] || [];
            porArea[a][s].push(p);
        });

        // Si hay un filtro de área activo, solo muestra esa.
        // Si no, muestra todas las áreas activas (con o sin procesos).
        const activas = _areas.filter(a => a.activo);
        const orderedAreas = _areaFiltro
            ? [_areaFiltro]
            : (activas.length ? activas.map(a => a.code) : Object.keys(porArea).sort());

        // Meter cualquier área que esté en porArea pero no en orderedAreas
        Object.keys(porArea).forEach(c => {
            if (!orderedAreas.includes(c)) orderedAreas.push(c);
        });

        const html = orderedAreas.map(code => {
            const subgroups = porArea[code] || {};
            const subKeys = Object.keys(subgroups).sort((a, b) => {
                if (a === '_') return -1;
                if (b === '_') return 1;
                return a.localeCompare(b);
            });

            const blocks = subKeys.length ? subKeys.map(subCode => {
                const items = subgroups[subCode];
                const subTitle = subCode === '_' ? '' :
                    `<h5 class="gta-doc-subgroup-title"><i class="fas fa-folder"></i> ${_esc(_subareaLabel(code, subCode))} <span class="gta-pill-count">${items.length}</span></h5>`;
                return `
                    <div class="gta-doc-subgroup">
                        ${subTitle}
                        <div class="gta-doc-list">${items.map(_procRow).join('')}</div>
                    </div>
                `;
            }).join('') : '<p class="gta-section-help">Sin procesos cargados todavía.</p>';

            return `
                <div class="gta-doc-area">
                    <h4 class="gta-doc-area-title">
                        <i class="fas fa-layer-group"></i> ${_esc(_areaLabel(code))}
                    </h4>
                    ${blocks}
                </div>
            `;
        }).join('');

        cont.innerHTML = html || '<div class="gta-empty">Sin áreas activas.</div>';
    }

    function _procRow(p) {
        const tieneArchivo = !!p.tiene_archivo;
        const tieneDef = !!p.tiene_definicion;
        const quiebres = Number(p.quiebres_abiertos || 0);
        const flujos = Number(p.flujos_count || 0);
        return `
            <div class="gta-doc-row gta-proc-row" onclick="Procesos.abrir(${p.id})">
                <div class="gta-doc-icon"><i class="fas ${_esc(p.icono || 'fa-file')}"></i></div>
                <div class="gta-doc-info">
                    <div class="gta-doc-name">${_esc(p.nombre)}</div>
                    <div class="gta-doc-meta">
                        ${tieneArchivo ? '<span class="gta-proc-badge has-file" title="Tiene archivo de referencia (PDF/Word) cargado por admin"><i class="fas fa-file"></i> Doc</span>' : ''}
                        ${tieneDef ? '<span class="gta-proc-badge has-def" title="Tiene pasos definidos: se puede iniciar un flujo desde este proceso"><i class="fas fa-cogs"></i> Ejecutable</span>' : ''}
                        ${quiebres ? `<span class="gta-proc-badge has-quiebre" title="${quiebres} quiebre(s) abierto(s) reportado(s) sobre este proceso"><i class="fas fa-flag"></i> ${quiebres}</span>` : ''}
                        ${flujos ? `<span class="gta-proc-badge" title="${flujos} flujo(s) iniciados a partir de este proceso"><i class="fas fa-list-check"></i> ${flujos}</span>` : ''}
                        ${p.descripcion ? `<span class="gta-proc-desc">${_esc(p.descripcion).slice(0, 80)}${p.descripcion.length > 80 ? '…' : ''}</span>` : ''}
                    </div>
                </div>
                <i class="fas fa-chevron-right" style="color:var(--text-soft); opacity:0.5;"></i>
            </div>
        `;
    }

    // ── Modal detalle (vista + edición) ───────────────────────────────
    let _modoEdit = false;
    let _pasosEdit = [];
    let _camposFormEdit = [];

    async function abrir(procId) {
        _modoEdit = false;
        const modal = document.getElementById('modal-proceso');
        const body = document.getElementById('proc-modal-body');
        const footer = document.getElementById('proc-modal-footer');
        document.getElementById('proc-modal-titulo').textContent = 'Cargando...';
        document.getElementById('proc-modal-eyebrow').textContent = `Proceso #${procId}`;
        body.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i></div>`;
        footer.innerHTML = '';
        modal.classList.add('is-open');

        try {
            const proc = await GtaApi.getProceso(procId);
            _procActivo = proc;
            _renderModal(proc);
        } catch (e) {
            body.innerHTML = `<div class="gta-empty">Error al cargar el proceso.</div>`;
        }
    }

    function cerrarModal() {
        document.getElementById('modal-proceso')?.classList.remove('is-open');
        _procActivo = null;
        _modoEdit = false;
        _pasosEdit = [];
    }

    function entrarModoEdicion() {
        if (!_procActivo) return;
        _modoEdit = true;
        _pasosEdit = (_procActivo.pasos_definicion || []).map((p, i) => ({
            orden: p.orden || (i + 1),
            titulo: p.titulo || p.nombre || '',
            descripcion: p.descripcion || '',
            area_code: p.area_code || p.area || '',
            subarea_code: p.subarea_code || null,
            sla_horas: p.sla_horas || 24,
            depende_de: Array.isArray(p.depende_de) ? p.depende_de : [],
            // Por default los pasos son bloqueantes (los que dependen de él
            // esperan a que se cierre). Marcarlo como false permite que los
            // siguientes corran en paralelo sin esperar a éste.
            bloqueante: p.bloqueante !== false,
        }));
        _camposFormEdit = _normalizarCamposForm(_procActivo.campos_formulario);
        _renderModal(_procActivo);
    }

    function salirModoEdicion() {
        _modoEdit = false;
        _pasosEdit = [];
        _renderModal(_procActivo);
    }

    function _renderModal(p) {
        document.getElementById('proc-modal-titulo').textContent = p.nombre || 'Proceso';
        const breadcrumb = `${_areaLabel(p.area)}${p.subarea_code ? ' / ' + _subareaLabel(p.area, p.subarea_code) : ''} · v${p.version || 1}`;
        document.getElementById('proc-modal-eyebrow').textContent = breadcrumb;

        if (_modoEdit) {
            _renderModalEdit(p);
        } else {
            _renderModalView(p);
        }
    }

    function _renderModalView(p) {
        const pasos = p.pasos_definicion || [];
        const flujos = p.flujos || [];
        const quiebres = p.quiebres || [];
        const comentarios = p.comentarios || [];
        const m = p.metricas || {};

        const estadoBadge = _estadoBadge(p.estado);

        // Si estamos en modo edición visual, renderizamos los pasos editados
        // (no los originales). El toolbar va DEBAJO del diagrama, pegado.
        const pasosParaRender = _modoEditDiag ? _pasosEditDiag : pasos;
        const toolbarBajo = _modoEditDiag
            ? `<div class="gta-flow-editor-toolbar gta-flow-editor-toolbar-bottom">
                   <i class="fas fa-pen"></i>
                   <span>Editando diagrama (cambios pendientes de guardar)</span>
                   <button class="btn-sm btn-secondary" onclick="Procesos._cancelarEditDiagrama()">Cancelar</button>
                   <button class="btn-sm btn-primary" onclick="Procesos._guardarEditDiagrama()"><i class="fas fa-check"></i> Guardar cambios</button>
               </div>`
            : (pasos.length
                ? `<div class="gta-flow-editor-toolbar gta-flow-editor-toolbar-bottom">
                       <button class="btn-sm btn-secondary" onclick="Procesos._entrarEditDiagrama()"><i class="fas fa-pen"></i> Editar diagrama</button>
                   </div>`
                : '');
        const pasosHtml = !pasosParaRender.length && !_modoEditDiag
            ? `<div class="gta-empty-pasos">
                  <i class="fas fa-stream"></i>
                  <p><strong>Este proceso no tiene pasos definidos todavía.</strong></p>
                  <p class="gta-section-help">Apretá <em>Editar</em> para construir la fuente de la verdad.</p>
              </div>`
            : _renderPasosDiagrama(pasosParaRender) + toolbarBajo;

        const flujosHtml = flujos.length ? flujos.map(f => `
            <div class="gta-doc-row" style="cursor:default;">
                <div class="gta-doc-icon"><i class="fas fa-list-check"></i></div>
                <div class="gta-doc-info">
                    <div class="gta-doc-name">${_esc(f.titulo)}</div>
                    <div class="gta-doc-meta">
                        <span class="gta-tarea-estado estado-${f.estado}">${f.estado}</span>
                        <span><i class="fas fa-user"></i> ${_esc(f.iniciado_por)}</span>
                        <span><i class="fas fa-list"></i> ${f.completadas}/${f.total_tareas}</span>
                    </div>
                </div>
            </div>
        `).join('') : '<p class="gta-section-help">No se ha ejecutado todavía.</p>';

        const iniciarBtn = pasos.length && p.estado === 'activo'
            ? `<button class="btn-primary" onclick="Procesos.iniciarFlujo(${p.id})"><i class="fas fa-rocket"></i> Iniciar flujo</button>`
            : '';
        // Botón opcional al lado de Iniciar flujo: ver el documento original
        // que sirvió para construir la definición. No es la fuente de verdad
        // (los pasos lo son), pero ayuda a consultarlo si alguien lo necesita.
        const verGuiaBtn = p.archivo_path
            ? `<button class="btn-secondary"
                       title="Ver el documento original que se usó para construir este proceso (PDF, Word, etc.). Los pasos son la fuente de la verdad."
                       onclick="Procesos.abrirDocPreview('${_esc(p.archivo_path)}')">
                  <i class="fas fa-file"></i> Ver guía original
              </button>`
            : '';

        const body = document.getElementById('proc-modal-body');
        body.innerHTML = `
            <div class="gta-flujo-summary">
                <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:8px;">
                    ${estadoBadge}
                </div>
                <div><strong>${_esc(p.descripcion || 'Sin descripción')}</strong></div>
                ${iniciarBtn || verGuiaBtn ? `<div style="margin-top:10px; display:flex; gap:8px; flex-wrap:wrap;">${iniciarBtn}${verGuiaBtn}</div>` : ''}
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:18px;">
                <i class="fas fa-bullseye"></i> Fuente de la verdad — pasos del proceso
            </h4>
            ${pasosHtml}

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-chart-line"></i> Métricas
            </h4>
            <div class="gta-flujo-summary">
                <div style="display:flex; gap:14px; flex-wrap:wrap; font-size:0.85rem; color:var(--text-soft);">
                    <span><i class="fas fa-clock"></i> SLA esperado: ${GtaUi.fmtSla(m.sla_horas_total)}</span>
                    <span><i class="fas fa-stopwatch"></i> Promedio real: ${m.prom_horas != null ? GtaUi.fmtSla(Math.round(m.prom_horas)) : '—'}</span>
                    <span><i class="fas fa-list-check"></i> Flujos completados: ${m.flujos_completados || 0}</span>
                </div>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-list-check"></i> Flujos ejecutados (${flujos.length})
            </h4>
            <div>${flujosHtml}</div>

        `;

        const footer = document.getElementById('proc-modal-footer');
        footer.innerHTML = `
            <button class="btn-secondary" onclick="Procesos.cerrarModal()">Cerrar</button>
            <button class="btn-primary" onclick="Procesos.entrarModoEdicion()">
                <i class="fas fa-pen"></i> Editar
            </button>
        `;
    }

    function _estadoBadge(estado) {
        const e = (estado || 'activo').toLowerCase();
        const map = {
            borrador: '<span class="gta-tarea-estado estado-pendiente"><i class="fas fa-pencil"></i> Borrador</span>',
            activo:   '<span class="gta-tarea-estado estado-completada"><i class="fas fa-check-circle"></i> Activo</span>',
            archivado:'<span class="gta-tarea-estado estado-vencida" style="opacity:0.6;"><i class="fas fa-archive"></i> Archivado</span>',
        };
        return map[e] || `<span class="gta-tarea-estado">${_esc(e)}</span>`;
    }

    function _renderModalEdit(p) {
        const activas = _areas.filter(a => a.activo);
        const subareasDelArea = (() => {
            const a = _areas.find(x => x.code === (p._editArea ?? p.area));
            return (a?.subareas || []).filter(s => s.activo);
        })();

        const estadoActual = (p.estado || 'activo').toLowerCase();

        const body = document.getElementById('proc-modal-body');
        body.innerHTML = `
            <div class="field">
                <label>Nombre del proceso *</label>
                <input type="text" id="ed-nombre" class="input-dark" value="${_esc(p.nombre || '')}">
            </div>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <div class="field" style="flex:1;">
                    <label>Área *</label>
                    <select id="ed-area" class="input-dark" onchange="Procesos._refreshSubareas()">
                        ${activas.map(a => `<option value="${a.code}" ${p.area === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('')}
                    </select>
                </div>
                <div class="field" style="flex:1;">
                    <label>Subárea (opcional)</label>
                    <select id="ed-subarea" class="input-dark">
                        <option value="">— Sin subárea —</option>
                        ${subareasDelArea.map(s => `<option value="${s.code}" ${p.subarea_code === s.code ? 'selected' : ''}>${_esc(s.label)}</option>`).join('')}
                    </select>
                </div>
                <div class="field" style="flex:1;">
                    <label>Estado</label>
                    <select id="ed-estado" class="input-dark">
                        <option value="borrador" ${estadoActual === 'borrador' ? 'selected' : ''}>Borrador</option>
                        <option value="activo" ${estadoActual === 'activo' ? 'selected' : ''}>Activo</option>
                        <option value="archivado" ${estadoActual === 'archivado' ? 'selected' : ''}>Archivado</option>
                    </select>
                </div>
            </div>
            <div class="field" style="margin-top:10px;">
                <label>Descripción breve</label>
                <textarea id="ed-desc" class="input-dark" rows="2">${_esc(p.descripcion || '')}</textarea>
            </div>

            <h4 class="gta-section-subtitle" style="margin-top:18px;">
                <i class="fas fa-bullseye"></i> Pasos — fuente de la verdad
            </h4>
            <p class="gta-section-help">
                Arrastrá los pasos por el ícono <i class="fas fa-grip-vertical"></i> para reordenarlos.
                Cada paso detona una tarea para el área/subárea indicada cuando se ejecuta el flujo.
                Las dependencias usan el número de orden (ej: <code>1,2</code>).
                Marcá <strong>bloqueante</strong> si los pasos siguientes deben esperar a que se cierre.
            </p>
            <div id="ed-pasos" class="gta-flujo-tareas-edit"></div>
            <button class="btn-secondary" onclick="Procesos._agregarPasoEdit()" style="margin-top:8px;">
                <i class="fas fa-plus"></i> Agregar paso
            </button>

            <h4 class="gta-section-subtitle" style="margin-top:24px;">
                <i class="fas fa-clipboard-list"></i> Formulario al iniciar el flujo
            </h4>
            <p class="gta-section-help">
                Datos que se piden al apretar <em>Iniciar flujo</em>. Si un campo está marcado
                como obligatorio, el flujo no arranca sin completarlo.
            </p>
            <div id="ed-campos-form" class="gta-campos-form-edit"></div>
            <button class="btn-secondary" onclick="Procesos._agregarCampoForm()" style="margin-top:8px;">
                <i class="fas fa-plus"></i> Agregar campo
            </button>
        `;
        _renderPasosEdit();
        _renderCamposFormEdit();

        const footer = document.getElementById('proc-modal-footer');
        footer.innerHTML = `
            <button class="btn-secondary" onclick="Procesos.salirModoEdicion()">Cancelar</button>
            <button class="btn-primary" onclick="Procesos.guardarEdicion()">
                <i class="fas fa-save"></i> Guardar cambios
            </button>
        `;
    }

    function _refreshSubareas() {
        const areaCode = document.getElementById('ed-area')?.value || '';
        const a = _areas.find(x => x.code === areaCode);
        const subs = (a?.subareas || []).filter(s => s.activo);
        const subSel = document.getElementById('ed-subarea');
        if (!subSel) return;
        subSel.innerHTML = '<option value="">— Sin subárea —</option>' +
            subs.map(s => `<option value="${s.code}">${_esc(s.label)}</option>`).join('');
    }

    function _renderPasosEdit() {
        const cont = document.getElementById('ed-pasos');
        if (!cont) return;
        const activas = _areas.filter(a => a.activo);
        cont.innerHTML = _pasosEdit.map((t, idx) => {
            const area = _areas.find(a => a.code === t.area_code);
            const subs = (area?.subareas || []).filter(s => s.activo);
            return `
            <div class="gta-paso-edit-row" draggable="true" data-idx="${idx}"
                 ondragstart="Procesos._dragStart(event, ${idx})"
                 ondragover="Procesos._dragOver(event)"
                 ondragleave="Procesos._dragLeave(event)"
                 ondrop="Procesos._drop(event, ${idx})"
                 ondragend="Procesos._dragEnd(event)">
                <div class="gta-paso-edit-handle" title="Arrastrar para reordenar">
                    <i class="fas fa-grip-vertical"></i>
                </div>
                <div class="gta-paso-edit-num">#${t.orden}</div>
                <div class="gta-paso-edit-fields">
                    <input type="text" class="input-dark" placeholder="Título del paso *"
                           value="${_esc(t.titulo)}" oninput="Procesos._setPasoEdit(${idx}, 'titulo', this.value)">
                    <textarea class="input-dark" rows="2" placeholder="Instrucciones / descripción para quien recibe la tarea (opcional)"
                              oninput="Procesos._setPasoEdit(${idx}, 'descripcion', this.value)">${_esc(t.descripcion || '')}</textarea>
                    <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <select class="input-dark" style="flex:2; min-width:140px;" onchange="Procesos._setPasoArea(${idx}, this.value)">
                            <option value="">— Área *</option>
                            ${activas.map(a => `<option value="${a.code}" ${t.area_code === a.code ? 'selected' : ''}>${_esc(a.label)}</option>`).join('')}
                        </select>
                        <select class="input-dark" style="flex:2; min-width:140px;" onchange="Procesos._setPasoEdit(${idx}, 'subarea_code', this.value || null)">
                            <option value="">— Subárea (opcional) —</option>
                            ${subs.map(s => `<option value="${s.code}" ${t.subarea_code === s.code ? 'selected' : ''}>${_esc(s.label)}</option>`).join('')}
                        </select>
                        <input type="number" class="input-dark" min="1" max="999" style="width:80px;"
                               value="${t.sla_horas}" placeholder="SLA h"
                               oninput="Procesos._setPasoEdit(${idx}, 'sla_horas', parseInt(this.value, 10) || 24)"
                               title="SLA en horas">
                        <input type="text" class="input-dark" placeholder="Depende de #"
                               value="${(t.depende_de || []).join(',')}" style="width:110px;"
                               oninput="Procesos._setDepsEdit(${idx}, this.value)"
                               title="Números de paso de los que depende, separados por coma (ej: 1,2)">
                    </div>
                    <label class="gta-paso-edit-bloqueante" title="Si está marcado, los pasos que dependan de éste esperan a que se cierre antes de empezar.">
                        <input type="checkbox" ${t.bloqueante !== false ? 'checked' : ''}
                               onchange="Procesos._setPasoEdit(${idx}, 'bloqueante', this.checked)">
                        <span>Bloqueante (los siguientes esperan a que se cierre)</span>
                    </label>
                </div>
                <button class="btn-sm btn-danger" onclick="Procesos._quitarPasoEdit(${idx})" title="Quitar paso">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        }).join('');
    }

    function _agregarPasoEdit() {
        _pasosEdit.push({
            orden: _pasosEdit.length + 1,
            titulo: '',
            descripcion: '',
            area_code: '',
            subarea_code: null,
            sla_horas: 24,
            depende_de: [],
            bloqueante: true,   // por default los pasos bloquean a sus siguientes
        });
        _renderPasosEdit();
    }

    function _setPasoEdit(idx, k, v) {
        if (_pasosEdit[idx]) _pasosEdit[idx][k] = v;
    }

    function _setPasoArea(idx, areaCode) {
        // Cambiar de área resetea la subárea (las subáreas son hijas del área)
        if (!_pasosEdit[idx]) return;
        _pasosEdit[idx].area_code = areaCode;
        _pasosEdit[idx].subarea_code = null;
        _renderPasosEdit();
    }

    function _setDepsEdit(idx, raw) {
        if (!_pasosEdit[idx]) return;
        _pasosEdit[idx].depende_de = (raw || '').split(',').map(s => parseInt(s.trim(), 10)).filter(Boolean);
    }
    function _quitarPasoEdit(idx) {
        _pasosEdit.splice(idx, 1);
        _pasosEdit.forEach((p, i) => p.orden = i + 1);
        _renderPasosEdit();
    }

    // ── Drag & Drop de pasos ─────────────────────────────────────────────
    let _dragSrcIdx = null;

    function _dragStart(ev, idx) {
        _dragSrcIdx = idx;
        ev.dataTransfer.effectAllowed = 'move';
        // Hack para Firefox: setData es obligatorio o el drag no se inicia
        try { ev.dataTransfer.setData('text/plain', String(idx)); } catch {}
        ev.currentTarget.classList.add('is-dragging');
    }

    function _dragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = 'move';
        ev.currentTarget.classList.add('is-drag-over');
    }

    function _dragLeave(ev) {
        ev.currentTarget.classList.remove('is-drag-over');
    }

    function _drop(ev, dstIdx) {
        ev.preventDefault();
        ev.currentTarget.classList.remove('is-drag-over');
        if (_dragSrcIdx === null || _dragSrcIdx === dstIdx) return;
        const moved = _pasosEdit.splice(_dragSrcIdx, 1)[0];
        _pasosEdit.splice(dstIdx, 0, moved);
        _pasosEdit.forEach((p, i) => p.orden = i + 1);
        _dragSrcIdx = null;
        _renderPasosEdit();
    }

    function _dragEnd(ev) {
        ev.currentTarget.classList.remove('is-dragging');
        document.querySelectorAll('.gta-paso-edit-row.is-drag-over')
            .forEach(el => el.classList.remove('is-drag-over'));
        _dragSrcIdx = null;
    }

    // ── Edición de campos del formulario obligatorio ─────────────────────

    function _renderCamposFormEdit() {
        const cont = document.getElementById('ed-campos-form');
        if (!cont) return;
        if (!_camposFormEdit.length) {
            cont.innerHTML = '<p class="gta-section-help" style="opacity:0.6;">Sin campos definidos. El flujo arranca sin pedir datos.</p>';
            return;
        }

        // Lista de campos tipo select para el dropdown "depende de"
        const camposSelect = _camposFormEdit
            .map((c, i) => ({ ...c, idx: i }))
            .filter(c => c.tipo === 'select' && c.key);

        cont.innerHTML = _camposFormEdit.map((c, idx) => {
            // Header: etiqueta, key, tipo
            const headerHtml = `
                <div style="display:flex; gap:8px;">
                    <input type="text" class="input-dark" placeholder="Etiqueta visible *" style="flex:2;"
                           value="${_esc(c.label || '')}"
                           oninput="Procesos._setCampoForm(${idx}, 'label', this.value)">
                    <input type="text" class="input-dark" placeholder="key (snake_case)" style="flex:1;"
                           value="${_esc(c.key || '')}"
                           oninput="Procesos._setCampoForm(${idx}, 'key', this.value.replace(/[^a-z0-9_]/gi, '_').toLowerCase())">
                    <select class="input-dark" style="width:170px;"
                            onchange="Procesos._setCampoTipo(${idx}, this.value)">
                        <option value="texto" ${c.tipo === 'texto' ? 'selected' : ''}>Texto</option>
                        <option value="textarea" ${c.tipo === 'textarea' ? 'selected' : ''}>Texto largo</option>
                        <option value="numero" ${c.tipo === 'numero' ? 'selected' : ''}>Número</option>
                        <option value="fecha" ${c.tipo === 'fecha' ? 'selected' : ''}>Fecha</option>
                        <option value="select" ${c.tipo === 'select' ? 'selected' : ''}>Lista</option>
                        <option value="select_dependiente" ${c.tipo === 'select_dependiente' ? 'selected' : ''}>Lista dependiente</option>
                    </select>
                </div>
            `;

            // Bloque específico por tipo
            let bloqueTipo = '';
            if (c.tipo === 'select') {
                bloqueTipo = `
                    <input type="text" class="input-dark" placeholder="Opciones separadas por coma (ej: si,no,n/a)" style="margin-top:6px;"
                           value="${_esc((c.opciones || []).join(','))}"
                           oninput="Procesos._setCampoOpciones(${idx}, this.value)">
                `;
            } else if (c.tipo === 'select_dependiente') {
                // Selector de campo padre
                const padreSelect = `
                    <select class="input-dark" style="margin-top:6px;"
                            onchange="Procesos._setCampoDependeDe(${idx}, this.value)">
                        <option value="">— Depende de qué campo —</option>
                        ${camposSelect.map(p => `<option value="${_esc(p.key)}" ${c.depende_de === p.key ? 'selected' : ''}>${_esc(p.label || p.key)} (${_esc(p.key)})</option>`).join('')}
                    </select>
                `;

                // Editor de opciones por valor del padre
                let opcionesPorValorHtml = '';
                if (c.depende_de) {
                    const padre = _camposFormEdit.find(x => x.key === c.depende_de);
                    const valoresPadre = (padre?.opciones || []);
                    if (!valoresPadre.length) {
                        opcionesPorValorHtml = `
                            <p class="gta-section-help" style="margin-top:6px; opacity:0.7;">
                                El campo padre <code>${_esc(c.depende_de)}</code> no tiene opciones aún.
                                Agregalas primero al padre y vuelve aquí.
                            </p>
                        `;
                    } else {
                        opcionesPorValorHtml = `
                            <div style="margin-top:6px;">
                                <p class="gta-section-help" style="margin:0 0 6px 0;">
                                    Opciones disponibles según el valor del padre:
                                </p>
                                ${valoresPadre.map(val => `
                                    <div style="display:flex; gap:8px; margin-bottom:4px; align-items:center;">
                                        <span style="min-width:160px; font-size:12px; color:var(--text-soft); font-weight:600;">${_esc(val)}:</span>
                                        <input type="text" class="input-dark" style="flex:1;"
                                               placeholder="Servicios para esta línea, separados por coma"
                                               value="${_esc(((c.opciones_por_valor || {})[val] || []).join(','))}"
                                               oninput="Procesos._setCampoOpcionesPorValor(${idx}, '${_esc(val).replace(/'/g, '&#39;')}', this.value)">
                                    </div>
                                `).join('')}
                            </div>
                        `;
                    }
                }

                bloqueTipo = padreSelect + opcionesPorValorHtml;
            }

            return `
                <div class="gta-campo-form-row">
                    <div class="gta-campo-form-num">#${idx + 1}</div>
                    <div class="gta-campo-form-fields">
                        ${headerHtml}
                        ${bloqueTipo}
                        <input type="text" class="input-dark" placeholder="Texto de ayuda (opcional)" style="margin-top:6px;"
                               value="${_esc(c.ayuda || '')}"
                               oninput="Procesos._setCampoForm(${idx}, 'ayuda', this.value)">
                        <label class="gta-paso-edit-bloqueante" style="margin-top:4px;">
                            <input type="checkbox" ${c.requerido !== false ? 'checked' : ''}
                                   onchange="Procesos._setCampoForm(${idx}, 'requerido', this.checked)">
                            <span>Obligatorio (no deja completar la tarea sin este dato)</span>
                        </label>
                    </div>
                    <button class="btn-sm btn-danger" onclick="Procesos._quitarCampoForm(${idx})" title="Quitar campo">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
        }).join('');
    }

    function _agregarCampoForm() {
        const n = _camposFormEdit.length + 1;
        _camposFormEdit.push({
            key: `campo_${n}`,
            label: '',
            tipo: 'texto',
            opciones: [],
            requerido: true,
            ayuda: '',
        });
        _renderCamposFormEdit();
    }

    function _setCampoForm(idx, k, v) {
        if (_camposFormEdit[idx]) _camposFormEdit[idx][k] = v;
    }

    function _setCampoTipo(idx, tipo) {
        if (!_camposFormEdit[idx]) return;
        const c = _camposFormEdit[idx];
        c.tipo = tipo;
        // Inicializar campos auxiliares según el tipo nuevo
        if (tipo === 'select' && !Array.isArray(c.opciones)) {
            c.opciones = [];
        }
        if (tipo === 'select_dependiente') {
            if (!c.depende_de) c.depende_de = '';
            if (!c.opciones_por_valor) c.opciones_por_valor = {};
        }
        _renderCamposFormEdit();
    }

    function _setCampoOpciones(idx, raw) {
        if (!_camposFormEdit[idx]) return;
        _camposFormEdit[idx].opciones = (raw || '').split(',').map(s => s.trim()).filter(Boolean);
        // Si hay hijos dependientes que apuntaban a este campo, re-renderizar
        // para que sus mapas de opciones_por_valor se actualicen visualmente.
        _renderCamposFormEdit();
    }

    function _setCampoDependeDe(idx, padreKey) {
        if (!_camposFormEdit[idx]) return;
        _camposFormEdit[idx].depende_de = padreKey;
        // Inicializar opciones_por_valor con las opciones del padre, vacías
        if (padreKey) {
            const padre = _camposFormEdit.find(c => c.key === padreKey);
            const valores = padre?.opciones || [];
            const actual = _camposFormEdit[idx].opciones_por_valor || {};
            const nuevo = {};
            for (const v of valores) {
                nuevo[v] = actual[v] || [];
            }
            _camposFormEdit[idx].opciones_por_valor = nuevo;
        }
        _renderCamposFormEdit();
    }

    function _setCampoOpcionesPorValor(idx, valorPadre, raw) {
        if (!_camposFormEdit[idx]) return;
        if (!_camposFormEdit[idx].opciones_por_valor) _camposFormEdit[idx].opciones_por_valor = {};
        _camposFormEdit[idx].opciones_por_valor[valorPadre] = (raw || '')
            .split(',').map(s => s.trim()).filter(Boolean);
    }

    function _quitarCampoForm(idx) {
        _camposFormEdit.splice(idx, 1);
        _renderCamposFormEdit();
    }

    async function guardarEdicion() {
        if (!_procActivo) return;
        const nombre = document.getElementById('ed-nombre').value.trim();
        const area = document.getElementById('ed-area').value;
        const subareaCode = document.getElementById('ed-subarea')?.value || null;
        const desc = document.getElementById('ed-desc').value.trim();
        const estado = document.getElementById('ed-estado')?.value || 'activo';

        if (!nombre || !area) {
            alert('Nombre y área son obligatorios');
            return;
        }

        // Filtramos pasos sin título o área (incompletos no se guardan).
        // Reordenamos por si quedó algún hueco después del drag&drop.
        const pasos = _pasosEdit
            .filter(p => p.titulo && p.area_code)
            .map((p, i) => ({
                orden: i + 1,
                titulo: p.titulo,
                descripcion: p.descripcion || '',
                area_code: p.area_code,
                subarea_code: p.subarea_code || null,
                sla_horas: p.sla_horas || 24,
                depende_de: Array.isArray(p.depende_de) ? p.depende_de : [],
                bloqueante: p.bloqueante !== false,
            }));

        // Filtramos campos sin label
        const camposForm = (_camposFormEdit || [])
            .filter(c => c.label && c.label.trim())
            .map((c, i) => {
                const base = {
                    key: (c.key || `campo_${i + 1}`).trim() || `campo_${i + 1}`,
                    label: c.label.trim(),
                    tipo: c.tipo || 'texto',
                    opciones: Array.isArray(c.opciones) ? c.opciones.filter(Boolean) : [],
                    requerido: c.requerido !== false,
                    ayuda: (c.ayuda || '').trim(),
                };
                if (c.tipo === 'select_dependiente') {
                    base.depende_de = (c.depende_de || '').trim();
                    base.opciones_por_valor = c.opciones_por_valor || {};
                }
                return base;
            });

        try {
            await GtaApi.actualizarProceso(_procActivo.id, {
                nombre,
                area,
                subarea_code: subareaCode,
                descripcion: desc,
                estado,
                pasos_definicion: JSON.stringify(pasos),
                campos_formulario: JSON.stringify(camposForm),
            });
            _modoEdit = false;
            _pasosEdit = [];
            _camposFormEdit = [];
            await abrir(_procActivo.id);
            await cargar();
        } catch (e) {
            alert('Error: ' + (e.detail || e.message || e));
        }
    }

    // ── Iniciar flujo desde proceso ───────────────────────────────────
    let _iniciarProcId = null;

    function iniciarFlujo(procId) {
        // Modal simple: solo título + descripción. Los campos del formulario
        // los pide la TAREA del paso 1 al cerrarla, no el inicio del flujo.
        _iniciarProcId = procId;
        const proc = _procActivo && _procActivo.id === procId ? _procActivo : _procesos.find(p => p.id === procId);

        const m = document.getElementById('modal-iniciar-flujo');
        if (!m) return;

        document.getElementById('iniciar-flujo-titulo-proceso').textContent = proc?.nombre || 'Proceso';
        document.getElementById('iniciar-flujo-campos').innerHTML = `
            <p class="gta-section-help" style="margin-top:8px;">
                Al iniciar, se va a generar la primera tarea asignada a vos.
                Los datos del proceso se completan al <strong>cerrar</strong> esa tarea,
                y recién ahí se desbloquean las áreas siguientes.
            </p>
        `;
        document.getElementById('iniciar-flujo-titulo').value = '';
        m.classList.add('is-open');
    }

    function cerrarIniciarFlujo() {
        document.getElementById('modal-iniciar-flujo')?.classList.remove('is-open');
        _iniciarProcId = null;
    }

    async function confirmarIniciarFlujo() {
        if (!_iniciarProcId) return;
        const titulo = (document.getElementById('iniciar-flujo-titulo').value || '').trim();
        if (!titulo) return alert('El título del flujo es obligatorio.');

        try {
            await GtaApi.crearFlujo({
                proceso_id: _iniciarProcId,
                titulo,
                datos_formulario: {},  // se llenan al cerrar la tarea del paso 1
            });
            cerrarIniciarFlujo();
            cerrarModal();
            // Después de iniciar, llevamos al usuario a la pestaña Tareas:
            // ahí va a ver el paso 1 ya asignado a él en "Mis tareas".
            await window.GtaCore.loadTab('tareas');
        } catch (e) {
            alert('Error al iniciar flujo: ' + (e.detail || e.message || e));
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    // ── Campos del formulario obligatorio al iniciar el flujo ────────────
    function _normalizarCamposForm(raw) {
        if (Array.isArray(raw)) return raw.map(_normalizarCampo);
        if (typeof raw === 'string' && raw.trim()) {
            try { return (JSON.parse(raw) || []).map(_normalizarCampo); }
            catch { return []; }
        }
        return [];
    }
    function _normalizarCampo(c, i) {
        return {
            key: c.key || `campo_${i + 1}`,
            label: c.label || c.titulo || `Campo ${i + 1}`,
            tipo: c.tipo || 'texto',  // texto | numero | fecha | select
            opciones: Array.isArray(c.opciones) ? c.opciones : [],
            requerido: c.requerido !== false,
            ayuda: c.ayuda || '',
        };
    }

    // ── Preview de documento (guía del proceso) ─────────────────────────
    // ── Editor visual del diagrama ─────────────────────────────────────

    function _entrarEditDiagrama() {
        if (!_procActivo) return;
        // Clonar profundo los pasos para no mutar el _procActivo cargado
        _pasosEditDiag = (_procActivo.pasos_definicion || []).map(p => ({
            orden: p.orden,
            titulo: p.titulo || '',
            descripcion: p.descripcion || '',
            area_code: p.area_code || p.area || '',
            subarea_code: p.subarea_code || null,
            sla_horas: p.sla_horas || 24,
            depende_de: Array.isArray(p.depende_de) ? p.depende_de.slice() : [],
            bloqueante: p.bloqueante !== false,
        }));
        _modoEditDiag = true;
        _renderModal(_procActivo);
    }

    function _cancelarEditDiagrama() {
        if (!_modoEditDiag) return;
        if (_huboCambiosDiag() && !confirm('Hay cambios sin guardar. ¿Descartar?')) return;
        _modoEditDiag = false;
        _pasosEditDiag = [];
        _renderModal(_procActivo);
    }

    function _huboCambiosDiag() {
        const orig = JSON.stringify(_procActivo?.pasos_definicion || []);
        const edit = JSON.stringify(_pasosEditDiag);
        return orig !== edit;
    }

    // ── Drag de cajas (mover entre columnas/filas) ─────────────────────

    // Convierte coordenadas de cursor (clientX/Y) a coordenadas del SVG
    // (las del viewBox, que es donde están las cajas).
    function _svgCoord(svg, clientX, clientY) {
        const pt = svg.createSVGPoint();
        pt.x = clientX;
        pt.y = clientY;
        const ctm = svg.getScreenCTM();
        if (!ctm) return { x: 0, y: 0 };
        const inv = ctm.inverse();
        const r = pt.matrixTransform(inv);
        return { x: r.x, y: r.y };
    }

    function _diagDragStart(pasoOrden, evt) {
        if (!_modoEditDiag) return;
        evt.preventDefault();
        const svg = document.querySelector('.gta-flow-diagram svg');
        if (!svg) return;
        const start = _svgCoord(svg, evt.clientX, evt.clientY);
        _dragState = {
            pasoOrden,
            svg,
            startX: start.x,
            startY: start.y,
            offsetX: 0,
            offsetY: 0,
            moved: false,
        };
        document.addEventListener('mousemove', _diagDragMove);
        document.addEventListener('mouseup', _diagDragEnd);
    }

    function _diagDragMove(evt) {
        if (!_dragState) return;
        const cur = _svgCoord(_dragState.svg, evt.clientX, evt.clientY);
        const dx = cur.x - _dragState.startX;
        const dy = cur.y - _dragState.startY;
        if (!_dragState.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
        _dragState.moved = true;
        _dragState.offsetX = dx;
        _dragState.offsetY = dy;
        // Mover el <g> con un transform translate (visual feedback)
        const g = _dragState.svg.querySelector(`.gta-flow-step[data-paso-orden="${_dragState.pasoOrden}"]`);
        if (g) {
            g.setAttribute('transform', `translate(${dx}, ${dy})`);
            g.style.opacity = '0.85';
        }
    }

    function _diagDragEnd(evt) {
        if (!_dragState) return;
        document.removeEventListener('mousemove', _diagDragMove);
        document.removeEventListener('mouseup', _diagDragEnd);

        const state = _dragState;
        _dragState = null;

        if (!state.moved) {
            // Sin movimiento → tratar como click: abrir editor del paso
            _editarPasoDiag(state.pasoOrden);
            return;
        }

        // Calcular drop: posición final del cursor en coords del SVG
        const drop = _svgCoord(state.svg, evt.clientX, evt.clientY);
        const layout = _diagLayout;
        if (!layout) {
            _renderModal(_procActivo);
            return;
        }

        // Columna destino: por X
        let colIdx = Math.floor(drop.x / layout.colW);
        colIdx = Math.max(0, Math.min(layout.areasOrden.length - 1, colIdx));
        const nuevaArea = layout.areasOrden[colIdx];

        // Fila destino: por Y
        const yRelativa = drop.y - layout.headerH - layout.padTop;
        let rowIdx = Math.floor(yRelativa / layout.rowH);
        // Acotar entre 0 y (cantidad de pasos - 1)
        rowIdx = Math.max(0, Math.min(_pasosEditDiag.length - 1, rowIdx));

        _diagMoverPaso(state.pasoOrden, nuevaArea, rowIdx);
    }

    // Mueve un paso: actualiza area_code y reordena la lista; renumera
    // todos los pasos y actualiza las referencias depende_de.
    function _diagMoverPaso(pasoOrden, nuevaArea, nuevaFila) {
        const idxOrigen = _pasosEditDiag.findIndex(p => p.orden === pasoOrden);
        if (idxOrigen < 0) {
            _renderModal(_procActivo);
            return;
        }
        // Ordenar por orden actual antes de mover
        _pasosEditDiag.sort((a, b) => a.orden - b.orden);
        const paso = _pasosEditDiag[idxOrigen];
        paso.area_code = nuevaArea;

        // Mover en la lista: sacarlo y reinsertarlo en nuevaFila
        _pasosEditDiag.splice(idxOrigen, 1);
        const target = Math.max(0, Math.min(_pasosEditDiag.length, nuevaFila));
        _pasosEditDiag.splice(target, 0, paso);

        // Renumerar a 1..N y construir mapping old→new para actualizar deps
        const mapping = {};
        _pasosEditDiag.forEach((p, i) => {
            mapping[p.orden] = i + 1;
        });
        _pasosEditDiag.forEach((p, i) => {
            p.orden = i + 1;
            p.depende_de = (p.depende_de || []).map(d => mapping[d]).filter(d => d != null);
        });

        _renderModal(_procActivo);
    }

    // ── Drag de flechas (crear dependencia) y click para eliminar ─────

    let _conectarState = null;  // { origenOrden, svg, linePreview }

    function _diagConectarStart(origenOrden, evt) {
        if (!_modoEditDiag) return;
        evt.preventDefault();
        const svg = document.querySelector('.gta-flow-diagram svg');
        if (!svg) return;

        // Crear path de preview que sigue al cursor (línea elástica)
        const start = _svgCoord(svg, evt.clientX, evt.clientY);
        const ns = 'http://www.w3.org/2000/svg';
        const linePreview = document.createElementNS(ns, 'path');
        linePreview.setAttribute('stroke', 'rgba(0, 255, 65, 0.8)');
        linePreview.setAttribute('stroke-width', '2');
        linePreview.setAttribute('stroke-dasharray', '4 3');
        linePreview.setAttribute('fill', 'none');
        linePreview.setAttribute('pointer-events', 'none');
        linePreview.setAttribute('d', `M ${start.x} ${start.y} L ${start.x} ${start.y}`);
        svg.appendChild(linePreview);

        _conectarState = { origenOrden, svg, linePreview, startX: start.x, startY: start.y };
        document.addEventListener('mousemove', _diagConectarMove);
        document.addEventListener('mouseup', _diagConectarEnd);
    }

    function _diagConectarMove(evt) {
        if (!_conectarState) return;
        const cur = _svgCoord(_conectarState.svg, evt.clientX, evt.clientY);
        _conectarState.linePreview.setAttribute(
            'd',
            `M ${_conectarState.startX} ${_conectarState.startY} L ${cur.x} ${cur.y}`,
        );
    }

    function _diagConectarEnd(evt) {
        if (!_conectarState) return;
        document.removeEventListener('mousemove', _diagConectarMove);
        document.removeEventListener('mouseup', _diagConectarEnd);

        const state = _conectarState;
        _conectarState = null;
        // Quitar la línea de preview
        state.linePreview.remove();

        // Detectar sobre qué caja se soltó
        const el = document.elementFromPoint(evt.clientX, evt.clientY);
        if (!el) return;
        const g = el.closest('.gta-flow-step');
        if (!g) return;
        const destinoOrden = parseInt(g.getAttribute('data-paso-orden'), 10);
        if (!destinoOrden || destinoOrden === state.origenOrden) return;

        // Agregar dependencia: destino depende de origen
        const destino = _pasosEditDiag.find(p => p.orden === destinoOrden);
        if (!destino) return;
        destino.depende_de = destino.depende_de || [];
        if (!destino.depende_de.includes(state.origenOrden)) {
            destino.depende_de.push(state.origenOrden);
            destino.depende_de.sort((a, b) => a - b);
            _renderModal(_procActivo);
        }
    }

    // Drag de los extremos de una flecha existente para reasignar
    // origen ('start') o destino ('end').
    let _modificarFlechaState = null;

    function _diagFlechaDragStart(origenOrden, destinoOrden, which, evt) {
        if (!_modoEditDiag) return;
        evt.preventDefault();
        const svg = document.querySelector('.gta-flow-diagram svg');
        if (!svg) return;

        const start = _svgCoord(svg, evt.clientX, evt.clientY);
        const ns = 'http://www.w3.org/2000/svg';
        const preview = document.createElementNS(ns, 'path');
        preview.setAttribute('stroke', which === 'end' ? 'rgba(255, 200, 80, 0.9)' : 'rgba(0, 255, 65, 0.9)');
        preview.setAttribute('stroke-width', '2');
        preview.setAttribute('stroke-dasharray', '4 3');
        preview.setAttribute('fill', 'none');
        preview.setAttribute('pointer-events', 'none');
        preview.setAttribute('d', `M ${start.x} ${start.y} L ${start.x} ${start.y}`);
        svg.appendChild(preview);

        _modificarFlechaState = {
            origenOrden, destinoOrden, which, svg, preview,
            startX: start.x, startY: start.y,
        };
        document.addEventListener('mousemove', _diagFlechaDragMove);
        document.addEventListener('mouseup', _diagFlechaDragEnd);
    }

    function _diagFlechaDragMove(evt) {
        if (!_modificarFlechaState) return;
        const cur = _svgCoord(_modificarFlechaState.svg, evt.clientX, evt.clientY);
        _modificarFlechaState.preview.setAttribute(
            'd',
            `M ${_modificarFlechaState.startX} ${_modificarFlechaState.startY} L ${cur.x} ${cur.y}`,
        );
    }

    function _diagFlechaDragEnd(evt) {
        if (!_modificarFlechaState) return;
        document.removeEventListener('mousemove', _diagFlechaDragMove);
        document.removeEventListener('mouseup', _diagFlechaDragEnd);

        const state = _modificarFlechaState;
        _modificarFlechaState = null;
        state.preview.remove();

        // Sobre qué caja se soltó
        const el = document.elementFromPoint(evt.clientX, evt.clientY);
        if (!el) return;
        const g = el.closest('.gta-flow-step');
        if (!g) return;
        const nuevoOrden = parseInt(g.getAttribute('data-paso-orden'), 10);
        if (!nuevoOrden) return;

        if (state.which === 'end') {
            // Cambiar destino de la flecha
            if (nuevoOrden === state.destinoOrden) return;       // sin cambio
            if (nuevoOrden === state.origenOrden) return;        // self-ref no permitido
            const destinoActual = _pasosEditDiag.find(p => p.orden === state.destinoOrden);
            const destinoNuevo  = _pasosEditDiag.find(p => p.orden === nuevoOrden);
            if (!destinoActual || !destinoNuevo) return;
            destinoActual.depende_de = (destinoActual.depende_de || []).filter(d => d !== state.origenOrden);
            destinoNuevo.depende_de = destinoNuevo.depende_de || [];
            if (!destinoNuevo.depende_de.includes(state.origenOrden)) {
                destinoNuevo.depende_de.push(state.origenOrden);
                destinoNuevo.depende_de.sort((a, b) => a - b);
            }
        } else if (state.which === 'start') {
            // Cambiar origen de la flecha (queda misma flecha pero apunta desde otro paso)
            if (nuevoOrden === state.origenOrden) return;
            if (nuevoOrden === state.destinoOrden) return;
            const destino = _pasosEditDiag.find(p => p.orden === state.destinoOrden);
            if (!destino) return;
            destino.depende_de = (destino.depende_de || []).filter(d => d !== state.origenOrden);
            if (!destino.depende_de.includes(nuevoOrden)) {
                destino.depende_de.push(nuevoOrden);
                destino.depende_de.sort((a, b) => a - b);
            }
        }

        _renderModal(_procActivo);
    }

    function _diagEliminarDep(origenOrden, destinoOrden) {
        if (!confirm(`¿Eliminar la dependencia del paso ${destinoOrden} con respecto al paso ${origenOrden}?`)) return;
        const destino = _pasosEditDiag.find(p => p.orden === destinoOrden);
        if (!destino) return;
        destino.depende_de = (destino.depende_de || []).filter(d => d !== origenOrden);
        _renderModal(_procActivo);
    }

    // Agrega un paso nuevo en el área dada. Por defecto sin deps y orden
    // = max(orden actual) + 1. El usuario edita los detalles después.
    function _agregarPasoDiag(areaCode) {
        const maxOrden = _pasosEditDiag.reduce((m, p) => Math.max(m, p.orden || 0), 0);
        const nuevo = {
            orden: maxOrden + 1,
            titulo: 'Nuevo paso',
            descripcion: '',
            area_code: areaCode,
            subarea_code: null,
            sla_horas: 24,
            depende_de: [],
            bloqueante: true,
        };
        _pasosEditDiag.push(nuevo);
        _renderModal(_procActivo);
        // Abrir editor inmediatamente para que el usuario termine de llenar
        setTimeout(() => _editarPasoDiag(nuevo.orden), 50);
    }

    function _eliminarPasoDiag(pasoOrden) {
        const p = _pasosEditDiag.find(x => x.orden === pasoOrden);
        if (!p) return;
        if (!confirm(`¿Eliminar el paso "${p.titulo}"?`)) return;
        // Quitar el paso y limpiar referencias en depende_de de los demás
        _pasosEditDiag = _pasosEditDiag.filter(x => x.orden !== pasoOrden);
        _pasosEditDiag.forEach(x => {
            x.depende_de = (x.depende_de || []).filter(d => d !== pasoOrden);
        });
        _renderModal(_procActivo);
    }

    // Modal de edición de un paso individual (título, descripción, área,
    // subárea, sla, deps, bloqueante).
    function _editarPasoDiag(pasoOrden) {
        const p = _pasosEditDiag.find(x => x.orden === pasoOrden);
        if (!p) return;

        // Áreas con subáreas para los dropdowns
        const areasActivas = _areas.filter(a => a.activo);
        const subareasDeArea = (code) => {
            const a = _areas.find(x => x.code === code);
            return a?.subareas || [];
        };

        // Dependencias posibles: cualquier paso de orden distinto (para evitar
        // ciclos triviales el usuario marca con cuidado; no validamos grafos
        // complejos acá — el backend ya tolera grafos válidos).
        const otros = _pasosEditDiag.filter(x => x.orden !== pasoOrden)
            .sort((a, b) => a.orden - b.orden);

        const modal = document.createElement('div');
        modal.className = 'modal-backdrop is-open';
        modal.innerHTML = `
            <div class="modal-content" style="max-width:700px;">
                <div class="modal-header">
                    <h2><i class="fas fa-pen"></i> Editar paso</h2>
                    <button class="modal-close-btn" id="ep-close" type="button">×</button>
                </div>
                <div class="modal-body">
                    <div class="field">
                        <label>Título *</label>
                        <input id="ep-titulo" class="input-dark" value="${_esc(p.titulo)}">
                    </div>
                    <div class="field" style="margin-top:10px;">
                        <label>Descripción</label>
                        <textarea id="ep-desc" class="input-dark" rows="3">${_esc(p.descripcion)}</textarea>
                    </div>
                    <div style="display:flex; gap:10px; margin-top:10px;">
                        <div class="field" style="flex:1;">
                            <label>Área *</label>
                            <select id="ep-area" class="input-dark">
                                ${areasActivas.map(a => `<option value="${a.code}" ${a.code===p.area_code?'selected':''}>${_esc(a.label)}</option>`).join('')}
                            </select>
                        </div>
                        <div class="field" style="flex:1;">
                            <label>Subárea</label>
                            <select id="ep-subarea" class="input-dark">
                                <option value="">— Sin subárea —</option>
                                ${subareasDeArea(p.area_code).map(s => `<option value="${s.code}" ${s.code===p.subarea_code?'selected':''}>${_esc(s.label)}</option>`).join('')}
                            </select>
                        </div>
                    </div>
                    <div style="display:flex; gap:10px; margin-top:10px;">
                        <div class="field" style="flex:1;">
                            <label>SLA (horas laborales)</label>
                            <input type="number" id="ep-sla" class="input-dark" min="0" value="${p.sla_horas || 0}">
                        </div>
                        <div class="field" style="flex:1; align-self:flex-end;">
                            <label class="gta-checkbox-label" style="display:flex; align-items:center; gap:6px;">
                                <input type="checkbox" id="ep-bloq" ${p.bloqueante !== false ? 'checked' : ''}>
                                <span>Bloqueante (los siguientes esperan a éste)</span>
                            </label>
                        </div>
                    </div>
                    <div class="field" style="margin-top:14px;">
                        <label>Depende de los pasos:</label>
                        <div class="gta-deps-list">
                            ${otros.length ? otros.map(o => `
                                <label class="gta-dep-check">
                                    <input type="checkbox" data-dep="${o.orden}" ${(p.depende_de||[]).includes(o.orden)?'checked':''}>
                                    <span>${o.orden}. ${_esc(o.titulo)}</span>
                                </label>
                            `).join('') : '<p class="gta-section-help">No hay otros pasos para depender.</p>'}
                        </div>
                    </div>
                </div>
                <div class="modal-footer" style="display:flex; justify-content:flex-end; gap:10px; margin-top:16px;">
                    <button class="btn-secondary" id="ep-cancel" type="button">Cancelar</button>
                    <button class="btn-primary" id="ep-ok" type="button"><i class="fas fa-check"></i> Aplicar</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const cleanup = () => modal.remove();
        modal.querySelector('#ep-close').onclick = cleanup;
        modal.querySelector('#ep-cancel').onclick = cleanup;
        modal.addEventListener('click', (e) => { if (e.target === modal) cleanup(); });

        // Al cambiar área, refrescar subáreas
        modal.querySelector('#ep-area').onchange = (e) => {
            const sel = modal.querySelector('#ep-subarea');
            const subs = subareasDeArea(e.target.value);
            sel.innerHTML = '<option value="">— Sin subárea —</option>' +
                subs.map(s => `<option value="${s.code}">${_esc(s.label)}</option>`).join('');
        };

        modal.querySelector('#ep-ok').onclick = () => {
            const titulo = modal.querySelector('#ep-titulo').value.trim();
            if (!titulo) { alert('El título es obligatorio'); return; }
            p.titulo = titulo;
            p.descripcion = modal.querySelector('#ep-desc').value.trim();
            p.area_code = modal.querySelector('#ep-area').value;
            p.subarea_code = modal.querySelector('#ep-subarea').value || null;
            p.sla_horas = parseInt(modal.querySelector('#ep-sla').value, 10) || 0;
            p.bloqueante = modal.querySelector('#ep-bloq').checked;
            p.depende_de = Array.from(modal.querySelectorAll('[data-dep]:checked'))
                .map(c => parseInt(c.getAttribute('data-dep'), 10))
                .sort((a, b) => a - b);
            cleanup();
            _renderModal(_procActivo);
        };
    }

    async function _guardarEditDiagrama() {
        if (!_procActivo) return;
        try {
            await GtaApi.actualizarProceso(_procActivo.id, {
                pasos_definicion: JSON.stringify(_pasosEditDiag),
            });
            _modoEditDiag = false;
            _pasosEditDiag = [];
            // Recargar el proceso con los cambios guardados
            await abrir(_procActivo.id);
            await cargar();
        } catch (e) {
            alert('Error al guardar: ' + (e.detail || e.message || e));
        }
    }

    // ── Detalle de un paso (click en una caja del diagrama) ────────────
    function abrirDetallePaso(pasoOrden) {
        if (!_procActivo) return;
        const pasos = _procActivo.pasos_definicion || [];
        const paso = pasos.find(p => p.orden === pasoOrden);
        if (!paso) return;

        const depende = (paso.depende_de || []).join(', ') || '—';
        const areaTxt = _areaLabel(paso.area_code || paso.area || '-');
        const subTxt = paso.subarea_code ? ' / ' + _subareaLabel(paso.area_code || paso.area, paso.subarea_code) : '';

        // Modal canónico (modal-backdrop + modal-content del design system)
        const modal = document.createElement('div');
        modal.className = 'modal-backdrop is-open';
        modal.innerHTML = `
            <div class="modal-content" style="max-width:600px;">
                <div class="modal-header">
                    <div>
                        <div class="gta-flujo-drawer-eyebrow">Paso del proceso</div>
                        <h2>${_esc(paso.titulo || 'Sin título')}</h2>
                    </div>
                    <button class="modal-close-btn" id="paso-det-close" type="button">×</button>
                </div>
                <div class="modal-body">
                    ${paso.descripcion ? `<p style="margin:0 0 14px;">${_esc(paso.descripcion)}</p>` : ''}
                    <div class="gta-flujo-summary" style="margin:0;">
                        <div style="display:flex; gap:14px; flex-wrap:wrap; font-size:0.85rem;">
                            <span><i class="fas fa-layer-group"></i> <strong>Área:</strong> ${_esc(areaTxt)}${_esc(subTxt)}</span>
                            <span><i class="fas fa-clock"></i> <strong>SLA:</strong> ${GtaUi.fmtSla(paso.sla_horas)}</span>
                            <span><i class="fas fa-link"></i> <strong>Depende de paso${(paso.depende_de||[]).length>1?'s':''}:</strong> ${_esc(depende)}</span>
                            <span><i class="fas fa-lock"></i> <strong>Bloqueante:</strong> ${paso.bloqueante !== false ? 'sí' : 'no'}</span>
                        </div>
                    </div>
                </div>
                <div class="modal-footer" style="display:flex; justify-content:flex-end; gap:10px; margin-top:20px;">
                    <button class="btn-secondary" id="paso-det-close-2" type="button">Cerrar</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        const cleanup = () => modal.remove();
        modal.querySelector('#paso-det-close').onclick = cleanup;
        modal.querySelector('#paso-det-close-2').onclick = cleanup;
        modal.addEventListener('click', (e) => { if (e.target === modal) cleanup(); });
    }

    async function abrirDocPreview(path) {
        const m = document.getElementById('modal-doc-preview');
        const body = document.getElementById('doc-preview-body');
        const title = document.getElementById('doc-preview-title');
        const footer = document.getElementById('doc-preview-footer');
        if (!m || !body) return;

        m.classList.add('is-open');
        const filename = String(path).split('/').pop() || path;
        if (title) title.textContent = filename;
        body.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando documento…</div>`;
        if (footer) {
            footer.innerHTML = `
                <a href="/api/gta/catalogo/download?path=${encodeURIComponent(path)}" class="btn-secondary" download>
                    <i class="fas fa-download"></i> Descargar
                </a>
                <button class="btn-secondary" onclick="Procesos.cerrarDocPreview()">Cerrar</button>
            `;
        }

        try {
            const meta = await GtaApi.getPreviewMeta(path);
            if (meta.mode === 'iframe') {
                const url = `/api/gta/catalogo/download?path=${encodeURIComponent(path)}`;
                body.innerHTML = `<iframe src="${url}" style="width:100%; height:75vh; border:0; background:#fff;"></iframe>`;
            } else if (meta.mode === 'image') {
                const url = `/api/gta/catalogo/download?path=${encodeURIComponent(path)}`;
                body.innerHTML = `<div style="text-align:center;"><img src="${url}" style="max-width:100%; height:auto; border-radius:8px;"></div>`;
            } else if (meta.mode === 'text') {
                const data = await GtaApi.getPreviewText(path);
                const truncMsg = data.truncated
                    ? `<div class="gta-section-help" style="margin-bottom:10px;"><i class="fas fa-scissors"></i> Documento muy largo, se muestra el inicio (${data.text.length}/${data.total_chars} caracteres). Descargá para ver completo.</div>`
                    : '';
                body.innerHTML = `
                    ${truncMsg}
                    <pre class="gta-doc-preview-text">${_esc(data.text || '(documento vacío)')}</pre>
                `;
            } else {
                body.innerHTML = `
                    <div class="gta-empty" style="padding:40px 20px;">
                        <i class="fas fa-file-circle-question" style="font-size:32px; opacity:0.4;"></i>
                        <p style="margin-top:10px;">No podemos previsualizar este tipo de archivo en el navegador.</p>
                        <p class="gta-section-help">Usá "Descargar" abajo para abrirlo localmente.</p>
                    </div>
                `;
            }
        } catch (e) {
            body.innerHTML = `<div class="gta-empty">Error al cargar preview: ${_esc(e.detail || e.message || e)}</div>`;
        }
    }

    function cerrarDocPreview() {
        document.getElementById('modal-doc-preview')?.classList.remove('is-open');
    }

    return {
        init, cargar, filtrarArea,
        abrir, cerrarModal,
        entrarModoEdicion, salirModoEdicion, guardarEdicion,
        _refreshSubareas, _agregarPasoEdit, _setPasoEdit, _setPasoArea,
        _setDepsEdit, _quitarPasoEdit,
        _dragStart, _dragOver, _dragLeave, _drop, _dragEnd,
        _agregarCampoForm, _setCampoForm, _setCampoTipo, _setCampoOpciones,
        _setCampoDependeDe, _setCampoOpcionesPorValor, _quitarCampoForm,
        iniciarFlujo, cerrarIniciarFlujo, confirmarIniciarFlujo,
        abrirDocPreview, cerrarDocPreview,
        abrirDetallePaso,
        _entrarEditDiagrama, _cancelarEditDiagrama, _guardarEditDiagrama,
        _agregarPasoDiag, _eliminarPasoDiag, _editarPasoDiag,
        _diagDragStart, _diagConectarStart, _diagEliminarDep,
        _diagFlechaDragStart,
    };
})();
