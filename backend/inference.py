"""Bounded evidence-keyed cache and one local generation at a time."""
from collections import OrderedDict
import copy
import hashlib
import json
import threading
import time
CACHE=OrderedDict();LOCK=threading.Lock();GENERATION=threading.Semaphore(1)
LAST={}
def cached(question,facts,language,generate):
    key=hashlib.sha256(json.dumps([question,facts,language],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    now=time.monotonic()
    with LOCK:
        if key in CACHE:
            stamped,result=CACHE[key]
            if now-stamped<1800:
                CACHE.move_to_end(key);return {**copy.deepcopy(result),'cached':True}
            del CACHE[key]
    if not GENERATION.acquire(timeout=3):raise ValueError('Local model is busy; retry after the current answer finishes.')
    try:
        with LOCK:
            if key in CACHE and time.monotonic()-CACHE[key][0]<1800:return {**copy.deepcopy(CACHE[key][1]),'cached':True}
        result=generate(question,facts,language)
        with LOCK:
            CACHE[key]=(time.monotonic(),copy.deepcopy(result));CACHE.move_to_end(key)
            while len(CACHE)>128:CACHE.popitem(last=False)
            LAST.clear();LAST.update(result.get('timing',{}))
        return {**result,'cached':False}
    finally:GENERATION.release()

def status():
    with LOCK:return {'cached_answers':len(CACHE),'last_generation':dict(LAST),'keep_alive':'20m','parallel_generations':1,'note':'Measured on the machine running Ollama; no speed-up benchmark is assumed.'}
