// Service Worker for Numislens PWA
const CACHE_NAME = 'numislens-v2';
const urlsToCache = [
  '/',
  '/index.html',
  '/styles/main.css',
  '/js/config.js',
  '/js/aiService.js',
  '/js/gradingSystem.js',
  '/js/valueEstimation.js',
  '/js/imageProcessor.js',
  '/js/app.js',
  '/manifest.json',
  '/icons/icon-72x72.png',
  '/icons/icon-96x96.png',
  '/icons/icon-128x128.png',
  '/icons/icon-144x144.png',
  '/icons/icon-152x152.png',
  '/icons/icon-192x192.png',
  '/icons/icon-384x384.png',
  '/icons/icon-512x512.png'
];

// Install event - cache resources
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
      .then(() => self.skipWaiting()) // Activate immediately
  );
});

// Fetch event - serve from cache or network with fallback strategy
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached version if available
        if (response) {
          return response;
        }

        // Else fetch from network
        return fetch(event.request).catch(() => {
          // If network fails and it's an HTML page, return the main page
          if (event.request.destination === 'document') {
            return caches.match('/');
          }
        });
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
    .then(() => {
      console.log('New service worker activated');
    })
  );
});

// Handle push notifications (if needed in future)
self.addEventListener('push', event => {
  console.log('Received a push notification');
  // Handle push notification here if implemented
});

// Handle background sync (if needed in future)
self.addEventListener('sync', event => {
  console.log('Background sync event received');
  // Handle background sync here if implemented
});