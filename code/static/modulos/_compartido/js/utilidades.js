// ==========================================================================
// utilidades.js (vPROD FINAL) - Shared Utils & Logout Fix
// ==========================================================================

// --- API CLIENT ---
// --- API CLIENT ---
const IS_PROD_DOMAIN = window.location.hostname.endsWith('.telconsulting.cl');

/**
 * Determines the API base URL based on the current environment.
 * @returns {string} The base URL for API requests (e.g., '/api', '/dev/api', '/prod/api').
 */
function getApiBase() {
  // 1. Path prefix has priority when running behind reverse proxy.
  // This avoids crossing environments if someone opens http://127.0.0.1/dev/... manually.
  const isDev = window.location.pathname.startsWith('/dev');
  const isProd = window.location.pathname.startsWith('/prod');
  if (isDev) return '/dev/api';
  if (isProd) return '/prod/api';

  // 2. Local Development (no prefix)
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return '/api';
  }

  // 3. Server default
  return '/prod/api';
}

// Expose global for legacy/other modules
window.getApiBase = getApiBase;

const LOGIN_URL = IS_PROD_DOMAIN ? `https://login.telconsulting.cl${window.location.pathname.startsWith('/dev') ? '/dev' : '/prod'}/` : '/login.html';

function redirectToLogin() {
  window.location.href = LOGIN_URL;
}

async function fetchApi(url, options = {}) {
  const reqOptions = { ...options };
  const timeoutMs = Number.isFinite(reqOptions.timeoutMs) ? reqOptions.timeoutMs : 12000;
  delete reqOptions.timeoutMs;

  let timeoutId = null;
  let timedOut = false;
  let timeoutController = null;
  const externalSignal = reqOptions.signal;
  let externalAbortHandler = null;

  if (timeoutMs > 0) {
    timeoutController = new AbortController();
    if (externalSignal) {
      if (externalSignal.aborted) {
        timeoutController.abort();
      } else {
        externalAbortHandler = () => timeoutController.abort();
        externalSignal.addEventListener('abort', externalAbortHandler, { once: true });
      }
    }
    timeoutId = window.setTimeout(() => {
      timedOut = true;
      timeoutController.abort();
    }, timeoutMs);
    reqOptions.signal = timeoutController.signal;
  }

  // Normalize URL using central getApiBase logic
  if (url.startsWith('/api')) {
    // Replace /api with the correct environment prefix
    // E.g. /api/users -> /dev/api/users OR /prod/api/users
    const base = getApiBase(); // e.g. '/dev/api'
    url = url.replace('/api', base);
  } else if (url.startsWith('/') && !url.startsWith('/dev') && !url.startsWith('/prod')) {
    // Relative path without prefix, assume API call if not static
    // Prefer explicit /api usage in calls, but handle fallback
    const base = getApiBase();
    url = `${base}${url}`;
  }

  reqOptions.credentials = 'include';
  reqOptions.headers = reqOptions.headers || {};

  if (reqOptions.body) {
    if (typeof reqOptions.body !== 'string' && !(reqOptions.body instanceof FormData)) {
      reqOptions.headers['Content-Type'] = 'application/json';
      reqOptions.body = JSON.stringify(reqOptions.body);
    } else if (typeof reqOptions.body === 'string' && !reqOptions.headers['Content-Type']) {
      reqOptions.headers['Content-Type'] = 'application/json';
    }
  }
  try {
    const resp = await fetch(url, reqOptions);

    if (resp.status === 401) {
      redirectToLogin();
      throw new Error('Sesion expirada');
    }

    if (resp.status === 403) {
      const authMsg = 'Acceso denegado (permisos insuficientes)';
      if (typeof window.showToast === 'function') {
        window.showToast("⚠️ " + authMsg, "warning");
      } else {
        console.warn(authMsg);
      }
      throw new Error(authMsg);
    }

    try {
      if (!resp.ok) {
        let msg = `Error ${resp.status}`;
        try {
          const d = await resp.json();
          if (typeof d === 'string') msg = d;
          else if (d.detail) msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
          else if (d.message) msg = d.message;
          else if (d.error) msg = d.error;
          else msg = JSON.stringify(d);
        } catch (e) {
          const t = await resp.text().catch(() => '');
          if (t) msg = t;
        }
        throw new Error(msg);
      }

      const text = await resp.text();
      try {
        return text ? JSON.parse(text) : {};
      } catch (e) {
        console.warn("API response was not JSON:", text);
        return { raw: text };
      }
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
      if (externalSignal && externalAbortHandler) {
        externalSignal.removeEventListener('abort', externalAbortHandler);
      }
    }
  } catch (err) {
    if (timeoutId) window.clearTimeout(timeoutId);
    if (externalSignal && externalAbortHandler) {
      externalSignal.removeEventListener('abort', externalAbortHandler);
    }
    if (timedOut) {
      throw new Error(`Timeout de red (${timeoutMs}ms)`);
    }
    throw err;
  }
}

async function verifySession() {
  try {
    const res = await fetchApi('/api/sesion');
    if (!res.ok) {
      redirectToLogin();
    } else {
      console.log("Sesion OK:", res.user);
    }
  } catch (e) {
    console.warn("Error verificando sesion:", e);
  }
}

// --- LOGOUT GLOBAL (CORREGIDO) ---
function initLogout() {
  const btn = document.getElementById('btnLogout');
  if (btn) {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        // Llamada al backend para borrar cookie
        await fetchApi('/auth/logout', { method: 'POST' });
      } catch (err) {
        console.error('Logout warning:', err);
      } finally {
        // REDIRECCION EXACTA AL DOMINIO DE LOGIN
        redirectToLogin();
      }
    });
  }
}

// --- MODALES (Standard) ---
function initModal() {
  const btnOpen = document.getElementById('btn-open-change-password');
  const modal = document.getElementById('modal-change-password');

  if (btnOpen && modal) {
    btnOpen.onclick = (e) => {
      e.preventDefault();
      modal.style.display = 'flex';
      const form = modal.querySelector('form');
      if (form) {
        form.reset();
      }
      const st = document.getElementById('modal-status-msg');
      if (st) {
        st.textContent = '';
      }
    };

    const closeBtns = modal.querySelectorAll('.modal-close-btn');
    closeBtns.forEach((b) => {
      b.onclick = () => (modal.style.display = 'none');
    });

    const form = modal.querySelector('form');
    if (form) {
      form.onsubmit = async (e) => {
        e.preventDefault();
        const oldP = document.getElementById('modal-old-pass').value;
        const newP = document.getElementById('modal-new-pass').value;
        const st = document.getElementById('modal-status-msg');

        if (st) {
          st.textContent = 'Procesando...';
          st.className = 'modal-status loading';
        }

        try {
          await fetchApi('/auth/change-password', {
            method: 'POST',
            body: {
              old_password: oldP,
              new_password: newP,
            },
          });
          if (st) {
            st.textContent = 'Contrasena actualizada.';
            st.className = 'modal-status success';
          }
          setTimeout(() => {
            modal.style.display = 'none';
          }, 1500);
        } catch (err) {
          if (st) {
            st.textContent = err.message;
            st.className = 'modal-status error';
          }
        }
      };
    }
  }
}

// --- TOAST NOTIFICATIONS SYSTEM ---
const TOAST_CSS = `
.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast {
  background: rgba(20, 20, 20, 0.95);
  color: #fff;
  padding: 12px 20px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  font-family: 'Inter', sans-serif; /* Asumiendo fuente del sistema o fallback */
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  gap: 12px;
  backdrop-filter: blur(10px);
  min-width: 300px;
  max-width: 400px;
  pointer-events: auto;
  opacity: 0;
  transform: translateY(20px);
  animation: toastIn 0.3s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}

.toast.success { border-left: 4px solid #10b981; }
.toast.error { border-left: 4px solid #ef4444; }
.toast.info { border-left: 4px solid #3b82f6; }
.toast.warning { border-left: 4px solid #f59e0b; }

.toast-message { flex: 1; line-height: 1.4; }
.toast-close { cursor: pointer; opacity: 0.6; padding: 4px; }
.toast-close:hover { opacity: 1; }

@keyframes toastIn {
  to { opacity: 1; transform: translateY(0); }
}
@keyframes toastOut {
  to { opacity: 0; transform: translateX(100%); }
}
`;

function injectToastStyles() {
  if (!document.getElementById('toast-styles')) {
    const style = document.createElement('style');
    style.id = 'toast-styles';
    style.textContent = TOAST_CSS;
    document.head.appendChild(style);
  }
}

function showToast(message, type = 'info') {
  injectToastStyles(); // Asegurar estilos

  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  // Iconos SVG simples
  const ICONS = {
    success: '<svg width="20" height="20" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>',
    error: '<svg width="20" height="20" fill="none" stroke="#ef4444" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>',
    info: '<svg width="20" height="20" fill="none" stroke="#3b82f6" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    warning: '<svg width="20" height="20" fill="none" stroke="#f59e0b" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>'
  };

  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `
    ${ICONS[type] || ''}
    <div class="toast-message">${message}</div>
    <div class="toast-close" onclick="this.parentElement.remove()">✕</div>
  `;

  container.appendChild(el);

  // Auto remove
  setTimeout(() => {
    el.style.animation = 'toastOut 0.3s forwards';
    el.addEventListener('animationend', () => el.remove());
  }, 5000);
}

// Exponer globalmente
window.fetchApi = fetchApi;
window.initLogout = initLogout;
window.initModal = initModal;
window.showToast = showToast;

// --- ENV SWITCH (PROD/DEV) ---
function initEnvSwitchGlobal() {
  const header = document.querySelector('.header-actions');
  if (!header) return;
  if (document.getElementById('env-indicator')) return;

  const indicator = document.createElement('div');
  indicator.id = 'env-indicator';
  indicator.className = 'pill';
  indicator.style.display = 'block';
  indicator.style.marginBottom = '10px';
  indicator.style.fontSize = '0.75rem';
  indicator.textContent = 'Modo: ...';

  const btn = document.createElement('button');
  btn.id = 'btnEnvSwitch';
  btn.className = 'btn-account';
  btn.title = 'Cambiar entorno';
  btn.innerHTML = '<i class="fas fa-exchange-alt"></i> <span>Cambiar entorno</span>';

  const footer = header.querySelector('.footer-buttons-container');
  let insertRef = footer || header.querySelector('button');
  if (!insertRef) insertRef = null;
  header.insertBefore(indicator, insertRef);
  header.insertBefore(btn, insertRef);

  const isProdHost = window.location.hostname.endsWith('.telconsulting.cl');
  if (!isProdHost) {
    indicator.textContent = 'Modo: LOCAL';
    btn.style.display = 'none';
    return;
  }

  fetch('/version', { credentials: 'include' })
    .then((resp) => resp.json())
    .then((info) => {
      const isDev = String(info.branch || '').toLowerCase() === 'dev';
      indicator.classList.remove('env-prod', 'env-dev');
      indicator.classList.add(isDev ? 'env-dev' : 'env-prod');
      const envText = isDev ? 'DEV' : 'PROD';
      indicator.innerHTML = `<span class="env-prefix">Modo:</span> <span class="env-long">${envText}</span><span class="env-short">${envText}</span>`;
      btn.innerHTML = isDev
        ? '<i class="fas fa-toggle-off"></i> <span>Ir a PROD</span>'
        : '<i class="fas fa-toggle-on"></i> <span>Ir a DEV</span>';
      btn.onclick = () => {
        window.location.href = isDev ? '/__env/prod' : '/__env/dev';
      };
    })
    .catch(() => {
      indicator.textContent = 'Modo: ?';
    });
}

document.addEventListener('DOMContentLoaded', () => {
  initEnvSwitchGlobal();
});
