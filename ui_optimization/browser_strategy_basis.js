const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../docs'),expected=JSON.parse(fs.readFileSync(path.join(root,'index.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 for(const width of [1440,375,320]){
  const page=await browser.newPage({viewport:{width,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{const u=new URL(r.request().url()),file=path.join(root,u.pathname==='/'?'index.html':u.pathname);return fs.existsSync(file)&&fs.statSync(file).isFile()?r.fulfill({path:file}):r.fulfill({status:404,body:''});});
  await page.goto('http://strategy.test/');await page.locator('[data-asset-symbol="510500"]').waitFor();
  for(const group of ['broad','us','industry','macro','bond']){
   await page.locator(`[data-category="${group}"]`).click();
   const cards=page.locator(`#today-category-${group} [data-asset-symbol]`);
   for(let i=0;i<await cards.count();i++){
    const card=cards.nth(i),code=await card.getAttribute('data-asset-symbol');await card.locator('details > summary').first().click();
    assert.equal(await card.locator('.strategy-summary').count(),1,code);
    assert.equal(await card.locator('.strategy-stats > div').count(),2,code);
    assert.equal(await card.locator('.strategy-summary .strategy-method, .strategy-summary .strategy-note').count(),0,code);
    const s=expected.find(x=>x.symbol===code);if(s){const info=s.details.strategy_presentation;assert.ok((await card.locator('.strategy-stats').innerText()).includes(info.backtest.annual_pct.toFixed(2)+'%'));assert.ok((await card.locator('.strategy-period').innerText()).includes(info.backtest.start));}
   }
  }
  await page.locator('[data-category="broad"]').click();
  for(const years of [3,10,5,3,5]){
   await page.evaluate(y=>window.changeValuationYears(String(y)),years);
   for(const code of ['510300','510500']){
   const card=page.locator(`[data-asset-symbol="${code}"]`);assert.equal(await card.locator('.strategy-summary').count(),1);
   const details=expected.find(x=>x.symbol===code).details;
   const bt=(code==='510500'?details.strategy_presentation:details.strategy_options[String(years)].strategy_presentation).backtest;
   if(code==='510500')assert.ok((await card.locator('.strategy-name').innerText()).includes('PE/PB固定5年'));
   if(code==='510500'){
    assert.equal(await card.locator('.state-step').count(),5);
    assert.equal(await card.locator('.state-step.is-current').count(),1);
    assert.equal(await card.locator('.state-step.is-current').innerText(),'退出');
   }
   const numbers=await card.locator('.strategy-stats dd').allTextContents();
   assert.deepEqual(numbers,[bt.annual_pct.toFixed(2)+'%',bt.max_drawdown_pct.toFixed(2)+'%']);
   assert.ok((await card.locator('.strategy-period').innerText()).includes(bt.start));
   assert.ok((await card.locator('.strategy-period').innerText()).includes(bt.end));
   }
  }
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow');assert.deepEqual(errors,[]);
  await page.locator('[data-asset-symbol="510500"]').screenshot({path:path.join(__dirname,`strategy_basis_${width}.png`)});await page.close();console.log('PASS strategy identity, metrics, repeat year switch and layout',width);
 }
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
