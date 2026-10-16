import React,{useEffect,useRef,useState} from 'react';
const copy={English:{new:'Regional update',open:'Read alert',dismiss:'Dismiss',more:'More updates are waiting in Alerts.'},Hindi:{new:'क्षेत्र की सूचना',open:'सूचना पढ़ें',dismiss:'बंद करें',more:'और सूचनाएँ सूचना पेज पर हैं।'},Marathi:{new:'क्षेत्राची सूचना',open:'सूचना वाचा',dismiss:'बंद करा',more:'आणखी सूचना सूचना पानावर आहेत.'}};
export function AlertPopup({language,onOpen}){
 const [queue,setQueue]=useState([]),seen=useRef(new Set()),pending=useRef(false);const t=copy[language];
 useEffect(()=>{let active=true;const controller=new AbortController();
 const check=async()=>{if(document.visibilityState==='hidden'||pending.current)return;pending.current=true;try{
 const response=await fetch('/api/farmer/inbox?language='+encodeURIComponent(language),{credentials:'same-origin',cache:'no-store',signal:controller.signal});if(!response.ok)return;
 const data=await response.json();if(!active)return;
 const eligible=(data.items||[]).filter(a=>!a.expired&&!a.withdrawn&&!a.read);const ids=new Set(eligible.map(a=>a.id));
 const fresh=eligible.filter(a=>{if(seen.current.has(a.id))return false;seen.current.add(a.id);try{return sessionStorage.getItem('jaldrishti-popup-'+a.id)!=='dismissed'}catch{return true}});
 setQueue(previous=>{const existing=previous.filter(a=>ids.has(a.id)).map(a=>eligible.find(v=>v.id===a.id));return [...existing,...fresh.filter(a=>!existing.some(v=>v.id===a.id))].slice(0,10)});
 }catch{}finally{pending.current=false}};
 check();const timer=setInterval(check,5000);const visible=()=>check();document.addEventListener('visibilitychange',visible);navigator.serviceWorker?.addEventListener('message',visible);
 return()=>{active=false;controller.abort();clearInterval(timer);document.removeEventListener('visibilitychange',visible);navigator.serviceWorker?.removeEventListener('message',visible)};
 },[language]);
 const item=queue[0];if(!item)return null;
 const dismiss=()=>{try{sessionStorage.setItem('jaldrishti-popup-'+item.id,'dismissed')}catch{}setQueue(q=>q.slice(1))};
 return <div className="regional-popup" role="region" aria-label={t.new}><div role="status" aria-live="polite" aria-atomic="true"><small>{t.new} · {item.district}{item.block?' · '+item.block:''}</small><h3>{item.title}</h3><p>{item.body}</p>{queue.length>1&&<small>{t.more}</small>}</div><div className="actions"><button onClick={()=>{onOpen(item);dismiss()}}>{t.open}</button><button className="secondary" onClick={dismiss}>{t.dismiss}</button></div></div>
}
