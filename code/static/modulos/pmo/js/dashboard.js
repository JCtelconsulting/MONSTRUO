export class PMODashboard {
    constructor() {
        this.containerInfo = null;
        this.init();
    }

    async init() {
        console.log("PMO Dashboard Init V4");
        this.switchTab('resumen');
        this.loadProjects();
    }

    switchTab(tabId) {
        document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
        const target = document.getElementById('view-' + tabId);
        if (target) target.classList.add('active');

        document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
        document.querySelectorAll('.tab-btn').forEach(el => {
            if (el.getAttribute('onclick')?.includes(`'${tabId}'`)) el.classList.add('active');
        });
    }

    openCreateModal() {
        document.getElementById('form-create-project').reset();
        document.getElementById('modal-create-project').showModal();
    }

    openIAModal() {
        document.getElementById('ia-content').value = '';
        document.getElementById('ia-result').style.display = 'none';
        document.getElementById('modal-ia-ingest').showModal();
    }

    async submitCreate() {
        const payload = {
            nombre: document.getElementById('proj-name').value,
            cliente_nombre: document.getElementById('proj-client').value,
            presupuesto_venta: parseFloat(document.getElementById('proj-budget').value) || 0,
            fecha_inicio: document.getElementById('proj-start').value || null,
            fecha_fin_estimada: document.getElementById('proj-end').value || null
        };

        try {
            const res = await fetch('/api/pmo/proyectos', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const json = await res.json();
            if (json.ok) {
                document.getElementById('modal-create-project').close();
                this.loadProjects();
            } else {
                alert('Error al crear proyecto: ' + JSON.stringify(json));
            }
        } catch (e) {
            console.error(e);
            alert('Error de conexión');
        }
    }

    // Funciones de Edicion y Detalle
    toggleDetail(id) {
        const details = document.getElementById(`details-${id}`);
        const icon = document.getElementById(`icon-expand-${id}`);
        if (!details || !icon) return;

        if (details.classList.contains('open')) {
            details.style.maxHeight = null;
            details.classList.remove('open');
            icon.classList.remove('fa-chevron-up');
            icon.classList.add('fa-chevron-down');
        } else {
            details.classList.add('open');
            details.style.maxHeight = details.scrollHeight + "px";
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-up');
        }
    }

    async updateProject(id) {
        const card = document.getElementById(`card-project-${id}`);
        if (!card) return;

        const payload = {
            presupuesto_venta: parseFloat(card.querySelector('.edit-budget').value) || 0,
            fecha_inicio: card.querySelector('.edit-start').value || null,
            fecha_fin_estimada: card.querySelector('.edit-end').value || null,
            estado: card.querySelector('.edit-status').value
        };

        try {
            const res = await fetch(`/api/pmo/proyectos/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const json = await res.json();
            if (json.ok) {
                // Feedback fluido: No recargar todo para no cerrar el acordeón
                // 1. Validar inputs visuales
                const newStatus = payload.estado;
                const newBudget = payload.presupuesto_venta;

                // 2. Actualizar Badge y Color Gauge (Visual Only)
                const statusMeta = this.getStatusInfo(newStatus);
                const badge = card.querySelector('.project-info span'); // El badge está ahi
                if (badge) {
                    badge.innerText = statusMeta.text;
                    badge.style.background = statusMeta.bg;
                    badge.style.color = statusMeta.color;
                }

                // 3. Feedback en Botón
                const btn = card.querySelector('button');
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="fas fa-check"></i> ¡Guardado!';
                btn.classList.add('btn-success');
                setTimeout(() => {
                    btn.innerHTML = originalText;
                    btn.classList.remove('btn-success');
                }, 2000);

            } else {
                alert("Error al actualizar: " + JSON.stringify(json));
            }
        } catch (e) { console.error(e); alert("Error red"); }
    }

    getStatusInfo(status) {
        const map = {
            'borrador': { text: 'Borrador', color: '#666', bg: '#333' },
            'activo': { text: 'Activo / Ejecución', color: '#000', bg: '#00d4ff' }, // Cyan Neon
            'pendiente_cliente': { text: 'Pendiente Cliente', color: '#000', bg: '#f59e0b' }, // Orange
            'pendiente_pago': { text: 'Pendiente Pago', color: '#fff', bg: '#ef4444' }, // Red
            'pendiente_interno': { text: 'Pendiente Interno', color: '#000', bg: '#fbbf24' }, // Yellow
            'cerrado': { text: 'Cerrado / Ok', color: '#fff', bg: '#10b981' } // Green
        };
        // Normalize status key
        const key = (status || 'borrador').toLowerCase();
        return map[key] || { text: key.toUpperCase(), color: '#ccc', bg: '#444' };
    }

    async submitIA() {
        const content = document.getElementById('ia-content').value;
        if (!content) return;

        const btn = document.querySelector('#form-ia-ingest button[type="submit"]');
        const originalText = btn.innerText;
        btn.innerText = "Pensando...";
        btn.disabled = true;

        try {
            const res = await fetch('/api/pmo/bitacora/ingesta', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ contenido_raw: content, origen: 'dashboard_manual' })
            });
            const json = await res.json();

            if (json.ok) {
                const resultDiv = document.getElementById('ia-result');
                const resultText = document.getElementById('ia-result-content');
                resultDiv.style.display = 'block';

                let html = `<strong>Resumen:</strong> ${json.ia_result.resumen}<br><br>`;

                if (json.ia_result.acciones.costos && json.ia_result.acciones.costos.length > 0) {
                    html += `<strong>Costos Detectados:</strong><ul>`;
                    json.ia_result.acciones.costos.forEach(c => {
                        html += `<li>${c.tipo}: ${c.descripcion} ($${c.monto || '?'})</li>`;
                    });
                    html += `</ul>`;
                }

                if (json.ia_result.acciones.tareas && json.ia_result.acciones.tareas.length > 0) {
                    html += `<strong>Tareas:</strong><ul>`;
                    json.ia_result.acciones.tareas.forEach(t => {
                        html += `<li>Asignar a ${t.responsable || '?'}: ${t.descripcion}</li>`;
                    });
                    html += `</ul>`;
                }

                resultText.innerHTML = html;
            } else {
                alert("Error IA: " + JSON.stringify(json));
            }
        } catch (e) {
            alert("Error de red IA: " + e.message);
        } finally {
            btn.innerText = originalText;
            btn.disabled = false;
        }
    }

    async loadProjects() {
        const container = document.getElementById('projects-list');
        if (!container) return;

        container.innerHTML = '<div style="text-align:center; padding:2rem; opacity:0.5;">Cargando proyectos...</div>';

        try {
            const res = await fetch('/api/pmo/proyectos');
            const data = await res.json();

            container.innerHTML = '';
            if (data.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:3rem; opacity:0.6; border:1px dashed #444; border-radius:12px;">No hay proyectos activos.<br><br>Dale al botón <b>+ Nuevo Proyecto</b></div>';
                this.updateKPIs(0, 0);
                return;
            }

            let totalBudget = 0;
            data.forEach(p => {
                totalBudget += (p.presupuesto_venta || 0);
                this.renderCard(container, p);
            });

            this.updateKPIs(data.length, totalBudget);

        } catch (e) {
            console.error(e);
            container.innerHTML = `<div style="color:red; text-align:center;">Error cargando proyectos: ${e.message}</div>`;
        }
    }

    updateKPIs(count, budget) {
        const kpiCount = document.getElementById('kpi-active-projects');
        if (kpiCount) kpiCount.innerText = count;

        const kpiBudget = document.getElementById('kpi-total-budget');
        if (kpiBudget) kpiBudget.innerText = new Intl.NumberFormat('es-CL', { style: 'currency', currency: 'CLP' }).format(budget);
    }

    renderCard(container, p) {
        const card = document.createElement('div');
        card.className = 'project-wide-card';
        card.id = `card-project-${p.id}`;

        const budget = p.presupuesto_venta || 0;
        const mockCost = budget > 0 ? Math.floor(Math.random() * (budget * 0.8)) : 0;
        const percent = budget > 0 ? Math.round((mockCost / budget) * 100) : 0;

        let color = '#28a745';
        if (percent > 50) color = '#ffcc00';
        if (percent > 85) color = '#ff3333';
        if (budget === 0) color = '#555';

        // Timeline Calc
        let progress = 0;
        const start = p.fecha_inicio ? new Date(p.fecha_inicio) : null;
        const end = p.fecha_fin_estimada ? new Date(p.fecha_fin_estimada) : null;
        const today = new Date();
        const startStr = start ? p.fecha_inicio : '';
        const endStr = end ? p.fecha_fin_estimada : '';

        if (start && end) {
            const totalDuration = end - start;
            const elapsed = today - start;
            if (totalDuration > 0) {
                progress = Math.min(100, Math.max(0, (elapsed / totalDuration) * 100));
            }
        }

        const statusMeta = this.getStatusInfo(p.estado || 'borrador');
        const badgeStyle = `background:${statusMeta.bg}; color:${statusMeta.color}; padding:4px 8px; border-radius:4px; font-weight:800; font-size:0.65rem; text-transform:uppercase; letter-spacing:0.5px; display:inline-block;`;

        card.innerHTML = `
            <div class="card-main-row" onclick="window.pmoDashboard.toggleDetail(${p.id})">
                <!-- COL 1: INFO (35%) -->
                <div class="project-info" style="flex: 0 0 35%; border-right:1px solid #333; padding-right:15px;">
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <!-- Proyecto -->
                        <div style="display:flex; align-items:center; gap:8px;">
                            <h3 style="margin:0; font-size:1.3rem; font-weight:700; color:#fff; line-height:1.2;">${p.nombre}</h3>
                            <span style="${badgeStyle}">${p.estado}</span> <!-- Usa texto raw o mapped? mejor mapped en v2 -->
                        </div>
                        <!-- Cliente (Etiqueta arriba) -->
                        <div style="margin-top:8px;">
                            <div style="font-size:0.7rem; color:#666; text-transform:uppercase; font-weight:bold; letter-spacing:1px; margin-bottom:2px;">
                                <i class="fas fa-building"></i> CLIENTE
                            </div>
                            <div style="font-size:1.3rem; font-weight:700; color:var(--neon); line-height:1.2;">
                                ${p.cliente_nombre || 'INTERNO'}
                            </div>
                        </div>
                    </div>
                </div>

                <!-- COL 2: TIMELINE (30%) - Centrado y Contenido -->
                <div class="project-timeline-area" style="flex: 0 0 35%; padding: 0 20px;">
                    <div style="width:100%; max-width:250px; margin:0 auto;">
                        <div class="timeline-dates" style="justify-content:space-between; display:flex;">
                            <span style="font-size:0.75rem; color:#aaa;">${start ? start.toLocaleDateString() : 'Inicio?'}</span>
                            <span style="font-size:0.75rem; color:#fff; font-weight:bold;">${progress.toFixed(0)}%</span>
                            <span style="font-size:0.75rem; color:#aaa;">${end ? end.toLocaleDateString() : 'Fin?'}</span>
                        </div>
                        <div class="timeline-bar-bg" style="height:6px; background:#222; border:1px solid #333;">
                            <div class="timeline-progress" style="width: ${progress}%; border-radius:4px;"></div>
                        </div>
                        <div style="text-align:center; margin-top:4px; font-size:0.65rem; color:#555; text-transform:uppercase;">
                            Progreso Tiempo
                        </div>
                    </div>
                </div>

                <!-- COL 3: GAUGE (30%) - Derecha -->
                <div style="flex: 0 0 30%; display:flex; justify-content:flex-end; align-items:center; gap:20px;">
                    <div class="gauge-container">
                        <div class="gauge-donut" style="--percent: ${percent}%; --card-accent: ${color}; transform:scale(0.9);">
                            <div class="gauge-value" style="font-size:0.9rem;">${percent}%</div>
                        </div>
                        <div class="gauge-label" style="opacity:0.7;">${budget > 0 ? 'Gasto' : 'S/P'}</div>
                    </div>
                    <div style="width:30px; text-align:center;">
                        <i id="icon-expand-${p.id}" class="fas fa-chevron-down" style="color:#444; font-size:1.2rem; transition:transform 0.3s;"></i>
                    </div>
                </div>
            </div>

            <!-- EXPANDABLE DETAILS -->
            <div id="details-${p.id}" class="card-details">
                <div class="details-grid">
                     <div class="form-group">
                        <label>Estado Global</label>
                        <select class="edit-input edit-status">
                            <option value="borrador" ${p.estado === 'borrador' ? 'selected' : ''}>Borrador</option>
                            <option value="activo" ${p.estado === 'activo' ? 'selected' : ''}>Activo (Ejecución)</option>
                            <option value="pendiente_cliente" ${p.estado === 'pendiente_cliente' ? 'selected' : ''}>Pendiente Cliente</option>
                            <option value="pendiente_pago" ${p.estado === 'pendiente_pago' ? 'selected' : ''}>Pendiente Pago</option>
                            <option value="pendiente_interno" ${p.estado === 'pendiente_interno' ? 'selected' : ''}>Pendiente Interno</option>
                            <option value="cerrado" ${p.estado === 'cerrado' ? 'selected' : ''}>Cerrado</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Presupuesto Venta ($)</label>
                        <input type="number" class="edit-input edit-budget" value="${budget}">
                    </div>
                    <div class="form-group">
                        <label>Cuadrilla Asignada</label>
                        <input type="text" class="edit-input" placeholder="Ej: Equipo Norte, Juan Pérez..." value=""> 
                    </div>
                     <div class="form-group">
                    </div>
                    <div class="form-group">
                        <label>Fecha Inicio</label>
                        <input type="date" class="edit-input edit-start" value="${startStr}">
                    </div>
                    <div class="form-group">
                        <label>Fecha Fin Estimada</label>
                        <input type="date" class="edit-input edit-end" value="${endStr}">
                    </div>
                    <div style="grid-column: 1 / -1; text-align:right; border-top:1px solid #444; padding-top:15px; margin-top:5px;">
                        <button class="btn-primary" onclick="window.pmoDashboard.updateProject(${p.id})">
                             <i class="fas fa-save"></i> Guardar Cambios & Auditar
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(card);
    }
}
