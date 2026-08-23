# AGENTS.md - helm-charts

> 이 저장소에서 작업하는 AI 에이전트를 위한 운영 프로토콜.
> 아키텍처 / AppProject / 디렉터리 구조는 README.md 를 참조한다 (여기서 중복 기록하지 않는다).

## Knowledge Layout
- **현재 구조, 결정, 규칙**: `docs/`. 카탈로그는 `docs/index.md` 다. 차트나 Makefile 을 고치기 전에 읽는다.
- **작업 일지, 백로그**: vault `workspaces/`.
- **교차 repo 지식**: vault `wiki/`, `shapes/`, `runbooks/`.
- frontmatter 필수 키 네 개: `title`, `updated`, `type`, `status`. 새 문서는 `docs/index.md` 에 등록한다.
- `docs/_meta/coupling.json` 에 매핑된 파일을 바꾸면 같은 PR 에서 해당 문서도 바꾼다.
- `docs/_meta/docs_lint.py` 는 손으로 고치지 않는다. 정본은 `kkamji-settings/agents/docs-wiki/docs_lint.py` 다.
- 검증: `python3 docs/_meta/docs_lint.py --root .`

## 0. 프로젝트 개요
- KKamJi homelab 의 ArgoCD GitOps 단일 source of truth. KubeADM bare-metal 클러스터(`k8s-m1` control-plane, `k8s-w1`/`k8s-w2` worker; Cilium + MetalLB)를 단일 ArgoCD 가 관리.
- 기술 스택: Helm(`charts/`), Shell(`Makefile`, `scripts/`), Docker(openclaw 이미지).
- 활성 차트는 `charts/`, 폐기 자산은 `_archived/`(수정/배포 대상 아님), EKS 전용은 `eks-charts/`.

## 1. GitOps 배포 흐름 (커밋 전 필독)
- 모든 ArgoCD Application 은 이 repo 의 `targetRevision=main` 을 추적한다. `main` push -> GitHub webhook -> ArgoCD self-sync(`prune` + `selfHeal` + `ServerSideApply`). 즉 **`main` push = 즉시 클러스터 apply**.
- 일상 변경은 `main` 에 직접 커밋한다. feature 브랜치는 배포되지 않으므로, 글로벌 "branch first" 기본값보다 이 정책을 우선한다.
- push 전 변경 범위를 확정하고 무관한 WIP 는 커밋에서 제외한다. 한 파일에 관심사가 섞이면 `git add <file>` 대신 `git apply --cached` 로 해당 헝크만 staging 한다.
- 사용자가 세션 중 같은 repo 에서 병렬로 커밋/푸시할 수 있다. commit/push 직전 `git fetch` + `git status` 로 재확인하고, 사용자 WIP 를 함께 쓸어담지 않도록 `git commit -- <paths>`(pathspec) 로 커밋한다.

## 2. 부트스트랩 정책 (중요)
- **운영 중 `helm install/upgrade` 금지**: SSA 환경에서 helm 매니저가 필드 ownership 을 잡으면 ArgoCD self-sync 가 stale 필드(cert-manager annotation/tls 등)를 제거하지 못한다.
- 신규 클러스터 일회성: `make setup`(= `make deps` + `make bootstrap`). bootstrap 은 `helm template | kubectl apply --server-side --field-manager=argocd-controller --force-conflicts` 한 번이면 충분하다.
- 이후 변경은 git push -> self-sync. Makefile 재실행은 불필요하다.

## 3. 주요 명령어
- Makefile 타깃 표와 기본 변수는 `docs/operations.md` 가 정본이다.

## 4. Helm 컨벤션
- 차트별 환경 값 파일은 `charts/<chart>/kkamji_local_values.yaml` 이다 (`values.yaml` 아님). template/lint 에 항상 `-f` 로 넘긴다.
- 의존성은 vendored(`charts/<chart>/charts/*.tgz` + `Chart.lock`) -> `helm template`/`helm lint` 가 오프라인으로 동작하고 `helm dependency build` 가 불필요하다. 의존성 갱신이 필요할 때만 `make deps`.
- 버전 핀은 `Chart.yaml`/`Chart.lock` 을 신뢰한다 (README 의 버전 문자열은 stale 할 수 있다).

## 5. 클러스터 (kubectl)
- 타겟 컨텍스트는 `kkamji-lab`. kubeconfig 에 회사 prod/staging 컨텍스트도 함께 있으므로, write/delete 전 반드시 `kubectl config current-context` 를 확인한다.
- 에이전트 실행 제한: `get`/`describe`/`diff`/`dry-run` 은 자율, `apply`/`delete`/`create` 는 수동 + 승인.
- 컨텍스트 기본 namespace 가 `default` 가 아니다 - 조회/조작 시 항상 `-n` 을 명시한다.
- pod 내부 확인은 `kubectl exec` 대신 `kubectl port-forward` + HTTP API 를 사용한다 (exec 는 권한 차단됨; Alertmanager `/api/v2/alerts·status`, Prometheus `/api/v1/rules·targets·query`).
- amtool/promtool 은 로컬 미설치 - `helm template --show-only` 로 secret 추출 후 docker(`quay.io/prometheus/alertmanager`, `quay.io/prometheus/prometheus`)의 `amtool check-config`/`amtool template render`/`promtool check rules` 로 검증한다.

## 6. External Secrets (ESO)
- ESO 함정과 SSM 키 네이밍은 `docs/rules/external-secrets.md` 가 정본이다.

## 7. 커밋 규칙
- Conventional Commits: `feat|fix|refac|docs|chore|test|perf`. `Co-Authored-By` / AI attribution 추가 금지.
- 출력물(파일/커밋/문서)에 비표준 타이포그래피(em/en dash, smart quote, ellipsis) 사용 금지. ASCII 로 대체한다.
- `git commit -- <pathspec>` 는 untracked 신규 파일을 포함하지 않는다. 신규 템플릿 파일은 `git add` 후 커밋한다 (누락 시 ArgoCD 가 partial 로 sync 되어 조용히 깨진다).

## 8. CI/CD
- GitHub Actions 는 `.github/workflows/build-openclaw-dev.yaml`(openclaw 이미지 빌드) 하나뿐이다. 차트 배포 CI 는 없고 ArgoCD self-sync 가 배포를 담당한다.

## 9. Gateway API 라우팅
- 소유 경계, 신규 서비스 온보딩, SSA diff 방지, 인증서 규칙은 `docs/rules/gateway-api-routing.md` 가 정본이다.
