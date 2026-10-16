"""Ollama locally, or a server-side OpenAI-compatible open-weight endpoint."""
import json
import os
import time
from urllib.request import Request,urlopen
from urllib.parse import urlparse

def complete(payload):
    base=os.getenv('LLM_BASE_URL','').rstrip('/')
    if not base:
        if os.getenv('DEPLOYMENT_MODE')=='cloud':
            raise ValueError('Configure a hosted open-weight LLM endpoint in server settings.')
        with urlopen(Request('http://127.0.0.1:11434/api/chat',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=180) as response:
            return json.load(response)
    if urlparse(base).scheme!='https' or not urlparse(base).hostname:
        raise ValueError('Hosted model requires an HTTPS API base ending in /v1.')
    body={'model':payload['model'],'messages':payload['messages'],'stream':False,'temperature':0.1,'max_tokens':payload['options']['num_predict'],'response_format':{'type':'json_object'}}
    headers={'Content-Type':'application/json'}
    if os.getenv('LLM_API_KEY'):headers['Authorization']='Bearer '+os.environ['LLM_API_KEY']
    began=time.monotonic()
    with urlopen(Request(base+'/chat/completions',data=json.dumps(body).encode(),headers=headers),timeout=45) as response:data=json.load(response)
    choice=data['choices'][0]
    return {'done_reason':choice.get('finish_reason'),'message':{'content':choice['message']['content']},'total_duration':int((time.monotonic()-began)*1e9),'eval_count':data.get('usage',{}).get('completion_tokens',0)}
