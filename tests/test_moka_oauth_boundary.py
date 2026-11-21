import json
import unittest
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.stores.memory import MemoryStore
from starlette.testclient import TestClient

from moka_oauth_boundary import AS_METADATA, OAuthBoundary, PREFIX, PUBLIC_PATHS, RESOURCE_METADATA


class ConsentForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == 'input' and fields.get('type') == 'hidden':
            self.fields[fields['name']] = fields['value']


class OAuthBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

        async def inner(scope, receive, send):
            self.calls.append((scope['method'], scope['path'], scope['raw_path'], scope['query_string']))
            body = json.dumps({'path': scope['path']}).encode()
            await send({'type': 'http.response.start', 'status': 200, 'headers': [(b'content-type', b'application/json')]})
            await send({'type': 'http.response.body', 'body': body})

        self.client = TestClient(OAuthBoundary(inner), base_url='https://hindsight.kkamji.net')

    def test_public_endpoints_are_exact_and_rewritten(self):
        expected = {
            '/.well-known/oauth-authorization-server/moka-recall': ('GET', '/.well-known/oauth-authorization-server'),
            '/.well-known/oauth-protected-resource/moka-recall/mcp': ('GET', '/.well-known/oauth-protected-resource/moka-recall/mcp'),
            '/moka-recall/authorize': ('GET', '/authorize'),
            '/moka-recall/token': ('POST', '/token'),
            '/moka-recall/register': ('POST', '/register'),
            '/moka-recall/consent': ('POST', '/consent'),
            '/moka-recall/google/callback': ('GET', '/google/callback'),
        }
        self.assertEqual(set(PUBLIC_PATHS), set(expected))
        for path, (method, target) in expected.items():
            with self.subTest(path=path):
                response = self.client.request(method, path + '?fixture=1')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.calls[-1], (method, target, target.encode('ascii'), b'fixture=1'))
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')

    def test_public_boundary_never_dispatches_mcp_native_or_aliases(self):
        for method, path in [
            ('POST', '/moka-recall/mcp'), ('DELETE', '/moka-recall/mcp'),
            ('POST', '/mcp'), ('POST', '/v1/default/banks/personal_shared/memories/recall'),
            ('POST', '/moka-recall/token/'), ('POST', '/moka-recall/%74oken'),
            ('GET', '/moka-recall/token'), ('PUT', '/moka-recall/consent'),
            ('GET', '/moka-recall'), ('GET', '/authorize'),
        ]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.client.request(method, path, follow_redirects=False).status_code, 404)
        self.assertEqual(self.calls, [])

    def test_bounded_public_input(self):
        res = self.client.post('/moka-recall/register', content=b'x' * 16385)
        self.assertEqual(res.status_code, 413)
        self.assertEqual(self.calls, [])


class ProviderContractTest(unittest.TestCase):
    origin = 'https://hindsight.kkamji.net'
    callback = 'https://chatgpt.com/connector_platform_oauth_redirect'

    def setUp(self):
        self.provider = GoogleProvider(
            client_id='fixture.apps.googleusercontent.com', client_secret='fixture',
            base_url=self.origin + PREFIX, redirect_path='/google/callback',
            allowed_client_redirect_uris=[self.callback], client_storage=MemoryStore(),
            jwt_signing_key='synthetic-signing-key-only-for-tests', enable_cimd=False,
            required_scopes=['openid', 'email'], valid_scopes=['openid', 'email'],
        )
        mcp = FastMCP('synthetic-only', auth=self.provider)
        self.client = TestClient(OAuthBoundary(mcp.http_app(stateless_http=True, json_response=True)), base_url=self.origin)

    def test_discovery_endpoints_reference_only_the_intended_origin_and_prefix(self):
        resource = self.client.get(RESOURCE_METADATA)
        self.assertEqual(resource.status_code, 200)
        self.assertEqual(resource.json()['resource'], self.origin + PREFIX + '/mcp')
        self.assertEqual(resource.json()['authorization_servers'], [self.origin + PREFIX])
        issuer = self.client.get(AS_METADATA + PREFIX)
        self.assertEqual(issuer.status_code, 200)
        self.assertEqual(issuer.json()['issuer'], self.origin + PREFIX)
        for field, path in [('authorization_endpoint', 'authorize'), ('token_endpoint', 'token'), ('registration_endpoint', 'register')]:
            self.assertEqual(issuer.json()[field], self.origin + PREFIX + '/' + path)
        self.assertIn('S256', issuer.json()['code_challenge_methods_supported'])
        self.assertEqual(self.client.get(AS_METADATA).status_code, 404)

    def test_registration_and_google_redirect_do_not_rewrite_existing_oauth(self):
        scopes = ' '.join(self.client.get(AS_METADATA + PREFIX).json()['scopes_supported'])
        request = {'redirect_uris': [self.callback], 'token_endpoint_auth_method': 'none',
                   'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'], 'scope': scopes}
        rejected = self.client.post(PREFIX + '/register', json={**request, 'redirect_uris': ['https://example.invalid/not-allowed']})
        self.assertEqual(rejected.status_code, 400)
        approved = self.client.post(PREFIX + '/register', json=request)
        self.assertEqual(approved.status_code, 201)
        params = {'client_id': approved.json()['client_id'], 'redirect_uri': self.callback,
                  'response_type': 'code', 'code_challenge': 'a' * 43, 'code_challenge_method': 'S256',
                  'scope': scopes, 'state': 'synthetic-only', 'resource': self.origin + PREFIX + '/mcp'}
        for invalid, error in [
            ({**params, 'resource': self.origin + '/mcp'}, 'invalid_target'),
            ({k: v for k, v in params.items() if k != 'code_challenge'}, 'invalid_request'),
        ]:
            refused = self.client.get(PREFIX + '/authorize', params=invalid, follow_redirects=False)
            self.assertEqual(refused.status_code, 302)
            dest = urlsplit(refused.headers['location'])
            self.assertEqual(f'{dest.scheme}://{dest.netloc}{dest.path}', self.callback)
            self.assertEqual(parse_qs(dest.query)['error'], [error])
        response = self.client.get(PREFIX + '/authorize', params=params, follow_redirects=False)
        self.assertIn(response.status_code, (302, 303, 307))
        consent = urlsplit(response.headers['location'])
        self.assertEqual((consent.scheme, consent.netloc, consent.path), ('https', 'hindsight.kkamji.net', PREFIX + '/consent'))
        form = self.client.get(response.headers['location'], follow_redirects=False)
        self.assertEqual(form.status_code, 200)
        parsed = ConsentForm()
        parsed.feed(form.text)
        fields = {**parsed.fields, 'action': 'approve'}
        response = self.client.post(PREFIX + '/consent', data=fields, follow_redirects=False)
        self.assertIn(response.status_code, (302, 303, 307))
        url = urlsplit(response.headers['location'])
        self.assertEqual(url.netloc, 'accounts.google.com')
        self.assertEqual(parse_qs(url.query)['redirect_uri'], [self.origin + PREFIX + '/google/callback'])
