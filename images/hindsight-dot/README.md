# Hindsight dot service candidate

Prepared locally only. Not a deployed or registered dot integration. Actual Google callback/consent, personal dot write capability, persistent Redis/ACL and Cilium policy require staging acceptance. No real credentials or personal memories included.

## Artifact and build

```
docker build -f Containerfile -t hindsight-dot-candidate:local .
docker run --rm --network none --read-only --tmpfs /tmp hindsight-dot-candidate:local python -c 'from adapter import safe_text; print(safe_text("Fictional Alex likes books.","/usr/local/bin/gitleaks"))'
```

Version-pinned official Python3.14.4, Gitleaks8.30.1, FastMCP4.2.0; exact Python transitive lock. Local Apple Silicon image build passed; CI must build intended cluster architecture and pin release digest. No registry push performed.

## Two single-worker modes

- Proxy: `uvicorn service:factory --factory --host 0.0.0.0 --port 8000 --workers 1 --no-access-log`
- Gateway: same with port8001. `DOT_MODE=gateway`.
- GET `/health`:200 process alive. GET `/ready`:200 only if authoritative enabled+epoch and OAuth storage read successful,503 otherwise. These reveal only ok/unavailable, bypass OAuth to support probes.
- Proxy serves MCP `/mcp` and GoogleProvider OAuth routes including `/auth/callback`. Gateway serves only two fixed native POST paths; all other paths denied. Do not put gateway behind public ingress.
- Read-only root filesystem, uid/gid10001, writable `/tmp` only, no service-account token required. Outbound requests are bounded/no redirects. Native timeout20s is acceptance submission timeout, not Hindsight extraction600s.

## Environment

Required: `DOT_MODE`, `DOT_EPOCH`, `DOT_PUBLIC_URL`, `DOT_OWNER_SUB`, `DOT_OWNER_EMAIL`, `DOT_GOOGLE_CLIENT_ID`, `DOT_REDIRECT_URIS` JSON exact HTTPS redirect list. `DOT_CAPABILITIES` JSON defaults `["hindsight:recall"]`; opt-in adds `hindsight:retain`.

Default URLs:
- `DOT_GATEWAY_URL=http://backend-policy.hindsight-dot.svc.cluster.local:8001`
- `DOT_NATIVE_URL=http://hindsight-api.hindsight.svc.cluster.local:8888`

Secret file-path env, both modes:
- `DOT_OAUTH_REDIS_URL_FILE`: dedicated Redis ACL user permitted RW ONLY `dot-oauth-e<epoch>:*` keys.
- `DOT_GATE_REDIS_URL_FILE`: distinct dedicated Redis ACL user permitted GET ONLY exact `dot-control:state` key. Services must not be able to enable themselves. Disable default Redis user. Store Redis data persistently and permit network ingress only from designated pods. TLS/internal network policy decision belongs to staging topology; don't publish Redis.
- `DOT_STORAGE_KEY_FILE`: Fernet urlsafe base64 key, stable across routine restarts.
- `DOT_SIGNING_KEY_FILE`: independent strong secret, stable across routine restarts.
- `DOT_GOOGLE_CLIENT_SECRET_FILE`: new dedicated Google web client only.

Gateway normal mode additionally needs `DOT_NATIVE_API_KEY_FILE`. `DOT_NATIVE_GATEWAY_KEY_FILE` is optional and unnecessary for direct internal API port8888; public Envoy header must not be reused gratuitously. Current native ApiKeyTenantExtension supports only one global key, not a verified dedicated least-privilege key. Mounting that global key needs explicit owner decision and network/permission containment; this candidate does not create a separate native identity.

Staging: `DOT_STAGING_SYNTHETIC=1` permits NO native credentials and requires EXACT `DOT_NATIVE_URL=http://synthetic-backend.hindsight-dot.svc.cluster.local:8080`. The synthetic service is a separate staging fixture not deployed by this code. This mode cannot point to real native service. No fixture seeding endpoint is exposed in the running service; Google mock seeding exists in tests only.

## Authoritative state and epoch

Operator-created Redis string `dot-control:state` is exactly `{"enabled":false,"epoch":1}` initially. No service setter or automatic enable exists. Missing/malformed/unreachable state fails closed. State socket timeout0.3s and async gate timeout0.5s. OAuth records use official RedisStore + official FernetEncryptionWrapper, collection prefix `dot-oauth-e<epoch>:`. Incrementing state epoch and changing deployed epoch automatically selects a fresh namespace; old tokens cannot resolve references. Routine same-epoch restart preserves records. Do not reset epoch backwards or delete live data casually. Stop workers for in-flight requests/streams; gate checks cannot undo already committed retains.

Redis ACL exact commands/key patterns must be verified against actual store operations before deployment; runtime must not have CONFIG/ACL/FLUSHDB/admin access. Candidate Redis adapter writes keys e.g. `dot-oauth-e1:mcp-upstream-tokens::<id>`. RedisStore generic library contains FLUSHDB API but service never calls it; ACL must deny it.

## Security boundary

Both proxy and gateway verify owner sub+verified email using GoogleProvider and independently consult gate. Gateway maps owner to configured fixed capabilities, never caller-selected Google scopes. Gateway alone holds native key. Cilium must block proxy from native service/public native host, permit proxy only private gateway, and narrowly allow gateway to native8888. Redis crypto key is shared between these two trusted components, so compromising either compromises OAuth session confidentiality; it does not grant native key to proxy automatically. No claims of protection against compromised cluster admin.

Retain invokes stable conversation/message ID normalization and heuristic privacy scanner at proxy AND gateway. Scanner output is NOT semantic consent proof. Only explicitly authorized summaries, never private agent notes/tool/system traces or historical bulk transcripts. Recall scanner filters query and returned selected text. Native errors are suppressed. Memory text is untrusted context, not instructions.

## Test evidence

- `python -m unittest test_service.ServiceTests test_service.StateTests -q`:8 tests pass (full owner HTTP token->MCP->independent gateway->synthetic native recall+retain, nonowner deny, company marker deny, disabled directgateway, same-store restart, new-epoch old token deny, encrypted value not plaintext, state shape checks).
- Existing upstream synthetic token/PKCE/refresh tests remain in `test_flow_base.py`; fixture, not real Google.
- Local image build and network-none nonroot/read-only scanner smoke pass.
- Not yet validated: durable Redis restart/ACL in real topology, distributed replicas (intentionally single), actual native identity, Cilium bypass denial, Google login/CSRF flow, real dot tool registration/write support. No production deployment should be inferred.
