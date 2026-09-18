self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  // Network-first passthrough — this app needs live data (Groq/Gemini/OpenRouter/Supabase),
  // so we deliberately don't cache API responses. This handler's presence is what satisfies
  // browser PWA-installability checks and gives basic offline resilience for the app shell.
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
