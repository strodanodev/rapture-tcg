/*
 * The service worker: what makes the game installable, and keeps it opening offline. ui/pwa.js registers it (https
 * only).
 *
 * Pages, the client modules, the engine and the game data go network first: a new deploy shows on the next launch,
 * and the cached copy is the offline fallback (audio/ too: a game may replace a sound under the same name). Files
 * under assets/ are named by version (a rebuilt arena ships as a new file), so they are served from the cache once
 * seen. Cross-origin requests (fonts, RPC, relay, wallet) are never touched.
 */
const VERSION = "tessaract-v1";
const ROOT = new URL("./", self.location).pathname;
const SHELL = ["./", "./manifest.webmanifest", "./favicon.svg"];
const IMMUTABLE = new RegExp(`^${ROOT}assets/`);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(VERSION).then((cache) => cache.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(ROOT)) return;

  if (req.mode === "navigate") {
    // every page is the one shell: the launch query (a replay link, a match) is kept, the cached root answers offline
    event.respondWith(fetch(req).then((res) => { put(ROOT, res.clone()); return res; }).catch(() => caches.match(ROOT)));
    return;
  }
  if (IMMUTABLE.test(url.pathname)) {
    event.respondWith(caches.match(req).then((hit) => hit ?? fetch(req).then((res) => { put(req, res.clone()); return res; })));
    return;
  }
  event.respondWith(fetch(req).then((res) => { put(req, res.clone()); return res; }).catch(() => caches.match(req)));
});

function put(key, res) {
  if (!res || !res.ok || res.type !== "basic") return;
  caches.open(VERSION).then((cache) => cache.put(key, res)).catch(() => {});
}
