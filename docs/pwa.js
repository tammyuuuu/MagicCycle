(() => {
  'use strict';
  const header = document.querySelector('header');
  const warning = document.createElement('div');
  warning.setAttribute('role', 'status');
  warning.setAttribute('aria-live', 'polite');
  warning.style.cssText = 'padding:8px 16px;background:#f8f0de;color:#85632e;font-size:12px';
  const offlineCopy = Boolean(window.__magicCycleOffline);
  const showStatus = () => {
    const offline = offlineCopy || !navigator.onLine;
    warning.textContent = offline ? '离线内容，请以页面生成时间为准。' : '';
    if (offline && header && !warning.isConnected) header.after(warning);
    if (!offline) warning.remove();
  };
  showStatus();
  window.addEventListener('online', showStatus);
  window.addEventListener('offline', showStatus);
  if ('serviceWorker' in navigator && window.isSecureContext) {
    navigator.serviceWorker.register('./sw.js', { updateViaCache: 'none' })
      .then(registration => {
        // A newer worker is used on the next navigation, without interrupting edits.
        registration.update().catch(() => {});
        document.addEventListener('visibilitychange', () => {
          if (document.visibilityState === 'visible') registration.update().catch(() => {});
        });
      })
      .catch(() => {});
  }
})();
