---
title: Makefile operations
updated: 2026-08-24
type: runbook
status: current
---

# Makefile operations

이 표와 변수 기본값은 `Makefile` 과 `scripts/` 의 실제 타깃을 반영한다. 타깃을 추가하거나
이름을 바꾸면 같은 PR 에서 여기도 고친다. CI 가 그것을 확인한다.

| 작업 | 명령 |
|---|---|
| 매니페스트 검증 (apply 없이) | `make template` |
| helm lint (`charts/*` 전체) | `make lint` |
| AppProject/Application 현황 | `make status` |
| root Application hard refresh | `make refresh` |
| `argocd-cm`/`argocd-secret` 유실 복구 | `make recover-secrets` |
| AppProject stuck(Pending deletion) 해소 | `make unstick-projects` |
| stale `manager=helm` 잔재 진단 | `make detect-helm-ownership` |

- Makefile 기본 변수: `RELEASE=argocd`, `NAMESPACE=argocd`, `UMBRELLA_CHART=charts/argocd`, `VALUES=charts/argocd/kkamji_local_values.yaml`, `FIELD_MANAGER=argocd-controller`.
- 단일 차트 부분 검증: `helm template <chart> -f charts/<chart>/kkamji_local_values.yaml --show-only templates/<file>`.

부트스트랩 정책과 `helm install/upgrade` 금지 근거는 `AGENTS.md` 의 부트스트랩 정책 절에 있다.
