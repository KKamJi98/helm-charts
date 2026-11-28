"""Single-process runner with listener isolation.

private-metadata and attended-window are the synthetic canary modes. service is
the durable Moka (ChatGPT Dots) connection: public OAuth on 8000, MCP only on
IPv4 loopback 8001 for the tunnel-client sidecar. grok-service is the isolated
public HTTPS MCP service for Grok Bot on port 8000 (Google OAuth DCR or bearer).
"""

import json
import logging
import os
import socket
import time
from pathlib import Path

import uvicorn
from moka_oauth_boundary import AS_METADATA, HEADERS, PREFIX, RESOURCE_METADATA
from moka_oauth_canary import CanaryConfig, MokaCanary, ServiceConfig
from starlette.responses import Response

PUBLIC_PORT = 8000
PRIVATE_PORT = 8001
STATE_DIR = "/var/lib/moka-oauth/grants"
GROK_STATE_DIR = "/var/lib/grok-memory/grants"
GROK_PREFIX = "/grok-memory"


class Window:
    def __init__(
        self,
        canary,
        deadline,
        *,
        wall=time.time,
        monotonic=time.monotonic,
        service=False,
        public_only=False,
    ):
        remaining = None if deadline is None else deadline - wall()
        if service and deadline is not None:
            raise ValueError("Service mode has no canary deadline")
        if remaining is not None and not 0 < remaining <= 600:
            raise ValueError("Canary deadline must be within ten minutes")
        self.service = service
        self.public_only = public_only
        self.canary = canary
        self.wall = wall
        self.monotonic = monotonic
        self.deadline = deadline
        self.stop_at = None if remaining is None else monotonic() + remaining

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            return (
                await self.canary.public(scope, receive, send)
                if self.public_only
                else await self.canary.private(scope, receive, send)
            )
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})
        if scope["type"] != "http":
            raise ValueError("Unsupported ASGI scope")
        address, port = scope.get("server") or (None, None)
        path = scope["path"]
        if self.service:
            if port == PUBLIC_PORT:
                return await self.canary.public(scope, receive, send)
            if not self.public_only and port == PRIVATE_PORT and address == "127.0.0.1":
                return await self.canary.private(scope, receive, send)
        elif self.deadline is None:
            if scope["method"] in {"GET", "HEAD"}:
                if port == PUBLIC_PORT and path in {
                    AS_METADATA + PREFIX,
                    RESOURCE_METADATA,
                }:
                    return await self.canary.public(scope, receive, send)
                if (
                    port == PRIVATE_PORT
                    and address == "127.0.0.1"
                    and path == "/.well-known/oauth-protected-resource/mcp"
                ):
                    return await self.canary.private(scope, receive, send)
        elif (
            self.stop_at is not None
            and self.wall() < self.deadline
            and self.monotonic() < self.stop_at
        ):
            if port == PUBLIC_PORT:
                return await self.canary.public(scope, receive, send)
            if port == PRIVATE_PORT and address == "127.0.0.1":
                return await self.canary.private(scope, receive, send)
        return await Response(status_code=404, headers=HEADERS)(scope, receive, send)


def _env_bool(name):
    return os.environ.get(name, "").strip().lower() == "true"


def main():
    mode = os.environ["MOKA_CANARY_MODE"]
    value = os.environ.get("MOKA_CANARY_DEADLINE_UNIX", "")
    for name in ("fastmcp", "mcp", "httpx", "httpx2", "httpcore", "authlib"):
        logging.getLogger(name).setLevel(logging.CRITICAL)

    if mode == "grok-service":
        if value:
            raise ValueError("Grok service mode has no canary deadline")
        root = Path("/run/grok-memory")
        auth_mode = os.environ.get("GROK_AUTH_MODE", "oauth").strip().lower()
        if auth_mode not in {"oauth", "bearer"}:
            raise ValueError("Unsupported GROK_AUTH_MODE")
        retain_enabled = _env_bool("GROK_RETAIN_ENABLED")
        if auth_mode == "oauth":
            config = CanaryConfig(
                **{
                    k: (root / k).read_text().strip()
                    for k in ("client_id", "client_secret", "owner_sub")
                }
            )
            raw_uris = json.loads(os.environ.get("GROK_ALLOWED_REDIRECT_URIS", "[]"))
            if not isinstance(raw_uris, list) or not raw_uris:
                raise ValueError(
                    "GROK_ALLOWED_REDIRECT_URIS must be a non-empty JSON list"
                )
            Path(GROK_STATE_DIR).mkdir(mode=0o700, exist_ok=True)
            service = ServiceConfig.from_secret_files(
                root,
                GROK_STATE_DIR,
                retain_enabled=retain_enabled,
                retain_source="grok_bot",
                prefix=GROK_PREFIX,
                allowed_callbacks=tuple(raw_uris),
                allow_public_mcp=True,
                bearer_mode=False,
            )
        else:
            config = None
            service = ServiceConfig.from_secret_files(
                root,
                GROK_STATE_DIR,
                retain_enabled=retain_enabled,
                retain_source="grok_bot",
                prefix=GROK_PREFIX,
                allow_public_mcp=True,
                bearer_mode=True,
            )
        app = Window(
            MokaCanary(config, service=service), None, service=True, public_only=True
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                access_log=False,
                proxy_headers=False,
                server_header=False,
                interface="asgi3",
                timeout_graceful_shutdown=3,
                limit_concurrency=24,
            )
        )
        with socket.create_server(("0.0.0.0", PUBLIC_PORT)) as public:
            server.run(sockets=[public])
        return

    root = Path("/run/moka-oauth")
    config = CanaryConfig(
        **{
            k: (root / k).read_text().strip()
            for k in ("client_id", "client_secret", "owner_sub")
        }
    )
    if mode not in {"private-metadata", "attended-window", "service"} or bool(
        value
    ) != (mode == "attended-window"):
        raise ValueError("Canary mode and deadline disagree")
    deadline = int(value) if value else None
    service = None
    if mode == "service":
        Path(STATE_DIR).mkdir(mode=0o700, exist_ok=True)
        service = ServiceConfig.from_secret_files(
            root,
            STATE_DIR,
            retain_enabled=_env_bool("MOKA_RETAIN_ENABLED"),
            retain_source="chatgpt_dot",
        )
    app = Window(
        MokaCanary(config, service=service), deadline, service=service is not None
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            access_log=False,
            proxy_headers=False,
            server_header=False,
            interface="asgi3",
            timeout_graceful_shutdown=3,
            limit_concurrency=24,
        )
    )
    with (
        socket.create_server(("0.0.0.0", PUBLIC_PORT)) as public,
        socket.create_server(("127.0.0.1", PRIVATE_PORT)) as private,
    ):
        server.run(sockets=[public, private])


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError):
        raise SystemExit(
            "Moka OAuth refused to start: invalid secret, listener, mode or deadline"
        ) from None
