const CACHE='piano-ai-v1';
const CORE=['/','/index.html','/demo.json','/icon.svg','/icon-192.png','/icon-512.png','/manifest.webmanifest',...Array.from({length:7},(_,i)=>`/samples/C${i+1}.mp3`)];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE))));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);if(event.request.method!=='GET'||url.origin!==location.origin||url.pathname.startsWith('/api/'))return;
 event.respondWith(fetch(event.request).then(res=>{if(res.ok){const copy=res.clone();void caches.open(CACHE).then(c=>c.put(event.request,copy))}return res}).catch(()=>caches.match(event.request).then(cached=>cached||(event.request.mode==='navigate'?caches.match('/index.html'):Response.error()))));
});
