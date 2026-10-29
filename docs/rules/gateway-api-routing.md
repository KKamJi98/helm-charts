---
title: Gateway API routing rules
updated: 2026-10-29T19:34:10+09:00
type: rule
status: current
---

# Gateway API routing rules

플랫폼 차트(`charts/envoy-gateway`)와 서비스 차트의 소유 경계, 신규 서비스 온보딩 절차,
ArgoCD SSA diff 방지 규칙이다.

- 플랫폼(charts/envoy-gateway)은 GatewayClass/Gateway(리스너)/https-redirect/wildcard Certificate 및 vendored dependency의 공유 Gateway CRD를 소유한다. HTTPRoute 는 각 서비스의 umbrella 차트 templates/ 또는 upstream 차트 기능이 소유한다 (kps·cilium, play-hub 는 자기 repo). TLSRoute/ssl-passthrough 는 2026-08-31 폐지됐다.
- 신규 서비스 온보딩: 자기 차트에 HTTPRoute 추가 - parentRef {name: kkamji, namespace: envoy-gateway-system, sectionName: https}. TLS 종료는 플랫폼 wildcard 리스너가 담당하므로 백엔드는 plain HTTP(대개 80)로 서빙한다. 리스너/인증서 변경 불필요.
- ArgoCD SSA diff 방지: route 매니페스트에 API server defaulting 필드(parentRefs/backendRefs 의 group·kind·weight, filter-only rule 의 기본 match)를 명시한다.
- 같은 443 포트에 protocol TLS(passthrough) 리스너를 HTTPS 리스너와 병행하지 않는다. Envoy Gateway 의 hostname intersection 계산이 깨져 신규 HTTPRoute 가 NoMatchingListenerHostname 으로 Accepted=False 가 된다 (2026-08-31 argocd 전환 사례). passthrough 가 필요하면 별도 포트를 사용한다.
- external-dns 의 gateway 소스는 target annotation 을 HTTPRoute 가 아닌 **Gateway** 에서 읽는다. Gateway 의 target annotation 이 빠지면 A 레코드가 내부 LB IP 로 덮여 외부 접근이 끊긴다.
- basic auth 는 Envoy SecurityPolicy 로 적용한다 ({SHA} htpasswd 만 지원 - basic-auth secret 의 .htpasswd 키 <- SSM /kkamji/monitoring/ingress/basic-auth-sha).
- 인증서: letsencrypt-prod 는 DNS-01(route53, zone 한정 cert_manager IAM user) 단일 solver 다. wildcard(*.kkamji.net) 인증서는 DNS-01 로만 발급된다.

## 공유 CRD의 1.8.1 한정 backport

`argocd/envoy-gateway` Application이 `BackendTrafficPolicy` CRD의 GitOps 소유자다. 서비스 차트에 동일 CRD를 복사하거나 일회성 kubectl patch로 수정하지 않는다. 이 CRD는 클러스터 공유 자산이며 Hindsight만의 schema가 아니다.

pristine vendor 원칙의 예외는 `charts/envoy-gateway/charts/gateway-helm-1.8.1.tgz` 안의 다음 member 하나뿐이다.

```text
gateway-helm/charts/crds/crds/generated/gateway.envoyproxy.io_backendtrafficpolicies.yaml
```

- upstream [v1.8.2 CRD](https://github.com/envoyproxy/gateway/blob/v1.8.2/charts/gateway-helm/charts/crds/crds/generated/gateway.envoyproxy.io_backendtrafficpolicies.yaml)와 byte 동일한 두 줄 수정이다. 근거는 [PR #9377](https://github.com/envoyproxy/gateway/pull/9377), commit `6916245861c10bb5ec3a2f1b3b667cf7d1c0a1bb`이다.
- `v1alpha1`의 `spec.rateLimit.global.rules[].limit.requests.format`과 `spec.rateLimit.local.rules[].limit.requests.format`만 `int32`에서 `int64`로 바꾼다. `minimum: 1`, `maximum: 4294967295`, CEL, version/scope/storage/conversion은 보존한다. Kubernetes 1.36의 signed int32 범위와 maximum 충돌을 해결하며 quota 범위를 확대하지 않는다.
- 수정 패키지는 upstream 원본이 아니다. `Chart.yaml`, `Chart.lock` dependency는 1.8.1을 유지한다. lock digest는 archive checksum이 아니므로 바꾸지 않는다. controller/data-plane 이미지, 다른 archive member와 tar header/padding, 전체 일반 workload 렌더는 그대로다.

| 대상 | SHA256 |
|---|---|
| 원본 1.8.1 tgz | `251a38715d533bdce2ed11fa5d6c6663a80222a3b170adf1fe7a48d6fe0f0087` |
| 원본 CRD member | `dc4eabbf2c9393355e30e35f2976f4ed2c09f9b69e9c4419509c2ba5d0b8bbd1` |
| backport CRD member, 공식 v1.8.2와 동일 | `3b285efcb7d8f9c292f386528d83a61bd719d992a67f9c48a848353f10655e66` |
| backport tgz | `5a632f35e784ba58938d7a360745c3d3e71a290244ee01aa22584dba8c5b06d8` |

### 재생성과 회귀 검사

patch의 정본은 [patch_envoy_gateway_crd.py](../../scripts/patch_envoy_gateway_crd.py)의 `OLD`/`NEW`와 hash guard다. 별도 원본 archive나 전체 CRD 복제본을 추가하지 않는다. script는 네트워크/클러스터에 접근하지 않고 1 MiB 압축/4 MiB tar 읽기 한도와 전체 tar/member hash를 검사한다. 정확한 원본 또는 정확한 backport만 허용하며 두 줄의 동일 길이 치환으로 나머지 tar bytes를 보존한다. gzip은 filename 비움, mtime 0, compression level 9로 정규화하고 atomic replace한다. 반복 실행은 byte 동일하다.

```bash
# make deps가 원본 1.8.1을 다시 받았을 때만 재적용한다.
python3 scripts/patch_envoy_gateway_crd.py
# 검사는 파일을 수정하지 않으며 backport 유실/비정규 패키지를 거부한다.
python3 scripts/patch_envoy_gateway_crd.py --check
uv run --no-project --python 3.12 --with pyyaml python -m unittest discover \
  -s tests -p test_envoy_gateway_crd.py -v
```

[전용 CI](../../.github/workflows/envoy-gateway-lint.yml)는 check, Helm 4.2.1 lint/render(`--include-crds --skip-tests --kube-version 1.36.1`), 재생성 byte equality와 전체 렌더 두 줄 diff를 검증한다. 테스트는 기존 Git blob `a4c644ef9e52cfbccbaa6e357cb2f09ac738b2ab`을 원본 fixture로 읽으므로 full Git history가 필요하다. 알 수 없는 vendor/부분 수정/크기 초과는 실패해야 하며 hash를 자동 갱신해 우회하지 않는다. 압축 도구 변경으로 재현성이 깨져도 자동 정규화하여 CI를 통과시키지 말고 원인을 검토한다.

### 반영 순서와 제거 조건

1. 공유 CRD 변경을 먼저 GitOps 반영하고 Application revision/sync, live local/global format과 범위, UID/storedVersions 및 기존 buffer-only policy의 상태 보존을 확인한다. CRD를 삭제/재생성하지 않는다.
2. 그 다음 Hindsight rate-limit candidate를 server dry-run하고 별도 GitOps 반영한다. 서로 다른 Application의 child sync-wave만으로 선후 관계가 보장되지는 않는다. CRD dry-run은 다음 CR dry-run에 가상 schema를 제공하지 않는다.
3. 실제 수정 schema에서 local/global 각각 `1`, 소규모 정상값, `2147483648`, `4294967295` 허용과 `0`, `-1`, `4294967296`, 소수, 문자열 거절을 확인한다. global runtime 서비스 활성화는 이 검증에 포함하지 않는다. route-local 429/refill 회복, 413, 기존 인증/MCP streaming은 이후 인수한다. source 테스트 통과를 실제 rate limiting 완료로 표시하지 않는다.
4. 공식 chart 1.8.2 이상으로 올리는 별도 변경에서 전체 workload/image diff를 검토하고 이 script, 전용 backport 테스트/CI 및 예외 문구를 제거하거나 정식 chart 검사로 교체한다. 최신 chart에 이 patch를 확장하지 않는다. rollback 시에도 1.36 admission 결함이 재발하므로 단순 int32 복원 대신 새 rateLimit 사용 철회와 수정 schema 보존을 우선 검토한다.
