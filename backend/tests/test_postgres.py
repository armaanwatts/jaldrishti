import os,sys,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import postgres_store
import push_delivery

class PostgresContractTests(unittest.TestCase):
    def test_hybrid_rows_preserve_named_and_positional_access(self):
        row=postgres_store.Row({'id':'abc','count':5})
        self.assertEqual(row[0],'abc');self.assertEqual(row['count'],5);self.assertEqual(dict(row),{'id':'abc','count':5})
    def test_notification_configuration_persists_in_database_not_disk(self):
        state={}
        with patch.dict(os.environ,{'DATABASE_URL':'server-only'}),patch.object(postgres_store,'get_setting',side_effect=lambda k:state.get(k)),patch.object(postgres_store,'put_setting_once',side_effect=lambda k,v:state.setdefault(k,v)):
            first=push_delivery.configure('mailto:owner@example.com')
            second=push_delivery.configure('mailto:owner@example.com')
            self.assertTrue(first['configured']);self.assertEqual(first,second)
            self.assertIn('private_key',json.loads(state['webpush']))
            self.assertNotIn('private_key',first)
