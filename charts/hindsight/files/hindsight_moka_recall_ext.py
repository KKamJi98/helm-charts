"""Hindsight HTTP extension: one recall-only endpoint for the Moka connector.

The dedicated key is accepted only here. The tenant extension never sees it, so
every native /v1 and /mcp route keeps rejecting it. The bank and the operation
are fixed in code; the request body cannot name another bank or a write.
"""

import hmac
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from hindsight_api.config import get_config
from hindsight_api.engine.memory_engine import VALID_RECALL_FACT_TYPES, Budget
from hindsight_api.extensions import HttpExtension
from hindsight_api.models import RequestContext

BANK_ID = "personal_shared"
ROUTE = "/moka-recall/recall"
MAX_BODY = 4096
MAX_QUERY = 1000
MAX_TOKENS = 4096
NO_STORE = {"cache-control": "no-store"}


def _deny(status, error):
    return JSONResponse({"error": error}, status_code=status, headers=NO_STORE)



class MokaRecallHttpExtension(HttpExtension):
    def __init__(self, config):
        super().__init__(config)
        key = config.get("moka_recall_key", "")
        if len(key) < 32 or key != key.strip():
            raise ValueError(
                "HINDSIGHT_API_HTTP_MOKA_RECALL_KEY must be a dedicated high-entropy key"
            )
        self._key = key.encode()

    def authorized(self, header):
        scheme, _, token = (header or "").partition(" ")
        return scheme == "Bearer" and hmac.compare_digest(token.encode(), self._key)

    def get_router(self, memory):
        router = APIRouter()

        @router.post(ROUTE, include_in_schema=False)
        async def moka_recall(request: Request):
            if not self.authorized(request.headers.get("authorization")):
                return _deny(401, "unauthorized")
            body = await request.body()
            if len(body) > MAX_BODY:
                return _deny(413, "body_too_large")
            try:
                payload = json.loads(body)
            except ValueError:
                return _deny(400, "invalid_json")
            if not isinstance(payload, dict) or set(payload) != {"query"}:
                return _deny(400, "only_query_is_accepted")
            query = payload["query"]
            if (
                not isinstance(query, str)
                or not query.strip()
                or len(query) > MAX_QUERY
            ):
                return _deny(400, "invalid_query")
            context = RequestContext(authenticated_schema=get_config().database_schema)
            result = await memory.recall_async(
                bank_id=BANK_ID,
                query=query.strip(),
                budget=Budget.MID,
                max_tokens=MAX_TOKENS,
                fact_type=list(VALID_RECALL_FACT_TYPES),
                prefer_observations=None,
                request_context=context,
            )
            return JSONResponse(
                {
                    "bank": BANK_ID,
                    "results": [
                        {
                            "text": fact.text,
                            "type": fact.fact_type,
                            "mentioned_at": fact.mentioned_at,
                            "occurred_start": fact.occurred_start,
                            "occurred_end": fact.occurred_end,
                        }
                        for fact in result.results
                    ],
                },
                headers=NO_STORE,
            )

        return router
