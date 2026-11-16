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
 async def test_durable_registration_survives_epoch_without_grants(self):
  from oauth_storage import OAuthStorage,REGISTRATION_PREFIX
  from unittest.mock import AsyncMock
  registrations=FernetEncryptionWrapper(PrefixCollectionsWrapper(self.backing,REGISTRATION_PREFIX),fernet=Fernet(Fernet.generate_key()),raise_on_decryption_error=True)
  oldstore=OAuthStorage(self.store,registrations)
  common=dict(read_status=self.state,google_secret='synthetic-secret-only',signing_key='synthetic-signing-key-only',google_http=self.http,outbound_http=self.gateway_http,registration_limiter=AsyncMock())
  cfg=replace(config('proxy'),synthetic_backend=True,native_url='http://synthetic-backend.hindsight-dot.svc.cluster.local:8080',owner_bound=True,durable_registration=True)
  old=Application(cfg,storage=oldstore,**common)
  client=await self.p.get_client('test-client');code=await self.p._code_store.get(key='synthetic-code')
  await old.provider.register_client(client)
  await old.provider._code_store.put(key='synthetic-code',value=code)
  await old.provider._code_store.put(key='unconsumed-code',value=code.model_copy(update={'code':'unconsumed-code'}))
  async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=old.app),base_url='https://isolated.invalid') as c:
   response=await c.post('/token',data={'grant_type':'authorization_code','client_id':'test-client','code':'synthetic-code','redirect_uri':'https://client.invalid/callback','code_verifier':self.verifier})
  self.assertEqual(response.status_code,200,response.text);tokens=response.json()
  self.assertIsNotNone(await old.provider.load_access_token(tokens['access_token']))
  # Same signing and session encryption keys deliberately: isolation must not depend on key rotation alone.
  nextsessions=FernetEncryptionWrapper(PrefixCollectionsWrapper(self.backing,'dot-oauth-e2:'),fernet=Fernet(self.key),raise_on_decryption_error=True)
  newstore=OAuthStorage(nextsessions,registrations)
  new=Application(replace(cfg,epoch=2),storage=newstore,**common)
  restored=await new.provider.get_client('test-client')
  self.assertIsNotNone(restored);self.assertEqual(restored.client_id,client.client_id)
  self.assertIsNone(await new.provider.load_access_token(tokens['access_token']))
  self.assertIsNone(await new.provider.load_refresh_token(restored,tokens['refresh_token']))
  self.assertIsNone(await new.provider._code_store.get(key='synthetic-code'))
  # Unconsumed code and transaction/CSRF/unknown collections must also be isolated.
  for collection in ('mcp-authorization-codes','mcp-oauth-transactions','mcp-consent-csrf-tokens','mcp-upstream-tokens','mcp-jti-mappings','mcp-refresh-tokens','future-sdk-collection'):
   await oldstore.put('old-record',{'synthetic':'old'},collection=collection)
   self.assertIsNone(await newstore.get('old-record',collection=collection))
  self.status=GateStatus(True,2)
  async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=new.app),base_url='https://isolated.invalid') as c:
   oldrefresh=await c.post('/token',data={'grant_type':'refresh_token','client_id':'test-client','refresh_token':tokens['refresh_token']})
   self.assertEqual(oldrefresh.status_code,401,oldrefresh.text);self.assertEqual(oldrefresh.json()['error'],'invalid_grant')
   oldcode=await c.post('/token',data={'grant_type':'authorization_code','client_id':'test-client','code':'unconsumed-code','redirect_uri':'https://client.invalid/callback','code_verifier':self.verifier})
   self.assertIn(oldcode.status_code,(400,401));self.assertEqual(oldcode.json()['error'],'invalid_grant')
   # Existing client, fresh owner authorization fixture; no re-registration.
   await new.provider._code_store.put(key='fresh-code',value=code.model_copy(update={'code':'fresh-code'}))
   fresh=await c.post('/token',data={'grant_type':'authorization_code','client_id':'test-client','code':'fresh-code','redirect_uri':'https://client.invalid/callback','code_verifier':self.verifier})
   self.assertEqual(fresh.status_code,200,fresh.text)
   self.assertIsNotNone(await new.provider.load_access_token(fresh.json()['access_token']))
  from types import SimpleNamespace
  from mcp.server.auth.provider import AuthorizeError
  with self.assertRaises(AuthorizeError):
   await new.provider.authorize(restored,SimpleNamespace(redirect_uri='https://attacker.invalid/callback'))
  changed=Application(replace(cfg,epoch=2,redirects=('https://new.invalid/callback',)),storage=newstore,**common)
  retained=await changed.provider.get_client('test-client')
  for uri in ('https://client.invalid/callback','https://new.invalid/callback'):
   with self.assertRaises(AuthorizeError):await changed.provider.authorize(retained,SimpleNamespace(redirect_uri=uri))
  await old.http.aclose();await new.http.aclose();await changed.http.aclose()

 async def test_durable_registration_is_synthetic_only(self):
  with self.assertRaises(ValueError):replace(config('proxy'),durable_registration=True)

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
 async def test_bound_owner_requires_limiter(self):
  with self.assertRaises(ValueError):
   Application(replace(config('proxy'),owner_bound=True),storage=self.store,read_status=self.state,google_secret='fake',signing_key='fake')
 async def test_rate_limit_before_callback_and_payload(self):
  from unittest.mock import AsyncMock
  from rate_limit import RegistrationLimited,RegistrationUnavailable
  limiter=AsyncMock()
  self.proxy.registration_limiter=limiter
  limiter.acquire.side_effect=RegistrationLimited(retry_after=60)
  response=await self.c.post('/register',content=b'invalid-json')
  self.assertEqual(response.status_code,429);self.assertEqual(response.headers['retry-after'],'60')
  limiter.acquire.side_effect=RegistrationUnavailable()
  response=await self.c.post('/register',json={'redirect_uris':['https://bad.invalid']})
  self.assertEqual(response.status_code,503)
  self.assertEqual(limiter.acquire.await_count,2)
 async def test_registration_body_bounds_and_redirect_quota(self):
  import asyncio
  from unittest.mock import AsyncMock
  self.proxy.registration_limiter=AsyncMock()
  response=await self.c.post('/register',content=b'x'*16385)
  self.assertEqual(response.status_code,413)
  for delayed in [False,True]:
   events=[]
   async def receive():
    if delayed:await asyncio.sleep(3)
    return {'type':'http.disconnect'}
   async def send(event):events.append(event)
   await self.proxy.app({'type':'http','path':'/register','method':'POST','headers':[]},receive,send)
   self.assertEqual(events[0]['status'],413)
  before=self.proxy.registration_limiter.acquire.await_count
  response=await self.c.post('/register/',json={'redirect_uris':['https://client.invalid/callback'],'scope':'openid'},follow_redirects=True)
  self.assertEqual(response.status_code,201)
  self.assertEqual(self.proxy.registration_limiter.acquire.await_count,before+1)

 async def test_wrong_google_audience_denied(self):
  tok=(await self.exchange()).json()['access_token'];self.identity['aud']='different-client'
  r=await self.call(tok,'recall_memory',{'query':'fictional memory query'})
  self.assertEqual(r.status_code,401);self.assertEqual(self.native,[])

 async def test_issuer_metadata_stable_callback(self):
  stable='https://chatgpt.com/connector_platform_oauth_redirect'
  app=Application(replace(config('proxy'),redirects=(stable,)),storage=self.store,read_status=self.state,google_secret='synthetic-only',signing_key='synthetic-only-key',google_http=self.http,outbound_http=self.gateway_http)
  async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app.app),base_url='https://isolated.invalid') as c:
   meta=(await c.get('/.well-known/oauth-authorization-server')).json()
   self.assertIs(meta['authorization_response_iss_parameter_supported'],True)
   for uri,expected in [(stable,201),('https://chatgpt.com/connector/oauth/msuk3CV7PsAT',400),(stable+'?next=invalid',400)]:
    response=await c.post('/register',json={'redirect_uris':[uri],'scope':'openid','token_endpoint_auth_method':'none'})
    self.assertEqual(response.status_code,expected,response.text)

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
    from mcp.server.auth.provider import RegistrationError
    with self.assertRaises(RegistrationError):
     await self.proxy.provider.register_client(client)
  self.assertIn('storage_or_provider_error',' '.join(logs.output))
  self.assertNotIn('PRIVATE-ERROR',' '.join(logs.output))
 async def test_dcr_storage_failure_through_asgi_is_sanitized(self):
  from unittest.mock import AsyncMock,patch
  with patch('owner_bridge.GoogleProvider.register_client',new=AsyncMock(side_effect=RuntimeError('PRIVATE-ASGI-SECRET'))):
   with self.assertLogs(level='INFO') as logs:
    response=await self.c.post('/register',json={'redirect_uris':['https://client.invalid/callback'],'scope':'openid'})
  self.assertEqual(response.status_code,400,response.text)
  self.assertEqual(response.json()['error'],'invalid_client_metadata')
  self.assertNotIn('PRIVATE-ASGI-SECRET',response.text+' '.join(logs.output))
  self.assertIn('Registration unavailable',response.text)
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

 async def test_all_operations_route_exact_collection_only(self):
  from oauth_storage import OAuthStorage,REGISTRATION_COLLECTION
  from unittest.mock import AsyncMock
  sessions,registrations=AsyncMock(),AsyncMock();store=OAuthStorage(sessions,registrations)
  for collection in (REGISTRATION_COLLECTION,None,'mcp-refresh-tokens',REGISTRATION_COLLECTION+'-unexpected'):
   target=registrations if collection==REGISTRATION_COLLECTION else sessions
   other=sessions if target is registrations else registrations
   for method,args in [('get',('k',)),('get_many',(['k'],)),('ttl',('k',)),('ttl_many',(['k'],)),('put',('k',{'v':1})),('put_many',(['k'],[{'v':1}])),('delete',('k',)),('delete_many',(['k'],))]:
    target.reset_mock();other.reset_mock()
    await getattr(store,method)(*args,collection=collection)
    getattr(target,method).assert_awaited_once()
    self.assertEqual(other.mock_calls,[])
    self.assertEqual(getattr(target,method).call_args.kwargs['collection'],collection)
 async def test_registration_failure_never_falls_back(self):
  from oauth_storage import OAuthStorage,REGISTRATION_COLLECTION
  from unittest.mock import AsyncMock
  sessions,registrations=AsyncMock(),AsyncMock()
  registrations.get.side_effect=RuntimeError('unavailable')
  with self.assertRaises(RuntimeError):await OAuthStorage(sessions,registrations).get('k',collection=REGISTRATION_COLLECTION)
  self.assertEqual(sessions.mock_calls,[])

 async def test_pinned_registration_collection_separator(self):
  from oauth_storage import REGISTRATION_PREFIX,REGISTRATION_COLLECTION
  backing=MemoryStore()
  wrapped=FernetEncryptionWrapper(PrefixCollectionsWrapper(backing,REGISTRATION_PREFIX),fernet=Fernet(Fernet.generate_key()),raise_on_decryption_error=True)
  await wrapped.put('fixture',{'synthetic':'registered-client'},collection=REGISTRATION_COLLECTION)
  self.assertEqual(await wrapped.get('fixture',collection=REGISTRATION_COLLECTION),{'synthetic':'registered-client'})
  raw=await backing.get('fixture',collection='dot-registration-v1:__mcp-oauth-proxy-clients')
  self.assertIsNotNone(raw);self.assertNotIn('registered-client',json.dumps(raw))
  self.assertIsNone(await backing.get('fixture',collection='dot-registration-v1:mcp-oauth-proxy-clients'))
