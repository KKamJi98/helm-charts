import base64
import hashlib
import time
import unittest
from dataclasses import replace

from fastmcp.server.auth.oauth_proxy.models import ClientCode
import httpx2

from moka_oauth_canary import CanaryConfig, MokaCanary
from moka_oauth_runner import Window


CONFIG = CanaryConfig(
    client_id='12345-fixture.apps.googleusercontent.com',
    client_secret='fixture-google-secret',
    owner_sub='9876543210000',
    owner_email='owner@example.invalid',
)
VERIFIER = 'a' * 43
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()


class CanaryExchangeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.identity = {'aud': CONFIG.client_id, 'sub': CONFIG.owner_sub, 'email': CONFIG.owner_email,
                         'email_verified': True, 'scope': 'openid https://www.googleapis.com/auth/userinfo.email',
                         'expires_in': 600}

        def google(req):
            self.assertIn(req.url.host, {'oauth2.googleapis.com', 'www.googleapis.com'})
            self.assertEqual(req.headers.get('authorization'), 'Bearer fixture-google-access')
            return httpx2.Response(200, json=self.identity)

        self.google = httpx2.AsyncClient(transport=httpx2.MockTransport(google), trust_env=False)
        self.addAsyncCleanup(self.google.aclose)
        self.runtime = MokaCanary(CONFIG, google=self.google)
        self.public = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=self.runtime.public),
                                         base_url='https://hindsight.kkamji.net')
        self.addAsyncCleanup(self.public.aclose)
        metadata = (await self.public.get('/.well-known/oauth-authorization-server/moka-recall')).json()
        self.endpoint = metadata['token_endpoint']
        self.scopes = metadata['scopes_supported']
        redirects = ['https://chatgpt.com/connector_platform_oauth_redirect']
        app = await self.public.post(metadata['registration_endpoint'], json={
            'redirect_uris': redirects, 'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
            'scope': ' '.join(self.scopes),
        })
        self.assertEqual(app.status_code, 201)
        self.client_id = app.json()['client_id']
        self.redirect = redirects[0]

    async def seed(self, name):
        now = time.time()
        await self.runtime.provider._code_store.put(key=name, value=ClientCode(
            code=name, client_id=self.client_id, redirect_uri=self.redirect, code_challenge=CHALLENGE,
            code_challenge_method='S256', scopes=self.scopes, created_at=now, expires_at=now + 60,
            idp_tokens={'access_token': 'fixture-google-access', 'expires_in': 600,
                        'scope': ' '.join(self.scopes), 'refresh_token': 'fixture-should-not-be-kept'},
        ))

    async def exchange(self, name, verifier=VERIFIER):
        return await self.public.post(self.endpoint, data={'grant_type': 'authorization_code', 'code': name,
                                                           'redirect_uri': self.redirect, 'client_id': self.client_id,
                                                           'code_verifier': verifier})

    async def test_owner_receives_short_token_only_and_public_mcp_is_closed(self):
        await self.seed('fixture-good')
        invalid = await self.exchange('fixture-good', 'z' * 43)
        self.assertIn(invalid.status_code, (400, 401))
        good = await self.exchange('fixture-good')
        self.assertEqual(good.status_code, 200, good.json().get('error'))
        grant = good.json()
        self.assertEqual(grant['expires_in'], 120)
        self.assertNotIn('refresh_token', grant)
        self.assertNotIn('fixture-google-access', good.text)
        self.assertIsNotNone(await self.runtime.provider.load_access_token(grant['access_token']))
        self.assertEqual((await self.public.post('/moka-recall/mcp', headers={'Authorization': 'Bearer '+grant['access_token']})).status_code, 404)
        self.assertIn((await self.exchange('fixture-good')).status_code, (400, 401))
        self.assertEqual(self.runtime.tool_names, ('connection_check',))

    async def test_nonowner_wrong_audience_and_unverified_email_get_no_token(self):
        original = self.identity.copy()
        for i, change in enumerate(({'sub': '0000000000000'}, {'aud': 'wrong-client'},
                                    {'email': 'not-owner@example.invalid'}, {'email_verified': False},
                                    {'email_verified': 1})):
            with self.subTest(case=i):
                name = f'fixture-bad-{i}'
                await self.seed(name)
                self.identity = original | change
                res = await self.exchange(name)
                self.assertIn(res.status_code, (400, 401))
                self.assertNotIn('access_token', res.json())

    async def test_placeholder_subject_fails_before_startup(self):
        with self.assertRaises(ValueError):
            MokaCanary(replace(CONFIG, owner_sub='not-bound'), google=self.google)

    async def test_closed_preflight_never_opens_login_or_mcp(self):
        app = Window(self.runtime, None)
        base = 'http://10.0.0.1:8000'
        private = 'http://127.0.0.1:8001'
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as c:
            self.assertEqual((await c.get(base + '/.well-known/oauth-authorization-server/moka-recall')).status_code, 200)
            self.assertEqual((await c.get(private + '/.well-known/oauth-protected-resource/mcp')).status_code, 200)
            for url in ('/authorize', '/google/callback', '/consent', '/mcp'):
                self.assertEqual((await c.get(base + '/moka-recall' + url)).status_code, 404)
            for url in ('/register', '/token', '/mcp'):
                self.assertEqual((await c.post(base + '/moka-recall' + url)).status_code, 404)
            self.assertEqual((await c.post(private + '/mcp')).status_code, 404)

    async def test_only_private_listener_serves_the_synthetic_tool_and_expiry_closes_both(self):
        await self.seed('fixture-ports')
        grant = (await self.exchange('fixture-ports')).json()['access_token']
        ticks = [100]
        app = Window(self.runtime, 120, wall=lambda: ticks[0], monotonic=lambda: ticks[0])
        headers = {'Authorization': 'Bearer '+grant, 'Accept': 'application/json, text/event-stream',
                   'MCP-Protocol-Version': '2025-11-25'}
        req = {'jsonrpc': '2.0', 'method': 'tools/list', 'id': 1, 'params': {}}
        async with self.runtime.app.router.lifespan_context(self.runtime.app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as c:
                self.assertEqual((await c.post('http://10.0.0.1:8000/mcp', json=req, headers=headers)).status_code, 404)
                self.assertEqual((await c.post('http://10.0.0.1:8001/mcp', json=req, headers=headers)).status_code, 404)
                uri = 'http://127.0.0.1:8001/mcp'
                self.assertEqual((await c.post(uri, json=req)).status_code, 401)
                listing = await c.post(uri, json=req, headers=headers)
                self.assertEqual(listing.status_code, 200)
                self.assertEqual([t['name'] for t in listing.json()['result']['tools']], ['connection_check'])
                readback = await c.post(uri, headers=headers, json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                                         'params': {'name': 'connection_check', 'arguments': {}}})
                self.assertEqual(readback.json()['result']['structuredContent'], {'owner_authenticated': True, 'synthetic_only': True})
                ticks[0] = 120
                self.assertEqual((await c.post(uri, json=req, headers=headers)).status_code, 404)
                metadata = 'http://10.0.0.1:8000/.well-known/oauth-authorization-server/moka-recall'
                self.assertEqual((await c.get(metadata)).status_code, 404)
        with self.assertRaises(ValueError):
            Window(self.runtime, 120, wall=lambda: 121)
