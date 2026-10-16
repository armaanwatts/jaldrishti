"""One fixed model, chronological holdouts, equal evaluation rows. No live forecast."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
from pathlib import Path
import json
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from core import load_records,ROOT

def evaluate():
    df=load_records();df['year']=df.date.dt.year;df['month']=df.date.dt.month
    m=df.groupby(['station_key','district','year','month'],as_index=False).agg(depth=('depth','median'),latitude=('latitude','first'),longitude=('longitude','first'))
    old=m[['station_key','year','month','depth']].copy();old.year+=1;old=old.rename(columns={'depth':'prior_depth'})
    pairs=m.merge(old,on=['station_key','year','month'],validate='one_to_one').dropna(subset=['depth','prior_depth'])
    train=pairs[pairs.year<=2020];validation=pairs[pairs.year==2021];test=pairs[pairs.year==2023]
    cols=['prior_depth','month','latitude','longitude']
    model=HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,l2_regularization=1,early_stopping=False,random_state=42)
    model.fit(train[cols],train.depth)
    out=ROOT/'outputs';out.mkdir(exist_ok=True);report=[]
    for name,split in [('validation_2021',validation),('test_2023',test)]:
        result=split.copy();result['model_depth']=model.predict(result[cols]);result['baseline_error']=(result.depth-result.prior_depth).abs();result['model_error']=(result.depth-result.model_depth).abs()
        result.to_csv(out/f'{name}_predictions.csv',index=False)
        result.groupby('district').agg(evaluated_measurements=('depth','size'),baseline_mae_m=('baseline_error','mean'),model_mae_m=('model_error','mean')).to_csv(out/f'{name}_district_scores.csv')
        report.append({'split':name,'evaluated':len(result),'baseline_mae_m':float(result.baseline_error.mean()),'model_mae_m':float(result.model_error.mean())})
    metadata={'training_targets':'1997–2020 where matching prior-year readings exist','training_pairs':len(train),'features':cols,'rainfall_used':False,'model':'HistGradientBoostingRegressor fixed configuration; no tuning on holdouts','results':report,'note':'Historical backtest only. Errors are not prediction intervals. No current-condition forecast.'}
    (out/'evaluation.json').write_text(json.dumps(metadata,indent=2));print(json.dumps(metadata,indent=2))
if __name__=='__main__': evaluate()
