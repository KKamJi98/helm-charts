---
title: Grafana PVC preparation only
updated: 2026-11-16T11:58:49+09:00
type: runbook
status: current
---

# Grafana PVC preparation only

## 소스 후보와 실제 데이터 보전의 경계

이 단계는 사용하지 않는 PVC 객체 하나만 준비합니다. Grafana persistence 활성화, 데이터 이관, Pod 교체, 로그인 전환을 수행하지 않습니다. [Keycloak 단계별 계획](../05_oidc-idp-preparation.md)과 private admin HTTPS는 그대로 두며 기존 UI7의 사람용 인증도 legacy 상태를 유지합니다.

부모가 제공한 공개 관측에서 Grafana `13.2.3-distroless`의 `/var/lib/grafana`는 `storage` emptyDir입니다. 원본 Pod는 `kube-prometheus-stack-grafana-6f4c6fbdf7-6nv7m`, UID `5a498faf-c021-4c2e-b413-6b54ca177fce`, 노드는 `k8s-w1`이며 부모가 Ready와 미교체를 확인했습니다. 공개 입력의 `grafanaReadyAndRestartedByThisStep: false`는 두 조건의 conjunction이고 unready라는 뜻이 아닙니다. leaf의 오프라인 검증은 이 관측을 새로 확인한 live 증거가 아닙니다.

준비 PVC 존재는 기존 사용자의 DB, dashboard, datasource credential이나 Grafana encryption key 보전의 증거가 아닙니다. 원본 Pod가 교체되기 전에 부모의 별도 데이터 보전 gate가 필요합니다.

## 최소 차트 계약

- wrapper의 `grafanaPvcPreparation` 하나만 boolean으로 받습니다. 기본값은 `false`, `kkamji_local_values.yaml`만 `true`로 opt in합니다. map, 문자열, null과 임의 PVC 설정 surface는 거부합니다.
- GitOps release `kube-prometheus-stack`, namespace `monitoring`에서는 `PersistentVolumeClaim/monitoring/kube-prometheus-stack-grafana` 하나만 추가합니다. 기존 monitoring 객체 전체와 Grafana Deployment/Pod template, config, Secret 참조, route는 그대로입니다.
- PVC는 `ReadWriteOnce`, `storageClassName: local-path`, 요청량 `10Gi`입니다. 용량은 vendored kube-prometheus-stack `92.3.0`에 포함된 Grafana chart `13.5.0`의 persistence 기본값에서 가져옵니다. 실제 데이터 크기나 디스크 여유를 확인한 sizing이 아닙니다.
- `volumeName`, selector, dataSource와 prebinding, ownership adoption은 없습니다. Job, hostPath, Secret, ServiceAccount, RBAC, Namespace나 NetworkPolicy도 추가하지 않습니다.
- upstream `grafana.persistence`는 고정된 비활성 기본값 그대로이며 `existingClaim`도 설정하지 않습니다. 준비 중 upstream persistence override, StatefulSet 전환과 Grafana name/namespace override를 거부합니다. 이 guard는 migration 승인 framework가 아닙니다.
- PVC 이름은 실제 pinned `grafana.fullname`, namespace는 `grafana.namespace` helper를 사용합니다. namespace는 `monitoring`만 허용합니다. 이름을 hardcode하거나 Helm lint release만 우회하지 않습니다. Helm lint 자체의 release 이름과 다른 명시적 release에서는 그 release의 Grafana 이름으로 일관되게 유도되므로 실제 GitOps 검증은 반드시 canonical release로 렌더합니다.
- vendor archive, Chart.yaml, Chart.lock과 controller/image 버전은 변경하지 않습니다. 다른 root/Application과 private Keycloak admin 자원도 변경하지 않습니다.

## 보존 옵션과 Pending의 의미

PVC의 per-object annotation은 `argocd.argoproj.io/sync-options: Prune=false,Delete=false`입니다. 정상 Argo prune과 Application 삭제 시 PVC 삭제를 막는 옵션입니다. 수동 Kubernetes 삭제, 관리자 강제 삭제, 스토리지 손실까지 막지는 않습니다. 준비 flag를 끄거나 소스에서 제거해도 정상 prune으로 정리되지 않는 PVC가 남을 수 있으며 정리는 별도의 승인된 수동 작업입니다.

부모가 확인한 `local-path`는 provisioner `rancher.io/local-path`, binding `WaitForFirstConsumer`, reclaim `Delete`입니다. 이 단계에는 PVC consumer가 없으므로 PVC가 **Pending**, Argo health가 **Progressing**인 상태가 가능합니다. binding 성공이나 배포 Healthy를 오프라인 성공 조건으로 바꾸지 않습니다.

local-path는 노드 종속입니다. reclaim `Delete`는 PVC 삭제 뒤 PV/데이터를 잃을 수 있는 정책이며 off-host recovery나 백업이 아닙니다. 보존 annotation도 off-host backup과 encryption-key 복구를 대체하지 않습니다. 기존 PV 경로나 노드 filesystem을 이 단계에서 읽거나 수정하지 않습니다.

## 원본 Pod 교체 전 부모 gate

다음 작업은 별도 부모 단계입니다. 이 문서는 완료 boolean이나 승인 bypass를 제공하지 않습니다.

1. 원본 Pod UID, readiness와 emptyDir 상태를 다시 확인하고, writer 정합성을 고려한 fresh backup을 확보합니다. 기존 backup이 있다는 주장만으로 최신 상태를 보전했다고 보지 않습니다.
2. Grafana users/dashboard/DB와 필요한 설정, administrator 및 crypto-key의 실제 원본을 안전하게 보호하고 off-host recovery 경로를 검증합니다. 값은 Git, render 증거나 이 문서에 기록하지 않습니다.
3. 실제 데이터 크기, 대상 노드, filesystem과 디스크 headroom을 확인하고, 승인된 별도 절차로 WaitForFirstConsumer binding과 복사/복원을 수행합니다. PVC 준비 자체는 bind나 copy를 하지 않습니다.
4. 격리된 복원 결과에서 DB/사용자/데이터 일치와 기존 암호화 credential의 실제 decrypt/사용을 확인합니다. Secret 참조가 같은 것만으로 crypto-key 복구가 입증되지 않습니다.
5. 위 gate 뒤 별도로 검토한 persistence 활성화 후보를 적용하기 전까지 원본 Grafana Pod를 교체하지 않습니다. 전략/replica/volume, initContainer, env와 보안 설정을 이 준비 변경에 섞지 않습니다. UI7 legacy 인증은 별도의 인증 전환 인수 전까지 유지합니다.

## 오프라인 검증

```bash
helm lint charts/kube-prometheus-stack --strict -n monitoring --kube-version 1.36.1
helm lint charts/kube-prometheus-stack --strict -n monitoring --kube-version 1.36.1 \
  -f charts/kube-prometheus-stack/kkamji_local_values.yaml
export HELM_BIN="$(command -v helm)"
python -m unittest discover -s tests -p 'test_grafana_pvc_preparation.py' -v
python docs/_meta/docs_lint.py --root .
git diff --check
```

영구 테스트는 실제 Helm `4.2.1`의 `template kube-prometheus-stack -n monitoring --kube-version 1.36.1 --skip-tests`를 사용합니다. lint에는 `--skip-tests` 옵션이 없으며 실제 lint 명령을 그대로 사용합니다. 테스트 stdout에는 full render나 Secret 값을 쓰지 않습니다.

고정 base `7b83ff9a53d4b705422feb1c2b4e98f7bb6e64dc`에서 생성한 whole-object/raw-body oracle로 기본 및 local의 enabled/disabled, 정확한 PVC 필드, 모든 기존 객체와 Grafana Deployment/Pod template을 검사합니다. local의 기존 130개 객체는 그대로이며 opt in에서는 PVC를 더한 131개입니다. 타입/추가 설정, upstream persistence/identity override와 위험한 source mutation을 거부하고 복원한 positive control도 검사합니다. 고정 계약을 mutable values와의 비교로 약화하지 않습니다.

upstream 기본 profile은 `randAlphaNum` admin-password 및 Pod `checksum/secret`의 비결정성이 있습니다. 정확한 기본 비교에만 synthetic `admin.existingSecret: grafana-pvc-offline-existing-admin` fixture를 사용합니다. random Secret이나 checksum을 같다고 보고하거나 정규화해 숨기지 않습니다. 실제 production local profile은 `grafana-auth` 참조 그대로 비교하며 모든 non-Secret raw body와 객체가 보존되어야 합니다. Secret 렌더는 메모리에만 두고 값은 출력하거나 저장하지 않습니다.

정적 문서 검사와 로컬 테스트 통과는 최종 commit의 freshness/coupling CI 통과가 아닙니다. 최종 소스 검토, staging/commit/push와 live 적용, 백업/binding/copy/restore/decrypt 인수는 부모 gate로 남습니다. 이 단계의 결과를 Grafana migration 완료로 부르지 않습니다.
