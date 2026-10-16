"""Match official IMD daily grids to wells; never replace missing rain with zero."""
from pathlib import Path
import pandas as pd

def features(observations, daily):
    outputs=[]
    daily=daily.copy();daily['date']=pd.to_datetime(daily.date).dt.normalize()
    if daily.duplicated(['station_key','date']).any(): raise ValueError('Duplicate daily rainfall dates.')
    daily['rain_mm']=pd.to_numeric(daily.rain_mm,errors='raise')
    daily.loc[daily.rain_mm<0,'rain_mm']=float('nan')
    for key,rows in observations.groupby('station_key'):
        rain=daily[daily.station_key.eq(key)].set_index('date').rain_mm.sort_index()
        if rain.empty: continue
        rain=rain.reindex(pd.date_range(rain.index.min(),rain.index.max(),freq='D'))
        for _,row in rows.iterrows():
            date=pd.Timestamp(row.date).normalize();record={'station_key':key,'date':row.date}
            for days in [30,90,180]:
                # Strictly before the observation day, including full windows only.
                window=rain.reindex(pd.date_range(date-pd.Timedelta(days=days),date-pd.Timedelta(days=1)))
                record[f'rain_{days}d_mm']=float(window.sum()) if window.notna().sum()==days else float('nan')
            outputs.append(record)
    return pd.DataFrame(outputs)

def import_grids(paths,observations):
    import xarray as xr
    import numpy as np
    stations=observations.drop_duplicates('station_key');parts=[]
    for path in paths:
        with xr.open_dataset(path) as ds:
            names={n.lower():n for n in ds.variables}
            lat=names.get('latitude',names.get('lat'));lon=names.get('longitude',names.get('lon'));time=names.get('time')
            var=names.get('rainfall')
            if not all([lat,lon,time,var]): raise ValueError('Expected IMD RAINFALL, LATITUDE, LONGITUDE, TIME variables.')
            if str(ds[var].attrs.get('units','')).lower() not in ['mm','millimeter','millimetres','millimeters']: raise ValueError('Rainfall units must be mm.')
            for axis in [lat,lon]:
                differences=np.abs(np.diff(ds[axis].values))
                if not len(differences) or not np.allclose(differences,.25,atol=1e-5): raise ValueError('Expected a 0.25-degree IMD grid.')
            for _,well in stations.iterrows():
                cell=ds[var].sel({lat:well.latitude,lon:well.longitude},method='nearest')
                if abs(float(cell[lat])-well.latitude)>.126 or abs(float(cell[lon])-well.longitude)>.126: continue
                parts.append(pd.DataFrame({'station_key':well.station_key,'date':pd.to_datetime(cell[time].values),'rain_mm':cell.values.reshape(-1),'grid_latitude':float(cell[lat]),'grid_longitude':float(cell[lon]),'source_file':Path(path).name}))
    if not parts: raise ValueError('No matching rainfall cells.')
    daily=pd.concat(parts,ignore_index=True)
    if daily.groupby(['station_key','date']).rain_mm.nunique().gt(1).any(): raise ValueError('Overlapping rainfall files disagree.')
    return daily.drop_duplicates(['station_key','date'])

if __name__=='__main__':
    import argparse
    from core import load_records,ROOT
    p=argparse.ArgumentParser();p.add_argument('files',nargs='+',type=Path);a=p.parse_args()
    df=load_records();daily=import_grids(a.files,df)
    daily.to_csv(ROOT/'data/rainfall_daily.csv',index=False)
    features(df,daily).to_csv(ROOT/'data/rainfall_features.csv',index=False)
    print('Saved matched daily rain and 30/90/180-day features. Missing windows remain unknown.')
