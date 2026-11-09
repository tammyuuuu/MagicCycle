const task=await taskSpace('Review NVDA entry monitor');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8769/index.html?entry=1');
await page.evaluate(()=>document.querySelector('[data-category="stock"]').scrollIntoView({block:'nearest',inline:'center'}));
await page.click('loc=css:[data-category="stock"]');
console.log('current',await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 cards:[...document.querySelectorAll('#stockList > .card')].map(el=>({symbol:el.dataset.assetSymbol,text:el.innerText}))})));
console.log('after',await page.evaluate(()=>{const card=document.querySelector('[data-asset-symbol="NVDA"]');Date.now=()=>Number(card.dataset.nvdaDeadline)+1000;window.expireNvdaCards();return card.innerText;}));
await task.finish({keep:[]});
