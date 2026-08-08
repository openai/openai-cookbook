const CACHE='aumara-staff-pwa-v2.2.0';
const SHELL=['/staff/','/staff/index.html','/staff/styles.css?v=220','/staff/app.js?v=220','/staff/patch.js?v=220','/staff/legacy.js?v=220','/staff/manifest.webmanifest','/staff/icon.svg'];
self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()));
});
self.addEventListener('activate',event=>{
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()));
});
self.addEventListener('fetch',event=>{
  if(event.request.method!=='GET') return;
  const url=new URL(event.request.url);
  if(url.origin!==self.location.origin) return;
  if(event.request.mode==='navigate'){
    event.respondWith(caches.match('/staff/').then(cached=>{
      const fresh=fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(c=>c.put('/staff/',copy));return response}).catch(()=>cached);
      return cached||fresh;
    }));
    return;
  }
  event.respondWith(caches.match(event.request).then(cached=>{
    const fresh=fetch(event.request).then(response=>{if(response&&response.ok){const copy=response.clone();caches.open(CACHE).then(c=>c.put(event.request,copy))}return response}).catch(()=>cached);
    return cached||fresh;
  }));
});
self.addEventListener('message',event=>{if(event.data==='SKIP_WAITING')self.skipWaiting()});