---
title: Homelab Kubernetes resource and non-HA optimization
updated: 2026-11-27T11:55:00+09:00
type: runbook
status: current
---

# Homelab Kubernetes resource and non-HA optimization

Single-owner personal homelab (`kkamji-lab`, Hyper-V VMs, Kubernetes v1.36.1) resource right-sizing and non-HA topology optimization based on live read-only Prometheus 7-day telemetry collected on 2026-11-23.

This document extends [Platform resource baseline](04_resource-baseline.md) with:
- Aggressive CPU/Memory Request minimization backed by 7-day P95 and Max working-set measurements.
- Removal of production-style HA topologies that do not fit a personal 3-node homelab.
- Direct relief for `k8s-m1` control-plane memory pressure (95.7% allocatable RAM / 543.9 MiB 7d minimum `MemAvailable`).
- Strict preservation of SHA-pinned Keycloak/OIDC, Grafana PVC, and ARC CI contracts.

## 1. Live cluster audit findings (2026-11-23)

Read-only snapshot via `kubectl --context kkamji-lab` and Prometheus `/api/v1/query` over `[7d]`:

| Node | Role | CPU Alloc | CPU Req (Live) | Mem Cap / Alloc | Mem Req | Live Node RAM | 7d Min MemAvail |
|---|---|---:|---:|---:|---:|---:|---:|
| `k8s-m1` | control-plane | 1400m | 680m / 48.6% (130m live) | 3915Mi / 3047Mi | 112Mi (3.7%) | 2915Mi (95.7%) | 543.9Mi |
| `k8s-w1` | worker | 7400m | 1515m / 20.5% (187m live) | 15991Mi / 15123Mi | 5081Mi (33.6%) | 4775Mi (31.6%) | 10224.7Mi |
| `k8s-w2` | worker | 7400m | 4035m / 54.5% (201m live) | 15991Mi / 15123Mi | 11009Mi (72.8%) | 8571Mi (56.7%) | 7060.2Mi |
| Total | 3 nodes | 16200m | 6230m / 38.5% (518m live) | 35897Mi / 33293Mi | 16201Mi (48.7%) | 16261Mi | - |

Key structural root causes observed:

1. **`k8s-m1` 95.7% RAM root cause**:
   - `kube-apiserver-k8s-m1` consumes 1928 MiB RSS live (2058.6 MiB P95, 2321.8 MiB 7d Max), representing 72% of all pod memory on `k8s-m1`. Go live heap is 822.0 MiB (`heap_inuse` 1300.6 MiB, `go_sys` 2424.5 MiB) with default `GOGC=100` and no `GOMEMLIMIT` across 122 CRDs (including 14 unused Istio CRDs).
   - `metallb-speaker` runs on `k8s-m1` with 4 containers (`speaker`, `frr`, `frr-metrics`, `reloader`, 115.1 MiB live) even though `k8s-m1` carries `node.kubernetes.io/exclude-from-external-load-balancers` and MetalLB only uses `L2Advertisement` (zero `BGPPeer` objects).
   - `cilium-operator` defaults to 2 HA replicas with control-plane toleration and pod anti-affinity, forcing a standby replica (47.4 MiB live) onto `k8s-m1`. `cilium.debug.enabled=true` and `cilium.bgpControlPlane.enabled=true` add unnecessary overhead across all 3 nodes.
   - `coredns` (2 replicas via `dns-autoscaler` `min: 2`) places 1 CoreDNS pod (38.2 MiB) plus `dns-autoscaler` (18.8 MiB) on `k8s-m1` (57.0 MiB total).
2. **Cluster CPU request bloat (12x live usage)**:
   - Actual live CPU across 78 pods is 518m (3.2%), while CPU Requests reserve 6230m (38.5%). On `k8s-w2`, 4035m (54.5%) CPU and 11009Mi (72.8%) Memory Requests constrain scheduling of 7Gi `binance-quant-lab-full` CI runners.
3. **Unused or HA-oversized workloads**:
   - `istio-system/istiod`: zero `istio-injection` namespaces, zero `istio-proxy` sidecars, zero Istio routing/security CRs; still reserves 500m CPU / 256Mi RAM with an idle HPA (`min: 1, max: 5`) and 14 CRDs.
   - `argocd-dex-server` (no `dex.config` in `argocd-cm`; planned Keycloak SSO uses Argo CD native OIDC) and `argocd-applicationset-controller` (zero `ApplicationSet` CRs).
   - `keycloak-db` CNPG cluster runs 3 HA replicas (750m CPU / 3072Mi RAM requested, 30Gi PVC, 2 HA PDBs) despite 7d Max of 114-164Mi per pod and 10-19m CPU.
   - Retired namespaces (`litellm`, `openclaw`, `play-hub`, `hindsight-dot`) already have zero running pods (only residual ConfigMaps remain).
   - `cilium-envoy` MUST stay enabled cluster-wide because `envoy-gateway-system/keycloak-admin-private-prometheus-ingress` enforces a Cilium L7 HTTP rule (`GET ^/stats/prometheus$`).

## 2. Three-tier optimization matrix

### Tier 1 + Tier 2 (Implemented in this GitOps branch)

All changes below are verified with Helm `v4.2.1+gd591a19`, preserve all security policies (CiliumNetworkPolicy, NetworkPolicy, TLS, ESO, Auth), and keep SHA-pinned `kube-prometheus-stack`, `envoy-gateway`, `keycloak-idp`, `keycloak-operator`, and `arc-full` contracts intact.

| Chart / Workload | 7d P95 / Max (CPU, Mem) | Before (Req / Lim / Replicas) | After (Req / Lim / Replicas) | Effect |
|---|---|---|---|---|
| `metallb` speaker | 6.0m / 6.6m, 65.9Mi / 66.1Mi | BestEffort (0/0), 3 nodes + FRR (12 ctrs) | `10m/24Mi`, lim `160Mi`, 2 workers, `frr=false` (2 ctrs) | -1 pod (`k8s-m1`), -10 ctrs, -227Mi live RAM (-115Mi on `k8s-m1`) |
| `metallb` controller | 2.3m / 3.0m, 118.1Mi / 154.0Mi | BestEffort (0/0) | `5m/32Mi`, lim `256Mi` | Bounded Burstable |
| `cilium` operator | 5.9m / 6.5m, 127.0Mi / 132.1Mi | BestEffort (0/0), `replicas: 2`, m1 toleration | `10m/32Mi`, lim `256Mi`, `replicas: 1`, worker-only | -1 pod (`k8s-m1`), -47Mi live RAM on `k8s-m1` |
| `cilium` agent / config | 74.4m / 84.0m, 420.8Mi / 426.0Mi | `debug=true`, `bgpControlPlane=true`, `cni.exclusive=true`, `bpf.masquerade=true`, `installNoConntrackIptablesRules=true` | `debug=false`, `bgpControlPlane=false`, `cni.exclusive=false`, `socketLB.hostNamespaceOnly=true`, `bpf.masquerade=false`, `installNoConntrackIptablesRules=false` | Lower agent CPU/RAM churn + Cilium KPR compatibility with Istio Ambient (`istio-cni` chaining + `ztunnel` redirection) |
| `cilium` hubble-relay + ui | relay 72Mi, ui 77Mi + 15Mi max | BestEffort (0/0) | relay `5m/24Mi` (160Mi), ui `5m/24Mi` (160Mi) + `5m/16Mi` (64Mi) | Bounded Burstable |
| `argocd` dex-server | 0.2m / 0.5m, 20.2Mi / 20.3Mi | `10m/64Mi`, `enabled: true` | `enabled: false` | -1 pod, -10m/-64Mi req, -20Mi live RAM |
| `argocd` applicationSet | 1.5m / 1.9m, 126.6Mi / 128.9Mi | `10m/64Mi`, `replicas: 1` | `replicas: 0`, `5m/48Mi` (192Mi) | -1 pod, -10m/-64Mi req, -25Mi live (129Mi peak) |
| `argocd` app-controller | 65.5m / 106.7m, 757.8Mi / 859.6Mi | `100m/1024Mi`, no lim | `50m/640Mi`, lim `1280Mi` | -50m / -384Mi req |
| `argocd` repo-server | 13.1m / 29.0m, 156.8Mi / 169.7Mi | `30m/256Mi`, no lim | `15m/160Mi`, lim `384Mi` | -15m / -96Mi req |
| `argocd` server / redis / notif | max 142Mi / 39Mi / 136Mi | `10m/64Mi` each | `5m/64Mi` (256Mi), `5m/48Mi` (128Mi), `5m/128Mi` (256Mi) | -15m CPU, honest notif req + OOM limits |
| `istio-base` + `istio-istiod` (Ambient 1.31.4) | 3.5m / 4.2m, 145.7Mi / 148.1Mi | 1.28.2 (EOL), `500m/256Mi`, HPA 1-5, sidecar mode | 1.31.4 (K8s 1.37), `profile: ambient`, `10m/160Mi`, lim `320Mi`, `autoscaleEnabled: false` | -490m / -96Mi req, removes idle HPA, upgrades EOL 1.28.2 -> 1.31.4 Ambient |
| `istio-cni` + `istio-ztunnel` (Ambient 1.31.4) | New worker-only DaemonSets | Not deployed (sidecar mode) | `istio-cni`: `10m/32Mi` (lim `128Mi`), `ztunnel`: `10m/48Mi` (lim `192Mi`), worker-only (`tolerations: []`, control-plane excluded) | Enables sidecarless L4 mTLS on `k8s-w1`/`k8s-w2` with 0 bytes on `k8s-m1` (+40m / +160Mi req total across 2 workers) |
| `metrics-server` | 4.7m / 5.5m, 84.2Mi / 84.6Mi | `100m/200Mi`, no lim | `10m/96Mi`, lim `192Mi` | -90m / -104Mi req |
| `loki` (binary / rules / gw) | max 506Mi / 105Mi / 15Mi | `20m/640Mi`, `10m/128Mi`, `10m/32Mi` | `15m/480Mi` (896Mi), `5m/112Mi` (192Mi), `5m/24Mi` (64Mi) | -15m / -184Mi req, keeps 168h retention |
| `alloy` (2 workers) | max 14.3m / 294.5Mi, rel 41.5Mi | `10m/320Mi` + `10m/50Mi`, reporting on | `10m/288Mi` (512Mi) + `5m/48Mi` (96Mi), `enableReporting: false` | -10m / -68Mi req across 2 workers |
| `hindsight` api | 75.4m / 153.6m, 2001Mi / 2063Mi | `1000m/2Gi`, lim `2/6Gi` | `150m/2Gi`, lim `2/4Gi` | -850m CPU req, -2Gi Mem lim (keeps 2Gi req) |
| `hindsight` control-plane | 0.4m / 1.1m, 71.9Mi / 75.1Mi | `100m/256Mi`, lim `1/1Gi` | `10m/96Mi`, lim `500m/256Mi` | -90m / -160Mi req, -768Mi Mem lim |
| `ci-cache` (zot) | 6.0m / 6.5m, 372.5Mi / 504.6Mi | `100m/256Mi`, lim `1/1Gi` | `15m/256Mi`, lim `1/1Gi` (keeps 30Gi/31Gi store) | -85m CPU req |
| `arc-controller` | 1.6m / 2.0m, 58.4Mi / 62.0Mi | `100m/128Mi`, lim `500m/256Mi` | `10m/64Mi`, lim `250m/192Mi` | -90m / -64Mi req |
| `arc-light` / `arc-bql-light` / `terraform-lab` listeners (3) | max 0.4m, 18.7-30.1Mi | `50m/64Mi` each, lim `250m/128Mi` | `5m/32Mi` each, lim `100m/96Mi` | -135m / -96Mi req |
| `arc-runtime` (2 workers) | 0.7m / 0.8m, 18.4Mi / 19.6Mi | `50m/64Mi`, lim `200m/128Mi` | `5m/24Mi`, lim `100m/64Mi` | -90m / -80Mi req |
| `cert-manager` (3 pods) | max 95Mi / 122Mi / 71Mi | BestEffort (0/0) | `5m/32Mi` (192Mi), `5m/32Mi` (256Mi), `5m/24Mi` (160Mi) | Bounded Burstable |
| `external-secrets` (3 pods) | max 153Mi / 162Mi / 140Mi | BestEffort (0/0) | `5m/32Mi` (256Mi) each | Bounded Burstable |
| `external-dns` | max 1.6m / 115.2Mi | BestEffort (0/0) | `5m/32Mi` (256Mi) | Bounded Burstable |

### Tier 2B (Outside `helm-charts`: Kubespray `k8s-m1` control-plane relief)

1. **`kube-apiserver` Go memory cap (`GOMEMLIMIT=1400MiB`)**:
   - Add `GOMEMLIMIT=1400MiB` via kubespray `kube_kubeadm_apiserver_extra_envs` (or static pod env on `k8s-m1`). Live heap is 822 MiB, so a 1400 MiB soft cap triggers GC before RSS climbs to 2.0-2.3 GiB, saving ~500-850 MiB on `k8s-m1` without harming API responsiveness.
2. **Non-HA CoreDNS (`replicas: 2 -> 1`, worker-only) + disable `dns-autoscaler`**:
   - Removes `dns-autoscaler` (which enforces `min: 2`) and the `k8s-m1` CoreDNS pod, freeing 57 MiB live RAM and 120m/80Mi requests on `k8s-m1`.
3. **Hyper-V VM RAM upgrade during K8s 1.37**:
   - Raise `k8s-m1` VM RAM from 4 GiB to 6 GiB (allocatable ~5095 MiB) to eliminate structural headroom pressure permanently.

### Tier 3 (Owner-approved follow-up PRs: SHA-pinned contracts & external repos)

| Item | Target Repo / Contract | Est. Savings | Required Pre-Check / Gate |
|---|---|---|---|
| Keycloak CNPG `3 -> 1` + Keycloak/Operator right-sizing | `charts/keycloak-idp`, `charts/keycloak-operator`, `test_keycloak_*.py` | -1885m CPU req, -3970Mi RAM req, -200Mi live RAM, -2 pods, -20Gi PVC | Verify `keycloak-db-backup` S3 Barman backup green; update immutable Keycloak preparation/production test contracts; remove HA PDBs (`keycloak-db`, `keycloak-db-primary`). |
| Full Istio retirement (`istio-istiod` + `istio-base` `enabled: false`) | `charts/argo-applications/management_local_values.yaml`, `charts/kube-prometheus-stack`, `test_keycloak_gitops_activation.py`, `test_keycloak_private_admin.py` | -10m CPU req, -160Mi RAM req, -148Mi live RAM, -14 CRDs on `k8s-m1` | Update management-root app count/digest tests; delete 14 `*.istio.io` CRDs and remove `istiod`/`envoy-stats` scrape jobs. |
| Envoy Gateway `kkamji` `EnvoyProxy` + controller right-sizing | `charts/envoy-gateway`, `test_keycloak_private_admin.py` | -165m CPU req, -448Mi RAM req | Attach `EnvoyProxy` (`concurrency: 1`, `20m/160Mi`, lim `384Mi`) to `Gateway/kkamji`; update public baseline hash in `test_keycloak_private_admin.py`. |
| Prometheus cardinality & Alertmanager tuning | `charts/kube-prometheus-stack`, `test_grafana_pvc_*.py`, `main9a.json` | -120Mi Alertmanager req; ~200-300Mi Prometheus RAM | Drop unused `apiserver` high-cardinality histogram buckets (40,843 of 114,922 series = 35.5%); re-baseline Grafana PVC goldens. |
| External app repos (`kkamji-platform`, `real-life-rpg`) | `KKamJi98/kkamji-platform`, `KKamJi98/real-life-rpg` | -185m CPU req, -672Mi RAM req | `kkamji-platform-api` uses 19.4Mi max vs 512Mi req (26x); `real-life-rpg` uses 33.7Mi max vs 256Mi req (7.6x). |
| Optional Hubble UI/Relay disable | `charts/cilium` | -158Mi live RAM, -2 pods | Only if `hubble.kkamji.net` UI is not needed; keep `hubble.metrics` enabled for `security-observability`. |

## 3. Cumulative impact summary

| Stage | Pods / Containers | Cluster CPU Req | Cluster Mem Req | `k8s-w2` CPU / Mem Req | `k8s-m1` Live Pod RAM (Node %) |
|---|---:|---:|---:|---:|---:|
| Baseline (2026-11-23) | 78 / 99 | 6230m (38.5%) | 16201Mi (48.7%) | 54.5% / 72.8% | 2560Mi (95.7%) |
| After Tier 1+2 (This Branch) | 74 / 86 (-4 / -13) | 4270m (26.4%, -31.5%) | 15181Mi (45.6%, -6.3%) | 29.3% / 68.9% | 2403Mi (~90.5%) |
| + Tier 2B `k8s-m1` Kubespray | 72 / 84 (-6 / -15) | 4150m (25.6%, -33.4%) | 15101Mi (45.4%, -6.8%) | 29.3% / 68.9% | ~1848Mi (~72.1%) |
| + Full Tier 3 (All Approved) | 70 / 82 (-8 / -17) | 1910m (11.8%, -69.3%) | 9891Mi (29.7%, -38.9%) | 10.3% / 47.8% | ~1848Mi (~43% @ 6GiB VM) |

## 4. Staged rollout, watchpoints, and rollback

### Recommended rollout order after PR review and merge to `main`

1. **Wave 1 (`k8s-m1` relief first)**: `metallb` -> verify `Gateway/kkamji` LB IP `10.0.1.100` stays reachable via L2 ARP on `k8s-w1`/`k8s-w2` and `metallb-speaker` terminates cleanly on `k8s-m1`. Then `cilium` -> verify single `cilium-operator` Ready on worker, `k8s-m1` operator terminated, and `hubble_drop_total` + `keycloak-admin-private-prometheus-ingress` L7 rule still pass.
2. **Wave 2 (Control plane & observability right-sizing)**: `argocd`, `istio-istiod`, `metrics-server`, `loki`, `alloy`, `cert-manager`, `external-secrets`, `external-dns`. Verify Argo CD UI/webhook sync, `kubectl top nodes`, Loki 7d log ingestion, and ExternalSecret Ready states.
3. **Wave 3 (Workloads & CI)**: `hindsight`, `ci-cache`, `arc-controller`, `arc-light`, `arc-bql-light`, `arc-runtime`. Verify Hindsight `/v1` + Moka recall tunnel, zot pull-through mirror, and ARC listeners online.

### OOM watchpoints (24-72h post-merge)

- `argocd-application-controller-0` (limit `1280Mi` vs 7d max `859.6Mi`): monitor during full repo refresh spikes.
- `loki-0` (limit `896Mi` vs 7d max `505.7Mi`): monitor after 7d retention chunk growth.
- `hindsight-api-0` (limit `4Gi` vs 7d max `2063Mi`): monitor during concurrent `retain` batches (`llmMaxConcurrent: 4`).
- `external-secrets` / `cert-manager` controllers (limits `192-256Mi` vs 7d max `95-162Mi`): watch `kube_pod_container_status_restarts_total`.

### Rollback

GitOps rollback is reverting the merge commit on `main` (or reverting individual `charts/<chart>/kkamji_local_values.yaml` files) and letting Argo CD self-sync converge. No PVCs, CNPG clusters, Secrets, or CRDs are deleted by Tier 1+2 changes.

## 5. Rollout execution log

- **Wave 1 (`fafd095`, 2026-11-23 03:03 KST)**: Deployed non-HA `metallb` (worker-only speaker, FRR disabled) and `cilium` (single worker-only operator, `debug=false`, `bgpControlPlane=false`, Istio Ambient CNI compatibility `cni.exclusive=false`, `socketLB.hostNamespaceOnly=true`, `bpf.masquerade=false`, `installNoConntrackIptablesRules=false`), rolled `ds/cilium` across all 3 nodes, verified `metallb` and `cilium` `Synced/Healthy` with `k8s-m1` live RAM down from 87% (2678Mi) to 75% (2295Mi) and `https://argocd.kkamji.net` returning HTTP/2 200.
- **Wave 2 (`31a73ae`, 2026-11-23 03:08 KST)**: Upgraded Istio `1.28.2 -> 1.31.4` Ambient Mode (`istio-base`, `istio-istiod`, worker-only `istio-cni` and `istio-ztunnel` verified 2/2 Running on `k8s-w1`/`k8s-w2`, 0 on `k8s-m1`, CNI chained cleanly in `/etc/cni/net.d/05-cilium.conflist`, ztunnel WDS/XDS ready) and applied right-sizing to `argocd` (Dex removed, ApplicationSet 0 replicas), `metrics-server`, `loki`, `alloy`, `cert-manager`, `external-secrets`, and `external-dns`. All 34/34 Argo CD Applications converged `Synced/Healthy`.
- **Wave 3 (`7c67382`, 2026-11-23 03:11 KST)**: Deployed workload and CI right-sizing (`hindsight`, `ci-cache`, `arc-controller`, `arc-light` both value files, `arc-bql-light`, `arc-runtime`) with `tests/test_homelab_resource_optimization.py`. All 34/34 Argo CD Applications converged `Synced/Healthy` and GitHub Actions CI passed.
- **Wave 4 (`k8s-m1` Kubespray/control-plane, 2026-11-23 03:13 KST)**: Removed `kube-system/dns-autoscaler`, scaled `deploy/coredns` to 1 worker-only replica, applied `GOMEMLIMIT=1400MiB` to `kube-apiserver-k8s-m1` with persistent `/etc/kubernetes/patches/kube-apiserver0+strategic.yaml`, and synced Kubespray inventory `k8s-cluster.yml`.
- **16.5h Post-Rollout Verification (2026-11-23 19:53 KST)**: 0 OOMKilled events and 0 unexpected restarts across all 34 Applications; `kube-apiserver` RSS held steadily at `1405 MiB` (`1574 MiB` OS `available` on `k8s-m1`, vs `543.9 MiB` 7d min before).
- **Tier 3 + Cleanup (2026-11-23 20:08 KST, owner-approved)**:
  - Deleted retired empty namespaces (`litellm`, `openclaw`, `play-hub`).
  - External app repos right-sized: `KKamJi98/kkamji-platform` (`7b6d3eb`, `-125m / -472Mi` req across `api`/`search`/`web`/`git-sync`) and `KKamJi98/real-life-rpg` (`0b16b9a`, `-85m / -192Mi` app req + `-40m / -64Mi` scheduler req).
  - `helm-charts` Tier 3: `envoy-gateway` controller (`10m/96Mi`, lim `384Mi`) + public `EnvoyProxy/kkamji-public` (`concurrency: 1`, `20m/192Mi`, lim `384Mi`, preserving PR #117 Backend API and query-stripped access log privacy), `kube-prometheus-stack` Alertmanager (`5m/80Mi`, lim `192Mi`) + Prometheus (`25m/768Mi`, lim `1536Mi`) + `kubeApiServer` unused histogram bucket drop (`~27.8k` series), and Keycloak production profile (`keycloak-idp` CNPG `instances: 3 -> 1`, DB `25m/256Mi` lim `1/512Mi`, server `50m/768Mi` lim `1500m/1536Mi`, `keycloak-operator` `10m/256Mi` lim `500m/450Mi`; S3 Barman backup and all security/TLS contracts preserved). Hubble UI remains enabled.
- **Istio Sidecar -> Ambient Full Cutover (2026-11-23 20:54 KST)**: See [Istio 1.31.4 Ambient Mode mesh architecture and operations](08_istio-ambient-mesh.md). Removed legacy sidecar `global.proxy` and Prometheus `envoy-stats` scrape job, added `istio-cni` `excludeNamespaces` and `neverInjectSelector` guards, and declaratively enrolled `real-life-rpg` and `kkamji-platform` via `istio.io/dataplane-mode: ambient` in `charts/argo-applications/personal_local_values.yaml`.
- **Istio CNI Reboot Hardening (2026-11-25 15:40 KST)**: Enabled `istioOwnedCNIConfig: true` (`02-istio-cni.conflist` chained from `cniConfFileName: 05-cilium.conflist`) in `charts/istio-cni/kkamji_local_values.yaml` to prevent Cilium startup conflist overwrite from dropping `istio-cni` out of the chain on worker node reboots (`istio/istio#60882`), keeping existing `istio-cni` resource requests/limits (`10m/32Mi`, lim `128Mi`) unchanged.
- **Cilium Default-Deny Alignment (2026-11-27 11:55 KST)**: Updated `arc-runtime/runtime-no-network` (and `ci-full/full-default-deny`) from `ingress: []` / `egress: []` to Cilium 1.19 valid `ingress: [{}]` / `egress: [{}]` so `Valid: True` default-deny enforcement is active without changing `arc-runtime` DaemonSet resources or probes.
