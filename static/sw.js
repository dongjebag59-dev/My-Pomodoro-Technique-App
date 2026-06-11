const CACHE_NAME = 'toti-v1';
const STATIC_ASSETS = [
  '/timer',
  '/static/tomatodoll.png',
  '/static/toti-logo.png',
  '/static/tomato.png',
  '/static/manifest.json',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Network-first for API calls, cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/timer/api') ||
      url.pathname.startsWith('/users') ||
      url.pathname.startsWith('/stats') ||
      url.pathname.startsWith('/sessions') ||
      url.pathname.startsWith('/ai_service')) {
    event.respondWith(fetch(event.request));
    return;
  }

  event.respondWith(
    caches.match(event.request).then(cached => cached || fetch(event.request))
  );
});

// Push notification handler
self.addEventListener('push', event => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || '토티', {
      body: data.body || '',
      icon: '/static/tomato.png',
      badge: '/static/tomato.png',
    })
  );
});

// ===== 타이머 백그라운드 알림 =====

let timerInterval = null;
let timerState = null; // { phase, remaining, focusTime, breakTime }

self.addEventListener('message', event => {
  const { type, payload } = event.data || {};

  if (type === 'TIMER_START') {
    timerState = { ...payload };
    clearInterval(timerInterval);
    timerInterval = setInterval(_tick, 1000);

  } else if (type === 'TIMER_STOP' || type === 'TIMER_PAUSE') {
    clearInterval(timerInterval);
    timerInterval = null;
    if (type === 'TIMER_STOP') timerState = null;

  } else if (type === 'TIMER_RESUME') {
    if (timerState) {
      timerState = { ...timerState, ...payload };
      clearInterval(timerInterval);
      timerInterval = setInterval(_tick, 1000);
    }

  } else if (type === 'TIMER_SYNC') {
    if (timerState) timerState = { ...timerState, ...payload };
  }
});

function _tick() {
  if (!timerState) return;
  timerState.remaining--;

  if (timerState.remaining <= 0) {
    const wasPhase = timerState.phase;
    if (wasPhase === 'focus') {
      _notify('집중 완료!', `휴식을 시작하세요 (${timerState.breakTime}분)`);
      timerState.phase = 'break';
      timerState.remaining = timerState.breakTime * 60;
    } else {
      _notify('휴식 종료!', `다음 집중 세션을 시작하세요 (${timerState.focusTime}분)`);
      timerState.phase = 'focus';
      timerState.remaining = timerState.focusTime * 60;
    }
    _broadcastPhaseChange(timerState.phase);
  }
}

function _notify(title, body) {
  self.registration.showNotification(title, {
    body,
    icon: '/static/tomato.png',
    badge: '/static/tomato.png',
    tag: 'toti-timer',
    renotify: true,
  });
}

function _broadcastPhaseChange(phase) {
  self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
    clients.forEach(c => c.postMessage({ type: 'PHASE_CHANGE', phase }));
  });
}

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clients => {
      const focused = clients.find(c => c.focused);
      if (focused) return focused.focus();
      const open = clients.find(c => c.url.includes('/timer'));
      if (open) return open.focus();
      return self.clients.openWindow('/timer');
    })
  );
});
