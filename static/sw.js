// SmartBrief Service Worker - 오프라인에서 저장된 분석 결과 확인 지원
const CACHE_NAME = 'smartbrief-v1';

// 설치 시 캐시할 URL (앱 진입점)
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/js/main.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(urlsToCache).catch((err) => {
        console.warn('[SW] 일부 리소스 캐시 실패:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys
        .filter((k) => k !== CACHE_NAME)
        .map((k) => caches.delete(k))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // 네트워크 요청만 처리 (다른 origin 제외)
  if (!event.request.url.startsWith(self.location.origin)) return;

  const url = new URL(event.request.url);
  // API, POST, 업로드 경로는 SW가 개입하지 않음 (Safari/iOS에서 form→upload 시 로딩 무한 방지)
  if (event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/save_html') || url.pathname.startsWith('/upload')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // HTML 페이지와 정적 리소스만 캐시
        const isHtml = response.headers.get('content-type')?.includes('text/html');
        const isStatic = url.pathname.startsWith('/static/');
        if ((isHtml || isStatic) && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => {
        // 오프라인: 캐시에서 반환
        return caches.match(event.request).then((cached) => {
          if (cached) return cached;
          // 메인 페이지 요청인데 캐시 없으면 index 대체 페이지
          if (event.request.mode === 'navigate') {
            return caches.match('/').then((indexCache) => indexCache || new Response(
              '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>SmartBrief - 오프라인</title></head><body><div style="padding:20px;font-family:sans-serif"><h1>오프라인 모드</h1><p>인터넷 연결을 확인해주세요.</p><p>저장된 분석 결과가 있다면, 온라인 상태에서 앱을 한 번 열어주시면 오프라인에서도 확인할 수 있습니다.</p></div></body></html>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
            ));
          }
          return new Response('', { status: 503, statusText: 'Service Unavailable' });
        });
      })
  );
});
