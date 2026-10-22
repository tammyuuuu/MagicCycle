const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve(__dirname,'../workspace_ui_20261022'),root=path.resolve(out,'..'),manifest=JSON.parse(fs.readFileSync(path.join(root,'workspace_data/manifest.json'),'utf8')),data=JSON.parse(fs.readFileSync(path.join(root,'workspace_data',manifest.current),'utf8'));
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
async function capture(page,label){await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});await noOverflow(page,label);await page.screenshot({path:path.join(__dirname,label+'.png'),fullPage:true});await page.screenshot({path:path.join(__dirname,label+'_viewport.png')});}
async function check(browser,kind,width){
 const {ctx,page,errors}=await make(browser,kind,width),tag=kind+'_'+width;
 assert.equal(await page.locator('#topnav a').count(),4);assert.equal(await page.locator('#diaryForm').count(),0);assert.equal(await page.locator('.strategy').count(),10);
 await nav(page,'lab');assert.equal(await page.locator('#limitedStrategies .strategy').count(),4);
 assert.equal(await page.locator('#limitedStrategies').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),1);
 await page.locator('#compareScenario').selectOption('nasdaq_unavailable');await page.locator('#compareA').selectOption('L3');await page.locator('#compareB').selectOption('L4');assert.ok((await page.locator('#comparisonMetrics').innerText()).includes('L4'));await page.locator('#compareScenario').selectOption('nasdaq_available');await nav(page,'plan');
 await nav(page,'today');await capture(page,tag+'_today');
 await nav(page,'plan');assert.equal(await page.evaluate(()=>XingxunStore.profile().positions.length),0);
 await page.locator('#assetTotal').fill('20000');await page.locator('#assetSnapshotForm button').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().opening.cash),2000);assert.equal(await page.locator('#assetSetup').isVisible(),false);
 // Existing ledger fixture starts earlier; onboarding above independently verified the new path.
 await page.evaluate(()=>{localStorage.clear();XingxunStore.addSnapshot('2026-10-01',20000);XingxunStore.initializeLedger({date:'2026-10-01',cash:2000,positions:[]});XingxunWorkspace.renderAccount();});
 await nav(page,'plan');await page.locator('#openAccountManage').click();await page.locator('#advancedManagement > summary').click();await page.locator('#advancedTrade > summary').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),2000);
 await page.locator('#tradeDate').fill('2026-10-09');await page.locator('#tradeAmount').fill('1000');await page.locator('#tradeCode').selectOption('000015');await page.locator('#tradeForm button[type=submit]').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().positions.length),0);assert.equal(await page.evaluate(()=>XingxunStore.profile().frozenCash),1000);
 await page.locator('#closeAccountManage').click();await nav(page,'plan');await page.locator('#pendingOrders button[data-edit]').click();
 const price=data.funds['000015'].nav.find(p=>p[0]==='2026-10-09')[1],q=Number((999.2/price).toFixed(4));
 await page.locator('#tradeState').selectOption('confirmed');await page.locator('#tradeConfirmDate').fill('2026-10-12');await page.locator('#tradeQuantity').fill(String(q));await page.locator('#tradeFee').fill('.8');await page.locator('#tradeForm button[type=submit]').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().positions[0]?.shares),q);
 await page.locator('#updateAssets').click();await page.locator('#assetSetup details > summary').click();await page.locator('#assetDate').fill('2026-10-20');await page.locator('#assetTotal').fill('30000');await page.locator('#assetSnapshotForm button').click();
 await page.locator('#openAccountManage').click();await page.locator('#flowDate').fill('2026-10-20');await page.locator('#flowAmount').fill('100');await page.locator('#flowForm button').click();
 await page.locator('#closeAccountManage').click();await nav(page,'plan');await capture(page,tag+'_plan');await nav(page,'review');await page.locator('#reviewEnd').fill('2026-10-21');
 let actual=await page.evaluate(()=>XingxunWorkspace.report),last=data.funds['000015'].nav.find(p=>p[0]==='2026-10-21')[1];
 assert.ok(actual.ready,actual.reason);assert.ok(Math.abs(actual.summary.cumulativePnl-(q*last-1000))<1e-7);assert.equal(actual.months[0].netFlow,100);assert.equal(actual.summary.fees,.8);
 await capture(page,tag+'_review');
 await nav(page,'plan');await page.locator('#openAccountManage').click();await page.locator('#tradeDate').fill('2026-10-15');await page.locator('#tradeCode').selectOption('000015');await page.locator('#tradeSide').selectOption('卖出');await page.locator('#tradeState').selectOption('confirmed');await page.locator('#tradeAmount').fill('400');await page.locator('#tradeQuantity').fill('300');await page.locator('#tradeFee').fill('.5');await page.locator('#tradeConfirmDate').fill('2026-10-16');await page.locator('#tradeForm button[type=submit]').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().receivable),400);assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),1100);
 await page.locator('#closeAccountManage').click();await page.locator('[data-settle]').click();await page.locator('#quickTradeDialog details > summary').click();await page.locator('#quickDate').fill('2026-10-19');await page.locator('#quickSave').click();assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),1500);assert.equal(await page.evaluate(()=>XingxunStore.profile().receivable),0);
 await nav(page,'review');await page.locator('#reviewEnd').fill('2026-10-21');
 actual=await page.evaluate(()=>XingxunWorkspace.report);assert.ok(Math.abs(actual.summary.cumulativePnl-(1500+(q-300)*last-2100))<1e-7);assert.equal(actual.summary.fees,1.3);
 const downloadPromise=page.waitForEvent('download');await page.locator('#exportAccount').click();const download=await downloadPromise,backup=path.join(out,tag+'_backup.json');await download.saveAs(backup);
 const expected=await page.evaluate(()=>({cash:XingxunStore.profile().poolCash,shares:XingxunStore.profile().positions[0].shares,receivable:XingxunStore.profile().receivable}));
 await nav(page,'lab');await page.locator('#compareScenario').selectOption('nasdaq_unavailable');assert.equal(await page.locator('#compareA').inputValue(),'L1');assert.equal(await page.locator('#compareB').inputValue(),'L2');
 await page.locator('#compareScenario').selectOption('cross');await page.locator('#compareA').selectOption('A');await page.locator('#compareB').selectOption('L1');assert.match(await page.locator('#comparisonNote').textContent(),/跨限购情景/);
 await page.locator('#compareSegment').selectOption('long_proxy');assert.match(await page.locator('#comparisonMetrics').textContent(),/2017-07-03/);await capture(page,tag+'_lab');
 await page.locator('#compareScenario').selectOption('nasdaq_available');await page.locator('#compareA').selectOption('A');await page.locator('#compareB').selectOption('A');await page.locator('#compareMode').selectOption('vs_hold');assert.match(await page.locator('#comparisonMetrics').textContent(),/再平衡/);assert.match(await page.locator('#comparisonMetrics').textContent(),/持有/);
 const restored=await make(browser,kind,width);await nav(restored.page,'review');await restored.page.locator('#importAccount').setInputFiles(backup);await restored.page.locator('#workspaceStatus').filter({hasText:'完整账本已恢复。'}).waitFor();
 assert.deepEqual(await restored.page.evaluate(()=>({cash:XingxunStore.profile().poolCash,shares:XingxunStore.profile().positions[0].shares,receivable:XingxunStore.profile().receivable})),expected);
 await noOverflow(restored.page,tag+'_restored');assert.deepEqual(errors,[]);assert.deepEqual(restored.errors,[]);
 reports.push({kind,width,errors:[],pages:4,bodyOverflow:false,subscription:true,redemption:true,settlement:true,flowSeparated:true,navPnl:true,jsonRestore:true,scenarioCompare:true});
 await ctx.close();await restored.ctx.close();console.log('PASS',tag);
}
(async()=>{const downloadsPath=path.join(out,'downloads');fs.mkdirSync(downloadsPath,{recursive:true});const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,downloadsPath});try{for(const kind of ['flask','static','official'])for(const width of [1440,375,320])await check(browser,kind,width);fs.writeFileSync(path.join(out,'browser_results.json'),JSON.stringify(reports,null,2));}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
