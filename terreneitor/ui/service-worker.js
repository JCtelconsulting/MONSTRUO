// ==========================================================================
// SERVICE WORKER DESACTIVADO (auto-destructor) — dev
// El SW cacheaba assets y causaba cruce dev/prod + loops. Este script borra
// todas las cachés y se desregistra solo. No intercepta fetch (todo va a la red).
// ==========================================================================
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((k) => caches.delete(k)));
      } catch (e) {}
      try {
        await self.registration.unregister();
      } catch (e) {}
    })()
  );
});
