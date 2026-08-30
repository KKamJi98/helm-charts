---
title: Gateway API routing rules
updated: 2026-08-31
type: rule
status: current
---

# Gateway API routing rules

플랫폼 차트(`charts/envoy-gateway`)와 서비스 차트의 소유 경계, 신규 서비스 온보딩 절차,
ArgoCD SSA diff 방지 규칙이다.

- 플랫폼(charts/envoy-gateway)은 GatewayClass/Gateway(리스너)/https-redirect/wildcard Certificate 만 소유한다. HTTPRoute 는 각 서비스의 umbrella 차트 templates/ 또는 upstream 차트 기능이 소유한다 (kps·cilium, play-hub 는 자기 repo). TLSRoute/ssl-passthrough 는 2026-08-31 폐지됐다.
- 신규 서비스 온보딩: 자기 차트에 HTTPRoute 추가 - parentRef {name: kkamji, namespace: envoy-gateway-system, sectionName: https}. TLS 종료는 플랫폼 wildcard 리스너가 담당하므로 백엔드는 plain HTTP(대개 80)로 서빙한다. 리스너/인증서 변경 불필요.
- ArgoCD SSA diff 방지: route 매니페스트에 API server defaulting 필드(parentRefs/backendRefs 의 group·kind·weight, filter-only rule 의 기본 match)를 명시한다.
- 같은 443 포트에 protocol TLS(passthrough) 리스너를 HTTPS 리스너와 병행하지 않는다. Envoy Gateway 의 hostname intersection 계산이 깨져 신규 HTTPRoute 가 NoMatchingListenerHostname 으로 Accepted=False 가 된다 (2026-08-31 argocd 전환 사례). passthrough 가 필요하면 별도 포트를 사용한다.
- external-dns 의 gateway 소스는 target annotation 을 HTTPRoute 가 아닌 **Gateway** 에서 읽는다. Gateway 의 target annotation 이 빠지면 A 레코드가 내부 LB IP 로 덮여 외부 접근이 끊긴다.
- basic auth 는 Envoy SecurityPolicy 로 적용한다 ({SHA} htpasswd 만 지원 - basic-auth secret 의 .htpasswd 키 <- SSM /kkamji/monitoring/ingress/basic-auth-sha).
- 인증서: letsencrypt-prod 는 DNS-01(route53, zone 한정 cert_manager IAM user) 단일 solver 다. wildcard(*.kkamji.net) 인증서는 DNS-01 로만 발급된다.
