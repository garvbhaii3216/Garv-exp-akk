const CACHE_NAME = 'expense-tracker-v4';
const ASSETS_TO_CACHE = [
  '/',
  '/static/index.html',
  '/static/tailwind.min.css',
  '/static/styles.css',
  '/static/lucide.min.js',
  '/static/chart.umd.min.js',
  '/static/app.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/favicon.png',
  '/static/apple-touch-icon.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keyList) => {
      return Promise.all(
        keyList.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Cache-First strategy for instant UI load (bypasses Render spin-up delays)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // API endpoints: network with offline fallback for GET categories/summary
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          // Cache successful GET responses for categories
          if (event.request.method === 'GET' && url.pathname.includes('/categories')) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(async () => {
          // If offline and request is cached
          const cached = await caches.match(event.request);
          if (cached) return cached;
          return new Response(JSON.stringify({ detail: 'Offline mode active', offline: true }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          });
        })
    );
    return;
  }

  // Navigation requests (HTML shell): Stale-While-Revalidate / Cache-First for 0ms startup
  if (event.request.mode === 'navigate' || url.pathname === '/') {
    event.respondWith(
      caches.match('/static/index.html').then((cached) => {
        const fetchPromise = fetch(event.request).then((networkRes) => {
          if (networkRes && networkRes.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put('/static/index.html', networkRes.clone()));
          }
          return networkRes;
        }).catch(() => cached);

        return cached || fetchPromise;
      })
    );
    return;
  }

  // Static Assets: Cache-First with background update
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) {
        // Fetch in background to keep cache fresh
        fetch(event.request).then((networkRes) => {
          if (networkRes && networkRes.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, networkRes));
          }
        }).catch(() => {});
        return cached;
      }
      return fetch(event.request).then((networkRes) => {
        if (networkRes && networkRes.status === 200) {
          const clone = networkRes.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return networkRes;
      });
    })
  );
});
