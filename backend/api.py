"""Local FastAPI service. Run behind localhost; no public account service implied."""
from functools import lru_cache
from pathlib import Path
from typing import Literal
import os
import hashlib
import json
import secrets
import threading
import time
import pandas as pd
from fastapi import FastAPI,HTTPException,Header,UploadFile,File,Form,Request
from fastapi.responses import HTMLResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from core import load_records,latest_stations,retrieve,local_answer,status_message,current_status,summary_facts,ROOT,MODEL
from i18n import district_name
from map_view import map_payload,render_map
from admin import verify,validate_upload,publish,PRIVATE

app=FastAPI(title='JalDrishti PS06',version='0.1.0')
@app.middleware('http')
async def private_api_cache(request,call_next):
    if request.url.path in ('/api/ask','/api/advisory') and request.method=='POST':
        key=request.client.host if request.client else 'unknown';now=time.time()
        with lock:
            recent=[v for v in request_times.get(key,[]) if now-v<60]
            if len(recent)>=6:
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail':'Please wait before asking another question.'},status_code=429)
            request_times[key]=recent+[now]
            if len(request_times)>2000:request_times.clear()
    response=await call_next(request)
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    return response

Language=Literal['English','Hindi','Marathi']
lock=threading.Lock();sessions={};pending={};failures=[];request_times={}
@lru_cache(maxsize=2)
def _records(version): return load_records()
def records(): return _records((ROOT/'data/observations.csv').stat().st_mtime_ns)
@lru_cache(maxsize=1)
def geo():
    return {key:json.loads((ROOT/'data'/filename).read_text()) for key,filename in {'states':'india_states.geojson','districts':'districts.geojson','blocks':'blocks.geojson'}.items()}
def subset(district,station=None,block=None):
    df=records();out=df[df.district.eq(district)]
    if out.empty: raise HTTPException(404,'District not found')
    if block: out=out[out.source_tehsil.eq(block)]
    if station: out=out[out.station_key.eq(station)]
    if out.empty: raise HTTPException(404,'No matching station records')
    return out

@app.get('/api/health')
def health(): return {'ok':True,'rainfall_loaded':((ROOT/'data/rainfall_features.csv').exists() or (ROOT/'data/pilot_rain_manifest.json').exists()),'live_forecast_enabled':False,'admin_configured':(PRIVATE/'admin.json').exists()}
@app.get('/api/districts')
def districts(language:Language='English'):
    return [{'value':d,'label':district_name(d,language)} for d in sorted(records().district.unique())]
@app.get('/api/district-directory')
def district_directory(language:Language='English'):
    result=[]
    for name,df in records().groupby('district'):
        last=df.date.max(); recent=df[df.date.eq(last)].dropna(subset=['depth'])
        result.append({'district':name,'label':district_name(name,language),'stations':int(df.station_key.nunique()),'readings':len(df),'blocks':int(df.source_tehsil.nunique()),'first_date':str(df.date.min().date()),'latest_date':str(last.date()),'round_wells':int(recent.station_key.nunique()),'round_median_m':None if recent.empty else round(float(recent.depth.median()),2),'current_forecast':False,'rainfall_pilot':name=='Yavatmal'})
    return result

@app.get('/api/overview')
def overview(district:str='Yavatmal',station:str|None=None,block:str|None=None):
    df=subset(district,station,block)
    return {'stations':int(df.station_key.nunique()),'readings':len(df),'first_date':str(df.date.min().date()),'latest_date':str(df.date.max().date()),'freshness':current_status(df),'rainfall_loaded':((ROOT/'data/rainfall_features.csv').exists() or (ROOT/'data/pilot_rain_manifest.json').exists())}
@app.get('/api/stations')
def stations(district:str='Yavatmal',block:str|None=None):
    df=subset(district,block=block);rows=latest_stations(df).sort_values('station')
    return json.loads(rows[['station_key','station','source_tehsil','latitude','longitude']].to_json(orient='records'))
@app.get('/api/blocks')
def blocks(district:str='Yavatmal'): return sorted(subset(district).source_tehsil.dropna().unique().tolist())
@app.get('/api/history')
def history(district:str='Yavatmal',station:str|None=None,block:str|None=None):
    df=subset(district,station,block).dropna(subset=['depth']).copy();df['month']=df.date.dt.to_period('M').dt.to_timestamp()
    monthly=df.groupby(['station_key','month'],as_index=False).depth.median()
    grouped=monthly.groupby('month').agg(depth=('depth','median'),lower=('depth',lambda s:s.quantile(.25)),upper=('depth',lambda s:s.quantile(.75)),count=('station_key','nunique')).reset_index()
    grouped['date']=grouped.month.dt.strftime('%Y-%m');return json.loads(grouped.drop(columns='month').to_json(orient='records'))
@app.get('/api/map',response_class=HTMLResponse)
def map_html(district:str='Yavatmal',station:str|None=None,block:str|None=None,language:Language='English',view:Literal['state','district','well','india']='district',pilot_month:int|None=None):
    subset(district,station,block)
    payload=map_payload(records(),geo(),district,station,language,view,block or '__all__')
    path=ROOT/'outputs/seasonal_test_2023.csv'
    if path.exists():
        test=pd.read_csv(path);test=test[test.district.eq(district) & test.historical_watch_candidate.eq(True)]
        if block: test=test[test.source_tehsil.eq(block)]
        payload['historical_watch']=json.loads(test[['latitude','longitude','year','month','predicted_depth']].to_json(orient='records'))
    recent=ROOT/'data/latest_telemetry_stations.csv'
    if recent.exists():
        latest=pd.read_csv(recent);latest=latest[latest.district.eq(district)]
        if block: latest=latest[latest.source_tehsil.eq(block)]
        payload['review_telemetry']=json.loads(latest.to_json(orient='records'))
    payload['telemetry_label']={'English':'2026 telemetry · raw values under review','Hindi':'2026 टेलीमेट्री · मान की जाँच बाकी','Marathi':'2026 टेलिमेट्री · मूल्यांची तपासणी बाकी'}[language]
    if pilot_month is not None:
        from pilot_api import pilot
        replay=pilot(district,station,block,pilot_month)
        # Keep all district markers visible even if a single manual well is selected.
        all_replay=pilot(district,None,block,pilot_month)
        by_key={r['station_key']:r for r in all_replay['rows']}
        for point in payload['points']:
            item=by_key.get(point['id'])
            point['pilot_colour']=item['colour'] if item else 'grey'
            point['pilot_target']='2023-'+str(pilot_month).zfill(2)
            if item:
                point['pilot_prediction']=item['predicted_depth'];point['pilot_actual']=item['target_depth']
        payload['pilot_labels']={'English':['Historical estimate','Actual measurement','Experimental anomaly; not a current crisis rating'],'Hindi':['पुराना अनुमान','असली माप','प्रयोगात्मक संकेत; आज के संकट का आकलन नहीं'],'Marathi':['जुना अंदाज','प्रत्यक्ष मोजणी','प्रायोगिक संकेत; आजच्या संकटाचे मूल्यांकन नाही']}[language]
    payload['watch_label']={'English':'Experimental historical watch (2023) · not crisis zones','Hindi':'2023 के पुराने शोध संकेत · संकट क्षेत्र नहीं','Marathi':'2023 चे जुने प्रायोगिक संकेत · संकट क्षेत्र नाहीत'}[language]
    return render_map(payload)

class Question(BaseModel):
    question:str=Field(min_length=1,max_length=1200)
    district:str='Yavatmal'
    station:str|None=None
    language:Language='English'
@app.post('/api/ask')
def ask(q:Question):
    subset(q.district,q.station)
    found=retrieve(records(),q.question,q.district,q.station)
    from latest_chat import latest_reply
    fresh=latest_reply(q.question,found['districts'],q.language,q.station) if found['status'] not in ('unsupported','future') else None
    if fresh is not None:return fresh
    evidence=found['facts']
    if found['status']!='ok' or not evidence: return {'answer':status_message(found['status'],q.language),'facts':evidence,'generated':False}
    try: answer=local_answer(q.question,evidence,q.language)
    except Exception as e: raise HTTPException(503,'Local model is busy; retry after the current answer finishes.' if 'busy' in str(e).lower() else 'AI service is unavailable or the answer failed evidence checks. Ask the administrator to check model settings.') from e
    return {**answer,'facts':evidence,'generated':True}
@app.get('/api/latest')
def latest_source(district:str='Yavatmal'):
    subset(district)
    manifest_path=ROOT/'data/latest_source_manifest.json'
    snapshot=ROOT/'data/latest_telemetry_stations.csv'
    if not manifest_path.exists() or not snapshot.exists():
        return {'source_url':'https://nwdp.nwic.gov.in/dataset/ground-water-level-telemetry-daily-maharashtra-gw','stations':[],'station_count':0,'manifest':{'integration_status':'not_loaded'}}
    manifest=json.loads(manifest_path.read_text());data=pd.read_csv(snapshot)
    data=data[data.district.eq(district)].sort_values('date',ascending=False)
    return {'source_url':manifest['source_url'],'checked_at':manifest['checked_at'],
            'latest_observation':str(data.date.max()) if len(data) else None,'station_count':len(data),
            'stations':json.loads(data.to_json(orient='records')),'manifest':manifest}

@app.get('/api/readiness')
def readiness():
    return {'cgwb':True,'rainfall_importer':True,'rainfall_data':((ROOT/'data/rainfall_features.csv').exists() or (ROOT/'data/pilot_rain_manifest.json').exists()) or (ROOT/'data/pilot_rain_manifest.json').exists(),'rainfall_coverage':'Yavatmal ERA5 pilot; not IMD','seasonal_backtest':(ROOT/'outputs/seasonal_evaluation.json').exists(),'validated_crisis_warnings':False,'local_llm':'qwen3:4b-instruct-2507-q4_K_M','backend':'FastAPI','dashboard':'React','current_forecast':False,'new_telemetry_review_snapshot':(ROOT/'data/latest_source_manifest.json').exists()}
@app.get('/api/seasonal')
def seasonal(district:str='Yavatmal',station:str|None=None):
    subset(district,station)
    report=ROOT/'outputs/seasonal_evaluation.json'
    result={'current_enabled':False,'reason':'Historical observations end in 2023. Rainfall and operational warning validation are incomplete.'}
    if report.exists(): result['evaluation']=json.loads(report.read_text())
    predictions=ROOT/'outputs/seasonal_test_2023.csv'
    if predictions.exists():
        df=pd.read_csv(predictions);df=df[df.district.eq(district)]
        if station: df=df[df.station_key.eq(station)]
        result['historical_examples']=json.loads(df.head(200).to_json(orient='records'))
        counts=df.groupby('source_tehsil').agg(test_readings=('station_key','size'),monitored_station_keys=('station_key','nunique'),experimental_candidates=('historical_watch_candidate','sum')).reset_index()
        result['block_research_summary']=json.loads(counts.to_json(orient='records'))
    return result

@app.post('/api/advisory')
def advisory(q:Question):
    if not q.station: raise HTTPException(422,'Select a monitoring well first')
    rows=subset(q.district,q.station)
    path=ROOT/'outputs/seasonal_test_2023.csv'
    if not path.exists(): raise HTTPException(409,'Historical model evaluation not available')
    test=pd.read_csv(path);test=test[test.station_key.eq(q.station)]
    if test.empty: raise HTTPException(404,'No historical test prediction for this station')
    row=test.sort_values(['year','month']).iloc[-1]
    fact={'id':'R1','label':q.district,'station':str(rows.iloc[0].station),
          'source':'https://nwdp.nwic.gov.in/dataset/gwl-manual-quarterly-central-ground-water-board-department',
          'historical_model_output':True,'current_supported':False,'forecast_supported':False,
          'origin_date':str(row.origin_date)[:10],'target_month':f'{int(row.year)}-{int(row.month):02}',
          'predicted_depth_m':round(float(row.predicted_depth),2),'observed_depth_m':round(float(row.target_depth),2),
          'lower_depth_m':round(float(row.lower_depth),2),'upper_depth_m':round(float(row.upper_depth),2),
          'uncertainty_is_empirical_not_guaranteed':True,'rainfall_used':False}
    try: answer=local_answer('Explain this historical next-round prediction simply, compare the actual measurement, and explain uncertainty. Do not give present-day farming or pumping advice.',[fact],q.language)
    except Exception as e: raise HTTPException(503,'AI service unavailable or explanation failed evidence checks') from e
    return {**answer,'facts':[fact],'generated':True}

class Login(BaseModel): password:str=Field(min_length=1,max_length=256)
def auth(authorization):
    token=authorization.removeprefix('Bearer ') if authorization else ''
    if sessions.get(token,0)<time.time(): raise HTTPException(401,'Administrator session expired')
    return token
@app.post('/api/admin/login')
def login(body:Login,request:Request):
    if request.url.scheme!='https' and request.client and request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Remote administrator login requires HTTPS')
    with lock:
        now=time.time();failures[:]=[x for x in failures if x>now-300]
        if len(failures)>=5: raise HTTPException(429,'Wait five minutes before another attempt')
        if not verify(body.password): failures.append(now);raise HTTPException(401,'Incorrect password or administrator not configured')
        sessions.clear();pending.clear();token=secrets.token_urlsafe(32);sessions[token]=now+900
    return {'token':token,'expires_in':900}
@app.post('/api/admin/logout')
def logout(authorization:str|None=Header(default=None)):
    token=auth(authorization)
    with lock:
        sessions.pop(token,None)
        for k in list(pending):
            if pending[k]['token']==token: pending.pop(k)
    return {'ok':True}
@app.post('/api/admin/preview')
async def preview(file:UploadFile=File(...),source_url:str=Form(...),authorization:str|None=Header(default=None)):
    token=auth(authorization);content=await file.read(40*1024*1024+1)
    try: df=validate_upload(content,records(),source_url)
    except Exception as e: raise HTTPException(422,str(e)) from e
    now=time.time()
    with lock:
        for k in list(pending):
            if pending[k]['expires']<now: pending.pop(k)
        if len(pending)>=5: raise HTTPException(429,'Publish or discard previous previews by signing out')
        key=secrets.token_urlsafe(24);pending[key]={'df':df,'source':source_url,'version':(ROOT/'data/observations.csv').stat().st_mtime_ns,'token':token,'expires':now+600}
    return {'preview_id':key,'rows':len(df),'preview':json.loads(df.head(20).to_json(orient='records',date_format='iso'))}
class Publish(BaseModel): preview_id:str;reviewed:bool=False
@app.post('/api/admin/publish')
def publish_data(body:Publish,authorization:str|None=Header(default=None)):
    token=auth(authorization)
    with lock:
        item=pending.get(body.preview_id)
        if not item or item['token']!=token or item['expires']<time.time(): raise HTTPException(400,'Preview expired')
        if not body.reviewed: raise HTTPException(400,'Review station identity, source and coordinates first')
        if item['version']!=(ROOT/'data/observations.csv').stat().st_mtime_ns: raise HTTPException(409,'Data changed. Preview the upload again.')
        try: added=publish(item['df'],records(),item['source'])
        except ValueError as e: raise HTTPException(409,str(e)) from e
        pending.pop(body.preview_id);_records.cache_clear()
    return {'added':added}
@app.get('/api/admin/audit')
def audit(authorization:str|None=Header(default=None)):
    auth(authorization);path=PRIVATE/'audit.jsonl'
    return {'entries':[json.loads(x) for x in path.read_text().splitlines()][-100:] if path.exists() else []}

@app.get('/api/pilot')
def pilot_replay(district:str='Yavatmal',station:str|None=None,block:str|None=None,month:int=5):
    subset(district,station,block)
    if month not in (1,5,8,11):raise HTTPException(422,'Choose a survey month')
    from pilot_api import pilot
    return pilot(district,station,block,month)
@app.get('/api/pilot/examples')
def pilot_examples():
    from pilot_api import examples
    return examples()

@app.get('/api/pilot/rain')
def pilot_rain(station:str|None=None):
    from pilot_api import rain_series
    return rain_series(station)
@app.get('/api/inference/status')
def inference_status():
    from inference import status
    return {'model':MODEL,**status()}
@app.post('/api/admin/inference/warm')
def warm_inference(request:Request,authorization:str|None=Header(default=None)):
    auth(authorization)
    from community import mutation
    mutation(request)
    if os.getenv('LLM_BASE_URL'):
        return {'ready':True,'model':MODEL,'note':'Hosted model configured; local warm-up is not applicable.'}
    from urllib.request import urlopen,Request as URLRequest
    try:
        body=json.dumps({'model':MODEL,'keep_alive':'20m','stream':False}).encode()
        with urlopen(URLRequest('http://127.0.0.1:11434/api/generate',data=body,headers={'Content-Type':'application/json'}),timeout=180) as response:result=json.load(response)
        return {'ready':True,'model':MODEL,'load_seconds':round(result.get('load_duration',0)/1e9,2)}
    except Exception as e:raise HTTPException(503,'Open Ollama and check that the model is installed') from e

from community import create_router
app.include_router(create_router(records,auth))

@app.get('/sw.js')
def service_worker():
    return FileResponse(ROOT.parent/'frontend/dist/sw.js',media_type='application/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

@app.get('/admin',response_class=HTMLResponse)
@app.get('/farmer',response_class=HTMLResponse)
def farmer_app():
    return FileResponse(ROOT.parent/'frontend/dist/index.html')

# Built React is served from the same localhost origin as the API.
DIST=ROOT.parent/'frontend/dist'
if DIST.exists(): app.mount('/',StaticFiles(directory=DIST,html=True),name='dashboard')
