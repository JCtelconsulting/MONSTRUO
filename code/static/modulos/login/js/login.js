// ========================= login.js (v6.1 - MULTI-DOMAIN) =========================
document.addEventListener('DOMContentLoaded', () => {
  console.log('Login JS Loaded (Multi-Domain)');

  // --- CONFIGURACION DE DOMINIOS ---
  // Reemplaza con los dominios reales de produccion
  const DOMINIOS = {
    login: 'https://login.telconsulting.cl',
    erp: 'https://erp.telconsulting.cl',
    pmo: 'https://pmo.telconsulting.cl',
    crm: 'https://crm.telconsulting.cl',
    bodega: 'https://bodega.telconsulting.cl',
    ticketera: 'https://ticketera.telconsulting.cl',
    ia: 'https://ia.telconsulting.cl',
    zabbix: 'https://zabbix.telconsulting.cl',
    config: 'https://config.telconsulting.cl',
  };

  // --- API BASE URL ---
  const IS_DEV = window.location.pathname.startsWith('/dev');
  const API_BASE = IS_DEV ? '/dev' : '';

  function getPostLoginTarget() {
    const isProdHost = window.location.hostname.toLowerCase().endsWith('.telconsulting.cl');
    if (!isProdHost) {
      return '/modulos/dashboard/dashboard.html';
    }
    // Detectar si estamos en /dev/ y mantener el prefijo, de lo contrario raiz
    const prefix = IS_DEV ? '/dev' : '';
    return `${prefix}/dashboard`;
  }

  // --- GOOGLE LOGIN ---
  const btnGoogle = document.getElementById('btnGoogle');
  if (btnGoogle) {
    btnGoogle.addEventListener('click', () => {
      // Usar la base de la API detectada para redirigir
      const redirectUrl = `${API_BASE}/api/auth/google/login`;
      window.location.href = redirectUrl;
    });
  }

  // Si ya tiene cookie, redirigir
  window.fetchApi('/api/auth/whoami')
    .then((data) => {
      if (data.logged) {
        const target = getPostLoginTarget();
        console.log('Sesion activa. Redirigiendo a:', target);
        window.location.href = target;
      }
    })
    .catch(() => { });

  const form = document.getElementById('loginForm');
  const btn = document.getElementById('btnLogin');
  const status = document.getElementById('status');

  if (!form) return;

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();

    status.textContent = 'Accediendo...';
    status.className = 'modal-status loading';
    btn.disabled = true;

    try {
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;

      await window.fetchApi('/api/auth/login', {
        method: 'POST',
        body: { email, password },
      });

      // Exito
      status.textContent = 'Acceso Correcto. Redirigiendo...';
      status.className = 'modal-status success';

      const target = getPostLoginTarget();

      // Pequeno delay para feedback visual
      setTimeout(() => {
        window.location.href = target;
      }, 500);
    } catch (e) {
      status.textContent = e.message;
      status.className = 'modal-status error';
      btn.disabled = false;
    }
  });
});
