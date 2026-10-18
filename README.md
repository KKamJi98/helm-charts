# helm-charts

Windows PC의 Hyper-V VM 위에 kubeadm으로 구축한 개인 Kubernetes 홈랩을 관리하는 Helm/GitOps 저장소입니다. Argo CD의 구성, AppProject, root Application과 서비스별 배포 선언을 보관합니다.

이 저장소는 VM 생성, OS 설치나 kubeadm 클러스터 구축을 대신하지 않습니다. 이미 준비한 클러스터 위의 애플리케이션 구성을 관리합니다. 차트가 존재하거나 Application이 선언되어 있다는 사실만으로 설치와 정상 운영이 검증된 것은 아닙니다.

바로 가기: [동기화 구조](#gitops-동기화-구조) | [디렉터리](#디렉터리-안내) | [최초 부트스트랩](#사전-준비와-최초-부트스트랩) | [일반 변경](#일반-변경-흐름) | [검증](#검증과-명령의-범위) | [복구](#복구와-트러블슈팅) | [보안](#보안과-secret-경계)

## 먼저 읽을 문서

| 확인할 내용 | 정본 |
|---|---|
| 전체 문서 목록 | [docs/index.md](docs/index.md) |
| 명령, 부트스트랩, 검증과 복구 | [Makefile operations](docs/operations.md) |
| Argo CD 버전 핀, renderer 호환성, 업그레이드와 롤백 | [Argo CD upgrades](docs/argocd-upgrades.md) |
| ESO와 Secret 수명주기 | [External Secrets rules](docs/rules/external-secrets.md) |
| Gateway/서비스 라우팅 소유 경계 | [Gateway API routing rules](docs/rules/gateway-api-routing.md) |
| 저장소 작업 규칙 | [AGENTS.md](AGENTS.md) |

이 README는 진입점입니다. 상세 절차와 시점별 운영 증적은 위 문서를 따릅니다. 버전은 README의 고정 숫자가 아니라 각 `Chart.yaml`, `Chart.lock`과 vendored 패키지에서 확인합니다.

## GitOps 동기화 구조

```text
검토한 변경을 main에 반영
  -> GitHub webhook 또는 Argo CD polling으로 감지
  -> Argo CD가 root Application을 reconcile
  -> charts/argo-applications + root별 values
  -> 자식 Application의 repository/path/chart
  -> Kubernetes 리소스에 반영
```

[charts/argocd](charts/argocd)는 upstream Argo CD, 로컬 AppProject와 root Application을 묶는 umbrella chart입니다. 최초 부트스트랩 뒤에는 `management-root`의 `argocd` Application이 이 umbrella를 다시 관리합니다.

AppProject는 `argocd`, `management`, `automation`, `personal`로 역할을 나눕니다. 정의는 umbrella의 [argo-projects 설정](charts/argocd/kkamji_local_values.yaml), 생성 템플릿은 [charts/argo-projects](charts/argo-projects)에서 관리합니다. 이 역할 구분이 보안 격리를 보장하지는 않습니다.

현재 root 선언의 정본은 [rootApplications](charts/argocd/kkamji_local_values.yaml), 생성 규칙은 [root-applications.yaml](charts/argocd/templates/root-applications.yaml)입니다.

| Root Application | 자식 선언 파일 | 선언 대상 예시 |
|---|---|---|
| `management-root` | [management_local_values.yaml](charts/argo-applications/management_local_values.yaml) | Argo CD, Cilium, MetalLB, Envoy Gateway, ESO, 관측 도구 |
| `automation-root` | [automation_local_values.yaml](charts/argo-applications/automation_local_values.yaml) | n8n과 자동화 도구 |
| `personal-root` | [personal_local_values.yaml](charts/argo-applications/personal_local_values.yaml) | 별도 저장소에서 관리하는 개인 애플리케이션 |

이 저장소의 GitOps 기준 branch는 `main`입니다. 자식 Application은 다른 Git 저장소나 버전이 고정된 외부 Helm chart를 사용할 수도 있습니다. 실제 소스와 revision은 각 Application 선언에서 확인합니다.

root 동기화 정책에는 자동 동기화, `prune`, `selfHeal`, `ServerSideApply`가 설정되어 있습니다. 따라서 `main` 반영은 배포 경계입니다. 삭제한 선언이 실제 리소스 삭제로 이어질 수 있으므로 문서 변경 승인과 인프라 변경 승인을 혼동하지 않습니다. 작업 branch에만 push하거나 PR을 여는 것은 클러스터 배포가 아닙니다.

`enabled: false`인 항목은 생성 대상에서 제외됩니다. 반대로 `enabled: true`라도 runtime의 중단 상태나 실패가 있을 수 있습니다. `skip-reconcile`로 중단한 앱은 임의로 재개하지 않으며, 과거의 `Synced/Healthy`를 최신 실행 증적으로 보지 않습니다.

예를 들어 OpenClaw는 선언상 비활성입니다. n8n은 선언상 활성이나, [2026-10-15 운영 기록](docs/argocd-upgrades.md#적용-결과)에서는 reconciliation 중단 상태였습니다. 이 기록은 확인 시점의 증거이며 실시간 상태판이 아닙니다.

## 디렉터리 안내

```text
charts/
  argocd/                 Argo CD umbrella, root Application, ESO 연동
  argo-projects/          AppProject 정의
  argo-applications/      root별 values에서 자식 Application 생성
  cilium/, metallb/       클러스터 네트워크 구성
  envoy-gateway/          Gateway API 플랫폼 구성
  external-secrets/       ESO 구성
  cert-manager/           인증서 구성
  n8n/, openclaw/         자동화 서비스 차트
  alloy/, loki/           관측 도구 차트
  ...                     나머지 인프라와 서비스 차트

eks-charts/               별도 EKS 환경용 구성
_archived/                운영 대상이 아닌 과거 자산
docs/                     운영 정본, 규칙과 결정 기록
scripts/                  상태 확인과 보조 스크립트
.github/workflows/        문서 검사와 OpenClaw 이미지 CI
Makefile                  검증, 상태 확인, bootstrap/복구 진입점
```

`charts/`의 모든 디렉터리가 활성 Application에 연결되는 것은 아닙니다. 반대로 외부 저장소의 Application에는 이 저장소 안의 서비스 차트가 없을 수 있습니다. 활성화 여부는 디렉터리 목록 대신 root별 values와 실제 Application 상태를 함께 확인합니다.

### Values와 의존성

- 서비스별 홈랩 override는 `charts/<chart>/kkamji_local_values.yaml`입니다. lint/render에도 해당 파일을 전달합니다.
- root별 Application 목록은 `charts/argo-applications/<root>_local_values.yaml`입니다.
- upstream 차트는 vendored 형태로 보관합니다. 의존성이 있는 차트의 `Chart.lock`과 패키지도 버전 핀의 일부입니다.
- 버전 변경이 없다면 검증을 위해 `make deps`나 dependency update를 반복하지 않습니다. 해당 명령은 로컬 lock/vendor를 바꿀 수 있습니다.
- release, Application 이름과 chart 경로를 바꾸는 작업은 단순 파일명 정리가 아닙니다. 리소스 identity와 삭제 영향을 먼저 검토합니다.

## 사전 준비와 최초 부트스트랩

필요한 준비물은 다음과 같습니다.

- 접근 가능한 kubeadm 클러스터와 정상 동작하는 CNI.
- 개인 홈랩의 `kkamji-lab` context와 필요한 namespace/권한. 회사나 다른 클러스터 context를 대상으로 실행하지 않습니다.
- Git, Make, kubectl, Helm. 배포 renderer와 Helm 버전은 [업그레이드 runbook](docs/argocd-upgrades.md)의 호환성 기준을 따릅니다.
- 문서 검사에 필요한 Python 3. `jq`는 일부 진단 명령에서 사용합니다.
- 저장소 접근용 GitHub App, SSM `SecureString`, ESO/SecretStore, 인증서와 Gateway 경로의 사전 준비. Secret 값은 저장소나 셸 명령 인자로 전달하지 않습니다.
- 배포할 서비스가 요구하는 DNS/LoadBalancer와 storage/PVC 준비. 이 저장소의 애플리케이션 선언만으로 외부 의존성이 준비되지는 않습니다.

먼저 `kubectl config current-context`로 대상을 확인하고 [bootstrap 절차](docs/operations.md#bootstrap)를 읽습니다. `make setup`은 dependency 갱신과 실제 클러스터 apply를 포함하는 신규 환경용 명령입니다. 이미 운영 중인 클러스터에서 동기화를 재촉하려고 재실행하는 명령이 아닙니다.

이 저장소는 `helm install/upgrade/rollback`을 일상 배포 경로로 사용하지 않습니다. 최초 bootstrap은 Argo CD와 같은 field manager를 쓰는 server-side apply 경로이며, 이후에는 검토한 Git 변경을 Argo CD가 반영합니다. 이는 무조건 안전한 복구나 필드 소유권 충돌의 자동 해결을 보장하지 않습니다.

## 일반 변경 흐름

1. 최신 원격과 작업 상태를 확인합니다. 격리된 작업 branch/worktree에서 관련 chart, values와 연결 문서만 수정합니다. 다른 사람의 변경을 stash/reset하거나 함께 stage하지 않습니다.
2. [검증 절차](docs/operations.md#validation)에 따라 전체 render, 대상 chart lint, 문서 검사와 diff를 확인합니다. 버전, API, 라우팅, Secret/PVC와 권한 변경의 영향을 검토합니다.
3. 검토한 범위만 commit/push합니다. `main`에 반영할 권한이 있는 변경만 배포 경계를 넘깁니다.
4. 반영 후 source revision, sync/health, workload와 요청한 서비스 동작을 확인합니다. PR 생성, push 성공이나 render 성공만으로 배포 완료를 선언하지 않습니다.

서비스의 HTTPRoute는 해당 서비스 차트가 소유하고, Gateway와 공용 TLS listener는 플랫폼 차트가 소유합니다. 신규 라우팅은 [Gateway API 규칙](docs/rules/gateway-api-routing.md)을 따르며 과거 nginx/SSL-passthrough 절차를 복사하지 않습니다.

## 검증과 명령의 범위

| 종류 | 예시 | 주의점 |
|---|---|---|
| 로컬 확인 | `make help`, 대상 chart의 `helm lint`, 전체 `helm template` | 클러스터 apply와 별개입니다. 전체 출력에 Secret 데이터가 포함될 수 있어 출력/보관하지 않습니다. |
| 문서 검사 | `python3 docs/_meta/docs_lint.py --root . --base origin/main` | 같은 날 본문을 고치면 `updated`도 실제 갱신 시각으로 올립니다. |
| 클러스터 조회 | context/namespace를 명시한 Application, workload, ESO 상태 확인 | Secret 값은 조회하지 않습니다. |
| 상태 변경 | `make setup`, `make bootstrap`, `make refresh`, 복구 target | apply, annotation 변경 또는 workload 재시작을 포함할 수 있어 별도 검토가 필요합니다. |

현재 `make template`은 출력 일부를 보여주는 preview이고, `make lint`는 개별 chart의 실패를 무시합니다. 두 target의 종료 코드만으로 검증 완료를 판정하지 않습니다. 전체 render와 대상 values를 적용한 직접 lint 명령은 [검증 정본](docs/operations.md#validation)에 있습니다.

[docs-lint workflow](.github/workflows/docs-lint.yml)는 문서를 검사하고, [OpenClaw workflow](.github/workflows/build-openclaw-dev.yaml)는 이미지를 빌드합니다. 차트 배포 경로는 CI의 수동 Helm 설치가 아니라 Argo CD입니다.

ARC는 [별도 준비 PR #9](https://github.com/KKamJi98/helm-charts/pull/9)의 후보이며, 이 문서 갱신 시점에는 설치되지 않았습니다. runner 등록이나 실제 ARC CI 성공을 검증한 운영 구성으로 소개하지 않습니다.

## 복구와 트러블슈팅

먼저 Git의 의도와 현재 runtime 상태를 분리합니다. 복구 전에는 대상, 변경 영향, 마지막 정상 revision, 데이터 백업과 사후 확인 방법을 정합니다.

| 증상 | 먼저 확인할 내용 | 안내 |
|---|---|---|
| 변경이 반영되지 않음 | branch/revision, root와 자식 diff, sync 오류, 중단 여부 | [일반 변경](docs/operations.md#normal-changes) |
| repository 인증 또는 ESO 오류 | ExternalSecret/SecretStore 상태, 접근 권한과 참조 | [Secret 규칙](docs/rules/external-secrets.md) |
| HTTP/TLS 접근 실패 | Service, HTTPRoute 조건, Gateway/TLS 소유 경계 | [라우팅 규칙](docs/rules/gateway-api-routing.md) |
| 버전 변경 후 비교/기동 실패 | 고정 버전, renderer, CRD 호환성과 이전 Git revision | [업그레이드/롤백](docs/argocd-upgrades.md) |
| 제어면 유실, 삭제 대기, ownership 문제 | 리소스 소유자, finalizer와 실제 영향 | [복구 정본](docs/operations.md#recovery) |

Git 역변경은 원하는 리소스 구성을 되돌리는 경로이지 DB/PVC 데이터 복구가 아닙니다. `make recover-secrets`는 재apply와 workload 재시작을 포함합니다. finalizer 제거, Namespace/Secret/PVC/CRD 삭제와 강제 ownership 변경을 일반 해결책으로 실행하지 않습니다.

## 보안과 Secret 경계

- 외부 관리 자격증명은 AWS SSM `SecureString`에 두고, ESO가 참조를 Kubernetes Secret으로 연결합니다. Git에는 참조와 선언만 둡니다. 차트나 controller가 생성하는 Secret까지 모두 SSM에서 복원된다고 가정하지 않습니다. 삭제/회전은 [ESO 수명주기 규칙](docs/rules/external-secrets.md)을 먼저 확인합니다.
- 토큰, private key, 비밀번호, kubeconfig 인증 데이터와 Secret 값을 문서/로그/커밋에 넣지 않습니다. `.gitignore`는 이미 추적한 값이나 로그 노출을 막아주지 않습니다.
- 렌더 결과나 진단 출력도 Secret을 포함할 수 있습니다. 값 전체를 출력하지 않고 상태와 참조만 확인합니다.
- 현재 AppProject에는 source repository, namespace와 리소스 허용 범위의 `*` 설정이 남아 있습니다. 엄격한 멀티테넌트 격리나 최소 권한을 보장하는 구성으로 소개하지 않습니다. Namespace는 VM 수준의 격리가 아닙니다.
- 권한, 네트워크, 외부 인증/등록과 GitOps 활성화는 문서/PR 게시 승인에 포함되지 않습니다.


## 라이선스

[MIT License](LICENSE).
