/* Bump this version when changing the offline shell or caching behavior. */
const CACHE = 'magiccycle-pwa-v43-mobile-navigation';
const ROOT = new URL('./', self.location.href);
const PAGE = new URL('index.html', ROOT).href;
const SHELL = ['index.html', 'pwa.js', 'manifest.webmanifest',
  'icons/apple-touch-icon.png', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/favicon-32.png'];
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cache.addAll(SHELL.map(path => new Request(new URL(path, ROOT), { cache: 'reload' })));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('magiccycle-pwa-') && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
async function networkFirst(request, navigation) {
  const cache = await caches.open(CACHE);
  const key = navigation ? PAGE : request;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(request, { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    await cache.put(key, response.clone());
    return response;
  } catch (error) {
    const stored = await cache.match(key);
    if (!stored) {
      if (!navigation) return Response.error();
      return new Response('<!doctype html><meta charset="utf-8"><p>暂时无法连接网站，请联网后重试。</p>', {
        status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' }
      });
    }
    if (!navigation) return stored;
    // Mark the actual cached response, including when navigator.onLine is misleading.
    const html = (await stored.text()).replace('</head>',
      '<script>window.__magicCycleOffline=true;</script></head>');
    return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  } finally {
    clearTimeout(timer);
  }
}
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== ROOT.origin || !url.pathname.startsWith(ROOT.pathname)) return;
  const navigation = request.mode === 'navigate' &&
    (url.pathname === ROOT.pathname || url.pathname === new URL(PAGE).pathname);
  const asset = SHELL.some(path => url.pathname === new URL(path, ROOT).pathname);
  if (navigation || asset) event.respondWith(networkFirst(request, navigation));
});
