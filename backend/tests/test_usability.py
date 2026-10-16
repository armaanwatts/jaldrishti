import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import api

class UsabilityTests(unittest.TestCase):
    def test_directory_matches_source_and_does_not_imply_current_forecast(self):
        client=TestClient(api.app)
        response=client.get('/api/district-directory?language=Marathi')
        self.assertEqual(response.status_code,200)
        rows=response.json();df=api.records()
        self.assertEqual(len(rows),df.district.nunique())
        for row in rows:
            source=df[df.district.eq(row['district'])]
            self.assertEqual(row['readings'],len(source))
            self.assertEqual(row['stations'],source.station_key.nunique())
            self.assertEqual(row['latest_date'],str(source.date.max().date()))
            self.assertFalse(row['current_forecast'])
            latest=source[source.date.eq(source.date.max())].depth.dropna()
            if len(latest):self.assertEqual(row['round_median_m'],round(float(latest.median()),2))
    def test_admin_and_farmer_routes_are_available_but_actions_protected(self):
        client=TestClient(api.app)
        for route in ['/admin','/farmer','/']:
            self.assertEqual(client.get(route).status_code,200)
        self.assertIn(client.get('/api/admin/audit').status_code,(401,403))
