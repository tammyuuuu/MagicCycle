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
async function capture(page,label){await page.evaluate(()=>{document.activeElement?.blur();window.scrollTo(0,0);});await noOverflow(page,label);await page.evaluate(()=>{document.getElementById('workspaceStatus').textContent='';window.scrollTo(0,0);});await page.screenshot({path:path.join(out,label+'.png'),fullPage:true});await page.evaluate(()=>{document.getElementById('workspaceStatus').textContent='';window.scrollTo(0,0);});await page.screenshot({path:path.join(out,label+'_viewport.png')});}

async function customPurchase(browser,kind,width){
 const {ctx,page,errors}=await make(browser,kind,width);await nav(page,'plan');
 await page.locator('#candidateSelect').selectOption('L1');await page.locator('#assetSnapshotForm button').click();
 await page.locator('#customBuyCode').selectOption('008701');await page.locator('#customBuyAmount').fill('500');await page.locator('#customBuyForm button').click();
 assert.deepEqual(await page.evaluate(()=>({cash:XingxunStore.profile().poolCash,frozen:XingxunStore.profile().frozenCash,entries:XingxunStore.journal().length,drafts:XingxunStore.profile().purchaseDrafts.length})),{cash:2000,frozen:0,entries:0,drafts:1});
 await page.reload();await nav(page,'plan');assert.equal(await page.locator('[data-use-draft]').count(),1);
 await page.locator('[data-use-draft]').click();await page.locator('#customBuyForm button').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),1500);assert.equal(await page.evaluate(()=>XingxunStore.profile().frozenCash),500);assert.equal(await page.evaluate(()=>XingxunStore.profile().positions.length),0);
 assert.equal(await page.locator('[data-use-draft]').count(),0);assert.equal(await page.evaluate(()=>XingxunStore.journal()[0].amount),500);
 await page.locator('[data-confirm]').click();await page.locator('#quickQuantity').fill('250');await page.locator('#quickTradeDialog details > summary').click();await page.locator('#quickFee').fill('0');await page.locator('#quickSave').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().positions[0].shares),250);
 assert.equal(await page.locator('#invest-review #advancedManagement,#invest-review #pendingOrders,#invest-review #tradeForm').count(),0);
 // A new public NAV refresh changes account P/L while the historical research series stays untouched.
 const day=await page.evaluate(()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai'}).format(new Date()));
 await page.route('**/account_nav.json',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({schema:'xingxun-account-nav-v1',funds:{'008701':{nav:[[day,2.1]]}},errors:{}})}));
 await page.route('**/api/account-nav',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({schema:'xingxun-account-nav-v1',funds:{'008701':{nav:[[day,2.1]]}},errors:{}})}));
 const original=await page.evaluate(()=>JSON.stringify(WORKSPACE_DATA.funds['008701'].nav));
 await nav(page,'review');await page.locator('#refreshReview').click();await page.waitForFunction(()=>Math.abs(XingxunWorkspace.report.summary?.cumulativePnl-25)<.001);
 assert.equal(await page.evaluate(()=>JSON.stringify(WORKSPACE_DATA.funds['008701'].nav)),original);
 assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),1500);
 assert.deepEqual(errors,[]);await noOverflow(page,'custom purchase review');await ctx.close();console.log('PASS custom purchase',kind,width);
}
async function simple(browser,kind,width){
 const {ctx,page,errors}=await make(browser,kind,width);await nav(page,'plan');
 assert.equal(await page.locator('#advancedManagement').getAttribute('open'),null);
 assert.equal(await page.locator('#invest-plan #actualPositions, #invest-plan #advancedManagement, #invest-plan #accountMetrics').count(),0);
 assert.equal(await page.locator('#tradeDate').isVisible(),false);
 assert.equal(await page.locator('#candidateSelect option').count(),10);
 await page.locator('#candidateSelect').selectOption('L1');await page.locator('#assetSnapshotForm button').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().opening.cash),2000);
 assert.equal(await page.evaluate(()=>XingxunStore.profile().positions.length),0);
 assert.equal(await page.locator('#assetSetup').isVisible(),false);
 await page.evaluate(()=>{document.getElementById('workspaceStatus').textContent='';window.scrollTo(0,0);});await page.screenshot({path:path.join(out,`simple_${kind}_${width}.png`),fullPage:true});
 await noOverflow(page,'simple plan');
 await page.locator('#planReference').evaluate(el=>el.open=true);await page.locator('[data-plan]').first().click();assert.equal(await page.locator('#quickQuantity').isVisible(),false);await page.locator('#quickSave').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().frozenCash),1000);
 assert.equal(await page.evaluate(()=>XingxunStore.profile().positions.length),0);
 assert.equal(await page.locator('[data-plan]').count(),1); // Other fund can proceed, same fund cannot duplicate.
 await nav(page,'plan');await page.locator('[data-confirm]').first().click();await page.locator('#quickQuantity').fill('824.01');await page.locator('#quickSave').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().frozenCash),0);
 assert.equal(await page.evaluate(()=>XingxunStore.profile().positions[0].shares),824.01);
 await page.reload();await nav(page,'plan');assert.equal(await page.locator('#candidateSelect').inputValue(),'L1');
 assert.equal(await page.evaluate(()=>XingxunStore.profile().opening.cash),2000); // Reload never initializes twice.
 // Independent existing-account fixture verifies the redemption path through actual cash receipt.
 await page.evaluate(()=>{localStorage.clear();XingxunStore.initializeLedger({date:'2026-10-01',cash:0,positions:[{code:'000015',name:'债券',shares:1600,cost:1900}]});XingxunStore.addSnapshot('2026-10-01',20000);XingxunWorkspace.renderAccount();});
 await page.locator('#candidateSelect').selectOption('L1');await page.locator('#planReference').evaluate(el=>el.open=true);await page.locator('[data-plan]').first().click();await page.locator('#quickSave').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),0);
 await nav(page,'plan');await page.locator('[data-confirm]').click();await page.locator('#quickAmount').fill('900');await page.locator('#quickSave').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().receivable),900);assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),0);
 await page.locator('[data-settle]').click();await page.locator('#quickAmount').fill('895');await page.locator('#quickSave').click();
 assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),895);assert.equal(await page.evaluate(()=>XingxunStore.profile().receivable),0);
 assert.equal(await page.locator('[data-settle]').count(),0);
 await page.evaluate(()=>XingxunWorkspace.renderAccount());assert.equal(await page.evaluate(()=>XingxunStore.profile().poolCash),895);
 assert.deepEqual(errors,[]);await noOverflow(page,'after lifecycle');await ctx.close();console.log('PASS simple',kind,width);
}
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{for(const kind of ['flask','static','official'])for(const width of [1440,375]){await customPurchase(browser,kind,width);await simple(browser,kind,width);}}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
