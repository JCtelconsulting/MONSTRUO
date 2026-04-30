// ==========================================================================
// utilidades.js (vPROD FINAL) - Shared Utils & Logout Fix
// ==========================================================================

// --- API CLIENT ---
// --- API CLIENT ---
const IS_PROD_DOMAIN = window.location.hostname.endsWith('.telconsulting.cl');
const IS_DEV_PATH = window.location.pathname.startsWith('/dev');

function getEnvPrefix() {
  return IS_DEV_PATH ? '/dev' : '';
}

/**
 * Determines the API base URL based on the current environment.
 * @returns {string} The base URL for API requests (e.g., '/api', '/dev/api').
 */
function getApiBase() {
  if (IS_DEV_PATH) return '/dev/api';
  return '/api';
}

// Expose global for legacy/other modules
window.getApiBase = getApiBase;
window.getEnvPrefix = getEnvPrefix;

const LOCAL_GATEWAY_URL = `${window.location.protocol || 'http:'}//${window.location.hostname || '127.0.0.1'}:9001`;
const LOGIN_URL = IS_PROD_DOMAIN
  ? `https://login.telconsulting.cl${getEnvPrefix() || ''}/`
  : `${LOCAL_GATEWAY_URL}${getEnvPrefix() || ''}/`;

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
    // E.g. /api/users -> /dev/api/users
    const base = getApiBase();
    url = url.replace('/api', base);
  } else if (url.startsWith('/') && !url.startsWith('/dev')) {
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
      // No recargar la página si el propio login falló
      if (url.includes('/api/auth/login')) {
        throw new Error('Credenciales inválidas');
      }
      redirectToLogin();
      throw new Error('Sesión expirada o permisos insuficientes');
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
    if (btn.dataset.logoutBound === '1') return;
    btn.dataset.logoutBound = '1';
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

function ensureChangePasswordModal() {
  let modal = document.getElementById('modal-change-password');
  if (modal) return modal;

  modal = document.createElement('div');
  modal.id = 'modal-change-password';
  modal.className = 'modal-backdrop';
  modal.innerHTML = `
    <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="change-password-title">
      <div class="modal-header">
        <h2 id="change-password-title">Cambiar Contrasena</h2>
        <button type="button" class="modal-close-btn" aria-label="Cerrar">&times;</button>
      </div>
      <form>
        <div class="modal-body">
          <div class="cfg-field">
            <label class="cfg-label" for="modal-old-pass">Contrasena Actual</label>
            <input type="password" id="modal-old-pass" class="input-dark" autocomplete="current-password" required>
          </div>
          <div class="cfg-field">
            <label class="cfg-label" for="modal-new-pass">Nueva Contrasena</label>
            <input type="password" id="modal-new-pass" class="input-dark" minlength="8" autocomplete="new-password" required>
          </div>
          <div id="modal-status-msg" class="modal-status"></div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-secondary modal-close-btn">Cancelar</button>
          <button type="submit" class="btn-primary">Actualizar</button>
        </div>
      </form>
    </div>
  `;
  document.body.appendChild(modal);
  return modal;
}

// --- MODALES (Standard) ---
function initModal() {
  const btnOpen = document.getElementById('btn-open-change-password');
  const modal = ensureChangePasswordModal();

  if (btnOpen && modal) {
    if (btnOpen.dataset.modalBound === '1') return;
    btnOpen.dataset.modalBound = '1';
    const closeModal = () => {
      modal.style.display = 'none';
    };
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
      b.onclick = closeModal;
    });

    if (modal.dataset.closeBound !== '1') {
      modal.dataset.closeBound = '1';
      modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
      });
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display === 'flex') closeModal();
      });
    }

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
            closeModal();
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


// --- ENV SWITCH (LEGACY REMOVED) ---
// La lógica de "Modo: ?" y "Cambiar entorno" (boton verde) se eliminó
// para favorecer el botón estándar del sidebar en el footer.

document.addEventListener('DOMContentLoaded', () => {
  // initEnvSwitchGlobal(); // Desactivado por redundancia
});
