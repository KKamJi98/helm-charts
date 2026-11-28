"""Owner-bound OAuth and scoped MCP service for ChatGPT Dots (Moka) and Grok Bot.

Without a ServiceConfig this is the synthetic canary: memory-only state, short
tokens, no refresh and a tool that never reads Hindsight. With a ServiceConfig
it keeps encrypted grants on disk, allows Google-backed refresh, exposes the
read-only recall tool, and optionally exposes scanner-gated retain_summary.
"""

import asyncio
import base64
import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import httpx2
from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from key_value.aio.wrappers.routing import RoutingWrapper
from mcp.server.auth.provider import AuthorizeError, RegistrationError, TokenError
from mcp.types import ToolAnnotations
from moka_oauth_boundary import (
    HEADERS,
    PREFIX,
    RESOURCE_METADATA,
    BearerMcpBoundary,
    OAuthBoundary,
)
from moka_oauth_scanner import (
    DEFAULT_SCANNER_PATH,
    MAX_SUMMARY_CHARS,
    MIN_SUMMARY_CHARS,
    safe_summary_text,
)
from pydantic import Field
from starlette.responses import Response

ORIGIN = "https://hindsight.kkamji.net"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
# ChatGPT uses the stable callback when the AS supports RFC 9207 issuer
# identification, otherwise a per-connector callback ID URI. Allow exactly these.
CALLBACK_ID = re.compile(r"https://chatgpt\.com/connector/oauth/[A-Za-z0-9_-]{1,128}")
STABLE_ID = re.compile(r"^[A-Za-z0-9_:-]{1,160}$")
ALLOWED_RETAIN_SOURCES = frozenset({"chatgpt_dot", "grok_bot"})
ALLOWED_PREFIXES = frozenset({"/moka-recall", "/grok-memory"})


def _valid_https_callback(uri):
    if not isinstance(uri, str) or uri != uri.strip() or len(uri) > 512:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in uri):
        return False
    parsed = urlsplit(uri)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
    )


def allowed_callback(uri, *, custom_callbacks=()):
    if custom_callbacks:
        return uri in custom_callbacks
    return uri == CALLBACK or CALLBACK_ID.fullmatch(uri) is not None


def registered_callbacks(client, *, custom_callbacks=()):
    uris = [str(uri) for uri in (client.redirect_uris or [])]
    return (
        uris
        if uris
        and len(uris) <= 4
        and all(allowed_callback(u, custom_callbacks=custom_callbacks) for u in uris)
        else []
    )


GOOGLE_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
RECALL_URL = (
    "http://hindsight-api.hindsight.svc.cluster.local:8888/ext/moka-recall/recall"
)
RETAIN_URL = (
    "http://hindsight-api.hindsight.svc.cluster.local:8888/ext/moka-recall/retain"
)
RECALL_BANK = "personal_shared"
MAX_QUERY = 1000
MAX_RESULTS = 50
# Only state created after the owner check (plus DCR clients, bounded below) is
# durable. Unauthenticated, short-lived OAuth state stays in a capped memory store.
CLIENTS = "mcp-oauth-proxy-clients"
GRANT_COLLECTIONS = frozenset(
    {
        "mcp-upstream-tokens",
        "mcp-jti-mappings",
        "mcp-refresh-tokens",
        "moka-owner-clients",
    }
)
MAX_STORED_CLIENTS = 128
MAX_OWNER_CLIENTS = 8
PENDING_CLIENT_SECONDS = 3600


def _tree(directory):
    directory.mkdir(mode=0o700, exist_ok=True)
    return FileTreeStore(
        data_directory=directory,
        key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(directory),
        collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(
            directory
        ),
    )


class DurableState:
    """Encrypted disk for DCR clients and owner grants; capped memory for the rest."""

    def __init__(self, service):
        fernet = Fernet(service.storage_key)
        self.clients_dir = service.state_dir / "clients"
        self.clients_tree = _tree(self.clients_dir)
        self.grants_tree = _tree(service.state_dir / "grants")
        self._client_names = FileTreeV1KeySanitizationStrategy(self.clients_dir)
        self._client_files = (
            self.clients_dir
            / FileTreeV1CollectionSanitizationStrategy(self.clients_dir).sanitize(
                CLIENTS
            )
        )
        clients = FernetEncryptionWrapper(self.clients_tree, fernet=fernet)
        grants = FernetEncryptionWrapper(self.grants_tree, fernet=fernet)
        routes = {CLIENTS: clients, **{name: grants for name in GRANT_COLLECTIONS}}
        self.store = RoutingWrapper(
            routing_function=routes.get,
            default_store=MemoryStore(max_entries_per_collection=128),
        )

    async def owner_clients(self):
        entry = await self.store.get(key="owner", collection="moka-owner-clients")
        return list(entry["ids"]) if entry else []

    async def remember_owner_client(self, client_id):
        ids = [i for i in await self.owner_clients() if i != client_id] + [client_id]
        await self.store.put(
            key="owner",
            collection="moka-owner-clients",
            value={"ids": ids[-MAX_OWNER_CLIENTS:]},
        )

    def stored_clients(self):
        return (
            list(self._client_files.glob("*.json"))
            if self._client_files.is_dir()
            else []
        )

    async def make_room(self):
        """Cull expired grants; at the client cap, drop clients that never passed the owner check."""
        await self.clients_tree.cull()
        await self.grants_tree.cull()
        if len(self.stored_clients()) < MAX_STORED_CLIENTS:
            return True
        keep = {
            self._client_names.sanitize(i) + ".json" for i in await self.owner_clients()
        }
        cutoff = time.time() - PENDING_CLIENT_SECONDS
        stale = sorted(
            (p.stat().st_mtime, p)
            for p in self.stored_clients()
            if p.name not in keep and p.stat().st_mtime < cutoff
        )
        excess = len(self.stored_clients()) - MAX_STORED_CLIENTS + 1
        for _, path in stale[: max(0, excess)]:
            path.unlink(missing_ok=True)
        return len(self.stored_clients()) < MAX_STORED_CLIENTS


@dataclass(frozen=True)
class CanaryConfig:
    client_id: str
    client_secret: str = field(repr=False)
    owner_sub: str = field(repr=False)
    owner_email: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if not re.fullmatch(
            r"[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com", self.client_id
        ):
            raise ValueError("Expected one Google web client ID")
        if not self.client_secret or not re.fullmatch(r"[0-9]{6,32}", self.owner_sub):
            raise ValueError(
                "Verified Google owner subject and client credential required"
            )
        if self.owner_email is not None and not re.fullmatch(
            r"[^\s@]+@[^\s@]+", self.owner_email
        ):
            raise ValueError("Expected one Google owner email address")


@dataclass(frozen=True)
class ServiceConfig:
    recall_key: str = field(repr=False)
    jwt_signing_key: bytes = field(repr=False)
    storage_key: str = field(repr=False)
    state_dir: Path
    retain_key: str | None = field(default=None, repr=False)
    retain_source: str = "chatgpt_dot"
    scanner_path: str = DEFAULT_SCANNER_PATH
    scanner_config: str | None = None
    prefix: str = PREFIX
    allowed_callbacks: tuple[str, ...] = ()
    allow_public_mcp: bool = False
    bearer_token: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if len(self.recall_key) < 32 or self.recall_key != self.recall_key.strip():
            raise ValueError("Dedicated recall key required")
        if self.bearer_token is None:
            if len(self.jwt_signing_key) < 32:
                raise ValueError("Persistent 32-byte JWT signing key required")
            Fernet(self.storage_key)
            if not self.state_dir.is_absolute():
                raise ValueError("Absolute grant state directory required")
        else:
            if (
                len(self.bearer_token) < 32
                or self.bearer_token != self.bearer_token.strip()
            ):
                raise ValueError("Dedicated MCP bearer token required")
            if hmac.compare_digest(self.bearer_token, self.recall_key):
                raise ValueError("MCP bearer token must be distinct from recall key")
        if self.retain_key is not None:
            if len(self.retain_key) < 32 or self.retain_key != self.retain_key.strip():
                raise ValueError("Dedicated retain key required")
            if hmac.compare_digest(self.retain_key, self.recall_key):
                raise ValueError("Retain key must be distinct from recall key")
            if self.bearer_token is not None and hmac.compare_digest(
                self.retain_key, self.bearer_token
            ):
                raise ValueError("Retain key must be distinct from bearer token")
        if self.retain_source not in ALLOWED_RETAIN_SOURCES:
            raise ValueError("Unsupported retain source")
        if self.prefix not in ALLOWED_PREFIXES:
            raise ValueError("Unsupported service path prefix")
        if self.prefix == PREFIX and self.allow_public_mcp:
            raise ValueError("Moka OAuth service must never expose public MCP")
        if (
            any(not _valid_https_callback(u) for u in self.allowed_callbacks)
            or len(self.allowed_callbacks) > 4
        ):
            raise ValueError("Expected 1..4 canonical HTTPS callback URIs")

    @classmethod
    def from_secret_files(
        cls,
        root,
        state_dir,
        *,
        retain_enabled=False,
        retain_source="chatgpt_dot",
        scanner_path=DEFAULT_SCANNER_PATH,
        prefix=PREFIX,
        allowed_callbacks=(),
        allow_public_mcp=False,
        bearer_mode=False,
    ):
        read = lambda name: (root / name).read_text().strip()
        retain_key = read("retain_api_key") if retain_enabled else None
        if bearer_mode:
            return cls(
                recall_key=read("recall_api_key"),
                jwt_signing_key=b"",
                storage_key="",
                state_dir=Path(state_dir),
                retain_key=retain_key,
                retain_source=retain_source,
                scanner_path=scanner_path,
                prefix=prefix,
                allowed_callbacks=tuple(allowed_callbacks),
                allow_public_mcp=allow_public_mcp,
                bearer_token=read("mcp_bearer_token"),
            )
        return cls(
            recall_key=read("recall_api_key"),
            jwt_signing_key=base64.b64decode(read("jwt_signing_key"), validate=True),
            storage_key=read("storage_encryption_key"),
            state_dir=Path(state_dir),
            retain_key=retain_key,
            retain_source=retain_source,
            scanner_path=scanner_path,
            prefix=prefix,
            allowed_callbacks=tuple(allowed_callbacks),
            allow_public_mcp=allow_public_mcp,
        )


class OwnerCanaryProvider(GoogleProvider):
    def __init__(self, config, *, google=None, service=None):
        self.owner = config
        self.service = service
        self.prefix = PREFIX if service is None else service.prefix
        self.custom_callbacks = () if service is None else service.allowed_callbacks
        self.state = None if service is None else DurableState(service)
        self.registration_times = []
        self.registration_lock = asyncio.Lock()
        self.exchange_lock = asyncio.Lock()
        if service is None:
            durable = dict(
                extra_authorize_params={
                    "access_type": "online",
                    "prompt": "select_account",
                },
                fastmcp_access_token_expiry_seconds=120,
                client_storage=MemoryStore(max_entries_per_collection=128),
                jwt_signing_key=secrets.token_bytes(32),
            )
        else:
            durable = dict(
                extra_authorize_params={
                    "access_type": "offline",
                    "prompt": "consent select_account",
                },
                fastmcp_access_token_expiry_seconds=3600,
                client_storage=self.state.store,
                jwt_signing_key=service.jwt_signing_key,
            )
        allowed_uris = (
            list(self.custom_callbacks)
            if self.custom_callbacks
            else [CALLBACK, "https://chatgpt.com/connector/oauth/*"]
        )
        super().__init__(
            client_id=config.client_id,
            client_secret=config.client_secret,
            base_url=ORIGIN + self.prefix,
            redirect_path="/google/callback",
            allowed_client_redirect_uris=allowed_uris,
            enable_cimd=False,
            required_scopes=GOOGLE_SCOPES,
            valid_scopes=GOOGLE_SCOPES,
            http_client=google,
            timeout_seconds=5,
            forward_resource=False,
            **durable,
        )

    def is_owner(self, identity):
        if identity is None or (identity.expires_at or 0) <= time.time():
            return False
        claims = identity.claims or {}
        return (
            identity.subject == claims.get("sub") == self.owner.owner_sub
            and claims.get("aud") == self.owner.client_id
            and isinstance(claims.get("email"), str)
            and bool(claims.get("email"))
            and (
                self.owner.owner_email is None
                or claims["email"] == self.owner.owner_email
            )
            and (
                claims.get("email_verified") is True
                or claims.get("email_verified") == "true"
            )
            and set(GOOGLE_SCOPES) <= set(identity.scopes)
        )

    async def register_client(self, client_info):
        if not registered_callbacks(
            client_info, custom_callbacks=self.custom_callbacks
        ):
            raise RegistrationError(
                "invalid_redirect_uri", "Approved client callback required"
            )
        if client_info.token_endpoint_auth_method != "none":
            raise RegistrationError(
                "invalid_client_metadata", "Public PKCE clients only"
            )
        async with self.registration_lock:
            now = time.monotonic()
            self.registration_times = [
                value for value in self.registration_times if now - value < 900
            ]
            if len(self.registration_times) >= 12:
                raise RegistrationError(
                    "invalid_client_metadata", "Canary registration limit reached"
                )
            if self.state is not None and not await self.state.make_room():
                raise RegistrationError(
                    "invalid_client_metadata", "Client registration capacity reached"
                )
            self.registration_times.append(now)
            await super().register_client(client_info)

    async def authorize(self, client, params):
        if str(params.redirect_uri) not in registered_callbacks(
            client, custom_callbacks=self.custom_callbacks
        ):
            raise AuthorizeError("invalid_request", "Approved client callback required")
        return await super().authorize(client, params)

    async def exchange_authorization_code(self, client, authorization_code):
        async with self.exchange_lock:
            code = await self._code_store.get(key=authorization_code.code)
            if (
                code is None
                or code.client_id != client.client_id
                or str(code.redirect_uri)
                not in registered_callbacks(
                    client, custom_callbacks=self.custom_callbacks
                )
                or code.expires_at <= time.time()
            ):
                raise TokenError("invalid_grant", "Invalid canary authorization")
            raw = code.idp_tokens.get("access_token")
            try:
                identity = (
                    await self._token_validator.verify_token(raw)
                    if isinstance(raw, str) and raw
                    else None
                )
            except Exception:
                identity = None
            if not self.is_owner(identity):
                await self._code_store.delete(key=authorization_code.code)
                raise TokenError("invalid_grant", "Invalid canary authorization")
            if self.service is None:
                tokens = {
                    k: v
                    for k, v in code.idp_tokens.items()
                    if k not in {"refresh_token", "refresh_expires_in"}
                }
                await self._code_store.put(
                    key=authorization_code.code,
                    value=code.model_copy(update={"idp_tokens": tokens}),
                    ttl=max(1, int(code.expires_at - time.time())),
                )
            grant = await super().exchange_authorization_code(
                client, authorization_code
            )
            if self.state is not None:
                await self.state.remember_owner_client(client.client_id)
            return grant

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if self.service is None:
            raise TokenError("invalid_grant", "Canary does not grant refresh tokens")
        return await super().exchange_refresh_token(client, refresh_token, scopes)

    async def load_access_token(self, token):
        identity = await super().load_access_token(token)
        return identity if self.is_owner(identity) else None


class HindsightRecall:
    """Calls only the recall-only extension; the bank is fixed server-side."""

    def __init__(self, key, *, client=None):
        self._headers = {"Authorization": "Bearer " + key}
        self._client = client

    async def __call__(self, query):
        client = self._client or httpx2.AsyncClient(
            trust_env=False, follow_redirects=False
        )
        try:
            res = await client.post(
                RECALL_URL, json={"query": query}, headers=self._headers, timeout=60
            )
        except httpx2.HTTPError:
            raise ToolError("Hindsight recall is unavailable") from None
        finally:
            if self._client is None:
                await client.aclose()
        if res.status_code != 200:
            raise ToolError("Hindsight recall failed")
        data = res.json()
        if (
            not isinstance(data, dict)
            or data.get("bank") != RECALL_BANK
            or not isinstance(data.get("results"), list)
        ):
            raise ToolError("Unexpected Hindsight recall response")
        fields = ("text", "type", "mentioned_at", "occurred_start", "occurred_end")
        return {
            "bank": RECALL_BANK,
            "results": [
                {k: item.get(k) for k in fields}
                for item in data["results"][:MAX_RESULTS]
                if isinstance(item, dict)
            ],
        }


class HindsightRetain:
    """Scanner-gated summary retain client; bank and source are fixed server-side."""

    def __init__(
        self,
        key,
        *,
        source,
        scanner_path=DEFAULT_SCANNER_PATH,
        scanner_config=None,
        client=None,
    ):
        self._headers = {"Authorization": "Bearer " + key}
        self._source = source
        self._scanner_path = scanner_path
        self._scanner_config = scanner_config
        self._client = client

    async def __call__(self, summary, conversation_id, message_id):
        if (
            not isinstance(conversation_id, str)
            or STABLE_ID.fullmatch(conversation_id) is None
        ):
            raise ToolError("Invalid conversation_id")
        if not isinstance(message_id, str) or STABLE_ID.fullmatch(message_id) is None:
            raise ToolError("Invalid message_id")
        if not safe_summary_text(
            summary, scanner_path=self._scanner_path, config_path=self._scanner_config
        ):
            raise ToolError("Summary refused by privacy/secret scanner")
        payload = {
            "summary": summary.strip(),
            "conversation_id": conversation_id,
            "message_id": message_id,
            "source": self._source,
        }
        client = self._client or httpx2.AsyncClient(
            trust_env=False, follow_redirects=False
        )
        try:
            res = await client.post(
                RETAIN_URL, json=payload, headers=self._headers, timeout=20
            )
        except httpx2.HTTPError:
            raise ToolError("Hindsight retain is unavailable") from None
        finally:
            if self._client is None:
                await client.aclose()
        if res.status_code == 422:
            raise ToolError("Summary refused by Hindsight policy gate")
        if res.status_code != 202:
            raise ToolError("Hindsight retain failed")
        data = res.json()
        if (
            not isinstance(data, dict)
            or data.get("bank") != RECALL_BANK
            or data.get("status") != "accepted_not_extracted"
            or not isinstance(data.get("operation_id"), str)
            or not isinstance(data.get("document_id"), str)
        ):
            raise ToolError("Unexpected Hindsight retain response")
        return {
            "bank": RECALL_BANK,
            "status": "accepted_not_extracted",
            "operation_id": data["operation_id"],
            "document_id": data["document_id"],
        }


class MokaCanary:
    def __init__(self, config, *, google=None, service=None, hindsight=None):
        self.service = service
        self.prefix = PREFIX if service is None else service.prefix
        self.bearer_mode = service is not None and service.bearer_token is not None
        self.provider = (
            None
            if self.bearer_mode
            else OwnerCanaryProvider(config, google=google, service=service)
        )
        if service is None:
            self.tool_names = ("connection_check",)
            mcp = FastMCP("Hindsight Moka OAuth check", auth=self.provider)

            @mcp.tool
            def connection_check() -> dict[str, bool]:
                """Confirm the owner OAuth connection without reading Hindsight."""
                return {"owner_authenticated": True, "synthetic_only": True}
        else:
            recall_backend = HindsightRecall(service.recall_key, client=hindsight)
            if service.retain_key is None:
                self.tool_names = ("recall",)
                instructions = (
                    "Read-only search over the owner's shared Hindsight memories (bank personal_shared). "
                    "It cannot store, edit or delete memories, or read any other bank."
                )
            else:
                self.tool_names = ("recall", "retain_summary")
                instructions = (
                    "Shared personal Hindsight memory (bank personal_shared). Use recall to search facts. "
                    "Use retain_summary ONLY for concise, owner-approved personal facts or decisions; "
                    "never submit company work data, secrets, credentials, raw transcripts, or unconfirmed speculation. "
                    "It cannot delete memories or access any other bank."
                )
            server_name = (
                "Hindsight Grok Memory"
                if service.retain_source == "grok_bot"
                else "Hindsight Recall"
            )
            mcp = FastMCP(server_name, auth=self.provider, instructions=instructions)

            @mcp.tool(
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                )
            )
            async def recall(
                query: Annotated[str, Field(min_length=1, max_length=MAX_QUERY)],
            ) -> dict:
                """Search the owner's shared Hindsight memories (personal_shared) and return matching facts."""
                return await recall_backend(query)

            if service.retain_key is not None:
                retain_backend = HindsightRetain(
                    service.retain_key,
                    source=service.retain_source,
                    scanner_path=service.scanner_path,
                    scanner_config=service.scanner_config,
                    client=hindsight,
                )

                @mcp.tool(
                    annotations=ToolAnnotations(
                        readOnlyHint=False,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=False,
                    )
                )
                async def retain_summary(
                    summary: Annotated[
                        str,
                        Field(
                            min_length=MIN_SUMMARY_CHARS, max_length=MAX_SUMMARY_CHARS
                        ),
                    ],
                    conversation_id: Annotated[
                        str, Field(min_length=1, max_length=160)
                    ],
                    message_id: Annotated[str, Field(min_length=1, max_length=160)],
                ) -> dict:
                    """Store one concise, owner-approved personal fact/decision summary into personal_shared."""
                    return await retain_backend(summary, conversation_id, message_id)

        self.app = mcp.http_app(stateless_http=True, json_response=True)
        if self.bearer_mode:
            self.public = BearerMcpBoundary(
                self.app, prefix=self.prefix, bearer_token=service.bearer_token
            )
        else:
            self.public = OAuthBoundary(
                self.app,
                prefix=self.prefix,
                allow_public_mcp=False if service is None else service.allow_public_mcp,
            )

    async def private(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            raise ValueError("Unsupported ASGI scope")
        path = scope["path"]
        if path == "/.well-known/oauth-protected-resource/mcp" and scope.get(
            "raw_path"
        ) == path.encode("ascii"):
            if scope["method"] in {"GET", "HEAD", "OPTIONS"}:
                return await self.app(
                    {
                        **scope,
                        "path": RESOURCE_METADATA,
                        "raw_path": RESOURCE_METADATA.encode("ascii"),
                    },
                    receive,
                    send,
                )
        if path == "/mcp" and scope.get("raw_path") == b"/mcp":
            return await self.app(scope, receive, send)
        return await Response(status_code=404, headers=HEADERS)(scope, receive, send)
