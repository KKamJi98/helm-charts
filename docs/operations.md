---
title: Makefile operations
updated: 2026-10-29T19:34:10+09:00
type: runbook
status: current
---

# Makefile operations

명령과 기본 변수의 정본입니다. target을 바꾸면 이 문서도 같은 변경에서 갱신합니다. 저장소 개요는 [README](../README.md), 버전/renderer와 업그레이드는 [Argo CD upgrades](argocd-upgrades.md)를 따릅니다.

## Command boundaries

Makefile의 kubectl 명령은 현재 context를 사용합니다. 클러스터를 읽거나 바꾸기 전에 `kubectl config current-context`가 승인된 개인 홈랩 `kkamji-lab`인지 확인합니다. namespace도 확인합니다. 다른 context에서 일단 실행해 보는 방식은 사용하지 않습니다.

| 작업 | 명령 | 영향과 한계 |
|---|---|---|
| 도움말 | `make help` | 로컬 target과 변수 안내 |
| 의존성 갱신 | `make deps` | 로컬 umbrella lock/vendor 변경과 네트워크 접근 |
| 최초 설정 | `make setup` | deps 후 bootstrap. 실제 클러스터 변경 |
| 최초 apply | `make bootstrap` | namespace 생성/apply와 umbrella SSA |
| render preview | `make template` | 앞 100줄만 표시. 전체 검증 대체 아님 |
| 전체 lint 편의 기능 | `make lint` | 개별 chart 실패를 무시하며 local override도 자동 전달하지 않음 |
| AppProject/Application 현황 | `make status` | `scripts/status.sh`의 클러스터 조회 |
| root hard refresh | `make refresh` | Application annotation 변경 |
| Argo CD 구성 유실 복구 | `make recover-secrets` | bootstrap 후 namespace 내 Deployment/StatefulSet 재시작 |
| AppProject 삭제 대기 해소 | `make unstick-projects` | finalizer 제거와 refresh. 삭제 영향 검토 필요 |
| stale Helm manager 진단 | `make detect-helm-ownership` | Secret 객체도 조회하므로 값 접근이 금지된 세션에서는 실행하지 않음 |

기본 변수는 `RELEASE=argocd`, `NAMESPACE=argocd`, `UMBRELLA_CHART=charts/argocd`, `VALUES=charts/argocd/kkamji_local_values.yaml`, `FIELD_MANAGER=argocd-controller`입니다. 변수 변경은 대상과 리소스 identity를 바꿀 수 있습니다.

## Bootstrap

이 저장소 밖에서 kubeadm 클러스터와 CNI가 준비되어 있어야 합니다. GitHub App 기반 저장소 접근, SSM SecureString/ESO와 SecretStore, 인증서 및 라우팅 의존성도 확인합니다. `make setup`이 이 선행 조건을 모두 구축해 주지는 않습니다.

1. 대상 context, namespace, 권한과 bootstrap 범위를 확인합니다. 기존 클러스터 복구라면 현재 리소스 소유권과 백업을 먼저 확인합니다.
2. [버전/renderer 기준](argocd-upgrades.md)에 맞춰 chart와 values를 lint/render하고 변경 영향을 검토합니다. 의존성 갱신과 그 diff도 검토 대상입니다.
3. 승인된 신규 환경에서만 `make setup`을 실행합니다. 구현은 `make deps` 후 `make bootstrap`입니다. 이미 검증한 vendor를 사용하는 경우의 bootstrap 범위는 별도로 결정합니다.
4. bootstrap은 namespace를 apply하고, Helm render를 `kubectl apply --server-side --field-manager=argocd-controller --force-conflicts`로 전달합니다. 강제 field ownership 조정이 포함되므로 단순 조회나 무해한 재실행으로 취급하지 않습니다.
5. Argo CD, AppProject, root/자식 Application, 저장소 접근과 ESO 상태를 확인합니다. 이후 일상 반영은 GitOps로 진행합니다.

운영 중 `helm install/upgrade/rollback`으로 별도 release manager를 추가하지 않습니다. [부트스트랩 정책](../AGENTS.md)과 [업그레이드 runbook](argocd-upgrades.md)의 field ownership/복구 원칙을 따릅니다.

## Validation

차트가 바뀌면 해당 chart의 local values를 명시합니다. 아래는 umbrella에 대한 전체 lint/render 예시입니다. 먼저 Helm 버전이 [배포 renderer](argocd-upgrades.md)의 기준에 맞는지 확인합니다.

```bash
helm version --short
helm lint charts/argocd -f charts/argocd/kkamji_local_values.yaml
helm template argocd charts/argocd --namespace argocd \
  -f charts/argocd/kkamji_local_values.yaml > /dev/null
python3 docs/_meta/docs_lint.py --root . --base origin/main
```

render 출력을 버리는 이유는 Secret 값을 터미널이나 증거 파일에 남기지 않기 위해서입니다. 실제 객체 비교가 필요하면 Secret을 제외한 구조만 안전하게 비교합니다. render 성공은 API schema/admission, CNI 동작이나 workload 기동을 증명하지 않습니다.

`make template`의 preview와 `make lint`의 성공 종료를 전체 gate로 쓰지 않습니다. 현재 Makefile은 각각 출력 일부만 보여주고 개별 lint 실패를 무시합니다. 위의 직접 명령에서 실제 종료 코드를 확인합니다. dependency가 이미 제공된 경우 검증만을 위해 갱신하지 않습니다.

문서만 바꾸면 metadata, 상대 링크/anchor와 실제 소스 일치 여부를 검증합니다. `updated`는 본문을 변경한 실제 시각으로 갱신합니다. [coupling.json](_meta/coupling.json)에 연결된 코드가 바뀌면 해당 문서도 함께 바꿉니다.

PR 검사는 [docs-lint workflow](../.github/workflows/docs-lint.yml)와 같은 `--base origin/main` 모드를 사용합니다. freshness/coupling의 변경 목록은 `origin/main...HEAD`의 커밋 차이이므로 최종 커밋 후에도 실행합니다. 미커밋 초안에서의 통과만으로 이 두 검사를 검증했다고 보고하지 않습니다. 상대 링크의 파일 존재 검사는 README와 heading anchor까지 검사하지 않으므로 별도로 확인합니다.

## Envoy Gateway vendor 예외 검사

`make deps`는 1.8.1 원본을 다시 받아 CRD backport를 지울 수 있다. 의존성 갱신 뒤 `python3 scripts/patch_envoy_gateway_crd.py`로 승인된 두 줄 수정만 재적용하고 `--check`로 확인한다. 다른 버전이나 미확인 vendor를 자동 수정하지 않는다. 범위, upstream provenance, checksum, full Git history를 쓰는 테스트 및 제거 조건은 [공유 CRD backport](rules/gateway-api-routing.md#공유-crd의-181-한정-backport)를 따른다.

[Envoy Gateway CI](../.github/workflows/envoy-gateway-lint.yml)는 vendor/script/test/workflow 변경에 실행되며 check, local values를 명시한 Helm lint/render와 전체 렌더 회귀 테스트를 수행한다. 이 gate는 클러스터 admission이나 실제 429 검증을 대신하지 않는다. 테스트 전용 임시 파일은 `TMPDIR` 아래에 두며 render Secret 값은 기록하지 않는다.

## Normal changes

1. 최신 원격, 현재 branch와 사용자 미커밋 변경을 확인합니다. 별도 작업 worktree에서 필요한 파일만 수정합니다.
2. 대상별 검증과 diff를 검토합니다. 무관한 변경을 stage하거나 자동 stash/reset하지 않습니다.
3. 승인된 commit만 `main`에 반영합니다. 작업 branch의 push/PR과 `main` push에 따른 실제 자동 배포를 구분합니다.
4. 반영한 Git revision, root와 자식 Application의 sync/health, workload readiness 및 요청한 기능을 확인합니다. webhook은 감지 경로이지 배포 성공 증명이 아닙니다.
5. source의 `enabled`와 runtime의 중단 상태를 함께 확인합니다. `skip-reconcile` 앱은 승인 없이 재개하지 않습니다. 중단 앱의 과거 Healthy 상태를 새 revision 검증에 포함하지 않습니다.

다음은 Secret 값을 포함하지 않는 읽기 전용 상태 확인 예시입니다. 실행 전 context 확인 결과가 대상과 일치하는지 확인합니다.

```bash
kubectl config current-context
kubectl get applications --context kkamji-lab -n argocd \
  -o 'custom-columns=NAME:.metadata.name,REVISION:.status.sync.revision,SYNC:.status.sync.status,HEALTH:.status.health.status,PAUSED:.metadata.annotations.argocd\.argoproj\.io/skip-reconcile'
kubectl get deployments,statefulsets --context kkamji-lab -n argocd
kubectl get externalsecrets --context kkamji-lab -n argocd
```

`make status`는 빠른 요약입니다. 현재 스크립트는 revision과 중단 annotation을 표시하지 않으므로 위 조회나 Argo CD 화면에서 별도로 확인합니다. `Synced/Healthy`만으로 실제 서비스 요청의 성공을 판정하지 않습니다.

## Recovery

복구 전 대상, blast radius, 마지막 정상 revision, 데이터/Secret의 복원 경로와 사후 확인을 정합니다. `main`에 반영한 Git 역변경도 자동 배포를 유발합니다. DB/PVC 데이터나 외부 Secret 값까지 되돌려 주지는 않습니다.

- 업그레이드 회귀는 [Git 기반 롤백과 CRD 호환성 절차](argocd-upgrades.md#백업과-롤백)를 따릅니다. 새 저장 형식을 사용한 CRD를 무조건 구 schema로 되돌리지 않습니다.
- `make recover-secrets`는 현재 Git 구성을 재apply하고 Argo CD namespace의 workload들을 재시작합니다. 외부 Secret 원본이나 데이터를 복구하는 명령이 아닙니다. 저장소/SSM/ESO 의존성과 소유권을 확인한 뒤 필요한 범위만 승인받습니다.
- `make unstick-projects`는 finalizer를 제거합니다. 삭제 중인 객체의 영향을 확인한 명시적 복구에서만 사용합니다. 기다리는 객체를 지우면 안전하다는 보장은 없습니다.
- ownership 충돌은 먼저 manager와 diff를 확인합니다. managedFields 삭제, 강제 replace, Namespace/Secret/PVC/CRD 삭제를 일괄 정리 절차로 실행하지 않습니다.
- Secret 삭제와 회전은 [ESO Owner/Retain 규칙](rules/external-secrets.md)을 확인합니다. Secret 값의 dump나 초기화는 일반 진단에 포함하지 않습니다.

## Troubleshooting

| 증상 | 읽기 전용으로 먼저 확인 | 다음 판단 |
|---|---|---|
| 변경 미반영/ComparisonError | 실제 source repo/revision/path/values, root와 자식의 diff/오류, 중단 annotation | branch 또는 renderer 문제와 중단 상태를 분리. 임의 refresh/apply로 우회하지 않음 |
| 저장소/ESO 인증 실패 | SecretStore/ExternalSecret 상태와 참조, 승인된 접근 권한 | [Secret 규칙](rules/external-secrets.md). 값은 조회하지 않음 |
| HTTP/TLS 장애 | Service와 route의 Accepted/ResolvedRefs, Gateway/listener와 인증서 참조 | [Gateway API 규칙](rules/gateway-api-routing.md). 구 nginx/passthrough 설정을 복사하지 않음 |
| chart 변경 후 기동 실패 | 버전 핀, Helm renderer, CRD served/storage 호환성, workload 이벤트 | [업그레이드 검증/롤백](argocd-upgrades.md) |
| 유실/삭제 대기/ownership 문제 | 소유자, finalizer, managedFields, 남은 데이터와 영향 | 위 Recovery 절차의 위험 경계를 확인한 뒤 필요한 조치만 승인 |

CI, render, sync/health는 서로 다른 증거입니다. 한 단계가 통과했다고 다른 단계를 성공으로 표시하지 않습니다.
