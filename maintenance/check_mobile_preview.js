const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:560,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8765/mobile');
  const frame=page.frames().find(f=>f.url().includes('/preview/index.html'));
  await frame.waitForFunction(()=>!!window.XingxunLoader||!!window.XingxunWorkspace);
  for(const width of [320,375,390,430]){
   await page.locator('#size').selectOption({value:width+','+({320:740,375:812,390:844,430:932}[width])});
   for(const tab of ['today','plan','review','lab']){
    await page.locator('.tabs [data-page='+tab+']').click();
    if(tab!=='today')await frame.waitForFunction(()=>!!window.XingxunWorkspace);
    if(tab==='lab')await frame.waitForFunction(()=>document.querySelectorAll('#labLegend button').length===10);
    assert.ok(await frame.locator(tab==='today'?'#page-today':'#invest-'+tab).isVisible());
    const measure=await frame.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth,body:getComputedStyle(document.body).fontSize,caption:getComputedStyle(document.querySelector('.fine')||document.body).fontSize}));
    assert.equal(measure.width,width);assert.equal(measure.overflow,false,`${width} ${tab} horizontal overflow`);
    if(tab==='today'){
     const header=await frame.locator('.site-header').evaluate(el=>{const s=getComputedStyle(el);return {height:el.getBoundingClientRect().height,background:s.backgroundImage,top:s.borderTopWidth,bottom:s.borderBottomWidth,before:getComputedStyle(el,'::before').content,after:getComputedStyle(el,'::after').content};});
     assert.equal(header.background,'none');assert.ok(!header.background.includes('url('));assert.equal(header.top,'0px');assert.equal(header.bottom,'0px');assert.equal(header.before,'none');assert.equal(header.after,'none');
     const previous=await frame.addStyleTag({content:'.site-header{padding:18px 16px 19px;border-top:1px solid transparent;border-bottom:1px solid transparent;}@media(max-width:350px){.site-header{padding:16px 12px;}}'});
     const oldHeight=await frame.locator('.site-header').evaluate(el=>el.getBoundingClientRect().height);await previous.evaluate(el=>el.remove());
     assert.ok(Math.abs(oldHeight-header.height-(width<=350?22:23))<.1,'Header compacted by 23px');
     await frame.locator('.site-header').evaluate(el=>el.style.setProperty('--header-safe-top','59px'));
     const safe=await frame.locator('.site-header').evaluate(el=>({height:el.getBoundingClientRect().height,iconTop:el.querySelector('.brand-emblem').getBoundingClientRect().top-el.getBoundingClientRect().top,color:getComputedStyle(el).backgroundColor,root:getComputedStyle(document.documentElement).backgroundColor}));
     assert.ok(Math.abs(safe.height-header.height-59)<.1);assert.ok(safe.iconTop>=59,'icon below Dynamic Island safe area');assert.equal(safe.color,'rgb(32, 46, 75)');assert.equal(safe.root,safe.color);
     await frame.locator('.site-header').evaluate(el=>el.style.removeProperty('--header-safe-top'));
     assert.equal(await frame.evaluate(()=>performance.getEntriesByType('resource').some(r=>r.name.includes('header-background.webp'))),false);
    }

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
