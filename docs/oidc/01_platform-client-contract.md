---
title: Keycloak OIDC client contract
updated: 2026-11-15T20:58:27+09:00
type: architecture
status: current
---

# Keycloak OIDC client contract

## 현재 상태

Keycloak 기준의 향후 Rust/Axum RP 연동 계약입니다. 플랫폼 코드, DB와 기존 로그인은 변경하지 않았습니다.
선택 제품은 Keycloak 26.8.2이며 제품 선정은 기업 IAM/장기 운영 기준입니다. 런타임 인수 완료를 뜻하지 않습니다.
[IdP 준비 runbook](../05_oidc-idp-preparation.md)과 함께 사용합니다.

## 등록값 제안

- IdP origin: `https://sso.kkamji.net`.
- 전용 realm: `kkamji`. 앱을 관리용 `master` realm에 연결하지 않습니다.
- client ID: `kkamji-platform`, confidential client, Authorization Code Flow + PKCE `S256`.
- issuer: `https://sso.kkamji.net/realms/kkamji`. trailing slash를 임의로 보정하지 않습니다.
- discovery: `https://sso.kkamji.net/realms/kkamji/.well-known/openid-configuration`.
- callback: `https://platform.kkamji.net/api/auth/oidc/callback` 한 개를 정확히 등록합니다.
- post-logout redirect 제안: `https://platform.kkamji.net/login`.
- scope는 우선 `openid`만 사용하고, 필요한 표시 정보에 한해 추가합니다.
- public signup, implicit flow, direct access grants와 불필요한 service account는 켜지 않습니다.

위 값은 제안입니다. DNS, realm, client나 credential을 생성한 상태가 아닙니다.
초기 관리 credential, DB credential과 앱 client secret은 분리합니다. 값은 SSM SecureString과 명시적 Secret 참조로만 제공합니다.
client secret과 소유자 subject는 브라우저나 공개 Git 설정에 넣지 않습니다.

## 서버 측 code 교환과 콜백

1. RP 서버가 일회성 state, nonce와 PKCE verifier를 만들고 10분 TTL의 server-side transaction에 묶습니다.
2. 브라우저에는 식별용 Secure/HttpOnly/host-only/SameSite=Lax 임시 쿠키만 발급합니다.
3. callback은 cookie/state/transaction을 대조하고 한 번만 원자적으로 소비합니다. 만료, 누락과 재사용은 거부합니다.
4. 서버만 authorization code를 교환합니다. timeout/IdP 오류를 구분하며 다른 인증 방식으로 자동 fallback하지 않습니다.
5. algorithm allowlist, 서명, 고정 issuer, audience, 필요한 azp, 만료/발급시각과 nonce를 검증합니다.
6. 검증한 iss + sub를 소유자 allowlist와 대조합니다. 이메일/표시명으로 소유자를 자동 연결하지 않습니다.
7. 승인된 소유자에게 앱 전용 세션을 발급하고 transaction/verifier를 폐기합니다.

Discovery/JWKS는 고정 issuer에서만 가져옵니다. token의 임의 jku/x5u 또는 브라우저 URL을 따라가지 않습니다.
unknown kid의 JWKS 갱신은 제한하며 검증 생략이나 무제한 재시도를 하지 않습니다.
returnTo는 검증된 앱 내부 경로만 허용합니다. 외부 URL, protocol-relative 경로와 header injection을 거부합니다.
callback의 origin은 배포 설정으로 고정합니다. untrusted Host/forwarded header로 만들지 않습니다.
access/ID/refresh token, verifier와 client secret을 URL에 넣지 않습니다.
callback의 code/state는 프로토콜상 query에 오므로 proxy/앱 요청 로그에서 query를 제거하고 일회성 소비와 referrer 정책을 검증합니다.
cookie와 원본 claim도 로그에 남기지 않습니다.
API에는 IdP access token을 브라우저 bearer로 재사용하지 않고 기존 앱 세션을 사용합니다.

## WebAuthn과 인증 진입점

목표는 WebAuthn의 user verification을 필수로 하고 소유자만 앱에 접근시키는 것입니다.
고정 버전에서 `webAuthnPolicyUserVerificationRequirement=required`, RP ID는 `sso.kkamji.net`으로 준비합니다.
passwordless passkeys는 이 password+WebAuthn 후보에서 끕니다. policy만으로 Browser flow 실행이 활성화되지는 않습니다.
REQUIRED WebAuthn은 미등록자를 자동 거부하지 않고 credential 등록을 요구할 수 있습니다.
password 보유자의 최초 등록이 가능한 만큼 소유자는 통제된 접근 경로에서 먼저 등록하고 client는 그동안 비활성으로 유지합니다.

- Browser flow의 cookie SSO, passwordless, recovery, broker와 다른 client가 MFA 우회 경로가 되는지 확인합니다.
- 신규 realm의 public registration은 닫습니다. 관리자 bootstrap 계정과 앱 소유자 계정을 구분합니다.
- SSO Cookie는 Forms를 건너뛸 수 있습니다. 매 로그인 fresh WebAuthn 보장과 혼동하지 않습니다.
- 운영 정책을 바꿀 때 기존 IdP SSO 세션과 앱의 과거 세션을 함께 다룹니다.
- acr/amr는 실제 발급되는 값을 검증한 경우에만 보안 판단에 사용합니다.
- 소유자가 안정된 sso.kkamji.net HTTPS origin에서 기기를 등록합니다. localhost RP 등록을 운영 등록으로 표시하지 않습니다.
- 서로 독립된 복구 수단과 두 번째 credential을 준비하고 실제 분실 복구를 시험합니다.
- 사용자 존재/생체 확인은 소유자의 기기에서 수행합니다. agent가 대신 완료했다고 보고하지 않습니다.

## 앱 세션과 전환

기존 기본 8시간/명시적 remember-me 30일 정책은 구현 시 소스와 함께 재확인합니다.
임의 callback query가 세션 기간을 늘리지 못하도록 사용자 선택을 server-side transaction에 묶습니다.
앱 쿠키의 Secure/HttpOnly/host-only/SameSite=Strict를 유지하고 Lax transaction 쿠키와 구분합니다.
IdP 쿠키의 Domain을 .kkamji.net 전체로 넓혀 앱 간에 공유하지 않습니다.
access/ID/refresh token은 브라우저 저장소에 주지 않습니다.

새 세션은 검증된 subject, 정책 버전과 서버 측 revoke 식별자를 가져야 합니다.
기기별 세션 조회/폐기는 서버가 검증한 principal 범위로 제한합니다.
최종 전환 시 과거 v1 비밀번호 쿠키를 명시적으로 폐기하고 로그인 endpoint도 비활성화합니다.
버튼 숨김이나 IdP MFA 설정 변경만으로 과거 30일 앱 세션이 폐기됐다고 보지 않습니다.
학습, 거래와 문서 데이터는 인증 migration으로 재작성하거나 삭제하지 않습니다.

## 로그아웃과 장애

로컬 로그아웃은 앱 서버의 revoke와 쿠키 제거를 먼저 완료합니다.
SSO 로그아웃 endpoint 제안은 realm의 `/protocol/openid-connect/logout`입니다.
고정 client와 허용한 post-logout redirect만 사용하고, ID token을 URL에 넣지 않는 흐름의 확인 화면/동작을 검증합니다.
로컬 로그아웃을 전역 로그아웃으로 부르지 않습니다.

Back-channel logout을 구현한다면 검증한 issuer/audience/events/sid로 해당 서버 세션만 폐기해야 합니다.
아직 구현하지 않았다면 IdP logout이 모든 앱 쿠키를 즉시 폐기한다고 주장하지 않습니다.
IdP 장애 시 새 로그인은 명확히 실패합니다. 기존 세션은 서명/만료/revoke 검사를 통과한 정책 기간 안에서만 유지합니다.
탈취나 복구 시 전체 기기를 폐기할 수 있어야 하며 자동 password/BasicAuth fallback을 추가하지 않습니다.

## 향후 인수 시험

- 정상 소유자 + WebAuthn user verification, 앱 세션 발급과 보호 API 접근.
- state/nonce/PKCE 변조, transaction 재사용/만료와 cookie 누락 거부.
- 다른 issuer/audience/subject, unsigned/만료 token, algorithm downgrade와 임의 key URL 거부.
- 미등록/타 사용자, 직접 recovery/registration URL과 약한 factor 우회 확인.
- 모바일/PC HTTPS 왕복, Strict 앱 쿠키와 Lax transaction 쿠키 분리.
- 기기 분실, 개별/전체 logout, old-v1 쿠키 거부와 JWKS 회전.
- IdP/DB 장애, timeout, 백업 복구와 민감 정보 로그 비노출.

이 시험은 현재 미실행인 구현/운영 완료 조건입니다. Helm 오프라인 검증에 합산하지 않습니다.

## 공식 근거

- [Keycloak 26.8.2](https://github.com/keycloak/keycloak/releases/tag/26.8.2)
- [Server administration](https://www.keycloak.org/docs/latest/server_admin/index.html)
- [Reverse proxy](https://www.keycloak.org/server/reverseproxy)
- [OIDC Core ID token validation](https://openid.net/specs/openid-connect-core-1_0.html#IDTokenValidation)
