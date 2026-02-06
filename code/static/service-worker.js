const CACHE_NAME = 'terreneitor-v2';
const ASSETS_TO_CACHE = [
    '/modulos/login/login.html',
    '/modulos/login/css/login.css',
    '/modulos/login/js/login.js',
    '/modulos/dashboard/inicio.html',
    '/modulos/_compartido/css/monstruo.css',
    '/modulos/_compartido/js/utilidades.js',
    '/modulos/_compartido/js/admin.js',
    '/modulos/_compartido/js/sidebar.js',
    '/modulos/_compartido/js/offline-store.js',
    '/manifest.json',
    'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css'
];

self.addEventListener('install', (event) => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                return cache.addAll(ASSETS_TO_CACHE);
            })
    );
});

self.addEventListener('fetch', (event) => {
    // Only cache GET requests
    if (event.request.method !== 'GET') return;

    event.respondWith(
        caches.match(event.request)
            .then((response) => {
                // Cache Hit - return response
                if (response) {
                    return response;
                }
                return fetch(event.request);
            })
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});
