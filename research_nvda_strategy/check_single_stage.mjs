const task=await taskSpace('Review NVDA holding card');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8770/index.html?single=1');
await page.evaluate(()=>document.querySelector('[data-category="stock"]').scrollIntoView({block:'nearest',inline:'center'}));
await page.click('loc=css:[data-category="stock"]');
await page.evaluate(()=>document.querySelector('[data-asset-symbol="NVDA"] > details > summary').scrollIntoView({block:'center'}));
await page.click('loc=css:[data-asset-symbol="NVDA"] > details > summary');
console.log(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 nvda:document.querySelector('[data-asset-symbol="NVDA"]').innerText,
 stages:document.querySelectorAll('[data-asset-symbol="NVDA"] .state-step').length,
 msft:!!document.querySelector('[data-asset-symbol="MSFT"]')})));
await task.finish({keep:[]});
