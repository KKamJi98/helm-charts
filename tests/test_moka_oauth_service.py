import asyncio
import base64
import hashlib
import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from cryptography.fernet import Fernet
from fastmcp.server.auth.oauth_proxy.models import ClientCode
import httpx2
from mcp.server.auth.provider import TokenError

from moka_oauth_canary import RECALL_URL, CanaryConfig, MokaCanary, ServiceConfig
from moka_oauth_runner import Window


CONFIG = CanaryConfig(
    client_id="12345-fixture.apps.googleusercontent.com",
    client_secret="fixture-google-secret",
    owner_sub="9876543210000",
    owner_email="owner@example.invalid",
)
RECALL_KEY = "r" * 48
VERIFIER = "b" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}


def service_config(directory, **changes):
    base = ServiceConfig(
        recall_key=RECALL_KEY,
        jwt_signing_key=b"s" * 32,
        storage_key=Fernet.generate_key().decode(),
        state_dir=Path(directory),
    )
    return replace(base, **changes)


class ServiceConfigTest(unittest.TestCase):
    def test_rejects_weak_or_missing_service_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            for change in (
                {"recall_key": "short"},
                {"recall_key": " " + RECALL_KEY},
                {"jwt_signing_key": b"x" * 16},
                {"storage_key": "not-fernet"},
                {"state_dir": Path("relative")},
            ):
                with self.subTest(change=sorted(change)):
                    with self.assertRaises(ValueError):
                        service_config(tmp, **change)

    def test_reads_secret_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = Fernet.generate_key().decode()
            (root / "recall_api_key").write_text(RECALL_KEY + "\n")
            (root / "jwt_signing_key").write_text(base64.b64encode(b"j" * 32).decode())
            (root / "storage_encryption_key").write_text(key)
            cfg = ServiceConfig.from_secret_files(root, "/var/lib/moka-oauth/grants")
            self.assertEqual(
                (cfg.recall_key, cfg.jwt_signing_key, cfg.storage_key),
                (RECALL_KEY, b"j" * 32, key),
            )
            self.assertNotIn(RECALL_KEY, repr(cfg))


class ServiceRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = service_config(self.tmp.name)
        self.identity = {
            "aud": CONFIG.client_id,
            "sub": CONFIG.owner_sub,
            "email": CONFIG.owner_email,
            "email_verified": True,
            "scope": "openid https://www.googleapis.com/auth/userinfo.email",
            "expires_in": 3000,
        }
        self.hindsight_calls = []
        self.hindsight_reply = None

        def google(req):
            self.assertIn(req.url.host, {"oauth2.googleapis.com", "www.googleapis.com"})
            self.assertEqual(
                req.headers.get("authorization"), "Bearer fixture-google-access"
            )
            return httpx2.Response(200, json=self.identity)

        def hindsight(req):
            self.hindsight_calls.append(req)
            if self.hindsight_reply is not None:
                return self.hindsight_reply
            return httpx2.Response(
                200,
                json={
                    "bank": "personal_shared",
                    "results": [
                        {
                            "text": "fixture memory",
                            "type": "world",
                            "mentioned_at": "2026-11-01T00:00:00Z",
                            "occurred_start": None,
                            "occurred_end": None,
                            "document_id": "not-forwarded",
                        }
                    ],
                },
            )

        self.google = httpx2.AsyncClient(
            transport=httpx2.MockTransport(google), trust_env=False
        )
        self.hindsight = httpx2.AsyncClient(
            transport=httpx2.MockTransport(hindsight), trust_env=False
        )
        self.addAsyncCleanup(self.google.aclose)
        self.addAsyncCleanup(self.hindsight.aclose)
        self.runtime = self.make_runtime()
        self.public = httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=self.runtime.public),
            base_url="https://hindsight.kkamji.net",
        )
        self.addAsyncCleanup(self.public.aclose)
        metadata = (
            await self.public.get("/.well-known/oauth-authorization-server/moka-recall")
        ).json()
        self.endpoint = metadata["token_endpoint"]
        self.scopes = metadata["scopes_supported"]
        app = await self.public.post(
            metadata["registration_endpoint"],
            json={
                "redirect_uris": [CALLBACK],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": " ".join(self.scopes),
            },
        )
        self.assertEqual(app.status_code, 201)
        self.client_id = app.json()["client_id"]

    def make_runtime(self):
        return MokaCanary(
            CONFIG, google=self.google, service=self.service, hindsight=self.hindsight
        )

    async def grant(self, name="fixture-code"):
        now = time.time()
        await self.runtime.provider._code_store.put(
            key=name,
            value=ClientCode(
                code=name,
                client_id=self.client_id,
                redirect_uri=CALLBACK,
                code_challenge=CHALLENGE,
                code_challenge_method="S256",
                scopes=self.scopes,
                created_at=now,
                expires_at=now + 60,
                idp_tokens={
                    "access_token": "fixture-google-access",
                    "expires_in": 3000,
                    "scope": " ".join(self.scopes),
                    "refresh_token": "fixture-google-refresh",
                },
            ),
        )
        return await self.public.post(
            self.endpoint,
            data={
                "grant_type": "authorization_code",
                "code": name,
                "redirect_uri": CALLBACK,
                "client_id": self.client_id,
                "code_verifier": VERIFIER,
            },
        )

    async def test_owner_grant_is_refreshable_encrypted_and_survives_restart(self):
        res = await self.grant()
        self.assertEqual(res.status_code, 200, res.text)
        grant = res.json()
        self.assertIn("refresh_token", grant)
        self.assertLessEqual(grant["expires_in"], 3600)
        self.assertNotIn("fixture-google", res.text)
        stored = b"".join(
            p.read_bytes() for p in Path(self.tmp.name).rglob("*") if p.is_file()
        )
        self.assertTrue(stored)
        for secret in (
            b"fixture-google-access",
            b"fixture-google-refresh",
            self.client_id.encode(),
        ):
            self.assertNotIn(secret, stored)
        restarted = self.make_runtime()
        self.assertIsNotNone(
            await restarted.provider.load_access_token(grant["access_token"])
        )
        self.assertIsNotNone(await restarted.provider.get_client(self.client_id))
        other_key = self.make_runtime_with(storage_key=Fernet.generate_key().decode())
        self.assertIsNone(await other_key.provider.load_access_token(grant["access_token"]))

    def make_runtime_with(self, **changes):
        return MokaCanary(
            CONFIG,
            google=self.google,
            service=replace(self.service, **changes),
            hindsight=self.hindsight,
        )

    async def test_nonowner_gets_no_grant_and_revoked_owner_loses_access(self):
        original = self.identity.copy()
        for i, change in enumerate(
            (
                {"sub": "0000000000000"},
                {"aud": "wrong-client"},
                {"email": "not-owner@example.invalid"},
                {"email_verified": False},
            )
        ):
            with self.subTest(case=i):
                self.identity = original | change
                res = await self.grant(f"fixture-bad-{i}")
                self.assertIn(res.status_code, (400, 401))
                self.assertNotIn("access_token", res.json())
        self.identity = original
        token = (await self.grant("fixture-good")).json()["access_token"]
        self.identity = original | {"email": "changed@example.invalid"}
        self.assertIsNone(await self.runtime.provider.load_access_token(token))

    async def test_unauthenticated_oauth_state_never_reaches_disk_and_clients_are_capped(self):
        self.assertEqual((await self.grant()).status_code, 200)
        names = [p.name for p in Path(self.tmp.name).rglob('*')]
        for ephemeral in ('transaction', 'authorization-codes', 'csrf'):
            self.assertFalse(any(ephemeral in n for n in names), (ephemeral, names))
        self.assertTrue(any('upstream' in n for n in names), names)
        token = (await self.grant('fixture-owner-client')).json()['access_token']
        state = self.runtime.provider.state
        owner_files = state.stored_clients()
        filler = '{"created_at": "2026-11-21T00:00:00+00:00", "value": {"x": 1}, "version": 1}'
        anonymous = [owner_files[0].parent / f'anonymous-{i}.json' for i in range(128)]
        for path in anonymous:
            path.write_text(filler)
        self.assertEqual((await self.register()).status_code, 400)  # recent clients are never evicted
        old = time.time() - 7200
        for path in anonymous:
            os.utime(path, (old, old))
        res = await self.register()
        self.assertEqual(res.status_code, 201, res.text)
        names = {p.name for p in state.stored_clients()}
        self.assertIn(owner_files[0].name, names)
        self.assertLessEqual(len(names), 129)
        self.assertGreater(sum(n.startswith('anonymous-') for n in names), 120)
        self.assertIsNotNone(await self.runtime.provider.load_access_token(token))
        self.assertIsNotNone(await self.runtime.provider.get_client(self.client_id))

    async def register(self):
        return await self.public.post('/moka-recall/register', json={
            'redirect_uris': [CALLBACK], 'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
            'scope': ' '.join(self.scopes)})

    async def test_concurrent_registrations_respect_the_rate_limit(self):
        results = await asyncio.gather(*(self.register() for _ in range(20)))
        self.assertEqual(sum(r.status_code == 201 for r in results), 11)  # 1 used in setUp

    async def test_only_chatgpt_stable_or_callback_id_redirects_register(self):
        cid = 'https://chatgpt.com/connector/oauth/AbC_123-xyz'
        accepted = ([CALLBACK], [cid], [CALLBACK, cid])
        rejected = (['https://evil.example/connector/oauth/abc'], ['https://chatgpt.com/connector/oauth/../x'],
                    ['http://chatgpt.com/connector/oauth/abc'], ['https://chatgpt.com/connector/oauth/abc?x=1'],
                    ['https://chatgpt.com/connector/oauth/abc/extra'], [CALLBACK, 'https://evil.example/cb'],
                    [f'https://chatgpt.com/connector/oauth/a{i}' for i in range(5)], [])
        for uris in accepted + rejected:
            with self.subTest(uris=uris):
                res = await self.public.post('/moka-recall/register', json={
                    'redirect_uris': uris, 'token_endpoint_auth_method': 'none',
                    'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
                    'scope': ' '.join(self.scopes)})
                self.assertEqual(res.status_code, 201 if uris in accepted else 400, res.text)

    async def test_callback_id_client_completes_owner_grant(self):
        cid = 'https://chatgpt.com/connector/oauth/AbC_123-xyz'
        app = await self.public.post('/moka-recall/register', json={
            'redirect_uris': [cid], 'token_endpoint_auth_method': 'none',
            'grant_types': ['authorization_code', 'refresh_token'], 'response_types': ['code'],
            'scope': ' '.join(self.scopes)})
        client_id = app.json()['client_id']
        now = time.time()
        await self.runtime.provider._code_store.put(key='fixture-cid', value=ClientCode(
            code='fixture-cid', client_id=client_id, redirect_uri=cid, code_challenge=CHALLENGE,
            code_challenge_method='S256', scopes=self.scopes, created_at=now, expires_at=now + 60,
            idp_tokens={'access_token': 'fixture-google-access', 'expires_in': 3000,
                        'scope': ' '.join(self.scopes), 'refresh_token': 'fixture-google-refresh'}))
        res = await self.public.post(self.endpoint, data={
            'grant_type': 'authorization_code', 'code': 'fixture-cid', 'redirect_uri': cid,
            'client_id': client_id, 'code_verifier': VERIFIER})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNotNone(await self.runtime.provider.load_access_token(res.json()['access_token']))

    async def test_refresh_is_delegated_instead_of_refused(self):
        client = await self.runtime.provider.get_client(self.client_id)
        bogus = type(
            "R",
            (),
            {"token": "not-a-jwt", "client_id": self.client_id, "scopes": self.scopes},
        )()
        with self.assertRaises(TokenError) as raised:
            await self.runtime.provider.exchange_refresh_token(
                client, bogus, self.scopes
            )
        self.assertNotIn("Canary", str(raised.exception.error_description))

    async def test_recall_tool_is_the_only_tool_and_reads_only_the_fixed_endpoint(self):
        token = (await self.grant()).json()["access_token"]
        app = Window(self.runtime, None, service=True)
        headers = MCP_HEADERS | {"Authorization": "Bearer " + token}
        listing = {"jsonrpc": "2.0", "method": "tools/list", "id": 1, "params": {}}
        async with self.runtime.app.router.lifespan_context(self.runtime.app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app)) as c:
                private = "http://127.0.0.1:8001/mcp"
                self.assertEqual(
                    (
                        await c.post(
                            "http://10.0.0.1:8000/mcp", json=listing, headers=headers
                        )
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    (
                        await c.post(
                            "http://10.0.0.1:8000/moka-recall/mcp",
                            json=listing,
                            headers=headers,
                        )
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    (
                        await c.post(
                            "http://10.0.0.1:8001/mcp", json=listing, headers=headers
                        )
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    (
                        await c.post(private, json=listing, headers=MCP_HEADERS)
                    ).status_code,
                    401,
                )
                self.assertEqual(
                    (
                        await c.get(
                            "http://10.0.0.1:8000/.well-known/oauth-authorization-server/moka-recall"
                        )
                    ).status_code,
                    200,
                )
                tools = (await c.post(private, json=listing, headers=headers)).json()[
                    "result"
                ]["tools"]
                self.assertEqual([t["name"] for t in tools], ["recall"])
                self.assertTrue(tools[0]["annotations"]["readOnlyHint"])
                self.assertEqual(set(tools[0]["inputSchema"]["properties"]), {"query"})

                async def call(arguments):
                    res = await c.post(
                        private,
                        headers=headers,
                        json={
                            "jsonrpc": "2.0",
                            "id": 2,
                            "method": "tools/call",
                            "params": {"name": "recall", "arguments": arguments},
                        },
                    )
                    return res.json()["result"]

                result = await call({"query": "what is the homelab?"})
                self.assertFalse(result.get("isError"))
                self.assertEqual(
                    result["structuredContent"],
                    {
                        "bank": "personal_shared",
                        "results": [
                            {
                                "text": "fixture memory",
                                "type": "world",
                                "mentioned_at": "2026-11-01T00:00:00Z",
                                "occurred_start": None,
                                "occurred_end": None,
                            }
                        ],
                    },
                )
                (req,) = self.hindsight_calls
                self.assertEqual((req.method, str(req.url)), ("POST", RECALL_URL))
                self.assertEqual(req.headers["authorization"], "Bearer " + RECALL_KEY)
                self.assertEqual(
                    json.loads(req.content), {"query": "what is the homelab?"}
                )

                for args in (
                    {"query": "x", "bank_id": "other"},
                    {"query": ""},
                    {"query": "a" * 1001},
                ):
                    with self.subTest(args=sorted(args)):
                        self.assertTrue((await call(args)).get("isError"))
                self.assertEqual(len(self.hindsight_calls), 1)

                for reply in (
                    httpx2.Response(401, json={"error": "unauthorized"}),
                    httpx2.Response(200, json={"bank": "other", "results": []}),
                ):
                    self.hindsight_reply = reply
                    failed = await call({"query": "x"})
                    self.assertTrue(failed.get("isError"))
                    self.assertNotIn(RECALL_KEY, json.dumps(failed))

    async def test_service_mode_never_takes_a_deadline(self):
        with self.assertRaises(ValueError):
            Window(self.runtime, int(time.time()) + 60, service=True)


if __name__ == "__main__":
    unittest.main()
