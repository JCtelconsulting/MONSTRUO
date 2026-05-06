// GTA API v2
window.GtaApi = (() => {
    const base = '/api/gta';
    const h = { 'Content-Type': 'application/json' };

    const get  = (path)       => window.fetchApi(`${base}${path}`);
    const post = (path, body) => window.fetchApi(`${base}${path}`, { method: 'POST',  headers: h, body: JSON.stringify(body) });
    const put  = (path, body) => window.fetchApi(`${base}${path}`, { method: 'PUT',   headers: h, body: JSON.stringify(body) });
    const patch= (path, body) => window.fetchApi(`${base}${path}`, { method: 'PATCH', headers: h, body: JSON.stringify(body) });
    const del  = (path)       => window.fetchApi(`${base}${path}`, { method: 'DELETE' });

    return {
        // Solicitudes
        getSolicitudes:  (params = '')     => get(`/solicitudes${params}`),
        getSolicitud:    (id)              => get(`/solicitudes/${id}`),
        crearSolicitud:  (data)            => post('/solicitudes', data),
        updateSolicitud: (id, data)        => patch(`/solicitudes/${id}`, data),
        completarPaso:   (id, paso_idx)    => post(`/solicitudes/${id}/pasos/${paso_idx}/completar`, {}),
        bloquearPaso:    (id, paso_idx, motivo) => post(`/solicitudes/${id}/pasos/${paso_idx}/bloquear`, { motivo }),
        addComentario:   (id, texto)       => post(`/solicitudes/${id}/comentarios`, { texto }),
        getComentarios:  (id)              => get(`/solicitudes/${id}/comentarios`),

        // Procesos (biblioteca unificada)
        getProcesos:           (params = '')   => get(`/procesos${params}`),
        getProceso:            (id)            => get(`/procesos/${id}`),
        crearProceso:          (data)          => post('/procesos', data),
        actualizarProceso:     (id, data)      => put(`/procesos/${id}`, data),
        agregarComentarioProc: (id, data)      => post(`/procesos/${id}/comentarios`, data),
        reportarQuiebreProc:   (id, data)      => post(`/procesos/${id}/quiebres`, data),
        seedProcesos:          ()              => post('/procesos/seed-from-files', {}),

        // Quiebres legacy
        resolverQuiebre: (id, nota)        => post(`/quiebres/${id}/resolver`, { nota }),

        // Stats
        getStats:        ()                => get('/stats'),

        // Catálogo de documentos descargados desde Drive (gta/data/procesos)
        getDocumentos:        ()           => get('/catalogo'),
        urlDocumento:         (path)       => `${base}/catalogo/download?path=${encodeURIComponent(path)}`,

        // Flujos cross-área
        listarFlujos:         (params = '')   => get(`/flujos${params}`),
        getFlujo:             (id)            => get(`/flujos/${id}`),
        getEventosFlujo:      (id)            => get(`/flujos/${id}/eventos`),
        crearFlujo:           (data)          => post('/flujos', data),
        completarTarea:       (id, data)      => post(`/flujo-tareas/${id}/completar`, data || {}),
        validarTarea:         (id, data)      => post(`/flujo-tareas/${id}/validar`, data),
        pedirAyuda:           (id, data)      => post(`/flujo-tareas/${id}/ayuda`, data),
        responderAyuda:       (id, data)      => post(`/flujo-ayudas/${id}/responder`, data),
        getMetricas:          ()              => get('/metricas'),

        // Tareas (modelo área-céntrico)
        getBandeja:           (subId)          => get(`/tareas/bandeja${subId ? `?subarea_id=${subId}` : ''}`),
        getMisTareas:         (incluirCerradas=false) => get(`/tareas/mias?incluir_cerradas=${incluirCerradas}`),
        getDondeColaboro:     (incluirCerradas=false) => get(`/tareas/colaboro?incluir_cerradas=${incluirCerradas}`),
        getTareasSubarea:     (subId)          => get(`/tareas/subarea/${subId}`),
        getTareaArea:         (id)             => get(`/tareas/${id}`),
        crearTareaArea:       (data)           => post('/tareas', data),
        tomarTareaArea:       (id)             => post(`/tareas/${id}/tomar`, {}),
        liberarTareaArea:     (id, motivo)     => post(`/tareas/${id}/liberar`, { motivo: motivo || null }),
        reasignarTareaArea:   (id, data)       => post(`/tareas/${id}/reasignar`, data),
        agregarColaborador:   (id, data)       => post(`/tareas/${id}/colaboradores`, data),
        quitarColaborador:    (id, data)       => window.fetchApi(`${base}/tareas/${id}/colaboradores`, { method: 'DELETE', headers: h, body: JSON.stringify(data) }),
        cerrarTareaArea:      (id, reporte)    => post(`/tareas/${id}/cerrar`, { reporte: reporte || null }),

        // Membresías
        getMembresiasSubarea: (subId, hist=false) => get(`/membresias/subarea/${subId}?incluir_historico=${hist}`),
        getMisMembresias:     (hist=false)        => get(`/membresias/mias?incluir_historico=${hist}`),
        asignarMembresia:     (data)              => post('/membresias', data),
        cerrarMembresia:      (id, motivo)        => window.fetchApi(`${base}/membresias/${id}`, { method: 'DELETE', headers: h, body: JSON.stringify({ motivo: motivo || null }) }),
    };
})();
