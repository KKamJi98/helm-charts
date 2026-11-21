"""Owner-bound OAuth for Moka.

Without a ServiceConfig this is the synthetic canary: memory-only state, short
tokens, no refresh and a tool that never reads Hindsight. With a ServiceConfig
it keeps encrypted grants on disk, allows Google-backed refresh and exposes one
read-only recall tool backed by the Hindsight recall-only extension.
"""

import asyncio
import base64
from dataclasses import dataclass, field
from pathlib import Path
import re
import secrets
import time
from typing import Annotated

from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.google import GoogleProvider
import httpx2
from key_value.aio.stores.filetree import FileTreeStore
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from mcp.server.auth.provider import AuthorizeError, RegistrationError, TokenError
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.responses import Response

from moka_oauth_boundary import HEADERS, OAuthBoundary, PREFIX, RESOURCE_METADATA

ORIGIN = 'https://hindsight.kkamji.net'
CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
GOOGLE_SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email']
RECALL_URL = 'http://hindsight-api.hindsight.svc.cluster.local:8888/ext/moka-recall/recall'
RECALL_BANK = 'personal_shared'
MAX_QUERY = 1000
MAX_RESULTS = 50


@dataclass(frozen=True)
class CanaryConfig:
    client_id: str
    client_secret: str = field(repr=False)
    owner_sub: str = field(repr=False)
    owner_email: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if not re.fullmatch(r'[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com', self.client_id):
            raise ValueError('Expected one Google web client ID')
        if not self.client_secret or not re.fullmatch(r'[0-9]{6,32}', self.owner_sub):
            raise ValueError('Verified Google owner subject and client credential required')
        if self.owner_email is not None and not re.fullmatch(r'[^\s@]+@[^\s@]+', self.owner_email):
            raise ValueError('Expected one Google owner email address')


@dataclass(frozen=True)
class ServiceConfig:
    recall_key: str = field(repr=False)
    jwt_signing_key: bytes = field(repr=False)
    storage_key: str = field(repr=False)
    state_dir: Path

    def __post_init__(self):
        if len(self.recall_key) < 32 or self.recall_key != self.recall_key.strip():
            raise ValueError('Dedicated recall key required')
        if len(self.jwt_signing_key) < 32:
            raise ValueError('Persistent 32-byte JWT signing key required')
        Fernet(self.storage_key)
        if not self.state_dir.is_absolute():
            raise ValueError('Absolute grant state directory required')

    @classmethod
    def from_secret_files(cls, root, state_dir):
        read = lambda name: (root / name).read_text().strip()
        return cls(recall_key=read('recall_api_key'),
                   jwt_signing_key=base64.b64decode(read('jwt_signing_key'), validate=True),
                   storage_key=read('storage_encryption_key'), state_dir=Path(state_dir))


class OwnerCanaryProvider(GoogleProvider):
    def __init__(self, config, *, google=None, service=None):
        self.owner = config
        self.service = service
        self.registration_times = []
        self.exchange_lock = asyncio.Lock()
        if service is None:
            durable = dict(
                extra_authorize_params={'access_type': 'online', 'prompt': 'select_account'},
                fastmcp_access_token_expiry_seconds=120,
                client_storage=MemoryStore(max_entries_per_collection=128),
                jwt_signing_key=secrets.token_bytes(32),
            )
        else:
            durable = dict(
                extra_authorize_params={'access_type': 'offline', 'prompt': 'consent select_account'},
                fastmcp_access_token_expiry_seconds=3600,
                client_storage=FernetEncryptionWrapper(
                    FileTreeStore(data_directory=service.state_dir), fernet=Fernet(service.storage_key)),
                jwt_signing_key=service.jwt_signing_key,
            )
        super().__init__(
            client_id=config.client_id, client_secret=config.client_secret,
            base_url=ORIGIN + PREFIX, redirect_path='/google/callback',
            allowed_client_redirect_uris=[CALLBACK], enable_cimd=False,
            required_scopes=GOOGLE_SCOPES, valid_scopes=GOOGLE_SCOPES,
            http_client=google, timeout_seconds=5, forward_resource=False,
            **durable,
        )

    def is_owner(self, identity):
        if identity is None or (identity.expires_at or 0) <= time.time():
            return False
        claims = identity.claims or {}
        return (identity.subject == claims.get('sub') == self.owner.owner_sub
                and claims.get('aud') == self.owner.client_id
                and isinstance(claims.get('email'), str) and bool(claims.get('email'))
                and (self.owner.owner_email is None or claims['email'] == self.owner.owner_email)
                and (claims.get('email_verified') is True or claims.get('email_verified') == 'true')
                and set(GOOGLE_SCOPES) <= set(identity.scopes))

    async def register_client(self, client_info):
        if [str(uri) for uri in (client_info.redirect_uris or [])] != [CALLBACK]:
            raise RegistrationError('invalid_redirect_uri', 'Exact ChatGPT callback required')
        if client_info.token_endpoint_auth_method != 'none':
            raise RegistrationError('invalid_client_metadata', 'Public PKCE clients only')
        now = time.monotonic()
        self.registration_times = [value for value in self.registration_times if now - value < 900]
        if len(self.registration_times) >= 12:
            raise RegistrationError('invalid_client_metadata', 'Canary registration limit reached')
        self.registration_times.append(now)
        await super().register_client(client_info)

    async def authorize(self, client, params):
        if str(params.redirect_uri) != CALLBACK or [str(uri) for uri in (client.redirect_uris or [])] != [CALLBACK]:
            raise AuthorizeError('invalid_request', 'Exact ChatGPT callback required')
        return await super().authorize(client, params)

    async def exchange_authorization_code(self, client, authorization_code):
        async with self.exchange_lock:
            code = await self._code_store.get(key=authorization_code.code)
            if (code is None or code.client_id != client.client_id or code.redirect_uri != CALLBACK
                    or code.expires_at <= time.time()):
                raise TokenError('invalid_grant', 'Invalid canary authorization')
            raw = code.idp_tokens.get('access_token')
            try:
                identity = await self._token_validator.verify_token(raw) if isinstance(raw, str) and raw else None
            except Exception:
                identity = None
            if not self.is_owner(identity):
                await self._code_store.delete(key=authorization_code.code)
                raise TokenError('invalid_grant', 'Invalid canary authorization')
            if self.service is None:
                tokens = {k: v for k, v in code.idp_tokens.items() if k not in {'refresh_token', 'refresh_expires_in'}}
                await self._code_store.put(key=authorization_code.code, value=code.model_copy(update={'idp_tokens': tokens}), ttl=max(1, int(code.expires_at - time.time())))
            return await super().exchange_authorization_code(client, authorization_code)

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if self.service is None:
            raise TokenError('invalid_grant', 'Canary does not grant refresh tokens')
        return await super().exchange_refresh_token(client, refresh_token, scopes)

    async def load_access_token(self, token):
        identity = await super().load_access_token(token)
        return identity if self.is_owner(identity) else None


class HindsightRecall:
    """Calls only the recall-only extension; the bank is fixed server-side."""

    def __init__(self, key, *, client=None):
        self._headers = {'Authorization': 'Bearer ' + key}
        self._client = client

    async def __call__(self, query):
        client = self._client or httpx2.AsyncClient(trust_env=False, follow_redirects=False)
        try:
            res = await client.post(RECALL_URL, json={'query': query}, headers=self._headers, timeout=60)
        except httpx2.HTTPError:
            raise ToolError('Hindsight recall is unavailable') from None
        finally:
            if self._client is None:
                await client.aclose()
        if res.status_code != 200:
            raise ToolError('Hindsight recall failed')
        data = res.json()
        if not isinstance(data, dict) or data.get('bank') != RECALL_BANK or not isinstance(data.get('results'), list):
            raise ToolError('Unexpected Hindsight recall response')
        fields = ('text', 'type', 'mentioned_at', 'occurred_start', 'occurred_end')
        return {'bank': RECALL_BANK, 'results': [
            {k: item.get(k) for k in fields} for item in data['results'][:MAX_RESULTS] if isinstance(item, dict)
        ]}


class MokaCanary:
    def __init__(self, config, *, google=None, service=None, hindsight=None):
        self.provider = OwnerCanaryProvider(config, google=google, service=service)
        if service is None:
            self.tool_names = ('connection_check',)
            mcp = FastMCP('Hindsight Moka OAuth check', auth=self.provider)

            @mcp.tool
            def connection_check() -> dict[str, bool]:
                """Confirm the owner OAuth connection without reading Hindsight."""
                return {'owner_authenticated': True, 'synthetic_only': True}
        else:
            self.tool_names = ('recall',)
            backend = HindsightRecall(service.recall_key, client=hindsight)
            mcp = FastMCP('Hindsight Recall', auth=self.provider, instructions=(
                "Read-only search over the owner's shared Hindsight memories (bank personal_shared). "
                'It cannot store, edit or delete memories, or read any other bank.'))

            @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                                  idempotentHint=True, openWorldHint=False))
            async def recall(query: Annotated[str, Field(min_length=1, max_length=MAX_QUERY)]) -> dict:
                """Search the owner's shared Hindsight memories (personal_shared) and return matching facts."""
                return await backend(query)

        self.app = mcp.http_app(stateless_http=True, json_response=True)
        self.public = OAuthBoundary(self.app)

    async def private(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        if scope['type'] != 'http':
            raise ValueError('Unsupported ASGI scope')
        path = scope['path']
        if path == '/.well-known/oauth-protected-resource/mcp' and scope.get('raw_path') == path.encode('ascii'):
            if scope['method'] in {'GET', 'HEAD', 'OPTIONS'}:
                return await self.app({**scope, 'path': RESOURCE_METADATA, 'raw_path': RESOURCE_METADATA.encode('ascii')}, receive, send)
        if path == '/mcp' and scope.get('raw_path') == b'/mcp':
            return await self.app(scope, receive, send)
        return await Response(status_code=404, headers=HEADERS)(scope, receive, send)
