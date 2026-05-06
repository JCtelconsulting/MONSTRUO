// Fundación — wrapper de API
window.FundApi = (() => {
    const base = '/api/fundacion';
    const h = { 'Content-Type': 'application/json' };
    const get = (p) => window.fetchApi(`${base}${p}`);
    const post = (p, b) => window.fetchApi(`${base}${p}`, { method: 'POST',  headers: h, body: JSON.stringify(b) });
    const patch = (p, b) => window.fetchApi(`${base}${p}`, { method: 'PATCH', headers: h, body: JSON.stringify(b) });
    const del = (p) => window.fetchApi(`${base}${p}`, { method: 'DELETE' });

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

        // Usuarios (admin de Fundación) — sigue en /api/admin/users con filtro
        getUsuarios:          ()                  => window.fetchApi('/api/admin/users?organizacion=fundacion'),
        crearUsuario:         (data)              => window.fetchApi('/api/admin/users', { method:'POST', headers:h, body: JSON.stringify(data) }),
        actualizarUsuario:    (username, data)    => window.fetchApi(`/api/admin/users/${encodeURIComponent(username)}`, { method:'PATCH', headers:h, body: JSON.stringify(data) }),
        eliminarUsuario:      (username)          => window.fetchApi(`/api/admin/users/${encodeURIComponent(username)}`, { method:'DELETE' }),
    };
})();
