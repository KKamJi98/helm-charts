---
title: CI cache registry (zot)
updated: 2026-10-20T00:10:00+09:00
type: architecture
status: current
---

# CI cache registry (zot)

`charts/ci-cache` runs one zot registry for ci-full job Pods. Stage 1 is a
Docker Hub pull-through mirror. Later stages add the CI image cache and the
test archive hand-off under the same registry. Each stage changes this page.

## What it serves

| Path | Source | Who writes |
| --- | --- | --- |
| `library/**` | Docker Hub, synced on demand | zot only (sync) |

Anonymous clients have `read` only. There is no push access in stage 1.

## Boundaries

- Network: `cache-from-full-jobs` admits only `ci-full` Pods labelled
  `arc.kkamji.net/role: job`, port 5000. Light runners (`ci-pr`) and every
  other namespace are denied. `full-jobs` in `charts/arc-full` gains one
  matching egress rule; all other private ranges stay excluded.
- Upstream: `cache-upstream` allows DNS and HTTPS to the Docker Hub registry,
  its token service and blob CDNs only. `production.cloudfront.docker.com` was
  the observed redirect on 2026-10-19.
- No credentials. A GitHub Environment would be the only way to give main
  jobs a secret that PR jobs cannot read, and the BQL and Platform repositories
  have none. The boundary is the network policy plus `read`-only access.
- Transport is plain HTTP inside the cluster. Docker verifies every layer and
  manifest by digest.

## Sizing

| Resource | Value | Why |
| --- | --- | --- |
| memory | request 256Mi, limit 1Gi, `GOMEMLIMIT` 768MiB | sync streams blobs to disk |
| store | emptyDir `sizeLimit` 30Gi, ephemeral request 30Gi | local-path PVCs do not enforce size |
| extensions | `sync` only | search/CVE would download a trivy DB and use memory |

kubelet evicts the Pod if the store passes 30Gi. That resets the cache instead
of filling the node disk. A restart also starts cold.

## Mirror settings that matter

- `http.compat: ["docker2s2"]` keeps Docker media types and digests. In
  v2.1.22 the old `preserveDigest` sync option is ignored. Platform pins base
  images by digest, so a converted manifest would miss and fall back.
- `onDemand` with `content: library/**` and no `pollInterval`: zot runs
  periodic sync only when both content and pollInterval are set
  (`pkg/extensions/extension_sync.go`).
- Tag requests are checked against Docker Hub on every request, so moving
  tags such as `ubuntu:26.04` stay current. Digest requests are served locally.
- Retention deletes `library/**` content not pulled for 14 days; GC runs hourly.

## Fail-open

`trusted-runtime.py` starts dockerd with `--registry-mirror` and
`--insecure-registry` for `zot.ci-cache.svc.cluster.local:5000`. dockerd and its
BuildKit fall back to Docker Hub when the mirror fails. Measured with Docker
29.9.1 (the pinned engine) on 2026-10-19:

| Mirror failure | `docker pull` | BuildKit `FROM` |
| --- | --- | --- |
| connection refused | 3.1s | 3.5s |
| DNS NXDOMAIN | 3.3s | 3.4s |
| silent drop (blackhole) | 3m34s | 2m35s |

A Service with no ready endpoint refuses. A wrong network policy drops
silently, so check the first CI run's pull time after any policy change.

## Rollback

Set `applications.ci-cache.enabled: false` and revert the two `charts/arc-full`
lines (mirror flags, egress rule). Runners pick up the runtime on their next
Pod. Without the egress rule a running mirror config would blackhole, so revert
both together.

## Verification

- `python3 -m unittest tests.test_ci_cache`
- After sync: Pod Ready, Argo Synced/Healthy, no hook Pods (Argo skips
  `helm.sh/hook: test`), zot memory idle and under CI load.
- Before/After: base image pull time in Platform image jobs (before: 38.5s
  for `rust:1.99.0-alpine3.22`, 338MB at about 10MB/s).
