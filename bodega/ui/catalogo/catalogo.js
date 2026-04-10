// Catalogo - lógica específica (si aplica)
if (!window.buildCatalogAI) {
    window.buildCatalogAI = function () {
        const msg = 'Catálogo IA en desarrollo. Usa reglas manuales por ahora.';
        if (window.showToast) {
            window.showToast(msg, 'info');
            return;
        }
        alert(msg);
    };
}
console.log('Catalogo tab loaded');
