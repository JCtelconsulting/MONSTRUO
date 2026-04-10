// bodega_ai.js - AI Logic (Rules, Suggestions, Auto-Pilot)
(function () {
    window.BodegaAI = {
        // --- BULK ACTION STATE ---
        selectedCases: new Set(),

        // --- PUBLIC METHODS ---
        toggleCaseSelection: function (id, checked) {
            if (checked) this.selectedCases.add(id);
            else this.selectedCases.delete(id);

            // UI Update is delegated to UI module
            if (window.BodegaUI) window.BodegaUI.updateBulkUI(this.selectedCases.size);
        },

        clearBulkSelection: function () {
            this.selectedCases.clear();
            // UI Clear
            document.querySelectorAll('.case-checkbox').forEach(c => c.checked = false);
            if (window.BodegaUI) window.BodegaUI.updateBulkUI(0);
        },

        processBulkInstructions: async function (isAuto = false) {
            const input = document.getElementById('bulk-instruction');
            let instruction = input ? input.value.trim() : "";
            const ids = Array.from(this.selectedCases);

            if (isAuto) {
                instruction = 'AUTO_PILOT';
            } else {
                if (!instruction) return alert("Escribe una instrucción.");
            }

            if (ids.length === 0) return;

            const btn = document.querySelector('#bulk-action-bar button.btn-primary');
            const originalText = btn ? btn.innerHTML : "Procesar";
            if (btn) {
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';
                btn.disabled = true;
            }

            try {
                const res = await window.fetchApi('/api/catalogo/resolver_duplicado_masivo', {
                    method: 'POST',
                    body: { case_ids: ids, instruction: instruction }
                });

                // Show result
                let msg = `Procesados ${res.processed} casos.\n`;
                if (res.details) {
                    res.details.forEach(d => {
                        if (d.status === 'ok') msg += `✅ Caso ${d.case_id}: ${d.actions.length} acciones.\n`;
                        else msg += `❌ Caso ${d.case_id}: ${d.message}\n`;
                    });
                }
                alert(msg);

                // Reload via Core
                this.clearBulkSelection();
                if (window.BodegaCore) window.BodegaCore.loadPending();

            } catch (e) {
                alert("Error: " + e.message);
            } finally {
                if (btn) {
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                }
            }
        },

        // --- SINGLE ITEM AI ---
        recommendCatAI: async function (itemId, divId) {
            const div = document.getElementById(divId);
            if (!div) return;
            div.innerHTML = '<i class="fas fa-magic fa-spin"></i> Pensando...';

            try {
                const res = await window.fetchApi('/api/catalogo/sugerir_categoria', {
                    method: 'POST', body: { item_id: itemId }
                });

                div.innerHTML = '';
                if (!res.sugerencias || res.sugerencias.length === 0) {
                    div.innerHTML = '<small>No hay sugerencias claras.</small>';
                    return;
                }

                res.sugerencias.forEach(sug => {
                    const btn = document.createElement('button');
                    btn.className = 'btn-secondary btn-sm';
                    btn.style = 'margin:2px; font-size:0.8em; text-align:left;';
                    btn.innerHTML = `<strong>${(sug.confidence * 100).toFixed(0)}%</strong> ${sug.ruta.join(' > ')}`;
                    btn.onclick = () => window.BodegaCore.applyCat(itemId, sug.categoria_id, 'ai');
                    div.appendChild(btn);
                });

            } catch (e) {
                div.innerHTML = `<span style="color:red">Error IA: ${e.message}</span>`;
            }
        },

        teachAIDuplicate: async function (caseId) {
            const input = document.getElementById('teach-dup-' + caseId);
            if (!input || !input.value.trim()) return alert("Escribe algo para enseñar.");

            const btn = document.querySelector(`button[onclick*="teachAIDuplicate(${caseId})"]`);
            if (btn) btn.disabled = true;

            try {
                // Here we reuse the bulk endpoint or simple resolve, BUT ideally we should have a teach endpoint.
                // For now, we simulate teaching by sending a instruction that resolves as IGNORE or KEEP based on text,
                // but effectively we are using the bulk resolver logic for single case.
                const res = await window.fetchApi('/api/catalogo/resolver_duplicado_instruccion', {
                    method: 'POST',
                    body: { case_id: caseId, instruction: input.value.trim() }
                });

                alert("IA Entrenada: " + (res.message || "OK"));
                if (window.BodegaCore) window.BodegaCore.loadPending();

            } catch (e) {
                alert("Error: " + e.message);
            } finally {
                if (btn) btn.disabled = false;
            }
        }
    };
    console.log("✅ BodegaAI Loaded");
})();
