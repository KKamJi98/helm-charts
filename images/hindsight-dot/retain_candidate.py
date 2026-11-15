"""Unwired conversation-summary retain candidate. Not enabled in existing server.

Caller must supply user-approved conversation facts, not private assistant notes.
No transcript discovery, hooks, background reads, or bulk upload are implemented.
"""

import hashlib
import re
import uuid

from adapter import safe_text

ID = re.compile(r"^[A-Za-z0-9_:-]{1,160}$")


def retain_summary(
    summary,
    conversation_id,
    message_id,
    *,
    request,
    scanner="/opt/homebrew/bin/gitleaks",
):
    if not isinstance(summary, str) or not 6 <= len(summary.strip()) <= 4000:
        raise ValueError("Bounded summary required")
    if not all(
        isinstance(v, str) and ID.fullmatch(v) for v in (conversation_id, message_id)
    ):
        raise ValueError("Stable message identifiers required")
    if not safe_text(summary, scanner):
        raise ValueError("Summary refused by privacy scanner")
    digest = hashlib.sha256((conversation_id + "\0" + message_id).encode()).hexdigest()
    # No client-selected bank, URL, tags, context, paths or raw internal IDs sent.
    operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "dot-summary-" + digest))
    payload = {
        "operation_id": operation_id,
        "items": [
            {
                "content": summary.strip(),
                "document_id": "dot-summary-" + digest,
                "metadata": {"source": "dot_user_conversation_summary", "schema": "v1"},
            }
        ],
        "async": True,
    }
    result = request(payload)
    if (
        not isinstance(result, dict)
        or result.get("operation_id") != operation_id
        or result.get("success") is not True
    ):
        raise RuntimeError("Retain acceptance unverified")
    return {"status": "accepted_not_extracted", "operation_id": result["operation_id"]}
