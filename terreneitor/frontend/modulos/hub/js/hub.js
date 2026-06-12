// Hub Terreneitor: entrada única del módulo dentro del ecosistema Monstruo.
// La barra lateral es la REAL de Monstruo (shared/js/sidebar.js del gateway);
// acá solo va la lógica de las tarjetas por rol y el guard de sesión.
(() => {
  const PFX = window.getEnvPrefix ? window.getEnvPrefix() : '';
  const GW = 'https://login.telconsulting.cl' + PFX;

  async function init() {
    let who = { logged: false };
    try {
      who = await (await fetch(PFX + '/api/auth/whoami', { credentials: 'include' })).json();
    } catch (e) {}
    if (!who.logged) {
      // Sin sesión propia ni del gateway -> login central del ecosistema
      location.href = GW + '/';
      return;
    }
    const rol = String(who.role || '').toUpperCase();
    const cards = [...document.querySelectorAll('.hub-card')].filter((c) =>
      c.dataset.rol.split(',').includes(rol)
    );
    // El técnico tiene un solo destino: directo a su módulo, sin clic extra.
    if (rol === 'TERRENO' && cards.length === 1) {
      location.href = PFX + cards[0].dataset.path;
      return;
    }
    cards.forEach((c) => {
      c.href = PFX + c.dataset.path;
      c.style.display = 'flex';
    });
  }

  init();
})();
