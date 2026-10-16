"""Forecast the next scheduled CGWB round, with information available at origin only."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
import json
import math
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from core import load_records,ROOT

def build_pairs(df):
    df=df.copy();df['year']=df.date.dt.year;df['month']=df.date.dt.month
    df=df[df.month.isin([1,5,8,11])]
    m=df.groupby(['station_key','district','year','month'],as_index=False).agg(depth=('depth','median'),latitude=('latitude','first'),longitude=('longitude','first'),origin_date=('date','max'),source_tehsil=('source_tehsil','first'))
    origin=m.copy();origin['origin_month']=origin.month;origin['origin_year']=origin.year
    origin['month']=origin.origin_month.map({1:5,5:8,8:11,11:1});origin['year']+=(origin.origin_month==11).astype(int)
    origin=origin.rename(columns={'depth':'last_depth'})
    target=m[['station_key','year','month','depth']].rename(columns={'depth':'target_depth'})
    pairs=origin.merge(target,on=['station_key','year','month'],validate='one_to_one')
    prior=m[['station_key','year','month','depth']].copy();prior.year+=1;prior=prior.rename(columns={'depth':'prior_year_depth'})
    return pairs.merge(prior,on=['station_key','year','month'],validate='one_to_one').dropna(subset=['last_depth','prior_year_depth','target_depth'])

def train():
    pairs=build_pairs(load_records());features=['last_depth','prior_year_depth','origin_month','month','latitude','longitude']
    rain=ROOT/'data/rainfall_features.csv';rain_used=False
    if rain.exists():
        rainfall=pd.read_csv(rain);rainfall['date']=pd.to_datetime(rainfall.date)
        pairs=pairs.merge(rainfall.rename(columns={'date':'origin_date'}),on=['station_key','origin_date'],how='left',validate='many_to_one')
        features+=['rain_30d_mm','rain_90d_mm','rain_180d_mm'];rain_used=True
    train=pairs[pairs.year<=2020];val=pairs[pairs.year==2021];test=pairs[pairs.year==2023]
    if min(len(train),len(val),len(test))<100: raise ValueError('Too few matched records for chronological evaluation')
    model=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,l2_regularization=1,early_stopping=False,random_state=42).fit(train[features],train.target_depth)
    residual=np.abs(val.target_depth-model.predict(val[features]))
    # Empirical held-out calibration; temporal/spatial dependence limits coverage claims.
    rank=min(len(residual)-1,math.ceil((len(residual)+1)*.9)-1)
    radius=float(np.sort(residual)[rank])
    thresholds=train.groupby(['district','month']).target_depth.agg(count='size',threshold=lambda v:v.quantile(.9)).reset_index()
    thresholds=thresholds[thresholds['count']>=30]
    out=ROOT/'outputs';out.mkdir(exist_ok=True);scores=[]
    for name,split in [('validation_2021',val),('test_2023',test)]:
        result=split.copy();result['predicted_depth']=model.predict(result[features]);result['lower_depth']=result.predicted_depth-radius;result['upper_depth']=result.predicted_depth+radius
        result['baseline_error']=(result.target_depth-result.prior_year_depth).abs();result['model_error']=(result.target_depth-result.predicted_depth).abs()
        result=result.merge(thresholds,on=['district','month'],how='left',validate='many_to_one')
        result['historical_watch_candidate']=result.lower_depth>result.threshold
        result['actual_above_threshold']=result.target_depth>result.threshold
        watch=result[result.historical_watch_candidate]
        positives=result[result.actual_above_threshold]
        scores.append({'split':name,'count':len(result),'baseline_mae_m':float(result.baseline_error.mean()),'model_mae_m':float(result.model_error.mean()),'empirical_interval_coverage':float(((result.target_depth>=result.lower_depth)&(result.target_depth<=result.upper_depth)).mean()),'watch_count':len(watch),'watch_precision':float(watch.actual_above_threshold.mean()) if len(watch) else None,'watch_recall':float(positives.historical_watch_candidate.mean()) if len(positives) else None})
        if name=='test_2023':result.to_csv(out/'seasonal_test_2023.csv',index=False)
    report={'target':'Next scheduled survey round: Jan→May (4 months), May→Aug (3), Aug→Nov (3), Nov→Jan (2)','training_target_end_year':2020,'validation_year':2021,'test_year':2023,'training_pairs':len(train),'features':features,'rainfall_used':rain_used,'interval_radius_m':radius,'interval_method':'Absolute residual 90th percentile from 2021; empirical, not a guaranteed confidence interval','watch_rule':'Exploratory only: lower predicted bound exceeds the training-only district/target-month 90th percentile, with at least 30 training measurements. This is not a validated crisis classification.','results':scores,'limitations':['2023 has been inspected in previous experiments: this is exploratory, not an untouched benchmark.','Rainfall integration and newer ground measurements are required for operational use.','Existing-station performance; no unseen-village validation.','No operational current forecast is enabled.']}
    (out/'seasonal_evaluation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':train()
