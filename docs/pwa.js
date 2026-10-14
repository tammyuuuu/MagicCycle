(() => {
  'use strict';
  const bar = document.createElement('div');
  bar.style.cssText = 'display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:10px 24px;background:#edf0f1;color:#46576b;font-size:13px';
  bar.innerHTML = '<span role="status" aria-live="polite"></span><button type="button" class="btn gray">刷新页面</button><button type="button" class="btn gray" hidden>安装应用</button>';
  const header = document.querySelector('header');
  if (!header) return;
  header.after(bar);
  const status = bar.querySelector('span');
  const [refresh, install] = bar.querySelectorAll('button');
  const offlineCopy = Boolean(window.__magicCycleOffline);
  const showStatus = () => {
    status.textContent = offlineCopy
      ? '正在显示离线缓存，请以页面生成时间为准。联网后点击刷新获取已发布版本。'
      : navigator.onLine
        ? '请以页面生成时间为准；刷新可获取网站已发布的最新版本。'
        : '网络已断开，当前内容可能过期，请以页面生成时间为准。';
  };
  showStatus();
  window.addEventListener('online', showStatus);
  window.addEventListener('offline', showStatus);
  refresh.addEventListener('click', () => window.location.reload());
  let installPrompt;
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    installPrompt = event;
    install.hidden = false;
  });
  install.addEventListener('click', async () => {
    if (!installPrompt) return;
    await installPrompt.prompt();
    installPrompt = null;
    install.hidden = true;
  });
  window.addEventListener('appinstalled', () => { install.hidden = true; });
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
