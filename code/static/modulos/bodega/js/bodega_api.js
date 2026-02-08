// bodega_api.js - API utilities for Bodega Module
(function () {
    window.BodegaAPI = {
        fetchApi: async function (endpoint, options = {}) {
            // Ensure endpoint starts with /api if not present, or use as is
            const url = endpoint.startsWith('http') ? endpoint : endpoint;

            const res = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                ...options,
                body: options.body ? JSON.stringify(options.body) : undefined
            });

            if (!res.ok) {
                let errDetail = `Error ${res.status}: ${res.statusText}`;
                try {
                    const err = await res.json();
                    if (err.detail) errDetail = err.detail;
                } catch (e) { }
                throw new Error(errDetail);
            }
            return res.json();
        }
    };

    // Global alias for compatibility with legacy code
    window.fetchApi = window.BodegaAPI.fetchApi;
    console.log("✅ BodegaAPI Loaded");
})();
