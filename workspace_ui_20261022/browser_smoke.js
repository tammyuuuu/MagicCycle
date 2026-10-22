const {chromium}=require('C:/Users/tammy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},locale:'zh-CN',timezoneId:'Asia/Shanghai'});
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(require('url').pathToFileURL(path.join(__dirname,'static_preview.html')).href,{waitUntil:'load'});
 await page.locator('#topnav a[data-page="lab"]').click();
 await page.screenshot({path:path.join(__dirname,'desktop_lab.png'),fullPage:true});
 console.log('title',await page.title(),'strategies',await page.locator('.strategy').count(),'errors',errors);
 console.log('body',await page.locator('#workspaceStatus').textContent());
 await page.setViewportSize({width:375,height:812});
 await page.screenshot({path:path.join(__dirname,'mobile_lab.png'),fullPage:true});
 console.log('mobile',await page.evaluate(()=>({inner:innerWidth,scroll:document.documentElement.scrollWidth})));
 console.log('overflow',await page.evaluate(()=>[...document.querySelectorAll('body *')].filter(e=>{let r=e.getBoundingClientRect();return r.width>375||r.right>375;}).slice(0,14).map(e=>({tag:e.tagName,id:e.id,class:e.className,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right}))));
 fs.writeFileSync(path.join(__dirname,'smoke.json'),JSON.stringify({errors},null,2));
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
