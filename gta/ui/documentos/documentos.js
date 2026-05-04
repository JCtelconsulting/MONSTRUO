// Documentos — navegador de procesos descargados desde Drive
window.Documentos = (() => {
    let _data = null;
    let _areaFiltro = '';
    let _texto = '';

    // Etiquetas legibles por área (alineadas con seed de gta.areas)
    const AREA_LABELS = {
        comercial: 'Comercial',
        preventa: 'Preventa',
        redes: 'Redes',
        sistemas: 'Sistemas',
        proveedores: 'Proveedores',
        finanzas: 'Finanzas',
        bodega: 'Bodega',
        capital_humano: 'Capital Humano',
        pmo: 'PMO',
        prevencion_riesgos: 'Prev. Riesgos',
        contabilidad: 'Contabilidad',
        ia: 'IA',
    };

    const SUB_LABELS = {
        ventas: 'Ventas',
        postventa: 'Postventa',
        infraestructura: 'Infraestructura',
        acceso: 'Acceso',
        mesa_ayuda: 'Mesa de Ayuda',
        soporte: 'Soporte',
        ciberseguridad: 'Ciberseguridad',
        compras: 'Compras',
        facturacion: 'Facturación',
        cobranzas: 'Cobranzas',
        contratacion: 'Contratación',
        desvinculacion: 'Desvinculación',
        proyectos: 'Proyectos',
        instalaciones: 'Instalaciones',
        gestion_documental: 'G. Documental',
        editables: 'Editables',
    };

    function init() { cargar(); }

    async function cargar() {
        const cont = document.getElementById('docs-content');
        if (!cont) return;
        cont.innerHTML = `<div class="gta-loading"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>`;
        try {
            const data = await GtaApi.getDocumentos();
            _data = data;
            _renderPills();
            _render();
            _updateCounter();
        } catch (e) {
            cont.innerHTML = GtaUi.empty('Error al cargar documentos: ' + (e.message || e));
        }
    }

    function _renderPills() {
        const pills = document.getElementById('docs-area-pills');
        if (!pills || !_data) return;
        const areasConDocs = (_data.areas || []).map(a => a.code);
        const html = ['<button class="gta-area-pill active" data-area="" onclick="Documentos.filtrarArea(this)">Todas</button>'];
        areasConDocs.forEach(code => {
            const label = AREA_LABELS[code] || code;
            const count = (_data.areas.find(a => a.code === code) || {}).count || 0;
            html.push(`<button class="gta-area-pill" data-area="${code}" onclick="Documentos.filtrarArea(this)">${label} <span class="gta-pill-count">${count}</span></button>`);
        });
        pills.innerHTML = html.join('');
    }

    function filtrar(texto) {
        _texto = (texto || '').toLowerCase().trim();
        _render();
    }

    function filtrarArea(btn) {
        document.querySelectorAll('#docs-area-pills .gta-area-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _areaFiltro = btn.dataset.area || '';
        _render();
    }

    function _matches(file) {
        if (!_texto) return true;
        return file.filename.toLowerCase().includes(_texto) || file.path.toLowerCase().includes(_texto);
    }

    function _esc(s) {
        return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function _fileRow(file) {
        const downloadUrl = GtaApi.urlDocumento(file.path);
        const date = file.modified_at ? new Date(file.modified_at).toLocaleDateString('es-CL') : '';
        return `
            <div class="gta-doc-row">
                <div class="gta-doc-icon"><i class="fas ${_esc(file.icon)}"></i></div>
                <div class="gta-doc-info">
                    <div class="gta-doc-name">${_esc(file.name)}</div>
                    <div class="gta-doc-meta">
                        <span class="gta-doc-ext">${_esc(file.ext.toUpperCase())}</span>
                        <span>${_esc(file.size_label)}</span>
                        ${date ? `<span>· ${date}</span>` : ''}
                    </div>
                </div>
                <a class="btn-sm gta-doc-download" href="${downloadUrl}" download="${_esc(file.filename)}" title="Descargar">
                    <i class="fas fa-download"></i>
                </a>
            </div>
        `;
    }

    function _renderArea(area) {
        const visibleFiles = (area.files || []).filter(_matches);
        const subBlocks = (area.subareas || []).map(sub => {
            const visible = (sub.files || []).filter(_matches);
            if (!visible.length) return '';
            const subLabel = SUB_LABELS[sub.code] || sub.code;
            return `
                <div class="gta-doc-subgroup">
                    <h5 class="gta-doc-subgroup-title"><i class="fas fa-folder"></i> ${_esc(subLabel)} <span class="gta-pill-count">${visible.length}</span></h5>
                    <div class="gta-doc-list">${visible.map(_fileRow).join('')}</div>
                </div>
            `;
        }).filter(Boolean).join('');

        if (!visibleFiles.length && !subBlocks) return '';

        const areaLabel = AREA_LABELS[area.code] || area.code;
        const directList = visibleFiles.length
            ? `<div class="gta-doc-list">${visibleFiles.map(_fileRow).join('')}</div>`
            : '';

        return `
            <div class="gta-doc-area">
                <h4 class="gta-doc-area-title">
                    <i class="fas fa-layer-group"></i> ${_esc(areaLabel)}
                </h4>
                ${directList}
                ${subBlocks}
            </div>
        `;
    }

    function _render() {
        const cont = document.getElementById('docs-content');
        if (!cont || !_data) return;

        const areas = (_data.areas || []).filter(a => !_areaFiltro || a.code === _areaFiltro);
        const blocks = areas.map(_renderArea).filter(Boolean);

        // Sueltos solo si no hay filtro de área
        if (!_areaFiltro) {
            const sueltos = (_data.sueltos || []).filter(_matches);
            if (sueltos.length) {
                blocks.push(`
                    <div class="gta-doc-area">
                        <h4 class="gta-doc-area-title"><i class="fas fa-question-circle"></i> Sin clasificar</h4>
                        <div class="gta-doc-list">${sueltos.map(_fileRow).join('')}</div>
                    </div>
                `);
            }
        }

        if (!blocks.length) {
            cont.innerHTML = GtaUi.empty(_texto ? `Sin resultados para "${_esc(_texto)}"` : 'No hay documentos.');
            return;
        }

        cont.innerHTML = blocks.join('');
        _updateCounter();
    }

    function _updateCounter() {
        const el = document.getElementById('docs-counter');
        if (!el || !_data) return;
        let total = 0;
        (_data.areas || []).forEach(a => {
            if (_areaFiltro && a.code !== _areaFiltro) return;
            total += (a.files || []).filter(_matches).length;
            (a.subareas || []).forEach(s => total += (s.files || []).filter(_matches).length);
        });
        if (!_areaFiltro) total += (_data.sueltos || []).filter(_matches).length;
        el.textContent = `${total} archivo${total === 1 ? '' : 's'}`;
    }

    return { init, cargar, filtrar, filtrarArea };
})();
