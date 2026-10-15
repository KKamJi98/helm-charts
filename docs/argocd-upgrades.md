---
title: Argo CD upgrades
updated: 2026-10-15
type: runbook
status: current
---

# Argo CD upgrades

## 정본과 작업 위치

- 정본은 `charts/argocd/Chart.yaml`, `Chart.lock`, `charts/*.tgz`, `kkamji_local_values.yaml`입니다.
- upstream `argo-cd` dependency의 alias는 `argocd`입니다. override는 `argocd.*` 아래에 둡니다.
- 로컬 저장소 컨테이너는 `~/code/helm-charts`입니다. `.bare`는 Git storage, `main`은 운영 기준 worktree, `<branch>`는 격리 작업 worktree입니다.
- 운영 중 `helm install/upgrade/rollback`이나 install.yaml 직접 적용을 사용하지 않습니다. 검증한 변경을 main에 반영하면 Argo CD가 자동 동기화합니다. main push가 배포 경계입니다.

## 현재 버전과 호환성 결정

- upstream chart `10.10.5`, app `v3.5.5`를 고정합니다. umbrella 자체의 version은 `0.1.0`입니다.
- Rollouts UI 확장은 `v0.4.0`입니다. Argo CD 3.5의 React 19에 맞춰 react-dom 및 react/jsx-runtime을 외부화한 릴리스입니다.
- chart 10은 NetworkPolicy 생성을 기본 활성화합니다. 이번 변경은 기존 네트워크 동작 보존을 위해 `argocd.global.networkPolicy.create=false`를 명시합니다. 정책 활성화는 별도 검증 대상으로 둡니다.
- upstream 기본 Redis `8.6.4-alpine`, Dex `v2.46.0`, extension installer `v1.1.0`을 사용합니다. Redis HA, replica 수, PVC, Secret 소유권은 변경하지 않습니다.
- Argo CD 3.5는 Helm 4를 사용합니다. `spec.source.helm.version=v3`로 구 renderer를 유지할 수 없습니다. 검증 renderer는 release에 고정된 Helm `4.2.1`입니다.
- HTTP OCI를 사용하면 Helm 4의 plain-http 등록 규칙을 검토해야 합니다. Kubernetes v1.36은 Argo CD 3.5의 공식 테스트 범위에 있습니다.

## 검증 순서

1. `kkamji-lab` context와 `argocd` namespace를 명시하고 source revision, 앱 상태, workload images/readiness, CRD storedVersions, ESO 상태를 기록합니다. `argocd.argoproj.io/skip-reconcile=true` 앱은 사전 목록을 보존합니다. Secret 값은 조회하지 않습니다.
2. 작업 worktree에서 dependency pin과 vendor/lock을 함께 갱신합니다. 공식 chart index digest와 다운로드한 패키지 SHA-256을 비교합니다. 변경하지 않은 argo-projects 패키지의 bytes는 보존합니다.
3. 같은 release/namespace/Kubernetes API capabilities/values로 기존과 후보를 렌더합니다. Secret 데이터는 출력하거나 증거에 저장하지 않습니다. 객체 제거, 중복 identity, immutable selector, Service/route, PVC, AppProject/root Application, ESO target/ownership 변경을 검사합니다.
4. CRD를 먼저 server-side dry-run하고 나머지 비밀이 아닌 리소스를 검증합니다. 기존 hook Job은 before-hook-creation 재생성 정책을 따릅니다. dry-run의 field-manager label 충돌과 실제 schema/immutable 오류를 구분합니다. force-conflicts를 쓴 dry-run은 실제 ownership 변경이 아닙니다.
5. 배포된 revision 및 실제 values로 관리 중인 Helm 앱들을 Helm 4.2.1에서 렌더합니다. 다른 저장소의 dirty checkout을 수정하거나 pull하지 않습니다.
6. 영향 요약 후 검증한 commit만 main에 반영하고 push합니다. Argo CD의 CRD 우선 적용 및 workload rollout을 관찰합니다. 실패 시 임의의 Secret 초기화/CRD 삭제/강제 rollout을 하지 않습니다.
7. 새 revision의 Synced/Healthy, 최종 image 및 init container 완료, CRD Established/storedVersions, ESO Ready, HTTPS UI/health/version, 확장 JS를 확인합니다. 활성 앱은 이후 정규 reconciliation의 timestamp 진행과 정상 상태를 확인합니다. 기존 skip-reconcile 앱은 재개하지 않으며 과거 Healthy 상태를 최신 runtime 검증으로 세지 않습니다. 실제 인증을 수행하지 않았으면 로그인/SSO 검증으로 표현하지 않습니다.

## 적용 결과

- release commit `c380fa5229575061000d34582853d489fa188e6d`를 main에 push한 뒤 Argo CD self-sync가 Succeeded로 완료되었습니다.
- 2026-10-15 19:51 KST 확인: 제어면 workload 7개 ready, 활성 앱 19개 Synced/Healthy 및 후속 정규 reconciliation 진행, CRD 3개 Established=True/storedVersions=[v1alpha1], ESO 4개 Ready=True입니다.
- kiali-operator, n8n, real-life-rpg는 배포 전부터 skip-reconcile=true였습니다. 중단 상태와 과거 status를 보존했으며 재개하거나 runtime 재검증 완료로 표현하지 않습니다.
- HTTPS의 UI/health/version/확장 JS가 HTTP 200이었고 version API는 v3.5.5였습니다. 제공된 확장 JS의 host ReactDOM 사용과 구 ReactDOM bundle 부재를 확인했습니다. 실제 사용자 로그인/SSO와 인증 후 Rollouts 화면 조작은 검증하지 않았습니다.

## 이번 후보의 preflight 근거

- 기존/후보 렌더 모두 66개 객체이며 객체 추가/제거는 없습니다. 13개 workload/Service selector와 AppProject/root Application, ESO, HTTPRoute spec은 동일합니다.
- RBAC rules 변경은 없으며 NetworkPolicy/PVC/Ingress 추가도 없습니다. CRD 3개의 served/storage 버전은 v1alpha1로 유지됩니다.
- Certificate 변경은 Secret template의 식별 label 추가입니다. issuer, DNS names, privateKey algorithm/encoding/rotationPolicy/size는 동일합니다.
- chart lint, 공식 archive checksum, 배포된 앱 22개의 Helm 4 렌더를 확인했습니다. CRD dry-run과 나머지 61개 비밀이 아닌 일반 객체의 server-side dry-run도 통과했습니다.
- 최초 runtime dry-run에서 RBAC 객체 2개의 chart/version label ownership 충돌이 있었습니다. schema/rules 변경 오류는 아니며, 강제 충돌 해결을 사용하는 dry-run에서 61개 모두 승인되었습니다. live field ownership은 이 검사로 변경하지 않았습니다.
- 확장 v0.4.0의 릴리스 asset digest를 확인했습니다. source externals 및 릴리스 JS의 host ReactDOM 사용도 확인했습니다. 사용하지 않는 JSX runtime은 최적화로 번들에 문자열이 없을 수 있으므로 문자열 부재만으로 실패를 단정하지 않습니다.

## 백업과 롤백

- 변경 전 revision은 `5674034790d131fedec46357d6901c6178fc86fd`이며 chart `9.5.19` / app `v3.4.3`입니다. 해당 Git 객체와 기존 vendor가 rollback source입니다.
- 배포 전 Secret을 제외한 workload/config/Argo CR/CRD snapshot을 task evidence에 보존합니다. 이는 전체 재해복구 백업이 아닙니다. Secret export/import나 restore drill은 이번 업그레이드의 검증으로 주장하지 않습니다.
- admin-password/webhook의 ESO Merge와 notifications/GitHub App의 Owner 정책을 유지합니다. Secret 재생성, SSM 값 변경, PVC/CRD 삭제는 수행하지 않습니다. Redis는 영구 데이터 저장소가 아니라 재생성 가능한 cache입니다.
- controller/repo/server의 지속 기동 실패, ComparisonError, repository 인증/Redis auth/RBAC 오류, UI/route 장애가 있으면 검증한 Git 역변경으로 기존 workload와 설정을 복원합니다. auto selfHeal을 우회하는 수동 image patch나 helm rollback은 일반 경로가 아닙니다.
- 새 CRD field/저장 형식을 사용했다면 schema까지 단순 역변경하지 않습니다. 새 CRD 보존과 구 controller 호환성을 먼저 검토합니다. Argo 제어면이 중단되면 명시적 복구 작업과 추가 위험 검토가 필요합니다.

## 공식 출처

- [Argo CD v3.5.5](https://github.com/argoproj/argo-cd/releases/tag/v3.5.5)
- [argo-helm argo-cd 10.10.5](https://github.com/argoproj/argo-helm/releases/tag/argo-cd-10.10.5)
- [Chart major 변경](https://github.com/argoproj/argo-helm/blob/argo-cd-10.10.5/charts/argo-cd/README.md#1000)
- [Argo CD 3.4 -> 3.5](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/operator-manual/upgrading/3.4-3.5.md)
- [React 19 확장](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/operator-manual/upgrading/ui-extensions-react-19-upgrading.md)
- [Rollouts 확장 v0.4.0](https://github.com/argoproj-labs/rollout-extension/releases/tag/v0.4.0)
- [Argo CD disaster recovery](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/operator-manual/disaster_recovery.md)
