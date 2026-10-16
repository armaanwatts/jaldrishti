"""Review-only official telemetry snapshot. Never infer its sign convention."""
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.request import urlopen,Request
import pandas as pd
from core import ROOT,canonical
URL='https://nwdp.nwic.gov.in/dataset/3e0f97ab-5bf6-498f-96c5-7b23dfdb9a70/resource/7a821ef4-b73b-4243-9a42-4f1a6f300230/download/gwl_tel_6_hourly_maharashtra_gw_mh_2026_2030.csv'
PAGE='https://nwdp.nwic.gov.in/dataset/ground-water-level-telemetry-daily-maharashtra-gw'

def prepare(path):
    collected=[];rows=0;negative=0;positive=0;first=None;last=None
    value='Groundwater Level Telemetry 6 Hourly (meter)'
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):digest.update(b)
    for part in pd.read_csv(path,chunksize=100000):
        required={'Station','District','Latitude','Longitude','Data Acquisition Time',value}
        if not required<=set(part):raise ValueError('Unexpected telemetry schema')
        part=part.rename(columns={'Station':'station','District':'district','Tehsil':'source_tehsil','Latitude':'latitude','Longitude':'longitude','Data Acquisition Time':'date',value:'raw_level_m'})
        part['date']=pd.to_datetime(part.date,dayfirst=True,errors='raise')
        for c in ['latitude','longitude','raw_level_m']:part[c]=pd.to_numeric(part[c],errors='raise')
        part['district']=part.district.map(canonical)
        if not part.latitude.between(15,23).all() or not part.longitude.between(72,81).all():raise ValueError('Coordinates outside Maharashtra review envelope')
        if (part.date>pd.Timestamp.now()).any():raise ValueError('Source contains future-dated records')
        rows+=len(part);negative+=int((part.raw_level_m<0).sum());positive+=int((part.raw_level_m>=0).sum())
        first=min(first,part.date.min()) if first is not None else part.date.min();last=max(last,part.date.max()) if last is not None else part.date.max()
        keys=['station','district','latitude','longitude']
        collected.append(part.sort_values('date').drop_duplicates(keys,keep='last')[keys+['source_tehsil','date','raw_level_m']])
    latest=pd.concat(collected,ignore_index=True).sort_values('date').drop_duplicates(['station','district','latitude','longitude'],keep='last')
    latest['telemetry_key']=[hashlib.sha256(f'MH_GW_TELEMETRY|{d}|{s}|{lat}|{lon}'.encode()).hexdigest()[:16] for d,s,lat,lon in zip(latest.district,latest.station,latest.latitude,latest.longitude)]
    manifest={'source_url':PAGE,'download_url':URL,'checked_at':pd.Timestamp.now(tz='UTC').isoformat(),'first_observation':first.isoformat(),'latest_observation':last.isoformat(),'raw_record_count':rows,'station_count':len(latest),'negative_values':negative,'nonnegative_values':positive,'sha256':digest.hexdigest(),'download_complete':True,'integration_status':'review_only','measurement_convention_verified':False,'used_for_forecasting':False,'issues':['Signed values need an authoritative measurement-convention review; no absolute-value conversion performed.','Dataset page producer-agency metadata says Madhya Pradesh GW despite Maharashtra title and rows. Review source metadata.','Telemetry identities are separate from CGWB manual station keys.','This snapshot does not establish that every station is current or healthy.']}
    latest.to_csv(ROOT/'data/latest_telemetry_stations.csv',index=False)
    (ROOT/'data/latest_source_manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def refresh():
    # Public, fixed source only; no arbitrary URLs or embedded credentials.
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'telemetry.csv';size=0
        with urlopen(Request(URL),timeout=120) as response,path.open('wb') as output:
            for block in iter(lambda:response.read(1024*1024),b''):
                size+=len(block)
                if size>200*1024*1024:raise ValueError('Download exceeded 200 MB review limit')
                output.write(block)
        return prepare(path)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--local-file',type=Path);a=p.parse_args()
    print(json.dumps(prepare(a.local_file) if a.local_file else refresh(),indent=2))
