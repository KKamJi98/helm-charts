"""Bidirectional retain_summary, privacy scanner, and Grok Bot MCP contract tests."""

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx2
import yaml
from cryptography.fernet import Fernet
from fastmcp.server.auth.oauth_proxy.models import ClientCode
from moka_oauth_canary import (
    RECALL_URL,
    RETAIN_URL,
    CanaryConfig,
    MokaCanary,
    ServiceConfig,
)
from moka_oauth_scanner import passes_policy_regex, safe_summary_text
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from test_moka_oauth_recall_ext import install_stubs

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts/hindsight"
RECALL_KEY = "r" * 48
RETAIN_KEY = "w" * 48
BEARER_TOKEN = "b" * 48
GROK_CALLBACK = "https://grok.com/connectors-oauth-exchange-code/"
CHATGPT_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
GITLEAKS_BIN = shutil.which("gitleaks") or "/opt/homebrew/bin/gitleaks"
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}
CONFIG = CanaryConfig(
    client_id="12345-fixture.apps.googleusercontent.com",
    client_secret="fixture-google-secret",
    owner_sub="9876543210000",
    owner_email="owner@example.invalid",
)
VERIFIER = "v" * 43
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest())
    .rstrip(b"=")
    .decode()
)


class RetainMemoryStub:
    def __init__(self):
        self.recall_calls = []
        self.retain_calls = []

    async def recall_async(self, **kwargs):
        self.recall_calls.append(kwargs)
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    text="fixture fact",
                    fact_type="world",
                    mentioned_at="2026-11-28T00:00:00Z",
                    occurred_start=None,
                    occurred_end=None,
                )
            ]
        )

    async def submit_async_retain(
        self, bank_id, contents, *, request_context, operation_id=None, **kwargs
    ):
        self.retain_calls.append(
            {
                "bank_id": bank_id,
                "contents": contents,
                "request_context": request_context,
                "operation_id": operation_id,
                "extra": kwargs,
            }
        )
        return {"operation_id": operation_id, "items_count": len(contents)}


class RetainExtensionTests(unittest.TestCase):
    def setUp(self):
        self.ext_module = install_stubs()
        self.memory = RetainMemoryStub()
        ext = self.ext_module.MokaRecallHttpExtension(
            {"moka_recall_key": RECALL_KEY, "moka_retain_key": RETAIN_KEY}
        )
        router = ext.get_router(self.memory)
        app = Starlette(
            routes=[
                Route("/ext" + path, handler, methods=["POST"])
                for path, handler in router.routes
            ]
        )
        self.client = TestClient(app)
        self.url = "/ext/moka-recall/retain"
        self.ok = {"Authorization": "Bearer " + RETAIN_KEY}

    def test_refuses_weak_or_reused_retain_key(self):
        for bad in ("short", " " + RETAIN_KEY, RECALL_KEY):
            with self.subTest(bad=bad[:6]), self.assertRaises(ValueError):
                self.ext_module.MokaRecallHttpExtension(
                    {"moka_recall_key": RECALL_KEY, "moka_retain_key": bad}
                )

    def test_rejects_missing_wrong_or_recall_key_on_retain(self):
        payload = {
            "summary": "Owner prefers Rust for new personal tools.",
            "conversation_id": "conv_1",
            "message_id": "msg_1",
            "source": "chatgpt_dot",
        }
        for headers in (
            {},
            {"Authorization": "Bearer " + RECALL_KEY},
            {"Authorization": "Bearer " + "x" * 48},
            {"Authorization": "Basic " + RETAIN_KEY},
        ):
            with self.subTest(headers=sorted(headers)):
                res = self.client.post(self.url, json=payload, headers=headers)
                self.assertEqual(res.status_code, 401)
        self.assertEqual(self.memory.retain_calls, [])

    def test_rejects_invalid_shapes_and_policy_violations(self):
        base = {
            "summary": "Owner prefers Rust for new personal tools.",
            "conversation_id": "conv-1",
            "message_id": "msg-1",
            "source": "grok_bot",
        }
        for bad, code in (
            ({**base, "bank_id": "other"}, 400),
            ({**base, "source": "unknown_client"}, 400),
            ({**base, "conversation_id": "../escape"}, 400),
            ({**base, "summary": "short"}, 400),
            ({**base, "summary": "a" * 4001}, 400),
            ({**base, "summary": "Company bunjang internal note"}, 422),
            ({**base, "summary": "Look at code-work deployment steps"}, 422),
            ({**base, "summary": "Ticket TECH-4683 follow-up item"}, 422),
            ({**base, "summary": "api_key: super-secret-credential-value"}, 422),
            ({**base, "summary": "-" * 5 + "BEGIN PRIVATE KEY" + "-" * 5}, 422),
        ):
            with self.subTest(code=code, summary=str(bad.get("summary", ""))[:24]):
                res = self.client.post(self.url, json=bad, headers=self.ok)
                self.assertEqual(res.status_code, code)
        big = b'{"summary":"' + b"a" * 17000 + b'"}'
        self.assertEqual(
            self.client.post(self.url, content=big, headers=self.ok).status_code, 413
        )
        self.assertEqual(self.memory.retain_calls, [])

    def test_accepts_clean_summary_with_fixed_bank_and_idempotent_ids(self):
        payload = {
            "summary": "  Owner confirmed AWS re:Invent 2026 travel prep notes.  ",
            "conversation_id": "grok-thread-42",
            "message_id": "msg_99",
            "source": "grok_bot",
        }
        res = self.client.post(self.url, json=payload, headers=self.ok)
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.headers["cache-control"], "no-store")
        digest = hashlib.sha256(b"grok_bot\x00grok-thread-42\x00msg_99").hexdigest()
        doc_id = f"grok_bot-summary-{digest}"
        op_id = str(uuid.uuid5(uuid.NAMESPACE_URL, doc_id))
        self.assertEqual(
            res.json(),
            {
                "bank": "personal_shared",
                "status": "accepted_not_extracted",
                "operation_id": op_id,
                "document_id": doc_id,
            },
        )
        (call,) = self.memory.retain_calls
        self.assertEqual(call["bank_id"], "personal_shared")
        self.assertEqual(call["operation_id"], op_id)
        self.assertEqual(len(call["contents"]), 1)
        item = call["contents"][0]
        self.assertEqual(
            item["content"], "Owner confirmed AWS re:Invent 2026 travel prep notes."
        )
        self.assertEqual(item["document_id"], doc_id)
        self.assertEqual(
            item["metadata"],
            {
                "source": "grok_bot_user_conversation_summary",
                "host": "grok_bot",
                "schema": "v1",
            },
        )


class ScannerTests(unittest.TestCase):
    def test_policy_regex_blocks_company_and_secret_patterns(self):
        self.assertTrue(passes_policy_regex("Owner likes dark female-vocal pop songs."))
        for bad in (
            "tiny",
            "bunjang cluster alert",
            "번장 배포 기록",
            "vault-company note",
            "DAC-1234 ticket",
            "token" + ": " + "a" * 16,
            "-" * 5 + "BEGIN OPENSSH PRIVATE KEY" + "-" * 5,
            "CONTEXT COMPACTION summary",
        ):
            with self.subTest(bad=bad):
                self.assertFalse(passes_policy_regex(bad))

    def test_safe_summary_text_fails_closed_when_scanner_missing(self):
        self.assertFalse(
            safe_summary_text(
                "Clean personal preference text.",
                scanner_path="/nonexistent/gitleaks",
            )
        )
        self.assertFalse(
            safe_summary_text(
                "Clean personal preference text.",
                scanner_path="gitleaks",
            )
        )

    @unittest.skipUnless(Path(GITLEAKS_BIN).is_file(), "gitleaks binary required")
    def test_safe_summary_text_with_real_gitleaks(self):
        self.assertTrue(
            safe_summary_text(
                "Owner plans to review Envoy Gateway route policies next week.",
                scanner_path=GITLEAKS_BIN,
            )
        )
        # Synthetic high-entropy GitHub PAT pattern (constructed dynamically)
        synthetic_pat = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
        self.assertFalse(
            safe_summary_text(
                f"Do not store {synthetic_pat} in memory.",
                scanner_path=GITLEAKS_BIN,
            )
        )


class BidirectionalAndGrokRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hindsight_calls = []
        self.identity = {
            "aud": CONFIG.client_id,
            "sub": CONFIG.owner_sub,
            "email": CONFIG.owner_email,
            "email_verified": True,
            "scope": "openid https://www.googleapis.com/auth/userinfo.email",
            "expires_in": 3000,
        }

        def google(req):
            return httpx2.Response(200, json=self.identity)

        def hindsight(req):
            self.hindsight_calls.append(req)
            body = json.loads(req.content)
            if str(req.url) == RECALL_URL:
                return httpx2.Response(
                    200,
                    json={
                        "bank": "personal_shared",
                        "results": [
                            {
                                "text": "synced fact",
                                "type": "world",
                                "mentioned_at": "2026-11-28T00:00:00Z",
                                "occurred_start": None,
                                "occurred_end": None,
                            }
                        ],
                    },
                )
            if str(req.url) == RETAIN_URL:
                doc_id = f"{body['source']}-summary-{'a' * 64}"
                return httpx2.Response(
                    202,
                    json={
                        "bank": "personal_shared",
                        "status": "accepted_not_extracted",
                        "operation_id": "op-1234",
                        "document_id": doc_id,
                    },
                )
            return httpx2.Response(404, json={"error": "not_found"})

        self.google = httpx2.AsyncClient(
            transport=httpx2.MockTransport(google), trust_env=False
        )
        self.hindsight = httpx2.AsyncClient(
            transport=httpx2.MockTransport(hindsight), trust_env=False
        )
        self.addAsyncCleanup(self.google.aclose)
        self.addAsyncCleanup(self.hindsight.aclose)

    async def _issue_owner_token(self, runtime, public_client, metadata, callback_uri):
        reg = await public_client.post(
            metadata["registration_endpoint"],
            json={
                "redirect_uris": [callback_uri],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "scope": " ".join(metadata["scopes_supported"]),
            },
        )
        self.assertEqual(reg.status_code, 201)
        client_id = reg.json()["client_id"]
        code = "code-" + client_id[:8]
        await runtime.provider._code_store.put(
            key=code,
            value=ClientCode(
                code=code,
                client_id=client_id,
                redirect_uri=callback_uri,
                code_challenge=CHALLENGE,
                code_challenge_method="S256",
                scopes=metadata["scopes_supported"],
                idp_tokens={
                    "access_token": "fixture-google-access",
                    "token_type": "Bearer",
                    "expires_in": 3000,
                },
                created_at=time.time(),
                expires_at=time.time() + 120,
            ),
            ttl=120,
        )
        tok = await public_client.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_uri,
                "client_id": client_id,
                "code_verifier": VERIFIER,
            },
        )
        self.assertEqual(tok.status_code, 200)
        return tok.json()["access_token"]

    @unittest.skipUnless(Path(GITLEAKS_BIN).is_file(), "gitleaks binary required")
    async def test_moka_bidirectional_keeps_public_mcp_closed_and_gates_retain(self):
        state_dir = Path(self.tmp.name) / "moka"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        service = ServiceConfig(
            recall_key=RECALL_KEY,
            retain_key=RETAIN_KEY,
            retain_source="chatgpt_dot",
            scanner_path=GITLEAKS_BIN,
            jwt_signing_key=b"s" * 32,
            storage_key=Fernet.generate_key().decode(),
            state_dir=state_dir,
        )
        runtime = MokaCanary(
            CONFIG, google=self.google, service=service, hindsight=self.hindsight
        )
        self.assertEqual(runtime.tool_names, ("recall", "retain_summary"))
        async with (
            runtime.app.router.lifespan_context(runtime.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=runtime.public),
                base_url="https://hindsight.kkamji.net",
            ) as public,
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=runtime.private),
                base_url="http://127.0.0.1:8001",
            ) as private,
        ):
            # Public /moka-recall/mcp MUST stay 404.
            self.assertEqual((await public.post("/moka-recall/mcp")).status_code, 404)
            metadata = (
                await public.get("/.well-known/oauth-authorization-server/moka-recall")
            ).json()
            token = await self._issue_owner_token(
                runtime, public, metadata, CHATGPT_CALLBACK
            )
            headers = {**MCP_HEADERS, "Authorization": "Bearer " + token}

            # Blocked company summary must NOT hit Hindsight API.
            blocked = await private.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "retain_summary",
                        "arguments": {
                            "summary": "Internal bunjang deployment note",
                            "conversation_id": "dot_c1",
                            "message_id": "dot_m1",
                        },
                    },
                },
            )
            self.assertEqual(blocked.status_code, 200)
            self.assertTrue(blocked.json()["result"]["isError"])
            self.assertEqual(self.hindsight_calls, [])

            # Clean summary succeeds with source=chatgpt_dot and retain_key.
            ok = await private.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "retain_summary",
                        "arguments": {
                            "summary": "Owner prefers weekly spaced repetition with Anki.",
                            "conversation_id": "dot_c1",
                            "message_id": "dot_m2",
                        },
                    },
                },
            )
            self.assertEqual(ok.status_code, 200)
            self.assertFalse(ok.json()["result"].get("isError", False))
            self.assertEqual(len(self.hindsight_calls), 1)
            sent = self.hindsight_calls[0]
            self.assertEqual(str(sent.url), RETAIN_URL)
            self.assertEqual(sent.headers["authorization"], "Bearer " + RETAIN_KEY)
            self.assertEqual(json.loads(sent.content)["source"], "chatgpt_dot")

    @unittest.skipUnless(Path(GITLEAKS_BIN).is_file(), "gitleaks binary required")
    async def test_grok_oauth_mode_public_mcp_and_callback_allowlist(self):
        state_dir = Path(self.tmp.name) / "grok-oauth"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        service = ServiceConfig(
            recall_key=RECALL_KEY,
            retain_key=RETAIN_KEY,
            retain_source="grok_bot",
            scanner_path=GITLEAKS_BIN,
            jwt_signing_key=b"g" * 32,
            storage_key=Fernet.generate_key().decode(),
            state_dir=state_dir,
            prefix="/grok-memory",
            allowed_callbacks=(GROK_CALLBACK,),
            allow_public_mcp=True,
        )
        runtime = MokaCanary(
            CONFIG, google=self.google, service=service, hindsight=self.hindsight
        )
        async with (
            runtime.app.router.lifespan_context(runtime.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=runtime.public),
                base_url="https://hindsight.kkamji.net",
            ) as public,
        ):
            # Unauthenticated /grok-memory/mcp must return 401.
            unauth = await public.post(
                "/grok-memory/mcp",
                headers=MCP_HEADERS,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            self.assertEqual(unauth.status_code, 401)
            metadata = (
                await public.get("/.well-known/oauth-authorization-server/grok-memory")
            ).json()
            # ChatGPT callback must be rejected by Grok DCR allowlist.
            bad_reg = await public.post(
                metadata["registration_endpoint"],
                json={
                    "redirect_uris": [CHATGPT_CALLBACK],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "scope": " ".join(metadata["scopes_supported"]),
                },
            )
            self.assertEqual(bad_reg.status_code, 400)

            token = await self._issue_owner_token(
                runtime, public, metadata, GROK_CALLBACK
            )
            headers = {**MCP_HEADERS, "Authorization": "Bearer " + token}
            res = await public.post(
                "/grok-memory/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "retain_summary",
                        "arguments": {
                            "summary": "Owner wants Grok Bot to share personal_shared context.",
                            "conversation_id": "grok_c1",
                            "message_id": "grok_m1",
                        },
                    },
                },
            )
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["result"].get("isError", False))
            self.assertEqual(
                json.loads(self.hindsight_calls[-1].content)["source"], "grok_bot"
            )

    @unittest.skipUnless(Path(GITLEAKS_BIN).is_file(), "gitleaks binary required")
    async def test_grok_bearer_mode_enforces_token_and_blocks_oauth_paths(self):
        service = ServiceConfig(
            recall_key=RECALL_KEY,
            retain_key=RETAIN_KEY,
            retain_source="grok_bot",
            scanner_path=GITLEAKS_BIN,
            jwt_signing_key=b"",
            storage_key="",
            state_dir=Path(self.tmp.name) / "grok-bearer",
            prefix="/grok-memory",
            allow_public_mcp=True,
            bearer_token=BEARER_TOKEN,
        )
        runtime = MokaCanary(
            None, google=self.google, service=service, hindsight=self.hindsight
        )
        async with (
            runtime.app.router.lifespan_context(runtime.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=runtime.public),
                base_url="https://hindsight.kkamji.net",
            ) as public,
        ):
            # OAuth endpoints are closed (404) in bearer mode.
            self.assertEqual(
                (
                    await public.get(
                        "/.well-known/oauth-authorization-server/grok-memory"
                    )
                ).status_code,
                404,
            )
            # Missing/wrong token -> 401.
            self.assertEqual(
                (
                    await public.post(
                        "/grok-memory/mcp",
                        headers=MCP_HEADERS,
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    )
                ).status_code,
                401,
            )
            self.assertEqual(
                (
                    await public.post(
                        "/grok-memory/mcp",
                        headers={
                            **MCP_HEADERS,
                            "Authorization": "Bearer " + RECALL_KEY,
                        },
                        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    )
                ).status_code,
                401,
            )
            # Valid bearer token -> recall works.
            res = await public.post(
                "/grok-memory/mcp",
                headers={**MCP_HEADERS, "Authorization": "Bearer " + BEARER_TOKEN},
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "recall", "arguments": {"query": "Anki"}},
                },
            )
            self.assertEqual(res.status_code, 200)
            self.assertFalse(res.json()["result"].get("isError", False))


def render_chart(*extra_args):
    cmd = [
        "helm",
        "template",
        "hindsight",
        str(CHART),
        "-n",
        "hindsight",
        "--skip-tests",
        "--kube-version",
        "1.36.1",
        "-f",
        str(CHART / "kkamji_local_values.yaml"),
        *extra_args,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise AssertionError(res.stderr or res.stdout)
    return [doc for doc in yaml.safe_load_all(res.stdout) if isinstance(doc, dict)]


class BidirectionalAndGrokChartTests(unittest.TestCase):
    IMG = "ghcr.io/kkamji98/hindsight-dot@sha256:" + "a" * 64

    def test_moka_retain_enabled_wires_separate_key_without_native_keys(self):
        docs = render_chart(
            "-f",
            str(CHART / "moka_private_values.yaml"),
            "--set",
            "mokaRecallOAuth.service.retainEnabled=true",
        )
        by_key = {(d["kind"], d["metadata"]["name"]): d for d in docs}
        api_env = {
            e["name"]: e
            for e in by_key["StatefulSet", "hindsight-api"]["spec"]["template"]["spec"][
                "containers"
            ][0]["env"]
        }
        self.assertEqual(
            api_env["HINDSIGHT_API_HTTP_MOKA_RETAIN_KEY"]["valueFrom"]["secretKeyRef"],
            {"name": "hindsight-moka-recall-oauth-api-key", "key": "retain_api_key"},
        )
        moka_env = {
            e["name"]: e.get("value")
            for e in by_key["Deployment", "hindsight-moka-recall-oauth"]["spec"][
                "template"
            ]["spec"]["containers"][0]["env"]
        }
        self.assertEqual(moka_env["MOKA_RETAIN_ENABLED"], "true")
        es_keys = {
            item["secretKey"]
            for item in by_key["ExternalSecret", "hindsight-moka-recall-oauth"]["spec"][
                "data"
            ]
        }
        self.assertIn("retain_api_key", es_keys)
        self.assertNotIn("api_key", es_keys)

    def test_grok_memory_oauth_and_bearer_templates_and_guards(self):
        docs = render_chart(
            "--set",
            "grokMemory.enabled=true",
            "--set",
            "grokMemory.publicEnabled=true",
            "--set",
            "grokMemory.retainEnabled=true",
            "--set",
            f"grokMemory.image={self.IMG}",
        )
        by_key = {(d["kind"], d["metadata"]["name"]): d for d in docs}
        self.assertIn(("Deployment", "hindsight-grok-memory"), by_key)
        self.assertIn(("HTTPRoute", "hindsight-grok-memory"), by_key)
        self.assertIn(("BackendTrafficPolicy", "hindsight-grok-memory-limits"), by_key)
        self.assertIn(("PersistentVolumeClaim", "hindsight-grok-memory-grants"), by_key)
        # Cilium egress must NOT include OpenAI API.
        grok_cnp = by_key["CiliumNetworkPolicy", "hindsight-grok-memory"]["spec"]
        fqdns = {
            f["matchName"] for r in grok_cnp["egress"] for f in r.get("toFQDNs", [])
        }
        self.assertEqual(fqdns, {"oauth2.googleapis.com", "www.googleapis.com"})
        # API CNP must allow ingress from hindsight-grok-memory on 8888.
        api_in = by_key["CiliumNetworkPolicy", "hindsight-api"]["spec"]["ingress"]
        self.assertTrue(
            any(
                ep.get("matchLabels", {}).get("app.kubernetes.io/name")
                == "hindsight-grok-memory"
                for r in api_in
                for ep in r.get("fromEndpoints", [])
            )
        )
        # Bearer mode omits PVC and OAuth routes.
        bearer_docs = render_chart(
            "--set",
            "grokMemory.enabled=true",
            "--set",
            "grokMemory.publicEnabled=true",
            "--set",
            "grokMemory.authMode=bearer",
            "--set",
            f"grokMemory.image={self.IMG}",
        )
        b_key = {(d["kind"], d["metadata"]["name"]): d for d in bearer_docs}
        self.assertNotIn(
            ("PersistentVolumeClaim", "hindsight-grok-memory-grants"), b_key
        )
        route_matches = {
            m["path"]["value"]
            for m in b_key["HTTPRoute", "hindsight-grok-memory"]["spec"]["rules"][0][
                "matches"
            ]
        }
        self.assertEqual(route_matches, {"/grok-memory/mcp"})

        # Validation guards reject bad configs.
        for bad_args, expected in (
            (
                ("--set", "grokMemory.publicEnabled=true"),
                "requires grokMemory.enabled=true",
            ),
            (
                (
                    "--set",
                    "grokMemory.enabled=true",
                    "--set",
                    "grokMemory.image=latest",
                ),
                "pinned FastMCP runtime image",
            ),
            (
                (
                    "--set",
                    "grokMemory.enabled=true",
                    "--set",
                    f"grokMemory.image={self.IMG}",
                    "--set",
                    "grokMemory.authMode=invalid",
                ),
                "must be oauth or bearer",
            ),
        ):
            with self.subTest(expected=expected):
                with self.assertRaises(AssertionError) as ctx:
                    render_chart(*bad_args)
                self.assertIn(expected, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
