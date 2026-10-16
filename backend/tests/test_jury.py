import sys
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api import app,request_times
from core import ROOT
from pilot_api import pilot,examples

class JuryTests(unittest.TestCase):
    def setUp(self):request_times.clear()
    def test_rain_is_real_pilot_and_not_claimed_imd(self):
        manifest=json.loads((ROOT/'data/pilot_rain_manifest.json').read_text())
        self.assertFalse(manifest['imd_data']);self.assertEqual(manifest['cell_count'],28)
        data=pd.read_csv(ROOT/'data/pilot_rain_cells.csv')
        self.assertEqual(len(data),102256);self.assertEqual(data.rain_mm.isna().sum(),0)
        self.assertTrue((data.rain_mm>=0).all())
    def test_no_future_rain_in_origin_feature(self):
        from train_pilot import attach_rain
        cells=pd.read_csv(ROOT/'data/pilot_rain_cells.csv')
        mapping=pd.read_csv(ROOT/'data/pilot_rain_station_map.csv').iloc[0]
        origin=pd.Timestamp('2020-07-01')
        pair=pd.DataFrame({'station_key':[mapping.station_key],'origin_date':[origin]})
        value=attach_rain(pair).iloc[0].rain_30d_mm
        selected=cells[cells.request_lat.eq(mapping.request_lat)&cells.request_lon.eq(mapping.request_lon)]
        dates=pd.to_datetime(selected.date);expected=selected[(dates>=origin-pd.Timedelta(days=30))&(dates<origin)].rain_mm.sum()
        self.assertAlmostEqual(value,expected,places=6)
    def test_historical_red_is_same_as_backtest_rule(self):
        replay=pilot('Yavatmal',month=5)
        self.assertTrue(replay['historical_only']);self.assertFalse(replay['report']['current_forecast_supported'])
        df=pd.read_csv(ROOT/'outputs/seasonal_test_2023.csv')
        candidates=examples();self.assertEqual(len(candidates),int(df.historical_watch_candidate.sum()))
        for row in df[df.historical_watch_candidate].itertuples():self.assertGreater(row.lower_depth,row.threshold)
    def test_pilot_does_not_hide_worse_rain_model(self):
        report=json.loads((ROOT/'outputs/pilot_report.json').read_text())
        test={r['method']:r['mae_m'] for r in report['scores'] if r['split']=='test_2023'}
        self.assertGreater(test['gradient_rain'],test['seasonal_baseline'])
        self.assertEqual(report['validation_year'],2022)
        self.assertTrue(all(c['target_year']<=2020 for cases in json.loads((ROOT/'outputs/pilot_cases.json').read_text()).values() for c in cases))
    def test_api_pilot_and_map_colours(self):
        c=TestClient(app)
        self.assertEqual(c.get('/api/pilot').status_code,200)
        self.assertTrue(c.get('/api/readiness').json()['rainfall_data'])
        html=c.get('/api/map?pilot_month=5').text
        self.assertIn('pilot_colour',html);self.assertIn('Critical',json.dumps(pilot('Yavatmal')['report']))
        self.assertEqual(c.get('/api/inference/status').json()['keep_alive'],'20m')
    def test_evidence_cache_invalidates_on_changed_facts(self):
        import inference
        with inference.LOCK:inference.CACHE.clear()
        calls=[]
        def generate(q,f,l):calls.append(f);return {'answer':'Evidence','sources':['R1']}
        a=inference.cached('question',[{'id':'R1','value':1}],'English',generate)
        b=inference.cached('question',[{'id':'R1','value':1}],'English',generate)
        d=inference.cached('question',[{'id':'R1','value':2}],'English',generate)
        self.assertFalse(a['cached']);self.assertTrue(b['cached']);self.assertFalse(d['cached']);self.assertEqual(len(calls),2)
