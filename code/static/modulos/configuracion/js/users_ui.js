
/**
 * Gestión de Usuarios en Configuración
 */

const UsersUI = (() => {
    let _users = [];

    async function load() {
        try {
            const data = await window.fetchApi('/api/admin/users');
            _users = data.items || [];
            renderTable();
        } catch (e) {
            console.error("Error loading users", e);
            document.getElementById('tbodyUsers').innerHTML =
                `<tr><td colspan="5" style="padding:20px; text-align:center; color:#ff4444;">Error: ${e.message}</td></tr>`;
        }
    }

    function renderTable() {
        const tbody = document.getElementById('tbodyUsers');
        if (!_users.length) {
            tbody.innerHTML = `<tr><td colspan="5" style="padding:20px; text-align:center; opacity:0.5;">No hay usuarios registrados</td></tr>`;
            return;
        }

        tbody.innerHTML = _users.map(u => {
            const statusBadge = u.is_active
                ? `<span style="color:#44ff88; background:rgba(68,255,136,0.1); padding:2px 8px; border-radius:12px; font-size:0.75rem;">Activo</span>`
                : `<span style="color:#ff4444; background:rgba(255,68,68,0.1); padding:2px 8px; border-radius:12px; font-size:0.75rem;">Inactivo</span>`;

            return `
            <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
                <td style="padding:10px 8px;"><strong>${u.username}</strong></td>
                <td style="padding:10px 8px;">${u.role}</td>
                <td style="padding:10px 8px;">${statusBadge}</td>
                <td style="padding:10px 8px; font-size:0.8rem; opacity:0.6;">${u.created_at || '-'}</td>
                <td style="padding:10px 8px; text-align:right;">
                    <button class="btn-icon-sm" onclick="UsersUI.openModal('${u.username}')" title="Editar">
                        <i class="fas fa-edit"></i>
                    </button>
                    ${u.username !== 'juan.lopez@telconsulting.cl' ? `
                    <button class="btn-icon-sm" onclick="UsersUI.deleteUser('${u.username}')" title="Eliminar" style="color:#ff4444;">
                        <i class="fas fa-trash"></i>
                    </button>` : ''}
                </td>
            </tr>`;
        }).join('');
    }

    const MODULES = [
        { id: 'dashboard', label: 'Dashboard' },
        { id: 'tks', label: 'Ticketera' },
        { id: 'pmo', label: 'Proyectos (PMO)' },
        { id: 'erp', label: 'ERP & Finanzas' },
        { id: 'crm', label: 'CRM' },
        { id: 'bodega', label: 'Bodega' },
        { id: 'ia', label: 'IA (Ultron)' },
        { id: 'zabbix', label: 'Zabbix' },
        { id: 'config', label: 'Configuración' }
    ];

    function openModal(username = null) {
        const modal = document.getElementById('modalUser');
        const form = document.getElementById('formUser');
        const title = document.getElementById('modalUserTitle');
        const userInput = document.getElementById('inpUsername');
        const container = document.getElementById('containerModules');

        form.reset();
        container.innerHTML = '';

        let userModules = [];

        if (username) {
            // Edit Mode
            const u = _users.find(x => x.username === username);
            if (!u) return;

            title.textContent = "Editar Usuario";
            userInput.value = u.username;
            userInput.disabled = true;
            document.getElementById('selRole').value = u.role;
            document.getElementById('chkActive').checked = u.is_active;
            document.getElementById('inpPassword').placeholder = "(Dejar en blanco para no cambiar)";
            form.dataset.mode = 'edit';
            userModules = u.allowed_modules || [];
        } else {
            // Create Mode
            title.textContent = "Nuevo Usuario";
            userInput.value = "";
            userInput.disabled = false;
            document.getElementById('inpPassword').placeholder = "Contraseña";
            document.getElementById('chkActive').checked = true;
            form.dataset.mode = 'create';
            // Default modules for new users? Maybe none or Dashboard
            userModules = ['dashboard'];
        }

        // Render Checkboxes
        MODULES.forEach(m => {
            const checked = userModules.includes(m.id) ? 'checked' : '';
            const div = document.createElement('div');
            div.style.display = 'flex';
            div.style.alignItems = 'center';
            div.style.gap = '6px';
            div.innerHTML = `
                <input type="checkbox" id="mod_${m.id}" value="${m.id}" ${checked}>
                <label for="mod_${m.id}" style="margin:0; font-size:0.8rem; cursor:pointer;">${m.label}</label>
            `;
            container.appendChild(div);
        });

        modal.style.display = 'flex';
    }

    async function saveUser(e) {
        e.preventDefault();
        const form = document.getElementById('formUser');
        const mode = form.dataset.mode;

        const username = document.getElementById('inpUsername').value.trim();
        const role = document.getElementById('selRole').value;
        const password = document.getElementById('inpPassword').value;
        const isActive = document.getElementById('chkActive').checked;

        // Collect modules
        const allowed_modules = [];
        const checks = document.getElementById('containerModules').querySelectorAll('input[type="checkbox"]');
        checks.forEach(c => {
            if (c.checked) allowed_modules.push(c.value);
        });

        if (!username || !role) {
            alert("Campos obligatorios faltantes");
            return;
        }

        try {
            if (mode === 'create') {
                if (!password) { alert("Contraseña requerida para nuevo usuario"); return; }
                await window.fetchApi('/api/admin/users', {
                    method: 'POST',
                    body: { username, password, role, allowed_modules }
                });
            } else {
                const body = { role, is_active: isActive, allowed_modules };
                if (password) body.password = password;

                await window.fetchApi(`/api/admin/users/${username}`, {
                    method: 'PATCH',
                    body: body
                });
            }

            document.getElementById('modalUser').style.display = 'none';
            load();
            if (window.showToast) window.showToast("Usuario guardado correctamente", "success");
            else alert("Usuario guardado");

        } catch (err) {
            alert("Error: " + err.message);
        }
    }

    async function deleteUser(username) {
        if (!confirm(`¿Estás SEGURO de eliminar a ${username}? Esta acción no se puede deshacer.`)) return;

        try {
            await window.fetchApi(`/api/admin/users/${username}`, { method: 'DELETE' });
            load();
            if (window.showToast) window.showToast("Usuario eliminado", "success");
        } catch (err) {
            alert("Error: " + err.message);
        }
    }

    return {
        load,
        openModal,
        saveUser,
        deleteUser
    };
})();

// Expose globally
window.UsersUI = UsersUI;
