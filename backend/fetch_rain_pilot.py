"""Yavatmal pilot: ERA5 daily precipitation via Open-Meteo, never called IMD data."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import pandas as pd
from core import load_records,ROOT
BASE='https://archive-api.open-meteo.com/v1/archive'
def fetch(start='2014-01-01',end='2023-12-31'):
    stations=load_records();stations=stations[stations.district.eq('Yavatmal')].drop_duplicates('station_key').copy()
    stations['request_lat']=(stations.latitude*4).round()/4;stations['request_lon']=(stations.longitude*4).round()/4
    cells=stations[['request_lat','request_lon']].drop_duplicates().sort_values(['request_lat','request_lon']).values.tolist()
    frames=[];requests=[]
    for offset in range(0,len(cells),7):
        batch=cells[offset:offset+7]
        params={'latitude':','.join(str(v[0]) for v in batch),'longitude':','.join(str(v[1]) for v in batch),'start_date':start,'end_date':end,'daily':'precipitation_sum','models':'era5','timezone':'Asia/Kolkata','cell_selection':'nearest','elevation':','.join('nan' for _ in batch)}
        url=BASE+'?'+urlencode(params)
        with urlopen(url,timeout=60) as response: raw=response.read()
        results=json.loads(raw)
        if isinstance(results,dict):results=[results]
        if len(results)!=len(batch):raise ValueError('Missing weather locations')
        requests.append({'url':url,'sha256':hashlib.sha256(raw).hexdigest()})
        for requested,result in zip(batch,results):
            if result.get('daily_units',{}).get('precipitation_sum')!='mm':raise ValueError('Unexpected weather units')
            if abs(result['latitude']-requested[0])>.26 or abs(result['longitude']-requested[1])>.26:raise ValueError('Weather grid mismatch')
            rain=pd.DataFrame({'date':result['daily']['time'],'rain_mm':result['daily']['precipitation_sum']})
            rain['request_lat']=requested[0];rain['request_lon']=requested[1];rain['grid_latitude']=result['latitude'];rain['grid_longitude']=result['longitude'];frames.append(rain)
        print('Fetched weather cells',min(offset+len(batch),len(cells)),'/',len(cells),flush=True)
    rain=pd.concat(frames,ignore_index=True)
    if (rain.rain_mm.dropna()<0).any():raise ValueError('Negative precipitation')
    rain.to_csv(ROOT/'data/pilot_rain_cells.csv',index=False)
    stations[['station_key','station','district','source_tehsil','latitude','longitude','request_lat','request_lon']].to_csv(ROOT/'data/pilot_rain_station_map.csv',index=False)
    manifest={'provider':'Open-Meteo Historical Weather API','model':'ERA5 reanalysis','variable':'daily precipitation_sum','units':'mm','timezone':'Asia/Kolkata','coverage':'Yavatmal only','requested_start':start,'requested_end':end,'actual_start':rain.date.min(),'actual_end':rain.date.max(),'cell_count':len(cells),'station_histories':len(stations),'daily_cell_records':len(rain),'missing_values':int(rain.rain_mm.isna().sum()),'source_url':'https://open-meteo.com/en/docs/historical-weather-api','attribution':'Weather data by Open-Meteo, ERA5 / Copernicus. CC BY 4.0; API use terms apply.','imd_data':False,'retrieved_at':pd.Timestamp.now(tz='UTC').isoformat(),'requests':requests}
    (ROOT/'data/pilot_rain_manifest.json').write_text(json.dumps(manifest,indent=2));return manifest
if __name__=='__main__':print(json.dumps(fetch(),indent=2))
