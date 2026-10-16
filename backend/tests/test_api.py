import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api import app
from train_seasonal import build_pairs
from core import load_records

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.client=TestClient(app)
    def test_dashboard_and_selection(self):
        self.assertEqual(self.client.get('/').status_code,200)
        stations=self.client.get('/api/stations?district=Yavatmal').json()
        key=stations[0]['station_key']
        self.assertEqual(self.client.get('/api/overview',params={'district':'Yavatmal','station':key}).json()['stations'],1)
        self.assertEqual(self.client.get('/api/overview?district=Delhi').status_code,404)
        self.assertEqual(self.client.get('/api/overview',params={'district':'Pune','station':key}).status_code,404)
    def test_map_has_no_live_tiles_and_localized_research_layer(self):
        html=self.client.get('/api/map?language=Marathi').text
        self.assertIn('2023 चे जुने प्रायोगिक संकेत',html)
        self.assertNotIn('tile.openstreetmap.org',html)
    def test_current_question_abstains_without_llm(self):
        reply=self.client.post('/api/ask',json={'question':'आज पानी की स्थिति क्या है?','language':'Hindi'}).json()
        self.assertFalse(reply['generated'])
    def test_admin_and_schema_validation(self):
        self.assertEqual(self.client.get('/api/admin/audit').status_code,401)
        self.assertEqual(self.client.post('/api/admin/publish',json={'preview_id':'fake','reviewed':True}).status_code,401)
        self.assertEqual(self.client.get('/api/map?language=invalid').status_code,422)
    def test_no_operational_crisis_claim(self):
        result=self.client.get('/api/readiness').json()
        self.assertFalse(result['validated_crisis_warnings']);self.assertFalse(result['current_forecast'])
        result=self.client.get('/api/seasonal').json()
        self.assertFalse(result['current_enabled'])
        self.assertEqual(result['evaluation']['test_year'],2023)
    def test_forecast_origins_are_before_targets(self):
        pairs=build_pairs(load_records())
        origin_index=pairs.origin_year*12+pairs.origin_month
        target_index=pairs.year*12+pairs.month
        self.assertTrue((origin_index<target_index).all())
        self.assertTrue(set(target_index-origin_index)<={2,3,4})

if __name__=='__main__':unittest.main()

class AdminRoundTrip(unittest.TestCase):
    def test_review_publish_backup_and_audit(self):
        import tempfile,shutil
        from unittest.mock import patch
        import api,admin
        import pandas as pd
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'data').mkdir();shutil.copy(api.ROOT/'data/observations.csv',root/'data/observations.csv')
            data=load_records(root/'data/observations.csv')
            def temp_records(): return load_records(root/'data/observations.csv')
            with patch.object(api,'ROOT',root),patch.object(api,'PRIVATE',root/'private'),patch.object(admin,'ROOT',root),patch.object(admin,'PRIVATE',root/'private'),patch.object(api,'records',temp_records):
                admin.configure('test-only-password-123')
                c=TestClient(api.app);reply=c.post('/api/admin/login',json={'password':'test-only-password-123'})
                self.assertEqual(reply.status_code,200)
                headers={'Authorization':'Bearer '+reply.json()['token']}
                row=data.head(1).copy();row['date']=pd.Timestamp('2024-01-01')
                preview=c.post('/api/admin/preview',headers=headers,files={'file':('test.csv',row.to_csv(index=False).encode(),'text/csv')},data={'source_url':'https://cgwb.gov.in/test'})
                self.assertEqual(preview.status_code,200,preview.text)
                key=preview.json()['preview_id']
                self.assertEqual(c.post('/api/admin/publish',headers=headers,json={'preview_id':key}).status_code,400)
                result=c.post('/api/admin/publish',headers=headers,json={'preview_id':key,'reviewed':True})
                self.assertEqual(result.status_code,200,result.text);self.assertEqual(result.json()['added'],1)
                self.assertEqual(len(list((root/'private').glob('observations_*.csv'))),1)
                self.assertEqual(c.get('/api/admin/audit',headers=headers).json()['entries'][0]['added'],1)
                self.assertEqual(c.post('/api/admin/logout',headers=headers).status_code,200)
                self.assertEqual(c.get('/api/admin/audit',headers=headers).status_code,401)
