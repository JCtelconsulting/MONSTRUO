// ==========================================================================
// utilidades.js (vPROD FINAL) - Shared Utils & Logout Fix
// ==========================================================================

// --- API CLIENT ---
function getEnvPrefix(pathname = window.location.pathname) {
  if (pathname === '/dev' || pathname.startsWith('/dev/')) return '/dev';
  // PROD no usa prefijo (URL limpia). /prod queda como alias compatible.
  if (pathname === '/prod' || pathname.startsWith('/prod/')) return '';
  return '';
}

function withEnvPrefix(path, pathname = window.location.pathname) {
  const envPrefix = getEnvPrefix(pathname);
  const normalized = String(path || '').startsWith('/') ? path : `/${path || ''}`;
  return envPrefix ? `${envPrefix}${normalized}` : normalized;
}

function getEnvLoginUrl(pathname = window.location.pathname) {
  // Login central del ecosistema Monstruo (Terreneitor ya no tiene login
  // propio; la sesión del gateway entra vía SSO). El login local queda solo
  // como respaldo directo en /modulos/login/.
  const LOGIN_HOST = 'https://login.telconsulting.cl';
  return `${LOGIN_HOST}${withEnvPrefix('/', pathname)}`;
}

// Escapa texto para interpolarlo de forma segura dentro de innerHTML.
// Nombres de tarea/proyecto/cliente, comentarios y nombres de archivo los
// controla el usuario y se muestran en la sesion de otro rol: sin escapar
// permiten XSS almacenado cross-rol.
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

// Exponer helpers para modulos que definen redirecciones propias.
window.getEnvPrefix = getEnvPrefix;
window.withEnvPrefix = withEnvPrefix;
window.getEnvLoginUrl = getEnvLoginUrl;
window.escapeHtml = escapeHtml;

// Favicon de marca (logo en la pestaña del navegador) en todas las paginas de terreneitor.
(function () {
  try {
    var href = withEnvPrefix('/shared/img/telconsulting-isotipo-dorado.png');
    var link = document.querySelector("link[rel~='icon']");
    if (!link) { link = document.createElement('link'); link.rel = 'icon'; (document.head || document.documentElement).appendChild(link); }
    link.type = 'image/png';
    link.href = href;
  } catch (e) { /* noop */ }
})();

function normalizeTelconsultingEnvLinks(root = document) {
  const envPrefix = getEnvPrefix();
  const prefixPath = envPrefix === '/dev' ? '/dev' : '';
  const allowedHosts = new Set([
    'portal.telconsulting.cl',
    'terreno.telconsulting.cl',
    'terreneitor.telconsulting.cl',
    'supervisor.telconsulting.cl',
    'gerencial.telconsulting.cl',
  ]);

  root.querySelectorAll('a[href]').forEach((anchor) => {
    const raw = anchor.getAttribute('href');
    if (!raw || raw.startsWith('#') || raw.startsWith('mailto:') || raw.startsWith('tel:')) {
      return;
    }

    let parsed;
    try {
      parsed = new URL(raw, window.location.origin);
    } catch (e) {
      return;
    }

    if (!allowedHosts.has(parsed.hostname)) return;

    if (parsed.pathname === '/dev' || parsed.pathname.startsWith('/dev/')) return;
    if (parsed.pathname === '/prod' || parsed.pathname.startsWith('/prod/')) return;
    if (parsed.pathname.startsWith('/api/') || parsed.pathname.startsWith('/auth/')) return;

    const suffixPath = parsed.pathname === '/' ? '/' : parsed.pathname;
    parsed.pathname = `${prefixPath}${suffixPath}`;
    anchor.href = parsed.toString();
  });
}

window.normalizeTelconsultingEnvLinks = normalizeTelconsultingEnvLinks;

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => normalizeTelconsultingEnvLinks());
} else {
  normalizeTelconsultingEnvLinks();
}

function redirectToLogin() {
  window.location.href = getEnvLoginUrl();
}

async function fetchApi(url, options = {}) {
  // Normalizar URL para API local respetando prefijo de entorno (/dev|/prod)
  if (typeof url === 'string' && url.startsWith('/')) {
    if (url.startsWith('/api/') || url === '/api') {
      url = withEnvPrefix(url);
    } else if (url.startsWith('/auth/') || url === '/auth') {
      // Auth SIEMPRE vive bajo /api/auth en backend
      url = withEnvPrefix('/api' + url);
    } else if (!url.startsWith('/dev/') && !url.startsWith('/prod/')) {
      // Compatibilidad: rutas relativas de API -> /dev/api/...
      url = withEnvPrefix(url.startsWith('/api') ? url : '/api' + url);
    }
  }
  options.credentials = 'include';
  options.headers = options.headers || {};

  if (options.body && typeof options.body !== 'string' && !(options.body instanceof FormData)) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const resp = await fetch(url, options);
  if (resp.status === 401 || resp.status === 403) {
    // Si YA hay sesión válida (ej: whoami true), no rebotes al login por un 403 de permisos.
    if (window.__lastWhoamiLogged === true) {
      throw new Error('No autorizado');
    }
    if (typeof window.handleAuthExpired === 'function') {
      window.handleAuthExpired();
    } else {
      redirectToLogin();
    }
    throw new Error('Sesion expirada');
  }
  if (!resp.ok) {
    let msg = 'Error ' + resp.status;
    try {
      const d = await resp.json();
      msg = d.detail || msg;
    } catch (e) {}
    throw new Error(msg);
  }
  const text = await resp.text();
  return text ? JSON.parse(text) : {};
}

// --- LOGOUT GLOBAL (CORREGIDO) ---
function initLogout() {
  const btn = document.getElementById('btnLogout');
  if (btn) {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        // Logout robusto: no usar fetchApi para evitar redirecciones por 401.
        await fetch(withEnvPrefix('/api/auth/logout'), {
          method: 'POST',
          credentials: 'include',
        });
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
    success:
      '<svg width="20" height="20" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>',
    error:
      '<svg width="20" height="20" fill="none" stroke="#ef4444" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>',
    info: '<svg width="20" height="20" fill="none" stroke="#3b82f6" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    warning:
      '<svg width="20" height="20" fill="none" stroke="#f59e0b" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>',
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
