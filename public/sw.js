const CACHE_NAME = 'numislens-v3';

const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/styles/main.css',
  '/manifest.json',
  '/js/app.js',
  '/js/api.js',
  '/js/router.js',
  '/js/views/settings.js',
  '/js/views/inventory.js',
  '/js/views/coin.js',
  '/icons/icon-192x192.png',
  '/icons/icon-512x512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name !== CACHE_NAME)
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  );
});

function isNavigationRequest(request) {
  return (
    request.mode === 'navigate' ||
    (request.method === 'GET' &&
      request.headers.get('accept')?.includes('text/html'))
  );
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  if (request.method !== 'GET') {
    return;
  }

  const url = new URL(request.url);

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  event.respondWith(
    (async () => {
      const cached = await caches.match(request);
      if (cached) {
        return cached;
      }

      try {
        const response = await fetch(request);
        if (response.ok && response.type !== 'opaque') {
          const cache = await caches.open(CACHE_NAME);
          await cache.put(request, response.clone());
        }
        return response;
      } catch {
        if (isNavigationRequest(request)) {
          const fallback = await caches.match('/');
          if (fallback) {
            return fallback;
          }
        }
        throw new Error('Network unavailable');
      }
    })()
  );
});
