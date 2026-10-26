---
title: External Secrets rules
updated: 2026-10-27T03:50:25+09:00
type: rule
status: current
---

# External Secrets rules

ESO 매니페스트를 고칠 때 함께 확인한다. 아래 항목은 전부 실제로 밟은 함정이다.

- ClusterExternalSecret 파생 자식 ExternalSecret 은 `refreshInterval` 이 Go 표준형으로 정규화된다(`1h` -> `1h0m0s`). 직접 정의한 ExternalSecret 은 리터럴 문자열을 유지한다.
- `creationPolicy: Owner` 는 ownerReference 를 설정한다 -> ExternalSecret 을 삭제하면 `deletionPolicy: Retain` 이어도 타깃 Secret 이 함께 GC 된다.
- repo 에 정의가 없고 `kubectl.kubernetes.io/last-applied-configuration` 만 있는 ExternalSecret 은 수동 생성된 orphan 일 수 있다 (GitOps 관리 대상 아님 -> 정리 후보).
- SSM ParameterStore 키 네이밍: `/kkamji/<component>/<purpose>` (예: `/kkamji/external-dns/aws-credentials`). 다중 키 자격증명은 SecureString JSON 1개 + `dataFrom.extract` 로 분해한다.
- ExternalSecret/CES 가 부트스트랩 직후 webhook race 로 실패하면 refresh(1h)를 기다리지 말고 `kubectl annotate ... force-sync=$(date +%s)` 로 즉시 reconcile 한다.
- argocd admin 비밀번호는 ESO Merge(argocd-admin-password-es)가 SSM bcrypt 해시(/kkamji/argocd/admin-password-bcrypt)로 고정한다. argocd-secret 의 admin.password 를 수동 수정하지 않는다.

## ARC candidate

ARC foundation은 단일 `/kkamji/arc/github-app` 경로를 기존 `parameter-store`로 참조합니다. 값은 커밋하거나 생성하지 않습니다. [ARC rollout](../arc-ci.md)의 사용자 입력, 단계별 활성화와 회전 경계를 따릅니다.
- ARC foundation의 `githubAuth.enabled`는 기본 false입니다. 인증 승인/안전한 SSM 입력/ESO의 정확한 경로와 KMS 권한 확인 전에 ExternalSecret을 생성하지 않습니다. controller 단계와 등록 단계를 분리하며, 값은 조회하지 않습니다.

## ARC App authentication

- ARC는 /kkamji/arc/github-app의 단일 SecureString JSON을 기존 parameter-store로 읽습니다. key 세 개는 github_app_id, github_app_installation_id, github_app_private_key입니다. 값은 chart/문서에 넣지 않습니다.
- ci-pr/arc-github-app-auth ExternalSecret과 target Secret을 두 light chart가 같은 이름으로 참조합니다. App key 하나를 공유하므로 저장소별 Secret 권한 분리라고 주장하지 않습니다.
- target은 creationPolicy=Orphan/deletionPolicy=Retain입니다. ExternalSecret 제거가 App credential 삭제로 이어지지 않도록 합니다.
- githubAuth.enabled는 기본 false입니다. 활성화 전에 arcSsmReuse의 enabled, namespaceTrustAccepted, existingStoreTrustAccepted, keyChoiceApproved, secureInputMetadataVerified를 확인합니다. 이 flag는 IAM 추가 권한 요구가 아니라 owner 신뢰/선택/보안 입력 확인입니다.
- 기존 shared Store를 재사용하면 해당 namespace의 ExternalSecret 작성자에게 허용된 기존 신뢰 범위가 남습니다. namespace 격리나 실제 AWS principal 연결을 flag만으로 증명하지 않습니다. 새 reader/Store/IAM/key policy를 자동으로 추가하지 않습니다.
- 사용자 보안 입력과 metadata 확인 전에는 auth를 켜거나 light Application을 활성화하지 않습니다. 실제 값 조회/로그 출력으로 검증하지 않습니다.
- 로컬 회귀 검사는 Helm을 PATH에 둔 뒤 uv run --no-project python -m unittest discover -s tests -p test_arc_auth.py -v로 실행합니다. 기본 off, 확인 gate 누락, 단일 canonical ExternalSecret과 두 consumer 참조를 검사합니다.
- Full-runner staging은 ci-full의 ESO가 같은 기존 SSM source를 참조합니다. Agent는 credential 값을 읽거나 복사하지 않습니다. 두 namespace는 하나의 App 권한을 공유하며 인증 격리라고 주장하지 않습니다. full chart의 기본 auth는 off이고 local reuse만 명시적으로 켭니다. Orphan/Retain과 기존 ci-pr source를 보존하며 새 IAM/Store/key를 만들지 않습니다.

## ARC runner image pull

- `ci-full`(arc-full)와 `ci-pr`(arc-foundation)의 `ghcr-pull-secret`은 `kubernetes.io/dockerconfigjson` ExternalSecret입니다. `imagePullSecret.enabled`가 true일 때만 렌더링되며 기본값은 false입니다.
- 원본은 `kkamji-platform/ghcr-pull-secret`과 같은 `/kkamji/personal/kkamji-platform/ghcr/pull-token`(classic PAT, `read:packages`만)입니다. 새 credential, Store, IAM 권한을 추가하지 않습니다. 같은 토큰을 세 namespace가 공유하므로 credential 격리라고 주장하지 않습니다.
- target은 `creationPolicy: Owner`입니다. ExternalSecret을 제거하면 pull Secret도 GC 됩니다. 원본 PAT는 SSM에 남습니다.
- PAT를 교체하거나 삭제하면 세 namespace의 새 pull이 모두 영향을 받습니다. 교체 후 세 ExternalSecret에 `force-sync`를 적용합니다. 절차는 [ARC runner images](../arc-runner-images.md)를 따릅니다.

## Hindsight private access

- [Hindsight runbook](../03_hindsight.md)의 전용 원본은 `/kkamji/automation/hindsight/access` SecureString JSON입니다. version 2가 이미 존재하므로 재생성/초기화하지 않습니다. property는 `api_key`, `ui_access_key`, `ui_htpasswd`이며 값은 조회/출력/커밋하지 않습니다.
- 기존 `parameter-store`를 재사용하고 target은 `creationPolicy: Orphan` / `deletionPolicy: Retain`입니다. API, CP와 Gateway consumer별 `data[].remoteRef.property`를 명시하며, 이 구성에서는 `dataFrom.extract`로 전체 JSON을 모든 consumer에 복제하지 않습니다. API key는 CP의 서버 측 dataplane 접근에도 필요하므로 이 둘 사이의 credential 분리를 주장하지 않습니다.
- agent의 SSM Get은 거부되며 기존 IAM은 변경하지 않습니다. 실제 ESO reader 4개의 SecretSynced/Ready와 target Secret 생성을 확인했습니다. Gateway/native 인증은 별도 live 인수 대기이며, metadata 존재를 HTTP 인증 성공으로 표시하지 않습니다.
- UI는 고엔트로피 전용 비밀번호와 Envoy가 지원하는 `{SHA}` htpasswd 형식을 사용합니다. API key도 고엔트로피 전용 값이며 다른 서비스 인증을 재사용하지 않습니다. shared Store 권한, ExternalSecret 작성자, 관리자와 key 보유자는 신뢰 범위에 남습니다.
- ChatGPT OAuth `credentials.json`/`host_id`는 이 SSM JSON에 넣지 않습니다. 전용 세션의 일회성 seed에서 writable PVC로 옮기고, 현재 refresh authority를 stale Secret으로 덮어쓰지 않습니다. 로컬 writer 종료, 재시작 지속성 확인과 seed 삭제 순서는 runbook을 따릅니다.
