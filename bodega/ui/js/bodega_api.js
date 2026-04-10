// bodega_api.js - API utilities for Bodega Module
(function () {
    // We already have a global fetchApi in utilidades.js
    // We just maintain the BodegaAPI namespace for compatibility
    window.BodegaAPI = {
        fetchApi: async function (endpoint, options = {}) {
            return window.fetchApi(endpoint, options);
        }
    };

    console.log("✅ BodegaAPI Loaded (Mapped to global fetchApi)");
})();
