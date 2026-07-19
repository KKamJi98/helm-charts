# ESO Secrets Centralization & Path Convention Migration

> Historical design record. Slack token paths and `slack-token-ces.yaml` references are retired; Discord webhook ESO resources are the current notification implementation.

**Date**: 2026-05-06
**Status**: Design (pending user review)

## Context

현재 ExternalSecret/ClusterExternalSecret/ClusterSecretStore 매니페스트가 두 git repo에 분산되어 있고 모두 deprecated `external-secrets.io/v1beta1` 을 사용한다. 또 SSM Parameter path 가 service 별로 일관되지 않다 (`/kkamji/argocd/...` 컨벤션 vs `basic-auth`/`grafana-auth`/`argocd-slack-token` 같은 top-level path).

본 작업은 (a) helm-charts repo에서 ESO 관련 secret 정의를 차트별로 흡수, (b) `external-secrets.io/v1` 통일, (c) SSM path를 cluster-prefix 기반 컨벤션으로 마이그레이션한다.

## In Scope

| 항목 | 작업 |
|---|---|
| `charts/external-secrets/` | **umbrella chart 전환** (Chart.yaml dependency=upstream 2.4.1) + `templates/cluster-secret-store.yaml`(v1) 추가 |
| `charts/kube-prometheus-stack/` | **umbrella chart 전환** (Chart.yaml dependency=upstream 75.12.0) + `templates/{basic-auth-ces,grafana-auth-ces}.yaml`(v1) 추가 |
| `charts/argocd/templates/` | `slack-token-ces.yaml` (v1) 추가 (argocd 는 이미 umbrella) |
| AWS SSM Parameter Store | basic-auth / grafana-auth / argocd-slack-token / kube-rca-* 7개 path 새 컨벤션으로 copy → apply → delete |
| `k8s-resources` repo (별 PR) | css-parameter-store + basic-auth/grafana-auth/slack-token 4개 매니페스트 삭제, kube-rca-* 4개는 prefix만 v1으로 갱신하고 잔류 |

## Out of Scope

- IRSA/Pod Identity 전환 (local cluster 비EKS, secretRef 유지)
- ClusterSecretStore name 변경 (`parameter-store` 그대로)
- `awssm-secret` (auth용 AWS access key) 자동 생성 — 현 사전 수동 생성 가정 유지
- kube-rca 매니페스트의 helm-charts 이전 (외부 repo 잔류, prefix만 변경)

## Decisions (사용자 확정)

1. **Path convention**: cluster context-prefixed
   - local cluster: `/kkamji/<service>/<group>/<key>`
   - kuberca cluster: `/kuberca/<service>/<group>/<key>`
2. **Resource kind**: 모두 `ClusterExternalSecret` 일관 사용 (단일 ns 도 CES로)
3. **JSON 객체 path**: property별 path로 split (예: grafana-auth → admin-user / admin-password 두 path)
4. **차트 구조**: external-secrets 를 umbrella chart 로 전환 (Chart.yaml dependency)
5. **PR 단위**: helm-charts 1개 통합 PR + k8s-resources 1개 PR + SSM 외부 절차 (Phase 0 / Phase 7). Phase 1~5 는 helm-charts PR 내부의 논리적 작업 분해 (커밋 단위로 분리 가능), 머지는 한 번.

## Path Migration Mapping

### local cluster (`/kkamji/`)

| 현재 SSM path | 새 SSM path | 사용처 |
|---|---|---|
| `/kkamji/argocd/github-webhook/secret` | (변경 없음) | argocd webhook |
| `/kkamji/argocd/github-app/app-id` | (변경 없음) | argocd repo creds |
| `/kkamji/argocd/github-app/installation-id-personal` | (변경 없음) | |
| `/kkamji/argocd/github-app/installation-id-kuberca` | (변경 없음) | |
| `/kkamji/argocd/github-app/private-key` | (변경 없음) | |
| `argocd-slack-token` | `/kkamji/argocd/notifications/slack-token` | argocd notifications |
| `basic-auth` | `/kkamji/monitoring/ingress/basic-auth` | prometheus/alertmanager ingress |
| `grafana-auth` (JSON) | split → `/kkamji/monitoring/grafana/admin-user` + `/kkamji/monitoring/grafana/admin-password` | grafana admin |

### kuberca cluster (`/kuberca/`) — 외부 repo 작업

| 현재 SSM path | 새 SSM path |
|---|---|
| `kube-rca-auth` (JSON) | split → `/kuberca/kube-rca/auth/<field>` (실제 JSON 필드 SSM 값 확인 후 결정) |
| `kube-rca-ai-api-keys` (JSON) | split → `/kuberca/kube-rca/ai/<field>` |
| `kube-rca-postgres-user-password` | `/kuberca/kube-rca/postgresql/user-password` |
| `kube-rca-postgres-password` | `/kuberca/kube-rca/postgresql/postgres-password` |
| `kube-rca-slack-channel-id` | `/kuberca/kube-rca/slack/channel-id` |
| `kube-rca-slack-token` | `/kuberca/kube-rca/slack/token` |

> kube-rca-auth/ai 의 JSON 내부 필드명은 마이그레이션 시점에 `aws ssm get-parameter` 로 확인 후 path 확정.

## Architecture

### 1. external-secrets chart umbrella 전환

**Before** (현재):
```
charts/external-secrets/
├── Chart.yaml (vendor v2.4.1, dep bitwarden-sdk-server)
├── templates/                       # ESO upstream 템플릿 통째 vendor
│   ├── deployment.yaml
│   ├── webhook-deployment.yaml
│   ├── crds/*.yaml
│   └── ... (40+ 파일)
├── values.yaml                       # ESO upstream values 통째
└── kkamji_local_values.yaml          # override
```

**After**:
```
charts/external-secrets/
├── Chart.yaml                        # name=external-secrets-bundle, dep external-secrets v2.4.1
├── Chart.lock                        # helm dependency update 결과
├── charts/external-secrets-2.4.1.tgz # vendored .tgz
├── templates/
│   └── cluster-secret-store.yaml     # 우리 ClusterSecretStore (v1)
├── values.yaml                       # 빈 또는 placeholder
└── kkamji_local_values.yaml          # external-secrets: <ESO override> 형태로 nest
```

`Chart.yaml`:
```yaml
apiVersion: v2
name: external-secrets
version: 0.1.0
type: application
dependencies:
  - name: external-secrets
    version: 2.4.1
    repository: https://charts.external-secrets.io
```

`kkamji_local_values.yaml`:
```yaml
external-secrets:           # ← sub-chart values
  installCRDs: true
  crds:
    unsafeServeV1Beta1: true

# 우리 매니페스트용 (templates/cluster-secret-store.yaml 가 참조)
clusterSecretStore:
  name: parameter-store
  region: ap-northeast-2
  authSecretRef:
    namespace: external-secrets
    name: awssm-secret
    accessKeyIDKey: access-key
    secretAccessKeyKey: secret-access-key
```

`templates/cluster-secret-store.yaml`:
```yaml
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: {{ .Values.clusterSecretStore.name | default "parameter-store" }}
spec:
  provider:
    aws:
      service: ParameterStore
      region: {{ .Values.clusterSecretStore.region }}
      auth:
        secretRef:
          accessKeyIDSecretRef:
            name: {{ .Values.clusterSecretStore.authSecretRef.name }}
            namespace: {{ .Values.clusterSecretStore.authSecretRef.namespace }}
            key: {{ .Values.clusterSecretStore.authSecretRef.accessKeyIDKey }}
          secretAccessKeySecretRef:
            name: {{ .Values.clusterSecretStore.authSecretRef.name }}
            namespace: {{ .Values.clusterSecretStore.authSecretRef.namespace }}
            key: {{ .Values.clusterSecretStore.authSecretRef.secretAccessKeyKey }}
```

### 2. kube-prometheus-stack chart umbrella 전환

**Before** (현재): vendor 형태 (templates 176 파일, charts/ 5개 의존성 untar — alertmanager/prometheus/prometheus-operator/grafana/kube-state-metrics/node-exporter)

**After**:
```
charts/kube-prometheus-stack/
├── Chart.yaml                                # name=kube-prometheus-stack-bundle, dep=kube-prometheus-stack 75.12.0
├── Chart.lock
├── charts/kube-prometheus-stack-75.12.0.tgz  # vendored .tgz (helm dep update 결과)
├── templates/
│   ├── basic-auth-ces.yaml                   # 우리 ClusterExternalSecret (v1)
│   └── grafana-auth-ces.yaml
├── values.yaml                               # 빈 또는 placeholder
├── kkamji_local_values.yaml                  # kube-prometheus-stack: <upstream override> 형태로 nest
└── kkamji_local_with_thanos.yaml             # 동일 패턴
```

`Chart.yaml`:
```yaml
apiVersion: v2
name: kube-prometheus-stack-bundle
version: 0.1.0
type: application
dependencies:
  - name: kube-prometheus-stack
    version: 75.12.0
    repository: https://prometheus-community.github.io/helm-charts
```

`kkamji_local_values.yaml` (구조 변경, 모든 upstream override 키를 nest):
```yaml
kube-prometheus-stack:           # ← sub-chart 이름과 동일하게
  alertmanager:
    ingress: {...}
    config: {...}
  prometheus: {...}
  grafana:
    admin:
      existingSecret: grafana-auth
      userKey: admin-user
      passwordKey: admin-password
    ingress: {...}

# 우리 매니페스트용 (templates/*-ces.yaml 가 참조)
basicAuth:
  ssmKey: /kkamji/monitoring/ingress/basic-auth
  namespaces: [monitoring, kube-rca, bookinfo]
grafanaAuth:
  adminUserSsmKey: /kkamji/monitoring/grafana/admin-user
  adminPasswordSsmKey: /kkamji/monitoring/grafana/admin-password
```

새 templates 추가 (vendor 의 templates/ 디렉터리는 통째 삭제, 우리 매니페스트만 남김):

`templates/basic-auth-ces.yaml`:
```yaml
apiVersion: external-secrets.io/v1
kind: ClusterExternalSecret
metadata:
  name: basic-auth-ces
spec:
  externalSecretName: basic-auth-es
  namespaceSelector:
    matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: In
        values: {{ .Values.basicAuth.namespaces | toJson }}
  refreshTime: 1h
  externalSecretSpec:
    refreshInterval: 1h
    secretStoreRef:
      name: parameter-store
      kind: ClusterSecretStore
    target:
      name: basic-auth
      creationPolicy: Owner
    data:
      - secretKey: auth
        remoteRef:
          key: {{ .Values.basicAuth.ssmKey | quote }}
```

`templates/grafana-auth-ces.yaml` — admin-user / admin-password 각각 별 path:
```yaml
apiVersion: external-secrets.io/v1
kind: ClusterExternalSecret
metadata:
  name: grafana-auth-ces
spec:
  externalSecretName: grafana-auth-es
  namespaceSelector:
    matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: In
        values: ["monitoring"]
  refreshTime: 1h
  externalSecretSpec:
    refreshInterval: 1h
    secretStoreRef:
      name: parameter-store
      kind: ClusterSecretStore
    target:
      name: grafana-auth
      creationPolicy: Owner
    data:
      - secretKey: admin-user
        remoteRef:
          key: {{ .Values.grafanaAuth.adminUserSsmKey | quote }}
      - secretKey: admin-password
        remoteRef:
          key: {{ .Values.grafanaAuth.adminPasswordSsmKey | quote }}
```

### 3. argocd 차트에 추가

`charts/argocd/templates/slack-token-ces.yaml`:
```yaml
apiVersion: external-secrets.io/v1
kind: ClusterExternalSecret
metadata:
  name: slack-token-ces
spec:
  externalSecretName: slack-token-es
  namespaceSelector:
    matchExpressions:
      - key: kubernetes.io/metadata.name
        operator: In
        values: ["argocd"]
  refreshTime: 1h
  externalSecretSpec:
    refreshInterval: 1h
    secretStoreRef:
      name: parameter-store
      kind: ClusterSecretStore
    target:
      name: argocd-notifications-secret
      creationPolicy: Owner
    data:
      - secretKey: slack-token
        remoteRef:
          key: {{ .Values.slackToken.ssmKey | quote }}
```

`kkamji_local_values.yaml` 에 추가:
```yaml
slackToken:
  ssmKey: /kkamji/argocd/notifications/slack-token
```

기존 `webhook-secret.yaml`, `repo-credentials.yaml` 은 v1 이미 적용됨, path 변경 없음.

### 4. k8s-resources repo 별 PR

helm-charts 머지 후:
- `external-secrets/cluster-secret-store/css-parameter-store.yaml` 삭제
- `external-secrets/cluster-external-secret/{basic-auth,grafana-auth,slack-token}-ces.yaml` 삭제
- `external-secrets/cluster-external-secret/kube-rca-*-ces.yaml` 4개:
  - `apiVersion: external-secrets.io/v1` 으로 변경
  - `data[].remoteRef.key` 새 prefix(`/kuberca/...`) 로 변경
  - JSON property split 적용

## Migration Procedure (Phase 단위 진행)

Phase 1~5 는 단일 helm-charts PR 안의 논리적 분해. 머지는 한 번이지만 PR review 시 phase 단위로 검토. Phase 0 (SSM 새 path 작성) 과 Phase 7 (old path 삭제) 은 외부 AWS 절차. Phase 6 은 k8s-resources repo 의 별 PR.

순서: **Phase 0 → helm-charts PR (Phase 1~5) → k8s-resources PR (Phase 6) → 24h 관찰 → Phase 7**.

### Phase 0 — SSM 새 path 작성 (prep, 사용자 직접 실행)

매니페스트 머지 전, 새 path 로 모든 SSM 값을 **미리** 작성. 기존 path 는 그대로 둠 (병행 운영). 모든 path `--type SecureString`. region 은 외부 매니페스트 ClusterSecretStore 기준 `ap-northeast-2`.

```bash
REGION=ap-northeast-2

# === local cluster (/kkamji/) — 3 group ===

# 1) basic-auth (string)
v=$(aws ssm get-parameter --name "basic-auth" --with-decryption --region $REGION \
    --query 'Parameter.Value' --output text)
aws ssm put-parameter --name "/kkamji/monitoring/ingress/basic-auth" \
    --type SecureString --value "$v" --region $REGION

# 2) grafana-auth (JSON → split: admin-user / admin-password)
SRC="grafana-auth"; DST_PREFIX="/kkamji/monitoring/grafana"
for k in $(aws ssm get-parameter --name "$SRC" --with-decryption --region $REGION \
    --query 'Parameter.Value' --output text | jq -r 'keys[]'); do
  v=$(aws ssm get-parameter --name "$SRC" --with-decryption --region $REGION \
      --query 'Parameter.Value' --output text | jq -r --arg k "$k" '.[$k]')
  aws ssm put-parameter --name "$DST_PREFIX/$k" \
      --type SecureString --value "$v" --region $REGION
done

# 3) argocd-slack-token (string)
v=$(aws ssm get-parameter --name "argocd-slack-token" --with-decryption --region $REGION \
    --query 'Parameter.Value' --output text)
aws ssm put-parameter --name "/kkamji/argocd/notifications/slack-token" \
    --type SecureString --value "$v" --region $REGION

# === kuberca cluster (/kuberca/) — 4 group ===

# 4) kube-rca-auth (JSON → split → /kuberca/kube-rca/auth/<field>)
SRC="kube-rca-auth"; DST_PREFIX="/kuberca/kube-rca/auth"
for k in $(aws ssm get-parameter --name "$SRC" --with-decryption --region $REGION \
    --query 'Parameter.Value' --output text | jq -r 'keys[]'); do
  v=$(aws ssm get-parameter --name "$SRC" --with-decryption --region $REGION \
      --query 'Parameter.Value' --output text | jq -r --arg k "$k" '.[$k]')
  aws ssm put-parameter --name "$DST_PREFIX/$k" \
      --type SecureString --value "$v" --region $REGION
done

# 5) kube-rca-ai-api-keys (JSON → split → /kuberca/kube-rca/ai/<field>)
SRC="kube-rca-ai-api-keys"; DST_PREFIX="/kuberca/kube-rca/ai"
for k in $(aws ssm get-parameter --name "$SRC" --with-decryption --region $REGION \
    --query 'Parameter.Value' --output text | jq -r 'keys[]'); do
  v=$(aws ssm get-parameter --name "$SRC" --with-decryption --region $REGION \
      --query 'Parameter.Value' --output text | jq -r --arg k "$k" '.[$k]')
  aws ssm put-parameter --name "$DST_PREFIX/$k" \
      --type SecureString --value "$v" --region $REGION
done

# 6) kube-rca-postgres-* (string × 2)
v=$(aws ssm get-parameter --name "kube-rca-postgres-user-password" --with-decryption \
    --region $REGION --query 'Parameter.Value' --output text)
aws ssm put-parameter --name "/kuberca/kube-rca/postgresql/user-password" \
    --type SecureString --value "$v" --region $REGION

v=$(aws ssm get-parameter --name "kube-rca-postgres-password" --with-decryption \
    --region $REGION --query 'Parameter.Value' --output text)
aws ssm put-parameter --name "/kuberca/kube-rca/postgresql/postgres-password" \
    --type SecureString --value "$v" --region $REGION

# 7) kube-rca-slack-* (string × 2)
v=$(aws ssm get-parameter --name "kube-rca-slack-channel-id" --with-decryption \
    --region $REGION --query 'Parameter.Value' --output text)
aws ssm put-parameter --name "/kuberca/kube-rca/slack/channel-id" \
    --type SecureString --value "$v" --region $REGION

v=$(aws ssm get-parameter --name "kube-rca-slack-token" --with-decryption \
    --region $REGION --query 'Parameter.Value' --output text)
aws ssm put-parameter --name "/kuberca/kube-rca/slack/token" \
    --type SecureString --value "$v" --region $REGION
```

**검증**: 새 path 모두 readable, 값 일치 확인.

```bash
REGION=ap-northeast-2
for new_path in \
  "/kkamji/monitoring/ingress/basic-auth" \
  "/kkamji/monitoring/grafana/admin-user" \
  "/kkamji/monitoring/grafana/admin-password" \
  "/kkamji/argocd/notifications/slack-token" \
  "/kuberca/kube-rca/postgresql/user-password" \
  "/kuberca/kube-rca/postgresql/postgres-password" \
  "/kuberca/kube-rca/slack/channel-id" \
  "/kuberca/kube-rca/slack/token"; do
  echo -n "$new_path: "
  aws ssm get-parameter --name "$new_path" --with-decryption --region $REGION \
    --query 'Parameter.Type' --output text 2>&1 || echo "MISSING"
done
# JSON split 결과 확인
aws ssm get-parameters-by-path --path "/kuberca/kube-rca/auth/" --recursive --region $REGION \
  --query 'Parameters[].Name' --output text
aws ssm get-parameters-by-path --path "/kuberca/kube-rca/ai/" --recursive --region $REGION \
  --query 'Parameters[].Name' --output text
```

### Phase 1 — external-secrets chart umbrella 전환 (PR #1)

vendor 형태 → Chart.yaml dependency 기반 umbrella. **helm template 결과 동등성 검증이 핵심.**

- 변경: `charts/external-secrets/Chart.yaml`, vendor templates/charts 디렉터리 삭제, `charts/external-secrets-2.4.1.tgz` 추가, `kkamji_local_values.yaml` 키를 `external-secrets:` 하위로 nest
- 검증:
  - `helm template <before> > /tmp/eso-old.yaml` (main branch)
  - `helm template <after>  > /tmp/eso-new.yaml`
  - `diff -u <(yq -P 'sort_keys(..)' /tmp/eso-old.yaml) <(yq -P 'sort_keys(..)' /tmp/eso-new.yaml)` → chart label 외 spec 차이 없음
  - 머지 후 ArgoCD `external-secrets` app Synced + Healthy
  - controller pod 재시작 없음 (또는 spec 동일하므로 rolling update 미발생)

### Phase 2 — ClusterSecretStore (v1) 추가 (PR #2)

- 변경: `charts/external-secrets/templates/cluster-secret-store.yaml` (v1) 신규 추가, `kkamji_local_values.yaml` 의 `clusterSecretStore` 블록 추가
- 사전: 클러스터에 이미 v1beta1 `parameter-store` 가 외부 `k8s-resources` app 으로 배포되어 있음. helm-charts PR 머지 시 `external-secrets` app 이 같은 이름 리소스를 v1 로 재생성 시도. ArgoCD 가 다른 app 의 리소스 takeover 시 drift 발생 가능.
- 절차:
  1. PR 머지 → ArgoCD sync 시도
  2. 양쪽 app (`external-secrets`, `k8s-resources`) 의 ClusterSecretStore 소유권 확인
  3. **`k8s-resources` app 의 css-parameter-store 삭제 (Phase 6) 가 완료되어야 drift 해소**. 즉 Phase 2 머지 후 Phase 6 까지 즉시 진행 권장
- 검증: `kubectl get clustersecretstore parameter-store -o jsonpath='{.spec.conditions[*]}'` valid, kubectl warning 없음 (v1)

### Phase 3 — kube-prometheus-stack chart umbrella 전환 (PR #3)

가장 큰 리팩토링. spec 동등성 보장 핵심.

- 변경: vendor 정리(templates 176 파일, charts/ 5개 의존성 디렉터리), Chart.yaml dependency 추가, .tgz 1개로 압축, kkamji_local_values.yaml/kkamji_local_with_thanos.yaml 키를 `kube-prometheus-stack:` 하위로 nest
- 검증:
  - `helm template` before/after diff (chart label, dependency name 차이 외 spec 동일 보장)
  - `kubectl diff -f <(helm template ...)` 로 클러스터 영향 사전 확인 — 대부분 no-op 이어야 정상
  - 머지 후 모니터링: prometheus-operator pod, alertmanager pod, grafana pod, prometheus pod 모두 stable (재시작 없음)
  - ServiceMonitor / PrometheusRule 개수 변화 없음 (`kubectl get servicemonitor -A | wc -l` before/after 동일)

### Phase 4 — basic-auth / grafana-auth ClusterExternalSecret 추가 (PR #4)

- 변경: `charts/kube-prometheus-stack/templates/{basic-auth-ces,grafana-auth-ces}.yaml` (v1) 추가, kkamji_local_values.yaml 에 `basicAuth`, `grafanaAuth` 블록 추가
- 사전: Phase 0 으로 새 SSM path 가 이미 readable
- 절차:
  1. PR 머지 → ArgoCD sync → 새 CES 가 새 SSM path 로 secret 동기화 시도
  2. `k8s-resources` app 의 기존 v1beta1 CES (basic-auth-ces, grafana-auth-ces) 가 같은 secret 을 owner 로 관리 중 → drift 가능
  3. **Phase 6 (k8s-resources cleanup) 가 직후 진행되어야 drift 해소**
- 검증: `kubectl get secret basic-auth -A`, `kubectl -n monitoring get secret grafana-auth` 정상, 값이 새 SSM path 와 일치

### Phase 5 — slack-token ClusterExternalSecret 추가 (argocd 차트, PR #5)

- 변경: `charts/argocd/templates/slack-token-ces.yaml` (v1) 추가, kkamji_local_values.yaml 에 `slackToken` 블록 추가
- 사전: Phase 0 의 `/kkamji/argocd/notifications/slack-token` 작성 완료
- 절차: Phase 4 와 동일 패턴 (Phase 6 직후 cleanup 으로 drift 해소)
- 검증: `kubectl -n argocd get secret argocd-notifications-secret -o jsonpath='{.data.slack-token}'` 새 값과 일치, ArgoCD notifications 동작 정상

### Phase 6 — k8s-resources repo cleanup (별 PR)

- 변경 (외부 repo `kube-rca/k8s-resources`):
  - `external-secrets/cluster-secret-store/css-parameter-store.yaml` 삭제
  - `external-secrets/cluster-external-secret/{basic-auth,grafana-auth,slack-token}-ces.yaml` 삭제
  - `external-secrets/cluster-external-secret/kube-rca-*-ces.yaml` 4개:
    - `apiVersion: external-secrets.io/v1`
    - `data[].remoteRef.key` 새 prefix(`/kuberca/...`) 로 변경
    - JSON property split 적용 (kube-rca-auth, kube-rca-ai 의 dataFrom.extract → data[] 로 재구조)
- 절차: helm-charts Phase 2/4/5 머지 직후 본 PR 머지 (drift window 최소화)
- 검증: ArgoCD `k8s-resources` app Synced, 기존 4개 CES 사라짐, kube-rca-* 4개는 새 prefix 로 SecretSynced

### Phase 7 — SSM 기존 path 삭제 (사용자 직접 실행)

모든 helm-charts/k8s-resources sync 검증 + secret 값 일치 확인 + 24h 관찰 후 진행 (롤백 윈도우).

```bash
REGION=ap-northeast-2
for old_path in \
  "basic-auth" \
  "grafana-auth" \
  "argocd-slack-token" \
  "kube-rca-auth" \
  "kube-rca-ai-api-keys" \
  "kube-rca-postgres-user-password" \
  "kube-rca-postgres-password" \
  "kube-rca-slack-channel-id" \
  "kube-rca-slack-token"; do
  echo "Deleting $old_path ..."
  aws ssm delete-parameter --name "$old_path" --region $REGION
done

# 검증: 기존 path 모두 사라졌는지
for old_path in basic-auth grafana-auth argocd-slack-token \
  kube-rca-auth kube-rca-ai-api-keys \
  kube-rca-postgres-user-password kube-rca-postgres-password \
  kube-rca-slack-channel-id kube-rca-slack-token; do
  aws ssm get-parameter --name "$old_path" --region $REGION 2>&1 \
    | grep -q ParameterNotFound && echo "$old_path: deleted ✓" || echo "$old_path: STILL EXISTS"
done
```

## Risks & Mitigations

### ServerSideApply 전제

직전 ESO 사고를 재분석하면 256KB annotation 한계는 ArgoCD 가 `ServerSideApply=true` 인데도 일부 케이스에서 client-side patch 로 fallback 한 결과였다. fallback 의 트리거는 다른 field manager 가 소유한 필드(`spec.conversion.webhookClientConfig`, manager=`external-secrets`/cert-controller) 를 새 매니페스트가 제거하려는 conflict 였다. 즉 **ServerSideApply 가 일관 유지되면 256KB 한계는 발생하지 않는다.**

이번 umbrella 전환 두 건은 직전 사고와 성격이 다르다:

| 측면 | 직전 ESO 0.14.3 → 2.4.1 | 이번 umbrella 전환 (ESO + kps) |
|---|---|---|
| spec 자체 변경 | 있음 (conversion 섹션 제거) | 없음 (helm template 결과 동일, packaging 만 변경) |
| Field manager conflict | 있음 (cert-controller 잔존 필드) | 거의 없음 (ArgoCD 가 모든 리소스 일관 소유) |
| 256KB annotation 한계 | client-side fallback 시 발생 | ServerSideApply 유지 시 발생 안 함 |

전제 조건:
- 두 ArgoCD app (`external-secrets`, `kube-prometheus-stack`) 의 `syncPolicy.syncOptions` 에 `ServerSideApply=true` 가 이미 있거나, 본 PR 에서 ApplicationSet/Application generator 매니페스트에 추가.
- ArgoCD v2.5+ (현 환경 v3.x 수준 가정 — Application 의 sync 기본 동작이 SSA 일관).

### Risks & Mitigations

| 위험 | 완화 |
|---|---|
| umbrella 전환 PR 의 git diff 가 +/- 수만 라인 (templates 통째 삭제, .tgz 1개 등장) | 코드 리뷰는 git diff 가 아니라 `helm template ... > rendered.yaml` 비교로 진행. before/after 렌더 결과가 일치(또는 무의미한 chart label 차이만)함을 reviewer 에게 명시. |
| ArgoCD sync 시 매니페스트 hash 변경 → 모든 리소스 재적용 reconcile | helm template 동등성 보장 시 ServerSideApply 가 spec 차이 없음을 인식해 no-op 또는 minimal patch. 트래픽 적은 시간대 적용 권장. |
| ServerSideApply 가 일관 유지되지 않을 가능성 (예: ApplicationSet 에서 옵션 누락) | 본 PR 에서 `external-secrets`, `kube-prometheus-stack` 두 Application 의 syncOptions 를 명시 검증. 누락 시 추가. |
| Field manager conflict 재발 (cert-controller 등 다른 controller 가 작성한 필드와 충돌) | ServerSideApply 단독으로 부족하면 syncOption 에 `RespectIgnoreDifferences=true` 또는 spec.ignoreDifferences 로 해당 필드 명시 제외. 직전 ESO 사고로 학습된 conversion 필드는 이미 정리됨. |
| 두 ArgoCD app 이 동일 ClusterExternalSecret 동시 적용 시 충돌 | helm-charts 와 k8s-resources 머지 윈도우 최소화. `creationPolicy: Owner` 라 재생성 정상 동작 (target Secret 일시 누락 가능 → ingress basic-auth 인증 실패 수 초). |
| target Secret 일시 누락으로 grafana/prometheus ingress 401 | 사용자 트래픽 적은 시간대 적용 권장. ESO refresh interval 1h 가 아닌 즉시 sync 되도록 수동 force-sync 가능. |
| awssm-secret 누락 시 ClusterSecretStore Invalid | 머지 전 `kubectl -n external-secrets get secret awssm-secret` 확인. 누락 시 사전 생성. |
| JSON split 값 mismatch (기존 admin-user JSON property name 과 다른 경우) | Phase 1 copy 시점에 `aws ssm get-parameter` + `jq -r .[key]` 결과 검증. |

## Verification

### Pre-merge
- `helm template` × 3 차트 + diff 비교
- `kubectl diff -f <(helm template …)`
- ArgoCD `kubectl get application external-secrets -o yaml` 의 conditions 검토 (직전 conversion issue 재현 여부)

### Post-merge
```bash
# CRD 정상
kubectl get crd externalsecrets.external-secrets.io -o jsonpath='{range .spec.versions[*]}{.name} served={.served} storage={.storage}{"\n"}{end}'

# ClusterSecretStore Valid
kubectl get clustersecretstore parameter-store -o jsonpath='{.status.conditions[*]}{"\n"}'

# 7개 ClusterExternalSecret SecretSynced
kubectl get clusterexternalsecret

# target Secret 들 재생성
for ns in monitoring kube-rca bookinfo; do
  kubectl -n $ns get secret basic-auth -o name 2>&1
done
kubectl -n monitoring get secret grafana-auth -o name
kubectl -n argocd get secret argocd-notifications-secret -o name

# Grafana/Prometheus/AlertManager ingress 401 healthcheck
curl -sk -u admin:<pw> https://grafana.kkamji.net/api/health
curl -sk -u <user>:<pw> https://prometheus.kkamji.net/-/healthy
```

## Rollback

1. helm-charts PR revert push → ArgoCD sync (vendor 형태로 복구, css-parameter-store template 사라짐)
2. k8s-resources PR revert (외부 4개 매니페스트 복구) → ArgoCD sync
3. SSM Phase 3 미실행 상태이면 기존 path 그대로 → 외부 매니페스트가 자연 동작 복귀
4. 만약 Phase 3 까지 실행 후 롤백이라면, copy 한 새 path 의 값을 다시 기존 path 로 복사 (대칭 복구)

## Open Questions (구현 시점에 확정)

1. **kube-rca-auth / kube-rca-ai SSM JSON 필드명**: Phase 1 시점에 `aws ssm get-parameter` 로 실제 키 확인 후 `/kuberca/kube-rca/auth/<key>` 결정.
2. **ESO/kube-prometheus-stack umbrella 전환 시 CRD 동기화**: 직전 conversion + 256KB 이슈 학습으로 PR 전 사전에 CRD `last-applied-configuration` annotation 정리 + server-side apply 강제 단계 포함.
3. **basic-auth target namespace 의 `bookinfo` 가 현재 작동 중인지** 확인. 작동 중이면 그대로, 아니면 namespace 목록 정리 (out of scope 가능).
4. **kube-prometheus-stack version**: 현재 vendor 75.12.0 → umbrella 전환 시 동일 75.12.0 유지 (버전 bump 는 surgical changes 원칙상 별 PR). 또는 사용자가 동시 bump 원하면 최신 확인 후 진행.
