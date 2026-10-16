const CACHE='jaldrishti-shell-popup-v4';
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/farmer','/manifest.webmanifest','/icons/icon192.png','/icons/icon512.png'])));self.skipWaiting()});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('jaldrishti-shell-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);if(url.origin!==self.location.origin||event.request.method!=='GET'||url.pathname.startsWith('/api/'))return;
 if(event.request.mode==='navigate'){
  event.respondWith(fetch(event.request).catch(()=>caches.match('/farmer')));return;
 }
 if(url.pathname.startsWith('/assets/')||url.pathname.startsWith('/icons/'))event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(c=>c.put(event.request,copy))}return response})));
});
self.addEventListener('push',event=>{
 let data={title:'JalDrishti',body:'A regional update is available.',url:'/farmer'};
 try{data={...data,...event.data.json()}}catch{}
 const expired=data.expires&&data.expires<Date.now()/1000;
 const body=expired?'A regional update has expired. Open the inbox for its current status.':data.body;
 event.waitUntil(Promise.all([self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients=>clients.forEach(client=>client.postMessage({type:'regional-update'}))),self.registration.showNotification(data.title,{body,tag:data.tag,icon:'/icons/icon192.png',badge:'/icons/icon192.png',data:{url:data.url||'/farmer'}})]));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();let url=new URL(event.notification.data?.url||'/farmer',self.location.origin);
 if(url.origin!==self.location.origin||url.pathname!=='/farmer')url=new URL('/farmer',self.location.origin);
 event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(async clients=>{
  for(const client of clients)if(new URL(client.url).origin===self.location.origin){await client.navigate(url.href);return client.focus()}
  return self.clients.openWindow(url.href);
 }));
});
