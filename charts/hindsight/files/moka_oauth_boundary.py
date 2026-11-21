"""Public OAuth boundary for the existing Hindsight host, not an MCP listener."""

import asyncio
from types import MappingProxyType

from starlette.responses import Response

PREFIX = '/moka-recall'
AS_METADATA = '/.well-known/oauth-authorization-server'
RESOURCE_METADATA = '/.well-known/oauth-protected-resource/moka-recall/mcp'
PUBLIC_PATHS = MappingProxyType({
    AS_METADATA + PREFIX: (frozenset({'GET', 'HEAD', 'OPTIONS'}), AS_METADATA),
    RESOURCE_METADATA: (frozenset({'GET', 'HEAD', 'OPTIONS'}), RESOURCE_METADATA),
    PREFIX + '/authorize': (frozenset({'GET', 'POST'}), '/authorize'),
    PREFIX + '/token': (frozenset({'POST', 'OPTIONS'}), '/token'),
    PREFIX + '/register': (frozenset({'POST', 'OPTIONS'}), '/register'),
    PREFIX + '/consent': (frozenset({'GET', 'POST'}), '/consent'),
    PREFIX + '/google/callback': (frozenset({'GET'}), '/google/callback'),
})
HEADERS = {'cache-control': 'no-store', 'referrer-policy': 'no-referrer', 'x-content-type-options': 'nosniff'}
MAX_BODY = 16384


class InputRejected(Exception):
    def __init__(self, status):
        self.status = status


async def bounded_body(receive):
    data = bytearray()
    while True:
        item = await receive()
        if item['type'] != 'http.request':
            raise InputRejected(400)
        chunk = item.get('body', b'')
        if len(data) + len(chunk) > MAX_BODY:
            raise InputRejected(413)
        data.extend(chunk)
        if not item.get('more_body'):
            return bytes(data)


class OAuthBoundary:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            return await self.app(scope, receive, send)
        if scope['type'] == 'websocket':
            return await send({'type': 'websocket.close', 'code': 1008})
        if scope['type'] != 'http':
            raise ValueError('Unsupported ASGI scope')
        path = scope['path']
        rule = PUBLIC_PATHS.get(path)
        if rule is None or scope['method'] not in rule[0] or scope.get('raw_path') != path.encode('ascii'):
            return await Response(status_code=404, headers=HEADERS)(scope, receive, send)
        if len(scope.get('query_string', b'')) > MAX_BODY:
            return await Response(status_code=414, headers=HEADERS)(scope, receive, send)
        try:
            body = await asyncio.wait_for(bounded_body(receive), timeout=2)
        except (InputRejected, TimeoutError) as exc:
            return await Response(status_code=getattr(exc, 'status', 408), headers=HEADERS)(scope, receive, send)
        if scope['method'] != 'POST' and body:
            return await Response(status_code=400, headers=HEADERS)(scope, receive, send)
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {'type': 'http.request', 'body': body, 'more_body': False}

        async def secure_response(message):
            if message['type'] == 'http.response.start':
                headers = [(k, v) for k, v in message.get('headers', []) if k.lower().decode('ascii') not in HEADERS]
                headers.extend((k.encode('ascii'), v.encode('ascii')) for k, v in HEADERS.items())
                message = {**message, 'headers': headers}
            await send(message)

        target = rule[1]
        await self.app({**scope, 'path': target, 'raw_path': target.encode('ascii')}, replay, secure_response)
