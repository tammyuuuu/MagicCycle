/* Small first-screen router; public history loads only when a page needs it. */
(() => {
  const assets=window.XINGXUN_ASSETS,loads=new Map();let selected='today';
  for(const type of ['gesturestart','gesturechange','gestureend'])document.addEventListener(type,e=>e.preventDefault(),{passive:false});
  function script(url){
    if(!loads.has(url))loads.set(url,new Promise((resolve,reject)=>{
      const el=document.createElement('script');el.src=url;el.onload=resolve;
      el.onerror=()=>{el.remove();loads.delete(url);reject(Error('页面资源暂未加载，请联网后重试'));};document.head.append(el);
    }));return loads.get(url);
  }
  let workspace;
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
    const status=document.getElementById('workspaceStatus');status.textContent='正在加载…';
    try{const app=await load();if(selected!==name){show(selected);status.textContent='';return;}await app.navigate(name);}
    catch(error){status.textContent=error.message;}
  }
  document.querySelectorAll('#topnav a').forEach(a=>{
    a.setAttribute('role','button');a.tabIndex=0;
    a.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();navigate(a.dataset.page);},true);
    a.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();a.click();}});
  });
  window.XingxunAssets={research:()=>script(assets.research)};
  window.XingxunLoader={navigate,load,get selected(){return selected;}};
})();
