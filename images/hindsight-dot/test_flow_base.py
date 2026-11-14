"""Actual FastMCP HTTP token endpoint, synthetic pre-seeded Google callback result."""
import unittest,time,hashlib,base64,contextlib
import httpx2
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from fastmcp.server.auth.oauth_proxy.models import ClientCode
from key_value.aio.stores.memory import MemoryStore
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyUrl
from emergency_gate import GateStatus,EmergencyGate

class FlowTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.status=GateStatus(True,1);self.refresh_calls=0
  async def state():return self.status
  self.state=state
  self.http=httpx2.AsyncClient(transport=httpx2.MockTransport(lambda r:httpx2.Response(200,json={'aud':'fake-client','sub':'fake-owner','scope':'openid','expires_in':600})))
  self.p=self.provider()
  self.app=EmergencyGate(FastMCP('isolated',auth=self.p).http_app(),state,1)
  self.c=httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.app),base_url='https://isolated.invalid')
  self.verifier='v'*43
  challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b'=').decode()
  await self.p.register_client(OAuthClientInformationFull(client_id='test-client',redirect_uris=[AnyUrl('https://client.invalid/callback')],scope='openid',grant_types=['authorization_code','refresh_token']))
  await self.p._code_store.put(key='synthetic-code',value=ClientCode(code='synthetic-code',client_id='test-client',redirect_uri='https://client.invalid/callback',code_challenge=challenge,code_challenge_method='S256',scopes=['openid'],idp_tokens={'access_token':'synthetic-upstream','refresh_token':'synthetic-refresh','expires_in':600,'scope':'openid'},expires_at=time.time()+60,created_at=time.time()))
  @contextlib.asynccontextmanager
  async def upstream():
   outer=self
   class Fake:
    async def refresh_token(self,**kwargs):
     outer.refresh_calls+=1
     return {'access_token':'synthetic-upstream-new','refresh_token':'synthetic-refresh-new','expires_in':600,'scope':'openid'}
   yield Fake()
  self.p._upstream_oauth_client=upstream
 def provider(self):
  return GoogleProvider(client_id='fake-client',client_secret='synthetic-secret-only',base_url='https://isolated.invalid',client_storage=MemoryStore(),http_client=self.http,fastmcp_access_token_expiry_seconds=60)
 async def asyncTearDown(self):await self.c.aclose();await self.http.aclose()
 async def exchange(self,verifier=None):
  return await self.c.post('/token',data={'grant_type':'authorization_code','client_id':'test-client','code':'synthetic-code','redirect_uri':'https://client.invalid/callback','code_verifier':verifier or self.verifier})
 async def refresh(self,token):
  return await self.c.post('/token',data={'grant_type':'refresh_token','client_id':'test-client','refresh_token':token})
 async def test_pkce_then_exchange_refresh_rotation(self):
  bad=await self.exchange('w'*43);self.assertIn(bad.status_code,(400,401))
  good=await self.exchange();self.assertEqual(good.status_code,200,good.text)
  tokens=good.json();self.assertEqual(tokens['expires_in'],60)
  self.assertIsNotNone(await self.p.load_access_token(tokens['access_token']))
  again=await self.exchange();self.assertIn(again.status_code,(400,401))
  refreshed=await self.refresh(tokens['refresh_token']);self.assertEqual(refreshed.status_code,200,refreshed.text)
  self.assertNotEqual(refreshed.json()['refresh_token'],tokens['refresh_token'])
  reused=await self.refresh(tokens['refresh_token']);self.assertIn(reused.status_code,(400,401))
 async def test_gate_prevents_refresh_without_upstream_call(self):
  tokens=(await self.exchange()).json();self.status=GateStatus(False,2)
  r=await self.refresh(tokens['refresh_token']);self.assertEqual(r.status_code,503);self.assertEqual(self.refresh_calls,0)
 async def test_fresh_store_restart_denies_old_access_refresh(self):
  tokens=(await self.exchange()).json();fresh=self.provider();FastMCP('fresh',auth=fresh).http_app()
  self.assertIsNone(await fresh.load_access_token(tokens['access_token']))
  self.assertIsNone(await fresh.load_refresh_token(OAuthClientInformationFull(client_id='test-client'),tokens['refresh_token']))
