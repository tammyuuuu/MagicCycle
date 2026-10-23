const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:560,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/mobile');
  const frame=page.frames().find(f=>f.url().includes('/preview/index.html'));
  await frame.waitForFunction(()=>!!window.XingxunWorkspace);
  for(const width of [320,375,390,430]){
   await page.locator('#size').selectOption({value:width+','+({320:740,375:812,390:844,430:932}[width])});
   for(const tab of ['today','plan','review','lab']){
    await page.locator('.tabs [data-page='+tab+']').click();
    assert.ok(await frame.locator(tab==='today'?'#page-today':'#invest-'+tab).isVisible());
    const measure=await frame.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,body:getComputedStyle(document.body).fontSize,caption:getComputedStyle(document.querySelector('.fine')||document.body).fontSize}));
    assert.equal(measure.width,width);assert.equal(measure.overflow,false,`${width} ${tab} horizontal overflow`);
    assert.equal(measure.body,'14px');assert.equal(measure.caption,'14px');
    if(tab==='plan'){
     const widths=await frame.evaluate(()=>['#assetTotal','#budgetRatio + .select-trigger','#ledgerStartDate'].map(id=>{const el=document.querySelector(id),r=el.getBoundingClientRect();return {left:r.left,width:r.width,height:r.height};}));
     for(const box of widths){assert.equal(box.width,widths[0].width);assert.equal(box.left,widths[0].left);assert.equal(box.height,48);}
    }
    if(width===375)await page.locator('#phone').screenshot({path:`maintenance/mobile_${tab}.png`});
   }
  }
  // Use an unsaved template clone to check wrapped labels without writing a ledger.
  await page.locator('.tabs [data-page=plan]').click();
  await frame.evaluate(()=>{const form=document.getElementById('buyFormTemplate').content.cloneNode(true);document.getElementById('invest-plan').prepend(form);});
  for(const width of [375,430]){
   await page.locator('#size').selectOption({value:width+','+({375:812,430:932}[width])});
   const boxes=await frame.locator('#invest-plan > .inline-buy .buy-fields').evaluate(el=>[...el.querySelectorAll('input,.select-trigger')].filter(e=>!e.closest('[hidden]')).map(e=>{const r=e.getBoundingClientRect();return {height:r.height,top:r.top,width:r.width};}));
   assert.equal(boxes.length,4);boxes.forEach(b=>assert.equal(b.height,48));
   assert.ok(boxes[0].top<boxes[1].top);assert.equal(boxes[2].top,boxes[3].top);
   assert.equal(boxes[0].width,boxes[1].width);assert.ok(boxes[0].width>boxes[2].width);
  }
  const trigger=frame.locator('#invest-plan > .inline-buy .select-trigger');
  await trigger.click();
  const menu=frame.locator('.select-menu:not([hidden])');
  await menu.getByRole('option',{name:'支付宝转入净额',exact:true}).click();
  assert.equal(await frame.locator('#invest-plan > .inline-buy #recordAmountBasis').inputValue(),'net_transfer_excluding_fee');
  await trigger.click();await trigger.press('Home');await trigger.press('Enter');
  assert.equal(await frame.locator('#invest-plan > .inline-buy #recordAmountBasis').inputValue(),'gross_including_subscription_fee');
  await trigger.click();await trigger.press('Escape');assert.equal(await trigger.getAttribute('aria-expanded'),'false');
  await page.locator('.tabs [data-page=lab]').click();
  await page.locator('#refresh').click();
  const refreshed=page.frames().find(f=>f.url().includes('/preview/index.html'));
  await refreshed.waitForFunction(()=>document.querySelector('#topnav a.active')?.dataset.page==='lab');
  assert.deepEqual(errors,[]);
  console.log('PASS: 4 pages at 320/375/390/430px, typography, navigation, refresh, no horizontal overflow or JS errors.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
