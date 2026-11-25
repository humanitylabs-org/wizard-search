/* Search's own service worker (fast open, issue #42, on for everyone). Scoped to Search's path only; registered by
 * app.js on every open.
 * The shell (page, styles, scripts, icon, and the shared /wizard-os-home/core/ scripts the page loads) is served
 * stale-while-revalidate: the saved copy paints at once, the network copy replaces it for the next open. Searches,
 * images, settings and every /api/ call stay network-only. The cache name carries the release (sw.js?v=<version>),
 * so a new Search release installs a new worker that drops the old copy. */
'use strict';
const VERSION = new URL(self.location.href).searchParams.get('v') || 'dev';
const PREFIX = 'wizard-search-shell-', CACHE = PREFIX + VERSION;
const BASE = new URL('./', self.location.href).pathname;
const CORE = '/wizard-os-home/core/';
const NETWORK_ONLY = /^(?:api\/|thumb\/|img\/|mcp$|sw\.js$|setup\.json$|openapi\.json$|SETUP\.md$)/;

const cacheable = r => !!r && r.ok && r.status === 200 && r.type === 'basic' && !r.redirected &&
  !/no-store/i.test(r.headers.get('cache-control') || '');

// Save every file a page names (versioned app.js?v=…, the shared app-client.js, the icon) that is not saved yet, so
// the open after this one paints from this device too. One file failing (a flaky tailnet) must not stop the rest.
async function warm(cache, html) {
  const urls = new Set(['icon.png', 'icon.svg', 'manifest.webmanifest'].map(p => new URL(BASE + p, self.location.href).href));
  for (const m of html.matchAll(/\b(?:src|href)="([^"#]+)"/g)) urls.add(new URL(m[1], self.location.origin + BASE).href);
  await Promise.all([...urls].map(async u => {
    const key = keyFor(new Request(u));
    if (!key || key === self.location.origin + BASE || await cache.match(key)) return;
    await fetch(u, { cache: 'no-cache' }).then(r => cacheable(r) && store(cache, key, r)).catch(() => {});
  }));
}

// A versioned file (app.js?v=…) replaces its older versions rather than piling up.
async function store(cache, key, response) {
  const u = new URL(key);
  if (u.searchParams.has('v')) for (const old of await cache.keys()) { const o = new URL(old.url); if (o.pathname === u.pathname && o.href !== u.href) await cache.delete(old); }
  await cache.put(key, response);
}

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    const page = await fetch(BASE, { cache: 'no-cache' }).catch(() => null);
    if (cacheable(page)) { const html = await page.clone().text(); await cache.put(self.location.origin + BASE, page); await warm(cache, html); }
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => event.waitUntil((async () => {
  // Own prefix only: never touch the shell's or another app's caches on this origin.
  for (const name of await caches.keys()) if (name.startsWith(PREFIX) && name !== CACHE) await caches.delete(name);
  await self.clients.claim();
})()));

function keyFor(request) {
  const u = new URL(request.url);
  if (u.origin !== self.location.origin) return null;
  if (u.pathname.startsWith(CORE)) return /\.(?:js|css)$/.test(u.pathname) ? u.href : null;
  if (!u.pathname.startsWith(BASE)) return null;
  const rest = u.pathname.slice(BASE.length);
  if (NETWORK_ONLY.test(rest)) return null;
  // Every page open (?q=…, ?tab=…, index.html) is the one Search page.
  if (rest === '' || rest === 'index.html') return self.location.origin + BASE;
  return request.mode === 'navigate' ? null : /\.(?:js|css|png|svg|webmanifest)$/.test(rest) ? u.href : null;
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET' || request.headers.has('range')) return;
  const key = keyFor(request);
  if (!key) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const saved = await cache.match(key);
    const fresh = fetch(request).then(r => {
      if (cacheable(r)) {
        const page = key === self.location.origin + BASE, copy = r.clone(), text = page ? r.clone().text() : null;
        // A new page (a release) brings its new files along now, not on the open after.
        event.waitUntil(store(cache, key, copy).then(() => text && text.then(html => warm(cache, html))).catch(() => {}));
      }
      return r;
    });
    if (saved) { event.waitUntil(fresh.catch(() => {})); return saved; }
    return fresh;
  })());
});
