/**
 * Ticketera V3 — Capa API
 * Todas las llamadas al backend centralizadas aquí.
 */
const TksApi = (() => {
    // Detectar si estamos en /dev (Reverse Proxy)
    const API_BASE = window.getApiBase ? window.getApiBase() : '/api';
    const BASE = `${API_BASE}/tks`;

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

        claimTicket: (id) => _fetch(`${BASE}/tickets/${id}/claim`, { method: 'POST' }),

        trashTicket: (id, body = {}) => _fetch(`${BASE}/tickets/${id}/trash`, { method: 'POST', body }),

        restoreTicket: (id) => _fetch(`${BASE}/tickets/${id}/restore`, { method: 'POST' }),

        // --- Eventos/Timeline ---
        getEventos: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/eventos`, requestOpts || {}),

        addEvento: (ticketId, body) =>
            _fetch(`${BASE}/tickets/${ticketId}/eventos`, { method: 'POST', body }),

        getTicketEmails: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/emails`, requestOpts || {}),
        getTicketWorkflow: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/workflow`, requestOpts || {}),
        transitionTicket: (ticketId, body, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/transitions`,
                requestOpts ? { method: 'POST', body, ...requestOpts } : { method: 'POST', body }
            ),
        getTicketApprovals: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/approvals`, requestOpts || {}),
        gerenciaDecision: (ticketId, body) => _fetch(`${BASE}/tickets/${ticketId}/gerencia-decision`, { method: 'POST', body }),
        getTicketAttachments: (ticketId, requestOpts = null) => _fetch(`${BASE}/tickets/${ticketId}/attachments`, requestOpts || {}),
        getTicketAttachmentDownloadUrl: (ticketId, attachmentId) => `${BASE}/tickets/${ticketId}/attachments/${attachmentId}/download`,
        getTicketAttachmentInlineUrl: (ticketId, attachmentId) => `${BASE}/tickets/${ticketId}/attachments/${attachmentId}/download?inline=1`,

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

        // --- Borradores de respuesta por correo ---
        getEmailDraft: (ticketId, requestOpts = null) =>
            _fetch(`${BASE}/tickets/${ticketId}/email-draft`, requestOpts || {}),
        lockEmailDraft: (ticketId, force = false, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft/lock`,
                requestOpts ? { method: 'POST', body: { force: !!force }, ...requestOpts } : { method: 'POST', body: { force: !!force } }
            ),
        heartbeatEmailDraftLock: (ticketId, lockToken, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft/lock/heartbeat`,
                requestOpts ? { method: 'POST', body: { lock_token: lockToken }, ...requestOpts } : { method: 'POST', body: { lock_token: lockToken } }
            ),
        saveEmailDraft: (ticketId, body, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft`,
                requestOpts ? { method: 'PUT', body, ...requestOpts } : { method: 'PUT', body }
            ),
        uploadEmailDraftAttachments: (ticketId, formData, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft/attachments`,
                requestOpts ? { method: 'POST', body: formData, ...requestOpts } : { method: 'POST', body: formData }
            ),
        deleteEmailDraftAttachment: (ticketId, attachmentId, lockToken, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft/attachments/${attachmentId}`,
                requestOpts ? { method: 'DELETE', body: { lock_token: lockToken }, ...requestOpts } : { method: 'DELETE', body: { lock_token: lockToken } }
            ),
        sendEmailDraft: (ticketId, body, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft/send`,
                requestOpts ? { method: 'POST', body, ...requestOpts } : { method: 'POST', body }
            ),
        discardEmailDraft: (ticketId, lockToken, requestOpts = null) =>
            _fetch(
                `${BASE}/tickets/${ticketId}/email-draft/discard`,
                requestOpts ? { method: 'POST', body: { lock_token: lockToken }, ...requestOpts } : { method: 'POST', body: { lock_token: lockToken } }
            ),

        // --- Kanban ---
        getTablero: (requestOpts = null) => _fetch(`${BASE}/tablero`, requestOpts || {}),

        // --- Stats ---
        getStats: (requestOpts = null) => _fetch(`${BASE}/stats`, requestOpts || {}),
        getAtendidosReport: (params = {}) => {
            const qs = new URLSearchParams();
            if (params.period) qs.set('period', params.period);
            if (params.customer_id) qs.set('customer_id', params.customer_id);
            if (params.resolved_after) qs.set('resolved_after', params.resolved_after);
            if (params.resolved_before) qs.set('resolved_before', params.resolved_before);
            const query = qs.toString();
            return _fetch(`${BASE}/reports/atendidos${query ? '?' + query : ''}`);
        },
        getClientesResumen: (requestOpts = null) => _fetch(`${BASE}/reports/clientes`, requestOpts || {}),
        getSlaMetrics: (params = {}, requestOpts = null) => {
            const qs = new URLSearchParams();
            if (params.date_from) qs.set('date_from', params.date_from);
            if (params.date_to) qs.set('date_to', params.date_to);
            if (params.severity) qs.set('severity', params.severity);
            if (params.assignee) qs.set('assignee', params.assignee);
            const query = qs.toString();
            return _fetch(`${BASE}/sla/metrics${query ? '?' + query : ''}`, requestOpts || {});
        },
        getAssignmentTimeline: (params = {}, requestOpts = null) => {
            const qs = new URLSearchParams();
            if (params.window_h) qs.set('window_h', params.window_h);
            if (params.limit) qs.set('limit', params.limit);
            const query = qs.toString();
            return _fetch(`${BASE}/asignacion/timeline${query ? '?' + query : ''}`, requestOpts || {});
        },

        // --- Notificaciones ---
        getNotificaciones: (requestOpts = null) => _fetch(`${BASE}/notificaciones`, requestOpts || {}),

        // --- Especialidades ---
        listEspecialidades: () => _fetch(`${BASE}/especialidades`),
        upsertEspecialidad: (body) => _fetch(`${BASE}/especialidades`, { method: 'POST', body }),
        toggleDisponibilidad: (username, available) =>
            _fetch(`${BASE}/especialidades/${username}/disponibilidad?available=${available}`, { method: 'PATCH' }),

        // --- Mis Tickets ---
        getMisTickets: () => _fetch(`${BASE}/mis-tickets`),

        // --- Ajustes Ticketera ---
        getDomainTemplateSettings: (requestOpts = null) =>
            _fetch(`${BASE}/settings/domain-templates`, requestOpts || {}),
        getMessageTemplates: (requestOpts = null) =>
            _fetch(`${BASE}/settings/message-templates`, requestOpts || {}),
        getMailTemplate: (templateKey, requestOpts = null) =>
            _fetch(`${BASE}/settings/mail-templates/${encodeURIComponent(templateKey)}`, requestOpts || {}),
        updateMessageTemplates: (body, requestOpts = null) =>
            _fetch(
                `${BASE}/settings/message-templates`,
                requestOpts ? { method: 'PUT', body, ...requestOpts } : { method: 'PUT', body }
            ),
        updateMailTemplate: (templateKey, body, requestOpts = null) =>
            _fetch(
                `${BASE}/settings/mail-templates/${encodeURIComponent(templateKey)}`,
                requestOpts ? { method: 'PUT', body, ...requestOpts } : { method: 'PUT', body }
            ),
        upsertRoutingRule: (body, requestOpts = null) =>
            _fetch(
                `${BASE}/settings/routing-rules`,
                requestOpts ? { method: 'POST', body, ...requestOpts } : { method: 'POST', body }
            ),
        deleteRoutingRule: (ruleId, requestOpts = null) =>
            _fetch(
                `${BASE}/settings/routing-rules/${ruleId}`,
                requestOpts ? { method: 'DELETE', ...requestOpts } : { method: 'DELETE' }
            ),

        // --- Operación / Cola / Canales ---
        getQueueHealth: (requestOpts = null) => _fetch(`${BASE}/ops/queue-health`, requestOpts || {}),
        getChannelsStatus: (requestOpts = null) => _fetch(`${BASE}/channels/status`, requestOpts || {}),
        listChannelNotifications: (params = {}, requestOpts = null) => {
            const qs = new URLSearchParams();
            if (params.status) qs.set('status', params.status);
            if (params.channel) qs.set('channel', params.channel);
            if (params.limit) qs.set('limit', params.limit);
            if (params.offset) qs.set('offset', params.offset);
            const query = qs.toString();
            return _fetch(`${BASE}/channels/notifications${query ? '?' + query : ''}`, requestOpts || {});
        },
        retryChannelNotification: (notificationId, requestOpts = null) =>
            _fetch(`${BASE}/channels/notifications/${notificationId}/retry`, requestOpts ? { method: 'POST', ...requestOpts } : { method: 'POST' }),
        recoverStaleJobs: (staleMinutes = 20, requestOpts = null) =>
            _fetch(
                `${API_BASE}/jobs/recover-stale?stale_minutes=${encodeURIComponent(staleMinutes)}`,
                requestOpts ? { method: 'POST', ...requestOpts } : { method: 'POST' }
            ),

        // --- Compliance ---
        listComplianceExportRuns: (requestOpts = null) => _fetch(`${BASE}/compliance/exports/runs?limit=20`, requestOpts || {}),
        listCompliancePurgeRuns: (requestOpts = null) => _fetch(`${BASE}/compliance/purge/runs?limit=20`, requestOpts || {}),
    };
})();
