"""Isolated server-side route policy. Must run outside the MCP adapter trust boundary.

A deployment must prevent adapter network bypass. This module alone is not a
network ACL and its upstream identity may still have broad native privileges.
"""

import json

from starlette.requests import Request
from starlette.responses import JSONResponse

PATH = "/v1/default/banks/personal_shared/memories/recall"


class RecallGateway:
    def __init__(self, verifier, forward):
        self.verifier, self.forward = verifier, forward

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            raise ValueError("HTTP only")
        request = Request(scope, receive)
        auth = request.headers.getlist("authorization")
        token = auth[0][7:] if len(auth) == 1 and auth[0].startswith("Bearer ") else ""
        access = await self.verifier.verify_token(token)
        if access is None:
            return await JSONResponse({"error": "unauthorized"}, 401)(
                scope, receive, send
            )
        if "hindsight:recall" not in access.scopes:
            return await JSONResponse({"error": "scope denied"}, 403)(scope, receive, send)
        # Check raw path as well: encoded slash/dot aliases must never bypass policy.
        if (
            scope["method"] != "POST"
            or scope["path"] != PATH
            or scope.get("raw_path", PATH.encode()) != PATH.encode()
            or scope.get("query_string")
        ):
            return await JSONResponse({"error": "route denied"}, 403)(
                scope, receive, send
            )
        data = b""
        try:
            async for chunk in request.stream():
                data += chunk
                if len(data) > 8192:
                    raise ValueError("size")
            body = json.loads(data)
            if not isinstance(body, dict) or set(body) != {"query", "max_tokens"}:
                raise ValueError("fields")
            if (
                not isinstance(body["query"], str)
                or not 6 <= len(body["query"].strip()) <= 2000
                or type(body["max_tokens"]) is not int
                or not 1 <= body["max_tokens"] <= 1024
            ):
                raise ValueError("limits")
        except (ValueError, TypeError, UnicodeError):
            return await JSONResponse({"error": "payload denied"}, 400)(
                scope, receive, send
            )
        # Fixed path; no headers, client-selected URL, bank or request options forwarded.
        # Recheck authoritative state after parsing/scanning, immediately before dispatch.
        access = await self.verifier.verify_token(token)
        if access is None or 'hindsight:recall' not in access.scopes:
            return await JSONResponse({'error': 'connection disabled'}, 401)(scope, receive, send)
        try:
            result = await self.forward(body)
            response = JSONResponse(result)
        except (OSError, ValueError, TypeError, RuntimeError):
            response = JSONResponse({"error": "upstream unavailable"}, 502)
        await response(scope, receive, send)
