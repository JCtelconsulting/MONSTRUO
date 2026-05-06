// GTA — Tab Tareas (modelo área-céntrico)
window.Tareas = (() => {
    let _sesion = null;
    let _vista = 'bandeja';      // bandeja | mias | colaboro
    let _subareas = [];
    let _data = { bandeja: [], mias: [], colaboro: [] };

    // ── Init ──────────────────────────────────────────────────────────
    async function init(sesion) {
        _sesion = sesion;
        await cargarSubareasCatalogo();
        await recargar();
    }

    async function cargarSubareasCatalogo() {
        try {
            const r = await GtaApi.getDocumentos();
            // El catálogo agrupa areas con subareas dentro
            const subs = [];
            (r.areas || []).forEach(a => {
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
            console.warn('[Tareas] no se pudo cargar catálogo de subáreas', e);
            _subareas = [];
        }
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
        const bL = _data.bandeja?.length;
        const mL = _data.mias?.length;
        const cL = _data.colaboro?.length;
        const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = (v ?? '—'); };
        set('count-bandeja',  bL);
        set('count-mias',     mL);
        set('count-colaboro', cL);
    }

    function _render() {
        const cont = document.getElementById('tareas-content');
        if (!cont) return;
        const items = _data[_vista] || [];
        if (!items.length) {
            cont.innerHTML = `<div class="gta-empty-state">
                <i class="fas ${_vista === 'bandeja' ? 'fa-inbox' : 'fa-circle-check'}"></i>
                ${_emptyMsg(_vista)}
            </div>`;
            return;
        }
        cont.innerHTML = items.map(t => _cardHtml(t, _vista)).join('');
    }

    function _emptyMsg(vista) {
        if (vista === 'bandeja')  return 'No hay tareas sin responsable en tus áreas.';
        if (vista === 'mias')     return 'No tenés tareas asignadas.';
        if (vista === 'colaboro') return 'No estás colaborando en ninguna tarea.';
        return 'Sin tareas.';
    }

    function _cardHtml(t, vista) {
        const sinResp = !t.responsable_id;
        const fechaCorta = t.created_at ? _fmtFecha(t.created_at) : '';
        const slaTxt = t.sla_due_at ? `SLA: ${_fmtFecha(t.sla_due_at)}` : (t.sla_horas ? `SLA: ${t.sla_horas}h` : '');
        const respTxt = t.responsable_username ? `<span><i class="fas fa-user"></i> ${_esc(t.responsable_username)}</span>` : '';

        const acciones = [];
        if (vista === 'bandeja') {
            acciones.push(`<button class="btn-tomar" onclick="event.stopPropagation(); Tareas.tomar(${t.id})">Tomar</button>`);
        }
        if (vista === 'mias') {
            acciones.push(`<button onclick="event.stopPropagation(); Tareas.liberar(${t.id})">Liberar</button>`);
            acciones.push(`<button onclick="event.stopPropagation(); Tareas.cerrar(${t.id})">Cerrar</button>`);
        }

        return `
            <div class="gta-tarea-card ${sinResp ? 'sin-responsable' : ''}" onclick="Tareas.abrirDetalle(${t.id})">
                <div class="gta-tarea-card-top">
                    <h3 class="gta-tarea-card-titulo">${_esc(t.titulo)}</h3>
                    <div class="gta-tarea-card-meta">
                        <span class="pill gta-prioridad-${t.prioridad}">${_esc(t.prioridad)}</span>
                        <span class="pill gta-estado-${t.estado}">${_esc(t.estado.replace('_', ' '))}</span>
                    </div>
                </div>
                ${t.descripcion ? `<p class="gta-tarea-card-desc">${_esc(t.descripcion)}</p>` : ''}
                <div class="gta-tarea-card-foot">
                    <span><i class="fas fa-folder"></i> ${_esc(t.area_label || '—')} / ${_esc(t.subarea_label || '—')}</span>
                    ${respTxt}
                    ${slaTxt ? `<span><i class="fas fa-clock"></i> ${_esc(slaTxt)}</span>` : ''}
                    ${fechaCorta ? `<span><i class="fas fa-calendar"></i> ${_esc(fechaCorta)}</span>` : ''}
                    <div class="gta-tarea-card-actions">${acciones.join('')}</div>
                </div>
            </div>
        `;
    }

    // ── Acciones ──────────────────────────────────────────────────────
    async function tomar(id) {
        try {
            await GtaApi.tomarTareaArea(id);
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    async function liberar(id) {
        const motivo = prompt('Motivo (opcional):') || '';
        try {
            await GtaApi.liberarTareaArea(id, motivo);
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    async function cerrar(id) {
        const reporte = prompt('Reporte de cierre (opcional):') || '';
        if (!confirm('¿Cerrar la tarea?')) return;
        try {
            await GtaApi.cerrarTareaArea(id, reporte);
            await recargar();
        } catch (e) { alert(_humanizeErr(e)); }
    }

    // ── Detalle ───────────────────────────────────────────────────────
    async function abrirDetalle(id) {
        const m = document.getElementById('modal-tarea');
        const body = document.getElementById('tarea-modal-body');
        const tit = document.getElementById('tarea-modal-titulo');
        const eyebrow = document.getElementById('tarea-modal-eyebrow');
        const foot = document.getElementById('tarea-modal-footer');
        if (!m) return;
        m.classList.add('show');
        if (body) body.innerHTML = '<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i></div>';
        try {
            const t = await GtaApi.getTareaArea(id);
            if (tit) tit.textContent = t.titulo || 'Tarea';
            if (eyebrow) eyebrow.textContent = `${t.area_label || ''} / ${t.subarea_label || ''}`;
            if (body) body.innerHTML = _detalleHtml(t);
            if (foot) foot.innerHTML = _detalleFooter(t);
        } catch (e) {
            if (body) body.innerHTML = `<div class="gta-empty-state">Error: ${_humanizeErr(e)}</div>`;
        }
    }

    function _detalleHtml(t) {
        const respHtml = t.responsable_actual
            ? `<div class="gta-tarea-participante">
                   <span><i class="fas fa-user-check"></i> ${_esc(t.responsable_actual.username)}</span>
                   <span class="pill">Responsable</span>
               </div>`
            : `<div class="gta-empty-state" style="padding:12px;">Sin responsable asignado</div>`;

        const colabsHtml = (t.colaboradores_actuales || []).map(c => `
            <div class="gta-tarea-participante">
                <span><i class="fas fa-handshake"></i> ${_esc(c.username)}</span>
                <span style="display:flex; gap:6px; align-items:center;">
                    <span class="pill">${_esc(c.rol.replace('_', ' '))}</span>
                    <button class="btn-secondary" style="padding:2px 8px; font-size:11px;"
                            onclick="Tareas.quitarColab(${t.id}, ${c.usuario_id}, '${_esc(c.rol)}')">Quitar</button>
                </span>
            </div>
        `).join('');

        return `
            <div class="gta-tarea-section">
                <h3>Descripción</h3>
                <div>${t.descripcion ? _esc(t.descripcion) : '<em style="opacity:0.6;">Sin descripción</em>'}</div>
            </div>
            <div class="gta-tarea-section">
                <h3>Estado</h3>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <span class="pill gta-estado-${t.estado}">${_esc(t.estado.replace('_', ' '))}</span>
                    <span class="pill gta-prioridad-${t.prioridad}">${_esc(t.prioridad)}</span>
                    ${t.sla_due_at ? `<span class="pill"><i class="fas fa-clock"></i> ${_fmtFecha(t.sla_due_at)}</span>` : ''}
                </div>
            </div>
            <div class="gta-tarea-section">
                <h3>Responsable</h3>
                <div class="gta-tarea-participantes">${respHtml}</div>
            </div>
            <div class="gta-tarea-section">
                <h3>Colaboradores
                    <button class="btn-secondary" style="float:right; padding:2px 10px; font-size:11px;"
                            onclick="Tareas.abrirColab(${t.id})"><i class="fas fa-plus"></i> Agregar</button>
                </h3>
                <div class="gta-tarea-participantes">
                    ${colabsHtml || '<div class="gta-empty-state" style="padding:12px;">Sin colaboradores</div>'}
                </div>
            </div>
        `;
    }

    function _detalleFooter(t) {
        const acciones = [];
        if (t.estado !== 'cerrada' && t.estado !== 'cancelada') {
            const myUsername = _sesion?.username;
            const soyResp = t.responsable_actual && t.responsable_actual.username === myUsername;
            if (!t.responsable_actual) {
                acciones.push(`<button class="btn-primary" onclick="Tareas.tomar(${t.id}); Tareas.cerrarModal();">Tomar tarea</button>`);
            } else if (soyResp) {
                acciones.push(`<button class="btn-secondary" onclick="Tareas.liberar(${t.id}); Tareas.cerrarModal();">Liberar</button>`);
                acciones.push(`<button class="btn-primary" onclick="Tareas.cerrar(${t.id}); Tareas.cerrarModal();">Cerrar tarea</button>`);
            }
        }
        return acciones.join(' ');
    }

    function cerrarModal() {
        document.getElementById('modal-tarea')?.classList.remove('show');
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
        init, cambiarVista, recargar,
        tomar, liberar, cerrar,
        abrirDetalle, cerrarModal,
        abrirNueva, cerrarNueva, guardarNueva,
        abrirColab, cerrarColab, guardarColab, quitarColab,
    };
})();
