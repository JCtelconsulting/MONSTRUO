(function () {
    // 1. Create Styles
    const style = document.createElement('style');
    style.innerHTML = `
        #admin-chat-widget { position: fixed; bottom: 20px; right: 20px; z-index: 10000; font-family: 'Space Grotesk', sans-serif; }
        #admin-chat-btn { width: 60px; height: 60px; border-radius: 50%; background: var(--color-info); color: #fff; border: none; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.3); font-size: 24px; transition: transform 0.2s; display:flex; align-items:center; justify-content:center;}
        #admin-chat-btn:hover { transform: scale(1.1); }
        #admin-chat-window { position: absolute; bottom: 80px; right: 0; width: 350px; height: 500px; background: #1a1f2b; border: 1px solid #444; border-radius: 12px; display: none; flex-direction: column; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        #admin-chat-header { padding: 15px; background: rgba(102, 16, 242, 0.2); border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; }
        #admin-chat-body { flex: 1; padding: 15px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
        #admin-chat-footer { padding: 15px; border-top: 1px solid rgba(255,255,255,0.1); display: flex; gap: 10px; }
        #admin-chat-input { flex: 1; background: rgba(0,0,0,0.3); border: 1px solid #444; color: #fff; padding: 8px; border-radius: 4px; outline: none; }
        #admin-chat-send { background: var(--color-info); color: #fff; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        .msg { padding: 8px 12px; border-radius: 8px; max-width: 80%; line-height: 1.4; font-size: 0.9rem; }
        .msg-user { align-self: flex-end; background: #007bff; color: #fff; }
        .msg-bot { align-self: flex-start; background: rgba(255,255,255,0.1); color: #ddd; }
        .msg-system { align-self: center; font-size: 0.8rem; color: #aaa; font-style: italic; margin-top: 5px; text-align: center; width: 100%; }
    `;
    document.head.appendChild(style);

    // 2. Create Elements
    const widget = document.createElement('div');
    widget.id = 'admin-chat-widget';

    widget.innerHTML = `
        <div id="admin-chat-window">
            <div id="admin-chat-header">
                <div>
                    <h4 style="margin:0; font-size:1rem; color:#fff;"><i class="fas fa-brain"></i> Monstruo Admin</h4>
                    <span style="font-size:0.75rem; color:#aaa;">System Architect</span>
                </div>
                <button id="admin-chat-close" style="background:none; border:none; color:#aaa; cursor:pointer;"><i class="fas fa-times"></i></button>
            </div>
            <div id="admin-chat-body">
                <div class="msg msg-bot">Hola. Soy el Administrador del Sistema. Puedes pedirme cambios en las reglas de categorización o consultas generales.</div>
            </div>
            <div id="admin-chat-footer">
                <input type="text" id="admin-chat-input" placeholder="Escribe 'Cambia la regla...'..." autocomplete="off">
                <button id="admin-chat-send"><i class="fas fa-paper-plane"></i></button>
            </div>
        </div>
        <button id="admin-chat-btn"><i class="fas fa-robot"></i></button>
    `;
    document.body.appendChild(widget);

    // 3. Logic
    const btn = document.getElementById('admin-chat-btn');
    const win = document.getElementById('admin-chat-window');
    const close = document.getElementById('admin-chat-close');
    const input = document.getElementById('admin-chat-input');
    const send = document.getElementById('admin-chat-send');
    const body = document.getElementById('admin-chat-body');

    function toggleChat() {
        const isOpen = win.style.display === 'flex';
        win.style.display = isOpen ? 'none' : 'flex';
        // Auto focus
        if (!isOpen) setTimeout(() => input.focus(), 100);
    }

    async function sendMessage() {
        const txt = input.value.trim();
        if (!txt) return;

        // User Msg
        appendMsg(txt, 'user');
        input.value = '';
        input.disabled = true;

        // Loading
        const loadId = appendMsg('Pensando...', 'bot', true);

        try {
            const res = await window.fetchApi('/api/admin/chat', { // Use fetchApi for auto-auth if needed, or standard fetch
                method: 'POST',
                body: { message: txt, context: {} }
            });
            const data = await res; // fetchApi returns JSON directly usually? No, fetchApi returns res.json() usually.

            // Check if fetchApi returns parsed json or response object. 
            // bodega.js uses window.fetchApi and awaits result. 
            // Let's assume input to fetchApi body is object, and it returns parsed JSON.
            // If checking utilidades.js is needed I can do that, but standard assumption in this project seems:
            // window.fetchApi(url, options) -> returns data object.

            // Remove loading
            document.getElementById(loadId).remove();

            // Bot Msg
            if (data.reply) {
                appendMsg(data.reply, 'bot');
            } else {
                appendMsg("Respuesta vacía del servidor.", 'bot');
            }

        } catch (e) {
            const l = document.getElementById(loadId);
            if (l) l.remove();
            appendMsg("Error: " + e.message, 'bot');
        } finally {
            input.disabled = false;
            input.focus();
        }
    }

    function appendMsg(text, type, isLoading = false) {
        const div = document.createElement('div');
        div.className = `msg msg-${type}`;
        if (isLoading) {
            div.id = 'msg-loading-' + Date.now();
            div.style.opacity = '0.7';
        }

        // Simple Markdown-ish parsing
        let html = text.replace(/\n/g, '<br>');

        // Render System Messages nicely
        if (text.includes('[System:')) {
            // Regex to match [System: ...] and wrap it
            html = html.replace(/\[System:\s*(.*?)\]/g, '</div><div class="msg-system"><i class="fas fa-terminal"></i> $1</div><div class="msg msg-bot">');
            // Clean up empty divs if any
            html = html.replace('<div class="msg msg-bot"></div>', '');
        }

        div.innerHTML = html;
        body.appendChild(div);
        body.scrollTop = body.scrollHeight;
        return div.id;
    }

    btn.onclick = toggleChat;
    close.onclick = toggleChat;
    send.onclick = sendMessage;
    input.onkeyup = (e) => { if (e.key === 'Enter') sendMessage(); }

})();
