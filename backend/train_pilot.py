"""Predeclared Yavatmal rainfall ablation + case-based next-round backtest."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from core import ROOT,load_records
from train_seasonal import build_pairs

def attach_rain(pairs):
    cells=pd.read_csv(ROOT/'data/pilot_rain_cells.csv');cells['date']=pd.to_datetime(cells.date)
    mapping=pd.read_csv(ROOT/'data/pilot_rain_station_map.csv')[['station_key','request_lat','request_lon']]
    records=[]
    for (lat,lon),group in cells.groupby(['request_lat','request_lon']):
        daily=group.set_index('date').rain_mm.sort_index()
        daily=daily.reindex(pd.date_range(daily.index.min(),daily.index.max(),freq='D'))
        data=pd.DataFrame({'origin_day':daily.index+pd.Timedelta(days=1),'request_lat':lat,'request_lon':lon})
        for days in [30,90,180]:data[f'rain_{days}d_mm']=daily.rolling(days,min_periods=days).sum().values
        records.append(data)
    rain=pd.concat(records,ignore_index=True)
    pairs=pairs.copy();pairs['origin_day']=pd.to_datetime(pairs.origin_date).dt.normalize()
    return pairs.merge(mapping,on='station_key',validate='many_to_one').merge(rain,on=['origin_day','request_lat','request_lon'],how='left',validate='many_to_one')

def anomaly(values,low,high):return np.where(values>high,'red',np.where(values>low,'amber','green'))

def train():
    observations=load_records();observations=observations[observations.district.eq('Yavatmal')]
    pairs=attach_rain(build_pairs(observations));raincols=['rain_30d_mm','rain_90d_mm','rain_180d_mm']
    pairs=pairs[pairs.year.ge(2015)].dropna(subset=raincols).copy()
    basecols=['last_depth','prior_year_depth','origin_month','month','latitude','longitude'];cols=basecols+raincols
    training=pairs[pairs.year.le(2020)].copy().reset_index(drop=True);val=pairs[pairs.year.eq(2022)].copy();test=pairs[pairs.year.eq(2023)].copy()
    if min(len(training),len(val),len(test))<20:raise ValueError('Too few paired readings')
    models={
        'gradient_no_rain':HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,l2_regularization=1,early_stopping=False,random_state=42),
        'gradient_rain':HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,l2_regularization=1,early_stopping=False,random_state=42),
        'cbr_rain':make_pipeline(StandardScaler(),KNeighborsRegressor(n_neighbors=8,weights='distance'))}
    for name,model in models.items():model.fit(training[basecols if name=='gradient_no_rain' else cols],training.target_depth)
    thresholds=training.groupby(['station_key','month']).target_depth.agg(samples='size',q75=lambda v:v.quantile(.75),q90=lambda v:v.quantile(.9)).reset_index()
    thresholds=thresholds[thresholds.samples.ge(4)]
    predictions={};scores=[];radii={}
    for split_name,frame in [('validation_2022',val),('test_2023',test)]:
        result=frame.copy();result['seasonal_baseline']=result.prior_year_depth
        for name,model in models.items():result[name]=model.predict(result[basecols if name=='gradient_no_rain' else cols])
        for name in ['seasonal_baseline',*models]:
            if split_name=='validation_2022':
                residual=np.sort(np.abs(result.target_depth-result[name]));rank=min(len(residual)-1,int(np.ceil((len(residual)+1)*.9))-1);radii[name]=float(residual[rank])
            scores.append({'split':split_name,'method':name,'measurements':len(result),'mae_m':float(np.abs(result.target_depth-result[name]).mean()),'empirical_interval_coverage':float((np.abs(result.target_depth-result[name])<=radii[name]).mean())})
        predictions[split_name]=result
    validation=[s for s in scores if s['split']=='validation_2022'];selected=min(validation,key=lambda s:s['mae_m'])['method']
    test_result=predictions['test_2023'].merge(thresholds,on=['station_key','month'],how='left',validate='many_to_one')
    test_result['predicted_depth']=test_result[selected];radius=radii[selected]
    test_result['lower_depth']=test_result.predicted_depth-radius;test_result['upper_depth']=test_result.predicted_depth+radius
    test_result['colour']=anomaly(test_result.predicted_depth,test_result.q75,test_result.q90)
    test_result.loc[test_result.q90.isna(),'colour']='grey'
    test_result['actual_colour']=anomaly(test_result.target_depth,test_result.q75,test_result.q90);test_result.loc[test_result.q90.isna(),'actual_colour']='grey'
    eligible=test_result[test_result.colour.ne('grey')];pred=eligible.colour.eq('red');actual=eligible.actual_colour.eq('red')
    tp=int((pred&actual).sum());fp=int((pred&~actual).sum());fn=int((~pred&actual).sum());tn=int((~pred&~actual).sum())
    metrics={'eligible_test_measurements':len(eligible),'true_positive':tp,'false_positive':fp,'false_negative':fn,'true_negative':tn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None}
    # CBR cases use training-only rows, even if another method wins validation.
    scaler=models['cbr_rain'].named_steps['standardscaler'];neighbors=models['cbr_rain'].named_steps['kneighborsregressor']
    distances,indices=neighbors.kneighbors(scaler.transform(test_result[cols]),n_neighbors=3)
    cases={}
    station_names=observations.drop_duplicates('station_key').set_index('station_key').station.to_dict()
    for (_,row),ds,ids in zip(test_result.iterrows(),distances,indices):
        key=f'{row.station_key}|{int(row.year)}|{int(row.month)}'
        case=[]
        for distance,index in zip(ds,ids):
            r=training.iloc[int(index)]
            case.append({'station':station_names.get(r.station_key,r.station_key),'origin_date':str(r.origin_date),'target_year':int(r.year),'target_month':int(r.month),'previous_depth_m':float(r.last_depth),'observed_target_depth_m':float(r.target_depth),'prior_90d_precipitation_mm':float(r.rain_90d_mm),'standardized_distance':round(float(distance),3)})
        cases[key]=case
    report={'pilot':'Yavatmal only','rainfall_provider':'Open-Meteo / ERA5 reanalysis; not IMD observations','training_years':'2015–2020 target years','training_pairs':len(training),'validation_year':2022,'test_year':2023,'forecast_horizon':'Next scheduled CGWB survey round, 2–4 months','selection':'Lowest 2022 validation MAE; configuration fixed before inspecting this pilot test output','selected_method':selected,'scores':scores,'interval_radius_m':radius,'warning_metrics':metrics,'colours':{'red':'Critical historical depth anomaly: estimate exceeds same-station/same-season training 90th percentile; experimental, not a confirmed crisis','amber':'Estimate above training 75th percentile but not 90th','green':'Estimate at or below training 75th percentile; not a safe-water claim','grey':'Fewer than four training readings for this station/season'},'thresholds_use_test_data':False,'current_forecast_supported':False,'validated_crisis_warnings':False,'limitations':['No matched next-round Yavatmal pairs were available in 2021; 2022 is used for validation.','2023 has been inspected previously; exploratory backtest, not an untouched final benchmark.','Rainfall is gridded reanalysis at nearest cells, not measured at the wells.','Statistical anomaly labels are not validated hydrological crisis labels.','No future precipitation is used; rolling windows end before the forecast-origin day.','Prediction intervals are empirical; report actual test coverage rather than promising 90%.']}
    out=ROOT/'outputs';out.mkdir(exist_ok=True)
    test_result['station']=test_result.station_key.map(station_names)
    test_result.to_csv(out/'pilot_test_predictions.csv',index=False)
    (out/'pilot_report.json').write_text(json.dumps(report,indent=2));(out/'pilot_cases.json').write_text(json.dumps(cases,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':train()
