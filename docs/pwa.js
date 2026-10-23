(() => {
 'use strict';
 const header=document.querySelector('header'),warning=document.createElement('div');
 warning.setAttribute('role','status');warning.setAttribute('aria-live','polite');
 warning.style.cssText='padding:8px 16px;background:#f8f0de;color:#85632e;font-size:14px';
 function showStatus(){warning.textContent=!navigator.onLine?'离线内容，请以页面更新时间为准。':'';if(warning.textContent&&header&&!warning.isConnected)header.after(warning);if(!warning.textContent)warning.remove();}
 showStatus();window.addEventListener('online',showStatus);window.addEventListener('offline',showStatus);
 if(!('serviceWorker' in navigator)||!window.isSecureContext)return;
 const hadController=!!navigator.serviceWorker.controller;let requested=false,dirty=false,registration,banner,reloading=false;
 document.addEventListener('input',e=>{if(e.target.matches('input,select,textarea'))dirty=true;});
 document.addEventListener('submit',()=>{dirty=false;});
 function promptUpdate(force=false){
  if((!registration?.waiting&&!force)||banner)return;
  banner=document.createElement('div');banner.id='pwaUpdate';banner.setAttribute('role','status');
  banner.style.cssText='position:fixed;z-index:2400;left:50%;transform:translateX(-50%);bottom:calc(84px + env(safe-area-inset-bottom,0px));width:min(432px,calc(100% - 24px));padding:12px 14px;border:1px solid #dbc18b;border-radius:10px;background:#fffefa;color:#293344;font-size:14px;box-shadow:0 4px 18px #202e4b22';
  const text=document.createElement('span');text.textContent='新版本已就绪，保存填写后刷新。';
  const button=document.createElement('button');button.type='button';button.id='pwaRefresh';button.className='btn';button.textContent='刷新更新';button.style.cssText='margin:8px 0 0;display:block';
  button.onclick=()=>{if(dirty&&!window.confirm('当前可能有未保存的填写内容，仍要刷新吗？'))return;if(!registration.waiting){location.reload();return;}requested=true;button.disabled=true;button.textContent='正在更新…';registration.waiting.postMessage({type:'ACTIVATE_UPDATE'});};
  banner.append(text,button);document.body.append(banner);
 }
 navigator.serviceWorker.addEventListener('controllerchange',()=>{
  if(requested&&!reloading){reloading=true;location.reload();}
  else if(hadController&&!banner){promptUpdate(true);}
 });
 async function check(){if(!navigator.onLine||!registration)return;try{await registration.update();promptUpdate();}catch{}}
 async function start(){
  try{
   registration=await navigator.serviceWorker.register('./sw.js',{updateViaCache:'none'});promptUpdate();
   registration.addEventListener('updatefound',()=>{const worker=registration.installing;worker?.addEventListener('statechange',()=>{if(worker.state==='installed')promptUpdate();});});
   await check();
   document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')check();});
   window.addEventListener('online',check);window.addEventListener('pageshow',check);
   setInterval(()=>{if(document.visibilityState==='visible')check();},60000);
  }catch{}
 }
 if('requestIdleCallback' in window)requestIdleCallback(start,{timeout:2500});else setTimeout(start,500);
})();
