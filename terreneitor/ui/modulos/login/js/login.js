// ========================= login.js (v7.5 - REDIRECT PROD DEFAULT) =========================
document.addEventListener('DOMContentLoaded', () => {
  const IS_DEV = window.location.pathname.startsWith('/dev');
  // Si no empieza con /dev, es Producción (raíz).
  const envKey = IS_DEV ? 'dev' : 'prod';
  const API_BASE = IS_DEV ? '/dev' : '';

  function getPostLoginTarget(role = null) {
    const r = String(role || '')
      .toUpperCase()
      .trim();
    const byRole = {
      ADMIN: 'https://portal.telconsulting.cl',
      GERENCIA: 'https://gerencial.telconsulting.cl',
      SUPERVISOR: 'https://supervisor.telconsulting.cl',
      TERRENO: 'https://terreneitor.telconsulting.cl',
    };
    const base = byRole[r] || 'https://portal.telconsulting.cl';
    return IS_DEV ? `${base}/dev/` : `${base}/`;
  }

  async function apiLocal(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });

    const text = await res.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {}

    if (!res.ok) {
      const err = new Error((data && (data.detail || data.message)) || `Error ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  const btnGoogle = document.getElementById('btnGoogle');
  const form = document.getElementById('loginForm');
  const btn = document.getElementById('btnLogin');
  const status = document.getElementById('status');

  if (btnGoogle) {
    btnGoogle.addEventListener('click', () => {
      window.location.href = `${API_BASE}/api/auth/google/login`;
    });
  }

  // Bootstrap session: si el usuario YA tiene cookie valida, mandarlo al
  // portal/modulo correspondiente. Pero si llega con ?reason=expired (un
  // modulo lo rechazo), o si esta atrapado en un bucle (lo detectamos con
  // sessionStorage), no redirigir y dejar que reintente login.
  const params = new URLSearchParams(window.location.search);
  const cameFromRejection = params.has('reason');
  const REDIRECT_KEY = 'login_redirect_attempt';
  const lastRedirectStr = sessionStorage.getItem(REDIRECT_KEY);
  const now = Date.now();
  const recentRedirect = lastRedirectStr && now - Number(lastRedirectStr) < 5000;

  if (!cameFromRejection && !recentRedirect) {
    apiLocal('/api/auth/whoami')
      .then((data) => {
        if (data?.logged) {
          sessionStorage.setItem(REDIRECT_KEY, String(now));
          window.location.href = getPostLoginTarget(data.role);
        }
      })
      .catch(() => {});
  }

  if (!form || !btn || !status) return;

  // Bloqueo duro de submit nativo
  form.setAttribute('novalidate', 'novalidate');
  form.setAttribute('action', 'javascript:void(0);');
  form.onsubmit = (e) => {
    if (e) e.preventDefault();
    return false;
  };

  async function handleLogin(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }

    status.textContent = 'Accediendo...';
    status.className = 'modal-status loading';
    btn.disabled = true;

    try {
      const email = document.getElementById('email')?.value?.trim() || '';
      const password = document.getElementById('password')?.value || '';

      const loginData = await apiLocal('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });

      status.textContent = 'Acceso Correcto. Redirigiendo...';
      status.className = 'modal-status success';
      setTimeout(() => {
        window.location.href = getPostLoginTarget(loginData?.role || null);
      }, 250);
    } catch (e) {
      const raw = String(e?.message || '').toLowerCase();
      const msg =
        e?.status == 401 || raw.includes('credenciales')
          ? 'Credenciales inválidas'
          : 'Error de autenticación. Intenta nuevamente.';
      status.textContent = msg;
      status.className = 'modal-status error';
      btn.disabled = false;
    }

    return false;
  }

  form.addEventListener('submit', handleLogin);
  btn.addEventListener('click', handleLogin);
  form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleLogin(e);
    }
  });
});
