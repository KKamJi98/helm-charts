"""Single-process runner with listener isolation.

private-metadata and attended-window are the synthetic canary modes. service is
the durable owner connection: public OAuth on 8000, MCP only on IPv4 loopback
8001 for the tunnel-client sidecar.
"""

import logging
import os
from pathlib import Path
import socket
import time

import uvicorn
from starlette.responses import Response

from moka_oauth_boundary import AS_METADATA, HEADERS, PREFIX, RESOURCE_METADATA
from moka_oauth_canary import CanaryConfig, MokaCanary, ServiceConfig

PUBLIC_PORT = 8000
PRIVATE_PORT = 8001
STATE_DIR = '/var/lib/moka-oauth/grants'


class Window:
    def __init__(self, canary, deadline, *, wall=time.time, monotonic=time.monotonic, service=False):
        remaining = None if deadline is None else deadline - wall()
        if service and deadline is not None:
            raise ValueError('Service mode has no canary deadline')
        if remaining is not None and not 0 < remaining <= 600:
            raise ValueError('Canary deadline must be within ten minutes')
        self.service = service
        self.canary = canary
        self.wall = wall
        self.monotonic = monotonic
        self.deadline = deadline
        self.stop_at = None if remaining is None else monotonic() + remaining

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.canary.private(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        if scope['type'] != 'http':
            raise ValueError('Unsupported ASGI scope')
        address, port = scope.get('server') or (None, None)
        path = scope['path']
        if self.service:
            if port == PUBLIC_PORT:
                return await self.canary.public(scope, receive, send)
            if port == PRIVATE_PORT and address == '127.0.0.1':
                return await self.canary.private(scope, receive, send)
        elif self.deadline is None:
            if scope['method'] in {'GET', 'HEAD'}:
                if port == PUBLIC_PORT and path in {AS_METADATA + PREFIX, RESOURCE_METADATA}:
                    return await self.canary.public(scope, receive, send)
                if port == PRIVATE_PORT and address == '127.0.0.1' and path == '/.well-known/oauth-protected-resource/mcp':
                    return await self.canary.private(scope, receive, send)
        elif self.stop_at is not None and self.wall() < self.deadline and self.monotonic() < self.stop_at:
            if port == PUBLIC_PORT:
                return await self.canary.public(scope, receive, send)
            if port == PRIVATE_PORT and address == '127.0.0.1':
                return await self.canary.private(scope, receive, send)
        return await Response(status_code=404, headers=HEADERS)(scope, receive, send)


def main():
    root = Path('/run/moka-oauth')
    config = CanaryConfig(**{k: (root / k).read_text().strip() for k in ('client_id', 'client_secret', 'owner_sub')})
    mode = os.environ['MOKA_CANARY_MODE']
    value = os.environ['MOKA_CANARY_DEADLINE_UNIX']
    if mode not in {'private-metadata', 'attended-window', 'service'} or bool(value) != (mode == 'attended-window'):
        raise ValueError('Canary mode and deadline disagree')
    deadline = int(value) if value else None
    service = None
    if mode == 'service':
        Path(STATE_DIR).mkdir(mode=0o700, exist_ok=True)
        service = ServiceConfig.from_secret_files(root, STATE_DIR)
    app = Window(MokaCanary(config, service=service), deadline, service=service is not None)
    for name in ('fastmcp', 'mcp', 'httpx', 'httpx2', 'httpcore', 'authlib'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, proxy_headers=False,
                                           server_header=False, interface='asgi3', timeout_graceful_shutdown=3,
                                           limit_concurrency=24))
    with socket.create_server(('0.0.0.0', PUBLIC_PORT)) as public, socket.create_server(('127.0.0.1', PRIVATE_PORT)) as private:
        server.run(sockets=[public, private])


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError):
        raise SystemExit('Moka OAuth refused to start: invalid secret, listener, mode or deadline') from None
