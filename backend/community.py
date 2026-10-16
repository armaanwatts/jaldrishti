"""Device profiles, explicit region subscriptions, reviewed alerts and durable inbox.

No personal names, phone numbers or continuous location tracking are collected.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlparse
from fastapi import APIRouter,HTTPException,Request,Response,Header
from pydantic import BaseModel,Field
from typing import Literal
import os
from core import ROOT

DB=ROOT/'private/community.sqlite3'
COOKIE='jaldrishti_device'
LANGS=['English','Hindi','Marathi']

@contextmanager
def database():
    DB.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    DB.parent.chmod(0o700)
    c=sqlite3.connect(DB,timeout=20);DB.chmod(0o600);c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL')
    c.executescript('''
    CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,language TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS regions(id TEXT PRIMARY KEY,profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,district TEXT NOT NULL,block TEXT NOT NULL DEFAULT '',UNIQUE(profile_id,district,block));
    CREATE TABLE IF NOT EXISTS subscriptions(profile_id TEXT PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,payload TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,district TEXT NOT NULL,block TEXT NOT NULL,kind TEXT NOT NULL,messages TEXT NOT NULL,source_url TEXT NOT NULL,observed_date TEXT NOT NULL,expires REAL NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,published REAL,owner TEXT NOT NULL,preview_until REAL NOT NULL,audience TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS inbox(alert_id TEXT NOT NULL REFERENCES alerts(id),profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,read_at REAL,PRIMARY KEY(alert_id,profile_id));
    CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,alert_id TEXT NOT NULL,profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,state TEXT NOT NULL DEFAULT 'queued',attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL DEFAULT 0,lease_until REAL NOT NULL DEFAULT 0,last_error TEXT,UNIQUE(alert_id,profile_id));
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS region_target ON regions(district,block,profile_id);
    CREATE INDEX IF NOT EXISTS inbox_profile ON inbox(profile_id,alert_id);
    CREATE INDEX IF NOT EXISTS outbox_queue ON outbox(state,next_try);
    ''')
    try:
        yield c;c.commit()
    except Exception:c.rollback();raise
    finally:c.close()

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def mutation(request):
    # Cross-site forms cannot add this custom header; CORS is not enabled.
    if request.headers.get('X-JalDrishti-Action')!='1':raise HTTPException(403,'Missing same-origin action header')
    origin=request.headers.get('origin')
    allowed={str(request.base_url).rstrip('/')} | {v.strip().rstrip('/') for v in os.getenv('PUBLIC_ORIGINS','').split(',') if v.strip()}
    if origin and origin.rstrip('/') not in allowed:raise HTTPException(403,'Cross-origin write rejected')
def farmer(request,c):
    value=request.cookies.get(COOKIE,'')
    row=c.execute('SELECT * FROM profiles WHERE token_hash=? AND expires>?',(digest(value),time.time())).fetchone()
    if not row:raise HTTPException(401,'Create a device profile first')
    return row

def audience(c,district,block):
    # A block alert targets matching block subscriptions, not district-wide subscribers.
    # District subscriptions are broad updates; this avoids claiming a block for them.
    sql='SELECT DISTINCT r.profile_id FROM regions r JOIN profiles p ON p.id=r.profile_id WHERE r.district=? AND p.expires>?'
    args=[district,time.time()]
    if block:sql+=' AND r.block=?';args.append(block)
    return sorted(r[0] for r in c.execute(sql,args))

def profile_data(c,row):
    return {'language':row['language'],'regions':[dict(r) for r in c.execute('SELECT id,district,block FROM regions WHERE profile_id=? ORDER BY district,block',(row['id'],))],
            'push_enabled':bool(c.execute('SELECT 1 FROM subscriptions WHERE profile_id=? AND enabled=1',(row['id'],)).fetchone()),'device_profile':True}

class Language(BaseModel): language:Literal['English','Hindi','Marathi']='English'
class Region(BaseModel): district:str=Field(min_length=1,max_length=100);block:str=Field(default='',max_length=100)
class Push(BaseModel): endpoint:str=Field(max_length=2048);keys:dict[str,str]
class Message(BaseModel): title:str=Field(min_length=3,max_length=120);body:str=Field(min_length=10,max_length=1200)
class Draft(BaseModel):
    district:str=Field(min_length=1,max_length=100)
    block:str=Field(default='',max_length=100)
    kind:Literal['test','data_update','advisory','warning']='data_update'
    messages:dict[str,Message]
    source_url:str=Field(max_length=2048)
    observed_date:str=Field(max_length=10)
    valid_hours:int=Field(default=48,ge=1,le=168)
class PushSetup(BaseModel): contact_email:str=Field(min_length=5,max_length=254)
class Approve(BaseModel): draft_id:str;reviewed:bool=False

def valid_endpoint(value):
    parsed=urlparse(value);host=(parsed.hostname or '').lower()
    # No arbitrary endpoints: prevent push delivery from becoming an SSRF proxy.
    allowed=host=='fcm.googleapis.com' or host=='updates.push.services.mozilla.com' or host.endswith('.push.services.mozilla.com') or host=='web.push.apple.com' or host.endswith('.push.apple.com') or host=='notify.windows.com' or host.endswith('.notify.windows.com')
    try:port=parsed.port
    except ValueError:raise HTTPException(422,'Invalid push endpoint port')
    if parsed.scheme!='https' or parsed.username or parsed.password or port not in [None,443] or not allowed:raise HTTPException(422,'Unsupported browser push endpoint')

def create_router(records,admin_auth):
    router=APIRouter(prefix='/api')
    def validate_region(region):
        df=records();sub=df[df.district.eq(region.district)]
        if sub.empty:raise HTTPException(422,'Choose a district from the loaded data')
        if region.block and not sub.source_tehsil.eq(region.block).any():raise HTTPException(422,'Choose a block from this district')
    @router.get('/farmer/profile')
    def me(request:Request):
        with database() as c:return profile_data(c,farmer(request,c))
    @router.post('/farmer/profile')
    def create(body:Language,request:Request,response:Response):
        mutation(request)
        with database() as c:
            existing=c.execute('SELECT * FROM profiles WHERE token_hash=? AND expires>?',(digest(request.cookies.get(COOKIE,'')),time.time())).fetchone()
            if existing:
                c.execute('UPDATE profiles SET language=? WHERE id=?',(body.language,existing['id']))
                return profile_data(c,c.execute('SELECT * FROM profiles WHERE id=?',(existing['id'],)).fetchone())
            token=secrets.token_urlsafe(32);identifier=secrets.token_hex(16);now=time.time();expires=now+90*86400
            c.execute('INSERT INTO profiles VALUES(?,?,?,?,?)',(identifier,digest(token),body.language,now,expires))
            response.set_cookie(COOKIE,token,max_age=90*86400,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/')
            return profile_data(c,c.execute('SELECT * FROM profiles WHERE id=?',(identifier,)).fetchone())
    @router.delete('/farmer/profile')
    def delete_profile(request:Request,response:Response):
        mutation(request)
        with database() as c:
            row=farmer(request,c);c.execute('DELETE FROM profiles WHERE id=?',(row['id'],))
        response.delete_cookie(COOKIE,path='/');return {'deleted':True}
    @router.post('/farmer/regions')
    def save_region(body:Region,request:Request):
        mutation(request);validate_region(body)
        with database() as c:
            row=farmer(request,c)
            count=c.execute('SELECT COUNT(*) FROM regions WHERE profile_id=?',(row['id'],)).fetchone()[0]
            exists=c.execute('SELECT 1 FROM regions WHERE profile_id=? AND district=? AND block=?',(row['id'],body.district,body.block)).fetchone()
            if count>=5 and not exists:raise HTTPException(422,'Maximum five saved alert regions')
            c.execute('INSERT OR IGNORE INTO regions VALUES(?,?,?,?)',(secrets.token_hex(12),row['id'],body.district,body.block))
            c.execute("INSERT OR IGNORE INTO inbox(alert_id,profile_id) SELECT id,? FROM alerts WHERE status='published' AND expires>? AND district=? AND (block='' OR block=?)",(row['id'],time.time(),body.district,body.block))
            return profile_data(c,row)
    @router.delete('/farmer/regions/{region_id}')
    def remove_region(region_id:str,request:Request):
        mutation(request)
        with database() as c:
            row=farmer(request,c);c.execute('DELETE FROM regions WHERE id=? AND profile_id=?',(region_id,row['id']))
            return profile_data(c,row)
    @router.get('/farmer/inbox')
    def inbox(request:Request,language:Literal['English','Hindi','Marathi']|None=None):
        with database() as c:
            row=farmer(request,c)
            results=c.execute('SELECT a.*,i.read_at FROM inbox i JOIN alerts a ON a.id=i.alert_id WHERE i.profile_id=? ORDER BY a.published DESC LIMIT 100',(row['id'],)).fetchall()
            items=[]
            for r in results:
                messages=json.loads(r['messages']);message=messages[language or row['language']]
                items.append({'id':r['id'],'district':r['district'],'block':r['block'],'kind':r['kind'],**message,'source_url':r['source_url'],'observed_date':r['observed_date'],'published_at':r['published'],'expires_at':r['expires'],'expired':r['expires']<time.time(),'withdrawn':r['status']=='withdrawn','read':r['read_at'] is not None})
            return {'items':items}
    @router.post('/farmer/inbox/{alert_id}/read')
    def mark_read(alert_id:str,request:Request):
        mutation(request)
        with database() as c:
            row=farmer(request,c);c.execute('UPDATE inbox SET read_at=? WHERE alert_id=? AND profile_id=?',(time.time(),alert_id,row['id']))
        return {'ok':True}
    @router.get('/push/config')
    def push_config():
        from push_delivery import public_config
        return public_config()
    @router.post('/farmer/push')
    def subscribe(body:Push,request:Request):
        mutation(request);valid_endpoint(body.endpoint)
        import base64
        try:
            public=base64.urlsafe_b64decode(body.keys.get('p256dh','')+'===');secret=base64.urlsafe_b64decode(body.keys.get('auth','')+'===')
            if len(public)!=65 or public[0]!=4 or len(secret)!=16:raise ValueError()
        except Exception:raise HTTPException(422,'Invalid subscription encryption keys')
        with database() as c:
            row=farmer(request,c)
            # A browser endpoint belongs to only one current device profile.
            old=c.execute("SELECT profile_id FROM subscriptions WHERE json_extract(payload,'$.endpoint')=? AND profile_id!=?",(body.endpoint,row['id'])).fetchall()
            for previous in old:
                c.execute('DELETE FROM subscriptions WHERE profile_id=?',(previous['profile_id'],))
                c.execute("UPDATE outbox SET state='cancelled' WHERE profile_id=? AND state IN ('queued','retry')",(previous['profile_id'],))
            c.execute('INSERT INTO subscriptions VALUES(?,?,1) ON CONFLICT(profile_id) DO UPDATE SET payload=excluded.payload,enabled=1',(row['id'],body.model_dump_json()))
        return {'enabled':True}
    @router.delete('/farmer/push')
    def unsubscribe(request:Request):
        mutation(request)
        with database() as c:
            row=farmer(request,c);c.execute('DELETE FROM subscriptions WHERE profile_id=?',(row['id'],));c.execute("UPDATE outbox SET state='cancelled' WHERE profile_id=? AND state IN ('queued','retry')",(row['id'],))
        return {'enabled':False}
    @router.post('/admin/alerts/preview')
    def preview(body:Draft,request:Request,authorization:str|None=Header(default=None)):
        token=admin_auth(authorization);mutation(request);validate_region(body)
        if body.kind=='warning':raise HTTPException(409,'Automated crisis warnings are not validated. Publish a sourced data update or reviewed advisory instead.')
        if set(body.messages)!=set(LANGS):raise HTTPException(422,'Provide reviewed English, Hindi and Marathi messages')
        parsed=urlparse(body.source_url)
        if parsed.scheme!='https' or not parsed.hostname:raise HTTPException(422,'Attach an HTTPS evidence URL')
        try:observed=datetime.strptime(body.observed_date,'%Y-%m-%d').date()
        except ValueError:raise HTTPException(422,'Use observation date YYYY-MM-DD')
        if observed>datetime.now(timezone.utc).date():raise HTTPException(422,'Observation date is in the future')
        now=time.time();identifier=secrets.token_hex(16)
        with database() as c:
            ids=audience(c,body.district,body.block)
            c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,body.district,body.block,body.kind,json.dumps({k:v.model_dump() for k,v in body.messages.items()},ensure_ascii=False),body.source_url,body.observed_date,now+body.valid_hours*3600,'draft',now,None,digest(token),now+600,json.dumps(ids)))
            push_count=sum(bool(c.execute('SELECT 1 FROM subscriptions WHERE profile_id=? AND enabled=1',(i,)).fetchone()) for i in ids)
        return {'draft_id':identifier,'recipient_devices':len(ids),'push_devices':push_count,'messages':{k:v.model_dump() for k,v in body.messages.items()},'preview_expires_in':600}
    @router.post('/admin/alerts/publish')
    def publish_alert(body:Approve,request:Request,authorization:str|None=Header(default=None)):
        token=admin_auth(authorization);mutation(request)
        if not body.reviewed:raise HTTPException(422,'Review evidence, language and region before publishing')
        with database() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM alerts WHERE id=?',(body.draft_id,)).fetchone()
            if not row or row['owner']!=digest(token):raise HTTPException(404,'Draft not found for this administrator session')
            if row['status']=='published':return {'published':True,'already_published':True,'recipient_devices':len(json.loads(row['audience']))}
            if row['status']!='draft' or row['preview_until']<time.time():raise HTTPException(409,'Preview expired. Create a new preview.')
            ids=audience(c,row['district'],row['block'])
            if ids!=json.loads(row['audience']):raise HTTPException(409,'Audience changed. Preview again before publishing.')
            now=time.time();c.execute("UPDATE alerts SET status='published',published=? WHERE id=?",(now,row['id']))
            for identifier in ids:
                c.execute('INSERT OR IGNORE INTO inbox(alert_id,profile_id) VALUES(?,?)',(row['id'],identifier))
                c.execute('INSERT OR IGNORE INTO outbox(alert_id,profile_id) SELECT ?,? WHERE EXISTS(SELECT 1 FROM subscriptions WHERE profile_id=? AND enabled=1)',(row['id'],identifier,identifier))
            c.execute('INSERT INTO events(time,action,details) VALUES(?,?,?)',(now,'publish_alert',json.dumps({'alert_id':row['id'],'recipients':len(ids),'district':row['district'],'block':row['block']})))
        return {'published':True,'recipient_devices':len(ids),'push':'queued where enabled; acceptance is not proof of delivery'}
    @router.post('/admin/push/setup')
    def setup_push(body:PushSetup,request:Request,authorization:str|None=Header(default=None)):
        admin_auth(authorization);mutation(request)
        email=body.contact_email.strip()
        if '@' not in email or any(ch in email for ch in [' ','\n','\r']):raise HTTPException(422,'Enter a real contact email address')
        from push_delivery import configure
        return configure('mailto:'+email)
    @router.post('/farmer/push/test')
    def test_own_push(request:Request):
        mutation(request)
        with database() as c:
            row=farmer(request,c)
            region=c.execute('SELECT district,block FROM regions WHERE profile_id=? ORDER BY id LIMIT 1',(row['id'],)).fetchone()
            if not region:raise HTTPException(422,'Save an alert region first')
            if not c.execute('SELECT 1 FROM subscriptions WHERE profile_id=? AND enabled=1',(row['id'],)).fetchone():raise HTTPException(422,'Enable push notifications on this device first')
            if c.execute("SELECT 1 FROM alerts WHERE owner=? AND kind='test' AND created>?",(row['id'],time.time()-60)).fetchone():raise HTTPException(429,'Wait one minute before another test')
            from push_delivery import public_config
            if not public_config()['configured']:raise HTTPException(409,'Administrator must configure Web Push first')
            now=time.time();identifier=secrets.token_hex(16)
            messages={
                'English':{'title':'TEST · JalDrishti notification','body':'This is a notification delivery test for your device. It is not a groundwater warning.'},
                'Hindi':{'title':'परीक्षण · जलदृष्टि सूचना','body':'यह आपके उपकरण पर सूचना पहुँचने का परीक्षण है। यह भूजल की चेतावनी नहीं है।'},
                'Marathi':{'title':'चाचणी · जलदृष्टी सूचना','body':'ही तुमच्या उपकरणावर सूचना येण्याची चाचणी आहे. हा भूजलाचा इशारा नाही.'}}
            df=records();selected=df[df.district.eq(region['district'])]
            observed=selected.date.max().strftime('%Y-%m-%d')
            c.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,region['district'],region['block'],'test',json.dumps(messages,ensure_ascii=False),'https://cgwb.gov.in/en/ground-water-level-monitoring',observed,now+3600,'published',now,now,row['id'],now,json.dumps([row['id']])))
            c.execute('INSERT INTO inbox(alert_id,profile_id) VALUES(?,?)',(identifier,row['id']))
            c.execute('INSERT INTO outbox(alert_id,profile_id) VALUES(?,?)',(identifier,row['id']))
        return {'queued':True,'note':'Test is queued for this device only. Keep the provided backend runner active.'}
    @router.get('/admin/alerts')
    def alert_list(authorization:str|None=Header(default=None)):
        admin_auth(authorization)
        with database() as c:
            rows=c.execute("SELECT id,district,block,kind,source_url,observed_date,status,created,published,expires FROM alerts WHERE status!='draft' ORDER BY created DESC LIMIT 100").fetchall()
            result=[]
            for row in rows:
                item=dict(row);item['recipient_devices']=c.execute('SELECT COUNT(*) FROM inbox WHERE alert_id=?',(row['id'],)).fetchone()[0]
                item['push_status']={r['state']:r['count'] for r in c.execute('SELECT state,COUNT(*) count FROM outbox WHERE alert_id=? GROUP BY state',(row['id'],))}
                result.append(item)
            return {'items':result}
    @router.post('/admin/alerts/{alert_id}/withdraw')
    def withdraw(alert_id:str,request:Request,authorization:str|None=Header(default=None)):
        admin_auth(authorization);mutation(request)
        with database() as c:
            c.execute("UPDATE alerts SET status='withdrawn' WHERE id=? AND status='published'",(alert_id,))
            c.execute("UPDATE outbox SET state='cancelled' WHERE alert_id=? AND state IN ('queued','retry')",(alert_id,))
            c.execute('INSERT INTO events(time,action,details) VALUES(?,?,?)',(time.time(),'withdraw_alert',json.dumps({'alert_id':alert_id})))
        return {'withdrawn':True,'note':'Previously displayed phone notifications cannot be recalled; the inbox shows withdrawal.'}
    return router
