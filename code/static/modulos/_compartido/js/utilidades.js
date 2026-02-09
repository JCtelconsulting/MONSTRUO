// ==========================================================================
// utilidades.js (vPROD FINAL) - Shared Utils & Logout Fix
// ==========================================================================

// --- API CLIENT ---
const IS_PROD_DOMAIN = window.location.hostname.endsWith('.telconsulting.cl');
const LOGIN_URL = IS_PROD_DOMAIN ? 'https://login.telconsulting.cl' : '/login.html';

function redirectToLogin() {
  window.location.href = LOGIN_URL;
}

async function fetchApi(url, options = {}) {
  // Normalizar URL
  if (typeof url === 'string' && url.startsWith('/') && !url.startsWith('/api')) {
    url = '/api' + url;
  }
  options.credentials = 'include';
  options.headers = options.headers || {};

  if (options.body) {
    if (typeof options.body !== 'string' && !(options.body instanceof FormData)) {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    } else if (typeof options.body === 'string' && !options.headers['Content-Type']) {
      // Assume JSON if string and no header set, or let user set it.
      // Better safe: user sets header if manually stringifying.
      options.headers['Content-Type'] = 'application/json';
    }
  }

  const resp = await fetch(url, options);

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

  if (!resp.ok) {
    let msg = `Error ${resp.status}`;
    try {
      const d = await resp.json();
      // Try to find a human readable message
      if (typeof d === 'string') msg = d;
      else if (d.detail) msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
      else if (d.message) msg = d.message;
      else if (d.error) msg = d.error;
      else msg = JSON.stringify(d);
    } catch (e) {
      // If json parse fails, use text or status text
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
