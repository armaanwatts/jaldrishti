import sys
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
import community
from core import load_records

HEADERS={'X-JalDrishti-Action':'1'}

def admin_auth(value):
    from fastapi import HTTPException
    if value!='Bearer test-admin':raise HTTPException(401,'unauthorized')
    return 'test-admin'

class CommunityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.df=load_records()
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.patch=patch.object(community,'DB',Path(self.folder.name)/'community.sqlite3');self.patch.start()
        app=FastAPI();app.include_router(community.create_router(lambda:self.df,admin_auth))
        self.a=TestClient(app);self.b=TestClient(app);self.admin=TestClient(app)
        self.h={**HEADERS,'Authorization':'Bearer test-admin'}
    def tearDown(self):self.patch.stop();self.folder.cleanup()
    def create(self,client,district,block='',language='English'):
        self.assertEqual(client.post('/api/farmer/profile',json={'language':language},headers=HEADERS).status_code,200)
        r=client.post('/api/farmer/regions',json={'district':district,'block':block},headers=HEADERS);self.assertEqual(r.status_code,200,r.text)
        return r.json()
    def draft(self,district='Yavatmal',block=''):
        return {'district':district,'block':block,'kind':'data_update','messages':{lang:{'title':lang+' update','body':'Reviewed historical source update for this region.'} for lang in community.LANGS},'source_url':'https://cgwb.gov.in/en/ground-water-level-monitoring','observed_date':'2023-05-10','valid_hours':24}
    def publish(self,body):
        r=self.admin.post('/api/admin/alerts/preview',json=body,headers=self.h);self.assertEqual(r.status_code,200,r.text)
        preview=r.json();r=self.admin.post('/api/admin/alerts/publish',json={'draft_id':preview['draft_id'],'reviewed':True},headers=self.h);self.assertEqual(r.status_code,200,r.text)
        return preview
    def test_regional_isolation_and_idempotency(self):
        self.create(self.a,'Yavatmal');self.create(self.b,'Pune')
        p=self.publish(self.draft());self.assertEqual(p['recipient_devices'],1)
        self.assertEqual(len(self.a.get('/api/farmer/inbox').json()['items']),1)
        self.assertEqual(self.b.get('/api/farmer/inbox').json()['items'],[])
        self.admin.post('/api/admin/alerts/publish',json={'draft_id':p['draft_id'],'reviewed':True},headers=self.h)
        self.assertEqual(len(self.a.get('/api/farmer/inbox').json()['items']),1)
    def test_block_and_language_targeting(self):
        block=self.df[self.df.district.eq('Yavatmal')].source_tehsil.dropna().iloc[0]
        self.create(self.a,'Yavatmal',block,'Marathi');self.create(self.b,'Yavatmal')
        p=self.publish(self.draft(block=block));self.assertEqual(p['recipient_devices'],1)
        self.assertTrue(self.a.get('/api/farmer/inbox').json()['items'][0]['title'].startswith('Marathi'))
        self.assertTrue(self.a.get('/api/farmer/inbox?language=Hindi').json()['items'][0]['title'].startswith('Hindi'))
        self.assertEqual(self.b.get('/api/farmer/inbox').json()['items'],[])
    def test_preview_changes_and_review_gate(self):
        self.create(self.a,'Yavatmal');r=self.admin.post('/api/admin/alerts/preview',json=self.draft(),headers=self.h).json()
        self.assertEqual(self.admin.post('/api/admin/alerts/publish',json={'draft_id':r['draft_id']},headers=self.h).status_code,422)
        self.create(self.b,'Yavatmal')
        self.assertEqual(self.admin.post('/api/admin/alerts/publish',json={'draft_id':r['draft_id'],'reviewed':True},headers=self.h).status_code,409)
    def test_csrf_auth_and_warning_gate(self):
        self.assertEqual(self.a.post('/api/farmer/profile',json={'language':'English'}).status_code,403)
        self.assertEqual(self.a.post('/api/farmer/profile',json={'language':'English'},headers={**HEADERS,'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.a.get('/api/farmer/inbox').status_code,401)
        body=self.draft();body['kind']='warning'
        self.assertEqual(self.admin.post('/api/admin/alerts/preview',json=body,headers=self.h).status_code,409)
        self.assertEqual(self.a.get('/api/admin/alerts').status_code,401)
    def test_withdraw_and_profile_deletion(self):
        self.create(self.a,'Yavatmal');p=self.publish(self.draft())
        self.admin.post('/api/admin/alerts/'+p['draft_id']+'/withdraw',headers=self.h)
        self.assertTrue(self.a.get('/api/farmer/inbox').json()['items'][0]['withdrawn'])
        self.a.delete('/api/farmer/profile',headers=HEADERS)
        self.assertEqual(self.a.get('/api/farmer/inbox').status_code,401)
    def test_source_and_region_validation(self):
        self.create(self.a,'Yavatmal')
        self.assertEqual(self.a.post('/api/farmer/regions',json={'district':'Delhi'},headers=HEADERS).status_code,422)
        self.assertEqual(self.a.post('/api/farmer/regions',json={'district':'Pune','block':'not-a-block'},headers=HEADERS).status_code,422)
        body=self.draft();body['source_url']='javascript:alert(1)'
        self.assertEqual(self.admin.post('/api/admin/alerts/preview',json=body,headers=self.h).status_code,422)
    def test_ssrf_push_endpoint_rejection(self):
        self.create(self.a,'Yavatmal')
        r=self.a.post('/api/farmer/push',json={'endpoint':'http://127.0.0.1/private','keys':{}},headers=HEADERS)
        self.assertEqual(r.status_code,422)

class LatestChatTests(unittest.TestCase):
    def test_recency_answer_separates_review_data(self):
        from latest_chat import latest_reply
        result=latest_reply('What is the latest Yavatmal data?',['Yavatmal'],'English')
        self.assertFalse(result['generated']);self.assertIn('still need checking',result['answer'])
        self.assertFalse(result['facts'][0]['current_supported'])
        self.assertIsNone(latest_reply('Predict next season',['Yavatmal'],'English'))
        self.assertIsNone(latest_reply('latest readings in 2020',['Yavatmal'],'English'))
        self.assertIn('no verified identity match',latest_reply('today',['Yavatmal'],'English','manual-well')['answer'])

class PushWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.df=load_records()
    setUp=CommunityTests.setUp
    tearDown=CommunityTests.tearDown
    create=CommunityTests.create
    draft=CommunityTests.draft
    publish=CommunityTests.publish
    def add_push(self):
        import base64
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        key=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        encode=lambda value:base64.urlsafe_b64encode(value).decode().rstrip('=')
        body={'endpoint':'https://fcm.googleapis.com/fcm/send/test-only','keys':{'p256dh':encode(key),'auth':encode(b'0123456789abcdef')}}
        r=self.a.post('/api/farmer/push',json=body,headers=HEADERS);self.assertEqual(r.status_code,200,r.text)
    def test_worker_uses_region_language_and_does_not_resend_accepted(self):
        import push_delivery,json
        self.create(self.a,'Yavatmal',language='Marathi');self.create(self.b,'Pune');self.add_push()
        self.publish(self.draft())
        with patch.object(push_delivery,'CONFIG',Path(self.folder.name)/'webpush.json'):
            push_delivery.configure('mailto:test@example.com')
            with patch('pywebpush.webpush') as send:
                self.assertEqual(push_delivery.process_queue()['processed'],1)
                message=json.loads(send.call_args.kwargs['data']);self.assertTrue(message['title'].startswith('Marathi'))
                self.assertTrue(message['url'].startswith('/farmer?'))
                push_delivery.process_queue();self.assertEqual(send.call_count,1)
        state=self.admin.get('/api/admin/alerts',headers=self.h).json()['items'][0]['push_status']
        self.assertEqual(state,{'accepted':1})
    def test_worker_rechecks_region_subscription_before_send(self):
        import push_delivery
        profile=self.create(self.a,'Yavatmal');self.add_push();self.publish(self.draft())
        self.a.delete('/api/farmer/regions/'+profile['regions'][0]['id'],headers=HEADERS)
        with patch.object(push_delivery,'CONFIG',Path(self.folder.name)/'webpush.json'):
            push_delivery.configure('mailto:test@example.com')
            with patch('pywebpush.webpush') as send:push_delivery.process_queue();send.assert_not_called()
        state=self.admin.get('/api/admin/alerts',headers=self.h).json()['items'][0]['push_status']
        self.assertEqual(state,{'cancelled':1})
    def test_expired_push_endpoint_is_disabled(self):
        import push_delivery
        from pywebpush import WebPushException
        from requests import Response
        self.create(self.a,'Yavatmal');self.add_push();self.publish(self.draft())
        response=Response();response.status_code=410
        with patch.object(push_delivery,'CONFIG',Path(self.folder.name)/'webpush.json'):
            push_delivery.configure('mailto:test@example.com')
            with patch('pywebpush.webpush',side_effect=WebPushException('gone',response=response)):push_delivery.process_queue()
        self.assertFalse(self.a.get('/api/farmer/profile').json()['push_enabled'])
    def test_active_updates_are_visible_to_new_subscribers(self):
        self.publish(self.draft());self.create(self.a,'Yavatmal')
        self.assertEqual(len(self.a.get('/api/farmer/inbox').json()['items']),1)

    def test_real_signing_and_encryption_without_network(self):
        import push_delivery
        from requests import Response
        self.create(self.a,'Yavatmal');self.add_push();self.publish(self.draft())
        accepted=Response();accepted.status_code=201;accepted._content=b''
        with patch.object(push_delivery,'CONFIG',Path(self.folder.name)/'webpush.json'):
            push_delivery.configure('mailto:test@example.com')
            with patch('requests.post',return_value=accepted) as transport:
                result=push_delivery.process_queue()
                self.assertEqual(result['processed'],1)
                transport.assert_called_once()
                self.assertIn('authorization',{k.lower():v for k,v in transport.call_args.kwargs['headers'].items()})
                self.assertIsInstance(transport.call_args.kwargs['data'],bytes)
        self.assertEqual(self.admin.get('/api/admin/alerts',headers=self.h).json()['items'][0]['push_status'],{'accepted':1})

class PushSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.df=load_records()
    setUp=CommunityTests.setUp
    tearDown=CommunityTests.tearDown
    create=CommunityTests.create
    draft=CommunityTests.draft
    publish=CommunityTests.publish
    def test_admin_setup_and_single_device_test_route(self):
        import push_delivery
        with patch.object(push_delivery,'CONFIG',Path(self.folder.name)/'webpush.json'):
            r=self.admin.post('/api/admin/push/setup',json={'contact_email':'test@example.com'},headers=self.h)
            self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()['configured'])
            self.assertNotIn('private_key',r.text)
            self.create(self.a,'Yavatmal');self.create(self.b,'Yavatmal')
            # Reuse a valid generated browser subscription; no network sending occurs.
            PushWorkerTests.add_push(self)
            result=self.a.post('/api/farmer/push/test',headers=HEADERS)
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(len(self.a.get('/api/farmer/inbox').json()['items']),1)
            self.assertEqual(self.b.get('/api/farmer/inbox').json()['items'],[])
            self.assertEqual(self.a.post('/api/farmer/push/test',headers=HEADERS).status_code,429)
