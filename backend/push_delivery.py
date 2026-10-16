"""Durable Web Push queue. Only administrator-published messages are eligible."""
import base64
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from core import ROOT
CONFIG=ROOT/'private/webpush.json'

def public_config():
    if not CONFIG.exists():return {'configured':False,'public_key':None}
    config=json.loads(CONFIG.read_text());return {'configured':True,'public_key':config['public_key']}

def configure(subject):
    if not (subject.startswith('mailto:') and '@' in subject):raise ValueError('Use a real contact address: mailto:you@example.com')
    if CONFIG.exists():return public_config()
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    key=ec.generate_private_key(ec.SECP256R1())
    pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    public=key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    CONFIG.write_text(json.dumps({'subject':subject,'private_key':pem,'public_key':base64.urlsafe_b64encode(public).decode().rstrip('=')}));CONFIG.chmod(0o600)
    return public_config()

def process_queue(limit=30):
    if not CONFIG.exists():return {'configured':False,'processed':0}
    from community import database,audience,valid_endpoint
    from pywebpush import webpush,WebPushException
    from py_vapid import Vapid
    config=json.loads(CONFIG.read_text());vapid=Vapid.from_pem(config['private_key'].encode());processed=0
    for _ in range(limit):
        now=time.time()
        with database() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute("UPDATE outbox SET state='retry' WHERE state='sending' AND lease_until<?",(now,))
            job=c.execute("SELECT o.*,a.district,a.block,a.messages,a.status,a.expires,p.language,s.payload,s.enabled FROM outbox o JOIN alerts a ON a.id=o.alert_id JOIN profiles p ON p.id=o.profile_id LEFT JOIN subscriptions s ON s.profile_id=o.profile_id WHERE o.state IN ('queued','retry') AND o.next_try<=? ORDER BY o.id LIMIT 1",(now,)).fetchone()
            if not job:break
            if job['status']!='published' or job['expires']<=now or not job['enabled'] or job['profile_id'] not in audience(c,job['district'],job['block']):
                c.execute("UPDATE outbox SET state='cancelled' WHERE id=?",(job['id'],));continue
            c.execute("UPDATE outbox SET state='sending',lease_until=?,attempts=attempts+1 WHERE id=?",(now+60,job['id']))
        subscription=json.loads(job['payload']);message=json.loads(job['messages'])[job['language']]
        payload={'title':message['title'],'body':message['body'][:220],'tag':'jaldrishti-'+job['alert_id'],'url':'/farmer?'+urlencode({'alert':job['alert_id'],'district':job['district'],'block':job['block']}),'expires':job['expires']}
        state='accepted';error=None;disable=False
        try:
            valid_endpoint(subscription['endpoint'])
            webpush(subscription_info=subscription,data=json.dumps(payload,ensure_ascii=False),vapid_private_key=vapid,vapid_claims={'sub':config['subject']},ttl=min(86400,max(1,int(job['expires']-now))),timeout=8)
        except WebPushException as e:
            code=e.response.status_code if e.response is not None else None
            error='Push service HTTP '+str(code) if code else 'Push network error'
            disable=code in (404,410)
            state='expired' if disable else ('failed' if job['attempts']>=2 else 'retry')
        except Exception:
            state='failed';error='Push configuration or subscription error'
        with database() as c:
            c.execute('UPDATE outbox SET state=?,last_error=?,next_try=?,lease_until=0 WHERE id=?',(state,error,time.time()+60*(2**job['attempts']),job['id']))
            if disable:c.execute('UPDATE subscriptions SET enabled=0 WHERE profile_id=?',(job['profile_id'],))
        processed+=1
    return {'configured':True,'processed':processed}

def run_worker(stop):
    while not stop.is_set():
        try:process_queue()
        except Exception as error:print('Push worker error:',type(error).__name__,flush=True) # No endpoint/key details in logs.
        stop.wait(3)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--contact');p.add_argument('--once',action='store_true');a=p.parse_args()
    if a.contact:print(json.dumps(configure(a.contact)))
    elif a.once:print(json.dumps(process_queue()))
    else:raise SystemExit('Use --contact mailto:you@example.com to set up push, or --once to process queued messages.')
