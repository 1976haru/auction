/* docs/sw.js
   경매·공매 정적 대시보드 PWA 서비스 워커.
   - 앱 셸: cache-first
   - mock_dashboard.json: stale-while-revalidate (오프라인에서도 가장 최근 데이터 표시)
   - navigation 요청 오프라인 fallback: cached index.html
*/
"use strict";

const VERSION = "auction-pwa-v1";
const CACHE = "auction-shell-" + VERSION;

const SHELL_ASSETS = [
  "./",
  "./index.html",
  "./styles.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icons/icon.svg",
  "./data/mock_dashboard.json",
];

self.addEventListener("install", (e) => {
  e.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await Promise.all(SHELL_ASSETS.map(async (url) => {
      try { await cache.add(new Request(url, { cache: "reload" })); }
      catch (_) { /* 누락된 파일이 있어도 install 자체는 성공 */ }
    }));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter((k) => k.startsWith("auction-shell-") && k !== CACHE)
          .map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  // 다른 출처는 그대로 통과
  if (url.origin !== self.location.origin) return;

  // 데이터: stale-while-revalidate
  if (url.pathname.endsWith("/mock_dashboard.json")) {
    e.respondWith((async () => {
      const cache = await caches.open(CACHE);
      const cached = await cache.match(req);
      const network = fetch(req).then((res) => {
        if (res && res.ok) cache.put(req, res.clone());
        return res;
      }).catch(() => cached);
      return cached || network;
    })());
    return;
  }

  // 그 외: cache-first → network → navigation fallback
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(req);
    if (cached) return cached;
    try {
      const res = await fetch(req);
      if (res && res.ok) {
        cache.put(req, res.clone());
      }
      return res;
    } catch (err) {
      if (req.mode === "navigate") {
        const fallback = await cache.match("./index.html");
        if (fallback) return fallback;
      }
      throw err;
    }
  })());
});

/* 클라이언트에서 새 SW 적용 시 강제 활성화 */
self.addEventListener("message", (e) => {
  if (e.data === "SKIP_WAITING") self.skipWaiting();
});
