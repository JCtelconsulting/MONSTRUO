// --- LOGICA DE CONCILIACION BANCARIA ---

async function initBancos() {
    console.log("Inicializando Módulo Bancos...");
    await loadBankAccounts();
}

async function loadBankAccounts() {
    const selector = document.getElementById('bancoSelector');
    if (!selector) return;

    selector.innerHTML = '<option value="">Cargando...</option>';
    try {
        const banks = await window.fetchApi('/api/conciliacion/banks');
        selector.innerHTML = '<option value="">Seleccione Cuenta...</option>';

        banks.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b.id;
            opt.textContent = `${b.bank_name || b.name} (ID: ${b.laudus_account_id})`;
            selector.appendChild(opt);
        });

        // Auto-load if bank selected or add listener
        selector.addEventListener('change', (e) => {
            if (e.target.value) loadMovements(e.target.value);
        });

    } catch (e) {
        selector.innerHTML = '<option value="">Error al cargar bancos</option>';
        console.error("Error loading banks:", e);
    }
}

async function uploadStatement() {
    const bankId = document.getElementById('bancoSelector').value;
    const fileInput = document.getElementById('fileCartola');

    if (!bankId) {
        alert("Por favor seleccione una cuenta bancaria.");
        return;
    }
    if (!fileInput.files || fileInput.files.length === 0) {
        alert("Seleccione un archivo CSV para subir.");
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append('bank_account_id', bankId);
    formData.append('file', file);

    const btn = document.getElementById('btnUploadCartola');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Subiendo...';
    btn.disabled = true;

    try {
        // Usamos fetch nativo porque window.fetchApi suele ser JSON-centric
        // y necesitamos Multipart
        const token = getCookie('access_token'); // From utilidades.js logic usually

        // Si fetchApi maneja auth, mejor usarlo si soporta FormData. 
        // Asumiendo fetchApi de admin.js:
        // si body es FormData, no pone Content-Type json.

        const resp = await window.fetchApi('/api/conciliacion/upload', {
            method: 'POST',
            body: formData
        });

        if (resp.status === 'success') {
            alert(`Carga Exitosa!\nPeriodo: ${resp.period}\nMovimientos: ${resp.lines_inserted} insertados, ${resp.lines_skipped_duplicate} duplicados.`);
            fileInput.value = ''; // Clear input
            // TODO: Recargar tabla de conciliación si existiera
        } else {
            alert("Error desconocido en carga.");
        }

    } catch (e) {
        console.error(e);
        alert("Error al subir cartola: " + e.message);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function syncFromLaudus() {
    const bankId = document.getElementById('bancoSelector').value;
    if (!bankId) {
        alert("Seleccione una cuenta bancaria (Ej: Santander).");
        return;
    }

    const btn = document.getElementById('btnSyncLaudus');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sincronizando...';
    btn.disabled = true;

    try {
        // Prepare FormData for endpoint (endpoint expects Form params)
        const formData = new FormData();
        formData.append('bank_account_id', bankId);

        const resp = await window.fetchApi('/api/conciliacion/sync', {
            method: 'POST',
            body: formData
        });

        if (resp.status === 'success') {
            const r = resp.results[0]; // Assuming single bank requested
            if (r) {
                // Auto-Match Trigger
                if (r.statement_id) {
                    window.showToast("Sincronización OK. Ejecutando Smart Match...", "info");

                    // Call Matcher silently
                    const formDataMatch = new FormData();
                    formDataMatch.append('statement_id', r.statement_id);
                    await window.fetchApi('/api/conciliacion/match', { method: 'POST', body: formDataMatch });

                    alert(`Sincronización y Conciliación Completada.\nBanco: ${r.bank}\nMovimientos: ${r.lines}`);
                } else {
                    alert(`Sincronización Completada (Sin ID de cartola).\nBanco: ${r.bank}`);
                }
            }
            // Reload table
            await loadMovements(bankId);
        } else {
            alert("Error en sincronización: " + (resp.detail || 'Desconocido'));
        }
    } catch (e) {
        console.error(e);
        alert("Error al sincronizar: " + e.message);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function loadMovements(bankId) {
    // Also load statements table
    loadStatements(bankId);

    const tbody = document.getElementById('tabla-movimientos');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Cargando...</td></tr>';

    try {
        const url = `/api/conciliacion/movements?bank_account_id=${bankId}`;
        const rows = await window.fetchApi(url);

        if (!rows || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No hay movimientos registrados.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        rows.forEach(r => {
            const amt = r.amount;
            const color = amt < 0 ? '#ff5555' : '#55ff55';
            const fmtAmt = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(amt);

            // Match Display Logic (Same as loadStatementDetails)
            let matchHtml = '<span style="opacity:0.3">-</span>';
            if (r.reconciled_at) {
                matchHtml = '<span class="text-success"><i class="fas fa-check-circle"></i> Conciliado</span>';
            } else if (r.rec_id) {
                const conf = Math.round(r.confidence * 100);
                const badgeClass = r.confidence >= 0.9 ? 'badge-success' : 'badge-warning';

                let detail = '';
                if (r.match_type === 'invoice') {
                    const fmInv = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(r.invoice_amount);
                    detail = `Factura #${r.external_id || r.invoice_id} (${r.customer_id})<br>Monto: ${fmInv}`;
                } else {
                    detail = r.match_desc ? r.match_desc.substring(0, 20) + '...' : 'Match Genérico';
                }

                matchHtml = `
                    <div style="font-size:11px; display:flex; align-items:center; justify-content:space-between;">
                        <div>
                            <span class="badge ${badgeClass}">Match (${conf}%)</span><br>
                            <small>${detail}</small>
                        </div>
                        <button class="btn-xs btn-primary" onclick="approveMatch(${r.rec_id})" title="Confirmar Pago">
                            <i class="fas fa-check"></i>
                        </button>
                    </div>
                `;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${r.date}</td>
                <td>${r.description}</td>
                <td>${r.document_number || '-'}</td>
                <td style="text-align:right; color:${color}; font-weight:bold;">${fmtAmt}</td>
                <td style="text-align:right;">${r.balance ? r.balance : '-'}</td>
                <td>${matchHtml}</td>
            `;
            tbody.appendChild(tr);
        });

    } catch (e) {
        console.error("Error loading movements:", e);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:red;">Error al cargar movimientos.</td></tr>';
    }
}

async function loadStatements(bankId) {
    const tbody = document.getElementById('tabla-cartolas');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Cargando...</td></tr>';

    try {
        const rows = await window.fetchApi(`/api/conciliacion/statements?bank_account_id=${bankId}`);
        if (!rows || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Sin historial.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        rows.forEach(r => {
            const btn = `<button class="btn-xs btn-primary" onclick="runMatch(${r.id})"><i class="fas fa-magic"></i> Conciliar</button>`;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${r.id}</td>
                <td>${r.uploaded_at.substring(0, 16)}</td>
                <td>${r.filename}</td>
                <td>${r.period_start || '?'} - ${r.period_end || '?'}</td>
                <td>${r.status}</td>
                <td>${btn}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error(e);
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:red;">Error: ${e.message}</td></tr>`;
    }
}

async function runMatch(stmtId) {
    if (!confirm("¿Ejecutar motor de conciliación para esta cartola?")) return;

    try {
        const formData = new FormData();
        formData.append('statement_id', stmtId);

        const res = await window.fetchApi('/api/conciliacion/match', {
            method: 'POST',
            body: formData
        });

        if (res.status === 'success') {
            const r = res.results;
            alert(`Motor Ejecutado.\nExactos: ${r.exact}\nSugeridos: ${r.suggested}`);
            loadStatementDetails(stmtId);
        }
    } catch (e) {
        alert("Error al ejecutar match: " + e.message);
    }
}

async function loadStatementDetails(stmtId) {
    const tbody = document.getElementById('tabla-movimientos');
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Cargando detalles...</td></tr>';

    try {
        const rows = await window.fetchApi(`/api/conciliacion/matches?statement_id=${stmtId}`);
        if (!rows || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Sin movimientos.</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        rows.forEach(r => {
            const amt = r.amount;
            const color = amt < 0 ? '#ff5555' : '#55ff55';
            const fmtAmt = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(amt);

            let matchHtml = '<span style="opacity:0.3">-</span>';
            if (r.rec_id) {
                const conf = Math.round(r.confidence * 100);
                const badgeClass = r.confidence >= 0.9 ? 'badge-success' : 'badge-warning';

                let detail = '';
                if (r.match_type === 'invoice') {
                    const fmInv = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(r.invoice_amount);
                    detail = `Factura #${r.external_id || r.invoice_id} (${r.customer_id})<br>Monto: ${fmInv}`;
                } else {
                    detail = r.match_desc ? r.match_desc.substring(0, 20) + '...' : 'Match Genérico';
                }

                matchHtml = `
                    <div style="font-size:11px; display:flex; align-items:center; justify-content:space-between;">
                        <div>
                            <span class="badge ${badgeClass}">Match (${conf}%)</span><br>
                            <small>${detail}</small>
                        </div>
                        <button class="btn-xs btn-primary" onclick="approveMatch(${r.rec_id})" title="Confirmar Pago">
                            <i class="fas fa-check"></i>
                        </button>
                    </div>
                `;
            }

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${r.date}</td>
                <td>${r.description}</td>
                <td>${r.document_number || '-'}</td>
                <td style="text-align:right; color:${color}; font-weight:bold;">${fmtAmt}</td>
                <td style="text-align:right;">-</td>
                <td>${matchHtml}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error(e);
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:red;">Error.</td></tr>';
    }
}

async function approveMatch(matchId) {
    if (!confirm("¿Confirmar este match? Se marcará la factura como PAGADA localmente (sin avisar a Laudus).")) return;

    try {
        const formData = new FormData();
        formData.append('match_id', matchId);

        const res = await window.fetchApi('/api/conciliacion/approve', {
            method: 'POST',
            body: formData
        });

        if (res.status === 'success') {
            window.showToast("Pago registrado correctamente (Local)", "success");
            // Reload details to verify
            const stmtId = document.querySelector('button[onclick^="runMatch"]').getAttribute('onclick').match(/\d+/)[0];
            // Dirty hack to get stmtId, better if we stored it global or passed it.
            // For now, let's just reload the active statement if possible or reload statements.
            // Actually `loadStatementDetails` needs stmtId. 
            // Let's assume the user hasn't changed view. 
            // We can re-fetch or just hide the row? Re-fetching is safer.

            // Better: find parent TR and remove it or update it.
            // But we don't have stmtId easily here unless we store it.
            // Let's reload the whole movements list for the bank... wait that resets view.

            // To be safe: Just alert and reload tab or nothing.
            // Let's try to reload if we can find the ID from context?
            // Nope. Let's just remove the button to visualize success.
            const btn = document.querySelector(`button[onclick="approveMatch(${matchId})"]`);
            if (btn) {
                btn.parentElement.innerHTML = '<span class="text-success"><i class="fas fa-check-circle"></i> Pagado</span>';
            }
        }
    } catch (e) {
        window.showToast("Error al aprobar: " + e.message, "error");
    }
}

// Hook up change event on init
// We need to modify initBancos to add listener

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
}
