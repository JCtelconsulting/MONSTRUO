// ========================= login.js (v6.1 - MULTI-DOMAIN) =========================
document.addEventListener('DOMContentLoaded', () => {
  console.log('Login JS Loaded (Multi-Domain)');

  // --- CONFIGURACION DE DOMINIOS ---
  // Reemplaza con los dominios reales de produccion
  const DESTINOS = {
    ADMIN: '/modulos/dashboard/dashboard.html',
    GERENCIA: '/modulos/dashboard/dashboard.html',
    TERRENO: '/modulos/dashboard/dashboard.html',
    SUPERVISOR: '/modulos/dashboard/dashboard.html',
  };

  // Si ya tiene cookie, redirigir
  fetch('/api/auth/whoami', { credentials: 'include' })
    .then((r) => r.json())
    .then((data) => {
      if (data.logged) {
        const target = DESTINOS[data.role] || '/modulos/dashboard/dashboard.html';
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

      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) throw new Error(data.detail || 'Credenciales incorrectas');

      // Exito
      status.textContent = 'Acceso Correcto. Redirigiendo...';
      status.className = 'modal-status success';

      const target = DESTINOS[data.role] || '/modulos/dashboard/dashboard.html';

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
