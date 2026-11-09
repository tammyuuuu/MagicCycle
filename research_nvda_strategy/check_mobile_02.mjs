const task=await taskSpace('Review NVDA stock page');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8768/index.html?nvda=2');
await page.click('loc=css:[data-category="stock"]');
await page.evaluate(()=>document.querySelector('[data-asset-symbol="NVDA"] > details > summary').scrollIntoView({block:'center'}));
await page.click('loc=css:[data-asset-symbol="NVDA"] > details > summary');
console.log(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 cards:[...document.querySelectorAll('#stockList > .card')].map(el=>({symbol:el.dataset.assetSymbol,text:el.innerText}))})));
console.log(await page.screenshot({path:'D:/file/fun/code/cycle/research_nvda_strategy/mobile.png'}));
await task.finish({keep:[]});
