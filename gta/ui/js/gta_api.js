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

        // Catálogo de procesos
        getProcesos:     (params = '')     => get(`/procesos${params}`),
        getProceso:      (id)              => get(`/procesos/${id}`),
        crearProceso:    (data)            => post('/procesos', data),
        updateProceso:   (id, data)        => put(`/procesos/${id}`, data),
        deleteProceso:   (id)              => del(`/procesos/${id}`),

        // Quiebres
        getQuiebres:     (params = '')     => get(`/quiebres${params}`),
        crearQuiebre:    (data)            => post('/quiebres', data),
        resolverQuiebre: (id, nota)        => post(`/quiebres/${id}/resolver`, { nota }),

        // Stats
        getStats:        ()                => get('/stats'),

        // Catálogo de documentos descargados desde Drive (gta/data/procesos)
        getDocumentos:        ()           => get('/catalogo'),
        urlDocumento:         (path)       => `${base}/catalogo/download?path=${encodeURIComponent(path)}`,
    };
})();
