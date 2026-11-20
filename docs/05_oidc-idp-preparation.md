---
title: Keycloak OIDC IdP preparation
updated: 2026-11-20T00:01:11+09:00
type: runbook
status: current
---

# Keycloak OIDC IdP preparation

## 현재 상태와 승인 경계

기업 IAM과 장기 운영 기준을 우선한다는 사용자 선택에 따라 Keycloak으로 준비합니다.
운영 전환을 위한 단계별 후보입니다. 관리 root에는 기존 Operator 선언을 유지하고, 전용 DB 기본값 위에 private server-only application 단계를 명시합니다. 소스 선언은 서버 배포, realm/client 생성이나 실제 로그인 인수의 성공을 뜻하지 않습니다.

- Community Keycloak 26.8.2와 공식 namespace-scoped Operator YAML을 고정합니다.
- Red Hat build of Keycloak의 상용 지원/SLA가 이 community 후보에 포함되는 것은 아닙니다.
- 공식 YAML을 감싼 얇은 로컬 Helm chart이며 공식 application Helm이라고 부르지 않습니다.
- experimental cluster-wide Operator Helm, OLM, preview Client CR와 custom provider를 사용하지 않습니다.
- 기본 준비 렌더는 외부 HTTPRoute, Application과 RealmImport를 생성하지 않습니다.
- 관리 root의 `keycloak-idp`는 기존 `productionPhase=application`, `forceString: true` parameter를 유지합니다. [별도 private admin-access 후보](oidc/04_private-admin-https.md)는 기존 16개 Application 전체 객체를 보존하고 Application 하나만 추가해 management 17개가 됩니다. automation 10개, personal 1개와 기존 앱 로그인은 변경하지 않습니다.
- 이 차트는 credential 값, AWS IAM이나 SSM 원본을 생성하지 않습니다. Secret 참조가 렌더됐다고 원본 존재를 주장하지 않습니다.
- 오프라인 schema/render 검증은 admission, 이미지 실행, DB TLS와 사용자 인증 인수의 대체가 아닙니다.
- [Grafana PVC 준비 전용 후보](oidc/05_grafana-pvc-preparation.md)는 monitoring에 unused PVC 하나만 추가합니다. 기존 Grafana emptyDir와 전체 Deployment/Pod template, config/Secret 참조/route, 다른 monitoring 객체와 UI7 legacy 인증을 보존합니다. fresh backup, binding/copy/restore와 실제 crypto-key decrypt 검증 전에는 원본 Grafana Pod를 교체하지 않으며 이 후보는 migration 완료가 아닙니다.

## DB 기본값과 private server GitOps 단계

`charts/argo-applications/management_local_values.yaml`은 `charts/keycloak-idp`를 release `keycloak`, namespace `keycloak`로 연결합니다. valueFiles 순서는 `kkamji_local_values.yaml`, `production-values.yaml`입니다.

production overlay의 기본 `productionPhase: database`는 그대로 두며 16개 namespaced 객체를 생성합니다. CNPG Cluster, 공개 CA projection과 외부 백업 참조/일정을 준비하지만 Keycloak 서버, Operator Application, RealmImport와 공개 HTTPRoute는 생성하지 않습니다.

이 후보는 기존 source factory를 수정하지 않고 `keycloak-idp`의 source.helm에 다음 parameter 하나만 추가합니다. release/namespace와 valueFiles 순서는 위와 같고 production overlay 자체는 바꾸지 않습니다.

```yaml
parameters:
  - name: productionPhase
    value: application
    forceString: true
```

Argo Helm parameter를 `--set-string productionPhase=application`으로 반영한 렌더는 17개 객체입니다. 기존 DB 16개는 동일하며 `Keycloak/keycloak` CR 하나만 추가합니다. production overlay와 독립 canonical profile은 app `instances: 1`을 고정합니다. 기존 production application 렌더와의 유일한 의미 차이는 `Keycloak/keycloak.spec.instances`의 2 -> 1입니다. stock digest, `startOptimized: false`, instance당 requests `1 CPU / 2 Gi`, 엄격한 DB TLS/FQDN과 public-only trust Secret 참조를 유지합니다. 빈 DB tolerations 생략을 보존하고 임시 reconcile bypass는 넣지 않습니다.

기본 local/CA-only 준비 profile은 2 app instances 그대로이며 production DB 기본 phase는 서버 없이 16개 객체 그대로입니다. 모든 profile의 DB 3 instances, PVC/storage, backup/retention, bootstrap/credential refs, namespace, 인증과 realm/client 상태를 바꾸지 않습니다. schema는 profile별 2/1 count를 제한하고, 독립 template guard는 schema 우회 시에도 다른 count나 보안 설정 변경을 거부합니다. 단일 app은 재시작, CA uptake나 해당 worker 장애 시 서비스 중단이 가능하며 app HA를 제공하지 않습니다. 배포 후 실제 readiness/연결과 기존 인증 보존은 부모가 별도로 확인합니다.

이 전환은 private server만 대상으로 하며 HTTPRoute/Ingress, RealmImport/OIDCClient/SAMLClient, Job/CronJob, Application이나 Secret 값을 생성하지 않습니다. 내부 HTTP8080은 통제된 인증 HTTPS 관리 경로를 의미하지 않습니다. 공개/admin/master 경로와 realm/client는 닫힌 상태이며 사람용/기계용 인증이나 기존 앱 로그인은 바꾸지 않습니다. main 반영은 서버 CR을 생성하는 실제 배포 경계입니다.

서버 적용은 부모의 실제 DB/공개 CA keyset/RBAC/TLS, 외부 백업/격리 복원과 Operator 인수를 선행조건으로 합니다. 준비 DB의 libpq TLS 결과는 실제 Keycloak JDBC 인수가 아닙니다. 실제 JDBC의 정상/잘못된 CA/host/downgrade 거부와 CA rotation/uptake, populated realm/MFA 상태의 외부 백업/격리 복원, 소유자 등록과 UI7은 부모의 미완료 gate입니다. 사람용 인증이나 realm/client를 이 후보로 열지 않습니다.

`tests/test_keycloak_gitops_activation.py`는 고정된 source/namespace/release/valueFiles/parameter, DB16 보존과 서버 전용17 렌더, 기존 Application 전체 객체 비간섭을 검사합니다. fixture helper는 명시적 forceString parameter를 `--set-string`으로 전달합니다. parameter 추가/이름/phase, release/namespace/valueFiles 변경과 realm/public/client 활성화 거부를 별도로 검사하며 mutable HEAD를 oracle로 쓰지 않습니다. 전용 Keycloak CI는 기존 Helm 4.2.1/uv 경로로 준비, CA, production과 GitOps 계약을 오프라인 검증합니다. 클러스터, AWS와 실제 credential에 접근하지 않습니다.

## Operator-only GitOps 단계

선행 Operator-only 단계가 같은 management root factory에 추가한 `keycloak-operator` Application을 그대로 유지합니다. project는 `management`, source는 `charts/keycloak-operator`, release는 `keycloak-operator`, destination namespace는 `keycloak`이며 valueFiles는 `kkamji_local_values.yaml` 하나입니다. 공식 pinned YAML을 감싼 기존 로컬 chart와 image digest를 그대로 사용합니다.

기존 factory의 자동 sync/prune/selfHeal, ServerSideApply와 Application finalizer를 상속합니다. inactive 예제를 활성 파일로 옮기거나 별도 배포 경로를 만들지 않습니다. main 반영은 실제 CRD/권한/Operator 배포 경계이며, Application 제거도 prune 영향을 검토해야 합니다.

이 Application은 CRD 4개, ClusterRole 5개, ClusterRoleBinding 1개, namespaced RoleBinding 5개, ServiceAccount/ClusterIP Service/Operator Deployment 각 1개로 총 18개 객체를 렌더합니다. Operator chart 자체는 Keycloak 서버 CR, RealmImport, preview client CR, 공개 route나 Secret 값을 생성하지 않습니다. 이번 서버 후보도 이 18개 객체와 별도의 production database 기본값 16개를 그대로 유지합니다.

준비 테스트의 Operator source 전면 금지는 이 정확한 management-root 선언 하나만 허용하는 계약으로 전환합니다. 다른 profile/이름/값의 선언과 활성 예제는 계속 거부합니다. 회귀 테스트는 root factory 비간섭, pinned 18개 객체, namespace/release/profile 변경 거부와 IdP/realm/공개 route 분리를 검사합니다. 변경 전 base와의 기존 Application byte/semantic 비교는 별도 작업 증적으로 남기며, 영구 테스트는 mutable HEAD를 oracle로 쓰지 않습니다.

이 단계의 소스와 오프라인 검증은 Operator 설치 성공이나 실제 TLS/백업/격리 복원 gate 통과를 뜻하지 않습니다. 부모가 확보한 선행 운영 증거와 이번 source candidate의 검증을 구분합니다. 소유자 MFA/복구, 실제 Keycloak 상태의 백업/복원과 서비스 로그인/negative 인수 전에는 사람용 인증을 열거나 기존 인증을 종료하지 않습니다.

## 소스와 이미지 고정

- Application/Operator: 26.8.2 GA, release 게시일 2026-11-05.
- Kubernetes resources commit: `79ba77fd65bb05a8300cd1396d6be9806a0f290f`.
- Keycloak source/docs commit: `e514445f9dcdabc5bdcf67cab56c1e49655de067`.
- Server: `quay.io/keycloak/keycloak@sha256:c68e286cacd87b942ac1939a0a1481461109d6acd3a57dc496969a319a76bbf0`.
- Operator: `quay.io/keycloak/keycloak-operator@sha256:df890db951b595fe46f3f985301a38b76fcfcc264f06201c54dfaf28adeba19e`.

Original YAML/CRD bytes와 SHA/Git blob identity, registry manifest digest를 대조합니다.
26.8.2라는 mutable tag만 신뢰하지 않습니다. release pipeline revision을 source commit과 혼동하지 않습니다.
이미지 signature/attestation, 취약점 scan, 실제 pull/startup은 아직 검증하지 않았습니다.

## 배포 단위와 권한

`charts/keycloak-operator`와 `charts/keycloak-idp`를 분리합니다. 기존 Bitnami `charts/keycloak`은 변경하지 않습니다. 목표 namespace는 `keycloak`입니다.
Operator의 현재 namespace watch와 namespaced resource/RoleBinding subject 변환을 공식 kustomization과 같게 유지합니다.

공식 26.8.2 bundle은 네 CRD를 포함합니다. Custom resource는 Namespaced이지만 CRD 자체는 cluster-scoped입니다.
기존 두 CRD만 설치하는 오래된 recipe를 재사용하지 않습니다. preview client CRD가 포함돼도 client CR는 사용하지 않습니다.

namespace-scoped라는 말이 namespace-only RBAC를 뜻하지 않습니다.
공식 controller ClusterRole은 namespace RoleBinding으로 연결되며, 별도 narrow ClusterRoleBinding은 OpenShift ingress discovery read를 허용합니다.
Operator-only 단계도 cluster-scoped CRD 4개와 ClusterRole 5개, ClusterRoleBinding 1개를 도입합니다. 정확한 권한 inventory는 렌더와 원본을 대조하며 별도 운영 적용 승인과 diff 확인 대상입니다. namespaced watch는 이 cluster-scoped 설치 권한을 없애지 않습니다.

Operator는 해당 namespace의 Secret과 workload를 넓게 관리합니다. 서버 CR을 아직 만들지 않아도 Operator 도입 자체가 이 신뢰 범위를 추가합니다.
Keycloak/RealmImport 작성자는 namespace 관리자와 같은 신뢰 범위로 봅니다. 무관한 credential을 두지 않습니다.
앱 truststore에 private CA key를 마운트하지 않지만, Operator/ESO/namespace/노드 관리자로부터 완전히 격리했다고 주장하지 않습니다.

## 서버와 전용 DB 목표

- Keycloak CR은 `k8s.keycloak.org/v2beta1`, name/release는 `keycloak`입니다.
- stock image를 `spec.image`로 고정하므로 `spec.startOptimized: false`도 명시합니다.
- production Keycloak은 1 replica, local/CA-only 준비는 2 replicas이며 전용 CNPG는 모두 3 instances입니다. 플랫폼 DB와 공유하지 않습니다.
- app의 기존 worker affinity와 실제 Operator labels에 맞는 hostname anti-affinity는 유지합니다. 단일 production replica를 두 worker에 동시에 나눌 수는 없습니다.
- DB 3개는 두 worker에서 엄격한 3-node anti-affinity를 만족할 수 없으므로 preferred 배치를 사용합니다.
- control-plane NoSchedule taint를 해제하지 않습니다. app에는 공유 RWO data PVC를 만들지 않습니다.
- 이미지 변경의 update strategy는 `RecreateOnImageChange`입니다. 업데이트 중단을 허용하는 선택입니다.
- 모든 upgrade가 rolling이라고 표현하지 않습니다. Auto/Explicit 전환은 별도 호환성/job/rollback 검증을 거칩니다.

Import/Auto-update Job은 서버 scheduling을 상속할 수 있습니다.
서버 hard anti-affinity가 일회성 Job까지 막지 않도록 지원되는 job scheduling override를 확인합니다.
실제 replica/placement/job peak는 최종 렌더/Operator 소스에 따라 계산합니다. 아직 runtime 스케줄링을 증명하지 않았습니다.

## 자원과 장애 도메인

목표는 각 Keycloak requests `1 CPU / 2 Gi`, limits `2 CPU / 2 Gi`입니다.
각 DB는 requests `250m / 1 Gi`, limits `1 CPU / 1 Gi`, storage `10 Gi`입니다.
Operator는 upstream requests `300m / 450 Mi`, limits `700m / 450 Mi`를 유지합니다.
local/CA-only 2-app 렌더와 고정 Operator 소스로 계산한 정상 모델은 6 Pods, requests `3050m / 7618 Mi`, limits `7700m / 7618 Mi`, DB `30 Gi`입니다.
import 1개는 7 Pods/requests `4050m / 9666 Mi`, Operator 기본 surge까지 겹치면 8 Pods/`4350m / 10116 Mi`입니다.
추가 CNPG Pod 하나를 여유로 더한 9 Pods/`4600m / 11140 Mi`는 보수적 reserve이며 controller가 그 동시성을 보장한다는 뜻이 아닙니다.
규칙적인 init/main은 순차 자원의 max로 계산했습니다. 실제 스케줄러, admission 변경과 운영 동시성은 미검증입니다.

1-app production 정상 모델은 5 Pods, requests `2050m / 5570 Mi`, limits `5700m / 5570 Mi`, DB `30 Gi`입니다. app instance당 resources는 줄이지 않습니다. 같은 가정의 import 1개를 더하면 6 Pods/requests `3050m / 7618 Mi`, Operator surge까지는 7 Pods/`3350m / 8068 Mi`, CNPG spare 1개까지의 보수적 reserve는 8 Pods/`3600m / 9092 Mi`입니다. 현재 application 렌더는 import Job을 만들지 않으며 이 계산은 실제 동시성이나 중단 없는 rollout을 보장하지 않습니다.

조사 시 requests headroom은 worker 1 `6575m / 8240.7 Mi`, worker 2 `4795m / 3882.7 Mi`였습니다.
이는 실제 RAM 여유나 처리량의 증거가 아닙니다. worker 2의 기존 memory limits 합계는 allocatable을 초과했습니다.
배포 전 실제 사용량, workload burst, 배치, 디스크와 유지보수 peak를 다시 확인합니다.

기록상 노드는 한 Windows host의 Hyper-V VM입니다. replica 수가 물리 host 장애 내성을 만들지는 않습니다.
local-path는 노드 종속이고 Delete reclaim입니다. CNPG replica도 off-host backup의 대체가 아닙니다.
실제 프로덕션 SLO를 주장하려면 독립 장애 도메인, replication 정책과 복구 인수를 별도로 검증해야 합니다.

## credential과 bootstrap 계약

SSM 입력 계약은 모두 SecureString JSON이며 기존 parameter-store에서 property만 읽습니다.

- `/kkamji/keycloak/database`: username/password -> `keycloak-db-app`. CNPG owner는 `keycloak`과 일치해야 합니다.
- `/kkamji/keycloak/bootstrap`: username/password -> `keycloak-bootstrap-admin`.
- `/kkamji/keycloak/clients/kkamji-platform`: client_secret -> `keycloak-oidc-client`의 client-secret.

credential consumer별 explicit property와 Orphan/Retain을 사용하고 기존 AWS ClusterSecretStore를 재사용합니다. 공개 CA용 namespaced Kubernetes SecretStore는 별도입니다.
원본 존재, KMS/ESO 실효 접근과 실제 값 일치는 운영에서 별도 확인합니다. 원본 삭제나 ESO 오류가 revoke를 보장하지 않습니다.

`spec.bootstrapAdmin.user.secret`는 초기 master realm 생성용입니다.
참조가 없으면 Operator가 초기 credential을 생성할 수 있으므로 명시한 Secret 참조를 유지합니다.
기존 master realm은 bootstrap 값을 무시하므로 ESO 갱신을 관리자 password 변경으로 부르지 않습니다.
임시 관리자 제거, 영구 관리/복구 수단과 앱 소유자 계정 분리는 미래 인수 조건입니다.
authentik runtime secret_key를 재사용하지 않습니다. Keycloak realm/signing 상태는 전용 DB의 보호/복구 대상입니다.

## DB TLS와 공개 CA의 소유권

DB host 제안은 `keycloak-db-rw.keycloak.svc.cluster.local`이며 CNPG certificate SAN과 일치해야 합니다.
`additionalOptions`의 `db-tls-mode=verify-server`는 고정 버전에서 PostgreSQL JDBC verify-full로 매핑됩니다.
`db.url`과 충돌하는 sslmode/sslfactory/sslrootcert를 넣지 않습니다. 단순 암호화를 server identity 검증으로 대체하지 않습니다.

지원되는 `spec.truststores`는 `keycloak-db-client-trust`라는 별도 공개 CA 전용 Secret을 참조합니다.
이 API는 Secret 전체를 마운트하므로 `keycloak-db-ca`를 직접 지정하지 않습니다.
공개 ca.crt/chain 외에 ca.key나 private material이 들어가면 배포를 중단합니다.
JRE 기본 trust anchors도 남으므로 DB 전용 CA만 허용하는 독점 pinning이라고 주장하지 않습니다.

공개 CA projection 소스는 기존 ESO의 Kubernetes provider로 구현했습니다. 기본 준비 profile에서는 off이고 production 두 단계에서는 필수입니다. target은 `ca.crt` 한 키만 보유해야 합니다.
[공급/회전 runbook](oidc/03_db-public-ca-supply.md)은 exact-reader TokenRequest/RBAC, 원본 Secret 전체를 읽는 ESO 신뢰 범위와 Operator의 restart 기반 uptake를 구분합니다. 실제 실효 권한, target keyset, 갱신/재연결과 거부 시험은 별도 운영 gate입니다.
다른 CA key로의 전환은 구/신 public-root overlap과 별도 검토한 maintenance/writer-handoff 후보가 필요합니다. 현재 production guard를 꺼서 임의로 수행하지 않습니다.

인수에는 정상 CA/host 연결과 잘못된 CA/SAN, plaintext downgrade 거부, CA 회전 후 재연결이 필요합니다.
실제 Keycloak JDBC 연결과 CA 회전/uptake runtime 인수는 아직 부모 gate입니다. 준비 DB의 libpq 검증이나 이 후보의 strict TLS 참조만으로 완료를 주장하지 않습니다.

## Envoy와 노출

공개 origin 제안은 `https://sso.kkamji.net`입니다. DNS/route를 생성하지 않았습니다.
기존 envoy-gateway-system/kkamji의 https listener를 사용하고 공용 Gateway/certificate를 수정하지 않습니다.
TLS termination 뒤 supported HTTP8080/xforwarded/strict hostname을 사용하며 Operator Ingress는 끕니다.
향후 backend는 `keycloak-service:8080`입니다. management9000을 공개하지 않습니다.
공개 route는 `/realms/kkamji`와 `/resources`만 허용합니다. 8080의 admin UI/API와 `/realms/master`는 내부 관리 경로로 남깁니다.
9000 차단만으로 admin API가 숨겨지지는 않습니다. 별도 관리 접근과 인코딩/경로 정규화 우회 거부를 실제로 인수해야 합니다.

실제 Envoy selector로만 앱 ingress를 허용하고, Operator management/peer/JGroups/DB 경로는 소스와 대조합니다.
egress 정책을 추가하지 않으므로 기존 egress 제어를 강제로 열지 않습니다.
다른 정책이 없는 새 namespace의 outbound는 제한되지 않습니다. egress 전체 격리를 제공한다고 표현하지 않습니다.
proxy-trusted-addresses를 설정한다면 실제 Envoy source를 검증한 뒤 제한합니다. 임의 private CIDR나 0/0을 추정하지 않습니다.
Windows portproxy 뒤 client IP 구분, X-Forwarded-* overwrite와 spoofing 거부는 별도 live gate입니다.

## RealmImport, 활성화와 client 회전

inactive 예제의 realm은 kkamji, client는 kkamji-platform이며 둘 다 disabled입니다.
public signup/reset과 불필요한 grant를 끄고 exact HTTPS callback, confidential client와 PKCE S256을 사용합니다.
client Secret은 `${OIDC_CLIENT_SECRET}` placeholder와 같은 namespace의 Secret ref로만 전달합니다.
flow에는 일반 enabled:false 필드가 없습니다. realm/client 비활성 또는 미바인딩 상태를 사용합니다.

**RealmImport는 create-only입니다.** 기존 realm 변경, 활성화와 client secret 회전을 reconcile하지 않습니다.
ESO가 client Secret을 갱신하거나 RealmImport enabled:true를 재적용해도 기존 Keycloak client는 바뀌지 않습니다.
후속 활성화/회전은 지원되는 Admin API/console에서 별도로 승인/수행하고 이전 credential 거부까지 readback해야 합니다.
아직 realm/client/Job을 만들지 않았습니다. 미래 성공한 import의 CR/Job 정리는 데이터/credential을 보존하는 별도 단계입니다.

## MFA, 앱 세션과 전환

필수 WebAuthn은 미등록 계정을 자동 거부하는 설정이 아닙니다. password 보유자가 등록 화면에 도달할 수 있습니다.
따라서 realm/client 공개 전에 소유자를 통제된 접근 경로에서 확인/등록하고 두 번째 복구 credential을 확보합니다.
SSO Cookie는 Forms를 건너뛸 수 있으므로 매 로그인마다 fresh WebAuthn을 강제한다고 표현하지 않습니다.
기존 SSO 세션, recovery/passwordless/broker/direct grant와 client flow override를 함께 점검합니다.
realm brute-force 보호와 proxy 요청 제한도 활성화 전 검토/인수합니다. IP 구분이나 account lockout 안전성을 기본값만으로 가정하지 않습니다.

[RP 계약](oidc/01_platform-client-contract.md)은 고정 issuer/owner sub, code/PKCE/state/nonce, 세션 revoke와 logout을 정의합니다.
RP 코드와 배포 상태는 해당 저장소와 rollout 증적으로 별도 확인합니다. 이 Helm 후보는 실제 소유자/MFA 인수나 기존 사람용 인증 종료를 증명하지 않습니다.

## 향후 rollout과 완료 조건

1. 정확한 검토 revision과 운영 적용 승인을 확보합니다. 새 CRD/권한과 원본 입력을 preview합니다.
2. DB 단계에서 namespace, ESO 입력과 전용 DB owner/TLS/공개 CA 및 외부 백업 기반을 확인합니다.
3. Operator-only 변경의 CRD/ClusterRole diff와 namespaced Secret/workload 신뢰 범위를 검토하고, 별도 승인된 적용 뒤 Operator readiness와 실제 watch/RBAC를 인수합니다. 서버/realm/route는 만들지 않습니다.
4. DB TLS/백업/격리 복구와 Operator gate 뒤 private server-only application 후보를 별도로 적용하고 Keycloak readiness, 실제 JDBC와 CA uptake를 인수합니다. 이번 source 변경은 이 단계의 후보이며 실제 적용 증거가 아닙니다. populated realm/MFA 상태의 off-host backup/격리 복원은 기존 사람용 인증을 닫기 전에 검증합니다.
5. 통제된 HTTPS 관리 접근으로 비활성 realm을 필요한 범위만 열고 client는 닫은 채 소유자를 등록합니다.
6. effective flow/export를 민감 정보 없이 확인하고 정상/우회/SSO/분실/복구 시험을 수행합니다.
7. 별도 Admin API/console 동작으로 client를 활성화하고 실제 issuer/discovery/JWKS/negative를 검증합니다.
8. RP를 구현/인수한 뒤 과거 v1 앱 세션을 폐기하고 기존 password endpoint를 종료합니다.

소스 선언과 오프라인 검증은 위 운영 단계의 성공 증거가 아닙니다. localhost에서 만든 RP credential을 운영 sso origin 등록으로 대체하지 않습니다.
계정/기기 등록, 잘못된 인증 거부, runtime restore 성공까지 확인해야 운영 전환 완료입니다.

## 백업, 중단과 롤백

전용 DB의 realm/user/WebAuthn credential/signing key와 필요한 설정/인증서/Secret 원본을 안전하게 보호합니다.
Realm JSON export만으로 세션/모든 상태를 포함한 DB backup을 대체하지 않습니다. export에는 민감 값이 포함될 수 있습니다.
초기 목표 제안은 RPO24시간/RTO2시간이며 아직 검증하지 않았습니다. 목적지/보존/암호화/복구 책임을 확정해야 합니다.
별도 namespace에서 복구하고 owner sub, issuer, MFA와 signing/JWKS, 앱 세션 상태를 확인합니다.

준비 후보는 적용하지 않으면 운영 영향이 없습니다. 차트/예제를 소스에서 제거하는 것과 실제 data 삭제를 구분합니다.
미래 실패 시 새 route/Application을 중지하고 기존 앱 인증 revision을 유지합니다. DB/PVC/SSM/CRD를 삭제하지 않습니다.
schema migration 후 컨테이너만 낮추지 않습니다. DB backup과 맞는 버전으로 별도 복구합니다.
비밀번호 endpoint의 재활성화는 별도 운영 판단이며 자동 fallback을 만들지 않습니다.

## CNPG PodSpec snapshot 경계

CNPG 1.30.0은 Pod 생성 시 저장한 `cnpg.io/podSpec` JSON과 새로 만든 PodSpec을 비교합니다. 명시적 빈 `tolerations: []`는 JSON snapshot에서 생략되어 nil로 복원되지만 원래 빈 배열과 `reflect.DeepEqual` 결과가 다릅니다. 운영에서 이 차이로 세 번째 DB Pod의 반복 재생성을 확인했습니다.

차트는 입력 profile과 guard를 유지하고, 깊은 복사본을 렌더하는 시점에 CNPG database affinity의 빈 tolerations만 생략합니다. 다른 값과 worker/anti-affinity/리소스/TLS/backup 경계는 바꾸지 않습니다. Kubernetes가 제공하는 기본 NoExecute toleration을 제거하거나 새 권한을 주는 변경도 아닙니다.

임시 `cnpg.io/reconcilePodSpec=disabled`는 Git 소스에 넣지 않습니다. 이미 적용한 임시 중지는 수정 revision 반영 후 제거하고, 정상 조정 상태에서 Pod UID 안정성, 3/3 Ready와 실제 TLS/backup/restore를 별도로 확인해야 합니다.

고정 소스: [PodSpec 비교](https://github.com/cloudnative-pg/cloudnative-pg/blob/4b5e244a7d031f67e025c83c1555e7726ecbbfa1/pkg/specs/podspec_diff.go), [snapshot 복원 경로](https://github.com/cloudnative-pg/cloudnative-pg/blob/4b5e244a7d031f67e025c83c1555e7726ecbbfa1/internal/controller/cluster_upgrade.go).

## 오프라인 검증의 경계

Helm4.2.1 strict lint/template, immutable 원본/overlay/schema, credential refs, namespace/RBAC/노출, 자원/job와 inactive 예제를 검사합니다.
기본 준비, 공개 CA와 production 단계의 회귀 suite에 GitOps 연결 검사를 추가했습니다. Operator18, 기본 IdP8, CA15, production DB16/application17 객체 계약을 검증합니다. 기본 준비 렌더에 노출/RealmImport/source Secret은 없습니다.
부모는 namespace 전체 egress allow-all을 제거하고 공개 admin/master 경로를 제외하는 RED/GREEN 회귀도 확인했습니다.
원본 공개 hash를 generic-api-key로 탐지한 raw scan6건은 원문/해시로 분류하며 억제하거나 raw exit1을 clean으로 표시하지 않습니다.
실제 결과는 [후보 README](../examples/keycloak-preparation/README.md)와 task 증적의 최종 review manifest/보고서로 관리합니다.
미커밋 docs 검사는 구조 검사이며 --base origin/main commit freshness/coupling CI 완료로 부르지 않습니다.

단일 production app 회귀는 local 2-app과 production 1-app의 전체 spec에서 count 외 동일성, DB 3-instance 보존, schema의 모든 app 필드 필수/불변성과 양 phase의 잘못된 count 거부를 검사합니다. Helm schema 우회 시에도 독립 guard를 시험합니다. main 반영 직전 최신 origin/main에 대해 동일한 렌더 diff를 다시 확인하고 최종 커밋에서 docs freshness/coupling과 CI를 실행합니다. 게시와 main 반영은 별도 부모 승인 경계이며 이 로컬 후보는 commit/push/live write를 수행하지 않습니다.

## 공식 근거

- [Pinned release](https://github.com/keycloak/keycloak/releases/tag/26.8.2)
- [Pinned Kubernetes resources](https://github.com/keycloak/keycloak-k8s-resources/tree/79ba77fd65bb05a8300cd1396d6be9806a0f290f/kubernetes)
- [Pinned Operator docs](https://github.com/keycloak/keycloak/tree/e514445f9dcdabc5bdcf67cab56c1e49655de067/docs/guides/operator)
- [HA overview](https://www.keycloak.org/high-availability/introduction)
- [PostgreSQL JDBC SSL](https://jdbc.postgresql.org/documentation/ssl/)


## Disabled seven-client source contract and enrollment boundary

The [consumer integration](oidc/02_consumer-sso-plan.md) preserves current server
runtime fixes and the historical one-client create-only seed. The separate
[seven-client source contract](../examples/keycloak-preparation/consumer-contract/seven-clients.yaml.inactive)
is not an applyable manifest or ready Admin API payload. All clients stay disabled;
refs contain names only. No active root, IdP/operator/private-admin object, flow
execution or owner is changed. [Controlled owner enrollment](oidc/07_owner-enrollment-source.md)
requires the parent's private HTTPS path, actual clone/export/binding and cookie
bypass review, human WebAuthn UV and independent backup/recovery, then trusted
private same-owner iss/sub and existing Grafana identity readback. RealmImport
reapply and ESO refresh are not existing-realm updates or client rotation.
The accepted Grafana storage migration is not reopened or converted into SSO approval.
