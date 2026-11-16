---
title: Grafana native PVC activation candidate
updated: 2026-11-17T01:39:57+09:00
type: runbook
status: current
---

# Grafana native PVC activation candidate

## Current-main consumer integration boundary

부모가 인수한 Grafana native retained-PVC 전환을 현재 기준으로 유지합니다. 아래의
emptyDir/미배포/전환 전 승인 서술은 당시 준비 또는 PR86 제안의 역사적 기록이며,
현재 storage/data 인수를 다시 여는 조건이나 현재 운영 상태의 oracle가 아닙니다.
consumer 기본 인증은 계속 legacy이고, source의 SSO acknowledgement는 false입니다.
[consumer 계획](02_consumer-sso-plan.md)과 [owner 등록 절차](07_owner-enrollment-source.md)는
별도의 owner/MFA/UI 인수를 요구합니다. 이 leaf는 runtime/dataMigrationAccepted를 false로 유지합니다.

새 keycloakSSO 기본값은 additive입니다. 기존 default/preparation/activation의 고정
whole-object/raw/hash, crypto, sidecar, ownership guard는 그대로이며 defaults exact
검사만 새 legacy 필드를 명시합니다. 별도 current-main 회귀는 131/141 객체와
retained-PVC + synthetic canary/final 조합을 immutable 9a baseline으로 검사합니다.
mutable values 두 벌의 동등성으로 storage 검증을 대체하지 않습니다.

## Historical preparation and activation proposal

이하 절차와 관측 시제는 원래 제안 시점의 기록입니다.


## 오프라인 후보이며 배포 승인이 아님

이 branch의 `kkamji_local_values.yaml`은 이미 보존 선언된 PVC를 Grafana의 native `existingClaim`으로 연결하는 소스 후보입니다. **부모가 실제 target-volume copy, 격리 app/crypto recovery, 최종 write 정합성 window를 모두 인수하기 전에는 main 병합이나 운영 적용을 하지 않습니다.** leaf는 branch/PR 게시와 운영 변경을 수행하지 않습니다.

부모는 소스 검토와 비밀 검사를 마친 뒤 격리 branch와 Draft PR을 게시해 exact-head CI를 먼저 확인할 수 있습니다. 먼저 운영 Application이 해당 branch/PR이 아닌 `main`을 추적함을 확인합니다. 게시 뒤에도 원격 main revision과 실제 Grafana Pod/volume이 바뀌지 않았는지 대조합니다. Draft PR에는 auto-merge를 설정하지 않습니다. branch/PR 게시나 CI 통과를 운영 전환 또는 데이터 인수로 기록하지 않습니다. 이 구분은 CI를 기다리는 동안 원본 Grafana의 쓰기를 불필요하게 차단하지 않기 위한 것입니다.

부모 제공 공개 입력은 PVC `monitoring/kube-prometheus-stack-grafana`, UID `33f72766-1047-4af4-9e4c-5e7c2283463c`가 Bound 10Gi local-path이며 PV UID `f7882274-a3b4-4e63-9d3e-35aa3f45f7d3`가 `k8s-w1`에 종속된다고 설명합니다. binding consumer는 정리되었고 원본 Grafana Pod UID `5a498faf-c021-4c2e-b413-6b54ca177fce`는 Ready/emptyDir로 남아 있습니다. 이 입력의 실제 app data 복사와 persistence 활성화는 false입니다. leaf는 cluster, DB, archive, Secret이나 filesystem data를 읽지 않았으며 공개 상태를 새로 관측한 것으로 주장하지 않습니다.

[준비 profile](05_grafana-pvc-preparation.md)의 PVC 선언/spec/보존 annotation은 그대로입니다. 기본 chart values는 준비 flag false, upstream persistence disabled로 안전하게 남습니다. `dataReady`, `cutoverApproved` 같은 값이나 일반 activation framework는 없습니다. 소스가 렌더된다는 사실은 데이터 인수의 대체물이 아닙니다.

## 지원하는 native profile 하나

local의 관련 설정은 다음뿐입니다. Secret 값이나 Keycloak 설정을 추가하지 않습니다.

```yaml
grafanaPvcPreparation: true
kube-prometheus-stack:
  grafana:
    replicas: 1
    deploymentStrategy:
      type: Recreate
      rollingUpdate: null
    persistence:
      enabled: true
      type: pvc
      existingClaim: '{{ include "grafana.fullname" . }}'
      storageClassName: local-path
      accessModes:
        - ReadWriteOnce
      size: 10Gi
    initChownData:
      enabled: false
```

pinned kube-prometheus-stack `92.3.0` 안의 Grafana chart는 `13.5.0`, runtime은 `13.2.3-distroless`입니다. native `_pod.tpl`은 persistence enabled/type pvc일 때 `tpl (.Values.persistence.existingClaim | default (include "grafana.fullname" .)) .`를 사용합니다. 고정 helper 표현식이 wrapper PVC 선언과 동일한 실제 release 이름을 유도합니다. native `pvc.yaml`은 existingClaim이 있으면 별도 PVC를 생성하지 않습니다. vendor/helper를 수정하거나 Helm lint release를 우회하지 않습니다.

canonical release에서는 consumer와 선언 모두 `kube-prometheus-stack-grafana`입니다. `test-release` 등 다른 release의 검사에서는 그 release의 선언/consumer가 함께 바뀌고 canonical claim을 잘못 참조하지 않습니다. 이는 다른 release를 production claim에 adopt시키는 기능이 아닙니다. 임의 claim 문자열, custom tpl, fullname/namespace override와 추가 persistence key는 거부합니다.

kind는 Deployment, replicas는 1, autoscaling은 disabled, strategy는 Recreate입니다. RWO만으로 모든 Pod 동시 쓰기를 차단할 수 있다고 주장하지 않습니다. Recreate는 새 ReplicaSet 시작 전 기존 Pod를 종료하는 무중첩 rollout과 중단 시간을 의도합니다. 실제 old writer 종료와 copy window는 부모가 확인해야 합니다.

`rollingUpdate: null`은 이 후보의 고정 source 계약입니다. active guard는 정확히 `{type: Recreate, rollingUpdate: null}`만 허용하며, pinned native template의 `toYaml`과 실제 Helm 4.2.1 출력에 null key가 남는지 검사합니다. 준비/default의 RollingUpdate profile은 바꾸지 않습니다. 그러나 null 선언만으로 기존 API object의 map을 제거할 수 있다고 보지 않습니다.

부모의 실제 API 검증은 null 추가 뒤에도 기존 API-defaulted `rollingUpdate: {maxSurge: '25%', maxUnavailable: '25%'}`가 남아 `spec.strategy.rollingUpdate: Forbidden`으로 거부되었습니다. Argo CD `v3.5.5`의 `gitops-engine/pkg/utils/kube/resource_ops.go`에 있는 기존 SSA `ForceConflicts=serverSideApply` 동작까지 맞춘 dry-run도 같은 결과였습니다. 따라서 초기의 다른 옵션 검증과 정확한 기존 controller 모드 검증을 구분하고, 둘 다 실패 증거로 보존합니다. controller 정책이나 field manager를 바꾸어 성공으로 처리하지 않습니다.

### 기존 RollingUpdate object의 필수 전환 단계

이 절차는 source chart가 자동 실행하는 hook/Job이 아닙니다. 부모만 승인된 최종 데이터 보전 window에서 수행합니다. 단일 SSA가 거부되는 상태를 그대로 main에 병합하여 자동 전환이 완료될 것으로 기대하지 않습니다.

1. 아래 gate 1-4와 exact-head CI를 먼저 인수합니다. intended main revision, namespace/Deployment UID, 원본 writer와 마지막 snapshot/copy의 정합성을 확인합니다.
2. 기존 object가 위 RollingUpdate/default map 상태라면, 현재 UID와 resourceVersion 및 strategy 전체를 `test`하는 JSON Patch를 준비합니다. **같은 요청에서** `/spec/strategy/rollingUpdate`를 제거하고 `/spec/strategy/type`을 `Recreate`로 바꿉니다. native dry-run의 전체 spec diff는 strategy 두 경로뿐이어야 하며 Pod template은 같아야 합니다. 예상 상태가 다르면 임의 patch나 강제 적용을 하지 않고 다시 판단합니다.
3. 데이터 window를 유지하고 intended main revision을 확인한 뒤 부모가 전환 patch를 수행합니다. main이 여전히 이전 RollingUpdate 소스를 추적하면 self-heal이 되돌릴 수 있으므로, 임의 시점에 미리 실행하거나 설정이 영구 유지될 것으로 가정하지 않습니다. 이미 Recreate이고 rollingUpdate가 없다면 전환 patch를 생략하고 현재 상태를 검증합니다.
4. 전환 뒤 동일한 기존 `argocd-controller` SSA 경로로 이 source를 적용하고 gate 5의 실제 PVC/단일 writer/데이터/crypto/legacy 인증을 인수합니다. 이전 격리 복원이나 source 테스트가 이 실제 인수를 대신하지 않습니다.

부모는 같은 source Pod spec과 PVC 참조를 사용한 별도 이름/selector/labels의 replicas 0 fixture에서 전환 전 SSA 거부, 원자적 strategy 전환 뒤 SSA 성공과 허용 네 경로의 최종 diff를 확인했습니다. Pod는 생성하지 않았고 fixture의 Deployment/ReplicaSet/Pod는 정리했습니다. 운영 대상에서는 strategy 전환 patch의 dry-run과 원본 UID/readiness/PVC 보존만 확인했습니다. 이는 **2단계 전환 계획의 검증**이지 운영 전환 적용, 원본 상태에서의 단일 SSA 성공 또는 데이터 복구 인수가 아닙니다.

map의 값을 같은 값으로 명시해 소유권만 추가하는 시험도 실패했습니다. 운영 managedFields 초기화, 임의 소유권 재배정, 별도 manager, Replace나 Deployment 삭제를 이 전환의 우회 수단으로 사용하지 않습니다. 전환 실패와 정리 증거는 성공 결과로 덮어쓰지 않습니다.

### init-chown을 새로 도입하지 않음

upstream `initChownData.enabled` 기본값은 true이며 persistence가 켜지면 UID 0과 CHOWN/DAC_OVERRIDE를 가진 busybox init-chown-data가 추가됩니다. 후보는 이를 명시적으로 false로 고정하고 guard가 true/문자열/null override를 거부합니다. 실제 후보의 기존 initContainers는 그대로이며 새 root/privileged helper나 보안 권한 확대는 없습니다. 대상 ownership 준비/검증은 부모의 별도 실제 copy gate입니다. 권한 오류를 root initContainer 추가로 우회하지 않습니다.

## 전체 렌더 보존 계약

비교 기준은 prepared HEAD `9c8ea6fb84e474095a62c34013d5644f7fa5d0f6`입니다. 동일한 실제 Helm `4.2.1`, namespace `monitoring`, Kube `1.36.1`, canonical release와 `--skip-tests --include-crds`를 사용합니다.

- 전체 141개 identity가 정확히 같습니다. 기존 Grafana Deployment만 변하며 나머지 140개 전체 객체(보존 PVC 포함), Secret 참조, 모든 non-Secret raw body가 같습니다.
- Deployment 전체 recursive diff는 정확히 네 경로입니다. `/spec/strategy/type` 변경, `/spec/strategy/rollingUpdate` null 추가, `/spec/template/spec/volumes/2/emptyDir` 제거, `/spec/template/spec/volumes/2/persistentVolumeClaim` 추가뿐입니다. storage는 그 위치에서 이름 `storage`, claimName `kube-prometheus-stack-grafana`로 고정합니다.
- image/command/env, securityContext, `/var/lib/grafana` mount, resources, sidecars, 기존 init 설정, Grafana ini와 config checksum, admin/crypto Secret 참조는 바뀌지 않습니다. 새 Secret/key 회전이나 인증 활성화가 없습니다.
- Namespace, PVC, Secret, RBAC, NetworkPolicy, workload, route, Gateway/HTTP API를 추가하지 않습니다. metadata/dependency/vendor/lock/image pin도 그대로입니다. PVC spec에 volumeName/prebinding, hostPath, dataSource나 새 StorageClass는 없습니다.
- old 24-file consumer branch는 합치지 않습니다. Keycloak, private admin, API/machine 경로와 UI7 legacy/native 인증은 그대로입니다. 이 후보는 SSO 전환이 아닙니다.

## 테스트와 진단 privacy

```bash
export HELM_BIN="$(command -v helm)"
python -m unittest discover -s tests -p 'test_grafana_pvc_*.py' -v
python docs/_meta/docs_lint.py --root .
git diff --check
```

CI는 실제 local active canonical `helm template`과 `--include-crds` 검증을 반드시 실행합니다. lint는 참고 검사입니다. Helm lint가 `fail`을 INFO로 표시하면서 exit 0을 반환할 수 있으므로, 잘못된 값의 거부는 실제 template nonzero exit로 확인합니다. `IsLint` bypass는 없습니다.

`--skip-tests`만 사용하는 legacy profile의 130+PVC=131과 실제 Argo `--include-crds` profile의 140+PVC=141을 구분합니다. 기본 profile의 random admin Secret/checksum 때문에 그 특정 비교만 명시적 synthetic existingSecret fixture를 사용합니다. 실제 local active 입력은 source 파일과 `grafana-auth` 참조 그대로이며 정규화하지 않습니다.

기존 preparation 10개 테스트와 모든 fixed preactivation golden은 유지합니다. 준비 회귀에만 [명시적 legacy source fixture](05_grafana-pvc-preparation.md)를 쓰고 active는 원래 local 파일을 직접 전달합니다. 실제 Helm 결과를 mock하지 않습니다. whole-object, Deployment/Pod, non-Secret raw 고정 hash를 사용하여 서로 같은 mutable config만 비교하는 공허한 oracle을 피합니다. active 결과에서 허용된 두 literal delta만 역으로 대입하여 immutable baseline에 맞는지도 확인합니다.

실제 source의 잘못된 claim/chown, PVC retention/spec, unrelated PriorityClass와 raw-only template mutation을 거부하고 원본 복원 positive control을 검사합니다. env/crypto-key, auth, image, 보안, resources, sidecar와 init 변경도 전체 계약으로 잡습니다. source mutation이 이미 Helm에서 거부되는 경우와 native exit 0 뒤 invariant가 거부하는 경우는 별도 기록합니다. 실제 test entry-point의 실패에서도 Secret 값을 노출하지 않는 회귀를 유지합니다.

명시적 null 회귀는 실제 source와 native strategy에 key가 존재하고 값이 null인지 모두 검사합니다. 실제 복사한 chart에서 null 줄을 제거하면 native template exit 1로 guard가 거부하고, 원본 복원 뒤 positive control이 성공해야 합니다. nonnull rollingUpdate 거부도 유지합니다. raw oracle은 실제 native 출력의 `rollingUpdate: null` 다음 `type: Recreate` 순서를 고정하고, immutable baseline 검사에서 strategy 전체를 원래 `{type: RollingUpdate}`로 되돌립니다. 기존 golden은 수정하지 않습니다. 이 회귀는 source/native 선언 계약만 검증하며 기존 API object의 map 제거 성공을 증명하지 않습니다.

CRD의 unquoted `=` enum은 SafeLoader에 해당 scalar constructor 하나만 추가해 읽습니다. CRD를 제외하거나 unsafe loader로 우회하지 않습니다. Secret data/stringData와 full render는 메모리에만 있고 digest만 증거로 저장합니다. native subprocess 수/exit와 unique unittest 수를 따로 보고하며 초기 실패/거부 기록은 덮어쓰지 않습니다. 변경 소스와 펼친 관련 vendor는 Gitleaks로 검사하고 raw exit, 검토된 비밀 아닌 finding, unresolved를 구분합니다. 실제/미해결 Secret finding이 있으면 그 경로는 중단합니다.

## 부모가 별도로 인수할 cutover gate

이 절차는 실행 명령이나 완료 상태가 아닙니다. live cluster/cloud/SSH/browser, DB/Secret/archive, binding/copy/restore/decrypt와 최종 승인 소유자는 부모입니다.

1. 원본 Pod UID/readiness/emptyDir, target PVC/PV UID/binding/node와 off-host backup 경로를 다시 확인합니다. 올바른 claim 이름만으로 올바른 데이터임을 가정하지 않습니다.
2. 실제 app DB/users/dashboard/datasource와 필요한 설정/crypto material을 안전하게 보호합니다. 실제 target-volume copy와 ownership, capacity/headroom을 검증합니다. 원본과 target 데이터는 이 source 변경으로 읽거나 수정하지 않습니다.
3. production과 분리한 복원에서 실제 app 데이터/사용자 일치와 암호화 credential의 실제 decrypt/사용을 확인합니다. 파일 크기/hash, DB 열림이나 Secret 참조 일치는 app/crypto recovery의 충분조건이 아닙니다.
4. 초기 backup 이후의 write를 놓치지 않도록 최종 fresh snapshot과 write-consistency window를 정합니다. 승인된 writer 중지/쓰기 차단 또는 동등하게 입증된 정합성 절차, DB/관련 파일의 일관된 마지막 copy, target readback과 최종 복원/crypto 검증을 인수합니다. 이전 격리 복원 성공만으로 그 뒤 발생한 write까지 복원되었다고 보지 않습니다.
5. 1-4의 인수와 부모의 최종 판단 뒤, 최종 write-consistency window를 유지한 채 main 병합과 위 2단계 전환 절차를 진행합니다. 최종 copy 이후 원본 writer가 다시 쓰지 않도록 하고 하나의 Grafana writer만 시작합니다. 적용 뒤 PVC mount, 데이터/사용자, 기존 credential 사용, ownership, readiness와 legacy 로그인 및 변경되지 않은 외부 경로를 확인합니다. Recreate 중단 시간을 명시적으로 수용합니다.
6. 1-4의 인수와 별도 최종 승인 전에는 main 병합이나 운영 적용을 하지 않습니다. 소스 검토와 비밀 검사, 운영 추적 revision 확인 뒤의 격리 branch/Draft PR 게시와 exact-head CI만 앞서 진행할 수 있습니다. final copy 뒤 원본 writer가 다시 쓰면 정합성 인수는 무효이며, 새로운 최종 snapshot/copy와 window가 필요합니다. 5의 실제 적용 후 검증을 완료하기 전에는 runtime consistency나 migration/crypto/SSO 성공을 선언하지 않습니다.

## 활성화 후 rollback은 PVC를 보존

production이 PVC에 쓰기 시작한 뒤 이 변경을 통째로 revert하여 emptyDir로 돌리면 현재 live 상태를 숨기거나 잃을 수 있습니다. 따라서 blind whole-commit revert는 rollback 절차가 아닙니다. PVC 삭제/초기화, preparation flag 제거를 복구 shortcut으로 쓰지 않습니다.

안전한 image/config rollback은 native persistence enabled, 정확한 existingClaim, 기존 보존 PVC 선언/annotation, Deployment replicas 1/Recreate, initChownData false와 필요한 동일 crypto material을 유지한 채 검증된 이전 image/config만 되돌립니다. DB/schema와 암호화 호환성을 먼저 확인하고 fresh consistent snapshot을 확보합니다. Helm release rollback이나 별도 manager로 소유권을 바꾸지 않습니다.

이전 app이 현재 DB/schema를 읽을 수 없다면 writer를 중지하고, 부모가 인수한 일관된 snapshot과 원래 crypto material의 격리 restore/decrypt를 다시 입증한 뒤 승인된 PVC 보존 복구 경로를 사용합니다. target 선택/복원과 최종 데이터 손실 범위 승인은 부모가 관리합니다. 원본 snapshot과 현재 PVC를 임의 삭제하거나 emptyDir 재시작으로 대체하지 않습니다. 복구 뒤에도 단일 writer, 실제 데이터와 credential 사용 및 legacy 인증을 다시 인수합니다.
