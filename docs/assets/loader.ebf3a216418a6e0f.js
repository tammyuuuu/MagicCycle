window.XINGXUN_ASSETS={"data":"./assets/account-data.639caac26fd68b1c.js","runtime":"./assets/workspace.0019f96e93a1394e.js","research":"./assets/research.21b35e3f4edf4768.js","lab":"./assets/strategy-lab.ce0453b14cb203b2.js"};
/* Small first-screen router; public history loads only when a page needs it. */
(() => {
  const assets=window.XINGXUN_ASSETS,loads=new Map();let selected='today';
  for(const type of ['gesturestart','gesturechange','gestureend'])document.addEventListener(type,e=>e.preventDefault(),{passive:false});
  function script(url){
    if(!loads.has(url))loads.set(url,new Promise((resolve,reject)=>{
      const el=document.createElement('script');el.src=url;
      const fail=message=>{clearTimeout(timer);el.onload=el.onerror=null;el.remove();loads.delete(url);reject(Error(message));};
      const timer=setTimeout(()=>fail('页面资源加载超时，请检查网络后重试'),20000);
      el.onload=()=>{clearTimeout(timer);resolve();};
      el.onerror=()=>fail('页面资源暂未加载，请联网后重试');document.head.append(el);
    }));return loads.get(url);
  }
  let workspace;
  let labPromise,labReady=false,labAttempts=0;
  function loadLab(){
    if(labReady)return Promise.resolve();
    if(!labPromise)labPromise=(async()=>{
      if(labAttempts++>0)loads.delete(assets.research);
      await Promise.all([script(assets.lab),script(assets.research)]);
      for(const s of window.WORKSPACE_DATA.research.strategies)Object.assign(s,window.XINGXUN_RESEARCH_RUNS?.[s.id]||{});
      if(!window.StrategyLab.ready)window.StrategyLab.init(window.WORKSPACE_DATA);
      if(!window.StrategyLab.ready)throw Error('历史数据包没有可用曲线，请重新加载');
      labReady=true;
    })().catch(error=>{labPromise=null;throw error;});
    return labPromise;
  }
  function load(){
    if(!workspace)workspace=script(assets.data).then(()=>script(assets.runtime)).then(()=>{
      if(!window.XingxunWorkspace)throw Error(document.getElementById('workspaceStatus').textContent||'账户初始化失败');
      window.renderPurchaseMonitor?.();return window.XingxunWorkspace;
    }).catch(error=>{workspace=null;throw error;});return workspace;
  }
  function show(name){
    document.body.classList.remove('scorecard-capture');
    for(const id of ['plan','review','lab'])document.getElementById('invest-'+id)?.classList.toggle('hidden',id!==name);
    document.getElementById('page-today')?.classList.toggle('hidden',name!=='today');
    document.querySelectorAll('#topnav a').forEach(a=>{const active=a.dataset.page===name;a.classList.toggle('active',active);a.setAttribute('aria-current',active?'page':'false');});
  }
  async function navigate(name){
    if(!['today','plan','review','lab'].includes(name))return;selected=name;show(name);
    if(name==='today'){if(window.XingxunWorkspace)window.XingxunWorkspace.navigate(name);return;}
    if(name==='lab'){
      const status=document.getElementById('workspaceStatus'),note=document.getElementById('labRangeNote');
      if(labReady){status.textContent='';if(window.XingxunWorkspace)await window.XingxunWorkspace.navigate(name);return;}
      status.textContent='正在加载历史数据…';note.textContent='正在读取历史数据，请稍候…';
      try{await loadLab();if(selected===name){status.textContent='';if(window.XingxunWorkspace)await window.XingxunWorkspace.navigate(name);}}
      catch(error){if(selected!==name)return;status.textContent=error.message;note.innerHTML='<span>历史数据暂未加载。</span> <button class="btn gray" type="button" data-retry-research>重新加载</button>';note.querySelector('button').onclick=()=>navigate(name);}
      return;
    }
    const status=document.getElementById('workspaceStatus');status.textContent='正在加载…';
    try{const app=await load();if(selected!==name){show(selected);status.textContent='';return;}const ok=await app.navigate(name);if(ok===false)return;}
    catch(error){status.textContent=error.message;}
  }
  document.querySelectorAll('#topnav a').forEach(a=>{
    a.setAttribute('role','button');a.tabIndex=0;
    a.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();navigate(a.dataset.page);},true);
    a.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();a.click();}});
  });
  window.XingxunAssets={research:({retry=false}={})=>{if(retry)loads.delete(assets.research);return Promise.all([script(assets.lab),script(assets.research)]);}};
  // Reopening an app clears JS memory, but not its public resource cache. Warm
  // only already-cached history during idle time; never fetch private accounts.
  function warmCachedLab(){
    if(labReady||labPromise||document.visibilityState==='hidden'||!window.caches)return;
    try{if(!navigator.serviceWorker?.controller)return;}catch{return;}
    const warm=async()=>{try{const hit=await caches.match(new URL(assets.research,location.href).href);if(hit)await loadLab();}catch{}};
    if(window.requestIdleCallback)requestIdleCallback(warm,{timeout:2500});else setTimeout(warm,300);
  }
  window.addEventListener('load',warmCachedLab);
  try{navigator.serviceWorker?.addEventListener('controllerchange',warmCachedLab);navigator.serviceWorker?.ready.then(warmCachedLab).catch(()=>{});}catch{}
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')warmCachedLab();});
  window.XingxunLoader={navigate,load,get selected(){return selected;},get labReady(){return labReady;}};
})();
