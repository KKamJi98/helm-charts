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
 async def test_dcr_metadata_and_registration(self):
  metadata=await self.c.get('/.well-known/oauth-authorization-server')
  self.assertEqual(metadata.status_code,200,metadata.text)
  self.assertTrue(metadata.json().get('registration_endpoint','').endswith('/register'))
  self.assertFalse(metadata.json().get('client_id_metadata_document_supported',False))
  good=await self.c.post('/register',json={'redirect_uris':['https://client.invalid/callback'],'scope':'openid','grant_types':['authorization_code','refresh_token'],'response_types':['code']})
  self.assertEqual(good.status_code,201,good.text)
  bad=await self.c.post('/register',json={'redirect_uris':['https://unapproved.invalid/callback'],'scope':'openid'})
  self.assertEqual(bad.status_code,400,bad.text)
 async def test_dcr_public_client_scope_and_redacted_diagnostics(self):
  payload={'redirect_uris':['https://client.invalid/callback'],'scope':'openid https://www.googleapis.com/auth/userinfo.email','grant_types':['authorization_code','refresh_token'],'response_types':['code'],'token_endpoint_auth_method':'none','client_name':'PRIVATE-MARKER'}
  with self.assertLogs('uvicorn.error',level='INFO') as logs:
   good=await self.c.post('/register',json=payload)
   payload['redirect_uris']=['https://unapproved.invalid/callback?secret=PRIVATE-MARKER']
   bad=await self.c.post('/register',json=payload)
  self.assertEqual(good.status_code,201,good.text)
  self.assertEqual(good.json()['token_endpoint_auth_method'],'none')
  self.assertEqual(bad.status_code,400,bad.text)
  self.assertEqual(bad.json()['error'],'invalid_redirect_uri')
  output=' '.join(logs.output)
  self.assertIn('DCR outcome=accepted',output)
  self.assertIn('DCR outcome=redirect_denied',output)
  self.assertNotIn('PRIVATE-MARKER',output)
  self.assertNotIn('https://',output)
 async def test_dcr_storage_error_diagnostics_redacted(self):
  from unittest.mock import AsyncMock,patch
  client=await self.proxy.provider.get_client('test-client')
  with patch('owner_bridge.GoogleProvider.register_client',new=AsyncMock(side_effect=RuntimeError('PRIVATE-ERROR'))):
   with self.assertLogs('uvicorn.error',level='INFO') as logs:
    with self.assertRaises(RuntimeError):
     await self.proxy.provider.register_client(client)
  self.assertIn('storage_or_provider_error',' '.join(logs.output))
  self.assertNotIn('PRIVATE-ERROR',' '.join(logs.output))
 async def test_dcr_diagnostics_bounded(self):
  self.proxy.provider._registration_events=0
  with self.assertLogs('uvicorn.error',level='INFO') as logs:
   for _ in range(20):
    self.proxy.provider._registration_event('redirect_denied')
  self.assertEqual(len(logs.output),16)

 async def test_redirect_variants_rejected(self):
  from types import SimpleNamespace
  from mcp.server.auth.provider import AuthorizeError
  client=await self.p.get_client('test-client')
  for uri in ['https://client.invalid/callback?redirect=https://attacker.invalid',
              'https://client.invalid/callback#fragment',
              'https://client.invalid/callbackA',
              'https://unapproved.invalid/callback']:
   bad=await self.c.post('/register',json={'redirect_uris':[uri],'scope':'openid'})
   self.assertEqual(bad.status_code,400,bad.text)
   with self.assertRaises(AuthorizeError):
    await self.p.authorize(client,SimpleNamespace(redirect_uri=uri))
  missing=await self.c.post('/register',json={'scope':'openid'})
  self.assertEqual(missing.status_code,400,missing.text)
  for uri in ['https://client.invalid/callback[AB]','https:///missing-host',
              'https://user@client.invalid/callback','https://client.invalid/callback#fragment']:
   with self.assertRaises(ValueError):replace(config('proxy'),redirects=(uri,))
 async def test_cimd_disabled_no_remote_discovery(self):
  self.assertIsNone(self.p._cimd_manager)
  self.assertIsNone(await self.p.get_client('https://unapproved.invalid/client.json'))
  self.assertEqual(self.native,[])
 async def test_bootstrap_logs_verified_identity_but_denies_mcp(self):
  tok=(await self.exchange()).json()['access_token']
  cfg=replace(config('proxy',capabilities=('hindsight:recall',)),owner_sub='bootstrap-unverified-deny-all',synthetic_backend=True,native_url='http://synthetic-backend.hindsight-dot.svc.cluster.local:8080',bootstrap_identity_diagnostic=True)
  bootstrap=Application(cfg,storage=self.store,read_status=self.state,google_secret='synthetic-secret-only',signing_key='synthetic-signing-key-only',google_http=self.http,outbound_http=self.gateway_http)
  async with bootstrap.raw.router.lifespan_context(bootstrap.raw):
   async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=bootstrap.app),base_url='https://isolated.invalid') as c:
    with self.assertLogs('uvicorn.error',level='INFO') as logs:
     response=await c.post('/mcp',headers={'authorization':'Bearer '+tok,'accept':'application/json, text/event-stream'},json={'jsonrpc':'2.0','id':1,'method':'tools/list'})
    self.assertEqual(response.status_code,401)
    text=' '.join(logs.output)
    self.assertIn('sub=fake-owner email=owner@example.invalid',text)
    self.assertNotIn(tok,text);self.assertNotIn('synthetic-upstream',text)
    self.assertNotIn('client_secret',text)
    with self.assertNoLogs('uvicorn.error',level='INFO'):
     self.assertIsNone(await bootstrap.provider.load_access_token(tok))
  self.assertEqual(self.native,[])
 async def test_bootstrap_does_not_log_other_email(self):
  tok=(await self.exchange()).json()['access_token']
  cfg=replace(config('proxy',capabilities=('hindsight:recall',)),owner_sub='bootstrap-unverified-deny-all',synthetic_backend=True,native_url='http://synthetic-backend.hindsight-dot.svc.cluster.local:8080',bootstrap_identity_diagnostic=True)
  bootstrap=Application(cfg,storage=self.store,read_status=self.state,google_secret='synthetic-secret-only',signing_key='synthetic-signing-key-only',google_http=self.http,outbound_http=self.gateway_http)
  self.identity['email']='other@example.invalid'
  with self.assertNoLogs('uvicorn.error',level='INFO'):self.assertIsNone(await bootstrap.provider.load_access_token(tok))
 async def test_bootstrap_rejects_native_or_real_subject(self):
  with self.assertRaises(ValueError):replace(config('proxy'),bootstrap_identity_diagnostic=True)
  with self.assertRaises(ValueError):replace(config('proxy'),owner_sub='bootstrap-unverified-deny-all',bootstrap_identity_diagnostic=True)
 # Base fixture tests only apply to original provider fixture, not replaced service fixture.
 test_pkce_then_exchange_refresh_rotation=None
 test_gate_prevents_refresh_without_upstream_call=None
 test_fresh_store_restart_denies_old_access_refresh=None

 async def test_uvicorn_asgi3_factory_health(self):
  import uvicorn
  for app in (self.proxy,self.gateway):
   cfg=uvicorn.Config(lambda:app.app,factory=True,interface='asgi3',log_config=None)
   cfg.load()
   async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=cfg.loaded_app),base_url='http://synthetic.invalid') as client:
    response=await client.get('/health')
    self.assertEqual(response.status_code,200,response.text)

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
