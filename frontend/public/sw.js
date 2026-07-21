/// <reference lib="webworker" />

const CACHE_NAME = "vision-rag-v1";

// 앱 셸 — 오프라인에서도 최소한 화면이 뜨도록 캐싱
const APP_SHELL = [
  "/",
  "/icon-192x192.png",
  "/icon-512x512.png",
  "/manifest.json",
];

// install: 앱 셸 캐싱
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

// activate: 오래된 캐시 정리
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// fetch: 네트워크 우선, 실패 시 캐시 폴백 (stale-while-revalidate)
self.addEventListener("fetch", (event) => {
  const { request } = event;

  // API 요청은 캐싱하지 않음
  if (request.url.includes("/api/") || request.url.includes("/chat/") || request.url.includes("/upload/")) {
    return;
  }

  // GET 요청만 캐싱
  if (request.method !== "GET") return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        // 정상 응답이면 캐시에 저장
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => {
        // 네트워크 실패 → 캐시에서 가져오기
        return caches.match(request).then((cached) => cached || new Response("Offline", { status: 503 }));
      })
  );
});
