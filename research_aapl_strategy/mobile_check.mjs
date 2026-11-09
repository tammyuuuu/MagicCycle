const task = await taskSpace('aapl-candidate-mobile-20261109');
const page = task.page('p1');
await page.cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
await page.goto('http://127.0.0.1:5000/',{timeout:60000});
await page.click('loc=css:button[data-category="stock"]');
await page.waitForSelector('loc=css:[data-asset-symbol="AAPL"]');
console.log(await page.evaluate(() => { const c=document.querySelector('[data-asset-symbol="AAPL"]'); c.scrollIntoView(); return {text:c.innerText,documentWidth:document.documentElement.scrollWidth,viewport:innerWidth}; }));
await page.screenshot({path:'D:/file/fun/code/cycle/research_aapl_strategy/mobile_aapl.png'});
await task.finish({keep:[]});
