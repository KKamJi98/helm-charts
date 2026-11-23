---
title: Grafana PVC preparation only
updated: 2026-11-23T20:54:00+09:00
type: runbook
status: current
---

# Grafana PVC preparation only

## Current-main consumer integration boundary

부모가 인수한 Grafana native retained-PVC 전환을 현재 기준으로 유지합니다. 아래의
emptyDir/미배포/전환 전 승인 서술은 당시 준비 또는 PR86 제안의 역사적 기록이며,
현재 storage/data 인수를 다시 여는 조건이나 현재 운영 상태의 oracle가 아닙니다.
consumer 기본 인증은 계속 legacy이고, source의 SSO acknowledgement는 false입니다.
[consumer 계획](02_consumer-sso-plan.md)과 [owner 등록 절차](07_owner-enrollment-source.md)는
별도의 owner/MFA/UI 인수를 요구합니다. 이 leaf는 runtime/dataMigrationAccepted를 false로 유지합니다.

새 keycloakSSO 기본값은 additive입니다. 기존 default/preparation/activation의 고정
whole-object/raw/hash, crypto, sidecar, ownership guard는 그대로이며 defaults exact
검사만 새 legacy 필드를 명시합니다. 2026-11-23 [홈랩 Tier 3 최적화](../07_homelab-resource-optimization.md) 및
[Istio Ambient 전환](../08_istio-ambient-mesh.md)에서
Alertmanager(`5m/80Mi`, lim `192Mi`), Prometheus(`25m/768Mi`, lim `1536Mi`), `kubeApiServer`
미사용 고카디널리티 histogram bucket drop(`~27.8k` series), 레거시 sidecar `envoy-stats`
scrape job 제거를 반영해 `kube-prometheus-stack` 로컬 전체 해시만 재기준선화했으며,
Grafana Deployment/Pod template 해시와 PVC/storage guard는 바이트 단위로 보존됩니다. 별도 current-main 회귀는 131/141 객체와
retained-PVC + synthetic canary/final 조합을 immutable 9a baseline으로 검사합니다.
mutable values 두 벌의 동등성으로 storage 검증을 대체하지 않습니다.

## Historical preparation and activation proposal

이하 절차와 관측 시제는 원래 제안 시점의 기록입니다.


## 준비 profile과 후속 후보의 경계

이 문서는 PR85의 사용하지 않는 PVC 준비 계약과 그 회귀 fixture를 설명합니다. 현재 branch의 local values는 별도의 [native activation 오프라인 후보](06_grafana-pvc-activation.md)입니다. 현재 local values를 준비 전용으로 간주해 운영에 적용하지 않습니다. Draft PR/CI는 운영 전환이 아니며, main 병합과 운영 적용에는 별도 activation gate가 필요합니다. 기본 values의 `grafanaPvcPreparation: false`와 upstream persistence 비활성 상태는 그대로입니다.

준비 profile은 PVC 객체 하나만 추가하며 Grafana persistence 활성화, 데이터 이관, Pod 교체, 로그인 전환을 수행하지 않습니다. [Keycloak 단계별 계획](../05_oidc-idp-preparation.md)과 private admin HTTPS는 그대로 두며 기존 UI7의 사람용 인증도 legacy 상태를 유지합니다.

부모가 제공한 공개 관측에서 Grafana `13.2.3-distroless`의 `/var/lib/grafana`는 `storage` emptyDir입니다. 원본 Pod는 `kube-prometheus-stack-grafana-6f4c6fbdf7-6nv7m`, UID `5a498faf-c021-4c2e-b413-6b54ca177fce`, 노드는 `k8s-w1`이며 부모가 Ready와 미교체를 확인했습니다. 후속 공개 입력의 준비 PVC는 Bound이지만 실제 application data 복사와 persistence 활성화는 false입니다. leaf의 오프라인 검증은 이 관측을 새로 확인한 live 증거가 아닙니다.

PVC 존재나 binding은 DB, dashboard, datasource credential이나 Grafana encryption key 보전의 증거가 아닙니다. 원본 Pod가 교체되기 전에 부모의 별도 데이터 보전 gate가 필요합니다.

## 고정 준비 계약

- wrapper의 `grafanaPvcPreparation`은 boolean만 받습니다. 기본값은 `false`입니다. map, 문자열, null과 임의 PVC 설정 surface는 거부합니다. activation 승인 flag를 추가하지 않습니다.
- GitOps release `kube-prometheus-stack`, namespace `monitoring`의 준비 profile에서는 `PersistentVolumeClaim/monitoring/kube-prometheus-stack-grafana` 하나만 추가합니다. 기존 monitoring 객체 전체와 Grafana Deployment/Pod template, config, Secret 참조, route는 그대로입니다.
- PVC는 `ReadWriteOnce`, `storageClassName: local-path`, 요청량 `10Gi`입니다. vendored kube-prometheus-stack `92.3.0`, Grafana chart `13.5.0`의 capacity 기본값이며 실제 데이터 크기나 디스크 여유를 확인한 sizing은 아닙니다.
- PVC 선언의 정확한 spec과 `Prune=false,Delete=false`는 후속 후보에서도 바뀌지 않습니다. `volumeName`, selector, dataSource, prebinding이나 arbitrary claim adoption은 없습니다. Job, hostPath, Secret, ServiceAccount, RBAC, Namespace나 NetworkPolicy도 추가하지 않습니다.
- 준비 profile의 upstream `grafana.persistence`는 고정 비활성 기본값이며 `existingClaim`도 없습니다. 기존 unsafe persistence/identity override 거부는 유지합니다. 후속 후보에서만 고정된 native existingClaim/Recreate profile 하나를 추가로 허용합니다.
- PVC와 consumer의 이름은 pinned `grafana.fullname`, namespace는 `grafana.namespace` helper를 사용합니다. namespace는 `monitoring`만 허용합니다. `IsLint`나 `test-release` bypass는 없습니다. 실제 GitOps 인수에는 canonical release 렌더가 필요합니다.
- vendor archive, Chart.yaml, Chart.lock, controller와 image pin은 변경하지 않습니다. 다른 root/Application과 private Keycloak admin 자원도 변경하지 않습니다.

## 보존 옵션과 binding

PVC의 per-object annotation은 `argocd.argoproj.io/sync-options: Prune=false,Delete=false`입니다. 정상 Argo prune과 Application 삭제 시 PVC 삭제를 막는 옵션입니다. 수동 Kubernetes 삭제, 관리자 강제 삭제, 스토리지 손실까지 막지는 않습니다. flag를 끄거나 소스에서 제거해도 정상 prune으로 정리되지 않는 PVC가 남을 수 있으며 삭제나 초기화는 이 절차에 포함되지 않습니다.

부모가 확인한 `local-path`는 provisioner `rancher.io/local-path`, binding `WaitForFirstConsumer`, reclaim `Delete`입니다. 준비 전용 단계에는 consumer가 없으므로 Pending/Progressing이 가능했습니다. 후속 공개 입력의 canonical PVC는 Bound 10Gi, node `k8s-w1`이며 별도 binding consumer는 정리되었습니다. 이를 leaf의 binding 실행이나 application data 복사 성공으로 보고하지 않습니다.

local-path는 노드 종속입니다. reclaim `Delete`는 PVC 삭제 뒤 PV/데이터를 잃을 수 있는 정책이며 off-host recovery나 백업이 아닙니다. 보존 annotation도 off-host backup과 encryption-key 복구를 대체하지 않습니다.

## 원본 Pod 교체 전 부모 gate

1. 원본 Pod UID, readiness와 emptyDir 상태를 다시 확인하고 writer 정합성을 고려한 fresh backup을 확보합니다. 기존 backup이 있다는 주장만으로 최신 상태가 보전되었다고 보지 않습니다.
2. 실제 DB/사용자/dashboard/datasource, 관리자와 crypto-key 원본을 보호하고 off-host recovery를 검증합니다. 값은 Git, render 증거나 이 문서에 기록하지 않습니다.
3. 실제 크기, target node/filesystem/headroom과 ownership을 확인하고 승인된 별도 절차로 target PVC에 복사/복원합니다. source 준비 자체는 bind나 copy를 하지 않습니다.
4. 격리 복원에서 app/사용자/데이터 일치와 기존 암호화 credential의 실제 decrypt/사용을 확인합니다. 같은 Secret 참조는 crypto 복구 증거가 아닙니다.
5. [activation gate와 PVC 보존 rollback](06_grafana-pvc-activation.md)을 별도로 인수합니다. 초기 backup 뒤 발생한 write를 포함하는 최종 fresh snapshot/정합성 window 없이는 cutover하지 않습니다. UI7 legacy 인증도 별도 인증 전환 인수 전까지 유지합니다.

## 오프라인 검증 profile

```bash
export HELM_BIN="$(command -v helm)"
python -m unittest discover -s tests -p 'test_grafana_pvc_*.py' -v
python docs/_meta/docs_lint.py --root .
git diff --check
```

기존 10개 preparation test와 고정 preactivation golden은 유지합니다. preparation 테스트는 현재 local 입력에서 이번에 추가한 네 Grafana 설정(`persistence`, `deploymentStrategy`, `initChownData`, `replicas`)만 제외한 명시적 legacy source fixture를 실제 Helm에 전달합니다. 나머지 source/auth 참조는 그대로이며 render/result를 mock하거나 active 결과를 정규화하지 않습니다. Helm 4에서 upstream에 없던 key의 null overlay는 null을 남기므로 이 fixture를 대신할 수 없습니다.

Helm `4.2.1`, release `kube-prometheus-stack`, namespace `monitoring`, Kube `1.36.1`, `--skip-tests` 기준으로 기존 local 130개에 PVC를 더하면 131개입니다. 실제 Argo 범위인 `--include-crds`에서는 기존 140개에 PVC를 더한 141개입니다. 이 두 profile을 같은 count로 부르지 않습니다. default와 legacy local의 enabled/disabled whole-object, non-Secret raw body와 Deployment/Pod 고정 hash를 유지합니다.

기본 profile은 upstream random admin-password와 Pod checksum 때문에 정확한 비교에만 synthetic `admin.existingSecret: grafana-pvc-offline-existing-admin`을 사용합니다. 실제 local은 `grafana-auth` 그대로입니다. Secret render는 메모리에만 두고 값이나 full render를 출력/저장하지 않습니다. 위험한 실제 source mutation, 진짜 test entry-point의 진단 privacy, 복원한 positive control을 유지합니다.

정적 문서 검사와 오프라인 테스트 통과는 최종 commit의 freshness/coupling CI나 live 성공이 아닙니다. staging/commit/push, 실제 백업/copy/restore/decrypt와 최종 인수는 부모 gate로 남습니다.
