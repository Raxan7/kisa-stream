// Minimal offline landing page. Never cache paid videos, playback tokens, API data or payments.
const VERSION = 'kisa-shell-v1';
const OFFLINE = '/offline.html';
self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(cache => cache.addAll([OFFLINE, '/icons/Icon-192.png'])));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key.startsWith('kisa-shell-') && key !== VERSION).map(key => caches.delete(key)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return;
  // Do not cache the authenticated Flutter app shell; show explicit offline page.
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE)));
});
