const task=await taskSpace('Verify NVDA mobile layout');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8768/index.html?nvda=4');
await page.evaluate(()=>document.querySelector('[data-category="stock"]').scrollIntoView({block:'nearest',inline:'center'}));
await page.click('loc=css:[data-category="stock"]');
await page.evaluate(()=>document.querySelector('[data-asset-symbol="NVDA"] > details > summary').scrollIntoView({block:'center'}));
await page.click('loc=css:[data-asset-symbol="NVDA"] > details > summary');
console.log(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 cards:[...document.querySelectorAll('#stockList > .card')].map(el=>({symbol:el.dataset.assetSymbol,width:el.getBoundingClientRect().width,text:el.innerText}))})));
await task.finish({keep:[]});
