import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api import app

class LatestTests(unittest.TestCase):
    def test_new_readings_are_kept_separate_and_review_only(self):
        client=TestClient(app)
        response=client.get('/api/latest?district=Yavatmal')
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertGreater(data['station_count'],0)
        self.assertFalse(data['manifest']['used_for_forecasting'])
        self.assertFalse(data['manifest']['measurement_convention_verified'])
        self.assertEqual(data['manifest']['latest_observation'][:10],'2026-10-14')
        self.assertEqual(data['manifest']['raw_record_count'],961043)
        self.assertEqual(client.get('/api/overview').json()['latest_date'],'2023-05-10')
    def test_raw_telemetry_is_not_crisis_classification(self):
        client=TestClient(app)
        self.assertFalse(client.get('/api/readiness').json()['current_forecast'])
        html=client.get('/api/map').text
        self.assertIn('2026 telemetry · raw values under review',html)
        self.assertNotIn('legend.addTo(map)',html)
        self.assertNotIn("blockLabels.addTo(map);",html)
