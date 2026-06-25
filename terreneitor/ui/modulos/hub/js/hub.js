// Hub Terreneitor: entrada única del módulo dentro del ecosistema Monstruo.
// La barra lateral es la REAL de Monstruo (shared/js/sidebar.js del gateway).
// Regla de acceso: ADMIN ve las tarjetas (puede entrar a todo); el resto NO ve
// el hub, entra DIRECTO a su módulo principal (para que no se metan donde no corresponde).
(() => {
  const PFX = window.getEnvPrefix ? window.getEnvPrefix() : '';
  const GW = 'https://login.telconsulting.cl' + PFX;
  // Módulo principal (landing) por rol para los no-admin.
  const PRINCIPAL = {
    TERRENO: '/modulos/terreno/',
    SUPERVISOR: '/modulos/supervisor/',
    GERENCIA: '/modulos/gerencia/',
  };

  async function init() {
    let who = { logged: false };
    try {
      who = await (await fetch(PFX + '/api/auth/whoami', { credentials: 'include' })).json();
    } catch (e) {}
    if (!who.logged) {
      // Sin sesión -> login central del ecosistema.
      location.href = GW + '/';
      return;
    }
    const rol = String(who.role || '').toUpperCase();

    // No-admin: directo a su módulo, sin pasar por el hub ni ver otras opciones.
    if (!rol.includes('ADMIN')) {
      const destino = PRINCIPAL[rol];
      if (destino) {
        location.href = PFX + destino;
        return;
      }
      // Rol sin módulo asignado: no lo dejamos en el hub, lo mandamos al login central.
      location.href = GW + '/';
      return;
    }

    // Admin: mostrar todas las tarjetas a las que tiene acceso.
    const cards = [...document.querySelectorAll('.hub-card')].filter((c) =>
      c.dataset.rol.split(',').includes(rol)
    );
    cards.forEach((c) => {
      c.href = PFX + c.dataset.path;
      c.style.display = 'flex';
    });
  }

  init();
})();
