const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=__dirname,root=path.resolve(out,'..'),manifest=JSON.parse(fs.readFileSync(path.join(root,'workspace_data/manifest.json'),'utf8')),data=JSON.parse(fs.readFileSync(path.join(root,'workspace_data',manifest.current),'utf8'));
const snapshot=JSON.parse(fs.readFileSync(path.join(out,'state_fixture.json'),'utf8'));
const reports=[];
async function make(browser,kind,width){
 const ctx=await browser.newContext({viewport:{width,height:900},locale:'zh-CN',timezoneId:'Asia/Shanghai',acceptDownloads:true});
 await ctx.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.hostname!=='xingxun.local.test')return route.abort();
  if(u.pathname==='/api/state')return route.fulfill({contentType:'application/json',body:JSON.stringify(snapshot)});
  if(u.pathname==='/api/alerts')return route.fulfill({contentType:'application/json',body:fs.readFileSync(path.join(out,'alerts_fixture.json'),'utf8')});
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync((kind==='official'?path.join(root,'docs/index.html'):path.join(out,kind+'_preview.html')),'utf8')});
  return route.fulfill({status:404,body:''});
 });
 const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('https://xingxun.local.test/',{waitUntil:'load'});await page.locator('#normalStrategies .strategy').first().waitFor({state:'attached'});
 return {ctx,page,errors};
}
async function nav(page,name){await page.locator(`#topnav a[data-${await page.locator('#topnav a').first().getAttribute('data-t')?'t':'page'}="${name}"]`).click();}
async function noOverflow(page,label){const d=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));assert.ok(d.scroll<=d.width,`${label} body overflow ${JSON.stringify(d)}`);}
async function capture(page,label){await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});await noOverflow(page,label);await page.screenshot({path:path.join(out,label+'.png'),fullPage:true});await page.screenshot({path:path.join(out,label+'_viewport.png')});}

const results=[];
async function checkResearch(browser,kind,width){
 const {ctx,page,errors}=await make(browser,kind,width),tag=`def_${kind}_${width}`;
 await nav(page,'today');await page.locator('#usPurchaseMonitor').waitFor();
 assert.ok(await page.locator('.today-categories').evaluate(el=>!!(el.compareDocumentPosition(document.getElementById('usPurchaseMonitor'))&Node.DOCUMENT_POSITION_FOLLOWING)), 'US monitor follows ETF signals');
 const tabs=page.locator('.today-categories .guide-tabs');assert.equal(await tabs.locator('button').count(),4);
 assert.equal(await tabs.locator('button[aria-pressed="true"]').evaluate(el=>getComputedStyle(el).backgroundColor),'rgb(247, 238, 219)');
 await tabs.locator('[data-category="macro"]').click();assert.equal(await page.locator('#today-category-macro').isVisible(),true);
 await tabs.locator('[data-category="broad"]').click();await noOverflow(page,'ETF tabs');

 assert.equal(await page.locator('#invest-plan #usPurchaseMonitor').count(),0);
 assert.equal(await page.locator('#usPurchaseMonitor .monitor-groups>div').count(),2);
 assert.equal(await page.locator('#usPurchaseMonitor .monitor-row').count(),7);
 assert.equal(await page.locator('#usPurchaseMonitor .status-label').filter({hasText:'符合模拟计划'}).count(),0);
 assert.ok((await page.locator('#usPurchaseMonitor').innerText()).includes('021000'));
 await noOverflow(page,'monitor');await page.screenshot({path:path.join(out,tag+'_today.png'),fullPage:false});
 await nav(page,'plan');await page.locator('#candidateSelect').selectOption('D');await nav(page,'today');assert.match(await page.locator('#usPurchaseMonitor').innerText(),/当前研究策略 D/);
 await nav(page,'lab');assert.equal(await page.locator('#normalStrategies .strategy').count(),6);assert.equal(await page.locator('#limitedStrategies .strategy').count(),4);
 await page.locator('#comparePair').selectOption('A:D');assert.equal(await page.locator('#compareA').inputValue(),'A');assert.equal(await page.locator('#compareB').inputValue(),'D');assert.equal(await page.locator('#researchCurve path').count(),2);
 const r=data.research.strategies.find(s=>s.id==='D').runs.find(r=>r.segment==='main'&&r.mode==='rebalance');assert.ok((await page.locator('#comparisonMetrics').innerText()).includes((r.cagr*100).toFixed(2)+'%'));
 await page.locator('#normalStrategies .strategy').nth(3).screenshot({path:path.join(out,tag+'_D_card.png')});
 await page.locator('#compareSegment').selectOption('real_2019');assert.match(await page.locator('#comparisonMetrics').innerText(),/数据不足.*008701/);assert.equal(await page.locator('#researchCurve path').count(),0);assert.equal(await page.locator('#researchDrawdown path').count(),0);assert.match(await page.locator('#normalStrategies').innerText(),/数据不足/);
 await page.locator('#compareSegment').selectOption('proxy_2013');assert.match(await page.locator('#comparisonNote').innerText(),/指数代理研究/);assert.equal(await page.locator('#researchCurve path').count(),2);assert.match(await page.locator('#normalStrategies').innerText(),/000216/);
 await noOverflow(page,'proxy interval');
 await page.locator('#compareSegment').selectOption('real_2020');assert.match(await page.locator('#comparisonNote').innerText(),/真实基金/);assert.match(await page.locator('#comparisonMetrics').innerText(),/2020-07-16/);
 await page.locator('#comparePair').selectOption('B:E');assert.equal(await page.locator('#compareB').inputValue(),'E');await page.locator('#comparePair').selectOption('C:F');assert.equal(await page.locator('#compareB').inputValue(),'F');
 await page.locator('#compareMode').selectOption('buy_hold');assert.match(await page.locator('#normalStrategies').innerText(),/同权重简单持有/);
 await page.locator('#compareSegment').selectOption('main');await page.locator('#compareMode').selectOption('rebalance');await page.locator('#comparePair').selectOption('A:D');
 await page.locator('#comparisonMetrics').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,tag+'_comparison.png'),fullPage:false});
 assert.deepEqual(errors,[]);await noOverflow(page,'lab');results.push({kind,width,monitorGroups:2,monitorRows:7,strategies:10,pairedComparisons:true,missingHistoryClearsCurves:true,proxyAndActualSeparated:true,errors});await ctx.close();console.log('PASS',tag);
}
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{for(const kind of ['flask','static','official'])for(const width of [1440,375])await checkResearch(browser,kind,width);fs.writeFileSync(path.join(out,'def_browser_results.json'),JSON.stringify(results,null,2));}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
