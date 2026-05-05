# helm-charts

KKamJi homelab의 ArgoCD GitOps 단일 source of truth. KubeADM bare-metal 클러스터 (`k8s-m1`/`k8s-w1`/`k8s-w2`)를 단일 ArgoCD가 관리한다.

## 아키텍처 한눈에

```
charts/argocd/                              ← 우산 차트 (helm install 1회)
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

### 2. helm upgrade --install (1회만)

```bash
cd ~/code/code-personal/helm-charts

helm dependency update charts/argocd

helm upgrade --install argocd charts/argocd -n argocd \
  --create-namespace \
  -f charts/argocd/kkamji_local_values.yaml \
  --take-ownership \
  --wait --timeout 10m
```

`--take-ownership`은 helm 3.13+에서 ArgoCD self-sync로 미리 만들어진 리소스에 helm ownership annotation을 자동 주입.

### 3. 자동 propagation 확인

```bash
# AppProject 5개
kubectl -n argocd get appproject

# Root Application 4개
kubectl -n argocd get app | grep -E "management-root|automation-root|personal-root|kuberca-root"

# ExternalSecret 2개 (GitHub App credential 자동 hydrate)
kubectl -n argocd get externalsecret

# 그 자식 Application들 정상 sync까지 1~5분
kubectl -n argocd get app -o jsonpath='{range .items[*]}{.metadata.name}\t{.status.sync.status}\t{.status.health.status}\n{end}' | column -t
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
kubectl -n argocd annotate app <name> argocd.argoproj.io/refresh=hard --overwrite
```

수동 helm 명령 절대 금지(예외: 부트스트랩, 복구).

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
ArgoCD 자체 ConfigMap/Secret이 cascade로 지워진 경우. helm release는 살아있으니 재 apply:
```bash
helm upgrade argocd charts/argocd -n argocd \
  -f charts/argocd/kkamji_local_values.yaml --wait
kubectl -n argocd rollout restart deploy
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

### 4. helm upgrade가 "AppProject xxx exists and cannot be imported"
ArgoCD가 self-sync로 만든 리소스를 helm이 인수 못 함. `--take-ownership` 또는 수동 annotation:
```bash
NS=argocd; RELEASE=argocd
for kn in $(kubectl -n $NS get appproject,application,externalsecret -o name); do
  kubectl -n $NS annotate $kn \
    meta.helm.sh/release-name=$RELEASE \
    meta.helm.sh/release-namespace=$NS --overwrite
  kubectl -n $NS label $kn \
    app.kubernetes.io/managed-by=Helm --overwrite
done
```

### 5. cilium-operator CrashLoopBackOff
`k8sServiceHost: auto`는 agent만 지원, operator는 거부. 명시 endpoint 필수:
```yaml
# charts/cilium/kkamji_local_values.yaml
k8sServiceHost: 10.0.0.101   # 단일 master IP
k8sServicePort: 6443
```
HA로 전환 시 VIP/LB로 변경.

### 6. cert-manager HTTP-01 challenge가 nginx-ingress에 거부
ingress-nginx v1.10+가 `pathType: Exact`를 거부. ClusterIssuer에서:
```yaml
solvers:
  - http01:
      ingress:
        ingressClassName: nginx   # ← 'class' (deprecated)이 아닌 ingressClassName
```

### 7. ExternalSecret CRD apiVersion 미스매치
ESO 0.10 미만이면 `external-secrets.io/v1` 미지원, `v1beta1` 사용:
```bash
kubectl api-resources --api-group=external-secrets.io
# 클러스터 등록 버전 확인 후 템플릿 apiVersion 일치
```

### 8. Certificate가 동일 secretName 두고 다툼
`Secret was issued for "argocd-server"` 경고. legacy Certificate 제거:
```bash
kubectl -n argocd delete certificate argocd-server
# 새 argocd-server-tls가 동일 Secret 인수
```

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
2. **helm install ↔ ArgoCD self-sync는 ouroboros** — `--take-ownership` 또는 ownership annotation 보정 없이는 helm upgrade가 거부됨.
3. **ESO CRD default 필드는 git에도 명시** — 안 쓰면 영구 OutOfSync.
4. **AppProject deletionTimestamp는 K8s가 unset 못함** — finalizer 제거 후 ArgoCD가 재생성하도록.
5. **secret은 SSM/ESO에 두고 git에는 절대 안 둠** — `secret-values.yaml`은 `.gitignore`에.

## 라이선스

MIT (LICENSE 참고).
