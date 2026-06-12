# AGENTS.md - helm-charts

> 이 저장소에서 작업하는 AI 에이전트를 위한 운영 프로토콜.
> 아키텍처 / AppProject / 디렉터리 구조는 README.md 를 참조한다 (여기서 중복 기록하지 않는다).

## 0. 프로젝트 개요
- KKamJi homelab 의 ArgoCD GitOps 단일 source of truth. KubeADM bare-metal 클러스터(`k8s-m1` control-plane, `k8s-w1`/`k8s-w2` worker; Cilium + MetalLB)를 단일 ArgoCD 가 관리.
- 기술 스택: Helm(`charts/`), Shell(`Makefile`, `scripts/`), Docker(openclaw 이미지).
- 활성 차트는 `charts/`, 폐기 자산은 `_archived/`(수정/배포 대상 아님), EKS 전용은 `eks-charts/`.

## 1. GitOps 배포 흐름 (커밋 전 필독)
- 모든 ArgoCD Application 은 이 repo 의 `targetRevision=main` 을 추적한다. `main` push -> GitHub webhook -> ArgoCD self-sync(`prune` + `selfHeal` + `ServerSideApply`). 즉 **`main` push = 즉시 클러스터 apply**.
- 일상 변경은 `main` 에 직접 커밋한다. feature 브랜치는 배포되지 않으므로, 글로벌 "branch first" 기본값보다 이 정책을 우선한다.
- push 전 변경 범위를 확정하고 무관한 WIP 는 커밋에서 제외한다. 한 파일에 관심사가 섞이면 `git add <file>` 대신 `git apply --cached` 로 해당 헝크만 staging 한다.

## 2. 부트스트랩 정책 (중요)
- **운영 중 `helm install/upgrade` 금지**: SSA 환경에서 helm 매니저가 필드 ownership 을 잡으면 ArgoCD self-sync 가 stale 필드(cert-manager annotation/tls 등)를 제거하지 못한다.
- 신규 클러스터 일회성: `make setup`(= `make deps` + `make bootstrap`). bootstrap 은 `helm template | kubectl apply --server-side --field-manager=argocd-controller --force-conflicts` 한 번이면 충분하다.
- 이후 변경은 git push -> self-sync. Makefile 재실행은 불필요하다.

## 3. 주요 명령어 (Makefile)
| 작업 | 명령 |
|---|---|
| 매니페스트 검증 (apply 없이) | `make template` |
| helm lint (`charts/*` 전체) | `make lint` |
| AppProject/Application 현황 | `make status` |
| root Application hard refresh | `make refresh` |
| `argocd-cm`/`argocd-secret` 유실 복구 | `make recover-secrets` |
| AppProject stuck(Pending deletion) 해소 | `make unstick-projects` |
| stale `manager=helm` 잔재 진단 | `make detect-helm-ownership` |

- Makefile 기본 변수: `RELEASE=argocd`, `NAMESPACE=argocd`, `UMBRELLA_CHART=charts/argocd`, `VALUES=charts/argocd/kkamji_local_values.yaml`, `FIELD_MANAGER=argocd-controller`.
- 단일 차트 부분 검증: `helm template <chart> -f charts/<chart>/kkamji_local_values.yaml --show-only templates/<file>`.

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

## 6. External Secrets (ESO) gotcha
- ClusterExternalSecret 파생 자식 ExternalSecret 은 `refreshInterval` 이 Go 표준형으로 정규화된다(`1h` -> `1h0m0s`). 직접 정의한 ExternalSecret 은 리터럴 문자열을 유지한다.
- `creationPolicy: Owner` 는 ownerReference 를 설정한다 -> ExternalSecret 을 삭제하면 `deletionPolicy: Retain` 이어도 타깃 Secret 이 함께 GC 된다.
- repo 에 정의가 없고 `kubectl.kubernetes.io/last-applied-configuration` 만 있는 ExternalSecret 은 수동 생성된 orphan 일 수 있다 (GitOps 관리 대상 아님 -> 정리 후보).

## 7. 커밋 규칙
- Conventional Commits: `feat|fix|refac|docs|chore|test|perf`. `Co-Authored-By` / AI attribution 추가 금지.
- 출력물(파일/커밋/문서)에 비표준 타이포그래피(em/en dash, smart quote, ellipsis) 사용 금지. ASCII 로 대체한다.

## 8. CI/CD
- GitHub Actions 는 `.github/workflows/build-openclaw-dev.yaml`(openclaw 이미지 빌드) 하나뿐이다. 차트 배포 CI 는 없고 ArgoCD self-sync 가 배포를 담당한다.
