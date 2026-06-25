// ========================= guarda_rol.js (v6.0) =========================
// Enforce de acceso por MÓDULO (path /modulos/<m>/).
// Arquitectura de host único (terreneitor.telconsulting.cl): el modelo viejo
// por subdominio quedó obsoleto (los subdominios redirigen todos al host único).
// - Admin: acceso total, no se redirige.
// - No-admin en un módulo que NO le corresponde -> a su módulo principal.
// - Reglas de acceso coherentes con las tarjetas del hub (data-rol).
// ========================================================================
document.addEventListener('DOMContentLoaded', () => {
  // Qué roles pueden ENTRAR a cada módulo (igual que data-rol de las tarjetas del hub).
  const ACCESO = {
    terreno: ['TERRENO', 'SUPERVISOR', 'ADMIN'],
    supervisor: ['SUPERVISOR', 'ADMIN'],
    gerencia: ['GERENCIA', 'ADMIN'],
    portal: ['ADMIN'],
  };
  // Módulo principal (landing) por rol: a dónde mandar a un no-admin que no corresponde.
  const PRINCIPAL = { TERRENO: 'terreno', SUPERVISOR: 'supervisor', GERENCIA: 'gerencia' };

  const envPrefix = typeof window.getEnvPrefix === 'function' ? window.getEnvPrefix() : '';
  const LOGIN_URL_CENTRAL = `https://terreneitor.telconsulting.cl${envPrefix}/`;

  function moduloDelPath(pathname) {
    const m = String(pathname || '').toLowerCase().match(/\/modulos\/([^/]+)/);
    return m ? m[1] : '';
  }

  async function checkAuthAndRedirect() {
    const pathname = String(window.location.pathname || '').toLowerCase();
    if (pathname.includes('login.html') || pathname.includes('/modulos/login/')) return;
    const moduloActual = moduloDelPath(pathname);

    try {
      const me = await fetchApi('/auth/whoami');
      if (!me || !me.logged) {
        window.__lastWhoamiLogged = false;
        throw new Error('Sesion invalida');
      }
      window.__lastWhoamiLogged = true;

      const role = String(me.role || '')
        .toUpperCase()
        .trim();

      // Admin: puede entrar a cualquier módulo.
      if (role.includes('ADMIN')) return;

      const permitidos = ACCESO[moduloActual];
      // Módulo con reglas y rol NO permitido -> lo mandamos a su módulo principal.
      if (permitidos && !permitidos.includes(role)) {
        const destino = PRINCIPAL[role];
        if (destino && destino !== moduloActual) {
          window.location.href = `${envPrefix}/modulos/${destino}/`;
        }
        return;
      }
      // Si el módulo le corresponde (o no tiene reglas), se queda donde está.
    } catch (err) {
      // Si ya sabíamos que la sesión era válida, no rebotar por errores transitorios.
      if (window.__lastWhoamiLogged === true) {
        console.warn(
          'Auth check falló pero la sesión era válida; no redirijo.',
          err
        );
        return;
      }
      const msg = String(err?.message || '').toLowerCase();
      // Solo rebotar al login si realmente parece sesión inválida.
      if (msg.includes('sesion') || msg.includes('401') || msg.includes('expirada')) {
        window.__lastWhoamiLogged = false;
        window.location.href = LOGIN_URL_CENTRAL;
        return;
      }
      // Red/timeout/permiso (403): quedarse donde está.
      console.warn(
        'Auth check falló (red/permiso); me quedo en la página.',
        err
      );
      return;
    }
  }

  checkAuthAndRedirect();
});
