---
title: 플랫폼 자원 요청 기준
updated: 2026-10-27T09:44:13+09:00
type: runbook
status: current
---

# 플랫폼 자원 요청 기준

## 범위와 근거

- 원 PR은 [#37](https://github.com/KKamJi98/helm-charts/pull/37)입니다. 2026-10-27의 실제 `kkamji-lab` 사용량으로 재검토했습니다. API server/node 버전은 v1.36.1, 검증 renderer는 Argo CD와 같은 Helm 4.2.1입니다.
- 24시간 `container_memory_working_set_bytes`의 p95/max와 5분 CPU rate의 24시간 p95를 조회했습니다. 전체 관측 구간의 측정이며 미래 최대 부하나 재시작 순간의 상한을 증명하지 않습니다.
- 로컬 증적은 `/home/kkamji/.hermes/task-artifacts/personal-open-pr-resolution-20261027/`의 metrics, render diff, server dry-run과 request headroom 기록입니다. Secret 값은 조회하지 않으며 렌더된 Secret 객체는 기록하지 않습니다.

## 적용 값

CPU는 millicore, 메모리는 Mi 기준입니다. CPU limit은 추가하지 않습니다.

| 대상 | CPU request | 메모리 request | 관측 메모리 p95 / max |
|---|---:|---:|---:|
| Alloy | 10m | 320Mi | 최대 116.9 / 125.8Mi |
| Argo application controller | 100m | 1Gi | 673.9 / 772.5Mi |
| Argo repo server | 30m | 256Mi | 95.8 / 112.7Mi |
| Argo server | 10m | 64Mi | 38.5 / 48.0Mi |
| Argo applicationset / notifications | 각 10m | 각 64Mi | 24.3 / 24.7Mi, 32.5 / 34.7Mi |
| Argo Dex / Redis | 각 10m | 각 64Mi | 39.3 / 39.4Mi, 13.9 / 15.2Mi |
| istiod | 기존 500m 유지 | 256Mi | 83.7 / 84.8Mi |
| Prometheus | 50m | 1Gi | 818.5 / 869.3Mi |
| Alertmanager | 10m | 기존 200Mi 유지 | 40.4 / 41.8Mi |
| Operator / kube-state-metrics | 각 10m | 각 96Mi | 62.6 / 63.5Mi, 48.4 / 48.7Mi |
| node exporter | 10m | 32Mi | 최대 22.8 / 23.7Mi |
| Loki / rules sidecar / gateway | 각 20m / 10m / 10m | 640Mi / 128Mi / 32Mi | 318.8 / 349.1Mi, 95.1 / 95.5Mi, 13.1 / 13.6Mi |

## 원안에서 제외하거나 보존한 항목

- Grafana의 live `storage` volume은 `emptyDir`입니다. Pod 교체로 사용자 SQLite 상태가 유실될 수 있으므로 본체와 dashboard/datasource sidecar의 resource 변경을 제외했습니다. 기존 Pod template의 렌더 결과를 바이트 단위로 보존합니다. 영속화와 데이터 이관은 별도 데이터 안전 작업입니다.
- istiod CPU request는 500m을 유지합니다. live HPA는 CPU metric만 사용하며 80% 계산의 분모를 바꾸지 않습니다. 메모리 request만 기존 2Gi에서 256Mi로 조정합니다. sidecar proxy defaults와 HPA spec은 변경하지 않습니다.
- Prometheus/Alertmanager의 config-reloader와 init-config-reloader request는 이번 변경에서 제외했습니다. vendored operator의 해당 request/limit 인자는 0을 유지합니다. 예약 계산의 CR별 추가 20m/64Mi는 실제 설정값이 아니라 보수적 여유분입니다.
- Alertmanager의 기존 200Mi 예약은 줄이지 않습니다. 원안의 새 Prometheus 2Gi hard limit은 startup/WAL replay 검증 없이 도입하지 않습니다. request는 runtime 사용량의 hard cap이 아닙니다.

## 검증과 배포 경계

- 현재/candidate를 같은 release, namespace, Kubernetes capabilities와 Helm 4.2.1로 렌더합니다. 객체 identity 추가/제거, PVC, Secret, selector, Service, HPA와 route 변경은 허용하지 않습니다. istiod의 values ConfigMap은 resource 값의 직렬화 차이만 허용합니다.
- operator의 config-reloader request 인자와 init container request 변경을 별도로 확인합니다. 모든 변경 객체가 `kkamji-lab` server-side dry-run에 통과해야 합니다. 이 검사는 실제 apply가 아닙니다.
- 현재 모든 대상 인스턴스가 동시에 추가된다는 보수적 예약 합계는 메모리 5406.0Mi, CPU 930.0m입니다. 현재 worker의 미예약 자원보다 작음을 확인했습니다. 미래 CI 동시 실행을 보장하는 계산은 아니며 기존 shared5Gi/20Gi 정책, priority와 quota는 바꾸지 않습니다.
- main merge는 Argo CD 자동 배포 경계입니다. 변경 영향과 rollback을 확인한 뒤 수행하며 앱의 skip-reconcile 상태를 바꾸지 않습니다. 직접 helm install/upgrade, 강제 rollout과 PVC/Secret 삭제를 사용하지 않습니다.
- 배포 뒤 대상 앱 revision과 Synced/Healthy, rollout, 실제 requests, Grafana Pod UID 보존과 후속 reconcile을 확인합니다. 이상이 생기면 검증한 Git 역변경으로 이전 requests를 복구합니다. 영구 데이터와 Secret은 초기화하지 않습니다.
