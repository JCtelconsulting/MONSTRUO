// gta_areas_ui.js — Pestaña GTA en Configuración (vista tabla)
// Gestión de áreas, subáreas y líderes del GTA.

(function () {
    'use strict';

    let _areas = [];               // [{code, label, ..., subareas:[...]}]
    let _users = [];
    let _membresias = [];          // membresías vigentes (para conteo y líder vigente)
    let _editingAreaCode = null;
    let _editingSubareaId = null;
    let _filterText = '';
    let _showInactive = false;
    let _firstLoadDone = false;

    // ── Carga inicial ────────────────────────────────────────────────────
    async function load() {
        const tbody = document.getElementById('gtaAreasTableBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" class="cfg-table-empty">Cargando…</td></tr>';

        try {
            const [areasResp, usersResp, membResp] = await Promise.all([
                window.fetchApi('/api/config/gta/areas'),
                window.fetchApi('/api/config/gta/users'),
                window.fetchApi('/api/config/gta/membresias'),
            ]);
            _areas = areasResp.items || [];
            _users = usersResp.items || [];
            _membresias = membResp.items || [];
            _firstLoadDone = true;
            render();
            // Refrescar también la sub-pestaña de membresías si está montada
            if (window.GtaMembresiasUI) window.GtaMembresiasUI.onAreasLoaded(_areas, _users, _membresias);
        } catch (e) {
            tbody.innerHTML = `<tr><td colspan="6" class="cfg-table-empty">Error al cargar: ${_esc(e.message || e)}</td></tr>`;
        }
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function _liderVigenteHtml(subareaId, areaLiderUsername, areaLiderNombre) {
        const m = _membresias.find(x => x.subarea_id === subareaId && x.rol === 'lider');
        if (m) return `<span class="cfg-tag cfg-tag-lider"><i class="fas fa-user-tie"></i> ${_esc(m.username)}</span>`;
        if (areaLiderUsername) return `<span class="cfg-tag" title="Heredado del área (legacy)">${_esc(areaLiderUsername)} <small>(legacy)</small></span>`;
        if (areaLiderNombre) return `<span class="cfg-tag">${_esc(areaLiderNombre)} <small>(legacy)</small></span>`;
        return '<span class="cfg-tag cfg-tag-empty">— Sin líder —</span>';
    }

    function _miembrosCount(subareaId) {
        return _membresias.filter(x => x.subarea_id === subareaId).length;
    }

    function _matchFilter(area, sub) {
        if (!_filterText) return true;
        const q = _filterText.toLowerCase();
        const fields = [
            area.code, area.label,
            sub ? sub.code : '', sub ? sub.label : '',
        ].map(s => String(s || '').toLowerCase());
        return fields.some(f => f.includes(q));
    }

    function render() {
        const tbody = document.getElementById('gtaAreasTableBody');
        if (!tbody) return;

        if (!_areas.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="cfg-table-empty">No hay áreas configuradas.</td></tr>';
            return;
        }

        const rows = [];
        _areas.forEach(area => {
            if (!_showInactive && !area.activo) return;
            const subs = (area.subareas || []).filter(s => _showInactive || s.activo);

            if (subs.length === 0) {
                if (!_matchFilter(area, null)) return;
                rows.push(`
                    <tr class="cfg-row-area">
                        <td>
                            <strong>${_esc(area.label)}</strong>
                            ${_areaTags(area)}
                            <div class="cfg-cell-sub">${_esc(area.code)}</div>
                        </td>
                        <td colspan="3" class="cfg-cell-empty"><em>Sin subáreas</em></td>
                        <td style="text-align:center;">${_estadoBadge(area.activo)}</td>
                        <td style="text-align:right;">
                            ${_areaActionsHtml(area)}
                        </td>
                    </tr>
                `);
                return;
            }

            subs.forEach((sub, idx) => {
                if (!_matchFilter(area, sub)) return;
                const isFirst = (idx === 0);
                rows.push(`
                    <tr class="cfg-row-subarea ${isFirst ? 'cfg-row-area-first' : ''}">
                        <td>
                            ${isFirst ? `
                                <strong>${_esc(area.label)}</strong>
                                ${_areaTags(area)}
                                <div class="cfg-cell-sub">${_esc(area.code)}</div>
                            ` : '<span class="cfg-cell-cont">↳</span>'}
                        </td>
                        <td>
                            <span>${_esc(sub.label)}</span>
                            <div class="cfg-cell-sub">${_esc(sub.code)}</div>
                        </td>
                        <td>${_liderVigenteHtml(sub.id, sub.lider_username, sub.lider_nombre)}</td>
                        <td style="text-align:center;"><span class="cfg-tag cfg-tag-num">${_miembrosCount(sub.id)}</span></td>
                        <td style="text-align:center;">${_estadoBadge(sub.activo)}</td>
                        <td style="text-align:right;">
                            <div class="cfg-row-actions">
                                ${isFirst ? _areaActionsHtml(area) : ''}
                                <button class="btn-sm" type="button" onclick="GtaAreasUI.openSubareaModal('${_esc(area.code)}', ${sub.id})" title="Editar subárea">
                                    <i class="fas fa-pen"></i>
                                </button>
                                <button class="btn-sm btn-danger" type="button" onclick="GtaAreasUI.deleteSubarea(${sub.id}, '${_esc(sub.label)}')" title="Eliminar subárea">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                `);
            });
        });

        tbody.innerHTML = rows.length
            ? rows.join('')
            : '<tr><td colspan="6" class="cfg-table-empty">Sin resultados con ese filtro.</td></tr>';
    }

    function _areaTags(area) {
        const parts = [];
        if (area.es_externa) parts.push('<span class="cfg-tag cfg-tag-warn">EXTERNA</span>');
        return parts.join(' ');
    }

    function _estadoBadge(activo) {
        return activo
            ? '<span class="cfg-tag cfg-tag-ok">Activa</span>'
            : '<span class="cfg-tag cfg-tag-muted">Inactiva</span>';
    }

    function _areaActionsHtml(area) {
        return `
            <button class="btn-sm" type="button" onclick="GtaAreasUI.openAreaModal('${_esc(area.code)}')" title="Editar área">
                <i class="fas fa-pen"></i>
            </button>
            <button class="btn-sm btn-primary" type="button" onclick="GtaAreasUI.openSubareaModal('${_esc(area.code)}', null)" title="Nueva subárea en esta área">
                <i class="fas fa-plus"></i>
            </button>
        `;
    }

    // ── Modales (idénticos a antes en lógica) ────────────────────────────
    function openAreaModal(code) {
        const area = _areas.find(a => a.code === code);
        if (!area) return;
        _editingAreaCode = code;

        document.getElementById('modalGtaAreaTitle').textContent = `Editar área: ${area.label}`;
        document.getElementById('gtaAreaCode').value = area.code;
        document.getElementById('gtaAreaLabel').value = area.label;
        document.getElementById('gtaAreaLiderNombre').value = area.lider_nombre || '';
        document.getElementById('gtaAreaExterna').checked = !!area.es_externa;
        document.getElementById('gtaAreaActivo').checked = !!area.activo;
        document.getElementById('gtaAreaOrden').value = area.orden ?? 99;

        const sel = document.getElementById('gtaAreaLider');
        sel.innerHTML = '<option value="">— Sin asignar —</option>' +
            _users.map(u => `<option value="${_esc(u.username)}" ${u.username === area.lider_username ? 'selected' : ''}>${_esc(u.username)} (${_esc(u.role || '-')})</option>`).join('');

        document.getElementById('modalGtaArea').setAttribute('aria-hidden', 'false');
        document.getElementById('modalGtaArea').classList.add('is-open');
    }

    function closeAreaModal() {
        document.getElementById('modalGtaArea').setAttribute('aria-hidden', 'true');
        document.getElementById('modalGtaArea').classList.remove('is-open');
        _editingAreaCode = null;
    }

    async function saveArea(ev) {
        ev.preventDefault();
        if (!_editingAreaCode) return;

        const body = {
            label: document.getElementById('gtaAreaLabel').value.trim(),
            lider_username: document.getElementById('gtaAreaLider').value,
            lider_nombre: document.getElementById('gtaAreaLiderNombre').value.trim(),
            es_externa: document.getElementById('gtaAreaExterna').checked,
            activo: document.getElementById('gtaAreaActivo').checked,
            orden: parseInt(document.getElementById('gtaAreaOrden').value, 10) || 99,
        };

        try {
            await window.fetchApi(`/api/config/gta/areas/${encodeURIComponent(_editingAreaCode)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            closeAreaModal();
            await load();
        } catch (e) {
            alert(`Error al guardar área: ${e.message || e}`);
        }
    }

    function openSubareaModal(parentCode, subId) {
        _editingSubareaId = subId;
        const parent = _areas.find(a => a.code === parentCode);
        if (!parent) return;

        document.getElementById('gtaSubareaParent').value = parentCode;
        document.getElementById('gtaSubareaParentLabel').value = parent.label;

        const sel = document.getElementById('gtaSubareaLider');
        sel.innerHTML = '<option value="">— Hereda del área padre —</option>' +
            _users.map(u => `<option value="${_esc(u.username)}">${_esc(u.username)} (${_esc(u.role || '-')})</option>`).join('');

        if (subId) {
            const sub = (parent.subareas || []).find(s => s.id === subId);
            if (!sub) return;
            document.getElementById('modalGtaSubareaTitle').textContent = `Editar subárea: ${sub.label}`;
            document.getElementById('gtaSubareaId').value = sub.id;
            document.getElementById('gtaSubareaCode').value = sub.code;
            document.getElementById('gtaSubareaCode').readOnly = true;
            document.getElementById('gtaSubareaLabel').value = sub.label;
            document.getElementById('gtaSubareaLider').value = sub.lider_username || '';
            document.getElementById('gtaSubareaActivo').checked = !!sub.activo;
            document.getElementById('gtaSubareaOrden').value = sub.orden ?? 99;
        } else {
            document.getElementById('modalGtaSubareaTitle').textContent = `Nueva subárea en ${parent.label}`;
            document.getElementById('gtaSubareaId').value = '';
            document.getElementById('gtaSubareaCode').value = '';
            document.getElementById('gtaSubareaCode').readOnly = false;
            document.getElementById('gtaSubareaLabel').value = '';
            document.getElementById('gtaSubareaLider').value = '';
            document.getElementById('gtaSubareaActivo').checked = true;
            document.getElementById('gtaSubareaOrden').value = 99;
        }

        document.getElementById('modalGtaSubarea').setAttribute('aria-hidden', 'false');
        document.getElementById('modalGtaSubarea').classList.add('is-open');
    }

    function closeSubareaModal() {
        document.getElementById('modalGtaSubarea').setAttribute('aria-hidden', 'true');
        document.getElementById('modalGtaSubarea').classList.remove('is-open');
        _editingSubareaId = null;
    }

    async function saveSubarea(ev) {
        ev.preventDefault();
        const id = document.getElementById('gtaSubareaId').value;
        const liderUsername = document.getElementById('gtaSubareaLider').value;
        const liderUser = _users.find(u => u.username === liderUsername);

        const body = {
            label: document.getElementById('gtaSubareaLabel').value.trim(),
            lider_username: liderUsername,
            lider_nombre: liderUser ? liderUser.username : '',
            activo: document.getElementById('gtaSubareaActivo').checked,
            orden: parseInt(document.getElementById('gtaSubareaOrden').value, 10) || 99,
        };

        try {
            if (id) {
                await window.fetchApi(`/api/config/gta/subareas/${encodeURIComponent(id)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
            } else {
                body.area_code = document.getElementById('gtaSubareaParent').value;
                body.code = document.getElementById('gtaSubareaCode').value.trim().toLowerCase();
                await window.fetchApi('/api/config/gta/subareas', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
            }
            closeSubareaModal();
            await load();
        } catch (e) {
            alert(`Error al guardar subárea: ${e.message || e}`);
        }
    }

    async function deleteSubarea(subId, label) {
        if (!confirm(`¿Eliminar la subárea "${label}"?`)) return;
        try {
            await window.fetchApi(`/api/config/gta/subareas/${encodeURIComponent(subId)}`, {
                method: 'DELETE',
            });
            await load();
        } catch (e) {
            alert(`Error al eliminar: ${e.message || e}`);
        }
    }

    // ── Sub-tabs internas (Áreas / Membresías) ───────────────────────────
    function _initSubtabs() {
        const tabs = document.querySelectorAll('#pane-gta .cfg-subtab');
        tabs.forEach(t => {
            t.addEventListener('click', () => {
                const target = t.getAttribute('data-gta-sub');
                tabs.forEach(x => x.classList.toggle('active', x === t));
                document.querySelectorAll('#pane-gta .cfg-gta-subpane').forEach(p => {
                    p.hidden = (p.getAttribute('data-gta-pane') !== target);
                });
                if (target === 'membresias' && window.GtaMembresiasUI) {
                    window.GtaMembresiasUI.onShow();
                }
            });
        });
    }

    // ── Filtros tabla ────────────────────────────────────────────────────
    function _initFilters() {
        const f = document.getElementById('gtaTblFilter');
        if (f) f.addEventListener('input', () => { _filterText = f.value.trim(); render(); });
        const i = document.getElementById('gtaTblShowInactive');
        if (i) i.addEventListener('change', () => { _showInactive = i.checked; render(); });
    }

    // Auto-load cuando se activa el pane GTA
    document.addEventListener('DOMContentLoaded', () => {
        const gtaTab = document.querySelector('.tab-btn[data-target="pane-gta"]');
        if (!gtaTab) return;
        _initSubtabs();
        _initFilters();
        gtaTab.addEventListener('click', () => {
            if (!_firstLoadDone) load();
        });
    });

    window.GtaAreasUI = {
        load,
        openAreaModal, closeAreaModal, saveArea,
        openSubareaModal, closeSubareaModal, saveSubarea,
        deleteSubarea,
        // Acceso a datos para el módulo de membresías
        _getAreas: () => _areas,
        _getUsers: () => _users,
        _getMembresias: () => _membresias,
        refresh: load,
    };
})();
