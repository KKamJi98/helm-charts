---
title: Istio 1.31.4 Ambient Mode mesh architecture and operations
updated: 2026-11-25T15:40:00+09:00
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
| `istio-cni` | `charts/istio-cni` | `1` | Worker-only DS (2 pods) | `10m/32Mi` / `128Mi` | Chained CNI plugin with Istio-owned config (`/etc/cni/net.d/02-istio-cni.conflist` sourced from `05-cilium.conflist`), in-pod redirection, `dnsCapture: true`, `k8s-m1` excluded |
| `istio-ztunnel` | `charts/istio-ztunnel` | `2` | Worker-only DS (2 pods) | `10m/48Mi` / `192Mi` | Rust L4 zero-trust tunnel (HBONE TCP `15008` mTLS with SPIFFE X.509, ~4Mi live RAM per node, `k8s-m1` excluded) |

Required Cilium 1.19.3 KPR settings in `charts/cilium/kkamji_local_values.yaml`:
- `cni.exclusive: false`: stops Cilium from removing `/etc/cni/net.d/02-istio-cni.conflist` on worker nodes (`k8s-m1` remains `cilium-cni` only).
- `socketLB.hostNamespaceOnly: true`: prevents Cilium socket-level LB from bypassing in-pod `ztunnel` redirection.
- `bpf.masquerade: false` + `installNoConntrackIptablesRules: false`: avoids conntrack/SNAT conflicts with chained CNI and Ambient `169.254.7.127` host health-probe traffic.

Required `istio-cni` reboot-safety settings in `charts/istio-cni/kkamji_local_values.yaml` (mitigates `istio/istio#60882`):
- `cniConfFileName: 05-cilium.conflist` + `istioOwnedCNIConfig: true` + `istioOwnedCNIConfigFileName: 02-istio-cni.conflist`: Cilium rewrites `/etc/cni/net.d/05-cilium.conflist` on every agent start (`write-cni-conf-when-ready`). Writing the chained config to Istio's own higher-priority `02-istio-cni.conflist` prevents Cilium from wiping `istio-cni` out of the chain across worker reboots (on Ubuntu 24.04 persistent `/etc/cni/net.d/`). Before `ztunnel` connects, `cmdAdd` fails closed so kubelet retries sandbox creation instead of leaving pods silently unenrolled (`:15008 Connection refused`).
- Follow-up on Istio `1.31.5+` (upstream backport `istio/istio#62923`, merged after `1.31.4`): enable `env.AMBIENT_RECONCILE_ENROLLMENT_INTERVAL: "5m"` for periodic netns enrollment self-healing.

Sidecar retirement cleanup:
- Removed legacy `global.proxy` sidecar configuration from `charts/istio-istiod/kkamji_local_values.yaml` and enforced `sidecarInjectorWebhook.enableNamespacesByDefault: false` with `neverInjectSelector` for `istio.io/dataplane-mode: ambient`.
- Removed dead legacy `envoy-stats` (`.*-envoy-prom`) sidecar scrape job from `charts/kube-prometheus-stack/kkamji_local_values.yaml`. Prometheus scrapes Ambient `ztunnel` (`:15020/metrics`), `istio-cni-node` (`:15014/metrics`), and `istiod` (`:15014/metrics`).

## 2. Namespace enrollment policy

Declarative GitOps enrollment via `syncPolicy.managedNamespaceMetadata.labels` (`istio.io/dataplane-mode: ambient`) in `charts/argo-applications/personal_local_values.yaml`:

- **Enrolled in Ambient Mode (L4 HBONE mTLS active)**:
  - `real-life-rpg`: `real-life-rpg` <-> `postgres-1` and `real-life-rpg-scheduler` CronJob <-> `postgres-1` upgraded transparently to HBONE mTLS with zero sidecar containers (CronJobs exit cleanly). Public traffic from non-ambient `Envoy Gateway` arrives on port `3000` (PERMISSIVE inbound). Note: `helm/real-life-rpg/templates/namespace.yaml` renders its own `Namespace` resource, so `istio.io/dataplane-mode: ambient` is declared in both `real-life-rpg` chart and Argo CD `managedNamespaceMetadata`.
  - `kkamji-platform`: `kkamji-platform-api` <-> `kkamji-platform-db-1` upgraded transparently to HBONE mTLS. Ingress `NetworkPolicy` resources (`kkamji-platform-api`, `kkamji-platform-web`) allow non-ambient `Envoy Gateway` traffic on TCP `8080` and Istio Ambient host-probe SNAT traffic from `169.254.7.127/32` on TCP `8080`.
- **Intentionally excluded (`istio-cni` `excludeNamespaces` + strict policy boundaries)**:
  - System / infra / CI namespaces (`kube-system`, `istio-system`, `metallb-system`, `cilium-secrets`, `envoy-gateway-system`, `cert-manager`, `external-secrets`, `external-dns`, `cnpg-system`, `argocd`, `monitoring`, `security`, `arc-system`, `arc-runtime`, `ci-pr`, `ci-full`, `ci-cache`).
  - `keycloak` and `hindsight`: enforce strict port-scoped `NetworkPolicy`/`CiliumNetworkPolicy` contracts (`8080`/`5432`/`8888`) that intentionally do not open HBONE TCP `15008` or kubelet probe SNAT `169.254.7.127/32`. Enroll only after explicitly adding TCP `15008` and `169.254.7.127/32` rules to their policy contracts.

### NetworkPolicy requirement for Ambient-enrolled pods on Cilium

`istio-cni` installs an `ISTIO_POSTRT` SNAT rule on worker nodes that rewrites host kubelet health probes targeting Ambient pods to link-local source IP `169.254.7.127` so probes bypass in-pod `ztunnel` redirection. Cilium classifies `169.254.7.127` as a non-host identity, so any Ambient-enrolled pod governed by an Ingress `NetworkPolicy` or `CiliumNetworkPolicy` must explicitly allow TCP ingress from `169.254.7.127/32` on its probe port(s) (and TCP `15008` for HBONE pod-to-pod mTLS if pod-to-pod ingress is restricted).

Do not work around this with a cluster-wide empty-selector `CiliumClusterwideNetworkPolicy` (`endpointSelector: {}`), because selecting pods that have no Ingress policy enables default-deny for all other ingress on those pods. Always add `169.254.7.127/32` inside the pod's own `NetworkPolicy` or `CiliumNetworkPolicy`.

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
- If a pod ever loses in-pod `:15008` HBONE enrollment after an unclean node reboot (`Connection refused (os error 111)` on `:15008`), restart only the `istio-cni-node` pod on that worker (`kubectl delete pod <istio-cni-node-pod> -n istio-system --context kkamji-lab`) so it re-scans running pod netns and updates `ztunnel` without restarting stateful workloads.
