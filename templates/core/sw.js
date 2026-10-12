/* Service worker — served by Django at /sw.js. Version {{ version }}. */
"use strict";

const VERSION = "app-{{ version }}";
const STATIC_CACHE = VERSION + "-static";
const OFFLINE_URL = "{{ offline_url }}";
const PRECACHE = {{ precache }};
const STATIC_PREFIX = "{{ static_prefix }}";
const DEV_MODE = {{ dev_mode }};

// Never cached: auth, admin, API data, exports/PDFs, media (personal or financial data).
const NEVER_CACHE = [/^\/accounts\//, /^\/django-admin\//, /^\/platform\//, /\/api\//, /\/files\//, /^\/media-public\//, /[?&]export=/, /\.pdf$/, /\/export\//, /\/download\//];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE.some((re) => re.test(url.pathname + url.search))) return;

  // Static files: cache first (network first in development, where names are not hashed).
  if (url.pathname.startsWith(STATIC_PREFIX) && DEV_MODE) {
    event.respondWith(fetch(request).catch(() => caches.match(request)));
    return;
  }
  if (url.pathname.startsWith(STATIC_PREFIX)) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(STATIC_CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      }))
    );
    return;
  }

  // Pages and HTMX requests: network first; navigations fall back to the offline page.
  // Pages are not stored because they contain personal/financial data.
  const isNavigation = request.mode === "navigate";
  event.respondWith(
    fetch(request).catch(() => {
      if (isNavigation) return caches.match(OFFLINE_URL);
      return new Response("", { status: 503, statusText: "Offline" });
    })
  );
});

// Web push (phase 7 sends these). Shows a notification and opens its URL when tapped.
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = { title: "{{ app_name|escapejs }}", body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "{{ app_name|escapejs }}", {
    body: data.body || "",
    icon: STATIC_PREFIX + "pwa/icon-192.png",
    badge: STATIC_PREFIX + "pwa/icon-96.png",
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.matchAll({ type: "window" }).then((wins) => {
    for (const win of wins) { if ("focus" in win) { win.navigate(target); return win.focus(); } }
    return self.clients.openWindow(target);
  }));
});
