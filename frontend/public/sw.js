const STATIC_CACHE = "turfbari-static-v1";
const OFFLINE_PAGE = "/offline.html";
const STATIC_CACHE_LIMIT = 100;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.add(OFFLINE_PAGE)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key.startsWith("turfbari-static-") && key !== STATIC_CACHE).map((key) => caches.delete(key)))),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/") || url.pathname.startsWith("/media/")) return;

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(async () => (await caches.match(OFFLINE_PAGE)) || Response.error()));
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          void caches.open(STATIC_CACHE).then(async (cache) => {
            await cache.put(request, copy);
            const keys = await cache.keys();
            await Promise.all(keys.slice(0, Math.max(0, keys.length - STATIC_CACHE_LIMIT - 1)).map((key) => cache.delete(key)));
          });
        }
        return response;
      })),
    );
  }
});
