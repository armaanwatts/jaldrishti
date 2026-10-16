import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import load_records,retrieve
from admin import validate_upload
from rainfall import features

class NewFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.df=load_records()
    def test_history_and_year_ranges(self):
        self.assertEqual(len(self.df),119937)
        self.assertEqual(self.df.date.min().year,1996)
        result=retrieve(self.df,'Pune 2010 to 2015','Yavatmal')
        self.assertEqual(set(result['rows'].date.dt.year),set(range(2010,2016)))
    def test_reject_conflicting_upload_and_identity(self):
        row=self.df.head(1).copy();row['depth']+=1
        with self.assertRaisesRegex(ValueError,'Conflicting'): validate_upload(row.to_csv(index=False).encode(),self.df,'https://nwdp.nwic.gov.in/dataset/test')
        row=self.df.head(1).copy();row['latitude']+=.01
        with self.assertRaisesRegex(ValueError,'station key'): validate_upload(row.to_csv(index=False).encode(),self.df,'https://cgwb.gov.in/test')
    def test_source_url_and_missing_values(self):
        row=self.df.head(1).copy()
        with self.assertRaises(ValueError): validate_upload(row.to_csv(index=False).encode(),self.df,'https://evil.example')
        row['depth']=float('nan')
        with self.assertRaises(ValueError): validate_upload(row.to_csv(index=False).encode(),self.df,'https://cgwb.gov.in/test')
    def test_rainfall_no_future_data_and_missing_window(self):
        dates=pd.date_range('2020-01-01','2020-08-01')
        daily=pd.DataFrame({'station_key':'a','date':dates,'rain_mm':1.0})
        daily.loc[daily.date.eq('2020-07-01'),'rain_mm']=9999
        obs=pd.DataFrame({'station_key':['a'],'date':[pd.Timestamp('2020-07-01')]})
        out=features(obs,daily).iloc[0]
        self.assertEqual(out.rain_30d_mm,30)
        daily=daily[~daily.date.eq('2020-06-30')]
        self.assertTrue(pd.isna(features(obs,daily).iloc[0].rain_30d_mm))

if __name__=='__main__': unittest.main()
