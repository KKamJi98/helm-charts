---
title: Istio 1.31.4 Ambient Mode mesh architecture and operations
updated: 2026-11-23T20:54:00+09:00
type: runbook
status: current
---

# Istio 1.31.4 Ambient Mode mesh architecture and operations

`kkamji-lab` completed the full cutover from legacy Istio `1.28.2` Sidecar Mode to sidecarless **Istio `1.31.4` Ambient Mode** (Kubernetes `1.32 - 1.37` supported, sourced from `https://blob.istio.io/istio-release/charts/`).

## 1. Component architecture and Cilium KPR compatibility

| Component | Chart Path | Sync Wave | Scheduling | Resources (Req / Lim) | Purpose |
|---|---|---|---|---|---|
| `istio-base` | `charts/istio-base` | `-1` | CRDs only | - | Istio 1.31.4 CRDs and default validator |
| `istio-istiod` | `charts/istio-istiod` | `0` | 1 replica (worker) | `10m/160Mi` / `320Mi` | Control plane (`profile: ambient`, `PILOT_ENABLE_AMBIENT=true`, HPA disabled, `neverInjectSelector` for Ambient workloads, worker-only Waypoint defaults) |
| `istio-cni` | `charts/istio-cni` | `1` | Worker-only DS (2 pods) | `10m/32Mi` / `128Mi` | Chained CNI plugin (`/etc/cni/net.d/05-cilium.conflist`), in-pod redirection, `dnsCapture: true`, `k8s-m1` excluded |
| `istio-ztunnel` | `charts/istio-ztunnel` | `2` | Worker-only DS (2 pods) | `10m/48Mi` / `192Mi` | Rust L4 zero-trust tunnel (HBONE TCP `15008` mTLS with SPIFFE X.509, ~4Mi live RAM per node, `k8s-m1` excluded) |

Required Cilium 1.19.3 KPR settings in `charts/cilium/kkamji_local_values.yaml`:
- `cni.exclusive: false`: lets `istio-cni` chain into `/etc/cni/net.d/05-cilium.conflist` on worker nodes (`k8s-m1` remains `cilium-cni` only).
- `socketLB.hostNamespaceOnly: true`: prevents Cilium socket-level LB from bypassing in-pod `ztunnel` redirection.
- `bpf.masquerade: false` + `installNoConntrackIptablesRules: false`: avoids conntrack/SNAT conflicts with chained CNI and Ambient `169.254.7.127` host health-probe traffic.

Sidecar retirement cleanup:
- Removed legacy `global.proxy` sidecar configuration from `charts/istio-istiod/kkamji_local_values.yaml` and enforced `sidecarInjectorWebhook.enableNamespacesByDefault: false` with `neverInjectSelector` for `istio.io/dataplane-mode: ambient`.
- Removed dead legacy `envoy-stats` (`.*-envoy-prom`) sidecar scrape job from `charts/kube-prometheus-stack/kkamji_local_values.yaml`. Prometheus scrapes Ambient `ztunnel` (`:15020/metrics`), `istio-cni-node` (`:15014/metrics`), and `istiod` (`:15014/metrics`).

## 2. Namespace enrollment policy

Declarative GitOps enrollment via `syncPolicy.managedNamespaceMetadata.labels` (`istio.io/dataplane-mode: ambient`) in `charts/argo-applications/personal_local_values.yaml`:

- **Enrolled in Ambient Mode (L4 HBONE mTLS active)**:
  - `real-life-rpg`: `real-life-rpg` <-> `postgres-1` and `real-life-rpg-scheduler` CronJob <-> `postgres-1` upgraded transparently to HBONE mTLS with zero sidecar containers (CronJobs exit cleanly). Public traffic from non-ambient `Envoy Gateway` arrives on port `3000` (PERMISSIVE inbound).
  - `kkamji-platform`: `kkamji-platform-api` <-> `kkamji-platform-db-1` upgraded transparently to HBONE mTLS. Existing ingress `NetworkPolicy` (`kkamji-platform-api`, `kkamji-platform-web`) continues allowing non-ambient `Envoy Gateway` traffic on TCP `8080`.
- **Intentionally excluded (`istio-cni` `excludeNamespaces` + strict policy boundaries)**:
  - System / infra / CI namespaces (`kube-system`, `istio-system`, `metallb-system`, `cilium-secrets`, `envoy-gateway-system`, `cert-manager`, `external-secrets`, `external-dns`, `cnpg-system`, `argocd`, `monitoring`, `security`, `arc-system`, `arc-runtime`, `ci-pr`, `ci-full`, `ci-cache`).
  - `keycloak` and `hindsight`: enforce strict port-scoped `NetworkPolicy`/`CiliumNetworkPolicy` contracts (`8080`/`5432`/`8888`) that intentionally do not open HBONE TCP `15008`. Enroll only after explicitly adding TCP `15008` rules to their policy contracts.

## 3. Verification and rollback

Live verification commands:
```bash
kubectl get ns --context kkamji-lab -l istio.io/dataplane-mode=ambient
kubectl get pods --context kkamji-lab -n istio-system -o wide
kubectl logs --context kkamji-lab -n istio-system ds/istio-cni-node --tail=30
```
Check live HBONE mTLS counters on `ztunnel` (`:15020/metrics` or Prometheus):
- `istio_tcp_connections_opened_total{connection_security_policy="mutual_tls"}`

Rollback:
- Remove `managedNamespaceMetadata.labels` from `charts/argo-applications/personal_local_values.yaml` (or run `kubectl label ns <ns> istio.io/dataplane-mode- --context kkamji-lab`). `istio-cni-node` detaches in-pod redirection dynamically with zero pod restarts.
