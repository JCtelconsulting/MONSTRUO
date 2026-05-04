// GTA Main v2 — controlador principal
window.GtaCore = (() => {
    let _currentTab = null;
    let _loadedResources = new Set();
    let _selectedProceso = null;
    let _solicitudActiva = null;
    let _sesion = null;

    // ── Init ──────────────────────────────────────────────────────────────
    async function init() {
        try {
            const data = await window.fetchApi('/api/sesion');
            if (data && data.ok) _sesion = data;
        } catch (e) { /* sin sesión */ }

        _aplicarPermisos();
        await loadTab('tablero');
        _cargarBadgeQuiebres();
    }

    function _aplicarPermisos() {
        const role = (_sesion?.role || '').toLowerCase();
        const esAdmin = role === 'admin' || role === 'gerencia';
        if (!esAdmin) {
            document.querySelectorAll('.gta-tab-admin').forEach(el => el.style.display = 'none');
        }
    }

    // ── Tabs ──────────────────────────────────────────────────────────────
    async function loadTab(tabName, triggerEl) {
        if (_currentTab === tabName) return;
        _currentTab = tabName;

        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        const btn = triggerEl || document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
        if (btn) btn.classList.add('active');

        const container = document.getElementById('tab-content');
        if (!container) return;
        container.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;

        try {
            const resp = await fetch(`${tabName}/${tabName}.html`);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            container.innerHTML = await resp.text();

            if (!_loadedResources.has(`css-${tabName}`)) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.href = `${tabName}/${tabName}.css?v=4`;
                document.head.appendChild(link);
                _loadedResources.add(`css-${tabName}`);
            }

            if (!_loadedResources.has(`js-${tabName}`)) {
                const script = document.createElement('script');
                script.src = `${tabName}/${tabName}.js?v=4`;
                document.body.appendChild(script);
                _loadedResources.add(`js-${tabName}`);
                await new Promise(r => { script.onload = r; script.onerror = r; });
            }

            // Llamar init de cada tab
            const inits = {
                tablero: window.Tablero,
                catalogo: window.Catalogo,
                documentos: window.Documentos,
                quiebres: window.Quiebres,
                procesos: window.Procesos,
            };
            if (inits[tabName]?.init) inits[tabName].init(_sesion);
        } catch (e) {
            console.error('Error cargando tab', tabName, e);
            container.innerHTML = GtaUi.empty('Error al cargar la pestaña.');
        }
    }

    // ── Drawer de solicitud ───────────────────────────────────────────────
    async function abrirSolicitud(id) {
        const drawer  = document.getElementById('gta-drawer');
        const overlay = document.getElementById('gta-drawer-overlay');
        const body    = document.getElementById('drawer-body');

        body.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i></div>`;
        drawer.classList.add('open');
        overlay.classList.add('open');

        try {
            const [sol, comentarios] = await Promise.all([
                GtaApi.getSolicitud(id),
                GtaApi.getComentarios(id),
            ]);
            _solicitudActiva = sol;
            document.getElementById('drawer-area-label').textContent = GtaUi.areaLabel(sol.area);
            document.getElementById('drawer-titulo').textContent = sol.titulo;
            body.innerHTML = _renderDrawerBody(sol, comentarios);
        } catch (e) {
            body.innerHTML = GtaUi.empty('Error al cargar solicitud.');
        }
    }

    function _renderDrawerBody(sol, comentarios) {
        const pasos = _parsePasos(sol.pasos_estado || '[]', sol.pasos_definicion || '[]');
        const tiempo = GtaUi.tiempoRestante(sol);
        const completados = pasos.filter(p => p.completado).length;

        return `
        <!-- Info -->
        <div>
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
                <span class="gta-tag ${sol.prioridad}">${sol.prioridad || 'media'}</span>
                <span class="gta-tag estado-${sol.estado}">${GtaUi.estadoLabel(sol.estado)}</span>
                ${tiempo ? `<span class="gta-card-tiempo ${tiempo.clase}"><i class="fas fa-clock"></i> ${tiempo.texto}</span>` : ''}
            </div>
            ${sol.descripcion ? `<p style="color:var(--text-soft);font-size:0.85rem;line-height:1.5;">${GtaUi.escHtml(sol.descripcion)}</p>` : ''}
            <div style="font-size:0.75rem;color:var(--text-soft);margin-top:8px;">
                <i class="fas fa-user"></i> Solicitado por <strong>${GtaUi.escHtml(sol.creado_por)}</strong>
                · <i class="fas fa-calendar"></i> ${GtaUi.fmtFecha(sol.created_at)}
            </div>
        </div>

        <!-- Progreso pasos -->
        <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:1px;font-weight:800;color:var(--text-soft);">
                    Pasos del proceso
                </div>
                <div style="font-size:0.75rem;color:var(--text-soft);">${completados}/${pasos.length}</div>
            </div>
            ${_barraProgreso(completados, pasos.length)}
            <div class="gta-pasos-list" style="margin-top:12px;">
                ${pasos.map((p, i) => _renderPasoDrawer(sol.id, i, p)).join('')}
            </div>
        </div>

        <!-- Comentarios -->
        <div>
            <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:1px;font-weight:800;color:var(--text-soft);margin-bottom:10px;">
                Comentarios (${comentarios.length})
            </div>
            <div class="gta-comentarios" id="drawer-comentarios">
                ${comentarios.length ? comentarios.map(_renderComentario).join('') : `<div style="color:var(--text-soft);font-size:0.82rem;">Sin comentarios aún.</div>`}
            </div>
            <div class="gta-comentario-nuevo" style="margin-top:12px;">
                <textarea id="drawer-nuevo-comentario" class="input-dark" rows="2" placeholder="Escribe un comentario..."></textarea>
                <button class="btn-primary" style="padding:8px 12px;white-space:nowrap;" onclick="GtaCore._enviarComentario(${sol.id})">
                    <i class="fas fa-paper-plane"></i>
                </button>
            </div>
        </div>

        <!-- Acciones -->
        <div style="display:flex; gap:8px; flex-wrap:wrap; padding-top:4px; border-top:1px solid rgba(255,255,255,0.06);">
            ${sol.estado !== 'completado' && sol.estado !== 'cancelado' ? `
            <button class="btn-primary" onclick="GtaCore._cambiarEstado(${sol.id}, 'completado')">
                <i class="fas fa-check"></i> Marcar completado
            </button>` : ''}
            ${sol.estado === 'pendiente' ? `
            <button class="btn-secondary" onclick="GtaCore._cambiarEstado(${sol.id}, 'en_progreso')">
                <i class="fas fa-play"></i> Iniciar
            </button>` : ''}
            <button class="btn-secondary" onclick="GtaCore.abrirModalQuiebre(${sol.id})" style="margin-left:auto;">
                <i class="fas fa-flag"></i> Reportar quiebre
            </button>
        </div>`;
    }

    function _parsePasos(estadoJson, defJson) {
        let estado = []; let def = [];
        try { estado = JSON.parse(estadoJson); } catch {}
        try { def   = JSON.parse(defJson); } catch {}
        return def.map((d, i) => ({
            texto: typeof d === 'string' ? d : d.texto || d,
            completado: estado[i]?.completado || false,
            bloqueado: estado[i]?.bloqueado || false,
        }));
    }

    function _barraProgreso(completados, total) {
        if (!total) return '';
        const pct = Math.round(completados / total * 100);
        const color = pct === 100 ? 'var(--neon)' : pct > 60 ? 'var(--info)' : 'var(--warning)';
        return `<div style="height:4px;background:rgba(255,255,255,0.08);border-radius:4px;overflow:hidden;">
            <div style="height:100%;width:${pct}%;background:${color};transition:width 0.4s ease;"></div>
        </div>`;
    }

    function _renderPasoDrawer(solId, idx, paso) {
        const cls = paso.completado ? 'completado' : paso.bloqueado ? 'bloqueado' : '';
        return `
        <div class="gta-paso-item ${cls}" id="paso-item-${idx}">
            <div class="gta-paso-check" onclick="GtaCore._togglePaso(${solId}, ${idx})">
                ${paso.completado ? '<i class="fas fa-check"></i>' : ''}
            </div>
            <div class="gta-paso-texto">${GtaUi.escHtml(paso.texto)}</div>
            ${!paso.completado && !paso.bloqueado ? `
            <button class="gta-paso-bloqueado-btn" onclick="GtaCore._bloquearPaso(${solId}, ${idx})">
                <i class="fas fa-ban"></i> Bloqueado
            </button>` : ''}
            ${paso.bloqueado ? `<span class="gta-tag" style="color:var(--danger);border-color:rgba(255,51,51,0.3);">Bloqueado</span>` : ''}
        </div>`;
    }

    function _renderComentario(c) {
        return `<div class="gta-comentario">
            <div class="gta-comentario-autor">${GtaUi.escHtml(c.autor)}</div>
            <div class="gta-comentario-texto">${GtaUi.escHtml(c.texto)}</div>
            <div class="gta-comentario-fecha">${GtaUi.fmtFecha(c.created_at)}</div>
        </div>`;
    }

    async function _togglePaso(solId, idx) {
        try {
            await GtaApi.completarPaso(solId, idx);
            abrirSolicitud(solId);
        } catch (e) { alert('Error al actualizar paso'); }
    }

    async function _bloquearPaso(solId, idx) {
        const motivo = prompt('Describe brevemente por qué está bloqueado este paso:');
        if (motivo === null) return;
        try {
            await GtaApi.bloquearPaso(solId, idx, motivo || 'Sin descripción');
            await GtaApi.crearQuiebre({ descripcion: `Paso bloqueado en solicitud #${solId}: ${motivo}`, tipo: 'paso_bloqueado', solicitud_id: solId });
            abrirSolicitud(solId);
            _cargarBadgeQuiebres();
        } catch (e) { alert('Error al reportar bloqueo'); }
    }

    async function _cambiarEstado(solId, estado) {
        try {
            await GtaApi.updateSolicitud(solId, { estado });
            cerrarDrawer();
            if (window.Tablero?.cargar) Tablero.cargar();
        } catch (e) { alert('Error al cambiar estado'); }
    }

    async function _enviarComentario(solId) {
        const ta = document.getElementById('drawer-nuevo-comentario');
        const texto = (ta?.value || '').trim();
        if (!texto) return;
        try {
            await GtaApi.addComentario(solId, texto);
            ta.value = '';
            const resp = await GtaApi.getComentarios(solId);
            const el = document.getElementById('drawer-comentarios');
            if (el) el.innerHTML = resp.map(_renderComentario).join('');
        } catch (e) { alert('Error al enviar comentario'); }
    }

    function cerrarDrawer() {
        document.getElementById('gta-drawer')?.classList.remove('open');
        document.getElementById('gta-drawer-overlay')?.classList.remove('open');
        _solicitudActiva = null;
    }

    // ── Modal nueva solicitud ─────────────────────────────────────────────
    function abrirCatalogo() {
        loadTab('catalogo', document.querySelector('.tab-btn[data-tab="catalogo"]'));
    }

    function seleccionarProceso(procesoId) {
        GtaApi.getProceso(procesoId).then(p => {
            _selectedProceso = p;
            _mostrarModalSolicitud(p);
        }).catch(() => alert('Error al cargar proceso'));
    }

    function _mostrarModalSolicitud(p) {
        const pasos = _parsePasosDefinicion(p.pasos_definicion || '[]');
        const campos = _parseCampos(p.campos_formulario || '[]');

        document.getElementById('modal-solicitud-titulo').textContent = p.nombre;
        document.getElementById('modal-solicitud-body').innerHTML = `
            <div class="gta-solicitud-proceso-info">
                <i class="fas ${p.icono || 'fa-tasks'}"></i>
                <div>
                    <strong>${GtaUi.escHtml(p.nombre)}</strong>
                    <span>${GtaUi.areaLabel(p.area)} ${p.sla_horas ? `· SLA: ${p.sla_horas}h` : ''}</span>
                </div>
            </div>

            ${pasos.length ? `
            <div class="gta-pasos-preview">
                <div class="gta-pasos-preview-title">Este proceso tiene ${pasos.length} pasos</div>
                ${pasos.map((t, i) => `
                <div class="gta-paso-preview">
                    <div class="gta-paso-num">${i+1}</div>
                    <div>${GtaUi.escHtml(t)}</div>
                </div>`).join('')}
            </div>` : ''}

            <div class="field">
                <label>Descripción de tu solicitud</label>
                <textarea id="solicitud-descripcion" class="input-dark" rows="3"
                    placeholder="Describe qué necesitas con el mayor detalle posible..."></textarea>
            </div>
            <div class="field" style="margin-top:12px;">
                <label>Prioridad</label>
                <select id="solicitud-prioridad" class="input-dark">
                    <option value="media">Media</option>
                    <option value="alta">Alta</option>
                    <option value="baja">Baja</option>
                </select>
            </div>
            ${campos.map(c => `
            <div class="field" style="margin-top:12px;">
                <label>${GtaUi.escHtml(c.label)}${c.required ? ' *' : ''}</label>
                <input type="${c.type || 'text'}" class="input-dark campo-extra" data-key="${GtaUi.escHtml(c.key)}"
                    placeholder="${GtaUi.escHtml(c.placeholder || '')}">
            </div>`).join('')}
        `;

        const modal = document.getElementById('modal-nueva-solicitud');
        modal.style.display = 'flex';
    }

    function _parsePasosDefinicion(json) {
        try {
            const arr = JSON.parse(json);
            return arr.map(p => typeof p === 'string' ? p : p.texto || '');
        } catch { return []; }
    }

    function _parseCampos(json) {
        try { return JSON.parse(json); } catch { return []; }
    }

    async function confirmarSolicitud() {
        if (!_selectedProceso) return;
        const desc     = document.getElementById('solicitud-descripcion')?.value?.trim();
        const prioridad = document.getElementById('solicitud-prioridad')?.value || 'media';
        if (!desc) { alert('Describe tu solicitud antes de enviar.'); return; }

        const extras = {};
        document.querySelectorAll('.campo-extra').forEach(el => {
            extras[el.dataset.key] = el.value;
        });

        try {
            await GtaApi.crearSolicitud({
                proceso_id: _selectedProceso.id,
                titulo: _selectedProceso.nombre,
                descripcion: desc,
                prioridad,
                area: _selectedProceso.area,
                campos_extra: JSON.stringify(extras),
            });
            cerrarModalSolicitud();
            loadTab('tablero', document.querySelector('.tab-btn[data-tab="tablero"]'));
            _currentTab = null; // forzar reload
            loadTab('tablero', document.querySelector('.tab-btn[data-tab="tablero"]'));
        } catch (e) { alert('Error al crear solicitud'); }
    }

    function cerrarModalSolicitud() {
        document.getElementById('modal-nueva-solicitud').style.display = 'none';
        _selectedProceso = null;
    }

    // ── Modal quiebre ─────────────────────────────────────────────────────
    function abrirModalQuiebre(solicitudId) {
        if (solicitudId) document.getElementById('quiebre-solicitud-ref').value = `#${solicitudId}`;
        document.getElementById('modal-quiebre').style.display = 'flex';
    }

    function cerrarModalQuiebre() {
        document.getElementById('modal-quiebre').style.display = 'none';
        document.getElementById('quiebre-descripcion').value = '';
        document.getElementById('quiebre-area').value = '';
        document.getElementById('quiebre-solicitud-ref').value = '';
    }

    async function enviarQuiebre() {
        const desc = document.getElementById('quiebre-descripcion')?.value?.trim();
        const area = document.getElementById('quiebre-area')?.value;
        if (!desc) { alert('Describe el problema.'); return; }
        if (!area) { alert('Selecciona el área involucrada.'); return; }
        try {
            await GtaApi.crearQuiebre({ descripcion: desc, area, tipo: 'sin_proceso' });
            cerrarModalQuiebre();
            _cargarBadgeQuiebres();
            alert('Quiebre reportado. El equipo responsable será notificado.');
        } catch (e) { alert('Error al reportar quiebre'); }
    }

    async function resolverQuiebre(id) {
        const nota = prompt('¿Cómo se resolvió? (opcional)') ?? '';
        try {
            await GtaApi.resolverQuiebre(id, nota);
            if (window.Quiebres?.cargar) Quiebres.cargar();
            _cargarBadgeQuiebres();
        } catch (e) { alert('Error al resolver quiebre'); }
    }

    function abrirQuiebre(id) {
        // Por ahora abre el drawer de la solicitud relacionada si existe
    }

    function irAQuiebres() {
        loadTab('quiebres', document.querySelector('.tab-btn[data-tab="quiebres"]'));
    }

    async function _cargarBadgeQuiebres() {
        try {
            const data = await GtaApi.getQuiebres('?estado=abierto');
            const count = Array.isArray(data) ? data.length : 0;
            const badge = document.getElementById('gta-quiebres-badge');
            const countEl = document.getElementById('gta-quiebres-count');
            if (badge && countEl) {
                countEl.textContent = count;
                badge.style.display = count > 0 ? 'block' : 'none';
                const tabBtn = document.getElementById('tab-btn-quiebres');
                if (tabBtn && count > 0) {
                    tabBtn.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:var(--warning)"></i> Quiebres <span style="color:var(--warning);font-weight:800;">(${count})</span>`;
                }
            }
        } catch {}
    }

    return {
        init, loadTab,
        abrirSolicitud, cerrarDrawer,
        abrirCatalogo, seleccionarProceso, confirmarSolicitud, cerrarModalSolicitud,
        abrirModalQuiebre, cerrarModalQuiebre, enviarQuiebre, resolverQuiebre, abrirQuiebre,
        irAQuiebres,
        _togglePaso, _bloquearPaso, _cambiarEstado, _enviarComentario,
    };
})();
