---
title: Hindsight dot isolated connection candidate
updated: 2026-11-14
type: runbook
status: current
---

# Hindsight dot connection candidate

This is a disabled GitOps candidate, not an installed service or verified personal dot connection. No Argo Application references `charts/hindsight-dot`. This work does not create Google credentials, change existing Hindsight routes, or read/copy the native key.

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

Redis ACL must disable the default user. OAuth user is restricted to `~dot-oauth-e*:*` and `get,set,setex,del,mget,mset,ping,client|setinfo`. Gate user has read-only `%R~dot-control:state` with `get,ping,client|setinfo`; neither runtime user may SET the control state or run FLUSHDB/CONFIG/ACL. An independent operator initializes `dot-control:state` to `{"enabled":false,"epoch":1}`. No initializer/setter/admin credential is mounted in application Pods. No initial state means fail-closed readiness. Epoch and signing/storage keys remain stable for normal restarts. Epoch changes select new encrypted OAuth collections, never reset epoch backwards.

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

## Offline checks

```
helm lint charts/hindsight-dot -n hindsight-dot -f charts/hindsight-dot/kkamji_local_values.yaml
uv run --no-project --with pyyaml python -m unittest discover -s tests -p test_hindsight_dot_chart.py -v
```

Tests cover disabled rendering, required gates, one-replica/non-root/no-token contracts, synthetic no-native/no-public state, native-key gateway-only projection, explicit native ESO property, and proxy egress shape. Source files remain uncommitted until the parent completes image/tests/docs review; final-commit docs freshness is not claimed.
