# helm-charts

KKamJi homelab의 ArgoCD GitOps 단일 source of truth. KubeADM bare-metal 클러스터 (`k8s-m1`/`k8s-w1`/`k8s-w2`)를 단일 ArgoCD가 관리한다.

## 아키텍처 한눈에

```
charts/argocd/                              ← 우산 차트 (SSA 1회 부트스트랩)
  ├── 의존성: upstream argo-cd v9.1.4
  ├── 의존성: argo-projects (file://)       ← AppProject 5개
  └── templates/
      ├── root-applications.yaml            ← 4개 root Application 생성
      └── repo-credentials.yaml             ← ESO ExternalSecret (GitHub App)
                ↓
   ┌─────────────┬──────────────┬──────────────┬──────────────┐
management-root automation-root personal-root  kuberca-root
   ↓               ↓                ↓               ↓
charts/argo-applications + 각 *_local_values.yaml
   ↓               ↓                ↓               ↓
14 Application   1 Application   2 Application  6 Application
(cilium, …)      (openclaw)      (play-hub, …)  (bookinfo, …)
```

### AppProject

| project | 용도 | Application |
|---|---|---|
| `argocd` | self-management | `argocd`(self) + 4 root Applications |
| `management` | 클러스터 인프라 | cilium, metallb, ingress-nginx, external-dns, external-secrets, cert-manager(+issuer), metrics-server, istio-base/istiod, kiali-operator, kube-prometheus-stack, alloy, loki, tempo |
| `automation` | 자동화 도구 | openclaw |
| `personal` | 개인 토이 프로젝트 | play-hub, lf-oss-na-2026 |
| `kuberca` | kube-rca 데모 자산 | bookinfo, load-generator, chaos-mesh, kuberca-monitoring, k8s-resources, kube-rca |

> 모든 AppProject는 `sourceRepos: ["*"]` (홈랩 단순화). 운영급으로 좁히려면 `KKamJi98/*`, `kube-rca/*`, 외부 차트 repo 화이트리스트.

## 디렉터리 구조

```
charts/
├── argocd/                  # 우산 (upstream argo-cd 9.1.4 + projects + roots + repo-creds)
├── argo-projects/           # AppProject CR 5개를 만드는 라이브러리 차트
├── argo-applications/       # 자식 Application CR을 찍어내는 generic iterator
│   ├── management_local_values.yaml
│   ├── automation_local_values.yaml
│   ├── personal_local_values.yaml
│   └── kuberca_local_values.yaml
│
├── kuberca-monitoring/      # kube-rca 전용 PrometheusRule + bookinfo dashboards
│
├── alloy/, loki/, tempo/    # LGTM observability stack
├── istio-base/, istio-istiod/, kiali-operator/
├── cilium/, metallb/, ingress-nginx/, external-dns/, external-secrets/, metrics-server/
├── cert-manager-issuer/, kube-prometheus-stack/
├── bookinfo/, chaos-mesh/, load-generator/
├── openclaw/
└── harbor/, keycloak/, minio/   # 보유만 (Application 미연결)

eks-charts/                  # EKS 전용 차트 (현재 미사용)
├── aws-load-balancer-controller/, eks-1.34/, karpenter/

_archived/                   # legacy (참고용 보관)
```

## values 파일 컨벤션

| 위치 | 파일명 | 용도 |
|---|---|---|
| chart-level (cilium, alloy 등) | `kkamji_local_values.yaml` | 홈랩 환경 override |
| `argo-applications/` | `<root>_local_values.yaml` | 각 root별 자식 Application 정의 |
| 미래 EKS 환경 시 | `kkamji_eks_values.yaml` | 일부 차트엔 이미 존재 |

## 부트스트랩 정책 (중요)

> **`helm install`/`helm upgrade` 는 사용하지 않는다.** 신규 클러스터에서도 `make bootstrap`(= `helm template | kubectl apply --server-side --field-manager=argocd-controller`) **1회**만 실행한다. 이후 모든 변경은 `git push` → ArgoCD self-sync.

**Why**: helm CLI 는 모든 필드의 managedFields manager 를 `helm` 으로 잡는다. 이후 ArgoCD self-sync(SSA, manager=`argocd-controller`)가 stale 필드(예: 제거된 cert-manager annotation, tls 블록)를 못 빼는 ownership drift 발생. 처음부터 manager 를 `argocd-controller` 로 통일하면 원천 차단된다.

진단: `make detect-helm-ownership` — argocd 네임스페이스에서 `manager: helm` 잔존 리소스 탐지. 결과가 비어있어야 정상.

## 부트스트랩 (신규/재설치 클러스터)

> ArgoCD 본체 + AppProjects + Root Applications를 한 번에 띄움.
> 이후엔 git push만 하면 ArgoCD가 self-sync.

### 1. 사전 준비

- KubeADM 클러스터 + cilium CNI 동작
- external-secrets Operator + `parameter-store` ClusterSecretStore (AWS SSM 연결) 사전 설치
- cert-manager + ClusterIssuer `letsencrypt-prod` 사전 설치
- AWS SSM에 GitHub App 자격증명 저장:
  ```bash
  aws ssm put-parameter --name "/kkamji/argocd/github-app/app-id" --type SecureString --value "<APP_ID>" --overwrite
  aws ssm put-parameter --name "/kkamji/argocd/github-app/installation-id-personal" --type SecureString --value "<INST_PERSONAL>" --overwrite
  aws ssm put-parameter --name "/kkamji/argocd/github-app/installation-id-kuberca"  --type SecureString --value "<INST_KUBERCA>"  --overwrite
  aws ssm put-parameter --name "/kkamji/argocd/github-app/private-key" --type SecureString --value "$(cat ~/path/to/argocd-app.pem)" --overwrite
  ```
- (선택) AWS SSM 에 GitHub webhook shared secret 저장 — push 즉시 sync 용:
  ```bash
  aws ssm put-parameter \
    --name /kkamji/argocd/github-webhook/secret \
    --type SecureString \
    --value "$(openssl rand -hex 32)" --overwrite
  ```

### 2. 부트스트랩 (Makefile 기반)

```bash
cd ~/code/code-personal/helm-charts

make setup        # = make deps + make bootstrap
                  # 내부: helm dependency update
                  #     + helm template | kubectl apply --server-side
                  #         --field-manager=argocd-controller --force-conflicts
                  # → helm release secret 미생성, 처음부터 ArgoCD 와 동일 manager

# 다른 namespace/release로 띄우려면:
make setup RELEASE=argocd NAMESPACE=argocd
```

부트스트랩 후 root Application 들이 즉시 생성되고, `argocd` self-Application (charts/argo-applications/management_local_values.yaml 정의)이 자기 자신을 self-manage 시작한다. 이후 `make bootstrap` 재실행은 불필요(원하면 idempotent SSA 라 안전하지만, 일상 변경은 git push 만 사용).

### 3. (선택) GitHub webhook 등록

3분 polling 대신 push 즉시 sync 하려면, GitHub repo Settings → Webhooks 에 등록:

| 필드 | 값 |
|---|---|
| Payload URL | `https://argocd.kkamji.net/api/webhook` |
| Content type | `application/json` |
| Secret | (위 SSM 에 저장한 hex 값) |
| Events | Just the push event |

> ESO 가 `/kkamji/argocd/github-webhook/secret` SSM 값을 `argocd-secret` 의 `webhook.github.secret` 키로 merge 한다 (`charts/argocd/templates/webhook-secret.yaml`). ArgoCD 는 secret 변경 자동 감지 → pod 재시작 불필요.

### 4. 자동 propagation 확인

```bash
make status       # AppProject 5개 + Application 4 root + 23 children + ExternalSecret 한눈에

# 또는 raw kubectl
kubectl -n argocd get appproject
kubectl -n argocd get app -o wide
kubectl -n argocd get externalsecret
```

## 일상 운영

> **변경 흐름은 `git push` 하나만**.

```bash
# 1) 차트/values 수정
$EDITOR charts/<chart>/kkamji_local_values.yaml

# 2) commit + push
git add -A && git commit -m "fix(<chart>): <change>" && git push

# 3) ArgoCD가 webhook 또는 polling(3분)으로 자동 감지·동기화
#    즉시 트리거하고 싶으면:
make refresh       # 모든 root에 hard refresh
# 또는 단일:
kubectl -n argocd annotate app <name> argocd.argoproj.io/refresh=hard --overwrite
```

수동 helm 명령(`helm install`/`helm upgrade`) 절대 금지. 부트스트랩에도 SSA 만 사용. 자세한 이유는 상단 [부트스트랩 정책](#부트스트랩-정책-중요) 참조.

### Make targets

```
make help                  # 전체 target 도움말
make setup                 # deps + bootstrap (부트스트랩)
make deps                  # helm dependency update
make bootstrap             # helm template | kubectl apply --server-side (SSA)
make refresh               # 모든 root hard refresh
make status                # 현재 상태 스냅샷
make template              # helm template 검증 (apply 없이)
make lint                  # helm lint 전 차트
make recover-secrets       # argocd-cm/secret 등 사라졌을 때 재apply + rollout restart
make unstick-projects      # AppProject Pending deletion stuck 해소
make detect-helm-ownership # (진단) argocd ns 에 manager=helm 잔존 리소스 탐지
```

## 시크릿 관리

### Source of truth: AWS SSM Parameter Store
- 모든 secret은 SSM `SecureString` (KMS 암호화)
- `/kkamji/<scope>/<resource>/<key>` 네이밍

### 주입 방식: External Secrets Operator
- argocd 자체 credential: `charts/argocd/templates/repo-credentials.yaml`이 ExternalSecret 생성 → ESO가 SSM에서 fetch → `argocd` ns Secret 생성
- 그 외 ExternalSecret은 `kube-rca/k8s-resources` repo에서 별도 관리

### GitHub App 인증 (private repo fetch)
- 단일 GitHub App, KKamJi98 + kube-rca 두 곳에 install
- App ID + Private key는 공유, Installation ID만 다름
- ArgoCD repo-creds Secret 2개를 ESO가 자동 생성:
  - `github-app-creds-personal` → `https://github.com/KKamJi98/`
  - `github-app-creds-kuberca` → `https://github.com/kube-rca/`

회전 시 `aws ssm put-parameter --overwrite`만 하면 ESO가 1시간 내 자동 sync.

## 이름 규칙 (renaming 금지)

부트스트랩 후 다음은 **rename 시 ouroboros 충돌**로 서비스 영향 가능. 절대 변경 금지:

| 항목 | 고정 이름 |
|---|---|
| Helm release name | `argocd` |
| Umbrella chart 폴더/이름 | `charts/argocd` |
| Self-managed Application name | `argocd` |
| Root Application names | `<project>-root` (management-root, …) |
| values 파일 패턴 | `kkamji_local_values.yaml`, `<root>_local_values.yaml` |

신규 chart 추가는 자유, 기존 rename은 별도 PR로 신중히 (cluster 측 마이그레이션 동반 필요).

## 복구 / 트러블슈팅

### 1. argocd-cm/argocd-secret이 사라짐
ArgoCD 자체 ConfigMap/Secret이 cascade로 지워진 경우. SSA 로 재apply + rollout:
```bash
make recover-secrets
# 내부: make bootstrap (재apply) + rollout restart deploy/statefulset
```

### 2. AppProject가 `Pending deletion`으로 stuck
deletionTimestamp가 박힌 채 finalizer로 멈춤. K8s는 `deletionTimestamp` 해제 불가:
```bash
for proj in argocd kuberca management; do
  kubectl -n argocd patch appproject $proj --type=json \
    -p='[{"op":"remove","path":"/metadata/finalizers"}]'
done
# 5초~30초 후 ArgoCD self-sync로 재생성
```

### 3. Application이 `default` project에 박혀있음
옛 부모 Application이 spec을 default로 덮어쓰는 중:
```bash
NS=argocd
orphan_del() {
  kubectl -n $NS patch app "$1" --type=json -p='[{"op":"remove","path":"/metadata/finalizers"}]' 2>/dev/null
  kubectl -n $NS delete app "$1" --cascade=orphan
}
# 옛 부모 제거 (자식 리소스는 보존)
orphan_del argo-applications
orphan_del argocd     # 옛 self-managed
# 새 root이 spec 갱신
for r in management-root automation-root personal-root kuberca-root; do
  kubectl -n $NS annotate app "$r" argocd.argoproj.io/refresh=hard --overwrite
done
```

### 4. cilium-operator CrashLoopBackOff
`k8sServiceHost: auto`는 agent만 지원, operator는 거부. 명시 endpoint 필수:
```yaml
# charts/cilium/kkamji_local_values.yaml
k8sServiceHost: 10.0.0.101   # 단일 master IP
k8sServicePort: 6443
```
HA로 전환 시 VIP/LB로 변경.

### 5. cert-manager HTTP-01 challenge가 nginx-ingress에 거부
ingress-nginx v1.10+가 `pathType: Exact`를 거부. ClusterIssuer에서:
```yaml
solvers:
  - http01:
      ingress:
        ingressClassName: nginx   # ← 'class' (deprecated)이 아닌 ingressClassName
```

### 6. ExternalSecret CRD apiVersion 미스매치
ESO 0.10 미만이면 `external-secrets.io/v1` 미지원, `v1beta1` 사용:
```bash
kubectl api-resources --api-group=external-secrets.io
# 클러스터 등록 버전 확인 후 템플릿 apiVersion 일치
```

### 7. Certificate가 동일 secretName 두고 다툼 (ssl-passthrough 환경)
`Secret was issued for "argocd-server"` 경고가 반복. 원인은 두 가지가 동시에 같은 Secret 발급을 요구하는 것:
- `server.certificate.enabled: true` → `Certificate/argocd-server`
- Ingress 의 `cert-manager.io/cluster-issuer` annotation + `tls: true` → ingress-shim 이 `Certificate/<secretName>` 자동 생성

ssl-passthrough 환경에서는 TLS 종료를 argocd-server pod 가 직접 하므로 명시적 Certificate 하나만 필요. Ingress 측 auto-issue 를 끄는 것이 정답:

```yaml
# charts/argocd/kkamji_local_values.yaml
argocd:
  server:
    ingress:
      tls: false      # ingress-shim 이 Certificate 안 만들게
      annotations:
        # cert-manager.io/cluster-issuer: 제거
        nginx.ingress.kubernetes.io/ssl-passthrough: "true"
        # ...
```

> **선결조건**: `nginx.ingress.kubernetes.io/ssl-passthrough` annotation 은 ingress-nginx 컨트롤러에 `--enable-ssl-passthrough` flag 가 **명시적으로** 켜져 있어야 해석된다. 안 켜져 있으면 annotation 이 무시되고 nginx 가 fake default 인증서로 응답한다 (브라우저 `NET::ERR_CERT_AUTHORITY_INVALID`). `charts/ingress-nginx/kkamji_local_values.yaml` 에서 `controller.extraArgs.enable-ssl-passthrough: "true"` 로 활성화. 이 flag 는 컨트롤러 전역이지만 passthrough annotation 이 없는 다른 호스트는 영향 없음.

기존에 만들어진 잔여 Certificate 수동 삭제:
```bash
kubectl -n argocd delete certificate argocd-server-tls
```

### 8. SSA ownership drift — Helm 잔존 manager 가 ArgoCD self-sync 를 무력화
증상: values 에서 annotation/필드를 제거했는데 클러스터 객체에서는 그대로 살아있음. ArgoCD 는 "Synced" 라고 보고. 원인: 옛 `helm install/upgrade` 가 박은 `manager: helm` 이 SSA 로 못 빠지고 잔존.

진단:
```bash
make detect-helm-ownership
# 결과 비어있어야 정상
```

청소:
```bash
NS=argocd
for resource in $(make detect-helm-ownership 2>/dev/null | grep -v '==>' | grep -v '결과'); do
  kubectl -n $NS get "$resource" --show-managed-fields -o json \
    | jq 'del(.metadata.managedFields[] | select(.manager == "helm"))' \
    | kubectl replace -f -
done
# helm release secret 도 함께 삭제 (ArgoCD 가 모든 리소스 관리하므로 안전)
kubectl -n $NS delete secret -l owner=helm
```

청소 후 ArgoCD sync 트리거하면 stale 필드가 자동 제거됨. **재발 방지**: `helm install/upgrade` 사용 금지, `make bootstrap` (SSA) 만 사용.

### 9. ESO ExternalSecret 영구 OutOfSync
ESO CRD가 `conversionStrategy/decodingStrategy/metadataPolicy` 등을 default로 주입. git에도 동일하게 명시해야 drift 안 남:
```yaml
data:
  - secretKey: ...
    remoteRef:
      key: ...
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
```

## 핵심 교훈

이 repo는 다음 함정을 모두 한 번씩 밟고 정리된 상태이다.

1. **이름은 부트스트랩 전에 결정, 이후 rename 금지** — release name / chart name / Application name 불일치는 라벨 충돌의 근원.
2. **`helm install/upgrade` 금지, SSA-only 부트스트랩** — helm CLI 가 박는 `manager: helm` 이 ArgoCD self-sync 의 stale 필드 제거를 영구히 차단함. `make bootstrap` (= `helm template | kubectl apply --server-side --field-manager=argocd-controller`) 으로 처음부터 manager 를 통일. 과거 `--take-ownership` 패턴은 self-perpetuating cycle 이라 폐기됨.
3. **ESO CRD default 필드는 git에도 명시** — 안 쓰면 영구 OutOfSync.
4. **AppProject deletionTimestamp는 K8s가 unset 못함** — finalizer 제거 후 ArgoCD가 재생성하도록.
5. **secret은 SSM/ESO에 두고 git에는 절대 안 둠** — `secret-values.yaml`은 `.gitignore`에.
6. **ssl-passthrough Ingress 와 `server.certificate` 는 둘 중 하나만** — 동시 활성화 시 같은 Secret 을 두 Certificate 가 다툼 (#7 참조).

## 라이선스

MIT (LICENSE 참고).
