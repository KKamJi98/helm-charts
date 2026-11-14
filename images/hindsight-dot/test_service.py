import json,time,unittest,os,shutil
from dataclasses import replace
from cryptography.fernet import Fernet
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from key_value.aio.wrappers.prefix_collections import PrefixCollectionsWrapper
import httpx2
from service import Application,Config,RedisStatus
from emergency_gate import GateStatus
from test_flow_base import FlowTests

SCANNER=os.environ.get('DOT_TEST_SCANNER') or shutil.which('gitleaks') or '/usr/local/bin/gitleaks'
def config(mode,capabilities=('hindsight:recall','hindsight:retain'),epoch=1):
 return Config(mode=mode,epoch=epoch,public_url='https://isolated.invalid',owner_sub='fake-owner',owner_email='owner@example.invalid',google_client_id='fake-client',redirects=('https://client.invalid/callback',),capabilities=capabilities,scanner=SCANNER)

class ServiceTests(FlowTests):
 async def asyncSetUp(self):
  await super().asyncSetUp()
  self.identity={'aud':'fake-client','sub':'fake-owner','email':'owner@example.invalid','email_verified':True,'scope':'openid https://www.googleapis.com/auth/userinfo.email','expires_in':600}
  self.http._transport=httpx2.MockTransport(lambda r:httpx2.Response(200,json=self.identity))
  self.native=[]
  def native(r):
   data=json.loads(r.content);self.native.append((r.url.path,data))
   if r.url.path.endswith('/recall'):return httpx2.Response(200,json={'results':[{'text':'Fictional Alex likes books.'}]})
   return httpx2.Response(200,json={'success':True,'operation_id':data['operation_id']})
  self.native_http=httpx2.AsyncClient(transport=httpx2.MockTransport(native))
  self.backing=MemoryStore();self.key=Fernet.generate_key()
  self.store=FernetEncryptionWrapper(PrefixCollectionsWrapper(self.backing,'dot-oauth-e1:'),fernet=Fernet(self.key))
  common=dict(storage=self.store,read_status=self.state,google_secret='synthetic-secret-only',signing_key='synthetic-signing-key-only',google_http=self.http)
  self.gateway=Application(config('gateway'),**common,native_headers={'Authorization':'Bearer synthetic-native-only','X-Hindsight-Client-Key':'synthetic-native-only'},outbound_http=self.native_http)
  self.gateway_http=httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.gateway.app),base_url='http://backend-policy.hindsight-dot.svc.cluster.local:8001')
  self.proxy=Application(config('proxy'),**common,outbound_http=self.gateway_http)
  # Seed same callback fixture/client from already-tested FastMCP token flow.
  client=await self.p.get_client('test-client');code=await self.p._code_store.get(key='synthetic-code')
  code.idp_tokens['scope']='openid https://www.googleapis.com/auth/userinfo.email'
  code.scopes=['openid','https://www.googleapis.com/auth/userinfo.email']
  await self.proxy.provider.register_client(client);await self.proxy.provider._code_store.put(key='synthetic-code',value=code)
  self.p=self.proxy.provider
  await self.c.aclose();self.c=httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.proxy.app),base_url='https://isolated.invalid')
 async def asyncTearDown(self):
  await self.gateway_http.aclose();await self.native_http.aclose();await super().asyncTearDown()
 async def call(self,tok,name,args):
  async with self.proxy.raw.router.lifespan_context(self.proxy.raw):
   return await self.c.post('/mcp',headers={'authorization':'Bearer '+tok,'accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}})
 async def test_full_owner_recall_and_save(self):
  tok=(await self.exchange()).json()['access_token']
  for name,args in [('recall_memory',{'query':'fictional memory query'}),('save_conversation_summary',{'summary':'Fictional Alex likes books.','conversation_id':'fixture','message_id':'message1'})]:
   r=await self.call(tok,name,args);self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['result'].get('isError'),r.text)
  self.assertEqual(len(self.native),2)
 async def test_company_marker_refused(self):
  tok=(await self.exchange()).json()['access_token']
  r=await self.call(tok,'save_conversation_summary',{'summary':'Synthetic bunjang document.','conversation_id':'fixture','message_id':'message1'})
  self.assertTrue(r.json()['result']['isError']);self.assertEqual(self.native,[])
 async def test_owner_denial(self):
  tok=(await self.exchange()).json()['access_token'];self.identity['sub']='other'
  r=await self.call(tok,'recall_memory',{'query':'fictional memory query'})
  self.assertEqual(r.status_code,401);self.assertEqual(self.native,[])
 async def test_direct_disabled_gateway(self):
  tok=(await self.exchange()).json()['access_token'];self.status=GateStatus(False,2)
  r=await self.gateway_http.post('/v1/default/banks/personal_shared/memories/recall',headers={'authorization':'Bearer '+tok},json={'query':'fictional query','max_tokens':100})
  self.assertEqual(r.status_code,503);self.assertEqual(self.native,[])
 async def test_new_epoch_denies_old_grant(self):
  tok=(await self.exchange()).json()['access_token']
  newstore=FernetEncryptionWrapper(PrefixCollectionsWrapper(self.backing,'dot-oauth-e2:'),fernet=Fernet(self.key))
  new=Application(config('proxy',epoch=2),storage=newstore,read_status=self.state,google_secret='synthetic-secret-only',signing_key='synthetic-signing-key-only',google_http=self.http,outbound_http=self.gateway_http)
  self.assertIsNone(await new.provider.load_access_token(tok))
 async def test_same_store_restart_keeps_session(self):
  tok=(await self.exchange()).json()['access_token']
  newstore=FernetEncryptionWrapper(PrefixCollectionsWrapper(self.backing,'dot-oauth-e1:'),fernet=Fernet(self.key))
  new=Application(config('proxy'),storage=newstore,read_status=self.state,google_secret='synthetic-secret-only',signing_key='synthetic-signing-key-only',google_http=self.http,outbound_http=self.gateway_http)
  self.assertIsNotNone(await new.provider.load_access_token(tok))
 # Base fixture tests only apply to original provider fixture, not replaced service fixture.
 test_pkce_then_exchange_refresh_rotation=None
 test_gate_prevents_refresh_without_upstream_call=None
 test_fresh_store_restart_denies_old_access_refresh=None

class StateTests(unittest.IsolatedAsyncioTestCase):
 async def test_state_shapes(self):
  class Fake:
   async def get(self,k):return self.data
  f=Fake();reader=RedisStatus(f)
  for d in [None,'{}','{"enabled":1,"epoch":1}','{"enabled":true,"epoch":true}']:
   f.data=d
   with self.assertRaises(ValueError):await reader()
  f.data='{"enabled":false,"epoch":2}';self.assertEqual(await reader(),GateStatus(False,2))
 async def test_encryption_at_rest(self):
  backing=MemoryStore();key=Fernet.generate_key();wrapped=FernetEncryptionWrapper(backing,fernet=Fernet(key))
  await wrapped.put('fixture',{'access_token':'synthetic-sensitive-token'},collection='oauth')
  raw=await backing.get('fixture',collection='oauth');self.assertNotIn('synthetic-sensitive-token',json.dumps(raw))
  self.assertEqual((await wrapped.get('fixture',collection='oauth'))['access_token'],'synthetic-sensitive-token')
