/* 2049 - offline support.
 * The page itself is always fetched fresh first (so a new version shows up
 * at once) and the cached copy is only the fallback when offline. Static
 * files are served from the cache and refreshed in the background. */
"use strict";
const CACHE = "2049-v0.18.1";
const SHELL = ["./", "index.html", "brain2049.js?v=0.18.1", "avatar.png", "icon_64.png",
               "icon_256.png", "icon_512.png", "manifest.webmanifest"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const isPage = req.mode === "navigate" || url.pathname.endsWith("/") || url.pathname.endsWith(".html");
  if (isPage) {
    // network first: always the latest version when online
    e.respondWith(fetch(req).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
      return res;
    }).catch(() => caches.match(req).then(r => r || caches.match("index.html"))));
    return;
  }
  const sameOrigin = url.origin === self.location.origin;
  const font = url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com";
  if (!sameOrigin && !font) return;
  // cache first, refreshed in the background
  e.respondWith(caches.open(CACHE).then(c => c.match(req).then(hit => {
    const net = fetch(req).then(res => {
      if (res.ok || res.type === "opaque") c.put(req, res.clone());
      return res;
    }).catch(() => hit);
    return hit || net;
  })));
});
