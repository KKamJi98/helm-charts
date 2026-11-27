---
title: Private Keycloak admin HTTPS candidate
updated: 2026-11-27T16:05:00+09:00
type: runbook
status: current
---

# Private Keycloak admin HTTPS candidate

## Scope and ownership

이 문서는 오프라인 검증 대상인 source candidate를 설명합니다. 실제 관리 HTTPS, 인증, DNS 제외, CNI 집행이나 로그 비노출을 인수한 기록이 아닙니다. 기존 앱 로그인, realm/client, owner/MFA, DB/CA와 인증서 발급 경로는 변경하지 않습니다.

`charts/envoy-gateway`가 private `EnvoyProxy`, `Gateway`, proxy ingress-deny `NetworkPolicy` 세 객체를 소유합니다. 별도 서비스 차트 `charts/keycloak-admin-access`는 `HTTPRoute`, named `ReferenceGrant`, server ingress `NetworkPolicy`, private proxy metrics용 `CiliumNetworkPolicy` 네 객체를 소유합니다. 후자는 dependency와 `Chart.lock`이 없는 native-resource chart입니다. Controller가 이후 생성할 Deployment/Service는 이 일곱 source 객체 수와 구분합니다.

두 차트의 `keycloakAdminPrivate.enabled` 기본값은 `false`이고 각 `kkamji_local_values.yaml`에서만 명시적으로 `true`입니다. private block은 boolean flag 하나만 지원하며 host, backend, selector, logging, Service type과 arbitrary patch를 values로 override할 수 없습니다. template guard는 schema validation을 건너뛰어도 잘못된 flag/추가 필드를 거부합니다. 활성 상태에서 namespace/release도 고정합니다. 기존 플랫폼의 public values 인터페이스를 전역적으로 잠그지는 않습니다.

management root는 `keycloak-admin-access` Application 하나를 추가합니다. destination은 `envoy-gateway-system`, release는 `keycloak-admin-access`, valueFiles는 `kkamji_local_values.yaml` 하나이며 기존 repo/main/project와 sync policy를 상속합니다. 이전 16개 Application은 전체 객체를 보존하여 management 17개, automation 9개, personal 1개입니다. IdP application 17개/DB 기본 16개/Operator 18개/IdP default 8개 렌더는 변경하지 않습니다. main 반영은 GitOps 배포 경계이며 이 문서는 반영 승인이 아닙니다.

별도의 [모카 recall 연동](../03_hindsight.md#모카chatgpt-읽기-전용-recall-연동)은 automation의 기존 Hindsight Application에 `moka_private_values.yaml`만 추가합니다. 이 때문에 automation 10개 객체의 검증 해시만 바뀝니다. 이후 `personal-root`에 `real-life-rpg`가 재활성화되어 personal 2개가 되었고(2026-11-23 [Istio Ambient 전환](../08_istio-ambient-mesh.md)으로 `real-life-rpg`와 `kkamji-platform`에 `istio.io/dataplane-mode: ambient` 네임스페이스 라벨 관리 추가), 2026-11-23 [홈랩 리소스 및 Istio Ambient 전환](../07_homelab-resource-optimization.md)으로 `management-root`에 `istio-cni`, `istio-ztunnel` 2개 Application(sync-wave 포함)이 추가되어 management 19개가 되었으며, 2026-11-24 R4 공개 라우트(`charts/keycloak-public-access`, `/realms/kkamji`와 `/resources` 전용) 추가로 management 20개(`keycloak-admin-access` 제외 19개)가 되었습니다. Tier 3 최적화에서 `envoy-gateway` controller와 공용 `EnvoyProxy/kkamji-public`(`concurrency: 1`, `20m/192Mi`, lim `384Mi`) 리소스만 경량화했습니다. PR #117의 Backend API 및 공용 access log query 제거와 Keycloak admin 7개 보안 객체 계약은 변경하지 않습니다.

## Separate discovery-only opt-in

The [owner discovery candidate](07_owner-enrollment-source.md#discovery-only-gateway-source-candidate)
adds three platform and three service objects under a distinct
`keycloakOwnerDiscovery.enabled` flag, default `false` and enabled only by the two
current local overlays. These six objects use `keycloak-owner-enrollment` names
and do not modify the seven admin objects described here. Current local renders
therefore contain platform 50 objects including shared CRDs and service 7 objects;
disabling discovery restores platform 47 and service 4, with whole-object equality.
The new route permits only exact GET realm discovery, reuses the existing named
Service ReferenceGrant and cannot render without that grant's admin opt-in.
The added service `CiliumNetworkPolicy/keycloak-owner-enrollment-prometheus-ingress`
mirrors the narrow L7 Prometheus scrape rule (`monitoring/kube-prometheus-stack-prometheus`,
TCP 19001, `GET ^/stats/prometheus$`).
There is no new admin/login path, Application, DNS publication or credential.

The sealed admin regression helper now explicitly disables discovery; fixed admin
specs, security mutations and whole-object digests are unchanged. The separate
owner suite checks the same full seven-object contract with discovery enabled and
that only its exact six objects are added. Real lint/template source checks do
not replace the pinned Helm 4.2.1 CI or parent-owned runtime gates below.

## Exact private path

- `Gateway/envoy-gateway-system/keycloak-admin-private`는 기존 `GatewayClass/envoy`를 사용합니다. 새 GatewayClass를 만들거나 기존 class에 `parametersRef`를 넣지 않습니다. (공용 `Gateway/kkamji`의 `EnvoyProxy/kkamji-public`과 컨트롤러 `extensionApis.enableBackend: true`는 공용 런타임 선행 조건으로 분리되어 있으며 private 7개 보안 객체 계약은 변경하지 않습니다.)
- 해당 Gateway의 `infrastructure.parametersRef`만 동일 namespace의 전용 `EnvoyProxy/keycloak-admin-private`를 가리킵니다. Envoy Gateway v1.8.1의 per-Gateway 구성을 사용하고 `mergeGateways: false`를 명시합니다.
- listener는 `https` 하나로 exact `sso.kkamji.net`, HTTPS 443, TLS Terminate입니다. `wildcard-kkamji-net-tls`는 같은 namespace의 Secret reference만 사용합니다. Secret/key/certificate를 읽거나 복사/생성하지 않으며 새 Certificate/Issuer, cross-namespace TLS grant와 HTTP/passthrough listener가 없습니다.
- allowedRoutes는 같은 namespace의 HTTPRoute뿐입니다. route의 유일한 parent는 private Gateway의 `https` section입니다. `/` PathPrefix는 이 private parent에서만 admin/master 경로를 포함합니다.
- 유일한 backend는 `Service/keycloak/keycloak-service:8080`, weight 1입니다. route의 group/kind/namespace/weight와 match type을 명시합니다. `ReferenceGrant/keycloak/keycloak-admin-private`는 `envoy-gateway-system`의 HTTPRoute에서 이 named Service로 향하는 참조만 허용합니다.
- private Envoy Service는 `ClusterIP`입니다. replicas 1, concurrency 1, Envoy container requests `100m/128Mi`, limits `500m/256Mi`를 설정합니다. 기존 controller/data-plane image 설정은 바꾸지 않습니다. controller가 추가하는 sidecar와 rollout peak의 실제 자원은 부모가 별도로 인수해야 합니다.
- 전용 proxy Pod의 `kkamji.net/access: keycloak-admin-private` label만 ingress deny 정책이 선택합니다. `policyTypes: [Ingress]`, `ingress: []`이며 egress 정책을 추가하지 않습니다. public proxy나 namespace 전체를 선택하지 않습니다.
- 새 server ingress 정책은 exact Keycloak server labels 네 개를 선택합니다. source namespace와 private proxy owning-Gateway labels 세 개 및 custom access label을 한 peer의 AND 조건으로 요구하며 TCP 8080만 허용합니다. 기존 세 정책은 유지합니다. 관리 9000, DB 5432와 namespace-wide/egress allow-all은 추가하지 않습니다.
- `telemetry.accessLog.disable: true`만 설정합니다. debug/body/header/token logging, bootstrap/extraArgs와 arbitrary Pod patch는 없습니다. 이것은 실제 모든 구성요소의 로그 비노출 증거가 아닙니다.

NetworkPolicy는 additive입니다. 새 deny가 다른 정책의 allow를 취소하지 않으며, port-forward가 CNI에 어떻게 처리되는지도 source model만으로 보장하지 않습니다. 부모가 기존 정책과 실제 label/port를 확인하고 cluster-client 차단 및 loopback port-forward 경로를 각각 시험해야 합니다.

## Private Envoy metrics repair

부모가 전달한 장애는 `job="kubernetes-pods"`의 private Envoy `http://<PodIP>:19001/stats/prometheus` 직접 scrape timeout이며, port-forward에서는 HTTP 200이었습니다. 기존 platform ingress-deny는 private proxy를 선택하지만 기존 service 정책은 Keycloak backend TCP 8080만 허용합니다. metrics ingress 예외는 없었습니다. 이 source 수정은 해당 누락을 복구하는 후보이며, port-forward 성공을 Prometheus/Cilium 경로의 정상 증거로 쓰거나 target을 discovery에서 제외해 장애를 숨기지 않습니다.

추가 객체는 `CiliumNetworkPolicy/envoy-gateway-system/keycloak-admin-private-prometheus-ingress` 하나입니다. 활성화 flag, release/namespace guard와 default-off 계약은 그대로 유지합니다.

- target은 private proxy의 component, owning-Gateway name/namespace, `kkamji.net/access` 네 label을 모두 요구합니다. Cilium label source는 `k8s:`로 명시합니다. namespace 전체나 public proxy를 선택하지 않습니다.
- source는 **한 `fromEndpoints.matchLabels` 안에서** `k8s:io.kubernetes.pod.namespace: monitoring`과 `k8s:io.cilium.k8s.policy.serviceaccount: kube-prometheus-stack-prometheus`를 AND로 요구합니다. 두 peer로 나누는 OR, namespace-only, IP/CIDR, entities와 모든 Pod 허용은 없습니다. 같은 ServiceAccount를 사용하도록 허용된 다른 Pod까지 구분하는 계약은 아니므로 그 ServiceAccount 사용 권한은 별도로 보호해야 합니다.
- 허용 포트는 문자열 `"19001"`, protocol은 `TCP` 하나입니다. Cilium HTTP L7 rule은 method `GET`, path 정규식 `^/stats/prometheus$` 하나만 허용합니다. 경로 접두사/접미사, query가 붙은 다른 request target, 다른 method와 일반 admin API에 대한 예외를 만들지 않습니다. scrape interval, timeout, annotations, Prometheus discovery와 alert rule은 변경하지 않습니다.
- 기존 ingress-deny, private HTTPS 443, proxy 내부 HTTPS listener 10443, Envoy admin 19000, Keycloak 8080/9000과 DB 5432의 접근 범위를 넓히지 않습니다. 기존 private HTTPS/loopback port-forward 절차, public Gateway와 모든 기존 객체는 보존합니다. egress, Service/listener, DNS와 인증서 변경도 없습니다.

공식 [Envoy Gateway v1.8.1 bootstrap](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/bootstrap/bootstrap.go) 기본값은 admin `127.0.0.1:19000`, stats `19001`입니다. [동일 버전의 bootstrap template](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/bootstrap/bootstrap.yaml.tpl)은 stats listener의 exact GET `/stats/prometheus`만 내부 admin cluster로 전달합니다. 따라서 기본 19001을 전체 admin API라고 단정하지 않습니다. 그와 별개로 이번 정책도 L4-only가 아닌 exact L7 allow를 요구하여 bootstrap 변경이나 잘못된 일반 admin 허용으로 확장하지 않습니다. 실제 generated bootstrap의 포트와 경로는 부모가 Secret 값을 읽지 않는 방식으로 재확인해야 합니다.

identity/namespace 의미는 [Cilium v1.19.3 Kubernetes policy 문서](https://github.com/cilium/cilium/blob/v1.19.3/Documentation/security/policy/kubernetes.rst)를 따릅니다. [HTTP API](https://github.com/cilium/cilium/blob/v1.19.3/pkg/policy/api/http.go)의 method/path는 정규식이며 [Envoy translator](https://github.com/cilium/cilium/blob/v1.19.3/pkg/envoy/policy/envoy_l7_rules_translator.go)가 `:method`/`:path` matcher로 변환합니다. pinned Cilium chart/local values의 렌더에는 `enable-l7-proxy: "true"`와 `cilium-envoy` DaemonSet이 있습니다. 이는 live 설정이나 L7 집행 인수가 아닙니다. L7 proxy가 비활성/불능이면 이 조건을 제거하거나 L4 allow-all로 낮추지 않습니다.

### Local verification and merge boundary

현재 Keycloak CI의 Helm `v4.2.1+gd591a19`, Python 3.12, PyYAML/jsonschema 조합을 그대로 사용합니다. [기존 workflow](../../.github/workflows/keycloak-lint.yml)의 chart/test path filter와 `test_keycloak*.py` discovery가 추가 회귀도 실행하므로 별도 배포 job을 만들지 않습니다. `HELM_BIN`은 검증된 Helm 4.2.1 binary를 명시하고 `TMPDIR`, `TMP`, `TEMP`는 소유한 evidence 디렉터리로 지정합니다.

```bash
export PATH=/home/linuxbrew/.linuxbrew/bin:$PATH
# HELM_BIN, TMPDIR, TMP, TEMP를 먼저 소유한 검증 경로로 지정한다.
"$HELM_BIN" version --short
uv run --no-project --python 3.12 --with pyyaml --with jsonschema \
  python -m unittest discover -s tests -p test_keycloak_private_admin.py -v
uv run --no-project --python 3.12 --with pyyaml --with jsonschema \
  python -m unittest discover -s tests -p 'test_keycloak*.py' -v
"$HELM_BIN" lint charts/keycloak-admin-access --strict -n envoy-gateway-system \
  -f charts/keycloak-admin-access/kkamji_local_values.yaml
"$HELM_BIN" template keycloak-admin-access charts/keycloak-admin-access \
  -n envoy-gateway-system --include-crds --skip-tests --kube-version 1.36.1 \
  -f charts/keycloak-admin-access/kkamji_local_values.yaml > /dev/null
git diff --check
python3 docs/_meta/docs_lint.py --root . --base origin/main
```

회귀는 예외 누락 RED와 추가 후 GREEN, default-off 0개/enabled service 4개/combined 7개, exact API/metadata/spec, 잘못된 source identity와 target label, TCP 포트 및 HTTP method/path, 과도한 allow/누락된 L7/namespace-only/SA-only 변형 거절을 확인합니다. baseline과 동일한 release/namespace/Kubernetes version으로 렌더하여 **새 CNP 1개 외 기존 객체 변경/삭제 0개**, platform와 management root 전체 불변을 확인합니다. 모델은 실제 Cilium datapath를 실행하지 않습니다. upstream Cilium v1.19.3 CNP CRD의 원본 schema로 별도 오프라인 검증할 수 있으며, 부분 `anyOf`/`oneOf` branch에 `additionalProperties: false`를 일괄 주입하면 유효한 sibling field까지 거절하므로 원본 schema를 유지해야 합니다. 정확한 추가 필드 금지는 고정 전체 객체 회귀가 별도로 보장합니다.

leaf는 local-only이며 commit/push, live API 조회/쓰기와 Secret 값 읽기를 하지 않습니다. 부모가 전달받은 worktree에서 source diff/evidence를 검토하고 최신 `origin/main`과 충돌 여부를 확인한 뒤, 승인된 이 세 파일만 별도 commit/PR로 게시합니다. 문서 freshness/coupling은 `origin/main...HEAD`를 쓰므로 최종 commit 후 docs lint를 다시 실행하고 required CI를 통과시켜야 합니다. 미커밋 초안의 docs lint 성공은 그 두 gate의 완료가 아닙니다. main 병합과 Argo CD 자동 sync는 부모의 별도 승인/운영 경계입니다.

### Parent-owned production acceptance and rollback

1. `kkamji-lab` context, 실제 Prometheus Pod의 namespace와 `spec.serviceAccountName`, private Envoy의 네 target label, generated bootstrap/annotation의 19001 및 `/stats/prometheus`, Cilium identity label과 L7 proxy readiness를 확인합니다. 같은 target/port를 넓게 허용하는 기존 KNP/CNP/CCNP가 없는지 확인합니다. additive 정책에서는 별도 L4 allow가 이번 L7 제한을 무력화할 수 있습니다.
2. 게시 revision의 `keycloak-admin-access` Application과 CNP 반영/admission, namespace의 Cilium policy import 상태를 확인합니다. chart source schema 검사나 Argo CD Healthy만으로 packet-path 성공을 선언하지 않습니다.
3. Prometheus의 기존 target URL과 job/Pod identity를 그대로 대조하여 active target이 유지되고 `health=up`, `lastError` 비움, 최근 `lastScrape` 갱신과 `up{job="kubernetes-pods",namespace="envoy-gateway-system"}`의 해당 private Pod 값 1을 여러 scrape 주기 확인합니다. 정확한 Pod label 이름은 실제 target labels로 선택합니다. 기존 metric series도 다시 수집되는지 확인합니다. discovery에서 사라진 target이나 alert silence는 복구가 아닙니다.
4. 부모가 승인한 bounded probe로 실제 Prometheus identity의 exact GET 성공과 다른 ServiceAccount/namespace의 19001 차단, 같은 identity의 443/10443/19000 차단 및 19001의 다른 method, `/config_dump`, `/server_info`, `/stats`, 접두사/접미사 경로 거절을 확인합니다. 위험한 admin mutation 요청은 보내지 않습니다. HTTP 404만으로 Cilium L7 거절을 입증하지 말고, 정책 drop/deny 또는 Cilium L7 verdict와 함께 구분합니다. 기존 private trusted HTTPS port-forward와 public route/DNS도 재검증합니다.
5. 실패 시 새 CNP만 제거하는 Git 역변경을 검토합니다. 기존 proxy deny 정책은 남겨 private HTTPS 격리를 보존하며 scrape 장애가 돌아올 수 있음을 명시합니다. CNP 제거, 수정된 테스트 계약과 문서는 하나의 별도 reviewed change로 처리합니다. backend/DB/PVC/Secret 삭제, 정책 전체 해제, 알림 억제와 target 제외로 되돌리지 않습니다.

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

`tests/test_keycloak_private_admin.py`는 real Helm render/lint, default off와 enabled 3+4, 기존 public 43개 객체의 고정 digest, 이전 root 16개 전체 객체의 고정 digest, exact refs/selectors와 위험 변형을 검사합니다. 잘못된 namespace/release/flag/추가 private 필드는 schema on/off로 거부합니다. EnvoyProxy는 기존 pinned vendor CRD schema로 확인합니다. 고정 DNS truth table과 additive NetworkPolicy model은 Go 실행이나 CNI enforcement가 아닙니다. 전체 canonical `test_keycloak*.py` suite는 기존 syncPolicy literal 및 root-fixture mutation 회귀도 유지합니다.

부모의 검토/승인 후 실제 생성된 private proxy Service를 identity/labels로 확인하고, loopback에만 kubectl port-forward하여 검증된 HTTPS를 사용합니다. curl 연결 검사는 `--connect-to sso.kkamji.net:443:127.0.0.1:8443`처럼 URL/SNI/Host를 `sso.kkamji.net`으로 유지하는 방식이 가능합니다. 인증서 검증을 끄거나 raw backend HTTP로 credential을 보내지 않습니다. 실제 브라우저의 origin/redirect, 인증과 owner/MFA 절차는 부모가 소유합니다. 전역 DNS나 public listener를 관리 접근 우회로로 바꾸지 않습니다.

남은 gate는 실제 API admission/Accepted/ResolvedRefs, generated ClusterIP/labels, public route/DNS 비간섭, 일반 cluster-client 차단, 부모 port-forward와 trusted HTTPS, 인증서 검증 실패 control, 실제 로그 privacy, DB negative/downgrade/CA uptake, owner/MFA/복구와 UI7입니다. 이 source 후보는 어느 gate도 실제 통과했다고 주장하지 않습니다. 임의 realm/client/owner 생성이나 기존 인증 전환은 하지 않습니다.

철회도 두 GitOps 소유자의 prune 영향과 순서를 부모가 검토해야 합니다. service access를 먼저 닫고 private platform infrastructure를 제거하는 source 역변경을 검토하되 기존 public Gateway/class, wildcard Secret/Certificate, Keycloak/DB/PVC와 기존 인증은 삭제하지 않습니다.

관련 정본: [Gateway ownership](../rules/gateway-api-routing.md), [Keycloak 단계](../05_oidc-idp-preparation.md), [DB public CA](03_db-public-ca-supply.md).


The owner-approved attended Hindsight epoch4 window updates only the exact automation-root snapshot for its temporary synthetic overlay. Keycloak management/personal roots and security contracts remain unchanged. The paired closure restores the original private-only snapshot; no assertion is skipped.


The attended Hindsight epoch4 closure restores the automation-root snapshot to its original private-only configuration. Keycloak management/personal roots and security contracts remain unchanged.

The prepared attended Hindsight epoch5 window changes only the automation-root snapshot for the existing temporary synthetic overlay. Keycloak management/personal roots and all security assertions remain unchanged. The paired closure restores the exact private-only snapshot. This source preparation does not open the route.

The prepared epoch5 closure restores the automation-root snapshot exactly to its original private-only value. No Keycloak management/personal roots or security assertions change.

The prepared Hindsight epoch6 fresh-DCR window updates only the automation-root snapshot for its existing temporary synthetic overlay. All Keycloak management/personal roots and security assertions remain unchanged. Paired closure restores the exact private-only snapshot; no assertions are skipped.

The prepared epoch6 closure restores the exact private-only automation-root snapshot. Existing Keycloak management/personal roots and security assertions remain unchanged.

The prepared epoch7 open updates only the exact automation-root snapshot for the temporary synthetic overlay. All Keycloak management/personal roots and security assertions remain unchanged.

The prepared epoch7 close restores the exact automation-root snapshot for the temporary synthetic overlay. All Keycloak management/personal roots and security assertions remain unchanged.

The 2026-11-22 hindsight-dot retirement disables `hindsight-dot-staging`, so the automation-root snapshot drops from 10 to 9 Application objects and only that count and digest change. Keycloak management/personal roots and security assertions remain unchanged.

The 2026-11-22 Stage 1 security-observability activation adds `security-observability` (`trivy-operator` and `tetragon` remain `enabled: false`), bringing the automation-root snapshot from 9 to 10 Application objects while keeping the 9 existing automation Applications, Keycloak management/personal roots, and security assertions unchanged.
