const task=await taskSpace('Review Apple observation card');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8772/index.html?apple=1');
await page.evaluate(()=>document.querySelector('[data-category="stock"]').scrollIntoView({block:'nearest',inline:'center'}));
await page.click('loc=css:[data-category="stock"]');
await page.evaluate(()=>document.querySelector('[data-asset-symbol="AAPL"] > details > summary').scrollIntoView({block:'center'}));
await page.click('loc=css:[data-asset-symbol="AAPL"] > details > summary');
console.log(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 symbols:[...document.querySelectorAll('#stockList > .card')].map(el=>el.dataset.assetSymbol),
 card:document.querySelector('[data-asset-symbol="AAPL"]').innerText,
 stages:document.querySelectorAll('[data-asset-symbol="AAPL"] .state-step').length})));
await task.finish({keep:[]});
