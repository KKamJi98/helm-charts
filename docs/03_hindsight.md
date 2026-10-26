---
title: Private Hindsight deployment and operations
updated: 2026-10-27T03:50:25+09:00
type: runbook
status: current
---

# 개인용 Hindsight

## 상태와 범위

이 문서는 `kkamji-lab`의 `hindsight.kkamji.net`에 UI/API/MCP를 제공하기 위한 설계와 인수 절차입니다. namespace와 ExternalSecret 4개의 bootstrap 및 SecretSynced/Ready 확인을 마쳤습니다. **서비스 Pod와 외부 경로는 아직 배포하지 않았습니다.** `status: current`는 문서의 유효성을 뜻하며, 운영 성공을 뜻하지 않습니다. 로컬 PoC나 ESO 성공을 HTTP 인증, Cilium enforcement나 재시작 지속성 검증으로 대신하지 않습니다.

- 서비스 차트는 [charts/hindsight](../charts/hindsight)입니다. root Application 연결은 `automation-root`의 승인된 변경으로 반영하며, `main` 반영과 자동 sync는 실제 배포 경계입니다.
- 새 Hindsight 전용 ChatGPT SIWC 로그인만 사용합니다. 기존 Hermes/Codex credential을 읽거나 복사하지 않으며, 전역 agent 설정/hook, 실제 대화 ingestion과 범용 model proxy는 추가하지 않습니다.
- DB와 embedding은 로컬에 두지만 retain에서 추출할 **본문은 OpenAI로 전송됩니다**. 외부 전송이 없는 시스템으로 소개하지 않습니다.

## Runtime과 저장소

| 구성 | 고정값과 이유 |
|---|---|
| API/worker/DB | 공식 AIO `ghcr.io/vectorize-io/hindsight:1.1.0@sha256:50311d02b4d5d2b7c5242bd336edf8735df8374eaad496a92f49c83b37d2aa06`, embedded pg0 |
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

| 경로 | Gateway 인증 | native 인증 |
|---|---|---|
| `https://hindsight.kkamji.net/` UI | 전용 BasicAuth, username `kkamji` | 별도 CP access key |
| 같은 host의 `/v1` API, `/mcp` MCP | 전용 API key, `Authorization: Bearer` | Hindsight ApiKeyTenantExtension의 같은 API key |

UI access key와 API key는 서로 다릅니다. CP는 서버 측에서 API key를 소비합니다. API route의 Gateway 인증은 native 검사를 대체하지 않으며, CP의 browser backend도 native access key로 보호합니다. 키를 가진 사람과 관리자까지 차단하는 절대적인 "나만 접근" 보장이 아닙니다. namespace나 bank 이름은 ACL이 아닙니다.

- TLS는 기존 `Gateway/envoy-gateway-system/kkamji`의 `https` listener와 wildcard 인증서를 재사용합니다. HTTPRoute/SecurityPolicy는 Hindsight 차트 소유이며 플랫폼 차트는 바꾸지 않습니다. [라우팅 규칙](rules/gateway-api-routing.md)을 따릅니다.
- Cilium 설계는 API/CP를 격리하고 Gateway -> UI/API, CP -> API만 허용합니다. API의 외부 egress는 OpenAI HTTPS와 DNS로 제한하며, public model downloader의 다운로드 egress는 auth 없는 별도 경계입니다. 실제 FQDN/DNS 허용과 차단은 live 인수 항목입니다.
- shared `parameter-store`, 해당 Store를 소비할 수 있는 ExternalSecret 작성자, cluster/namespace 관리자와 key 보유자는 신뢰 범위에 남습니다. 새 IAM/Store를 추가하지 않았다는 사실을 독점 접근 증명으로 해석하지 않습니다.
- 공식 API/AIO와 CP digest의 signature 검증을 마쳤습니다. 현재 Grype 결과는 API/AIO Critical 0, OS High 59(58 wont-fix, 1 not-fixed), CP Critical/High 0입니다. 잔여 High를 제거하거나 완전한 보안으로 주장하지 않습니다. API는 Gateway와 native 인증 및 namespace 한정 Cilium 정책으로 제한합니다. provenance와 취약점 검사는 별개의 gate입니다.

## Secret과 OAuth 소유권

SSM `/kkamji/automation/hindsight/access`는 이미 존재하는 **SecureString version 2**입니다. JSON property는 `api_key`, `ui_access_key`, `ui_htpasswd`입니다. 재생성하거나 임의 초기화하지 않습니다. agent의 describe/write 권한과 Get 거부 상태에서 metadata를 확인했으며, IAM은 바꾸지 않았습니다. 실제 reader인 ESO 4개는 SecretSynced/Ready와 target Secret 생성을 확인했습니다. 실제 HTTP 인증 검증은 아직 남았습니다.

[ESO 규칙](rules/external-secrets.md)에 따라 기존 `parameter-store`를 사용하고 필요한 property만 명시적으로 매핑합니다. target은 Orphan/Retain입니다. API/CP runtime Secret과 Gateway용 Secret을 구분하며, Gateway API key source는 충분한 entropy가 있는 전용 key입니다. 기존 Envoy는 `{SHA}` htpasswd 형식을 요구하므로 UI 비밀번호는 고엔트로피로 유지합니다. 사람이 외우기 쉬운 비밀번호나 다른 서비스의 htpasswd를 재사용하지 않습니다.

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

아래 서비스 인수 항목은 **배포 후 검증 대기**입니다. namespace/ESO bootstrap의 부분 성공과 구분합니다. 기존에 승인된 Hindsight 대상과 범위에서만 반영하며, 새 권한/대상/데이터 안전성 경계는 먼저 확인합니다. `helm install/upgrade`나 Makefile bootstrap 재실행으로 GitOps를 우회하지 않습니다.

1. `kubectl config current-context`가 `kkamji-lab`인지 확인하고 모든 조회/변경에 context와 namespace를 명시합니다. root/child Application의 실제 namespace/revision, node/storage 여유, CRD/admission, ESO와 Gateway 의존성을 확인한 뒤 대상만 diff/dry-run합니다.
2. 최종 chart/test/문서/Secret scan 결과와 변경 영향을 검토하고 이미 승인된 main 반영 범위에서 진행합니다. 자동 sync로 생성되는 route가 인증 실패 시 fail-closed인지 확인합니다. SSM version 2는 유지합니다.
3. ESO Ready와 정확한 property/target 참조, model 준비 완료, API StatefulSet 단일 writer, CP readiness와 실제 image ID를 확인합니다. OAuth 이전은 위 순서대로 진행합니다. Secret 값 dump나 Pod exec는 하지 않습니다.
4. DNS/TLS와 HTTPRoute Accepted/ResolvedRefs, SecurityPolicy 상태를 확인합니다. UI는 BasicAuth 없음/오류와 CP key 없음/오류를 각각 거절해야 합니다. 올바른 UI 인증으로만 화면이 동작하는지 확인합니다.
5. API/MCP는 key 없음/오류를 외부 경로와 native 경로에서 각각 거절해야 합니다. loopback port-forward를 사용하되 credential을 콘솔에 출력하지 않습니다. CP backend의 native access key 우회 여부와 승인되지 않은 Pod의 API/CP 접근 차단도 확인합니다.
6. 전용 synthetic bank에서 retain 작업 완료, 의미 있는 recall과 MCP 요청을 검증합니다. 실제 OpenAI 추출 실패/계정 제한을 숨기거나 다른 model/provider로 우회하지 않습니다. readiness와 retain 접수 200만으로 합격시키지 않습니다.
7. 승인된 Pod 교체 뒤 DB/recall/auth 지속성을 검사하고 seed를 삭제합니다. seed 없는 추가 재시작 성공, refresh 후 현재 PVC 재사용과 단일 writer를 확인합니다. 실 대화 ingestion은 이 인수와 별도 승인입니다.

## 복구

먼저 caller를 멈추고 현재 writer, refresh authority, PVC와 마지막 정상 Git/image/config를 확인합니다. reviewed Git 역변경과 Argo sync로 복구하며 DB schema 호환성과 백업을 먼저 검토합니다. namespace/PVC를 지우거나 refreshed auth를 seed로 덮어쓰지 않습니다. 오래된 WSL OAuth snapshot을 그대로 다시 시작하지 않습니다. 로컬로 되돌려야 한다면 cluster writer 종료 후 현재 auth authority를 승인된 경로로 이전해야 합니다.

ESO 오류는 Store/ExternalSecret 상태와 property 참조부터, 401/403은 Gateway와 native 인증을 나누어, model 오류는 Job/checksum/허용 egress부터 조사합니다. auth init 실패는 seed 부재와 기존 PVC 손상을 구분합니다. 값 조회, IAM 확대, force delete나 무관한 서비스 재시작으로 우회하지 않습니다.
