/**
 * Utilidades compartidas para Monstruo UI
 * Mapeo de estados y funciones auxiliares
 */

// ================================================================================
// MAPEO DE ESTADOS (DB → UI)
// ================================================================================

/**
 * Mapeo de estados internos (inglés en DB) a español (UI)
 */
const MAPEO_ESTADOS = {
    // Estados de tareas/casos
    "open": "Abierto",
    "doing": "En Proceso",
    "in_progress": "En Proceso",
    "blocked": "Bloqueado",
    "done": "Listo",
    "closed": "Cerrado",

    // Estados de aprobación
    "pending": "Pendiente",
    "approved": "Aprobado",
    "rejected": "Rechazado",

    // Estados de conexión
    "connected": "Conectado",
    "disconnected": "Desconectado",
    "degraded": "Degradado",

    // Estados genéricos
    "error": "Error",
    "failed": "Fallido",
    "success": "Éxito",
    "active": "Activo",
    "inactive": "Inactivo"
};

/**
 * Mapeo de prioridades
 */
const MAPEO_PRIORIDADES = {
    "low": "Baja",
    "medium": "Media",
    "high": "Alta",
    "critical": "Crítica"
};

/**
 * Mapeo de severidades
 */
const MAPEO_SEVERIDADES = {
    "info": "Información",
    "warning": "Advertencia",
    "error": "Error",
    "critical": "Crítico"
};

// ================================================================================
// FUNCIONES AUXILIARES
// ================================================================================

/**
 * Traduce un estado de inglés a español
 * @param {string} estado - Estado en inglés
 * @returns {string} - Estado en español (o original si no encuentra traducción)
 */
function traducirEstado(estado) {
    if (!estado) return "";
    const estadoLower = estado.toLowerCase();
    return MAPEO_ESTADOS[estadoLower] || estado;
}

/**
 * Traduce una prioridad
 */
function traducirPrioridad(prioridad) {
    if (!prioridad) return "";
    const prioridadLower = prioridad.toLowerCase();
    return MAPEO_PRIORIDADES[prioridadLower] || prioridad;
}

/**
 * Traduce una severidad
 */
function traducirSeveridad(severidad) {
    if (!severidad) return "";
    const severidadLower = severidad.toLowerCase();
    return MAPEO_SEVERIDADES[severidadLower] || severidad;
}

/**
 * Crea un pill de estado con la clase CSS correcta
 * @param {string} estado - Estado (en inglés o español)
 * @returns {string} - HTML del pill
 */
function crearPillEstado(estado) {
    if (!estado) return "";
    const estadoLower = estado.toLowerCase();
    const estadoTraducido = traducirEstado(estadoLower);
    return `<span class="pill status-${estadoLower}">${escaparHTML(estadoTraducido)}</span>`;
}

/**
 * Escapa HTML para prevenir XSS
 */
function escaparHTML(str) {
    if (!str) return "";
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Formatea fecha ISO a formato legible
 * @param {string} isoDate - Fecha en formato ISO
 * @returns {string} - Fecha formateada
 */
function formatearFecha(isoDate) {
    if (!isoDate) return "";
    try {
        const fecha = new Date(isoDate);
        return fecha.toLocaleString('es-CL', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return isoDate;
    }
}

/**
 * Hace una llamada a la API con autenticación
 * @param {string} path - Path del endpoint
 * @param {object} options - Opciones fetch
 * @returns {Promise<{status: number, json: any, text: string}>}
 */
async function llamarAPI(path, options = {}) {
    const token = localStorage.getItem("monstruo_token") || localStorage.getItem("token") || "";
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";
    if (token) {
        headers["Authorization"] = "Bearer " + token;
    }

    const res = await fetch(path, { ...options, headers });
    let texto = await res.text();
    let json = null;
    try {
        json = JSON.parse(texto);
    } catch (e) {
        // No es JSON
    }

    return {
        status: res.status,
        json: json,
        text: texto
    };
}

// ================================================================================
// EXPORTAR (si se usa como módulo)
// ================================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        MAPEO_ESTADOS,
        MAP EO_PRIORIDADES,
        MAPEO_SEVERIDADES,
        traducirEstado,
        traducirPrioridad,
        traducirSeveridad,
        crearPillEstado,
        escaparHTML,
        formatearFecha,
        llamarAPI
    };
}
