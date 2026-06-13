export async function fetchApi(url, options = {}) {
  if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/api')) {
    url = '/api' + url;
  }
  // Prefijo de entorno (/dev): sin esto, estando en /dev las llamadas pegaban
  // a PROD y la app rebotaba al login.
  if (
    typeof url === 'string' &&
    url.startsWith('/api') &&
    window.location.pathname.startsWith('/dev')
  ) {
    url = '/dev' + url;
  }
  options.credentials = 'include';
  options.headers = options.headers || {};
  if (options.body && typeof options.body !== 'string' && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }
  const resp = await fetch(url, options);
  // Solo 401 (no autenticado) desloguea; 403 (sin permiso) NO debe rebotar
  // al login: cae al manejo de error normal para que la seccion lo muestre.
  if (resp.status === 401) {
    if (window.handleAuthExpired) window.handleAuthExpired();
    throw new Error('Sesion expirada');
  }
  if (!resp.ok) {
    let m = `Error ${resp.status}`;
    try {
      const d = await resp.json();
      m = d.detail || m;
    } catch (e) {}
    throw new Error(m);
  }
  const text = await resp.text();
  return text ? JSON.parse(text) : {};
}

export const SupervisorAPI = {
  async whoami() {
    return fetchApi('/auth/whoami');
  },
  async logout() {
    return fetchApi('/auth/logout', { method: 'POST' });
  },
  async getProyectos() {
    // /api/proyectos/ sirve a SUPERVISOR y ADMIN. Antes intentaba primero
    // /api/admin/proyectos (admin-only) => 403 ruidoso en consola para supervisor.
    return fetchApi('/api/proyectos/');
  },
  async getEspecialistas() {
    return fetchApi('/api/especialistas/');
  },
  async runScanner() {
    return fetchApi('/api/scanner/run', { method: 'POST' });
  },
  async createPlan(data) {
    return fetchApi('/api/planes-trabajo/', { method: 'POST', body: data });
  },
  async getClientes() {
    return fetchApi('/api/clientes');
  },
  async addCliente(nombre) {
    return fetchApi('/api/clientes', { method: 'POST', body: { nombre } });
  },
  async siguienteNumero(cliente) {
    return fetchApi('/api/planes-trabajo/siguiente-numero?cliente=' + encodeURIComponent(cliente));
  },
  async getProyectoDetalle(pid) {
    return fetchApi(`/api/proyectos/${pid}/detalle-planificacion/`);
  },
  async getPlanesActivos() {
    return fetchApi('/api/planes-trabajo/activos-detalle/');
  },
  async deleteAsignacion(id) {
    return fetchApi(`/api/asignaciones/${id}`, { method: 'DELETE' });
  },
  async deletePlan(id) {
    return fetchApi(`/api/planes-trabajo/${id}`, { method: 'DELETE' });
  },
  async reasignarTareaValidada(id) {
    return fetchApi(`/api/asignaciones/${id}/reasignar-validada`, { method: 'POST' });
  },
  async archivarPlan(pid) {
    return fetchApi(`/api/planes-trabajo/${pid}/archivar-mover`, { method: 'POST' });
  },
  async getAsignacionesPorEstado(estado) {
    return fetchApi(`/api/asignaciones/por-estado/${estado}`);
  },
  async getArchivosPorValidar(asigId) {
    return fetchApi(`/api/asignacion/${asigId}/archivos-por-validar`);
  },
  async validarBloque(ids) {
    for (const id of ids) {
      await fetchApi(`/api/asignaciones/${id}/validar/`, { method: 'POST' });
    }
    return { status: 'ok' };
  },
  async rechazarBloque(ids) {
    for (const id of ids) {
      await fetchApi(`/api/asignaciones/${id}/rechazar/`, {
        method: 'POST',
        body: { comentario: 'Rechazo masivo supervisor' },
      });
    }
    return { status: 'ok' };
  },
  async validarTarea(id) {
    return fetchApi(`/api/asignaciones/${id}/validar/`, { method: 'POST' });
  },
  async rechazarTarea(id, comentario = 'Rechazo supervisor') {
    return fetchApi(`/api/asignaciones/${id}/rechazar/`, { method: 'POST', body: { comentario } });
  },
  async getFotosCuarentena() {
    return fetchApi('/api/excepciones/fotos');
  },
  async aprobarFoto(data) {
    return fetchApi('/api/archivos/aprobar-archivo', { method: 'POST', body: data });
  },
  async rechazarFoto(data) {
    return fetchApi('/api/archivos/rechazar-archivo', { method: 'POST', body: data });
  },
  async corregirExif(data) {
    return fetchApi('/api/excepciones/aplicar-exif-manual', { method: 'POST', body: data });
  },
  async eliminarFotoCuarentena(data) {
    return fetchApi('/api/excepciones/rechazar-permanente', { method: 'POST', body: data });
  },
  async getPlanesListos() {
    // En lugar de un endpoint 'listos', el legado usaba todas las asignaciones VALIDADA
    return fetchApi('/api/asignaciones/por-estado/VALIDADA');
  },
  async getArchivosPlan(planId) {
    return fetchApi(`/api/informes/archivos-plan/${planId}`);
  },
  async startResumenPlan(planId, archivos) {
    return fetchApi(`/api/informes/start-resumen-plan/${planId}`, {
      method: 'POST',
      body: { archivos_incluidos: archivos },
    });
  },
  async getJobStatus(jobId) {
    return fetchApi(`/api/informes/job-status/${jobId}`);
  },
  async addItemsToPlan(pid, itemIds) {
    return fetchApi(`/api/planes-trabajo/${pid}/add-items`, {
      method: 'POST',
      body: { item_ids: itemIds },
    });
  },
  async generarReporteGlobal(body) {
    return fetchApi('/api/reportes/generar', { method: 'POST', body });
  },
};
