const task = await taskSpace('MSFT mobile review');
const page = task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride', {width:375,height:812,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:8766/index.html');
await page.click('loc=css:[data-category="stock"]');
await page.click('loc=css:#stockList details summary');
console.log(await page.evaluate(() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,card:document.querySelector('#stockList').innerText})));
console.log(await page.screenshot({path:'D:/file/fun/code/cycle/research_msft_strategy/mobile_check.png'}));
await task.finish({keep:[]});
