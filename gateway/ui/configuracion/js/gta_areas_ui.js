// gta_areas_ui.js — Pestaña GTA en Configuración
// Gestión de áreas, subáreas y líderes del GTA

(function () {
    'use strict';

    let _areas = [];
    let _users = [];
    let _editingAreaCode = null;
    let _editingSubareaId = null;

    // ── Carga inicial ────────────────────────────────────────────────────
    async function load() {
        const container = document.getElementById('gtaAreasContainer');
        if (!container) return;
        container.innerHTML = '<div class="cfg-role-guide-empty">Cargando áreas...</div>';

        try {
            const [areasResp, usersResp] = await Promise.all([
                window.fetchApi('/api/config/gta/areas'),
                window.fetchApi('/api/config/gta/users'),
            ]);
            _areas = areasResp.items || [];
            _users = usersResp.items || [];
            render();
        } catch (e) {
            container.innerHTML = `<div class="cfg-role-guide-empty">Error al cargar: ${e.message || e}</div>`;
        }
    }

    function _liderText(area) {
        if (area.lider_username) {
            const u = _users.find(x => x.username === area.lider_username);
            return u ? `${area.lider_nombre || area.lider_username} (${area.lider_username})` : area.lider_username;
        }
        return area.lider_nombre || '— Sin asignar —';
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function render() {
        const container = document.getElementById('gtaAreasContainer');
        if (!container) return;

        if (_areas.length === 0) {
            container.innerHTML = '<div class="cfg-role-guide-empty">No hay áreas configuradas.</div>';
            return;
        }

        const html = _areas.map(area => {
            const liderHtml = _liderText(area);
            const externaTag = area.es_externa ? '<span class="tarea-tag" style="background:#444; color:#bbb;">EXTERNA</span>' : '';
            const inactivaTag = !area.activo ? '<span class="tarea-tag prioridad-baja">INACTIVA</span>' : '';

            const subareasHtml = (area.subareas || []).map(sub => `
                <div class="cfg-subarea-row">
                    <div class="cfg-subarea-info">
                        <span class="cfg-subarea-label">${_esc(sub.label)}</span>
                        <span class="cfg-subarea-code">${_esc(sub.code)}</span>
                        ${sub.lider_nombre ? `<span class="cfg-subarea-lider">Líder: ${_esc(sub.lider_nombre)}</span>` : ''}
                        ${!sub.activo ? '<span class="tarea-tag prioridad-baja">INACTIVA</span>' : ''}
                    </div>
                    <div class="cfg-subarea-actions">
                        <button class="btn-sm" onclick="GtaAreasUI.openSubareaModal('${_esc(area.code)}', ${sub.id})" title="Editar">
                            <i class="fas fa-pen"></i>
                        </button>
                        <button class="btn-sm btn-danger" onclick="GtaAreasUI.deleteSubarea(${sub.id}, '${_esc(sub.label)}')" title="Eliminar">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `).join('');

            return `
            <div class="cfg-area-card" data-area="${_esc(area.code)}">
                <div class="cfg-area-header">
                    <div class="cfg-area-title">
                        <h4>${_esc(area.label)} ${externaTag} ${inactivaTag}</h4>
                        <div class="cfg-area-meta">
                            <span class="cfg-area-code">${_esc(area.code)}</span>
                            <span class="cfg-area-lider"><i class="fas fa-user-tie"></i> ${_esc(liderHtml)}</span>
                        </div>
                    </div>
                    <div class="cfg-area-actions">
                        <button class="btn-sm" onclick="GtaAreasUI.openAreaModal('${_esc(area.code)}')" title="Editar área">
                            <i class="fas fa-pen"></i> Editar
                        </button>
                        <button class="btn-sm btn-primary" onclick="GtaAreasUI.openSubareaModal('${_esc(area.code)}', null)" title="Agregar subárea">
                            <i class="fas fa-plus"></i> Subárea
                        </button>
                    </div>
                </div>
                ${subareasHtml ? `<div class="cfg-subareas-list">${subareasHtml}</div>` : '<div class="cfg-subareas-empty">Sin subáreas</div>'}
            </div>
            `;
        }).join('');

        container.innerHTML = html;
    }

    // ── Modal: Editar Área ───────────────────────────────────────────────
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

        // Llenar select de líderes con usuarios del sistema
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

    // ── Modal: Subárea (crear o editar) ──────────────────────────────────
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

    // ── Auto-load cuando se activa la pestaña GTA ────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        const gtaTab = document.querySelector('.tab-btn[data-target="pane-gta"]');
        if (!gtaTab) return;
        gtaTab.addEventListener('click', () => {
            // Carga lazy: primera vez que se abre la pestaña
            if (_areas.length === 0) load();
        });
    });

    window.GtaAreasUI = {
        load,
        openAreaModal, closeAreaModal, saveArea,
        openSubareaModal, closeSubareaModal, saveSubarea,
        deleteSubarea,
    };
})();
