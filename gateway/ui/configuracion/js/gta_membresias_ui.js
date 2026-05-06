// gta_membresias_ui.js — Sub-pestaña de Líderes y Miembros (Configuración → GTA)

(function () {
    'use strict';

    let _areas = [];
    let _users = [];
    let _membresias = [];
    let _filterText = '';
    let _wired = false;

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function _fmtFecha(iso) {
        if (!iso) return '—';
        try {
            const d = new Date(iso);
            return d.toLocaleString('es-CL', { day:'2-digit', month:'2-digit', year:'numeric' });
        } catch { return iso; }
    }

    function onAreasLoaded(areas, users, memb) {
        _areas = areas || [];
        _users = users || [];
        _membresias = memb || [];
        _render();
    }

    function onShow() {
        // Si todavía no se cargaron datos (entrar directo a la sub-tab), pedirlos.
        if (!_areas.length && window.GtaAreasUI) {
            window.GtaAreasUI.refresh();
        } else {
            _render();
        }
    }

    function _matchFilter(m) {
        if (!_filterText) return true;
        const q = _filterText.toLowerCase();
        return [
            m.area_label, m.subarea_label, m.username, m.rol,
        ].some(s => String(s || '').toLowerCase().includes(q));
    }

    function _rolBadge(rol) {
        if (rol === 'lider') return '<span class="cfg-tag cfg-tag-lider"><i class="fas fa-user-tie"></i> Líder</span>';
        return '<span class="cfg-tag">Miembro</span>';
    }

    function _principalBadge(es) {
        return es
            ? '<span class="cfg-tag cfg-tag-ok">Principal</span>'
            : '<span class="cfg-tag cfg-tag-muted">Secundaria</span>';
    }

    function _render() {
        const tbody = document.getElementById('gtaMembTableBody');
        if (!tbody) return;

        const items = (_membresias || []).filter(_matchFilter);
        if (!items.length) {
            tbody.innerHTML = `<tr><td colspan="6" class="cfg-table-empty">
                ${_membresias.length ? 'Sin resultados con ese filtro.' : 'No hay membresías asignadas. Usá "Asignar membresía" para empezar.'}
            </td></tr>`;
            return;
        }

        tbody.innerHTML = items.map(m => `
            <tr>
                <td>
                    <strong>${_esc(m.area_label || '—')}</strong>
                    <div class="cfg-cell-sub">${_esc(m.subarea_label || '—')}</div>
                </td>
                <td>${_esc(m.username)}</td>
                <td>${_rolBadge(m.rol)}</td>
                <td>${_principalBadge(!!m.es_principal)}</td>
                <td>${_fmtFecha(m.desde)}</td>
                <td style="text-align:right;">
                    <button class="btn-sm btn-danger" type="button"
                            onclick="GtaMembresiasUI.cerrar(${m.id}, '${_esc(m.username)}', '${_esc(m.subarea_label)}')"
                            title="Cerrar membresía">
                        <i class="fas fa-times"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    }

    // ── Modal asignar ────────────────────────────────────────────────────
    function openModal() {
        if (!_areas.length || !_users.length) {
            alert('Todavía no se cargaron las áreas. Probá de nuevo en un momento.');
            return;
        }

        // Subáreas (option grouping por área)
        const subSel = document.getElementById('gtaMembSubarea');
        const groups = _areas
            .filter(a => a.activo)
            .map(a => {
                const subs = (a.subareas || []).filter(s => s.activo);
                if (!subs.length) return '';
                return `<optgroup label="${_esc(a.label)}">
                    ${subs.map(s => `<option value="${s.id}">${_esc(s.label)} (${_esc(s.code)})</option>`).join('')}
                </optgroup>`;
            }).filter(Boolean).join('');
        subSel.innerHTML = '<option value="">— Seleccionar —</option>' + groups;

        // Usuarios activos
        const userSel = document.getElementById('gtaMembUsuario');
        userSel.innerHTML = '<option value="">— Seleccionar —</option>' +
            _users.map(u => `<option value="${u.id}">${_esc(u.username)} (${_esc(u.role || '-')})</option>`).join('');

        document.getElementById('gtaMembRol').value = 'miembro';
        document.getElementById('gtaMembPrincipal').checked = false;
        document.getElementById('gtaMembMotivo').value = '';

        document.getElementById('modalGtaMembresia').setAttribute('aria-hidden', 'false');
        document.getElementById('modalGtaMembresia').classList.add('is-open');
    }

    function closeModal() {
        document.getElementById('modalGtaMembresia').setAttribute('aria-hidden', 'true');
        document.getElementById('modalGtaMembresia').classList.remove('is-open');
    }

    async function save(ev) {
        ev.preventDefault();
        const subarea_id = parseInt(document.getElementById('gtaMembSubarea').value || '0', 10);
        const usuario_id = parseInt(document.getElementById('gtaMembUsuario').value || '0', 10);
        const rol = document.getElementById('gtaMembRol').value;
        const es_principal = document.getElementById('gtaMembPrincipal').checked;
        const motivo = document.getElementById('gtaMembMotivo').value.trim() || null;

        if (!subarea_id || !usuario_id) {
            alert('Seleccioná subárea y usuario.');
            return;
        }

        try {
            await window.fetchApi('/api/config/gta/membresias', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ subarea_id, usuario_id, rol, es_principal, motivo }),
            });
            closeModal();
            if (window.GtaAreasUI) await window.GtaAreasUI.refresh();
        } catch (e) {
            alert(`Error: ${e.message || e}`);
        }
    }

    async function cerrar(membresia_id, username, subareaLabel) {
        if (!confirm(`¿Cerrar la membresía de ${username} en ${subareaLabel}?\nLas tareas siguen vivas en la subárea.`)) return;
        try {
            await window.fetchApi(`/api/config/gta/membresias/${membresia_id}`, { method: 'DELETE' });
            if (window.GtaAreasUI) await window.GtaAreasUI.refresh();
        } catch (e) {
            alert(`Error: ${e.message || e}`);
        }
    }

    // Wire del filtro (una sola vez)
    function _wireFilter() {
        if (_wired) return;
        const f = document.getElementById('gtaMembFilter');
        if (f) {
            f.addEventListener('input', () => { _filterText = f.value.trim(); _render(); });
            _wired = true;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        _wireFilter();
    });

    window.GtaMembresiasUI = {
        onAreasLoaded, onShow,
        openModal, closeModal, save, cerrar,
    };
})();
