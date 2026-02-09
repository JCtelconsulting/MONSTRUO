// Bancos UI Controller (v2 - Clean)
// Desc: Controles de sesión individual para el nodo Android.

async function initBancosModule() {
    console.log("Bancos Module Loaded");

    // Configure iframe source for current host
    setAndroidFrameSrc();

    // Check Android status (best effort)
    checkAndroidHealth();

    // Start Lock heartbeat
    startLockHeartbeat();
}

function setAndroidFrameSrc() {
    const frame = document.getElementById('androidFrame');
    if (!frame) return;

    const udid = frame.getAttribute('data-udid') || '';
    const wsBase = frame.getAttribute('data-ws-base') || '';
    if (!udid || !wsBase) return;

    const protocol = window.location.protocol;
    const host = window.location.host;
    const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:';

    const wsUrl = `${wsProtocol}//${host}${wsBase}/?action=proxy-adb&remote=tcp:8886&udid=${encodeURIComponent(udid)}`;
    const streamUrl = `${protocol}//${host}${wsBase}/#!action=stream&udid=${encodeURIComponent(udid)}&player=mse&ws=${encodeURIComponent(wsUrl)}`;

    frame.src = streamUrl;
}

function checkAndroidHealth() {
    const frame = document.getElementById('androidFrame');
    const loader = document.getElementById('androidLoader');

    if (frame) {
        frame.onload = () => {
            setTimeout(() => {
                if (loader) loader.style.display = 'none';
            }, 1000);
        };
    }

    // Fallback timer
    setTimeout(() => {
        if (loader) loader.style.display = 'none';
    }, 4000);
}

// --- Lock & Turnos System (Real API) ---
let hasControl = false;
let lockInterval = null;

function startLockHeartbeat() {
    if (lockInterval) clearInterval(lockInterval);
    updateLockStatus();
    lockInterval = setInterval(updateLockStatus, 5000);
}

async function updateLockStatus() {
    try {
        const status = await window.fetchApi('/api/bancos/session');
        const led = document.getElementById('lockLed');
        const text = document.getElementById('lockText');
        const btn = document.querySelector('.bank-toolbar .erp-btn');

        if (!led || !text) return;

        hasControl = status.is_mine;

        if (status.locked) {
            if (status.is_mine) {
                led.className = "led bg-neon animate-pulse";
                text.innerText = "Controlado por Ti";
                text.className = "text-white font-bold";
                if (btn) btn.innerHTML = '<i class="fas fa-sign-out-alt" style="margin-right:8px;"></i> Liberar Control';
            } else {
                led.className = "led bg-red-500";
                text.innerText = `Ocupado por ${status.owner}`;
                text.className = "text-danger";
                if (btn) {
                    btn.classList.add('disabled');
                    btn.innerHTML = '<i class="fas fa-lock" style="margin-right:8px;"></i> Ocupado';
                    btn.style.opacity = '0.5';
                    btn.style.pointerEvents = 'none';
                }
            }
        } else {
            led.className = "led bg-green-500";
            text.innerText = "Disponible";
            text.className = "text-text-soft";
            if (btn) {
                btn.classList.remove('disabled');
                btn.innerHTML = '<i class="fas fa-fingerprint" style="margin-right:8px;"></i> Solicitar Control';
                btn.style.opacity = '1';
                btn.style.pointerEvents = 'auto';
            }
        }
    } catch (err) {
        console.error("Lock heartbeat fail:", err);
    }
}

async function requestBankControl() {
    try {
        if (!hasControl) {
            await window.fetchApi('/api/bancos/session/acquire', { method: 'POST' });
            window.showToast("Control adquirido", "success");
        } else {
            await window.fetchApi('/api/bancos/session/release', { method: 'POST' });
            window.showToast("Control liberado", "info");
        }
        updateLockStatus();
    } catch (err) {
        window.showToast(err.message || "Error al gestionar sesión", "error");
    }
}

// Zoom Controls
function applyZoom(val) {
    const frame = document.querySelector('.phone-frame');
    if (!frame) return;
    frame.style.transform = `scale(${val})`;
    const label = document.getElementById('zoomValue');
    if (label) label.innerText = `${Math.round(val * 100)}%`;
}
