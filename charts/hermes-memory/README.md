# Hermes shared memory backend

This chart deploys the shared vector store used by Hermes mem0 OSS mode.

Important: Hermes's mem0 plugin does not use a remote mem0 REST server in OSS mode.
Each Hermes process runs the mem0 library in-process and connects to this shared Qdrant backend.

## Runtime endpoint

- Namespace: `hermes`
- Host: `memory.kkamji.net`
- Backend: Qdrant HTTP API on port 6333
- Auth: Envoy Gateway `SecurityPolicy` API key plus Qdrant API key using the same `api-key`/`x-api-key` header value

## Bootstrap secret mode

Current bootstrap uses `auth.generatedSecret.enabled=true` because this Hermes session does not have AWS credentials to write SSM SecureString parameters.
The generated secret is not stored in Git. The ArgoCD Application ignores `/data` drift for `hermes-memory-qdrant-auth` to avoid random rotation on each render.

Target best-practice mode:

1. Store `/kkamji/hermes/mem0/qdrant-api-key` as an AWS SSM `SecureString`.
2. Set `auth.generatedSecret.enabled=false`.
3. Set `auth.externalSecret.enabled=true`.
4. Remove the ArgoCD Secret ignoreDifference after migration if desired.

## Hermes mem0 OSS config shape

Each Hermes instance should use the same embedder model to avoid Qdrant collection dimension mismatch.

```json
{
  "mode": "oss",
  "user_id": "ethan",
  "agent_id": "herwin-or-hermac",
  "oss": {
    "llm": {"provider": "openai", "config": {"model": "gpt-5-mini"}},
    "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
    "vector_store": {
      "provider": "qdrant",
      "config": {
        "url": "https://memory.kkamji.net",
        "api_key": "<from hermes-memory-qdrant-auth>"
      }
    }
  }
}
```

Caveat: current Hermes mem0 reads filter by `user_id` only. `agent_id` is written but not used as the default read filter. Use `user_id=ethan` only for intentionally shared global memory; use separate user IDs or plugin changes if strict herwin/hermac isolation is required.
