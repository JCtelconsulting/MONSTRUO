window.FundConfiguracion = (() => {
    let _ctx = null;
    let _users = [];
    let _todasSedes = [];
    let _membresias = [];
    let _sedeEditando = null;

    async function init(ctx) {
        _ctx = ctx;
        _wireSubtabs();
        _wireButtons();
        await Promise.all([_loadUsers(), _loadSedes(), _loadMembresias()]);
        _renderUsers();
        _renderSedes();
        _renderMembresias();
    }

    function onSedeChange() { /* configuracion no depende de la sede del header */ }

    // ── Sub-tabs ──────────────────────────────────────────────────────
    function _wireSubtabs() {
        document.querySelectorAll('.fund-subtab').forEach(btn => {
            btn.onclick = () => {
                const target = btn.getAttribute('data-fund-sub');
                document.querySelectorAll('.fund-subtab').forEach(b => b.classList.toggle('active', b === btn));
                document.querySelectorAll('.fund-subpane').forEach(p => {
                    p.hidden = p.getAttribute('data-fund-pane') !== target;
                });
            };
        });
    }

    function _wireButtons() {
        document.getElementById('fund-cfg-user-new')?.addEventListener('click', _abrirNuevoUsuario);
        document.getElementById('fund-cfg-sede-new')?.addEventListener('click', () => abrirModalSede(null));
        document.getElementById('fund-cfg-mem-new')?.addEventListener('click', _abrirNuevaMembresia);
    }

    // ── Usuarios ─────────────────────────────────────────────────────
    async function _loadUsers() {
        try {
            const r = await FundApi.getUsuarios();
            _users = r.items || [];
        } catch (e) { _users = []; console.error('users', e); }
    }

    function _renderUsers() {
        const tbody = document.getElementById('fund-cfg-users-body');
        if (!tbody) return;
        if (!_users.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="fund-empty-row">No hay usuarios de Fundación.</td></tr>';
            return;
        }
        tbody.innerHTML = _users.map(u => {
            const sedesUser = _membresias.filter(m => m.username === u.username).map(m => m.sede_nombre);
            return `
                <tr>
                    <td>${_esc(u.username)}</td>
                    <td><span class="tarea-tag">${_esc(_rolLabel(u.role))}</span></td>
                    <td>${u.is_active ? '<span class="tarea-tag prioridad-baja">Activo</span>' : '<span class="tarea-tag">Inactivo</span>'}</td>
                    <td>${sedesUser.length ? sedesUser.map(s => `<span class="tarea-tag">${_esc(s)}</span>`).join(' ') : '<em style="opacity:0.6;">—</em>'}</td>
                    <td style="text-align:right;">
                        <button class="btn-sm" type="button" onclick="FundConfiguracion.toggleUserActivo('${_esc(u.username)}', ${!u.is_active})" title="${u.is_active ? 'Desactivar' : 'Activar'}">
                            <i class="fas ${u.is_active ? 'fa-user-slash' : 'fa-user-check'}"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    async function _abrirNuevoUsuario() {
        const username = prompt('Email del nuevo usuario:');
        if (!username) return;
        const password = prompt('Contraseña inicial:');
        if (!password) return;
        try {
            await FundApi.crearUsuario({
                username, password,
                role: 'gestora_educativa',
                allowed_modules: ['dashboard', 'fundacion'],
                organizacion: 'fundacion',
            });
            await _loadUsers();
            _renderUsers();
        } catch (e) { alert(`Error: ${e?.detail || e?.message || e}`); }
    }

    async function toggleUserActivo(username, nuevoEstado) {
        if (!confirm(`${nuevoEstado ? 'Activar' : 'Desactivar'} a ${username}?`)) return;
        try {
            await FundApi.actualizarUsuario(username, { is_active: nuevoEstado });
            await _loadUsers();
            _renderUsers();
        } catch (e) { alert(`Error: ${e?.detail || e?.message || e}`); }
    }

    function _rolLabel(r) {
        return ({
            admin: 'Admin (super)',
            directora_social: 'Directora Social',
            jefa_pedagogica: 'Jefa Pedagógica',
            coordinadora_territorial: 'Coordinadora Territorial',
            lider_educativo: 'Líder Educativo',
            gestora_educativa: 'Gestora Educativa',
            ejecutiva: 'Ejecutiva',
            fundacion: 'Fundación',
        })[r] || r || '—';
    }

    // ── Sedes ────────────────────────────────────────────────────────
    async function _loadSedes() {
        try {
            const r = await FundApi.getTodasSedes(true);
            _todasSedes = r.items || [];
        } catch (e) { _todasSedes = []; console.error('sedes', e); }
    }

    function _renderSedes() {
        const tbody = document.getElementById('fund-cfg-sedes-body');
        if (!tbody) return;
        if (!_todasSedes.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="fund-empty-row">No hay sedes.</td></tr>';
            return;
        }
        tbody.innerHTML = _todasSedes.map(s => `
            <tr>
                <td><strong>${_esc(s.nombre)}</strong></td>
                <td><code style="opacity:0.7;">${_esc(s.code)}</code></td>
                <td>${_esc(s.region || '—')}</td>
                <td>${s.activo ? '<span class="tarea-tag prioridad-baja">Activa</span>' : '<span class="tarea-tag">Inactiva</span>'}</td>
                <td style="text-align:right;">
                    <button class="btn-sm" type="button" onclick="FundConfiguracion.abrirModalSede(${s.id})"><i class="fas fa-pen"></i></button>
                </td>
            </tr>
        `).join('');
    }

    function abrirModalSede(sedeId) {
        _sedeEditando = sedeId;
        const sede = _todasSedes.find(s => s.id === sedeId) || null;
        document.getElementById('fund-modal-sede-title').textContent = sede ? `Editar sede: ${sede.nombre}` : 'Nueva sede';
        document.getElementById('fund-sede-id').value = sede?.id || '';
        document.getElementById('fund-sede-code').value = sede?.code || '';
        document.getElementById('fund-sede-code').readOnly = !!sede;
        document.getElementById('fund-sede-nombre').value = sede?.nombre || '';
        document.getElementById('fund-sede-region').value = sede?.region || '';
        document.getElementById('fund-sede-desc').value = sede?.descripcion || '';
        document.getElementById('fund-sede-activo').checked = sede ? !!sede.activo : true;
        const m = document.getElementById('fund-modal-sede');
        if (m) m.style.display = 'flex';
    }

    function cerrarModalSede() {
        const m = document.getElementById('fund-modal-sede');
        if (m) m.style.display = 'none';
    }

    async function guardarSede() {
        const id = document.getElementById('fund-sede-id').value;
        const code = document.getElementById('fund-sede-code').value.trim().toLowerCase();
        const nombre = document.getElementById('fund-sede-nombre').value.trim();
        const region = document.getElementById('fund-sede-region').value.trim() || null;
        const descripcion = document.getElementById('fund-sede-desc').value.trim() || null;
        const activo = document.getElementById('fund-sede-activo').checked;
        if (!nombre) return alert('Nombre obligatorio');
        try {
            if (id) {
                await FundApi.actualizarSede(parseInt(id, 10), { nombre, region, descripcion, activo });
            } else {
                if (!code) return alert('Código obligatorio');
                await FundApi.crearSede({ code, nombre, region, descripcion });
            }
            cerrarModalSede();
            await _loadSedes();
            _renderSedes();
        } catch (e) { alert(`Error: ${e?.detail || e?.message || e}`); }
    }

    // ── Membresías ───────────────────────────────────────────────────
    async function _loadMembresias() {
        try {
            const r = await FundApi.getMembresias();
            _membresias = r.items || [];
        } catch (e) { _membresias = []; console.error('membresias', e); }
    }

    function _renderMembresias() {
        const tbody = document.getElementById('fund-cfg-mem-body');
        if (!tbody) return;
        if (!_membresias.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="fund-empty-row">No hay membresías. Asigná una para empezar.</td></tr>';
            return;
        }
        tbody.innerHTML = _membresias.map(m => `
            <tr>
                <td><strong>${_esc(m.sede_nombre)}</strong></td>
                <td>${_esc(m.username)}</td>
                <td><span class="tarea-tag">${_esc(_rolLabel(m.rol))}</span></td>
                <td>${_fmt(m.desde)}</td>
                <td style="text-align:right;">
                    <button class="btn-sm btn-danger" type="button" onclick="FundConfiguracion.cerrarMembresia(${m.id}, '${_esc(m.username)}', '${_esc(m.sede_nombre)}')" title="Cerrar membresía">
                        <i class="fas fa-times"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    function _abrirNuevaMembresia() {
        const sedeSel = document.getElementById('fund-mem-sede');
        const userSel = document.getElementById('fund-mem-usuario');
        sedeSel.innerHTML = (_todasSedes.filter(s => s.activo).map(s => `<option value="${s.id}">${_esc(s.nombre)}</option>`).join('')) || '<option value="">— No hay sedes —</option>';
        userSel.innerHTML = (_users.filter(u => u.is_active).map(u => `<option value="${u.id}">${_esc(u.username)}</option>`).join('')) || '<option value="">— No hay usuarios —</option>';

        // Como /api/admin/users no devuelve id directamente, fallback: usamos username
        // Verificamos: si los items no tienen id, mostramos warning.
        if (_users.length && !_users[0].id && !_users[0].user_id) {
            // El endpoint no expone id; lo resolvemos en el guardado vía /api/admin/users buscando por username.
            // Para simplificar, deshabilitamos por ahora si falta.
        }

        document.getElementById('fund-mem-rol').value = 'gestora_educativa';
        document.getElementById('fund-mem-motivo').value = '';
        const m = document.getElementById('fund-modal-mem');
        if (m) m.style.display = 'flex';
    }

    function cerrarModalMem() {
        const m = document.getElementById('fund-modal-mem');
        if (m) m.style.display = 'none';
    }

    async function guardarMembresia() {
        const sede_id = parseInt(document.getElementById('fund-mem-sede').value || '0', 10);
        const userValOrId = document.getElementById('fund-mem-usuario').value;
        const rol = document.getElementById('fund-mem-rol').value;
        const motivo = document.getElementById('fund-mem-motivo').value.trim() || null;
        if (!sede_id || !userValOrId) return alert('Sede y usuario obligatorios');

        // El select tiene IDs si el endpoint los expone; si no, valor es username y resolvemos vía /api/config/gta/users
        let usuario_id;
        if (/^\d+$/.test(userValOrId)) {
            usuario_id = parseInt(userValOrId, 10);
        } else {
            try {
                const r = await window.fetchApi('/api/config/gta/users');
                const found = (r.items || []).find(u => u.username === userValOrId);
                if (!found) return alert('No se pudo resolver el id del usuario.');
                usuario_id = found.id;
            } catch {
                return alert('No se pudo resolver el id del usuario.');
            }
        }

        try {
            await FundApi.crearMembresia({ usuario_id, sede_id, rol, motivo });
            cerrarModalMem();
            await _loadMembresias();
            _renderMembresias();
            _renderUsers();   // refresca columna "Sedes" en Usuarios
        } catch (e) { alert(`Error: ${e?.detail || e?.message || e}`); }
    }

    async function cerrarMembresia(id, username, sedeNombre) {
        if (!confirm(`¿Cerrar la membresía de ${username} en ${sedeNombre}?`)) return;
        try {
            await FundApi.cerrarMembresia(id);
            await _loadMembresias();
            _renderMembresias();
            _renderUsers();
        } catch (e) { alert(`Error: ${e?.detail || e?.message || e}`); }
    }

    // ── helpers ──
    function _esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
    function _fmt(iso) { if (!iso) return '—'; try { return new Date(iso).toLocaleDateString('es-CL'); } catch { return iso; } }

    return {
        init, onSedeChange,
        toggleUserActivo,
        abrirModalSede, cerrarModalSede, guardarSede,
        cerrarModalMem, guardarMembresia, cerrarMembresia,
    };
})();
