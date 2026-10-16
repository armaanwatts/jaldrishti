"""Run the farmer PWA and dashboard on one origin, with a durable push worker."""
import argparse
from pathlib import Path
import socket
import sys
import threading
import subprocess
sys.path.insert(0,str(Path(__file__).parent/'backend'))
import uvicorn
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',default=8002,type=int);a=p.parse_args()
    stop=threading.Event()
    from push_delivery import run_worker
    worker=threading.Thread(target=run_worker,args=(stop,),daemon=True);worker.start()
    def preload():
        import json
        from urllib.request import Request,urlopen
        from core import MODEL
        try:
            payload=json.dumps({'model':MODEL,'stream':False,'keep_alive':'20m','options':{'num_ctx':4096}}).encode()
            with urlopen(Request('http://127.0.0.1:11434/api/generate',data=payload,headers={'Content-Type':'application/json'}),timeout=120) as response:response.read()
            print('Local Qwen preloaded for faster first answers.',flush=True)
        except Exception:print('Open Ollama, then use Warm local model in Administrator.',flush=True)
    threading.Thread(target=preload,daemon=True).start()
    print(f'Dashboard: http://127.0.0.1:{a.port}/')
    print(f'Farmer view: http://127.0.0.1:{a.port}/farmer')
    if a.host=='0.0.0.0':
        address=None
        if sys.platform=='darwin':
            for interface in ['en0','en1']:
                result=subprocess.run(['ipconfig','getifaddr',interface],capture_output=True,text=True)
                if result.returncode==0 and result.stdout.strip():address=result.stdout.strip();break
        if address:print(f'Phone on the same Wi-Fi: http://{address}:{a.port}/farmer')
        else:print('Phone Wi-Fi URL: http://YOUR_MAC_WIFI_IP:'+str(a.port)+'/farmer')
        print('Phone push, installation and voice require an HTTPS origin. LAN HTTP supports basic data, chat and inbox testing.')
    try:uvicorn.run('api:app',host=a.host,port=a.port,proxy_headers=True,forwarded_allow_ips='127.0.0.1')
    finally:stop.set()
