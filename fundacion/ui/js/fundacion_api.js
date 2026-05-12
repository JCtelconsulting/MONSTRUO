// Fundación — wrapper de API
window.FundApi = (() => {
    const base = '/api/fundacion';
    const h = { 'Content-Type': 'application/json' };
    const get = (p) => window.fetchApi(`${base}${p}`);
    const post = (p, b) => window.fetchApi(`${base}${p}`, { method: 'POST',  headers: h, body: JSON.stringify(b) });
    const patch = (p, b) => window.fetchApi(`${base}${p}`, { method: 'PATCH', headers: h, body: JSON.stringify(b) });
    const del = (p) => window.fetchApi(`${base}${p}`, { method: 'DELETE' });

    const _repQS = (path, sedeId, desde, hasta) => {
        const qs = new URLSearchParams();
        if (sedeId != null) qs.set('sede_id', sedeId);
        if (desde) qs.set('desde', desde);
        if (hasta) qs.set('hasta', hasta);
        const q = qs.toString();
        return get(`${path}${q ? `?${q}` : ''}`);
    };

    return {
        // Sedes accesibles según scope
        getSedesAccesibles:   ()                  => get('/sedes'),
        getTodasSedes:        (incluirInactivas=false) => get(`/sedes/all?incluir_inactivas=${incluirInactivas}`),
        crearSede:            (data)              => post('/sedes', data),
        actualizarSede:       (id, data)          => patch(`/sedes/${id}`, data),

        // Membresías por sede
        getMembresias:        (sedeId)            => get(sedeId ? `/membresias?sede_id=${sedeId}` : '/membresias'),
        getMisMembresias:     ()                  => get('/membresias/mias'),
        crearMembresia:       (data)              => post('/membresias', data),
        cerrarMembresia:      (id, motivo)        => del(`/membresias/${id}${motivo ? `?motivo=${encodeURIComponent(motivo)}` : ''}`),

        // Tareas (sistema viejo, compat)
        listarTareas:         (start, end)        => get(`/tareas${start ? `?start=${start}` : ''}${end ? `${start ? '&' : '?'}end=${end}` : ''}`),
        crearTarea:           (data)              => post('/tareas', data),
        actualizarTarea:      (id, data)          => patch(`/tareas/${id}`, data),
        eliminarTarea:        (id)                => del(`/tareas/${id}`),

        // Sync de planillas Google Sheets (timeout largo: 7 planillas)
        syncSheets:           (sedeCode)          => window.fetchApi(`${base}/sync/sheets${sedeCode ? `?sede_code=${encodeURIComponent(sedeCode)}` : ''}`, {
            method: 'POST', headers: h, body: JSON.stringify({}), timeoutMs: 180000,
        }),
        getSyncLogs:          (limit=20)          => get(`/sync/logs?limit=${limit}`),

        // Catálogos pedagógicos
        getCatNiveles:        ()                  => get('/catalogos/niveles'),
        getCatDominios:       ()                  => get('/catalogos/dominios'),
        getCatCompetencias:   ()                  => get('/catalogos/competencias'),
        getCatBloqueTipos:    ()                  => get('/catalogos/bloque-tipos'),
        getCatClima:          ()                  => get('/catalogos/clima'),
        getCatActividades:    (opts={}) => {
            const qs = new URLSearchParams();
            if (opts.q) qs.set('q', opts.q);
            if (opts.bloqueTipoId != null) qs.set('bloque_tipo_id', opts.bloqueTipoId);
            if (opts.bloqueSubtipoId != null) qs.set('bloque_subtipo_id', opts.bloqueSubtipoId);
            if (opts.limit) qs.set('limit', opts.limit);
            const q = qs.toString();
            return get(`/catalogos/actividades${q ? `?${q}` : ''}`);
        },
        getPlanificacionOficial: (nivelId, fecha) => get(`/planificacion-oficial?nivel_id=${nivelId}&fecha=${fecha}`),

        // Sesiones pedagógicas
        listSesiones:         (sedeId, nivelId, desde, hasta) => {
            const qs = new URLSearchParams({ sede_id: sedeId });
            if (nivelId != null) qs.set('nivel_id', nivelId);
            if (desde) qs.set('desde', desde);
            if (hasta) qs.set('hasta', hasta);
            return get(`/sesiones?${qs}`);
        },
        getSesionByFecha:     (sedeId, fecha, nivelId) => get(`/sesiones/by-fecha?sede_id=${sedeId}&fecha=${fecha}&nivel_id=${nivelId}`),
        getSesion:            (id)                => get(`/sesiones/${id}`),
        upsertSesion:         (data)              => window.fetchApi(`${base}/sesiones`, {
            method: 'PUT', headers: h, body: JSON.stringify(data), timeoutMs: 30000,
        }),
        deleteSesion:         (id)                => del(`/sesiones/${id}`),

        // Reportes pedagógicos (a-f)
        repCobertura:         (sedeId, desde, hasta) => _repQS('/reportes/cobertura-bloques', sedeId, desde, hasta),
        repCompetencias:      (sedeId, desde, hasta) => _repQS('/reportes/competencias-trabajadas', sedeId, desde, hasta),
        repMateriales:        (sedeId, desde, hasta) => _repQS('/reportes/materiales-uso', sedeId, desde, hasta),
        repAdaptaciones:      (sedeId, desde, hasta) => _repQS('/reportes/adaptaciones', sedeId, desde, hasta),
        repClima:             (sedeId, desde, hasta) => _repQS('/reportes/clima', sedeId, desde, hasta),
        repActividadPeriodo:  (sedeId, desde, hasta) => _repQS('/reportes/actividad-periodo', sedeId, desde, hasta),

        // Reportes (vistas SQL)
        getDashboard:         ()                  => get('/reportes/dashboard'),
        getReporteAlumnos:    (filtros={})        => {
            const qs = new URLSearchParams();
            if (filtros.sede_id != null) qs.set('sede_id', filtros.sede_id);
            if (filtros.matricula_activa != null) qs.set('matricula_activa', filtros.matricula_activa);
            if (filtros.nivel_riesgo) qs.set('nivel_riesgo', filtros.nivel_riesgo);
            const q = qs.toString();
            return get(`/reportes/alumnos${q ? `?${q}` : ''}`);
        },
        getAsistenciaMensual: (sedeId)            => get(`/reportes/asistencia-mensual${sedeId ? `?sede_id=${sedeId}` : ''}`),
        getAsistenciaMatriz:  (sedeId, desde, hasta) => {
            const qs = new URLSearchParams({ sede_id: sedeId });
            if (desde) qs.set('desde', desde);
            if (hasta) qs.set('hasta', hasta);
            return get(`/reportes/asistencia-matriz?${qs}`);
        },

        // Usuarios (admin de Fundación) — sigue en /api/admin/users con filtro
        getUsuarios:          ()                  => window.fetchApi('/api/admin/users?organizacion=fundacion'),
        crearUsuario:         (data)              => window.fetchApi('/api/admin/users', { method:'POST', headers:h, body: JSON.stringify(data) }),
        actualizarUsuario:    (username, data)    => window.fetchApi(`/api/admin/users/${encodeURIComponent(username)}`, { method:'PATCH', headers:h, body: JSON.stringify(data) }),
        eliminarUsuario:      (username)          => window.fetchApi(`/api/admin/users/${encodeURIComponent(username)}`, { method:'DELETE' }),
    };
})();
