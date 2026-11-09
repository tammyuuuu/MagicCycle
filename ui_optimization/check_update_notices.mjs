const task=await taskSpace('Check all asset update labels');
const page=task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8771/index.html?notices=1');
await page.evaluate(()=>document.querySelector('[data-category="stock"]').scrollIntoView({block:'nearest',inline:'center'}));
await page.click('loc=css:[data-category="stock"]');
console.log(await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
 cards:[...document.querySelectorAll('.today-category .asset-list > .card')].map(el=>({symbol:el.dataset.assetSymbol,
 notice:(el.textContent.match(/[^。\n]{0,30}(?:未更新|待更新|更新失败|更新受限|过期|过旧|等待数据更新|网络异常)[^。\n]{0,30}/g)||[])})),
 stocks:[...document.querySelectorAll('#stockList > .card')].map(el=>el.innerText)})));
await task.finish({keep:[]});
