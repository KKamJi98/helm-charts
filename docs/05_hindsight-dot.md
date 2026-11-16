---
title: Hindsight dot isolated connection candidate
updated: 2026-11-16T12:20:32.522463+00:00
type: runbook
status: current
---

# Hindsight dot connection candidate

Private synthetic staging is deployed after PR68/69. The PR70 public diagnostic window failed at ChatGPT app creation after OAuth discovery, before Google exchange. PR71 removed the dedicated public route and control state is disabled at epoch2. This is not a verified dot connection. No native key or real memory was used. The inactive diagnostic overlay is a candidate, not the currently applied configuration.

## Topology

Use namespace `hindsight-dot` only. Two one-replica Recreate Deployments run the digest-pinned service image: `proxy:8000` and private `backend-policy:8001`. One Redis StatefulSet uses a dedicated 1Gi local-path PVC, AOF with appendfsync always, and an externally supplied ACL file. It is single-node-local, not HA. Redis UID999/GID1000 matches the pinned official 8.4.0-alpine image. Runtime Pods have no API token, no privilege escalation, read-only root filesystems and non-root identities.

Synthetic mode is default. It includes a separate non-persistent fake backend accepting the two fixed personal_shared paths, exposes no native key, and does not render the native ingress rule. The fixture receives synthetic content only; it does not seed Google OAuth state or provide a login bypass.

The optional HTTPRoute owns only `hindsight-dot.kkamji.net` on the existing `envoy-gateway-system/kkamji` HTTPS listener. Existing wildcard TLS and native/UI routes are unchanged. `publicRoute.networkValidated` records an operator acceptance decision, not proof of enforcement. Do not enable the route before testing isolation and owner authentication.

## Configuration and secrets

Rendering enabled workloads requires immutable image digests, verified owner subject, dedicated Google client ID, exact HTTPS MCP client callback allowlist, positive epoch, and permitted capabilities. Default capability is recall-only; retain must be explicit. Google OAuth callback is `https://hindsight-dot.kkamji.net/auth/callback`. The separate Google project/client and policy agreement are managed outside this chart.

Externally supplied Secrets:

- `hindsight-dot-runtime`: `oauth_redis_url`, `gate_redis_url`, `storage_key`, `signing_key`, `google_client_secret`.
- `hindsight-dot-redis-acl`: `users.acl`.
- Real mode only: `hindsight-dot-native` with `api_key`, mounted into backend-policy only.

When `externalSecrets.enabled=true`, ESO maps explicit properties from `/kkamji/automation/hindsight/dot`; `users.acl` maps source property `redis_acl`. No whole-object extraction. Native key maps only `api_key` from existing `/kkamji/automation/hindsight/access`. Orphan/Retain preserves Secret targets; removing ESO does NOT revoke credentials. Existing Store/IAM permissions are not expanded by this chart. Verify source authorization and KMS/store metadata before enabling readers.

Native mode needs explicit approval because the existing native key is schema-wide. Gateway policy and Cilium isolate its use but do not reduce intrinsic key permissions. Shared-key compromise/revocation can affect existing clients. This is not a distinct least-privilege native identity.

Redis ACL must disable the default user. OAuth user is restricted to the current exact epoch prefix, for example `~dot-oauth-e1:*` and `get,set,setex,del,mget,mset,ping,client|setinfo`. Gate user has read-only `%R~dot-control:state` with `get,ping,client|setinfo`; neither runtime user may SET the control state or run FLUSHDB/CONFIG/ACL. An independent operator initializes `dot-control:state` to `{"enabled":false,"epoch":1}`. No initializer/setter/admin credential is mounted in application Pods. No initial state means fail-closed readiness. Epoch and signing/storage keys remain stable for normal restarts. Epoch changes select new encrypted OAuth collections, never reset epoch backwards.

## Network boundary

Cilium policies select each component and enforce ingress/egress. Proxy accepts only existing Envoy gateway Pods, may reach Google identity FQDNs, state6379 and backend-policy8001, and has no native8888/public-native-host rule. Backend-policy accepts proxy, may reach Google/state and synthetic8080 OR native8888. Redis accepts only proxy/gateway and has no outbound rule. Synthetic backend accepts only gateway and has no outbound rule. Native mode creates an additive policy in `hindsight` allowing only the labeled gateway namespace/Pod to API8888. Do not broaden existing policies.

These manifests are offline contract tests, not evidence of live Cilium enforcement. Test DNS behavior, actual label matching, direct native ClusterIP and public native host denial, node/host pathways, forbidden ports and Redis ACL in private staging. Cilium policies are additive with any pre-existing policy; ensure no competing allow-all policy exists. The authorized control operator needs a separate bounded operational path; no operator ingress or API-admin role is granted here. Cluster admins remain trusted. Internal service hops use HTTP/TCP under Cilium isolation; this is not encrypted pod-to-pod transport.

## Release acceptance and rollback

1. Build intended cluster architecture, publish reviewed image, pin digest; verify scanner and non-root image.
2. Prepare approved Secrets without logging values; verify Redis encrypted persistence/ACL and operator gate access. No writes of real conversations.
3. Render and server-dry-run in the personal context, then add reviewed GitOps Application only after explicit release authorization. Do not run helm install/upgrade.
4. Keep public route off. Validate network paths, read-only defaults, native absence in synthetic mode, readiness failure, restart persistence and kill/epoch behavior.
5. Complete owner Google login and actual dot registration with synthetic data. Personal dot retain visibility is unproven until tested; never promise universal transcript capture.
6. Switch to native only under approved shared-key handling. Summaries require explicit user-authorized facts; heuristic scanning cannot prove consent. No bulk historical upload or private agent notes.

Stop only the new route/proxy/gateway for rollback; stopping workers terminates streams but cannot undo committed retains. Gate checks alone cannot cancel already-dispatched native work. Invalidate dedicated sessions/refresh references and increment epoch before reopening. Preserve existing Hindsight data, clients, routes and 600-second extraction timeout. Preserve PVC/retained Secrets until explicit data-removal authorization. The chart does not automate destructive rollback.

Callback registration and authorization both enforce exact URI membership, including query strings. FastMCP pattern matching alone is not trusted; callback glob brackets and fragments are rejected.

## Offline checks

```
helm lint charts/hindsight-dot -n hindsight-dot -f charts/hindsight-dot/kkamji_local_values.yaml
uv run --no-project --with pyyaml python -m unittest discover -s tests -p test_hindsight_dot_chart.py -v
```

Tests cover disabled rendering, required gates, one-replica/non-root/no-token contracts, synthetic no-native/no-public state, native-key gateway-only projection, explicit native ESO property, and proxy egress shape. Draft PR #68 carries the disabled candidate. Final-commit checks do not establish live deployment acceptance.

## Private staging operator and acceptance procedure

These are prepared procedures, not executed cluster evidence. They add no chart initializer, credentials, RBAC, route, or automatic hook. Use only synthetic mode with publicRoute disabled. Image workflow validates matching PRs without publishing; publishing is a separate explicit manual job, default off. Workflow registration/dispatch availability must be verified after landing; deployment always pins the resulting digest.

1. Provision a dedicated Redis `operator` ACL entry with only `%RW~dot-control:state +get +set`. Keep its password in an approved local private credential store, never runtime SSM JSON, app Secret, Job, CLI argument or repository. The ACL file contains its password hash, not plaintext. Runtime ACL users remain unchanged. Do not grant CONFIG, ACL, FLUSHDB, scan or OAuth key access. Use one operator at a time.
2. Authorized personal-cluster operator needs existing pod get and pods/portforward permissions only for this operational step. Do not grant new cluster-wide RBAC. Run local `scripts/hindsight-dot/gate_control.py initialize --epoch 1` using a trusted Python environment with redis installed. The script prompts privately, binds forwarding to 127.0.0.1 only, allows 15 seconds to establish access and tears down forwarding on every exit. It uses `state-0`, never kubectl exec. Initial state is disabled, SET NX, with no overwrite. All changes compare the exact current epoch. Use security-stop for security rollback: Redis 8.4 SET IFEQ atomically advances epoch by one and disables the gate. No automatic retries or backwards epoch changes. maintenance-pause is explicitly non-revoking and must never substitute for security-stop. No proxy/gateway Pod receives the operator password.
3. Port-forward uses the Kubernetes API/kubelet trusted-admin path and may bypass ordinary Cilium ingress enforcement. It is NOT evidence of policy acceptance. Local administrator access and endpoint trust are required; abort if existing access cannot establish this narrow path, rather than widening state ingress. The script avoids existing listeners but cannot defend against a malicious local administrator racing its loopback port.
4. Render `scripts/hindsight-dot/network_fixtures.py --image REGISTRY/IMAGE@sha256:DIGEST --native-ip NATIVE_CLUSTER_IP --public-native-ip RESOLVED_PUBLIC_IP` to a temporary JSON file. No command in this script applies resources. Use current read-only service/DNS evidence for IP values and verify destination health independently first. Review and apply only these three bounded Jobs in hindsight-dot under release authorization; no Secrets, service-account tokens, production payloads or CNP changes. Jobs expire after 90 seconds and TTL cleanup after 600 seconds; no retry. Private registry pull credentials, if required, must use an existing approved imagePullSecret reference without exposing values.
5. Proxy/gateway Jobs deliberately carry the respective policy identity labels, so they exercise existing rules without widening policy. Their readiness probes always fail on closed port65534, preventing ready Service endpoints (verify publishNotReadyAddresses is false). Outsider has neither identity. This label authority is a staging-only privilege, not a new trusted production identity. Inspect Job logs and completion via kubectl logs/get, never exec. DNS failure is an explicit failure, not accepted as a network denial. Native/public denied destinations must be independently known reachable/healthy; a timeout alone is insufficient proof. Require corresponding Cilium dropped-flow evidence for denied paths and forwarded-flow evidence for allowed paths, plus policy revision/identity labels matching the test Pods.
6. Additional live-only gates: node/host bypass posture, all public native IPs including IPv6 if available, forbidden ports, actual Envoy labels, DNS and Google443, Redis runtime ACL denials and control persistence, and real owner OAuth exchange. These Jobs do not establish those claims. Do not set networkValidated until evidence is reviewed; remove completed fixture Jobs before public route. No native mode or real memory write is part of this staging procedure.

The operator path changes only the dedicated Redis control key. Security rollback uses `security-stop --epoch CURRENT`, atomically committing disabled plus CURRENT+1. Existing processes fail closed on epoch mismatch. Provision the new exact-epoch OAuth ACL and matching dedicated credentials first; do not widen to a cross-epoch wildcard. Preserve the incremented control state, do not initialize or restore it. Update BOTH proxy and gateway GitOps epoch and credential references to the new values, reconcile Redis ACL and both Deployments, verify OAuth storage access and old-session rejection, then verify the deployed configuration before `enable --epoch NEW --verified-configs-epoch NEW`. The latter flag is an explicit operator attestation, not an automated cluster verification. Old OAuth collections must not be restored or reused; verify old access/refresh rejection after reopen. New owner authorization may be required. Never decrease epoch to recover sessions. `maintenance-pause` preserves the epoch and therefore intentionally permits old sessions when resumed: it is not token revocation. Neither operation undoes an already-dispatched native retain. Keep PVC/Secrets for authorized recovery, without restoring a prior control epoch.

[Redis SET documentation](https://redis.io/docs/latest/commands/set/) specifies IFEQ since 8.4.0; the pinned Redis image meets that requirement. CAS needs only the existing GET/SET key ACL, not Lua, WATCH, MULTI, or additional command permissions. On unsupported syntax, competing update or ambiguous transport failure, stop and inspect state manually; never fall back to plain SET. A compromised operator credential still has raw SET authority and can violate monotonicity outside this tool, so it remains privileged and local-only.

## Approved synthetic staging preparation (2026-11-15)

The owner approved a dedicated personal-cluster namespace, Redis 1Gi PVC, proxy/gateway/synthetic backend, narrow Cilium rules, image publishing and dedicated runtime SSM/Secrets. Public routes, existing native keys, real memories and company resources remain excluded. `staging_local_values.yaml` pins the tested published digest from workflow run 43711932181. Anonymous manifest retrieval succeeded. Owner identity is the deny-all placeholder and the callback is synthetic only; neither enables real login or memory access.

The proposed Application targets main. Branch publication is not a merge or deployment. AWS personal session renewal and runtime parameter provisioning are pending; do not merge or claim live acceptance until these and explicit merge authorization are complete. Initialize the Redis gate disabled after deployment, then enable only for approved synthetic checks using the separate local operator credential. No production native mode is enabled by this change.

## Initial live staging finding

PR 68 deployed private synthetic staging on 2026-11-15. ESO synchronized and the 1Gi PVC bound, but Uvicorn 0.54 auto-detected the factory-returned bound async method as ASGI2, causing health HTTP 500 and restart loops. Explicit `--interface asgi3` in both Helm commands fixes invocation selection; the image default command is aligned for future builds. Regression coverage exercises the loaded Uvicorn app, not only direct ASGITransport. Existing digest can be reused with the Helm argument fix. This correction still requires separate merge approval. Public route and native mode remain off; gate remains disabled at epoch 1. Live network acceptance remains pending.

## Proposed public synthetic identity diagnostic

The owner approved the trusted-node boundary and a dedicated HTTPS OAuth test, excluding native keys, real memories and retain. Local node TCP checks reached same-node proxy/gateway/Redis; this is an explicit administrator trust boundary, not host isolation. Cross-node timeouts were not independently attributed. Bounded Pod tests and Hubble showed intended native/public drops; a readiness-gated proxy recheck passed all five TCP expectations.

The proposed third values file `oauth_diagnostic_values.yaml` exposes only hindsight-dot.kkamji.net via the existing HTTPS Gateway. `networkValidated` records scoped acceptance with the above limits, not universal isolation. The exact ChatGPT callback was read from the authenticated custom MCP advanced OAuth UI on 2026-11-15. It is not a credential. Discovery is currently unavailable before route deployment. Recheck callback before registration; never widen its allowlist to a wildcard. Use DCR after metadata discovery succeeds; do not copy the Google client secret into ChatGPT.

This overlay enables identity diagnostic only, with deny-all owner, synthetic backend and recall-only capability. Diagnostic logs only a verified matching owner's subject/email and denies MCP access. The operator gate remains disabled until deployment inspection; enable briefly for the approved OAuth test. Recording the real owner subject or allowing tool access is a separate reviewed change. If testing fails, remove the overlay through GitOps and security-stop the dedicated gate to invalidate sessions; preserve PVC and existing Hindsight. Merge is a separate approval gate.

## OAuth window stopped

The 2026-11-15 supervised public diagnostic reached valid HTTPS/OAuth metadata discovery and ChatGPT detected DCR. Creating the custom plugin returned a generic rejected-settings error before Google authorization; root cause is not established. No real memory or native key was used. The operator security-stopped the gate at epoch 2, invalidating epoch 1 sessions; do not decrement it. This rollback removes only the public diagnostic overlay from the Argo values list. Preserve retained Secrets/PVC. Any next attempt needs reviewed epoch-2 ACL/storage credentials and both deployment epochs before re-enabling. The overlay file remains an inactive candidate, not a live configuration.


## Next diagnostic candidate and epoch2 restart plan

Source-only DCR diagnostics emit a maximum of 16 fixed-vocabulary events per provider process: accepted, redirect_denied, storage_or_provider_error. These new events do not record metadata, callback strings, exceptions, tokens or credentials. Provider/storage exceptions are converted to a fixed RegistrationError without a chained traceback; a synthetic ASGI registration test checks captured application logs and response for leakage. This is not a blanket claim that all Uvicorn/framework logs are redacted. This bounds log volume, not request rate; it is NOT a DCR abuse-control feature. Validation rejected before the provider callback is not covered. Public retry must remain short and attended.

The generic ChatGPT rejection is not a proven redirect mismatch. Official OpenAI authentication guidance supports exact callback-ID redirects; retain the exact observed callback and do not widen the allowlist without evidence. Local tests cover public-client none authentication, advertised Google scopes, exact callback rejection and redacted bounded logs. These cannot reproduce ChatGPT's unknown original registration payload.

Before any restart: preserve control disabled/epoch2 and the existing PVC. Prepare an epoch2 bundle in a fresh private directory, use new signing/storage keys and epoch2-only OAuth ACL namespace, and keep operator material out of SSM/runtime. Do not initialize or decrease the existing control epoch. ESO refresh alone does not prove Redis ACL reload: coordinate a GitOps rollout of Redis and both app Deployments, verify applied ACL and epoch2 storage access privately, and prove epoch1 grants fail. Failed rotation stays closed; do not restore epoch1 control state. The Google credential does not need unrelated rotation. Secret writes, rollout, image publication and public route activation are separate from this source-only change.

Reference: https://developers.openai.com/plugins/build/auth


## Epoch2 private rollout candidate

The approved epoch2 runtime bundle has been stored as SSM version2; no native credential is included. Before merging this rollout, confirm both ESO target Secrets match that bundle without printing values. ESO remains on its existing one-hour refresh interval. No force-refresh or public-route activation is bundled. Redis Pod template now tracks the non-secret credential epoch so a GitOps epoch bump reloads its ACL file by restart. The existing PVC and disabled epoch2 control state must survive; do not initialize or revert the state. Proxy/gateway epoch changes trigger their existing Recreate rollout. A rollout failure stays closed and is repaired forward, not by enabling epoch1.


## Supervised epoch2 stable-callback diagnostic

After metadata discovery, the same ChatGPT custom MCP draft now displays `https://chatgpt.com/connector_platform_oauth_redirect` in its user-defined client view. Local provider metadata independently advertises `authorization_response_iss_parameter_supported=true`. This matches the OpenAI documented stable-redirect rule. The earlier callback-ID allowlist was observed before discovery; mismatch is a strong hypothesis, not a proven historical request payload.

This attempt replaces, rather than broadens, the exact allowlist. Tests accept the stable URL and reject the previous callback-ID URL and query variants. The same dedicated synthetic public overlay is activated only for an attended diagnostic. Gate remains disabled2 until rollout and TLS checks. No native secrets, memories or writes; bootstrap still denies all tool access. There is no DCR rate limiter: the operator must keep the open window short and close on unexpected load, UI rejection or completion. On failure remove the overlay, security-stop to epoch3, and verify actual route prune. No automatic restart or epoch downgrade.


## Epoch2 supervised result and close

Stable exact callback resolved the app-creation blocker: DCR accepted, ChatGPT synthetic plugin was created, Google personal email authorization completed, and the server verified the owner identity. Bootstrap intentionally denied MCP access (401); no native key or real memory was used. The verified subject is stored only in the local private evidence, not this repository. Following the attended diagnostic, security-stop advanced control to disabled epoch3 and this change removes the public overlay. Verify actual HTTPRoute prune. Installed synthetic plugin presence is not a usable memory connection. Further production access needs a separately reviewed owner/epoch3 configuration and applicable authorization.


## Owner-positive synthetic candidate

Optional owner.fromSecret injects verified owner subject from the dedicated runtime Secret, never public values. Bound-owner mode requires a separate rate credential. Source preparation does not enable it, rotate credentials, update image digests or reopen routes. Google tokeninfo validates audience and supplies subject; the bridge additionally matches claims.sub to verified subject and claims.aud to the dedicated Google client. It never trusts a decoded unverified JWT. Native mode remains excluded from this phase.

DCR now uses one persistent JSON state key dot-dcr-eN:state, fixed-window5/600seconds and hard32 attempts per epoch. It reserves with Redis8.4 SET IFEQ using Redis TIME, at most8 explicit compare-conflict retries, and no retry after ambiguous network outcomes. Missing/corrupt/expiring state fails closed. Existing clients do not expire due to quota. Rate identity has GET/SET/TIME/TTL on this exact key only. Trusted initializer uses SET INITIAL_STATE NX; Redis ACL cannot enforce NX/IFEQ options. This is admission abuse control, not an authorization boundary against a compromised proxy. Registration body cap16KiB/read timeout2s and oversize/slow/disconnect/slash tests remain. Token/recall budgets are not added, so this candidate permits only a short supervised synthetic window, not durable exposure.


## Durability blocker and CAS replacement (not deployed)

An isolated official Redis8.4.0 AOF-always restart test exposed a blocker in the proposed Lua counter: its MULTI/EXEC effects were fsynced, but AOF loading rejected the transaction with NOPERM under the default-disabled ACL. Direct SET fixtures survived while counter increments did not. Existing production ACL/default user must NOT be broadened to mask this.

The replacement candidate uses one persistent JSON state key and Redis8.4 SET IFEQ compare-and-set, with Redis TIME for window calculation and bounded contention retries. Missing/corrupt/expiring state fails closed. A CAS with ambiguous network outcome is never retried; at worst quota is consumed without registration. The dedicated rate identity receives GET/SET/TIME/TTL for only dot-dcr-eN:state, not control/OAuth/other epoch keys. ACL cannot restrict SET to IFEQ/NX options, so the limiter and trusted initializer enforce those options. A compromised proxy can overwrite its quota state; this quota is abuse control, not an authorization boundary. Owner authentication, network restrictions and emergency gate remain independent. No real ACL/SSM/deployment changes are made by this replacement.

CAS isolated validation: offline12 tests and actual official Redis8.4.0 integration9 tests passed, including graceful AOF restart retaining window/epoch quota. Direct and Lua attempts to access foreign keys are denied, and EVAL is not granted at all. These synthetic fixtures use no cluster credentials; their owned container and temporary data directory are removed after completion. Real deployment must still verify its mounted ACL and existing control/PVC preservation.

The isolated AOF test runs as the invoking non-root UID/GID so Linux-host bind-mounted AOF evidence remains readable/cleanable without sudo. The first Linux CI attempt failed on fixture ownership, not a demonstrated CAS counter loss; no production UID/securityContext is changed.

### Epoch3 private owner synthetic rollout

PR76 source-only commit 579dee5 passed candidate and explicit publish run 43739331618. The private staging values now pin its tested digest and epoch3, enable verified owner from the dedicated ESO Secret, and retain synthetic-only/native-disabled/public-route-disabled. Both existing ESO Secret fields matched SSM version3 before preparing this change. New owner/rate fields must be checked after ESO reconciliation before any gate enable. Gate stays disabled3; readiness503 is expected. Rate state bootstrap is trusted exact-key SET NX, not an ACL-enforced option. A compromised rate credential can reset only its quota state. Rollback stops the gate with a forward epoch and leaves the route absent; never restore prior ACL/epoch. No actual memory or native credentials.

### Supervised owner-bound synthetic window

The dedicated owner_synthetic_window_values overlay retains verified owner binding, admission quota, synthetic-only recall and no native key. It is distinct from the inactive deny-all diagnostic overlay. Private epoch3 checks passed and gate was restored disabled3 before publication. The short supervised OAuth test must end with forward security-stop epoch4 and removal of the overlay/actual route. Quota is 5 attempts/600 seconds, 32 total per epoch (2 used by private acceptance checks); do not reset counters. This is not permanent public availability or real memory consent.

### Owner synthetic window closed

ChatGPT reported Primary connection complete for a new epoch3 synthetic plugin after verified Google owner OAuth. Old epoch2 client was correctly rejected as unregistered. No real/native memory was accessed. Tool invocation was not demonstrated in this worker session, so OAuth success is not recall completion. Security-stop advanced the control gate to disabled4, invalidating epoch3 access. This change removes the transient public overlay; verify actual HTTPRoute prune and external refusal after sync. Keep credentials/PVC/native intact and never lower epoch.


### Epoch4 private resume

The owner renewed the personal AWS session and authorized continuing the bounded synthetic recall test. A fresh epoch4 runtime bundle was stored as SSM version4 with a new local-only operator credential. Existing disabled epoch4 control state and PVC must be preserved. The rollout remains private with no public route and no native credentials. Before enabling, verify both ESO Secrets, deployed ACL, epoch4 OAuth/rate access and old credential rejection. A later attended public window is limited to 10 minutes and must finish with disabled epoch5, actual route removal and external refusal. OAuth reconnection may be necessary; this change does not establish recall success.


### Epoch4 attended recall window

Private checks passed after PR87: disabled4 survived Redis restart, both apps use epoch4 synthetic-only without native credentials, new OAuth namespace works, foreign-key access and old Redis authentication are rejected. The fresh rate state was initialized once using NX. This overlay is only for the owner-approved attended MCP recall test, at most 10 minutes. End it with security-stop to disabled5, removal of the overlay and actual route, and external 404 verification. No personal memories are read; the synthetic fixture returns an empty result set.


### Epoch4 window closure

This change removes the temporary owner-bound public overlay. The operator must security-stop forward to disabled5 and verify actual route removal and external 404. This closure change alone does not establish a successful recall; report the observed MCP result separately. Preserve the Redis PVC and native Hindsight settings, and never restore epoch3 or epoch4 grants.


## Durable DCR registration, revocable synthetic sessions

`durableRegistration` is an opt-in candidate and remains false in deployed values.
It requires syntheticBackend and a verified secret-backed owner. No native mode,
new network destination, Google scope, callback, or control privilege is added.
FastMCP 4.2.0 uses one client_storage for DCR and sessions; the public AsyncKeyValue
router sends exactly `mcp-oauth-proxy-clients` to a separate encrypted collection.
Every other collection (including unknown future SDK collections) remains under
`dot-oauth-e<epoch>:`. There is no migration, old-store fallback, or data restore.
The image tests cover all eight storage operations and the pinned SDK contract.

The opt-in runtime adds `registration_redis_url` and `registration_key`.
The dedicated registration Redis user can access only
`~dot-registration-v1:__mcp-oauth-proxy-clients::*` with the same bounded basic
store commands; it cannot access session/control/rate keys or administrative
commands. The double underscore after the prefix is inserted by the pinned
PrefixCollectionsWrapper; a regression test fixes this wire-format contract.
Its password may rotate on every epoch. The independent registration
Fernet key must remain stable while the app connection is retained. Missing key,
Redis failure, or decryption failure is not treated as permission to use another
store. Readiness checks both stores when opted in.

`prepare_staging_secrets.py --durable-registration --verified-owner OWNER ...`
creates a new private `registration-local.json` containing only schema and the
registration encryption key. For later epochs, explicitly pass
`--registration-key PRIVATE_REGISTRATION_LOCAL_JSON`; the helper rejects a whole
runtime bundle, insecure permissions, and symlinks. It preserves only that key,
rotates session/signing/Redis credentials, and creates no network writes. The
file is secret, owner-only, and must not be committed or exposed. Losing this key
requires a new client registration, not restoring old grants.

Initial adoption starts an empty registry: the old ChatGPT client is not recovered.
A supported reconnect may still use its old client ID; if it does not perform new
DCR, stop and use the supported new-connection flow only with appropriate approval.
Prepare this before the bounded public window. Subsequent epochs preserve DCR
identity but require new owner authorization: old access/refresh tokens, unconsumed
codes, transactions, CSRF records, upstream tokens and JTI mappings are denied.
Regression tests hold signing and session encryption keys constant to prove that
epoch namespace isolation, not just key rotation, rejects the old tokens.
The public route, fresh image digest, new epoch rollout and operator enable remain
separate explicitly controlled steps. Never reuse an old epoch or leave the route
open while investigating OAuth failure.


## Private epoch5 synthetic rollout

PR90 separates durable DCR registration from epoch-scoped grants. This private rollout pins the tested commit62c2770 image digest and opts in only the existing synthetic environment at epoch5. Gate must remain disabled5 and the HTTPRoute absent while the fresh runtime/ACL are reconciled and checked. Never restore e3/e4 grants. Verify registry encrypted roundtrip, cross-key ACL denial, revoked Redis credentials, both app configurations, and native service preservation before any separately bounded OAuth window.
