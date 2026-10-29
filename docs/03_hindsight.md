---
title: Private Hindsight deployment and operations
updated: 2026-10-29T20:13:22+09:00
type: runbook
status: current
---

# 개인용 Hindsight

## 상태와 범위

2026-10-27에 승인된 `kkamji-lab` 배포, 도메인, 전용 UI/API/MCP 인증과 합성 인수를 완료했습니다. 구독 retain/recall, OAuth 갱신의 PVC 저장, seed 삭제 후 Pod 재생성과 추가 구독 호출을 실제 확인했습니다. 실제 대화 자동 수집, 프로젝트 hook, 전역 Hermes/Claude Code 통합은 켜지 않았습니다. 아래 잔여 High 취약점과 관리자/키 신뢰 경계는 기능 인수 성공과 별개로 유지됩니다.

- 서비스 차트는 [charts/hindsight](../charts/hindsight)입니다. root Application 연결은 `automation-root`의 승인된 변경으로 반영하며, `main` 반영과 자동 sync는 실제 배포 경계입니다.
- 새 Hindsight 전용 ChatGPT SIWC 로그인만 사용합니다. 기존 Hermes/Codex credential을 읽거나 복사하지 않으며, 전역 agent 설정/hook, 실제 대화 ingestion과 범용 model proxy는 추가하지 않습니다.
- DB와 embedding은 로컬에 두지만 retain에서 추출할 **본문은 OpenAI로 전송됩니다**. 외부 전송이 없는 시스템으로 소개하지 않습니다.

## Runtime과 저장소

| 구성 | 고정값과 이유 |
|---|---|
| API/worker/DB | AIO 보안 파생 후보 `ghcr.io/kkamji98/hindsight-security:1.1.0-20261029@sha256:99f91e62f5e870d91a2e03bb3fce695541dff694dac6dcdb692319f462060074`, embedded pg0. [빌드 및 서명 절차](../images/hindsight-security/README.md)를 따릅니다. |
| UI | upstream Hindsight chart `1.1.0`, alias `server`의 Control Plane(CP). [values](../charts/hindsight/values.yaml)의 별도 공식 digest를 사용합니다. |
| vendor | [hindsight-1.1.0.tgz](../charts/hindsight/charts/hindsight-1.1.0.tgz), SHA256 `5199851d7c998c14517d43d70d15f5c87756388acc8128621fd3504c77c275bd`. Chart.lock의 dependency digest와 archive checksum은 서로 다른 값입니다. |
| writer | API StatefulSet 1 replica, OrderedReady. upstream API Deployment/독립 worker/PostgreSQL은 비활성입니다. surge, 강제 Pod 삭제나 병렬 OAuth writer를 허용하지 않습니다. |
| PVC | `hindsight-data` 8Gi(DB), `hindsight-chatgpt` 1Gi(auth), `hindsight-models` 2Gi(model). `local-path`, 선택 노드 `k8s-w2`입니다. |
| LLM | canonical `kkamji-settings/agents/hermes/model-lane.sh`에서 생성한 [local values](../charts/hindsight/kkamji_local_values.yaml)를 따릅니다. 현재 생성값은 `gpt-6.1-sol` / `xhigh`이며 별도 tuning/fallback을 추가하지 않습니다. |
| embedding | `intfloat/multilingual-e5-small`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, ONNX CPU, 384차원, 최대 512 token, mean pooling + L2 정규화, `query: ` / `passage: ` prefix입니다. |
| recall | RRF를 baseline으로 사용합니다. 별도 neural reranker나 외부 embedding API를 암묵적으로 추가하지 않습니다. |

public model 준비 Job은 정확한 revision과 파일 checksum을 검증하고 model PVC만 기록합니다. auth/DB/Secret을 mount하지 않습니다. API는 model PVC를 읽기 전용으로 사용하고 offline mode로 시작합니다. 완료한 model 디렉터리를 다른 revision으로 덮어쓰지 않습니다. 실패한 Job은 자동 재시도하지 않으며 원인을 확인한 뒤 승인된 재실행으로 복구합니다.

PVC는 Argo prune/delete 방지 선언을 사용하지만 namespace/노드 삭제, 관리자 작업이나 디스크 장애를 막지는 못합니다. `local-path`는 HA/원격 백업이 아니며 요청 용량이 filesystem quota임을 보장하지 않습니다. 배포 전에 노드 여유와 StorageClass를 확인합니다. 별도 오프호스트 백업과 복원 검증을 구성하지 않으면 노드 디스크 장애까지 복구할 수 있다고 주장하지 않습니다.

## 접근과 신뢰 경계

2026-10-29에 아래 접근 고도화를 배포하고 소유자 UI 로그인, API 인증 조합, WSL CLI의 실제 recall을 검증했습니다. 뒤의 2026-10-27 인수표는 이전 BasicAuth/shared Gateway key 배포의 기록입니다. Route 53, 공유 Gateway/listener, workload, PVC, 모델 설정, native 인증과 Cilium 정책은 변경하지 않았습니다. Cloudflare와 Tunnel은 사용하지 않습니다.

| 경로 | Gateway 인증 | native 인증 |
|---|---|---|
| `https://hindsight.kkamji.net/` UI | Google OIDC, cookie JWT and exact owner email RBAC | Existing CP access key |
| Same host `/v1` API, `/mcp` MCP | Per-client raw key in `X-Hindsight-Client-Key` | Existing Hindsight API key via the `Authorization` Bearer scheme |

UI access key와 API key는 서로 다릅니다. CP는 서버 측에서 API key를 소비합니다. API route의 Gateway 인증은 native 검사를 대체하지 않으며, CP의 browser backend도 native access key로 보호합니다. 키를 가진 사람과 관리자까지 차단하는 절대적인 "나만 접근" 보장이 아닙니다. namespace나 bank 이름은 ACL이 아닙니다.

The UI policy uses Google issuer `https://accounts.google.com`, JWKS `https://www.googleapis.com/oauth2/v3/certs`, and public client ID `47443292322-rlsttvfbbvbp3lg5icerudodded0i7ev.apps.googleusercontent.com` for both OIDC and the JWT audience. An empty, missing or different client ID fails Helm rendering when exposure is enabled. JWT reads only `HindsightGoogleIdToken`; default-deny RBAC permits exactly `email=rlaxowl5460@gmail.com`. Client email/token headers are not authorization inputs. The browser-facing OIDC ID-token cookie is encrypted, host-only and SameSite=Lax. Envoy decrypts token cookies before JWT validation and forwards them toward the trusted CP backend; do not log Cookie headers. API native Authorization is preserved; `forwardIDToken` and `clientIDRef` are not used.

Google must register exactly `https://hindsight.kkamji.net/oauth2/callback`. Callback and `/oauth2/logout` use the same UI catch-all policy, not an unauthenticated bypass route. OAuth callback 302 alone does not prove owner access: a different Google account must receive 403 on the original UI resource. Logout clears the Gateway session, not necessarily the native CP or Google session. Controller discovery and Envoy token/JWKS HTTPS reachability, refresh and expiry require live verification without widening API/CP egress.

The API policy consumes only `X-Hindsight-Client-Key`, sets `sanitize: true` to remove that header, and forwards the authenticated Secret data-key name as `X-Hindsight-Client-ID`, replacing a caller-supplied value. It neither injects nor removes native Authorization. Both credentials are required externally; CP -> API internal calls keep their existing native boundary. Per-client Gateway keys support independent rotation, not native tenant or bank isolation.

요청 본문 제한은 `1Mi`이며 초과 요청은 413으로 거절합니다. 응답 streaming은 buffer하지 않습니다. 후속 후보의 local rate limit은 UI 300회/분, API/MCP 120회/분입니다. Envoy 인스턴스별 token bucket이며 사용자별 전역 quota가 아닙니다. 인증 필터에서 먼저 거절한 요청은 limiter에 도달하지 않으므로 로그인 brute-force 방어라고 주장하지 않습니다. 플랫폼 소유 CRD의 공식 `int32 -> int64` 두 줄 backport를 먼저 반영하고 실제 경계값 admission을 확인한 뒤 Hindsight를 배포합니다.

기존 HTTPRoute response header modifier에 더해 두 route 전용 `EnvoyExtensionPolicy`의 `envoy_on_response`가 HSTS `max-age=86400`, nosniff, Referrer-Policy `no-referrer`만 replace합니다. status, Location, Set-Cookie, body, 요청과 필터 순서는 바꾸지 않습니다. `includeSubDomains`와 `preload`는 사용하지 않습니다. 임시 경로의 OAuth 302/nonce cookie, API 401과 보안 헤더, 타 앱 6개의 응답 불변을 검증했습니다. 첫 Lua slot은 공유 listener를 갱신하므로 본 배포에서 장시간 연결의 재접속도 확인합니다. route 선택 전 TLS/codec 오류까지 보장하는 설정은 아닙니다. 본 경로 적용과 413/429/MCP 재검증은 후속 인수 항목입니다.

`BackendTrafficPolicy.responseOverride`는 사용하지 않습니다. header-only처럼 보여도 새 응답을 만들면서 OAuth Location/Set-Cookie를 없애는 문제가 실제 canary에서 재현됐습니다. 실패 후보와 임시 리소스는 폐기했습니다.

This design is pinned to [Envoy Gateway v1.8.1 filter ordering](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/httpfilters.go), its [OIDC/JWT/RBAC fixture](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/testdata/in/xds-ir/securitypolicy-with-oidc-jwt-authz.yaml), and [Envoy v1.38.1 OAuth2 cookie handling](https://github.com/envoyproxy/envoy/blob/v1.38.1/source/extensions/filters/http/oauth2/filter.cc). API/CRD acceptance alone does not prove runtime filter behavior. The boolean `email_verified` claim is not incorrectly treated as a string; Google `sub` is not guessed. Cookie theft and privileged administrators remain trust boundaries. Do not log Cookie, Authorization or client-key values.

공식 1.1.0의 bank transfer API는 기본 비활성입니다. 합성 자료 복원과 소유자 백업을 위해 `HINDSIGHT_API_ENABLE_DOCUMENT_IMPORT_API`와 `HINDSIGHT_API_ENABLE_DOCUMENT_EXPORT_API`를 명시적으로 켭니다. 기존 Gateway/native API key 검사는 유지하며 무인증 archive 업로드를 허용하지 않습니다.

- TLS는 기존 `Gateway/envoy-gateway-system/kkamji`의 `https` listener와 wildcard 인증서를 재사용합니다. HTTPRoute/SecurityPolicy는 Hindsight 차트 소유이며 플랫폼 차트는 바꾸지 않습니다. [라우팅 규칙](rules/gateway-api-routing.md)을 따릅니다.
- 인증된 UI와 API/MCP route의 request/backendRequest 상한은 각각 `600s`입니다. Envoy의 기본 request 제한은 15초이며 실제 구독 호출은 이를 넘을 수 있습니다. 동기 retain은 연결 종료 시 취소되므로 긴 retain은 `async: true`와 operation 조회를 우선합니다. 이 timeout은 클라이언트/LLM 자체 deadline을 늘리지 않으며 인증이나 외부 egress도 바꾸지 않습니다. [공식 timeout 문서](https://gateway.envoyproxy.io/docs/tasks/traffic/http-timeouts/)를 따릅니다.
- Cilium 설계는 API/CP를 격리하고 Gateway -> UI/API, CP -> API만 허용합니다. API의 외부 egress는 OpenAI HTTPS와 DNS로 제한하며, public model downloader의 다운로드 egress는 auth 없는 별도 경계입니다. 실제 FQDN/DNS 허용과 차단은 live 인수 항목입니다.
- DNS의 내부 검색 suffix는 `**.cluster.local`로 허용합니다. 현재 Cilium CRD에서 `*`는 한 단계만 매칭하므로 `*.cluster.local`은 `hindsight-api.hindsight.svc.cluster.local` 같은 이름을 포함하지 않습니다. 외부 FQDN/포트 허용 목록은 이 내부 DNS 규칙과 분리합니다.
- 고정 ONNX의 다운로드 metadata가 반환한 `us.aws.cdn.hf.co`를 모델 준비 Job에만 DNS와 TCP 443으로 허용합니다. 단일 단계 `*.hf.co`는 이 다중 단계 CDN 이름을 포함하지 않습니다. API/CP의 외부 허용 목록과 `world` 권한은 늘리지 않습니다.
- shared `parameter-store`, 해당 Store를 소비할 수 있는 ExternalSecret 작성자, cluster/namespace 관리자와 key 보유자는 신뢰 범위에 남습니다. 새 IAM/Store를 추가하지 않았다는 사실을 독점 접근 증명으로 해석하지 않습니다.
- 2026-10-29의 동일 Grype 0.121.0/DB v6.1.10 재검사에서 원본 AIO는 Critical 1/High 62, 파생 후보는 Critical 0/High 59입니다. Authlib/dnspython의 대상 advisory 4개를 제거했고 joserfc 의존성만 추가했습니다. OS High 59(58 wont-fix, 1 not-fixed)는 그대로이며 Debian stable 갱신 simulation도 tzdata 외 수정 패키지를 제공하지 않았습니다. CP는 별도 재스캔에서 Critical/High 0입니다. 취약점 ignore는 추가하지 않았습니다.
- 공개 GHCR 파생 digest와 로컬 검사 이미지가 일치하며 전용 로컬 key 서명을 [signing.pub](../images/hindsight-security/signing.pub)로 검증했습니다. upstream 공식 서명이나 공개 transparency-log 인증이 아닙니다. 서명과 취약점 검사는 별개이며, 기존 OS 위험과 압축된 pg0 library/PVC cache의 검증 한계는 남습니다.

## 2026-10-29 후속 보안 후보와 계정 점검

- authlib 1.9.1, dnspython 2.9.0, 새 의존성 joserfc 1.6.8만 변경했습니다. API source/schema, Python, pg0, ONNX, CP, 모델과 provider는 유지합니다. `uv pip check`, 정상/위조 서명 회귀와 격리 pg0 재시작을 검증했습니다. 공식 원본과 승인된 파생 digest만 공통 guard로 허용합니다. 새 image는 model Job 이름도 바꾸므로 기존 공개 모델 checksum을 재확인하는 Job이 선행합니다. model Job은 DB/auth PVC에 접근하지 않습니다.
- source 후보와 image 게시를 운영 rollout 완료로 해석하지 않습니다. 실제 적용 뒤 단일 writer 종료/기동, PVC UID와 seed 부재, CP/API/MCP, E5 recall, 같은 provider의 합성 retain과 auth 저장 경계를 확인합니다. 이전 OAuth snapshot으로 rollback하지 않습니다.
- Google 계정 보안 화면에서 소유자의 2단계 인증 활성화와 패스키 등록을 읽기 전용으로 확인했습니다. 계정 설정은 변경하지 않았습니다. 기존 Google 세션 재사용은 매 Hindsight 접속마다 MFA challenge가 발생한다는 뜻이 아닙니다. CP access key와 Google 로그인을 합쳐 MFA라고 부르지 않습니다.
- 실제 다른 개인 Google 계정의 로그인 시험은 사용자가 직접 로그인하는 단계입니다. 회사 계정은 사용하지 않았으며, 403 실제 확인 전에는 완료로 표시하지 않습니다.

## 2026-10-29 최초 접근 고도화 인수 (후속 계정 점검 이전)

- 최초 인수에서는 Google 개인 계정과 기존 CP access key로 `/dashboard` 진입을 확인했고, 다른 계정/MFA는 시험하지 않았습니다. 이후 위 후속 계정 점검에서 Google 2단계 인증 활성 상태를 읽기 전용으로 확인했습니다. 계정 설정 변경이나 매 접속 시 MFA challenge를 검증했다는 뜻은 아닙니다.
- 외부 API는 키 없음, native 키만 있음, Gateway 키만 있음, 각각 잘못된 키의 다섯 조합에서 모두 401을 반환했습니다. 네 클라이언트 키는 올바른 native 키와 함께 각각 200을 반환했습니다.
- `1Mi` 초과 요청은 413으로 차단됐습니다. HTTP 인증/크기 검사 14개를 통과했습니다. 요청 빈도 제한과 인증 응답 HSTS 누락은 위에 명시한 잔여 항목입니다.
- 실제 xDS에서 OAuth2 -> JWT -> buffer -> RBAC 순서와 API의 `X-Hindsight-Client-Key` 추출, credential 제거, 검증된 `X-Hindsight-Client-ID` 전달을 확인했습니다. admin config 원문은 저장하거나 출력하지 않았습니다.
- WSL Claude Code는 등록한 headersHelper를 사용해 실제 `mcp__hindsight__recall`을 한 번 호출했고 합성 문서 `f01`을 조회했습니다. Hermes도 native MCP registry/dispatcher에서 같은 문서를 조회했습니다. Hermes는 `tools.include: [recall]`, `tools.resources: false`, `tools.prompts: false`로 실제 노출 도구가 recall 하나임을 검증했습니다.
- 실행 중인 Hermes gateway와 기존 TUI는 재시작하지 않았습니다. 새 TUI에서 설정을 읽습니다. 자동 대화 ingestion과 retain hook은 활성화하지 않았습니다. 초기 연결 bank는 `poc_korean_a_20261026_113238`이며 실제 개인 기억의 저장 범위는 별도로 정합니다.
- Mac용 전용 키와 실행 지침을 로컬에서 준비했습니다. Mac 실기 적용은 하지 않았습니다. 지침은 `/home/kkamji/.local/share/hindsight-k8s-private/MAC-SETUP.md`이고, 비밀값 없는 helper는 같은 디렉터리의 `claude-headers.py`입니다. Mac에는 Google client secret이나 ChatGPT OAuth PVC 내용을 복사하지 않습니다.
- 임시 SSO 검증 route/policy와 관리용 port-forward는 제거했습니다. 전용 SSM과 새 OAuth client는 운영 자산으로 유지합니다.
- Kubernetes가 기본 주입하는 `clientSecret.group/kind`, `refreshToken: true`, `remoteJWKS.cacheDuration: 300s`를 소스에 명시합니다. 수정 전후 server-defaulted spec이 동일함을 확인했으며, 인증 동작 변경 없이 Argo SSA drift를 해소하는 변경입니다.

## Secret과 OAuth 소유권

Edge credentials use a separate SecureString JSON at `auth.edgeSsmKey=/kkamji/automation/hindsight/edge-auth`. `hindsight-google-oidc` maps `client-secret` from `oidc_client_secret`; `hindsight-gateway-client-keys` maps exactly `wsl_claude`, `wsl_hermes`, `mac_claude`, `mac_hermes` to identically named properties. Each client key must be independent and high entropy. The new ExternalSecrets render only with exposure enabled, use the existing `parameter-store`, explicit property mappings, Opaque targets and Orphan/Retain. SSM version 1 metadata, both ESO readers' Ready state, exact target/source equality without value output, and owner Google login were verified. No credential value belongs in the chart.

The original `auth.ssmKey` and all four existing ExternalSecrets stay unchanged for native consumers and rollback. The old Gateway UI/API Secrets are not referenced by the candidate SecurityPolicies. Rollback is a reviewed Git reversal, not an automatic BasicAuth fallback on OIDC failure, and must not reset native keys or the refreshed ChatGPT PVC.

To revoke one client, rotate only its edge JSON property to a new independent value and verify ESO reconciliation plus rejection of the old key. Removing a required SSM property or deleting an Orphan/Retain ExternalSecret can leave the previous Kubernetes Secret active; neither action proves revocation. Verify the other three client keys and native authentication remain valid. Do not dump Secret data during checks. Google UI OIDC is separate from the existing ChatGPT model OAuth authority below.

SSM `/kkamji/automation/hindsight/access`는 이미 존재하는 **SecureString version 2**입니다. JSON property는 `api_key`, `ui_access_key`, `ui_htpasswd`입니다. 재생성하거나 임의 초기화하지 않습니다. agent의 describe/write 권한과 Get 거부 상태에서 metadata를 확인했으며, IAM은 바꾸지 않았습니다. The four original ESO readers were verified SecretSynced/Ready with target Secrets in the previous deployment; this is not evidence for the two new edge readers. 외부 HTTPS UI/API/MCP와 native API/MCP의 무인증/오키 거절 및 소유자 성공을 확인했습니다. CP의 cookie 없는 backend 조회도 거절됩니다.

[ESO 규칙](rules/external-secrets.md)에 따라 기존 `parameter-store`를 사용하고 필요한 property만 명시적으로 매핑합니다. target은 Orphan/Retain입니다. API/CP runtime Secret과 Gateway용 Secret을 구분합니다. Legacy rollback keeps the high-entropy `{SHA}` htpasswd and raw shared API key; the candidate uses the separate edge credentials above. 사람이 외우기 쉬운 비밀번호나 다른 서비스의 htpasswd를 재사용하지 않습니다.

소유자 전달 파일은 `/home/kkamji/.local/share/hindsight-k8s-private/owner-access.json`의 mode 0600 파일입니다. 승인된 이전과 인증 검증에서는 부모 프로세스만 필요한 Hindsight 전용 값을 메모리에서 소비합니다. worker에게 전달하거나 콘솔/문서/CI/일반 로그/셸 인자에 출력하지 않습니다. 다른 앱의 credential은 읽지 않습니다. metadata 존재 확인은 property 내용이나 HTTP 인증 성공 검증이 아닙니다.

OAuth의 운영 authority는 writable auth PVC의 `/auth/chatgpt/credentials.json`과 `host_id`입니다. 다음 순서를 지킵니다.

1. 이미 로그인한 **Hindsight 전용** SIWC의 두 파일만 이전 대상으로 확정합니다. 다른 앱의 home이나 credential 디렉터리를 통째로 가져오지 않습니다.
2. WSL 로컬 writer를 먼저 정지하고 종료를 확인합니다. cluster writer와 refresh 권한을 동시에 사용하지 않습니다.
3. 승인된 보안 입력 경로로 임시 `hindsight-chatgpt-seed` Secret을 만듭니다. bootstrap은 빈 auth home에만 한 번 설치하고 directory 0700/file 0600, runtime 소유자와 필수 grant/host 일치를 검사합니다. 유효한 PVC가 있으면 이를 검증하고 재사용하며 stale seed로 덮어쓰지 않습니다. 손상된 기존 home도 자동 초기화하지 않습니다.
4. 실제 합성 호출과 재시작 후 auth/DB 지속성을 확인한 다음 seed Secret을 삭제합니다. 이후 재시작은 seed 없이 현재 PVC로 성공해야 합니다. seed 삭제 전후의 결과를 따로 기록합니다.

회전과 재로그인도 단일 writer/현재 authority 보존 원칙을 따릅니다. access key 회전은 SSM/ESO와 Pod 소비 방식, Gateway/native 인증을 함께 점검하는 별도 승인 작업입니다. SSM 변경만으로 기존 Pod 환경변수가 갱신됐다고 가정하지 않습니다.

## 로컬 검증

저장소 루트에서 실행합니다. vendored dependency를 다시 받지 않으며 출력에 credential을 넣지 않습니다.

```
helm lint charts/hindsight -n hindsight -f charts/hindsight/kkamji_local_values.yaml
helm template hindsight charts/hindsight -n hindsight --skip-tests --kube-version 1.36.1 -f charts/hindsight/kkamji_local_values.yaml > /dev/null
uv run --no-project --python 3.12 --with pyyaml python -m unittest discover -s tests -p test_hindsight_chart.py -v
python3 docs/_meta/docs_lint.py --root . --base origin/main
```

최종 source/CI의 실제 Python dependency와 Helm renderer를 맞추고, unittest가 **실제 테스트를 실행했는지** 확인합니다. 0 tests, lint/template 성공이나 probe 200은 deployment/model call/auth 성공이 아닙니다. 문서의 freshness/coupling은 최종 커밋 diff로 다시 검사해야 하며 미커밋 초안에서 완료 처리하지 않습니다. 링크/anchor 보완은 [검증 정본](operations.md#validation)을 따릅니다.

로컬 합성 PoC는 14 documents/8 queries에서 top1 6/8, top3 8/8, 재생성 후 recall 26.8ms였습니다. embedding-only 비교의 E5 8/8 대 BGE 1/8은 이 작은 fixture의 결과일 뿐 일반 품질/한국어 성능 우위의 증명이 아닙니다. 클러스터 성능이나 실제 데이터 품질로 확장하지 않습니다.

## 반영과 live 인수 조건

아래 항목은 최종 인수 조건입니다. 위 상태에 기록한 부분 성공과 아직 남은 검증을 구분합니다. 기존에 승인된 Hindsight 대상과 범위에서만 반영하며, 새 권한/대상/데이터 안전성 경계는 먼저 확인합니다. `helm install/upgrade`나 Makefile bootstrap 재실행으로 GitOps를 우회하지 않습니다.

1. `kubectl config current-context`가 `kkamji-lab`인지 확인하고 모든 조회/변경에 context와 namespace를 명시합니다. root/child Application의 실제 namespace/revision, node/storage 여유, CRD/admission, ESO와 Gateway 의존성을 확인한 뒤 대상만 diff/dry-run합니다.
2. 최종 chart/test/문서/Secret scan 결과와 변경 영향을 검토하고 이미 승인된 main 반영 범위에서 진행합니다. 자동 sync로 생성되는 route가 인증 실패 시 fail-closed인지 확인합니다. SSM version 2는 유지합니다.
3. ESO Ready와 정확한 property/target 참조, model 준비 완료, API StatefulSet 단일 writer, CP readiness와 실제 image ID를 확인합니다. OAuth 이전은 위 순서대로 진행합니다. Secret 값 dump나 Pod exec는 하지 않습니다.
4. Verify DNS/TLS, HTTPRoute Accepted/ResolvedRefs, SecurityPolicy and BackendTrafficPolicy status and final route xDS. Confirm the live Envoy version and OAuth2 -> JWT -> RBAC ordering. Requests without a UI session, including spoofed email/token headers, must not bypass OIDC; wrong/tampered/expired/audience-mismatched cookies must not reach CP. Verify owner login, wrong-account resource 403, callback state rejection, logout/refresh/expiry and native CP key denial independently. Do not treat callback 302 as owner acceptance.
5. Verify API/MCP denial with neither key, native key only, Gateway key only and either wrong key. With both valid, verify Gateway key removal, native Authorization preservation and spoofed client-ID replacement without logging values. Exercise all four client identities, bounded 413 behavior, MCP response streaming and HSTS. Test individual revocation when a key is actually rotated; no 429 acceptance is claimed while rate limiting is deferred. Use loopback port-forward for native checks; retain CP native checks and unauthorized-Pod network denial.
6. 전용 synthetic bank에서 retain 작업 완료, 의미 있는 recall과 MCP 요청을 검증합니다. 실제 OpenAI 추출 실패/계정 제한을 숨기거나 다른 model/provider로 우회하지 않습니다. readiness와 retain 접수 200만으로 합격시키지 않습니다.
7. 승인된 Pod 교체 뒤 DB/recall/auth 지속성을 검사하고 seed를 삭제합니다. seed 없는 추가 재시작 성공, refresh 후 현재 PVC 재사용과 단일 writer를 확인합니다. 실 대화 ingestion은 이 인수와 별도 승인입니다.

## 2026-10-27 live 인수 결과

기능 배포 기준은 [timeout 수정 PR 59](https://github.com/KKamJi98/helm-charts/pull/59)의 main `db8822d1cb855fc1c13f4d94a773cb6d7f5fc247`입니다. 최종 문서 커밋은 같은 manifest를 유지합니다.

| 항목 | 실제 확인 |
|---|---|
| GitOps/저장소 | Hindsight `Synced`/`Healthy`, API/CP Ready, model Job의 6개 파일 SHA 검증 완료, PVC 3개 Bound |
| DNS/TLS | 소유자 HTTPS 호출 성공, 시스템 trust와 hostname 검사 활성, TLSv1.3. 관측 인증서 만료는 2027-01-08 UTC이며 자동 갱신은 기존 Gateway 소유입니다. |
| UI HTTP 흐름 | BasicAuth 무인증/오키 401, native CP 로그인 오키 401/소유자 200, dashboard 200. 인증 cookie는 Secure/HttpOnly이며 cookie 없는 CP backend 조회는 401입니다. |
| API/MCP | 외부 Gateway와 loopback native 경로 각각 무인증/오키 401, 소유자 200. 단일 Bearer는 성공하고 이중 Bearer는 거절됩니다. |
| 내부 우회 | 승인되지 않은 Pod에서 API 8888/CP 3000 직접 접속이 차단됐고 Hubble `POLICY_DENIED`를 확인했습니다. |
| 합성 기억 | 원본 14문서를 두 bank로 복원하고 별도 인수 bank에 2문서를 추가했습니다. 3개 bank 총 16문서의 조회와 기대 document recall이 성공했습니다. 일반 품질/성능 benchmark는 아닙니다. |
| 구독 추론 | 동일 `chatgpt` provider의 실제 추출이 성공했습니다. 비동기 operation 완료 뒤 recall, seed 없는 새 Pod의 HTTPS 동기 retain 21.173초 완료와 새 document recall을 확인했습니다. |
| OAuth 지속성 | WSL 원본 writer는 정지했습니다. PVC의 access/refresh 값이 모두 초기 seed와 달라진 상태와 file 0600/home 0700을 값/해시 노출 없이 확인했습니다. seed 삭제 후 새 Pod가 Ready이고 PVC UID 3개와 기존 기억이 보존됐습니다. |
| MCP 공유 | 독립 protocol client 2개가 `2025-11-25`로 연결하고 같은 bank의 `f01`을 recall했습니다. 36개 tool 목록과 recall의 single-bank schema를 확인했으며 실제 Hermes/Claude Code 설정 활성화는 아닙니다. |
| 검증/정리 | 회귀 39개와 Helm/Ruff/strict server dry-run/source secret scan, 독립 검토와 PR/main CI를 통과했습니다. 임시 진단 Pod/정책과 이 작업의 port-forward를 정리했습니다. |

## 복구

먼저 caller를 멈추고 현재 writer, refresh authority, PVC와 마지막 정상 Git/image/config를 확인합니다. reviewed Git 역변경과 Argo sync로 복구하며 DB schema 호환성과 백업을 먼저 검토합니다. namespace/PVC를 지우거나 refreshed auth를 seed로 덮어쓰지 않습니다. 오래된 WSL OAuth snapshot을 그대로 다시 시작하지 않습니다. 로컬로 되돌려야 한다면 cluster writer 종료 후 현재 auth authority를 승인된 경로로 이전해야 합니다.

ESO 오류는 Store/ExternalSecret 상태와 property 참조부터, 401/403은 Gateway와 native 인증을 나누어, model 오류는 Job/checksum/허용 egress부터 조사합니다. auth init 실패는 seed 부재와 기존 PVC 손상을 구분합니다. 값 조회, IAM 확대, force delete나 무관한 서비스 재시작으로 우회하지 않습니다.
