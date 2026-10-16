"""One backend instance with a persistent disk and background alert delivery."""
import os
import shutil
import sys
import threading
from pathlib import Path
import uvicorn

if __name__=='__main__':
    root=Path(__file__).parent/'backend'
    if not os.getenv('DATABASE_URL'):
        raise SystemExit('Set the Supabase server-only DATABASE_URL. Free cloud deployment requires durable external storage.')
    # Public datasets ship in Git; only private state is stored in Postgres.
    (root/'private').mkdir(exist_ok=True,mode=0o700)
    sys.path.insert(0,str(root))
    from admin import configure,PRIVATE
    password=os.getenv('ADMIN_PASSWORD','')
    if not (PRIVATE/'admin.json').exists():
        if len(password)<12:raise SystemExit('Set ADMIN_PASSWORD with at least twelve characters in backend environment settings.')
        configure(password)
    from postgres_store import initialize
    initialize()
    from push_delivery import configure as configure_push,run_worker
    if os.getenv('PUSH_CONTACT_EMAIL'):configure_push('mailto:'+os.environ['PUSH_CONTACT_EMAIL'])
    stop=threading.Event();threading.Thread(target=run_worker,args=(stop,),daemon=True).start()
    try:uvicorn.run('api:app',host='0.0.0.0',port=int(os.getenv('PORT','10000')),workers=1,proxy_headers=True,forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS','127.0.0.1'))
    finally:stop.set()
