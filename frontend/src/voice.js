import {useEffect,useRef,useState} from 'react';
export function useVoice(language,onTranscript){
 const [listening,setListening]=useState(false),[message,setMessage]=useState(''),[speaking,setSpeaking]=useState(false);
 const recognition=useRef(null),callback=useRef(onTranscript);callback.current=onTranscript;
 const locale={English:'en-IN',Hindi:'hi-IN',Marathi:'mr-IN'}[language];
 const supported=typeof window!=='undefined'&&!!(window.SpeechRecognition||window.webkitSpeechRecognition);
 const canSpeak=typeof window!=='undefined'&&'speechSynthesis' in window;
 const stop=()=>{recognition.current?.stop();setListening(false);if(canSpeak)window.speechSynthesis.cancel();setSpeaking(false)};
 useEffect(()=>{stop();setMessage('');return stop},[language]);
 const dictate=()=>{
  setMessage('');if(listening){recognition.current?.stop();return}
  if(!supported){setMessage('unsupported');return}
  const Constructor=window.SpeechRecognition||window.webkitSpeechRecognition;
  const r=new Constructor();recognition.current=r;r.lang=locale;r.continuous=false;r.interimResults=false;
  r.onstart=()=>setListening(true);r.onend=()=>setListening(false);
  r.onerror=e=>{setListening(false);setMessage(e.error==='not-allowed'?'denied':e.error==='no-speech'?'noSpeech':'voiceError')};
  r.onresult=e=>{const words=Array.from(e.results).filter(result=>result.isFinal).map(result=>result[0].transcript).join(' ');if(words)callback.current(words)};
  try{r.start()}catch{setMessage('voiceError')}
 };
 const speak=text=>{
  setMessage('');if(!canSpeak){setMessage('unsupported');return}
  window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang=locale;u.rate=.9;
  const voices=window.speechSynthesis.getVoices();const candidates=voices.filter(v=>v.lang.toLowerCase().startsWith(locale.slice(0,2)));
  const voice=candidates.find(v=>v.localService)||candidates[0];
  if(!voice&&language!=='English'){setMessage('noVoice');setSpeaking(false);return}
  if(voice)u.voice=voice;
  u.onstart=()=>setSpeaking(true);u.onend=()=>setSpeaking(false);u.onerror=()=>{setSpeaking(false);setMessage('voiceError')};
  window.speechSynthesis.speak(u);
 };
 return {listening,speaking,message,supported,canSpeak,dictate,speak,stop};
}
