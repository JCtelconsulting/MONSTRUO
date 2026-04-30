// Procesos — admin del catálogo (solo admin/gerencia)
window.Procesos = (() => {
    let _datos = [];
    let _pasosCount = 0;
    let _camposCount = 0;

    function init(sesion) {
        const role = (sesion?.role || '').toLowerCase();
        if (role !== 'admin' && role !== 'gerencia') {
            document.querySelector('.gta-procesos').innerHTML =
                GtaUi.empty('No tienes permisos para administrar procesos.');
            return;
        }
        cargar();
    }

    async function cargar() {
        const tbody = document.getElementById('procesos-tbody');
        if (!tbody) return;
        try {
            const data = await GtaApi.getProcesos();
            _datos = Array.isArray(data) ? data : [];
            filtrar();
        } catch (e) {
            if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--danger);padding:2rem;">Error al cargar procesos.</td></tr>`;
        }
    }

    function filtrar(texto) {
        const tbody = document.getElementById('procesos-tbody');
        if (!tbody) return;
        const q      = (texto || document.getElementById('procesos-search')?.value || '').toLowerCase();
        const area   = document.getElementById('procesos-filtro-area')?.value || '';
        const estado = document.getElementById('procesos-filtro-estado')?.value ?? 'activo';

        let lista = _datos;
        if (q)      lista = lista.filter(p => p.nombre.toLowerCase().includes(q));
        if (area)   lista = lista.filter(p => p.area === area);
        if (estado) lista = lista.filter(p => p.estado === estado);

        if (!lista.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:2rem;color:var(--text-soft);">Sin procesos para este filtro.</td></tr>`;
            return;
        }

        tbody.innerHTML = lista.map(p => `
        <tr>
            <td>
                <div style="display:flex;align-items:center;gap:8px;">
                    <i class="fas ${p.icono || 'fa-tasks'}" style="color:var(--neon);opacity:0.7;"></i>
                    <strong>${GtaUi.escHtml(p.nombre)}</strong>
                </div>
                ${p.descripcion ? `<div style="color:var(--text-soft);font-size:0.78rem;margin-top:3px;">${GtaUi.escHtml(p.descripcion)}</div>` : ''}
            </td>
            <td><span class="gta-tag">${GtaUi.areaLabel(p.area)}</span></td>
            <td style="color:var(--text-soft);">${p.pasos_count || 0}</td>
            <td style="color:var(--text-soft);">${p.sla_horas ? `${p.sla_horas}h` : '—'}</td>
            <td style="color:var(--text-soft);">${p.solicitudes_count || 0}</td>
            <td>
                <span class="gta-tag ${p.estado === 'activo' ? 'baja' : ''}">${p.estado === 'activo' ? 'Activo' : 'Inactivo'}</span>
            </td>
            <td style="display:flex;gap:6px;justify-content:flex-end;">
                <button class="btn-sm" onclick="Procesos.abrirFormulario(${p.id})"><i class="fas fa-edit"></i></button>
                <button class="btn-sm btn-danger" onclick="Procesos.toggleEstado(${p.id}, '${p.estado}')">
                    ${p.estado === 'activo' ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>'}
                </button>
            </td>
        </tr>`).join('');
    }

    function abrirFormulario(id) {
        _pasosCount = 0;
        _camposCount = 0;
        document.getElementById('proceso-id').value = id || '';
        document.getElementById('modal-proceso-titulo').textContent = id ? 'Editar Proceso' : 'Nuevo Proceso';
        document.getElementById('proceso-pasos-lista').innerHTML = '';
        document.getElementById('proceso-campos-lista').innerHTML = '';

        if (id) {
            GtaApi.getProceso(id).then(p => {
                document.getElementById('proceso-nombre').value       = p.nombre || '';
                document.getElementById('proceso-area').value         = p.area || '';
                document.getElementById('proceso-descripcion').value  = p.descripcion || '';
                document.getElementById('proceso-sla').value          = p.sla_horas || '';
                document.getElementById('proceso-icono').value        = p.icono || '';

                const pasos = _parsePasos(p.pasos_definicion || '[]');
                pasos.forEach(t => agregarPaso(t));

                const campos = _parseCampos(p.campos_formulario || '[]');
                campos.forEach(c => agregarCampo(c));
            });
        } else {
            ['proceso-nombre','proceso-area','proceso-descripcion','proceso-sla','proceso-icono'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });
            agregarPaso();
        }

        document.getElementById('modal-proceso').style.display = 'flex';
    }

    function cerrarFormulario() {
        document.getElementById('modal-proceso').style.display = 'none';
    }

    function agregarPaso(texto = '') {
        _pasosCount++;
        const idx = _pasosCount;
        const div = document.createElement('div');
        div.className = 'gta-paso-editor';
        div.id = `paso-editor-${idx}`;
        div.innerHTML = `
            <i class="fas fa-grip-vertical gta-paso-drag"></i>
            <input type="text" placeholder="Descripción del paso ${idx}..." value="${GtaUi.escHtml(texto)}" data-paso-idx="${idx}">
            <button type="button" class="btn-sm btn-danger" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>`;
        document.getElementById('proceso-pasos-lista').appendChild(div);
    }

    function agregarCampo(campo = null) {
        _camposCount++;
        const idx = _camposCount;
        const div = document.createElement('div');
        div.className = 'gta-paso-editor';
        div.innerHTML = `
            <input type="text" placeholder="Clave (ej: cliente)" value="${GtaUi.escHtml(campo?.key || '')}" data-campo-key="${idx}" style="flex:0.5;">
            <input type="text" placeholder="Etiqueta (ej: Cliente)" value="${GtaUi.escHtml(campo?.label || '')}" data-campo-label="${idx}" style="flex:1;">
            <select data-campo-type="${idx}" style="background:rgba(8,12,18,0.8);border:1px solid rgba(255,255,255,0.12);color:#fff;border-radius:8px;padding:6px 8px;">
                <option value="text" ${campo?.type === 'text' ? 'selected' : ''}>Texto</option>
                <option value="number" ${campo?.type === 'number' ? 'selected' : ''}>Número</option>
                <option value="date" ${campo?.type === 'date' ? 'selected' : ''}>Fecha</option>
                <option value="textarea" ${campo?.type === 'textarea' ? 'selected' : ''}>Área de texto</option>
            </select>
            <button type="button" class="btn-sm btn-danger" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>`;
        document.getElementById('proceso-campos-lista').appendChild(div);
    }

    function _parsePasos(json) {
        try { const a = JSON.parse(json); return a.map(p => typeof p === 'string' ? p : p.texto || ''); }
        catch { return []; }
    }

    function _parseCampos(json) {
        try { return JSON.parse(json); } catch { return []; }
    }

    async function guardar() {
        const id     = document.getElementById('proceso-id').value;
        const nombre = document.getElementById('proceso-nombre').value.trim();
        const area   = document.getElementById('proceso-area').value;
        if (!nombre) { alert('El nombre es obligatorio.'); return; }
        if (!area)   { alert('Selecciona el área responsable.'); return; }

        // Recopilar pasos
        const pasos = [];
        document.querySelectorAll('[data-paso-idx]').forEach(el => {
            const t = el.value.trim();
            if (t) pasos.push(t);
        });
        if (!pasos.length) { alert('Agrega al menos un paso al proceso.'); return; }

        // Recopilar campos
        const campos = [];
        const keys   = document.querySelectorAll('[data-campo-key]');
        keys.forEach(kEl => {
            const idx   = kEl.dataset.campoKey;
            const key   = kEl.value.trim();
            const label = document.querySelector(`[data-campo-label="${idx}"]`)?.value.trim() || key;
            const type  = document.querySelector(`[data-campo-type="${idx}"]`)?.value || 'text';
            if (key) campos.push({ key, label, type });
        });

        const payload = {
            nombre,
            area,
            descripcion: document.getElementById('proceso-descripcion').value.trim(),
            sla_horas:   parseInt(document.getElementById('proceso-sla').value) || null,
            icono:       document.getElementById('proceso-icono').value.trim() || null,
            pasos_definicion: JSON.stringify(pasos),
            campos_formulario: JSON.stringify(campos),
        };

        try {
            if (id) await GtaApi.updateProceso(id, payload);
            else    await GtaApi.crearProceso(payload);
            cerrarFormulario();
            cargar();
        } catch (e) { alert('Error al guardar proceso'); }
    }

    async function toggleEstado(id, estadoActual) {
        const nuevo = estadoActual === 'activo' ? 'inactivo' : 'activo';
        if (!confirm(`¿${nuevo === 'inactivo' ? 'Desactivar' : 'Activar'} este proceso?`)) return;
        try {
            await GtaApi.updateProceso(id, { estado: nuevo });
            cargar();
        } catch (e) { alert('Error al cambiar estado'); }
    }

    return { init, cargar, filtrar, abrirFormulario, cerrarFormulario, agregarPaso, agregarCampo, guardar, toggleEstado };
})();
