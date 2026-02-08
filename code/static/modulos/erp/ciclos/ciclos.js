// Ciclos (Auto-Facturación) Logic

let allRules = [];

async function initCiclos() {
    console.log("Iniciando Ciclos...");
    await fetchUF();
    await loadRules();
}

// Expose globally
window.initCiclos = initCiclos;

async function fetchUF() {
    try {
        const data = await window.fetchApi('/api/facturacion/uf');
        if (data && data.uf) {
            const fmt = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(data.uf);
            document.getElementById('uf-today-val').innerText = fmt;
            document.getElementById('uf-date-val').innerText = `Actualizado: ${data.fecha}`;
        }
    } catch (e) {
        console.error("Error fetching UF:", e);
        document.getElementById('uf-today-val').innerText = "Erro";
    }
}

async function loadRules() {
    const tbody = document.getElementById('tabla-ciclos');
    if (!tbody) return;

    try {
        const rules = await window.fetchApi('/api/facturacion/ciclos');
        allRules = rules || [];
        renderRules(allRules);

        const activeCount = allRules.filter(r => r.is_active).length;
        document.getElementById('active-rules-count').innerText = activeCount;

    } catch (e) {
        console.error("Error loading rules:", e);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:red;">Error al cargar las reglas</td></tr>';
    }
}

function renderRules(rules) {
    const tbody = document.getElementById('tabla-ciclos');
    tbody.innerHTML = '';

    if (rules.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:3rem; opacity:0.5;">No hay reglas configuradas</td></tr>';
        return;
    }

    rules.forEach(r => {
        const tr = document.createElement('tr');

        let valorStr = "";
        if (r.currency === 'UF') {
            valorStr = `<b>${r.base_amount} UF</b> <br><small style="opacity:0.6;">(${r.uf_rule})</small>`;
        } else {
            valorStr = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(r.base_amount);
        }

        tr.innerHTML = `
            <td><b>${r.customer_id}</b></td>
            <td>Cada ${r.frequency_months} mes(es)</td>
            <td>${valorStr}</td>
            <td>Día ${r.day_of_month}</td>
            <td>${r.next_billing_date || 'Pendiente'}</td>
            <td>
                <button class="btn-icon" title="Editar" onclick="editRule('${r.customer_id}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon" title="Previsualizar" onclick="previewRule('${r.customer_id}')">
                    <i class="fas fa-eye"></i>
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function openNewRuleModal() {
    document.getElementById('modal-rule-title').innerText = "Nueva Regla de Ciclo";
    document.getElementById('rule-customer-id').value = "";
    document.getElementById('rule-customer-id').disabled = false;
    document.getElementById('rule-description').value = "";
    document.getElementById('rule-base-amount').value = 0;
    document.getElementById('rule-currency').value = "CLP";
    document.getElementById('rule-frequency').value = 1;
    document.getElementById('rule-day').value = 5;
    document.getElementById('rule-auto-issue').checked = false;


    toggleUFRules();
    loadCustomers(); // Load CRM customers
    document.getElementById('modal-rule').showModal();
}

async function loadCustomers() {
    const select = document.getElementById('rule-customer-id');
    if (select.options.length > 1) return; // Already loaded

    try {
        select.innerHTML = '<option value="" disabled selected>Cargando...</option>';
        const customers = await window.fetchApi('/api/crm/customers?limit=100');

        select.innerHTML = '<option value="" disabled selected>Seleccione Cliente</option>';
        if (customers && customers.length > 0) {
            customers.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id; // Assuming ID matches what Laudus needs or we use a mapping
                opt.text = `${c.name} (${c.rut})`;
                select.appendChild(opt);
            });
        }
    } catch (e) {
        console.error("Error loading customers:", e);
        select.innerHTML = '<option value="" disabled>Error al cargar</option>';
    }
}

function toggleUFRules() {
    const isUF = document.getElementById('rule-currency').value === 'UF';
    document.getElementById('uf-rules-container').style.display = isUF ? 'block' : 'none';
}

function toggleUFValue() {
    const type = document.getElementById('rule-uf-type').value;
    const needsVal = (type === 'VALOR_FIJO' || type === 'VALOR_CONTRATO');
    document.getElementById('uf-custom-value-group').style.display = needsVal ? 'block' : 'none';
}

async function saveRule() {
    const payload = {
        customer_id: document.getElementById('rule-customer-id').value,
        description: document.getElementById('rule-description').value,
        currency: document.getElementById('rule-currency').value,
        uf_rule: document.getElementById('rule-uf-type').value,
        uf_custom_value: parseFloat(document.getElementById('rule-uf-custom-val').value) || 0,
        base_amount: parseFloat(document.getElementById('rule-base-amount').value) || 0,
        frequency_months: parseInt(document.getElementById('rule-frequency').value) || 1,
        day_of_month: parseInt(document.getElementById('rule-day').value) || 5,
        is_active: true,
        auto_issue: document.getElementById('rule-auto-issue').checked
    };

    if (!payload.customer_id) {
        alert("El ID del cliente es obligatorio");
        return;
    }

    try {
        const resp = await window.fetchApi('/api/facturacion/ciclos', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (resp && resp.ok) {
            document.getElementById('modal-rule').close();
            loadRules();
        } else {
            alert("Error al guardar la regla");
        }
    } catch (e) {
        console.error(e);
        alert("Error de conexión");
    }
}

async function editRule(cid) {
    const rule = allRules.find(r => r.customer_id === cid);
    if (!rule) return;

    document.getElementById('modal-rule-title').innerText = "Editar Regla: " + cid;

    // Ensure customers are loaded for the select
    await loadCustomers();
    document.getElementById('rule-customer-id').value = rule.customer_id;
    document.getElementById('rule-customer-id').disabled = true;
    document.getElementById('rule-description').value = rule.description || "";
    document.getElementById('rule-base-amount').value = rule.base_amount || 0;
    document.getElementById('rule-currency').value = rule.currency || "CLP";
    document.getElementById('rule-frequency').value = rule.frequency_months || 1;
    document.getElementById('rule-day').value = rule.day_of_month || 5;

    // UF values
    document.getElementById('rule-uf-type').value = rule.uf_rule || "VALOR_DIA";
    document.getElementById('rule-uf-custom-val').value = rule.uf_custom_value || 0;

    document.getElementById('rule-auto-issue').checked = !!rule.auto_issue;

    toggleUFRules();
    toggleUFValue();
    document.getElementById('modal-rule').showModal();
}

async function previewRule(cid) {
    const rule = allRules.find(r => r.customer_id === cid);
    if (!rule) return;

    try {
        const data = await window.fetchApi('/api/facturacion/ciclos/preview', {
            method: 'POST',
            body: JSON.stringify(rule)
        });

        if (data) {
            const fmt = (n) => new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(n);
            let msg = `Previsualización para ${cid}:\n\n`;
            msg += `Monto Base: ${rule.base_amount} ${rule.currency}\n`;
            if (data.uf_used) msg += `UF aplicada: ${fmt(data.uf_used)}\n`;
            msg += `Neto calculado: ${fmt(data.total_neto)}\n`;
            msg += `Total (IVA inc): ${fmt(data.total_final)}\n\n`;
            msg += `Glosa: ${data.glosa || '(Sin glosa)'}`;

            alert(msg);
        }
    } catch (e) {
        console.error(e);
        alert("Error al previsualizar regla");
    }
}
