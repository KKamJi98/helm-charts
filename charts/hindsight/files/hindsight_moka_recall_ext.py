"""Hindsight HTTP extension: bank-pinned recall and opt-in retain endpoints.

Dedicated keys are accepted only here. The tenant extension never sees them, so
every native /v1 and /mcp route keeps rejecting them. The bank (personal_shared)
and allowed operations are fixed in code; callers cannot target another bank or
call destructive memory APIs.
"""

import hashlib
import hmac
import json
import re
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from hindsight_api.config import get_config
from hindsight_api.engine.memory_engine import VALID_RECALL_FACT_TYPES, Budget
from hindsight_api.extensions import HttpExtension
from hindsight_api.models import RequestContext

BANK_ID = "personal_shared"
ROUTE = "/moka-recall/recall"
RETAIN_ROUTE = "/moka-recall/retain"
MAX_BODY = 4096
MAX_QUERY = 1000
MAX_TOKENS = 4096
MAX_RETAIN_BODY = 16384
MIN_SUMMARY = 6
MAX_SUMMARY = 4000
ALLOWED_RETAIN_SOURCES = frozenset({"chatgpt_dot", "grok_bot"})
STABLE_ID = re.compile(r"^[A-Za-z0-9_:-]{1,160}$")
NO_STORE = {"cache-control": "no-store"}

# Server-side defense-in-depth policy gate (runs in addition to proxy Gitleaks).
POLICY_BLOCK = re.compile(
    r"\b(?:bunjang|bgzt|quicket)\b|"
    r"(?<![가-힣])번장|번개장터|"
    r"code-work|vault-company|bunjang\.co\.kr|ethan\.kim@|"
    r"\b(?:DAC|TECH|INFRA|DEVOPS|SECOPS|SRE)-\d{3,6}\b|"
    r"(?:password|secret|token|api[_ -]?key|비밀번호|인증번호|복구코드)\s*[:=]|"
    r"authorization\s*:|cookie\s*:|-----BEGIN|"
    r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|"
    r"\bsk-[A-Za-z0-9_-]{20,}\b|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b|"
    r"CONTEXT COMPACTION|ASYNC DELEGATION|INTERNAL NOTIFICATION",
    re.IGNORECASE,
)


def _deny(status, error):
    return JSONResponse({"error": error}, status_code=status, headers=NO_STORE)


def _validate_key(raw, label):
    if not isinstance(raw, str) or len(raw) < 32 or raw != raw.strip():
        raise ValueError(f"{label} must be a dedicated high-entropy key")
    return raw.encode()


class MokaRecallHttpExtension(HttpExtension):
    def __init__(self, config):
        super().__init__(config)
        self._key = _validate_key(
            config.get("moka_recall_key", ""), "HINDSIGHT_API_HTTP_MOKA_RECALL_KEY"
        )
        retain_raw = config.get("moka_retain_key")
        if retain_raw is None or retain_raw == "":
            self._retain_key = None
        else:
            self._retain_key = _validate_key(
                retain_raw, "HINDSIGHT_API_HTTP_MOKA_RETAIN_KEY"
            )
            if hmac.compare_digest(self._retain_key, self._key):
                raise ValueError(
                    "HINDSIGHT_API_HTTP_MOKA_RETAIN_KEY must be distinct from recall key"
                )

    def _authorized_for(self, header, expected_key):
        if expected_key is None:
            return False
        scheme, _, token = (header or "").partition(" ")
        return scheme == "Bearer" and hmac.compare_digest(token.encode(), expected_key)

    def authorized(self, header):
        return self._authorized_for(header, self._key)

    def authorized_retain(self, header):
        return self._authorized_for(header, self._retain_key)

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

        if self._retain_key is not None:

            @router.post(RETAIN_ROUTE, include_in_schema=False)
            async def moka_retain(request: Request):
                if not self.authorized_retain(request.headers.get("authorization")):
                    return _deny(401, "unauthorized")
                body = await request.body()
                if len(body) > MAX_RETAIN_BODY:
                    return _deny(413, "body_too_large")
                try:
                    payload = json.loads(body)
                except ValueError:
                    return _deny(400, "invalid_json")
                if not isinstance(payload, dict) or set(payload) != {
                    "summary",
                    "conversation_id",
                    "message_id",
                    "source",
                }:
                    return _deny(400, "invalid_retain_fields")
                source = payload["source"]
                if not isinstance(source, str) or source not in ALLOWED_RETAIN_SOURCES:
                    return _deny(400, "invalid_source")
                conversation_id = payload["conversation_id"]
                message_id = payload["message_id"]
                if not all(
                    isinstance(v, str) and STABLE_ID.fullmatch(v) is not None
                    for v in (conversation_id, message_id)
                ):
                    return _deny(400, "invalid_identifiers")
                summary = payload["summary"]
                if not isinstance(summary, str) or "\x00" in summary:
                    return _deny(400, "invalid_summary")
                clean_summary = summary.strip()
                if not MIN_SUMMARY <= len(clean_summary) <= MAX_SUMMARY:
                    return _deny(400, "invalid_summary")
                if POLICY_BLOCK.search(clean_summary) is not None:
                    return _deny(422, "content_rejected_by_policy")

                digest = hashlib.sha256(
                    f"{source}\0{conversation_id}\0{message_id}".encode()
                ).hexdigest()
                document_id = f"{source}-summary-{digest}"
                operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, document_id))
                context = RequestContext(
                    authenticated_schema=get_config().database_schema
                )
                result = await memory.submit_async_retain(
                    BANK_ID,
                    [
                        {
                            "content": clean_summary,
                            "document_id": document_id,
                            "context": f"Owner-approved summary from {source}",
                            "metadata": {
                                "source": f"{source}_user_conversation_summary",
                                "host": source,
                                "schema": "v1",
                            },
                        }
                    ],
                    request_context=context,
                    operation_id=operation_id,
                )
                return JSONResponse(
                    {
                        "bank": BANK_ID,
                        "status": "accepted_not_extracted",
                        "operation_id": result["operation_id"],
                        "document_id": document_id,
                    },
                    status_code=202,
                    headers=NO_STORE,
                )

        return router
