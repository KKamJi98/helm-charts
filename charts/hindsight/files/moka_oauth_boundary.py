"""Public OAuth / MCP HTTP boundary for the existing Hindsight host."""

import asyncio
import hmac
from types import MappingProxyType

from starlette.responses import Response

PREFIX = "/moka-recall"
AS_METADATA = "/.well-known/oauth-authorization-server"
RESOURCE_METADATA = "/.well-known/oauth-protected-resource/moka-recall/mcp"
HEADERS = {
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
}
MAX_BODY = 16384
MAX_MCP_BODY = 65536


def build_public_paths(prefix=PREFIX, *, allow_public_mcp=False):
    resource_meta = f"/.well-known/oauth-protected-resource{prefix}/mcp"
    paths = {
        AS_METADATA + prefix: (
            frozenset({"GET", "HEAD", "OPTIONS"}),
            AS_METADATA,
            MAX_BODY,
        ),
        resource_meta: (frozenset({"GET", "HEAD", "OPTIONS"}), resource_meta, MAX_BODY),
        prefix + "/authorize": (frozenset({"GET", "POST"}), "/authorize", MAX_BODY),
        prefix + "/token": (frozenset({"POST", "OPTIONS"}), "/token", MAX_BODY),
        prefix + "/register": (frozenset({"POST", "OPTIONS"}), "/register", MAX_BODY),
        prefix + "/consent": (frozenset({"GET", "POST"}), "/consent", MAX_BODY),
        prefix + "/google/callback": (frozenset({"GET"}), "/google/callback", MAX_BODY),
    }
    if allow_public_mcp:
        paths[prefix + "/mcp"] = (
            frozenset({"GET", "POST", "DELETE", "OPTIONS"}),
            "/mcp",
            MAX_MCP_BODY,
        )
    return MappingProxyType(paths)


PUBLIC_PATHS = MappingProxyType(
    {k: (v[0], v[1]) for k, v in build_public_paths(PREFIX).items()}
)


class InputRejected(Exception):
    def __init__(self, status):
        self.status = status


async def bounded_body(receive, max_body=MAX_BODY):
    data = bytearray()
    while True:
        item = await receive()
        if item["type"] != "http.request":
            raise InputRejected(400)
        chunk = item.get("body", b"")
        if len(data) + len(chunk) > max_body:
            raise InputRejected(413)
        data.extend(chunk)
        if not item.get("more_body"):
            return bytes(data)


async def _dispatch_bounded(app, scope, receive, send, *, target, max_body):
    if len(scope.get("query_string", b"")) > MAX_BODY:
        return await Response(status_code=414, headers=HEADERS)(scope, receive, send)
    try:
        body = await asyncio.wait_for(
            bounded_body(receive, max_body=max_body), timeout=2
        )
    except (InputRejected, TimeoutError) as exc:
        return await Response(status_code=getattr(exc, "status", 408), headers=HEADERS)(
            scope, receive, send
        )
    if scope["method"] not in {"POST", "DELETE"} and body:
        return await Response(status_code=400, headers=HEADERS)(scope, receive, send)
    sent = False

    async def replay():
        nonlocal sent
        if sent:
            return await receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def secure_response(message):
        if message["type"] == "http.response.start":
            headers = [
                (k, v)
                for k, v in message.get("headers", [])
                if k.lower().decode("ascii") not in HEADERS
            ]
            headers.extend(
                (k.encode("ascii"), v.encode("ascii")) for k, v in HEADERS.items()
            )
            message = {**message, "headers": headers}
        await send(message)

    await app(
        {**scope, "path": target, "raw_path": target.encode("ascii")},
        replay,
        secure_response,
    )


class OAuthBoundary:
    def __init__(self, app, *, prefix=PREFIX, allow_public_mcp=False):
        self.app = app
        self.prefix = prefix
        self.allow_public_mcp = allow_public_mcp
        self._paths = build_public_paths(prefix, allow_public_mcp=allow_public_mcp)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            raise ValueError("Unsupported ASGI scope")
        path = scope["path"]
        rule = self._paths.get(path)
        if (
            rule is None
            or scope["method"] not in rule[0]
            or scope.get("raw_path") != path.encode("ascii")
        ):
            return await Response(status_code=404, headers=HEADERS)(
                scope, receive, send
            )
        await _dispatch_bounded(
            self.app, scope, receive, send, target=rule[1], max_body=rule[2]
        )


class BearerMcpBoundary:
    """Scoped public MCP boundary protected by a dedicated per-client Bearer key."""

    def __init__(self, app, *, prefix, bearer_token):
        if (
            not isinstance(bearer_token, str)
            or len(bearer_token) < 32
            or bearer_token != bearer_token.strip()
        ):
            raise ValueError("Dedicated high-entropy MCP bearer token required")
        self.app = app
        self.prefix = prefix
        self._mcp_path = prefix + "/mcp"
        self._token = bearer_token.encode("utf-8")

    def _authorized(self, scope):
        auth_headers = [
            v.decode("latin-1")
            for k, v in scope.get("headers", [])
            if k.lower() == b"authorization"
        ]
        if len(auth_headers) != 1:
            return False
        scheme, _, token = auth_headers[0].partition(" ")
        return scheme == "Bearer" and hmac.compare_digest(
            token.encode("utf-8"), self._token
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            raise ValueError("Unsupported ASGI scope")
        path = scope["path"]
        if path != self._mcp_path or scope.get("raw_path") != self._mcp_path.encode(
            "ascii"
        ):
            return await Response(status_code=404, headers=HEADERS)(
                scope, receive, send
            )
        if scope["method"] not in {"GET", "POST", "DELETE", "OPTIONS"}:
            return await Response(status_code=405, headers=HEADERS)(
                scope, receive, send
            )
        if scope["method"] != "OPTIONS" and not self._authorized(scope):
            unauth_headers = {
                **HEADERS,
                "www-authenticate": 'Bearer realm="hindsight-grok-memory"',
            }
            return await Response(status_code=401, headers=unauth_headers)(
                scope, receive, send
            )
        await _dispatch_bounded(
            self.app, scope, receive, send, target="/mcp", max_body=MAX_MCP_BODY
        )
