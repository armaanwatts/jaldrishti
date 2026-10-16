"""Historical replay with an explicit separation of global and rainfall experiments."""
from functools import lru_cache
import json
import pandas as pd
import numpy as np
from core import ROOT,load_records

@lru_cache(maxsize=2)
def tables(version):
    rain_test=pd.read_csv(ROOT/'outputs/pilot_test_predictions.csv')
    global_test=pd.read_csv(ROOT/'outputs/seasonal_test_2023.csv')
    names=load_records().drop_duplicates('station_key').set_index('station_key').station.to_dict()
    global_test['station']=global_test.station_key.map(names)
    global_test['colour']=np.where(global_test.historical_watch_candidate,'red',np.where(global_test.predicted_depth>global_test.threshold,'amber','green'))
    global_test.loc[global_test.threshold.isna(),'colour']='grey'
    global_test['actual_colour']=np.where(global_test.actual_above_threshold,'red','green')
    report=json.loads((ROOT/'outputs/pilot_report.json').read_text())
    warning_report=json.loads((ROOT/'outputs/seasonal_evaluation.json').read_text())
    valid=global_test[global_test.threshold.notna()]
    predicted=valid.historical_watch_candidate.eq(True);actual=valid.actual_above_threshold.eq(True)
    warning_report['computed_confusion']={'true_positive':int((predicted&actual).sum()),'false_positive':int((predicted&~actual).sum()),'false_negative':int((~predicted&actual).sum()),'true_negative':int((~predicted&~actual).sum()),'eligible_test_measurements':len(valid)}
    cases=json.loads((ROOT/'outputs/pilot_cases.json').read_text())
    return global_test,rain_test,report,warning_report,cases

def load():return tables((ROOT/'outputs/pilot_report.json').stat().st_mtime_ns)

def pilot(district,station=None,block=None,month=5):
    global_test,rain_test,report,warning_report,cases=load()
    data=global_test[global_test.district.eq(district)&global_test.month.eq(month)].copy()
    if block:data=data[data.source_tehsil.eq(block)]
    if station:data=data[data.station_key.eq(station)]
    data['rank']=data.colour.map({'red':0,'amber':1,'green':2,'grey':3});data=data.sort_values(['rank','station'])
    selected_cases=cases.get(f'{station}|2023|{month}',[]) if station and district=='Yavatmal' else []
    manifest=json.loads((ROOT/'data/pilot_rain_manifest.json').read_text()) if district=='Yavatmal' else None
    return {'available':True,'historical_only':True,'target_year':2023,'target_month':month,'warning_report':warning_report,'report':report if district=='Yavatmal' else None,'rows':json.loads(data.drop(columns='rank').to_json(orient='records',date_format='iso')),'cases':selected_cases,'rainfall':manifest,'colour_counts':{key:int(data.colour.eq(key).sum()) for key in ['red','amber','green','grey']},'colour_rule':'Groundwater-only global backtest: red = lower empirical prediction bound exceeds training district/season 90th percentile; amber = point estimate exceeds threshold; green = neither, not safe; grey = insufficient data.'}

def rain_series(station=None):
    mapping=pd.read_csv(ROOT/'data/pilot_rain_station_map.csv');rain=pd.read_csv(ROOT/'data/pilot_rain_cells.csv')
    rain=rain[rain.date.str.startswith('2023')].copy()
    if station:
        match=mapping[mapping.station_key.eq(station)]
        if match.empty:return []
        row=match.iloc[0];rain=rain[rain.request_lat.eq(row.request_lat)&rain.request_lon.eq(row.request_lon)]
    rain['month']=rain.date.str[:7]
    cells=rain.groupby(['request_lat','request_lon','month'],as_index=False).rain_mm.sum(min_count=1)
    return json.loads(cells.groupby('month',as_index=False).rain_mm.mean().to_json(orient='records'))

def examples():
    data,_,_,_,_=load();data=data[data.colour.eq('red')]
    return json.loads(data[['district','station','station_key','month','predicted_depth','target_depth','actual_above_threshold']].to_json(orient='records'))
