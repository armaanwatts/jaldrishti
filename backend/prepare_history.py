"""Normalize official NWDP exports; never join stations by village name alone."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from core import canonical
ROOT = Path(__file__).parent
BASE = 'https://nwdp.nwic.gov.in/dataset/956add67-cba9-41a5-9d5c-96d73db44aef/resource/'
SOURCES = [('0e7180fa-5282-4df6-bead-8ca7a7557e74','1991_2020'),('073029e8-492d-416c-9857-3ad3e27c69a6','2021_2025')]
def normalize(raw, url):
    out = raw.rename(columns={'Station':'station','District':'district','Tehsil':'source_tehsil','Latitude':'latitude','Longitude':'longitude','Data Acquisition Time':'date','Groundwater Level Quarterly Manual (meter)':'depth'}).copy()
    out['district'] = out.district.map(canonical)
    out['date'] = pd.to_datetime(out.date, dayfirst=True, errors='raise')
    for c in ['latitude','longitude','depth']: out[c]=pd.to_numeric(out[c],errors='raise')
    # Match the original exact source-coordinate key, without rounding or fuzzy names.
    out['station_key']=[hashlib.sha256(f'{d}|{s}|{lat}|{lon}'.encode()).hexdigest()[:16] for d,s,lat,lon in zip(out.district,out.station,out.latitude,out.longitude)]
    out['source_url']=url
    return out[['station_key','station','district','source_tehsil','latitude','longitude','date','depth','source_url']]
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--raw-folder',type=Path,required=True);a=p.parse_args()
    parts=[]
    for resource,years in SOURCES:
        url=BASE+resource+'/download/gwl_manual_quarterly_cgwb_mh_'+years+'.csv'
        parts.append(normalize(pd.read_csv(a.raw_folder/('mh_'+years+'.csv')),url))
    df=pd.concat(parts,ignore_index=True).drop_duplicates()
    conflicts=df.groupby(['station_key','date']).depth.nunique().gt(1)
    if conflicts.any(): raise ValueError('Conflicting station/date readings require review.')
    df=df.drop_duplicates(['station_key','date']).sort_values(['date','station_key'])
    df.to_csv(ROOT/'data/observations.csv',index=False)
    print(json.dumps({'records':len(df),'stations':df.station_key.nunique(),'first':str(df.date.min()),'last':str(df.date.max())},indent=2))
