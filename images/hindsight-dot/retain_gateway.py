"""Unbound retain-only gateway candidate; no network listener or real credentials."""
import json
import re
import uuid
from adapter import safe_text
from starlette.requests import Request
from starlette.responses import JSONResponse

PATH = '/v1/default/banks/personal_shared/memories'

class RetainGateway:
    def __init__(self, verifier, forward, scanner="/opt/homebrew/bin/gitleaks"):
        self.verifier, self.forward = verifier, forward
        self.scanner = scanner

    async def __call__(self, scope, receive, send):
        request = Request(scope, receive)
        auth = request.headers.getlist('authorization')
        token = auth[0][7:] if len(auth) == 1 and auth[0].startswith('Bearer ') else ''
        access = await self.verifier.verify_token(token)
        if access is None:
            return await JSONResponse({'error': 'unauthorized'}, 401)(scope, receive, send)
        if 'hindsight:retain' not in access.scopes:
            return await JSONResponse({'error': 'scope denied'}, 403)(scope, receive, send)
        if (scope['method'] != 'POST' or scope['path'] != PATH or
            scope.get('raw_path', PATH.encode()) != PATH.encode() or scope.get('query_string')):
            return await JSONResponse({'error': 'route denied'}, 403)(scope, receive, send)
        data = b''
        try:
            async for chunk in request.stream():
                data += chunk
                if len(data) > 20000:
                    raise ValueError('size')
            body = json.loads(data)
            if not isinstance(body, dict) or set(body) != {'operation_id', 'items', 'async'} or body['async'] is not True:
                raise ValueError('shape')
            if not isinstance(body['items'], list) or len(body['items']) != 1:
                raise ValueError('items')
            item = body['items'][0]
            if not isinstance(item, dict) or set(item) != {'content', 'document_id', 'metadata'}:
                raise ValueError('item')
            if not isinstance(item['content'], str) or not 6 <= len(item['content'].strip()) <= 4000:
                raise ValueError('content')
            if not safe_text(item['content'], self.scanner):
                raise ValueError('privacy')
            if not isinstance(item['document_id'], str) or not re.fullmatch(r'dot-summary-[0-9a-f]{64}', item['document_id']):
                raise ValueError('id')
            if body['operation_id'] != str(uuid.uuid5(uuid.NAMESPACE_URL, item['document_id'])):
                raise ValueError('id binding')
            if item['metadata'] != {'source': 'dot_user_conversation_summary', 'schema': 'v1'}:
                raise ValueError('metadata')
        except (ValueError, TypeError, KeyError, UnicodeError):
            return await JSONResponse({'error': 'payload denied'}, 400)(scope, receive, send)
        # Recheck authoritative state after parsing/scanning, immediately before dispatch.
        access = await self.verifier.verify_token(token)
        if access is None or 'hindsight:retain' not in access.scopes:
            return await JSONResponse({'error': 'connection disabled'}, 401)(scope, receive, send)
        try:
            result = await self.forward(body)
            response = JSONResponse(result)
        except (OSError, ValueError, TypeError, RuntimeError):
            response = JSONResponse({'error': 'upstream unavailable'}, 502)
        await response(scope, receive, send)
