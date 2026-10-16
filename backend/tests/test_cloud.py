import os,sys,json,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import model_transport
class CloudTests(unittest.TestCase):
    def test_cloud_has_no_implicit_laptop_dependency(self):
        with patch.dict(os.environ,{'DEPLOYMENT_MODE':'cloud','LLM_BASE_URL':''}):
            with self.assertRaises(ValueError):model_transport.complete({})
    def test_hosted_completion_adapter(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"answer":"test","sources":[]}'}}],'usage':{'completion_tokens':8}})
        with patch.dict(os.environ,{'LLM_BASE_URL':'https://model.example/v1','LLM_API_KEY':'test-secret'}),patch.object(model_transport,'urlopen',return_value=response) as call:
            result=model_transport.complete({'model':'open-weight-model','messages':[],'options':{'num_predict':384}})
            self.assertEqual(result['done_reason'],'stop');self.assertEqual(result['eval_count'],8)
            request=call.call_args.args[0];self.assertEqual(request.full_url,'https://model.example/v1/chat/completions')
            self.assertEqual(request.get_header('Authorization'),'Bearer test-secret')
    def test_cloud_requires_encrypted_model_endpoint(self):
        with patch.dict(os.environ,{'LLM_BASE_URL':'http://model.example/v1'}):
            with self.assertRaises(ValueError):model_transport.complete({})
