export class FundacionCalendar {
    constructor() {
        this.currentDate = new Date();
        this.tasks = [];
        this.user = null;
        this.view = 'month'; // day, week, month
        this.activeTab = 'calendario'; // calendario, planificacion
        this.currentCurso = 'Todos';
        this.currentMadre = null;
        this.currentSub = null;
        this.filters = {
            search: '',
            status: 'todos',
            tipo: 'todos' // todos, clases, ejecutiva
        };
        this.draggedTask = null;
        this.currentEditingTask = null;
        this._fetchPromise = null; // Anti-doble-fetch
        this.init();
    }

    async init() {
        console.log("Iniciando Calendario Fundación v4...");
        await this.loadSession();
        this.setupEventListeners();
        await this.fetchTasks();   // Carga ÚNICA inicial
        this.render();
        this.renderTasks();
    }

    async loadSession() {
        try {
            const data = await window.fetchApi('/api/sesion');
            if (data.ok) {
                this.user = data;
                if (data.roles?.some(r => ['admin', 'monitora', 'gerencia', 'ejecutiva'].includes(r))) {
                    document.getElementById('btn-new-task').hidden = false;
                }
            }
        } catch (e) {
            console.error("Error cargando sesión", e);
        }
    }

    setupEventListeners() {
        // Tab Switching
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.onclick = (e) => {
                const tab = e.currentTarget.dataset.tab;
                this.switchTab(tab);
            };
        });

        // Navigation (Calendar) - SIN llamada al servidor
        document.getElementById('prev-period').onclick = () => this.navigate(-1);
        document.getElementById('next-period').onclick = () => this.navigate(1);
        document.getElementById('btn-today').onclick = () => {
            this.currentDate = new Date();
            this.render();
            this.renderTasks();
        };

        // View Selection dropdown
        const btnView = document.getElementById('btn-view-dropdown');
        const content = document.getElementById('view-dropdown-content');

        if (btnView) {
            btnView.onclick = (e) => {
                e.stopPropagation();
                content.classList.toggle('show');
            };
        }

        window.onclick = () => {
            if (content) content.classList.remove('show');
        };

        // Cambio de vista - SIN llamada al servidor
        document.querySelectorAll('.dropdown-item[data-view]').forEach(item => {
            item.onclick = (e) => {
                this.view = e.currentTarget.dataset.view;
                document.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active'));
                e.currentTarget.classList.add('active');
                document.getElementById('active-view-label').textContent = e.currentTarget.textContent;
                this.render();
                this.renderTasks();
            };
        });

        // Planning Filters
        const searchInput = document.getElementById('search-tasks');
        if (searchInput) {
            let debounceTimer;
            searchInput.oninput = (e) => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    this.filters.search = e.target.value.toLowerCase();
                    this.renderPlanningView();
                }, 150);
            };
        }

        const filterStatus = document.getElementById('filter-status');
        if (filterStatus) {
            filterStatus.onchange = (e) => {
                this.filters.status = e.target.value;
                this.renderPlanningView();
            };
        }

        // Filtro de tipo - SIN llamada al servidor
        const filterTipo = document.getElementById('filter-tipo');
        if (filterTipo) {
            filterTipo.onchange = (e) => {
                this.filters.tipo = e.target.value;
                if (this.activeTab === 'planificacion') {
                    this.renderCategories();
                    this.renderPlanningView();
                } else {
                    this.renderTasks();
                }
            };
        }

        // Modals
        const btnNew = document.getElementById('btn-new-task');
        if (btnNew) btnNew.onclick = () => this.openTaskModal();

        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-task').close();
        });
        document.getElementById('form-task').onsubmit = (e) => {
            e.preventDefault();
            this.saveTask();
        };
        document.getElementById('btn-delete-task').onclick = () => this.deleteTask();

        // Replacement Catalog
        const btnReplace = document.getElementById('btn-replace-task');
        if (btnReplace) {
            btnReplace.onclick = () => this.openReplacementCatalog();
        }

        document.querySelectorAll('.close-catalog-modal').forEach(btn => {
            btn.onclick = () => document.getElementById('modal-catalog').close();
        });

        // Global Drag Events for cleanup
        document.addEventListener('dragend', () => {
            document.querySelectorAll('.time-task-item').forEach(el => el.classList.remove('dragging'));
            document.querySelectorAll('.time-slot-col').forEach(el => el.classList.remove('drag-over'));
        });
    }

    switchTab(tab) {
        this.activeTab = tab;
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `pane-${tab}`));

        if (tab === 'planificacion') {
            this.renderCategories();
            this.renderPlanningView();
        } else {
            this.render();
            this.renderTasks();
        }
    }

    // CARGA COMPLETA - solo se llama al iniciar o tras guardar/eliminar
    async fetchTasks() {
        if (this._fetchPromise) return this._fetchPromise;
        this._fetchPromise = (async () => {
            try {
                const data = await window.fetchApi('/api/fundacion/tareas');
                this.tasks = data;
            } catch (e) {
                console.error("Error fetching tasks", e);
            } finally {
                this._fetchPromise = null;
            }
        })();
        return this._fetchPromise;
    }

    // Navegación - SOLO renderizado local, sin red
    navigate(dir) {
        if (this.view === 'month') {
            this.currentDate.setMonth(this.currentDate.getMonth() + dir);
        } else if (this.view === 'week') {
            this.currentDate.setDate(this.currentDate.getDate() + (dir * 7));
        } else {
            this.currentDate.setDate(this.currentDate.getDate() + dir);
        }
        this.render();
        this.renderTasks();
    }

    render() {
        if (this.activeTab !== 'calendario') return;

        const container = document.getElementById('calendar-view-container');
        const monthLabel = document.getElementById('current-month');
        if (!container || !monthLabel) return;

        if (this.view === 'day') {
            monthLabel.textContent = this.currentDate.toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' }).toUpperCase();
            this.renderTimeGridView(container, 1);
        } else if (this.view === 'week') {
            const start = this.getStartOfWeek(this.currentDate);
            const end = new Date(start);
            end.setDate(end.getDate() + 6);
            monthLabel.textContent = `${start.getDate()} - ${end.getDate()} ${start.toLocaleString('es-ES', { month: 'short' })} ${start.getFullYear()}`.toUpperCase();
            this.renderTimeGridView(container, 7);
        } else {
            monthLabel.textContent = this.currentDate.toLocaleString('es-ES', { month: 'long', year: 'numeric' }).toUpperCase();
            this.renderMonthView(container);
        }
    }

    renderMonthView(container) {
        container.innerHTML = `
            <div class="calendar-grid" id="calendar-grid">
                ${['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'].map(h => `<div class="calendar-day-head">${h}</div>`).join('')}
            </div>`;

        const grid = document.getElementById('calendar-grid');
        const year = this.currentDate.getFullYear();
        const month = this.currentDate.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDayIdx = new Date(year, month + 1, 0).getDate();

        let startIdx = firstDay.getDay() - 1;
        if (startIdx === -1) startIdx = 6;

        const prevLastDay = new Date(year, month, 0).getDate();
        for (let i = startIdx; i > 0; i--) this.createDayEl(grid, prevLastDay - i + 1, true);
        for (let i = 1; i <= lastDayIdx; i++) {
            const isToday = this.isSameDay(new Date(year, month, i), new Date());
            this.createDayEl(grid, i, false, isToday);
        }

        const totalUsed = grid.children.length;
        const totalCells = totalUsed > 35 ? 42 : 35;
        for (let i = 1; grid.children.length < totalCells; i++) {
            this.createDayEl(grid, i, true);
        }
    }

    createDayEl(grid, num, isOther, isToday) {
        const div = document.createElement('div');
        div.className = `calendar-day ${isOther ? 'other-month' : ''} ${isToday ? 'today' : ''}`;
        div.innerHTML = `<span class="day-number">${num}</span><div class="task-list"></div>`;
        if (!isOther) div.dataset.day = num;
        grid.appendChild(div);
    }

    renderTimeGridView(container, days) {
        container.style.setProperty('--cols', days);
        const startDate = days === 7 ? this.getStartOfWeek(this.currentDate) : new Date(this.currentDate);

        let headerHtml = '<div class="time-header-cell">Hora</div>';
        for (let i = 0; i < days; i++) {
            const d = new Date(startDate);
            d.setDate(d.getDate() + i);
            headerHtml += `<div class="time-header-cell">${d.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric' })}</div>`;
        }

        let bodyHtml = '<div class="time-label-col">';
        for (let h = 8; h <= 20; h++) {
            bodyHtml += `<div class="time-label">${h}:00</div>`;
        }
        bodyHtml += '</div>';

        let allDayHtml = '<div class="all-day-row"><div class="all-day-label">Todo el día</div>';
        for (let i = 0; i < days; i++) {
            const d = new Date(startDate);
            d.setDate(d.getDate() + i);
            const dateStr = this._localDateStr(d);
            allDayHtml += `<div class="all-day-cell" data-date="${dateStr}"></div>`;
        }
        allDayHtml += '</div>';

        for (let i = 0; i < days; i++) {
            const d = new Date(startDate);
            d.setDate(d.getDate() + i);
            const dateStr = this._localDateStr(d);
            bodyHtml += `<div class="time-slot-col" data-date="${dateStr}">`;
            for (let h = 8; h <= 20; h++) {
                bodyHtml += `<div class="time-slot"></div>`;
            }
            bodyHtml += '</div>';
        }

        container.innerHTML = `
            <div class="time-grid-wrapper">
                <div class="time-grid-header">${headerHtml}</div>
                ${allDayHtml}
                <div class="time-grid-body">${bodyHtml}</div>
            </div>`;

        // Add drop events to columns
        container.querySelectorAll('.time-slot-col').forEach(col => {
            col.ondragover = (e) => {
                e.preventDefault();
                col.classList.add('drag-over');
            };
            col.ondragleave = () => col.classList.remove('drag-over');
            col.ondrop = (e) => this.handleDrop(e, col);
        });
    }

    // Utilidad: obtener fecha local YYYY-MM-DD sin problemas de zona horaria
    _localDateStr(d) {
        const pad = n => n.toString().padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    }

    renderCategories() {
        const container = document.getElementById('planning-categories');
        if (!container) return;

        // Pre-filtrar por tipo
        const tasksForCategories = this._filterByTipo();

        // Estructura: hierarchy[curso][madre][sub]
        const hierarchy = {};
        tasksForCategories.forEach(t => {
            const curso = t.curso || 'Ejecutiva';
            const madre = t.categoria_madre || 'Sin Categoría';
            const sub = t.subcategoria || '(General)';

            if (!hierarchy[curso]) hierarchy[curso] = {};
            if (!hierarchy[curso][madre]) hierarchy[curso][madre] = {};
            if (!hierarchy[curso][madre][sub]) hierarchy[curso][madre][sub] = 0;
            hierarchy[curso][madre][sub]++;
        });

        let html = `
            <li class="category-item ${this.currentCurso === 'Todos' ? 'active' : ''}" onclick="window.fundacion.setHierarchy('Todos', null, null)">
                <span><strong>Todos los Cursos</strong></span>
                <span class="cat-count">${tasksForCategories.length}</span>
            </li>
        `;

        Object.keys(hierarchy).sort().forEach(curso => {
            const isCursoActive = this.currentCurso === curso;
            const isEjecutiva = (curso === 'Ejecutiva');

            // Calcular total curso
            const totalCurso = Object.values(hierarchy[curso]).reduce((acc, madre) =>
                acc + Object.values(madre).reduce((a, b) => a + b, 0), 0);

            html += `
                <li class="category-item level-1 ${isCursoActive ? 'active' : ''}" onclick="window.fundacion.setHierarchy('${curso}', null, null)">
                    <i class="fas ${isEjecutiva ? 'fa-briefcase' : 'fa-graduation-cap'}" style="margin-right:8px; opacity:0.7"></i>
                    <span>${curso}</span>
                    <span class="cat-count">${totalCurso}</span>
                </li>
            `;

            if (isCursoActive) {
                const madres = hierarchy[curso];

                if (isEjecutiva) {
                    const subsEjecutivas = {};
                    Object.keys(madres).forEach(m => {
                        Object.keys(madres[m]).forEach(s => {
                            subsEjecutivas[s] = (subsEjecutivas[s] || 0) + madres[m][s];
                        });
                    });

                    Object.keys(subsEjecutivas).sort().forEach(sub => {
                        const isSubActive = this.currentSub === sub;
                        html += `
                            <li class="category-item level-2 ${isSubActive ? 'active' : ''}" style="margin-left: 15px;" onclick="window.fundacion.setHierarchy('${curso}', null, '${sub}')">
                                <i class="fas fa-tag" style="margin-right:8px; opacity:0.6"></i>
                                <span>${sub}</span>
                                <span class="cat-count">${subsEjecutivas[sub]}</span>
                            </li>
                        `;
                    });
                } else {
                    Object.keys(madres).sort().forEach(madre => {
                        const isMadreActive = this.currentMadre === madre;
                        const totalMadre = Object.values(madres[madre]).reduce((a, b) => a + b, 0);

                        html += `
                            <li class="category-item level-2 ${isMadreActive ? 'active' : ''}" style="margin-left: 15px;" onclick="window.fundacion.setHierarchy('${curso}', '${madre}', null)">
                                <i class="fas fa-folder-open" style="margin-right:8px; opacity:0.6"></i>
                                <span>${madre}</span>
                                <span class="cat-count">${totalMadre}</span>
                            </li>
                        `;

                        if (isMadreActive) {
                            const subs = madres[madre];
                            Object.keys(subs).sort().forEach(sub => {
                                const isSubActive = this.currentSub === sub;
                                html += `
                                    <li class="category-item level-3 ${isSubActive ? 'active' : ''}" style="margin-left: 30px; font-size: 0.8rem;" onclick="window.fundacion.setHierarchy('${curso}', '${madre}', '${sub}')">
                                        <span>${sub}</span>
                                        <span class="cat-count">${subs[sub]}</span>
                                    </li>
                                `;
                            });
                        }
                    });
                }
            }
        });

        container.innerHTML = html;
    }

    setHierarchy(curso, madre, sub) {
        this.currentCurso = curso;
        this.currentMadre = madre;
        this.currentSub = sub;
        this.renderCategories();
        this.renderPlanningView();
    }

    // Filtro central reutilizable por tipo
    _filterByTipo() {
        return this.tasks.filter(t => {
            if (this.filters.tipo === 'todos') return true;
            if (this.filters.tipo === 'ejecutiva') return t.categoria === 'ejecutiva';
            if (this.filters.tipo === 'clases') return t.categoria !== 'ejecutiva';
            return true;
        });
    }

    renderPlanningView() {
        const container = document.getElementById('planning-list-container');
        const countEl = document.getElementById('tasks-count');
        if (!container || !countEl) return;

        const filtered = this._filterByTipo().filter(t => {
            const matchesCurso = this.currentCurso === 'Todos' || (t.curso || 'Ejecutiva') === this.currentCurso;
            const matchesMadre = !this.currentMadre || (t.categoria_madre || 'Sin Categoría') === this.currentMadre;

            let matchesSub = true;
            if (this.currentSub) {
                const subValue = t.subcategoria || '(General)';
                matchesSub = (subValue === this.currentSub);
            }

            const matchesSearch = t.titulo.toLowerCase().includes(this.filters.search) ||
                (t.descripcion || '').toLowerCase().includes(this.filters.search);
            const matchesStatus = this.filters.status === 'todos' || t.estado === this.filters.status;
            return matchesCurso && matchesMadre && matchesSub && matchesSearch && matchesStatus;
        });

        countEl.textContent = `${filtered.length} actividades`;

        if (filtered.length === 0) {
            container.innerHTML = '<div style="padding:40px; text-align:center; color:#666;">No hay actividades en esta categoría con los filtros actuales.</div>';
            return;
        }

        let html = `
            <table class="planning-table">
                <thead>
                    <tr>
                        <th>Actividad</th>
                        <th>Fecha Planeada</th>
                        <th>Estado</th>
                        <th>Seguimiento</th>
                    </tr>
                </thead>
                <tbody>
        `;

        filtered.forEach(t => {
            const start = new Date(t.fecha_inicio).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
            const hasReport = !!t.reporte;
            const hasIssues = !!t.imprevistos;

            let reportStatus = '<span style="color:#666">Sin reporte</span>';
            if (hasIssues) reportStatus = '<span style="color:#ff4d4d"><i class="fas fa-exclamation-triangle"></i> Imprevisto</span>';
            else if (hasReport) reportStatus = '<span style="color:var(--neon)"><i class="fas fa-check-circle"></i> Reportado</span>';

            html += `
                <tr class="planning-row" style="cursor:pointer" onclick="window.fundacion.${t.categoria === 'ejecutiva' ? 'openExecutiveInfo' : 'openTaskModal'}(${JSON.stringify(t).replace(/"/g, '&quot;')})">
                    <td style="border-left: 4px solid ${t.color}">
                        <div style="font-weight:600">${t.titulo}</div>
                        <div style="color:#888; font-size:0.75rem">${(t.descripcion || '').substring(0, 100)}${t.descripcion?.length > 100 ? '...' : ''}</div>
                    </td>
                    <td>${start}</td>
                    <td><span class="pill" style="border-color:${t.color}; font-size:0.7rem">${t.estado}</span></td>
                    <td>${reportStatus}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        container.innerHTML = html;
    }

    renderTasks() {
        const filtered = this._filterByTipo();

        if (this.view === 'month') {
            document.querySelectorAll('.task-list').forEach(l => l.innerHTML = '');
            const month = this.currentDate.getMonth();
            const year = this.currentDate.getFullYear();

            // Crear un fragmento por día para batch DOM
            const dayFragments = {};
            filtered.forEach(t => {
                const start = new Date(t.fecha_inicio);
                if (start.getMonth() === month && start.getFullYear() === year) {
                    const day = start.getDate();
                    if (!dayFragments[day]) dayFragments[day] = document.createDocumentFragment();
                    dayFragments[day].appendChild(this.createTaskItem(t, false));
                }
            });

            // Insertar todos los fragmentos de una vez
            Object.entries(dayFragments).forEach(([day, frag]) => {
                const el = document.querySelector(`.calendar-day[data-day="${day}"] .task-list`);
                if (el) el.appendChild(frag);
            });
        } else {
            // Limpiar contenedores
            document.querySelectorAll('.all-day-cell').forEach(c => c.innerHTML = '');
            document.querySelectorAll('.time-slot-col').forEach(c => {
                c.querySelectorAll('.time-task-item').forEach(item => item.remove());
            });

            // Usar fragmentos para batch
            const allDayFrags = {};
            const timeFrags = {};

            filtered.forEach(t => {
                const start = new Date(t.fecha_inicio);
                const dateStr = this._localDateStr(start);

                if (t.categoria === 'ejecutiva') {
                    if (!allDayFrags[dateStr]) allDayFrags[dateStr] = document.createDocumentFragment();
                    allDayFrags[dateStr].appendChild(this.createTaskItem(t, true));
                } else {
                    if (!timeFrags[dateStr]) timeFrags[dateStr] = document.createDocumentFragment();
                    timeFrags[dateStr].appendChild(this.createTaskItem(t, true));
                }
            });

            Object.entries(allDayFrags).forEach(([dateStr, frag]) => {
                const col = document.querySelector(`.all-day-cell[data-date="${dateStr}"]`);
                if (col) col.appendChild(frag);
            });

            Object.entries(timeFrags).forEach(([dateStr, frag]) => {
                const col = document.querySelector(`.time-slot-col[data-date="${dateStr}"]`);
                if (col) col.appendChild(frag);
            });
        }
    }

    createTaskItem(t, isTimeGrid) {
        const div = document.createElement('div');
        const isAllDay = isTimeGrid && t.categoria === 'ejecutiva';

        div.className = isAllDay ? 'all-day-task-item' : (isTimeGrid ? 'time-task-item' : 'task-item');
        div.style.borderLeftColor = t.color;

        let content = t.titulo;
        if (t.imprevistos) content = `<i class="fas fa-exclamation-triangle" style="color:#ff4d4d"></i> ` + content;
        else if (t.reporte) content = `<i class="fas fa-check-circle" style="color:var(--neon); font-size:0.7em"></i> ` + content;

        div.innerHTML = content;
        div.title = t.titulo;

        if (isTimeGrid && !isAllDay) {
            const start = new Date(t.fecha_inicio);
            const end = t.fecha_fin ? new Date(t.fecha_fin) : new Date(start.getTime() + 3600000);
            const startHour = start.getHours() + start.getMinutes() / 60;
            const endHour = end.getHours() + end.getMinutes() / 60;

            const top = (startHour - 8) * 80;
            const height = (endHour - startHour) * 80;

            if (startHour >= 8 && startHour <= 21) {
                div.style.top = `${top}px`;
                div.style.height = `${Math.max(30, height)}px`;
                div.style.backgroundColor = `${t.color}22`;
            } else {
                div.style.display = 'none';
            }
        }

        div.onclick = (e) => {
            e.stopPropagation();
            if (t.categoria === 'ejecutiva') {
                this.openExecutiveInfo(t);
            } else {
                this.currentEditingTask = t;
                this.openReplacementCatalog();
            }
        };

        if (isTimeGrid && !isAllDay) {
            div.draggable = true;
            div.ondragstart = (e) => {
                this.draggedTask = t;
                div.classList.add('dragging');
                e.dataTransfer.setData('text/plain', t.id);
                e.dataTransfer.effectAllowed = 'move';
            };
        }

        return div;
    }

    getStartOfWeek(date) {
        const d = new Date(date);
        const day = d.getDay();
        const diff = d.getDate() - day + (day === 0 ? -6 : 1);
        return new Date(d.setDate(diff));
    }

    toLocalISO(date) {
        const pad = (n) => n.toString().padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    async handleDrop(e, col) {
        e.preventDefault();
        col.classList.remove('drag-over');
        if (!this.draggedTask) return;

        const bodyGrid = col.closest('.time-grid-body');
        const rect = bodyGrid.getBoundingClientRect();

        // El scroll es del bodyGrid
        const relativeY = (e.clientY - rect.top) + bodyGrid.scrollTop;

        // Ajuste: 80px por hora, empezando a las 8:00
        const hourDecimal = 8 + (relativeY / 80);

        // Ajuste a la media hora más cercana
        const snappedHour = Math.round(hourDecimal * 2) / 2;
        const hours = Math.floor(snappedHour);
        const minutes = (snappedHour % 1) * 60;

        const dateParts = col.dataset.date.split('-');
        const newStart = new Date(dateParts[0], dateParts[1] - 1, dateParts[2], hours, minutes);

        // Fixed 1.5 hours duration
        const duration = 1.5 * 3600000;
        const newEnd = new Date(newStart.getTime() + duration);

        // Detectar solapamientos y buscar hueco
        let currentStart = newStart;
        let currentEnd = newEnd;
        let checkCount = 0;
        const maxChecks = 48;

        const findOverlap = (s, e) => {
            return this.tasks.find(t => {
                if (t.id === this.draggedTask.id) return false;
                const tStart = new Date(t.fecha_inicio);
                const tEnd = t.fecha_fin ? new Date(t.fecha_fin) : new Date(tStart.getTime() + 1.5 * 3600000);
                if (!this.isSameDay(tStart, s)) return false;

                return (s < tEnd && e > tStart);
            });
        };

        let overlapping = findOverlap(currentStart, currentEnd);

        if (overlapping) {
            const overlapStart = new Date(overlapping.fecha_inicio);
            const overlapEnd = overlapping.fecha_fin ? new Date(overlapping.fecha_fin) : new Date(overlapStart.getTime() + 1.5 * 3600000);
            const overlapCenter = overlapStart.getTime() + (overlapEnd.getTime() - overlapStart.getTime()) / 2;
            const dropCenter = currentStart.getTime() + duration / 2;

            const step = (dropCenter < overlapCenter) ? -1800000 : 1800000;

            while (overlapping && checkCount < maxChecks) {
                currentStart = new Date(currentStart.getTime() + step);
                currentEnd = new Date(currentStart.getTime() + duration);

                if (currentStart.getHours() < 7 || currentStart.getHours() > 21) break;

                overlapping = findOverlap(currentStart, currentEnd);
                checkCount++;
            }
        }

        try {
            const startStr = this.toLocalISO(currentStart);
            const endStr = this.toLocalISO(currentEnd);

            await window.fetchApi(`/api/fundacion/tareas/${this.draggedTask.id}`, {
                method: 'PATCH',
                body: JSON.stringify({ fecha_inicio: startStr, fecha_fin: endStr })
            });

            if (checkCount > 0) {
                window.showToast("Actividad ajustada al hueco más cercano", "info");
            } else {
                window.showToast("Actividad movida", "success");
            }

            await this.fetchTasks();
            this.render();
            this.renderTasks();
        } catch (err) {
            console.error("Drop error:", err);
            window.showToast("Error al mover actividad", "error");
        } finally {
            this.draggedTask = null;
        }
    }

    isSameDay(d1, d2) {
        return d1.getDate() === d2.getDate() && d1.getMonth() === d2.getMonth() && d1.getFullYear() === d2.getFullYear();
    }

    openExecutiveInfo(t) {
        const modal = document.getElementById('modal-executive-info');
        if (!modal) return;

        const tag = document.getElementById('exec-info-tag');
        const title = document.getElementById('exec-info-title');
        const dateText = document.getElementById('exec-info-date-text');
        const desc = document.getElementById('exec-info-desc');

        tag.textContent = t.subcategoria || 'Hito';
        tag.style.borderColor = t.color;
        tag.style.color = t.color;

        title.textContent = t.titulo;

        const date = new Date(t.fecha_inicio);
        dateText.textContent = date.toLocaleDateString('es-ES', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric'
        }).replace(/^\w/, c => c.toUpperCase());

        desc.textContent = t.descripcion || 'Sin descripción adicional para este hito.';

        modal.showModal();
    }

    openTaskModal(task = null) {
        const modal = document.getElementById('modal-task');
        const form = document.getElementById('form-task');
        this.currentEditingTask = task;
        document.getElementById('task-id').value = task ? task.id : '';

        const roles = this.user?.roles || [];
        const isMonitora = roles.some(r => ['admin', 'monitora', 'gerencia', 'ejecutiva'].includes(r));
        const isOwner = task && task.asignado_a === this.user?.username;

        // Reset visibility
        document.getElementById('report-section').style.display = 'block';

        if (task) {
            document.getElementById('modal-title').textContent = "Detalle de Tarea";
            document.getElementById('task-title').value = task.titulo;
            document.getElementById('task-desc').value = task.descripcion || '';
            document.getElementById('task-start').value = task.fecha_inicio.substring(0, 16);
            document.getElementById('task-end').value = task.fecha_fin ? task.fecha_fin.substring(0, 16) : '';
            document.getElementById('task-assignee').value = task.asignado_a || '';
            document.getElementById('task-status').value = task.estado;
            document.getElementById('task-color').value = task.color || '#4facfe';
            document.getElementById('task-report').value = task.reporte || '';
            document.getElementById('task-issues').value = task.imprevistos || '';
            document.getElementById('task-curso').value = task.curso || 'Prekinder y Kinder 2026';
            document.getElementById('task-category-madre').value = task.categoria_madre || '';
            document.getElementById('task-subcategory').value = task.subcategoria || '';

            const meta = document.getElementById('report-meta');
            if (task.reportado_at) {
                meta.textContent = `Reportado el: ${new Date(task.reportado_at).toLocaleString()}`;
            } else {
                meta.textContent = '';
            }

            // Permissions
            const canEditFull = isMonitora;
            const canReport = isOwner || isMonitora;

            ['task-title', 'task-desc', 'task-start', 'task-end', 'task-assignee', 'task-color', 'task-status', 'task-curso', 'task-category-madre', 'task-subcategory'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.disabled = !canEditFull;
            });

            ['task-status', 'task-report', 'task-issues'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.disabled = !canReport;
            });

            document.getElementById('btn-delete-task').style.display = isMonitora ? 'inline-block' : 'none';
            document.getElementById('btn-save-task').style.display = canReport ? 'inline-block' : 'none';
            document.getElementById('btn-replace-task').style.display = isMonitora ? 'inline-block' : 'none';

        } else {
            document.getElementById('btn-replace-task').style.display = 'none';
            document.getElementById('modal-title').textContent = "Nueva Tarea";
            form.reset();
            const now = new Date();
            now.setMinutes(0);
            document.getElementById('task-start').value = now.toISOString().substring(0, 16);
            document.getElementById('btn-delete-task').style.display = 'none';
            document.getElementById('report-section').style.display = 'none';

            ['task-title', 'task-desc', 'task-start', 'task-end', 'task-assignee', 'task-color', 'task-status', 'task-category'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.disabled = false;
            });
        }
        modal.showModal();
    }

    async saveTask() {
        const id = document.getElementById('task-id').value;
        const payload = {
            titulo: document.getElementById('task-title').value,
            descripcion: document.getElementById('task-desc').value,
            fecha_inicio: document.getElementById('task-start').value,
            fecha_fin: document.getElementById('task-end').value || null,
            asignado_a: document.getElementById('task-assignee').value || null,
            estado: document.getElementById('task-status').value,
            color: document.getElementById('task-color').value,
            reporte: document.getElementById('task-report').value || null,
            imprevistos: document.getElementById('task-issues').value || null,
            curso: document.getElementById('task-curso').value || null,
            categoria_madre: document.getElementById('task-category-madre').value || null,
            subcategoria: document.getElementById('task-subcategory').value || null
        };
        try {
            const url = id ? `/api/fundacion/tareas/${id}` : '/api/fundacion/tareas';
            const res = await window.fetchApi(url, { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
            if (res.ok || res.id) {
                document.getElementById('modal-task').close();
                await this.fetchTasks();
                if (this.activeTab === 'calendario') {
                    this.render();
                    this.renderTasks();
                } else {
                    this.renderCategories();
                    this.renderPlanningView();
                }
            }
        } catch (e) {
            console.error(e);
        }
    }

    async deleteTask() {
        if (!confirm("¿Eliminar tarea?")) return;
        const id = document.getElementById('task-id').value;
        try {
            const res = await window.fetchApi(`/api/fundacion/tareas/${id}`, { method: 'DELETE' });
            if (res.ok) {
                document.getElementById('modal-task').close();
                await this.fetchTasks();
                if (this.activeTab === 'calendario') {
                    this.render();
                    this.renderTasks();
                } else {
                    this.renderCategories();
                    this.renderPlanningView();
                }
            }
        } catch (e) { console.error(e); }
    }

    openReplacementCatalog() {
        if (!this.currentEditingTask) return;

        // Cerrar modal de tarea para evitar superposición
        const taskModal = document.getElementById('modal-task');
        if (taskModal) taskModal.close();

        const catalogModal = document.getElementById('modal-catalog');
        const list = document.getElementById('catalog-list');
        list.innerHTML = '';

        // Buscar actividades únicas de la misma categoría madre
        const category = this.currentEditingTask.categoria_madre;

        const uniqueActivities = [];
        const seen = new Set();

        this.tasks.forEach(t => {
            if (t.categoria_madre === category && !seen.has(t.titulo)) {
                uniqueActivities.push(t);
                seen.add(t.titulo);
            }
        });

        if (uniqueActivities.length === 0) {
            list.innerHTML = '<p style="text-align:center; padding:20px; opacity:0.5;">No hay actividades alternativas registradas para esta categoría.</p>';
        } else {
            uniqueActivities.forEach(act => {
                if (act.titulo === this.currentEditingTask.titulo) return;
                const el = document.createElement('div');
                el.className = 'catalog-item';
                el.innerHTML = `
                    <h4>${act.titulo}</h4>
                    <p>${act.descripcion || 'Sin descripción'}</p>
                    <div style="font-size:0.7rem; margin-top:5px; opacity:0.6;">${act.subcategoria || ''}</div>
                `;
                el.onclick = () => this.replaceTask(act);
                list.appendChild(el);
            });
        }

        catalogModal.showModal();
    }

    async replaceTask(catalogAct) {
        if (!confirm(`¿Sustituir "${this.currentEditingTask.titulo}" por "${catalogAct.titulo}"?`)) return;

        try {
            await window.fetchApi(`/api/fundacion/tareas/${this.currentEditingTask.id}`, {
                method: 'PATCH',
                body: JSON.stringify({
                    titulo: catalogAct.titulo,
                    descripcion: catalogAct.descripcion,
                    color: catalogAct.color,
                    subcategoria: catalogAct.subcategoria
                })
            });

            document.getElementById('modal-catalog').close();
            document.getElementById('modal-task').close();
            window.showToast("Actividad sustituida correctamente", "success");
            await this.fetchTasks();
            this.render();
            this.renderTasks();
        } catch (err) {
            console.error(err);
            window.showToast("Error al sustituir actividad", "error");
        }
    }
}
