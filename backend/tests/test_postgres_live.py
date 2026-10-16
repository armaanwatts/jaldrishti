"""Run against a disposable PostgreSQL database: TEST_POSTGRES_URL=... python -m unittest discover -s backend/tests -p test_postgres_live.py.
Never point this test at a production database: it clears the private test schema.
"""
import os,sys,unittest,json,threading,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import postgres_store,community,push_delivery

@unittest.skipUnless(os.getenv('TEST_POSTGRES_URL'),'Disposable PostgreSQL URL not set')
class PostgresLiveTests(unittest.TestCase):
    def test_transaction_schema_targeting_and_durable_push_keys(self):
        import psycopg
        from psycopg.rows import dict_row
        url=os.environ['TEST_POSTGRES_URL']
        def connect():return psycopg.connect(url,row_factory=dict_row,prepare_threshold=None)
        with patch.dict(os.environ,{'DATABASE_URL':url}),patch.object(postgres_store,'SCHEMA','jaldrishti_test_private'),patch.object(postgres_store,'connect',connect),patch.object(postgres_store,'_ready',False):
            with connect() as raw:raw.execute('DROP SCHEMA IF EXISTS jaldrishti_test_private CASCADE')
            postgres_store.initialize()
            with community.database() as c:
                c.execute('INSERT INTO profiles VALUES(?,?,?,?,?)',('farmer1','hash','Marathi',time.time(),time.time()+86400))
                c.execute('INSERT OR IGNORE INTO regions VALUES(?,?,?,?)',('r1','farmer1','Yavatmal','Kalamb'))
                c.execute('INSERT OR IGNORE INTO regions VALUES(?,?,?,?)',('r2','farmer1','Yavatmal','Kalamb'))
                self.assertEqual(community.audience(c,'Yavatmal','Kalamb'),['farmer1'])
                self.assertEqual(community.audience(c,'Nagpur',''),[])
                c.execute('INSERT INTO subscriptions VALUES(?,?,1) ON CONFLICT(profile_id) DO UPDATE SET payload=excluded.payload,enabled=1',('farmer1',json.dumps({'endpoint':'https://web.push.apple.com/test'})))
                self.assertEqual(c.execute("SELECT profile_id FROM subscriptions WHERE json_extract(payload,'$.endpoint')=?",('https://web.push.apple.com/test',)).fetchone()[0],'farmer1')
            first=push_delivery.configure('mailto:owner@example.com');postgres_store._ready=False
            second=push_delivery.configure('mailto:owner@example.com');self.assertEqual(first,second)
            with self.assertRaises(RuntimeError):
                with community.database() as c:
                    c.execute('DELETE FROM regions');raise RuntimeError('abort')
            with community.database() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM regions').fetchone()[0],1)
            with connect() as raw:raw.execute('DROP SCHEMA jaldrishti_test_private CASCADE')
