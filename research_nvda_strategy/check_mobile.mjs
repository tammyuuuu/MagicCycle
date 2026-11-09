const task=await taskSpace('NVDA long term mobile review');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8768/index.html?nvda=1');
await page.click('loc=css:[data-category="stock"]');
await page.click('loc=css:[data-asset-symbol="NVDA"] > details > summary');
console.log(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 cards:[...document.querySelectorAll('#stockList > .card')].map(el=>({symbol:el.dataset.assetSymbol,text:el.innerText}))})));
console.log(await page.screenshot({path:'D:/file/fun/code/cycle/research_nvda_strategy/mobile.png',fullPage:true}));
await task.finish({keep:[]});
