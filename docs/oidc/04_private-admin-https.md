---
title: Private Keycloak admin HTTPS candidate
updated: 2026-11-16T12:26:07.952090+00:00
type: runbook
status: current
---

# Private Keycloak admin HTTPS candidate

## Scope and ownership

이 문서는 오프라인 검증 대상인 source candidate를 설명합니다. 실제 관리 HTTPS, 인증, DNS 제외, CNI 집행이나 로그 비노출을 인수한 기록이 아닙니다. 기존 앱 로그인, realm/client, owner/MFA, DB/CA와 인증서 발급 경로는 변경하지 않습니다.

`charts/envoy-gateway`가 private `EnvoyProxy`, `Gateway`, proxy ingress-deny `NetworkPolicy` 세 객체를 소유합니다. 별도 서비스 차트 `charts/keycloak-admin-access`는 `HTTPRoute`, named `ReferenceGrant`, server ingress `NetworkPolicy` 세 객체만 소유합니다. 후자는 dependency와 `Chart.lock`이 없는 native-resource chart입니다. Controller가 이후 생성할 Deployment/Service는 이 여섯 source 객체 수와 구분합니다.

두 차트의 `keycloakAdminPrivate.enabled` 기본값은 `false`이고 각 `kkamji_local_values.yaml`에서만 명시적으로 `true`입니다. private block은 boolean flag 하나만 지원하며 host, backend, selector, logging, Service type과 arbitrary patch를 values로 override할 수 없습니다. template guard는 schema validation을 건너뛰어도 잘못된 flag/추가 필드를 거부합니다. 활성 상태에서 namespace/release도 고정합니다. 기존 플랫폼의 public values 인터페이스를 전역적으로 잠그지는 않습니다.

management root는 `keycloak-admin-access` Application 하나를 추가합니다. destination은 `envoy-gateway-system`, release는 `keycloak-admin-access`, valueFiles는 `kkamji_local_values.yaml` 하나이며 기존 repo/main/project와 sync policy를 상속합니다. 이전 16개 Application은 전체 객체를 보존하여 management 17개, automation 10개, personal 1개입니다. IdP application 17개/DB 기본 16개/Operator 18개/IdP default 8개 렌더는 변경하지 않습니다. main 반영은 GitOps 배포 경계이며 이 문서는 반영 승인이 아닙니다.

## Exact private path

- `Gateway/envoy-gateway-system/keycloak-admin-private`는 기존 `GatewayClass/envoy`를 사용합니다. 새 GatewayClass를 만들거나 기존 class에 `parametersRef`를 넣지 않습니다.
- 해당 Gateway의 `infrastructure.parametersRef`만 동일 namespace의 전용 `EnvoyProxy/keycloak-admin-private`를 가리킵니다. Envoy Gateway v1.8.1의 per-Gateway 구성을 사용하고 `mergeGateways: false`를 명시합니다.
- listener는 `https` 하나로 exact `sso.kkamji.net`, HTTPS 443, TLS Terminate입니다. `wildcard-kkamji-net-tls`는 같은 namespace의 Secret reference만 사용합니다. Secret/key/certificate를 읽거나 복사/생성하지 않으며 새 Certificate/Issuer, cross-namespace TLS grant와 HTTP/passthrough listener가 없습니다.
- allowedRoutes는 같은 namespace의 HTTPRoute뿐입니다. route의 유일한 parent는 private Gateway의 `https` section입니다. `/` PathPrefix는 이 private parent에서만 admin/master 경로를 포함합니다.
- 유일한 backend는 `Service/keycloak/keycloak-service:8080`, weight 1입니다. route의 group/kind/namespace/weight와 match type을 명시합니다. `ReferenceGrant/keycloak/keycloak-admin-private`는 `envoy-gateway-system`의 HTTPRoute에서 이 named Service로 향하는 참조만 허용합니다.
- private Envoy Service는 `ClusterIP`입니다. replicas 1, concurrency 1, Envoy container requests `100m/128Mi`, limits `500m/256Mi`를 설정합니다. 기존 controller/data-plane image 설정은 바꾸지 않습니다. controller가 추가하는 sidecar와 rollout peak의 실제 자원은 부모가 별도로 인수해야 합니다.
- 전용 proxy Pod의 `kkamji.net/access: keycloak-admin-private` label만 ingress deny 정책이 선택합니다. `policyTypes: [Ingress]`, `ingress: []`이며 egress 정책을 추가하지 않습니다. public proxy나 namespace 전체를 선택하지 않습니다.
- 새 server ingress 정책은 exact Keycloak server labels 네 개를 선택합니다. source namespace와 private proxy owning-Gateway labels 세 개 및 custom access label을 한 peer의 AND 조건으로 요구하며 TCP 8080만 허용합니다. 기존 세 정책은 유지합니다. 관리 9000, DB 5432와 namespace-wide/egress allow-all은 추가하지 않습니다.
- `telemetry.accessLog.disable: true`만 설정합니다. debug/body/header/token logging, bootstrap/extraArgs와 arbitrary Pod patch는 없습니다. 이것은 실제 모든 구성요소의 로그 비노출 증거가 아닙니다.

NetworkPolicy는 additive입니다. 새 deny가 다른 정책의 allow를 취소하지 않으며, port-forward가 CNI에 어떻게 처리되는지도 source model만으로 보장하지 않습니다. 부모가 기존 정책과 실제 label/port를 확인하고 cluster-client 차단 및 loopback port-forward 경로를 각각 시험해야 합니다.

## ExternalDNS safety contract

제공된 snapshot의 ExternalDNS v0.21.0 source는 service/gateway-httproute/gateway-tlsroute이며 annotation-prefix override가 없습니다. private Gateway, HTTPRoute와 `envoyService.annotations`에는 다음 annotation만 둡니다.

```yaml
external-dns.alpha.kubernetes.io/controller: keycloak-admin-private-disabled
```

v0.21.0의 `DefaultAnnotationPrefix`는 `external-dns.alpha.kubernetes.io/`, `ControllerValue`는 `dns-controller`입니다. `IsControllerMismatch`는 controller key가 존재하고 기대값과 다를 때만 true입니다. `gateway.go`는 **route metadata**에 이 함수를 적용하고 resolve 전에 skip합니다. `service.go`도 각 Service에서 함수를 호출한 뒤 skip합니다. Gateway annotation 하나만으로 route의 DNS 생성을 막는다고 가정하지 않습니다. HTTPRoute와 generated Service 양쪽 annotation이 필요합니다.

key 누락이나 `dns-controller` 값은 skip하지 않습니다. 지원되지 않은 `exclude` annotation으로 대체하지 않습니다. private 객체에 hostname/target annotation을 넣거나 ExternalDNS/global 설정, public Gateway target 또는 DNS record를 바꾸지 않습니다. 실제 generated Service annotation, ExternalDNS endpoint/record 비간섭은 부모의 별도 gate입니다.

확인한 public source는 Envoy Gateway tag v1.8.1의 `site/content/en/latest/tasks/operations/customize-envoyproxy.md`, `api/v1alpha1/envoyproxy_types.go`와 ExternalDNS tag v0.21.0의 `source/gateway.go`, `source/service.go`, `source/annotations/annotations.go`, `source/annotations/processors.go`입니다. 제공된 cached bundle의 SHA256을 대조했습니다.

| Cached public source | SHA256 |
|---|---|
| Envoy customize-envoyproxy.md | `ed68e5d928c05bfacf4f028d163b11bf0113079f66d16096015eadd41a72dac5` |
| Envoy envoyproxy_types.go | `c2a1058cbedf36fe780378f2d9f58fdf569691f2861ba7df2953acbf24fcb95e` |
| ExternalDNS gateway.go | `87af224fa082043027e94a48bdd551a90a24340735ab664d58dbf664311dac1d` |
| ExternalDNS service.go | `613dac131c15aecfe46e3c0c8c02a69d9734d800d826da592d375d93a86e420e` |
| ExternalDNS annotations.go | `030583921c9a11af12e3a869a5eb99603a8d46ff098567dc89b003439a30a910` |
| ExternalDNS processors.go | `8be1cbed56963b9181f302401a13dc53a190b12997350a12468aafaf1024849c` |

## Offline evidence and parent acceptance

`tests/test_keycloak_private_admin.py`는 real Helm render/lint, default off와 enabled 3+3, 기존 public 43개 객체의 고정 digest, 이전 root 16개 전체 객체의 고정 digest, exact refs/selectors와 위험 변형을 검사합니다. 잘못된 namespace/release/flag/추가 private 필드는 schema on/off로 거부합니다. EnvoyProxy는 기존 pinned vendor CRD schema로 확인합니다. 고정 DNS truth table과 additive NetworkPolicy model은 Go 실행이나 CNI enforcement가 아닙니다. 전체 canonical `test_keycloak*.py` suite는 기존 syncPolicy literal 및 root-fixture mutation 회귀도 유지합니다.

부모의 검토/승인 후 실제 생성된 private proxy Service를 identity/labels로 확인하고, loopback에만 kubectl port-forward하여 검증된 HTTPS를 사용합니다. curl 연결 검사는 `--connect-to sso.kkamji.net:443:127.0.0.1:8443`처럼 URL/SNI/Host를 `sso.kkamji.net`으로 유지하는 방식이 가능합니다. 인증서 검증을 끄거나 raw backend HTTP로 credential을 보내지 않습니다. 실제 브라우저의 origin/redirect, 인증과 owner/MFA 절차는 부모가 소유합니다. 전역 DNS나 public listener를 관리 접근 우회로로 바꾸지 않습니다.

남은 gate는 실제 API admission/Accepted/ResolvedRefs, generated ClusterIP/labels, public route/DNS 비간섭, 일반 cluster-client 차단, 부모 port-forward와 trusted HTTPS, 인증서 검증 실패 control, 실제 로그 privacy, DB negative/downgrade/CA uptake, owner/MFA/복구와 UI7입니다. 이 source 후보는 어느 gate도 실제 통과했다고 주장하지 않습니다. 임의 realm/client/owner 생성이나 기존 인증 전환은 하지 않습니다.

철회도 두 GitOps 소유자의 prune 영향과 순서를 부모가 검토해야 합니다. service access를 먼저 닫고 private platform infrastructure를 제거하는 source 역변경을 검토하되 기존 public Gateway/class, wildcard Secret/Certificate, Keycloak/DB/PVC와 기존 인증은 삭제하지 않습니다.

관련 정본: [Gateway ownership](../rules/gateway-api-routing.md), [Keycloak 단계](../05_oidc-idp-preparation.md), [DB public CA](03_db-public-ca-supply.md).


The owner-approved attended Hindsight epoch4 window updates only the exact automation-root snapshot for its temporary synthetic overlay. Keycloak management/personal roots and security contracts remain unchanged. The paired closure restores the original private-only snapshot; no assertion is skipped.


The attended Hindsight epoch4 closure restores the automation-root snapshot to its original private-only configuration. Keycloak management/personal roots and security contracts remain unchanged.

The prepared attended Hindsight epoch5 window changes only the automation-root snapshot for the existing temporary synthetic overlay. Keycloak management/personal roots and all security assertions remain unchanged. The paired closure restores the exact private-only snapshot. This source preparation does not open the route.

The prepared epoch5 closure restores the automation-root snapshot exactly to its original private-only value. No Keycloak management/personal roots or security assertions change.
