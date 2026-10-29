/* Generated release changes whenever exported content changes. */
const RELEASE = 'dc854f5f70c483672b91';
const CACHE = 'magiccycle-pwa-' + RELEASE;
const ROOT = new URL('./', self.location.href);
const PAGE = new URL('index.html', ROOT).href;
self.addEventListener('install', event => {
 event.waitUntil((async()=>{
  const response=await fetch(new URL('pwa-manifest.json',ROOT),{cache:'no-store'});
  if(!response.ok)throw Error('Offline manifest unavailable');
  const manifest=await response.json();
  if(manifest.version!==RELEASE)throw Error('Deployment still publishing; retain previous version');
  const cache=await caches.open(CACHE);
  try{await Promise.all(manifest.files.map(async path=>{
   const request=new Request(new URL(path,ROOT),{cache:'reload'});
   let response;
   // Unchanged, content-addressed research is reused without another download.
   if(/^assets\/[\w-]+\.[a-f0-9]{16}\.js$/.test(path)){
    for(const name of (await caches.keys()).filter(k=>k.startsWith('magiccycle-pwa-')&&k!==CACHE)){
     response=await (await caches.open(name)).match(request);if(response)break;
    }
   }
   response=response||await fetch(request);
   if(!response.ok)throw Error('Incomplete release: '+path);
   const bytes=await response.clone().arrayBuffer();
   const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
   if(hash!==manifest.hashes[path])throw Error('Release hash mismatch: '+path);
   await cache.put(request,response);
  }));}
  catch(error){await caches.delete(CACHE);throw error;}
  // Updates wait for the user's refresh action; first install activates normally.
 })());
});
self.addEventListener('message',event=>{
 if(event.data?.type==='ACTIVATE_UPDATE')event.waitUntil(self.skipWaiting());
 if(event.data?.type==='GET_RELEASE')event.ports[0]?.postMessage({version:RELEASE});
});
self.addEventListener('activate',event=>{
 event.waitUntil((async()=>{
  // CacheStorage contains only public resources; never touch localStorage or IndexedDB.
  // Keep the preceding cache so open tabs can finish loading their immutable bundles.
  const keys=(await caches.keys()).filter(k=>k.startsWith('magiccycle-pwa-')&&k!==CACHE);
  for(const key of keys.slice(0,-1))await caches.delete(key);
  await self.clients.claim();
 })());
});
async function cachedResponse(request,navigation){
 const cache=await caches.open(CACHE),key=navigation?PAGE:request;
 let stored=await cache.match(key);
 if(!stored&&!navigation){
  for(const name of (await caches.keys()).filter(k=>k.startsWith('magiccycle-pwa-')).reverse()){
   stored=await (await caches.open(name)).match(key);if(stored)break;
  }
 }
 if(stored)return stored;
 const response=await fetch(request);
 if(response.ok)await cache.put(key,response.clone());
 return response;
}
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==ROOT.origin||!url.pathname.startsWith(ROOT.pathname))return;
 const navigation=request.mode==='navigate'&&(url.pathname===ROOT.pathname||url.pathname===new URL(PAGE).pathname);
 const relative=url.pathname.slice(ROOT.pathname.length);
 // Update checks and live quotes bypass the offline shell. A stale quote never becomes today's data.
 if(['sw.js','pwa-manifest.json','account_nav.json'].includes(relative))return;
 if(navigation||relative.startsWith('assets/')||relative.startsWith('icons/')||['pwa.js','manifest.webmanifest'].includes(relative))
  event.respondWith(cachedResponse(request,navigation));
});
