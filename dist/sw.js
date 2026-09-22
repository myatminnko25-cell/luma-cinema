/* Network-first pages: never cache catalog, admin, auth or video streams. */
const CACHE='luma-offline-v1';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.add('/offline.html'))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('luma-offline-')&&key!==CACHE).map(key=>caches.delete(key))))));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin||event.request.mode!=='navigate'||!['/','/index.html'].includes(url.pathname))return;
 event.respondWith(fetch(event.request).catch(()=>caches.open(CACHE).then(cache=>cache.match('/offline.html'))));
});
