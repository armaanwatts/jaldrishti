"""Explicit jury-demo HTTPS tunnel; never starts one automatically."""
import argparse
import re
import shutil
import subprocess
import sys
p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8002);a=p.parse_args()
program=shutil.which('cloudflared')
if not program:
    raise SystemExit('cloudflared is not installed. On macOS with Homebrew: brew install cloudflared\nThen run this script again. Official downloads: https://developers.cloudflare.com/tunnel/downloads/')
print('This creates a temporary public URL to the running JalDrishti app. Keep this Terminal open. Stop with Ctrl+C.',flush=True)
process=subprocess.Popen([program,'tunnel','--url',f'http://127.0.0.1:{a.port}'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
try:
    for line in process.stdout:
        match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
        if match:print('\nPHONE LINK: '+match.group(0)+'/farmer\nADMIN DASHBOARD: '+match.group(0)+'/\nUse this SAME origin when saving regions and enabling push.\n',flush=True)
        elif any(term in line.lower() for term in ['error','failed','registered tunnel']):print(line.rstrip(),flush=True)
finally:
    process.terminate()
