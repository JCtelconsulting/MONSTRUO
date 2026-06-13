// ========================= guarda_rol.js (v5.4) =========================
// Enforce por rol + subdominio (DEV/PROD) según prefijo /dev|/prod
// - Admin (cualquier variante) no se redirige
// - Roles no mapeados: no redirigir (evita mandar a portal por fallback)
// ========================================================================
document.addEventListener('DOMContentLoaded', () => {
  const DESTINO_POR_ROL = {
    ADMIN: 'https://portal.telconsulting.cl',
    GERENCIA: 'https://gerencial.telconsulting.cl',
    TERRENO: 'https://terreneitor.telconsulting.cl',
    SUPERVISOR: 'https://supervisor.telconsulting.cl',
  };

  const envPrefix = typeof window.getEnvPrefix === 'function' ? window.getEnvPrefix() : '';
  const isDev = envPrefix === '/dev';
  const envKey = isDev ? 'dev' : '';
  const withEnv = (baseUrl) => `${baseUrl.replace(/\/+$/, '')}${isDev ? '/dev/' : '/'}`;
  const LOGIN_URL_CENTRAL = isDev
    ? 'https://terreno.telconsulting.cl/dev'
    : 'https://terreno.telconsulting.cl';

  async function checkAuthAndRedirect() {
    const pathname = String(window.location.pathname || '').toLowerCase();
    if (pathname.includes('login.html') || pathname.includes('/modulos/login/')) return;

    try {
      const me = await fetchApi('/auth/whoami');
      if (!me || !me.logged) {
        window.__lastWhoamiLogged = false; // Explicitly set to false if session is invalid
        throw new Error('Sesion invalida');
      }
      window.__lastWhoamiLogged = true; // Set to true if session is valid

      const role = String(me.role || '')
        .toUpperCase()
        .trim();

      // Admin: permitir navegar cualquier subdominio
      if (role.includes('ADMIN')) return;

      const destinoBase = DESTINO_POR_ROL[role];
      // Si el rol no está mapeado, no redirigir (evita fallback erróneo)
      if (!destinoBase) return;

      const destinoOficial = withEnv(destinoBase);
      const currentDomain = window.location.hostname;
      const targetDomain = new URL(destinoOficial).hostname;

      if (currentDomain !== targetDomain) {
        // Si es un rol ADMIN y estamos en un entorno DEV, permitir quedarse en el subdominio actual.
        if (role.includes('ADMIN') && envKey === 'dev') {
          return; // No redirigir
        }

        window.location.href = destinoOficial;
        return;
      }
    } catch (err) {
      // Si ya sabemos que hay sesión válida, no rebotar al login por errores transitorios.
      if (window.__lastWhoamiLogged === true) {
        // Log the error for debugging, but prevent redirection
        console.warn(
          'Authentication check failed but session was previously valid. Preventing redirection.',
          err
        );
        return;
      }

      const msg = String(err?.message || '').toLowerCase();
      // Solo rebotar si realmente parece sesión inválida
      if (msg.includes('sesion') || msg.includes('401') || msg.includes('expirada')) {
        window.__lastWhoamiLogged = false; // Explicitly mark as not logged in before redirecting
        window.location.href = LOGIN_URL_CENTRAL;
        return; // Add return to ensure no further processing after redirect
      }
      // En otros casos (timeout/red/403 permisos), quedarse donde está.
      // We don't change __lastWhoamiLogged here as it might be a temporary network issue or 403.
      // The current state of __lastWhoamiLogged (if true) should protect against redirection.
      console.warn(
        'Authentication check failed with a non-session-expired error. Staying on current page.',
        err
      );
      return;
    }
  }

  checkAuthAndRedirect();
});
