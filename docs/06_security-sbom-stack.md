---
title: Homelab security and SBOM stack
updated: 2026-11-29T01:00:00+09:00
type: architecture
status: current
---

# Homelab security and SBOM stack

## Architecture summary

`kkamji-lab` uses a hybrid security observability architecture:

- **Observability, SIEM, logs, and raw metrics** stay in the existing monitoring stack (`Prometheus`, `Alertmanager`, `Grafana`, `Loki`, `Alloy`, `Cilium Hubble`, `Envoy Gateway`).
- **Automated SBOM and vulnerability posture** is provided by `charts/trivy-operator` (v0.38.1 / app v0.36.1), generating Kubernetes-native CycloneDX `SbomReport`, `VulnerabilityReport`, `ExposedSecretReport`, `ConfigAuditReport`, and `RbacAssessmentReport` CRs with Prometheus metrics.
- **Lightweight eBPF runtime SIEM** is provided by `charts/tetragon` (v1.7.1) on worker nodes only, exporting JSON security events to container `stdout` so the existing `alloy` DaemonSet ships them to `loki`, alongside Prometheus metrics.
- **Security rules, ServiceMonitors, and dashboards** live in `charts/security-observability` (`security` namespace). Because Prometheus watches all namespaces for `release: kube-prometheus-stack` CRs and Grafana's dashboard sidecar watches `NAMESPACE=ALL` for `grafana_dashboard: "1"`, this chart leaves SHA-pinned `charts/kube-prometheus-stack` and `charts/cilium` untouched while restoring `hubble_*` metrics scraping.
- **Executive posture hub** lives in `platform.kkamji.net` (`/security` and Home `Systems`), receiving only compact sanitized KPI snapshots via `POST /api/ingest/security-posture` behind `PLATFORM_INGEST_TOKEN` (CronJob gated off by default until approved).

## Live resource audit and sizing (2026-11-22)

Read-only measurements on `kkamji-lab` (Kubernetes v1.36.1, Hyper-V VMs):

- `k8s-m1` (control-plane): 2.98 GiB allocatable, **2884 MiB (94%) used** (`kube-apiserver` 1735 MiB), 56 GiB root disk free. **No new workloads or DaemonSets may run on `k8s-m1`.** `charts/tetragon/kkamji_local_values.yaml` explicitly sets `tolerations: []` to override the upstream `operator: Exists` toleration.
- `k8s-w1` (worker): 14.77 GiB allocatable, 3970 MiB (26%) used, 4.72 GiB (31%) requested, 122 GiB root disk free.
- `k8s-w2` (worker): 14.77 GiB allocatable, 8042 MiB (53%) used, 10.82 GiB (73%) requested, 110 GiB root disk free.
- Existing PVCs: Prometheus TSDB uses **558 MiB** on a 30 GiB PVC (`retention: 1d`); Loki `storage-loki-0` (10 GiB PVC) stores **~23.4 MiB** compressed chunks under 24h retention (~180 MiB raw ingested), so extending `charts/loki/kkamji_local_values.yaml` to `168h` (7 days) keeps usage well under 1.5 GiB. On 2026-11-23, Loki requests/limits were right-sized (`singleBinary` 15m/480Mi req, 896Mi lim; `sidecar` 5m/112Mi req, 192Mi lim; `gateway` 5m/24Mi req, 64Mi lim) while preserving `168h` retention unchanged ([homelab resource optimization](07_homelab-resource-optimization.md)).

Estimated steady-state addition:

| Component | Placement | CPU req | Memory req / lim | Notes |
|---|---|---:|---:|---|
| `trivy-operator` | 1 worker pod | 50m | 150Mi / 512Mi | `scanJobsConcurrentLimit: 1`, `trivy.slow: true`, excludes `ci-pr,ci-full` |
| `tetragon` DaemonSet | `k8s-w1`, `k8s-w2` only | 2x 50m + 2x 10m | 2x (128Mi+32Mi) / 2x (384Mi+96Mi) | `tolerations: []` skips `k8s-m1`; audit-only `TracingPolicy` |
| `tetragon-operator` | 1 worker pod | 10m | 64Mi / 128Mi | Manages `TracingPolicy` CRDs |
| `security-observability` | CRs + ConfigMaps | 0m | 0Mi | Optional 5m CronJob (`enabled: false`) uses 20m / 32Mi ephemeral |

Total steady-state request addition is ~470 MiB (~1.0-1.4 GiB peak with one scan job), compared to 6-10+ GiB minimum for Dependency-Track v5 or 4-8 GiB for Wazuh/OpenSearch.

## Hubble metrics discovery fix

Live Prometheus audit found zero `hubble_*` series because `kube-system/hubble` ServiceMonitor lacked `release: kube-prometheus-stack`. `charts/security-observability/templates/servicemonitors.yaml` adds a labeled `ServiceMonitor` targeting `kube-system` (`k8s-app: hubble`, port `hubble-metrics`) and `monitoring` (`loki`, port `http-metrics`) without modifying SHA-pinned `charts/cilium`.

The Loki monitor excludes Services labeled `prometheus.io/service-monitor: "false"`. This skips the gateway and headless discovery paths while keeping the single-binary Loki metrics endpoint.

## Staged rollout and rollback

`charts/argo-applications/automation_local_values.yaml` manages the staged rollout for `security-observability`, `trivy-operator`, and `tetragon` under `project: management` (`namespace: security`) without modifying SHA-pinned `charts/argocd` or OIDC-coupled `management_local_values.yaml`. `charts/argo-applications/security_local_values.yaml` retains the offline reference template.

1. **Stage 1 (Observability + Loki 7d):** Merge Loki retention update and enable `security-observability` (`enabled: true`). Verify `hubble_drop_total` in Prometheus and 3 dashboards in Grafana folder `Security`.
2. **Stage 2 (SBOM Automation):** Enable `trivy-operator` (`enabled: true`). Verify `SbomReport` / `VulnerabilityReport` CRs and `trivy_image_vulnerabilities` metrics while checking worker RAM.
3. **Stage 3 (Runtime SIEM):** Enable `tetragon` (`enabled: true`). Verify exactly 2 DaemonSet pods (`k8s-w1`, `k8s-w2`; 0 on `k8s-m1`) and JSON logs in Loki (`{namespace="security", container="export-stdout"}`).
4. **Stage 4 (Platform Hub):** Deploy `kkamji-platform` `/security` image pin, verify `ClusterSecretStore/parameter-store` key `/kkamji/personal/kkamji-platform/app/ingest-token`, then enable `posturePublisher.enabled: true`.

Rollback for each stage is setting `enabled: false` (or reverting the Git commit) via GitOps. Audit-only `TracingPolicy` performs no `SIGKILL` enforcement, and no existing PVCs or Secrets are removed on rollback.

## Local validation

```bash
helm lint charts/trivy-operator -f charts/trivy-operator/kkamji_local_values.yaml
helm lint charts/tetragon -f charts/tetragon/kkamji_local_values.yaml
helm lint charts/security-observability -f charts/security-observability/kkamji_local_values.yaml
helm lint charts/loki -f charts/loki/kkamji_local_values.yaml
python3 -m unittest tests/test_security_sbom_charts.py
python3 docs/_meta/docs_lint.py --root . --base origin/main
```
