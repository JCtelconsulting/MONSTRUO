/**
 * Ticketera V3 — Capa API
 * Todas las llamadas al backend centralizadas aquí.
 */
const TksApi = (() => {
    // Detectar si estamos en /dev (Reverse Proxy)
    const BASE = window.getApiBase ? window.getApiBase() + '/tks' : '/api/tks';

    async function _fetch(url, opts = {}) {
        return window.fetchApi(url, opts);
    }

    return {
        // --- Tickets ---
        listTickets: (params = {}, requestOpts = null) => {
            const qs = new URLSearchParams();
            if (params.status) qs.set('status', params.status);
            if (params.q) qs.set('q', params.q);
            if (params.categoria) qs.set('categoria', params.categoria);
            if (params.asignado_a) qs.set('asignado_a', params.asignado_a);
            if (params.severidad) qs.set('severidad', params.severidad);
            if (params.limit) qs.set('limit', params.limit);
            if (params.offset) qs.set('offset', params.offset);
            const query = qs.toString();
            return _fetch(`${BASE}/tickets${query ? '?' + query : ''}`, requestOpts || {});
        },

        getTicket: (id, requestOpts = null) => _fetch(`${BASE}/tickets/${id}`, requestOpts || {}),

        createTicket: (body) => _fetch(`${BASE}/tickets`, { method: 'POST', body }),

        updateTicket: (id, body) => _fetch(`${BASE}/tickets/${id}`, { method: 'PATCH', body }),

        // --- Eventos/Timeline ---
        getEventos: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/eventos`, requestOpts || {}),

        addEvento: (ticketId, body) =>
            _fetch(`${BASE}/tickets/${ticketId}/eventos`, { method: 'POST', body }),

        getTicketEmails: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/emails`, requestOpts || {}),

        replyByEmail: (ticketId, body, requestOpts = null) => {
            // Si body es FormData, no stringify y dejar que fetch ponga headers (multipart).
            // _fetch/window.fetchApi wrapper podría forzar JSON si no tenemos cuidado.
            // Asumimos window.fetchApi maneja esto si detecta FormData o si content-type es undefined.
            // Si fetchApi fuerza JSON, habrá que usar fetch directo o modificar fetchApi.
            // Por ahora asumimos que si pasamos opts con body objeto, fetchApi lo serializa, 
            // pero si es FormData deberíamos pasarlo tal cual.
            return _fetch(
                `${BASE}/tickets/${ticketId}/reply-email`,
                requestOpts ? { method: 'POST', body, ...requestOpts } : { method: 'POST', body }
            );
        },

        // --- Kanban ---
        getTablero: (requestOpts = null) => _fetch(`${BASE}/tablero`, requestOpts || {}),

        // --- Stats ---
        getStats: (requestOpts = null) => _fetch(`${BASE}/stats`, requestOpts || {}),

        // --- Notificaciones ---
        getNotificaciones: (requestOpts = null) => _fetch(`${BASE}/notificaciones`, requestOpts || {}),

        // --- Especialidades ---
        listEspecialidades: () => _fetch(`${BASE}/especialidades`),
        upsertEspecialidad: (body) => _fetch(`${BASE}/especialidades`, { method: 'POST', body }),
        toggleDisponibilidad: (username, available) =>
            _fetch(`${BASE}/especialidades/${username}/disponibilidad?available=${available}`, { method: 'PATCH' }),

        // --- Mis Tickets ---
        getMisTickets: () => _fetch(`${BASE}/mis-tickets`),
    };
})();
