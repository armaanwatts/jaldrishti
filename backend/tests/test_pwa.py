import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from api import app

class PwaTests(unittest.TestCase):
    def test_phone_entry_and_worker(self):
        c=TestClient(app)
        r=c.get('/farmer');self.assertEqual(r.status_code,200);self.assertIn('/manifest.webmanifest',r.text)
        r=c.get('/sw.js');self.assertEqual(r.status_code,200);self.assertEqual(r.headers['cache-control'],'no-cache')
        self.assertIn("url.pathname.startsWith('/api/')",r.text)
        manifest=c.get('/manifest.webmanifest').json();self.assertEqual(manifest['start_url'],'/farmer')
        for icon in manifest['icons']:self.assertEqual(c.get(icon['src']).status_code,200)
    def test_today_reply_labels_newer_raw_source(self):
        c=TestClient(app)
        r=c.post('/api/ask',json={'question':'What is the latest data today?','district':'Yavatmal','language':'English'})
        self.assertEqual(r.status_code,200)
        self.assertFalse(r.json()['generated']);self.assertIn('not a live reading',r.json()['answer'])
        self.assertFalse(r.json()['facts'][0]['measurement_convention_verified'])
