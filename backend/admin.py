"""Local administrator authentication, validated data publishing and audit trail."""
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlparse
import pandas as pd
ROOT=Path(__file__).parent
PRIVATE=ROOT/'private'

def configure(password):
    if len(password)<12: raise ValueError('Use at least 12 characters.')
    PRIVATE.mkdir(exist_ok=True,mode=0o700)
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    target=PRIVATE/'admin.json'
    target.write_text(json.dumps({'salt':salt,'digest':digest}))
    target.chmod(0o600)

def verify(password):
    path=PRIVATE/'admin.json'
    if not path.exists(): return False
    config=json.loads(path.read_text())
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(config['salt']),600000).hex()
    return hmac.compare_digest(config['digest'],digest)

def validate_upload(content, existing, source_url):
    if len(content)>40*1024*1024: raise ValueError('Maximum upload size: 40 MB.')
    host=urlparse(source_url).hostname or ''
    if urlparse(source_url).scheme!='https' or not (host=='cgwb.gov.in' or host.endswith('.cgwb.gov.in') or host=='nwdp.nwic.gov.in'):
        raise ValueError('Provide an HTTPS CGWB or NWDP source URL.')
    df=pd.read_csv(io.BytesIO(content),dtype={'station_key':str})
    required=['station_key','station','district','source_tehsil','latitude','longitude','date','depth']
    if not set(required)<=set(df): raise ValueError('Missing columns: '+', '.join(sorted(set(required)-set(df))))
    df=df[required].copy()
    if df.empty: raise ValueError('Upload contains no observations.')
    for c in ['station_key','station','district']:
        if df[c].isna().any() or df[c].str.strip().eq('').any(): raise ValueError('Missing station identity.')
        df[c]=df[c].str.strip()
    if not df.district.isin(existing.district.unique()).all(): raise ValueError('District names must match the supplied Maharashtra template.')
    df['date']=pd.to_datetime(df.date,errors='raise',format='mixed')
    if df.date.isna().any() or (df.date>pd.Timestamp.now()).any(): raise ValueError('Missing/future observation dates.')
    for c in ['latitude','longitude','depth']: df[c]=pd.to_numeric(df[c],errors='raise')
    if not df.latitude.between(15,23).all() or not df.longitude.between(72,81).all(): raise ValueError('Coordinates outside the Maharashtra review envelope.')
    if df.depth.isna().any() or not df.depth.between(-10,500).all(): raise ValueError('Depths must be finite, between -10 and 500 m; review unusual values.')
    # Station metadata must remain stable across old and new rows.
    combined=pd.concat([existing[required],df],ignore_index=True)
    identity=combined.groupby('station_key')[['station','district','latitude','longitude']].nunique()
    if identity.gt(1).any().any(): raise ValueError('A station key maps to different names or coordinates. Review identity before importing.')
    if combined.groupby(['station_key','date']).depth.nunique().gt(1).any(): raise ValueError('Conflicting readings for the same station and date.')
    df['source_url']=source_url
    return df.drop_duplicates(['station_key','date'])

def publish(df, existing, source_url):
    PRIVATE.mkdir(exist_ok=True,mode=0o700)
    stamp=time.time_ns(); path=ROOT/'data/observations.csv'
    backup=PRIVATE/f'observations_{stamp}.csv';backup.write_bytes(path.read_bytes())
    current=pd.read_csv(path)
    current["date"]=pd.to_datetime(current.date)
    if not current.reset_index(drop=True).equals(existing.reset_index(drop=True)): raise ValueError('Dataset changed; refresh and review the upload again.')
    merged=pd.concat([existing,df],ignore_index=True).drop_duplicates(['station_key','date'],keep='first').sort_values(['date','station_key'])
    temp=path.with_suffix('.tmp');merged.to_csv(temp,index=False);os.replace(temp,path)
    with (PRIVATE/'audit.jsonl').open('a') as f:
        f.write(json.dumps({'time':pd.Timestamp.now().isoformat(),'action':'publish_observations','added':len(merged)-len(existing),'source':source_url,'backup':backup.name})+'\n')
    return len(merged)-len(existing)

def panel(df, words):
    import streamlit as st
    st.subheader(words('admin'))
    if not (PRIVATE/'admin.json').exists():
        st.info(words('admin_setup'));st.code('./.venv/bin/python JalDrishti_v2/admin.py setup');return
    now=time.time()
    if not st.session_state.get('admin_until',0)>now:
        with st.form('admin_login'):
            password=st.text_input(words('password'),type='password')
            login=st.form_submit_button(words('login'))
        if login:
            if now<st.session_state.get('retry_after',0): st.error(words('wait_login'))
            elif verify(password): st.session_state['admin_until']=now+900;st.rerun()
            else:
                st.session_state['retry_after']=now+5;st.error(words('bad_password'))
        return
    st.caption(words('local_admin_note'))
    if st.button(words('logout')): st.session_state['admin_until']=0;st.rerun()
    if not (ROOT/'data/rainfall_features.csv').exists(): st.info(words('rain_pending'))
    st.write(words('dataset_status'))
    st.json({'records':len(df),'stations':df.station_key.nunique(),'first_date':str(df.date.min().date()),'latest_date':str(df.date.max().date()),'missing_depths':int(df.depth.isna().sum())})
    st.download_button(words('template'),df.head(0).drop(columns=['source_url'],errors='ignore').to_csv(index=False),'observation_template.csv')
    source=st.text_input(words('source_url'),key='import_source')
    upload=st.file_uploader(words('upload'),type=['csv'])
    if upload:
        try:
            content=upload.getvalue();preview=validate_upload(content,df,source)
            st.dataframe(preview.head(30),hide_index=True)
            st.write(words('preview_count').format(count=len(preview)))
            approved=st.checkbox(words('review_coordinates'))
            if st.button(words('publish'),disabled=not approved):
                count=publish(preview,df,source);st.cache_data.clear();st.success(words('published').format(count=count));st.rerun()
        except (ValueError,TypeError,KeyError) as e: st.error(str(e))
    if (PRIVATE/'audit.jsonl').exists():
        with st.expander(words('audit')):
            st.code((PRIVATE/'audit.jsonl').read_text()[-15000:])
            st.download_button(words('audit'),(PRIVATE/'audit.jsonl').read_bytes(),'audit.jsonl','application/jsonl')

if __name__=='__main__':
    import getpass,sys
    if sys.argv[1:]!=['setup']: raise SystemExit('Usage: python admin.py setup')
    p=getpass.getpass('New administrator password (12+ characters): ')
    if p!=getpass.getpass('Repeat password: '): raise SystemExit('Passwords do not match.')
    configure(p);print('Administrator configured. Keep the app bound to localhost.')
