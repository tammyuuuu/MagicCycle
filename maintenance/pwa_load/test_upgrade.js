const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const http=require('http'),fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve('docs'),fixtures=path.resolve('maintenance/pwa_load');
const legacy='db9659fba53c63fa5ba7d19242761e57988ada08';
const prior=Object.fromEntries(['index.html','sw.js','pwa.js'].map(name=>[name,require('child_process').execFileSync('git',['show',legacy+':docs/'+name],{maxBuffer:20000000})]));
(async()=>{
 let release='old',failResearch=false;const requests=[];
 const manifest=JSON.parse(fs.readFileSync(root+'/pwa-manifest.json'));
 const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://localhost').pathname;
  if(pathname==='/blank'){res.setHeader('Content-Type','text/html');return res.end('<!doctype html>fixture');}
  if(!pathname.startsWith('/cycle/')){res.writeHead(404);return res.end();}
  const name=pathname.slice(7)||'index.html';requests.push(name);
  if(failResearch&&name==='pwa.js'){res.writeHead(503);return res.end();}
  let file=path.join(root,name);
  if(release==='old'&&prior[name]){res.setHeader('Content-Type',name.endsWith('.html')?'text/html; charset=utf-8':'application/javascript');return res.end(prior[name]);}
  if(!file.startsWith(root+path.sep)&&!file.startsWith(fixtures+path.sep)||!fs.existsSync(file)){res.writeHead(404);return res.end();}
  let data=fs.readFileSync(file);
  if(release==='second'){
   if(name==='sw.js')data=Buffer.from(data.toString().replace(manifest.version,manifest.version+'-second'));
   if(name==='pwa-manifest.json'){const html=fs.readFileSync(root+'/index.html','utf8').replace('</head>','<meta name="fixture-release" content="second"></head>');data=Buffer.from(JSON.stringify({...manifest,version:manifest.version+'-second',hashes:{...manifest.hashes,'index.html':require('crypto').createHash('sha256').update(html).digest('hex')}}));}
   if(name==='index.html')data=Buffer.from(data.toString().replace('</head>','<meta name="fixture-release" content="second"></head>'));
  }
  res.setHeader('Cache-Control','no-store');res.setHeader('Content-Type',name.endsWith('.js')?'application/javascript':name.endsWith('.html')?'text/html; charset=utf-8':name.endsWith('.json')?'application/json':name.endsWith('.webmanifest')?'application/manifest+json':'application/octet-stream');res.end(data);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const origin='http://127.0.0.1:'+server.address().port,url=origin+'/cycle/index.html';
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const ctx=await browser.newContext({viewport:{width:375,height:812},isMobile:true,hasTouch:true});const page=await ctx.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.waitForFunction(()=>!!window.XingxunWorkspace);
  await page.evaluate(async()=>{await navigator.serviceWorker.register('./sw.js');await navigator.serviceWorker.ready;});
  await page.waitForFunction(()=>!!navigator.serviceWorker.controller);
  const saved=await page.evaluate(()=>{
   const S=window.XingxunStore;S.initializeLedger({date:'2026-07-01',cash:1000,positions:[]});
   S.saveJournal([{id:'upgrade-trade',mode:'real',accountId:'strategy',date:'2026-07-06',submittedDate:'2026-07-06',confirmedDate:'2026-07-06',code:'008701',action:'买入',status:'confirmed',amount:80.16,quantity:40.055,fee:.05,source:'manual_executed_buy',amountInputBasis:'gross_including_subscription_fee'}]);
   const p=S.profile();p.ratio=.05;p.researchSelection='L1';S.saveProfile(p);
   localStorage.setItem('valuationYears','10');localStorage.setItem('unrelated-user-setting','keep-me');
   return Object.fromEntries(Object.keys(localStorage).map(k=>[k,localStorage.getItem(k)]));
  });
  release='current';await page.reload();await page.waitForSelector('#pwaRefresh',{timeout:30000});
  assert.equal(await page.evaluate(()=>!!window.XingxunWorkspace),false,'account module must not initialize on today');
  assert.equal(await page.evaluate(()=>window.WORKSPACE_DATA.research.strategies.some(s=>s.runs)),false,'history must not parse on today');
  await Promise.all([page.waitForNavigation(),page.locator('#pwaRefresh').click()]);
  assert.deepEqual(await page.evaluate(()=>Object.fromEntries(Object.keys(localStorage).map(k=>[k,localStorage.getItem(k)]))),saved);
  await page.waitForFunction(()=>!!window.XingxunLoader);
  assert.equal(await page.locator('#page-today').isVisible(),true);
  await ctx.setOffline(true);await page.reload();await page.waitForFunction(()=>!!window.XingxunLoader);
  for(const tab of ['plan','review','lab','today']){
   await page.locator('#topnav a[data-page='+tab+']').tap();
   if(tab==='plan')await page.waitForFunction(()=>!!window.XingxunWorkspace);
   if(tab==='lab')await page.waitForFunction(()=>document.querySelectorAll('#labLegend button').length===10);
   assert.equal(await page.locator(tab==='today'?'#page-today':'#invest-'+tab).isVisible(),true);
  }
  assert.equal(await page.evaluate(()=>window.XingxunStore.journal().length),1);
  assert.equal(await page.evaluate(()=>window.XingxunStore.profile().ratio),.05);
  await ctx.setOffline(false);
  // Failed offline precache cannot activate a broken release or erase current data.
  const historyDownloads=requests.filter(name=>name.includes('research.')).length;
  release='second';failResearch=true;
  await page.evaluate(async()=>{try{await (await navigator.serviceWorker.getRegistration()).update();}catch{}});
  await page.waitForFunction(async()=>!(await navigator.serviceWorker.getRegistration()).installing);
  assert.equal(await page.evaluate(async()=>!!(await navigator.serviceWorker.getRegistration()).waiting),false);
  assert.equal(await page.locator('meta[name="fixture-release"]').count(),0);
  failResearch=false;
  await page.evaluate(async()=>{await (await navigator.serviceWorker.getRegistration()).update();});
  await page.waitForSelector('#pwaRefresh',{timeout:30000});
  assert.equal(await page.locator('meta[name="fixture-release"]').count(),0,'update must wait for consent');
  await page.locator('#topnav a[data-page=plan]').tap();await page.locator('#assetTotal').fill('123456');
  page.once('dialog',dialog=>dialog.dismiss());await page.locator('#pwaRefresh').click();
  assert.equal(await page.locator('#assetTotal').inputValue(),'123456');
  page.once('dialog',dialog=>dialog.accept());await Promise.all([page.waitForNavigation(),page.locator('#pwaRefresh').click()]);
  assert.equal(await page.locator('meta[name="fixture-release"]').getAttribute('content'),'second');
  assert.equal(requests.filter(name=>name.includes('research.')).length,historyDownloads,'unchanged research must reuse the prior offline cache');
  assert.deepEqual(await page.evaluate(()=>Object.fromEntries(Object.keys(localStorage).map(k=>[k,localStorage.getItem(k)]))),saved);
  const starts=Date.now();await ctx.setOffline(true);await page.reload();assert.ok(Date.now()-starts<3000,'cached launch must not wait 8s for network');
  assert.deepEqual(errors,[]);
  console.log('PASS: real legacy v50 -> split shell -> next release; waiting/update prompt, failed install rollback, dirty-form cancel, local ledger/settings/confirmed trade retained byte-for-byte, all four pages offline, subpath hosting, fast offline reopen.');
  fs.writeFileSync(fixtures+'/upgrade_results.json',JSON.stringify({passed:true,legacy:'v50',release:manifest.version,localStorageKeys:Object.keys(saved),offlineAllPages:true,failedInstallRetainsOld:true},null,2));
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
