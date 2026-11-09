const task = await taskSpace('Verify corrected MSFT');
const page = task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride', {width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8767/index.html?verified=2');
await page.click('loc=css:[data-category="stock"]');
await page.click('loc=css:#stockList > .card > details > summary');
console.log(await page.evaluate(() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,card:document.querySelector('#stockList').innerText})));
console.log(await page.screenshot({path:'D:/file/fun/code/cycle/research_msft_strategy/fresh_page.png'}));
await task.finish({keep:[]});
