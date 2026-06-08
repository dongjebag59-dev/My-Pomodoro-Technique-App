const CACHE_NAME = 'toti-v1';
const STATIC_ASSETS = [
  '/timer',
  '/static/tomatodoll.png',
  '/static/toti-logo.png',
  '/static/tomato.png',
  '/static/manifest.json',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for API calls, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/timer/api') ||
      url.pathname.startsWith('/users') ||
      url.pathname.startsWith('/stats') ||
      url.pathname.startsWith('/sessions') ||
      url.pathname.startsWith('/ai_service')) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});

// Push notification handler
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || '토티', {
      body: data.body || '',
      icon: '/static/tomato.png',
      badge: '/static/tomato.png',
    })
  );
});
