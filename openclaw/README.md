# OpenClaw Helm Chart

Kubernetes에서 OpenClaw Gateway를 홈랩용으로 빠르게 올리기 위한 Helm chart입니다. 기본 chart는 `gateway.auth.mode: token`을 전제로 동작하고, `kkamji_local_values.yaml`은 NodePort + LAN access + `web_search`까지 포함한 homelab preset입니다.

## 주요 구성

| 항목 | 설명 |
|------|------|
| Runtime | `ghcr.io/openclaw/openclaw` / `appVersion: 2026.4.2` |
| Port | `18789` (WS + HTTP multiplex) |
| Auth | Gateway token Secret 자동 생성 또는 existing Secret 참조 |
| Storage | PVC 또는 `emptyDir` (`resource-policy: keep`) |
| Agents | `agents.defaults` + `agents.list[]` 자동 생성 |
| SOUL.md | agent별 workspace에 자동 배치 |
| Web Search | `duckduckgo` 또는 `searxng` provider values 지원 |

## 설치

chart 루트에서 실행:

```bash
helm install openclaw . \
  -n openclaw --create-namespace \
  -f kkamji_local_values.yaml
```

업그레이드:

```bash
helm upgrade openclaw . \
  -n openclaw \
  -f kkamji_local_values.yaml
```

삭제:

```bash
helm uninstall openclaw -n openclaw
```

PVC는 `resource-policy: keep`으로 보존됩니다. 완전히 지우려면 별도로 삭제해야 합니다.

```bash
kubectl delete pvc openclaw-data -n openclaw
```

## 접속

`kkamji_local_values.yaml` 기준으로는 NodePort를 사용합니다.

```bash
export NODE_PORT=$(kubectl get svc -n openclaw openclaw -o jsonpath='{.spec.ports[0].nodePort}')
export NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
export OPENCLAW_URL="http://$NODE_IP:$NODE_PORT/"
export OPENCLAW_TOKEN=$(kubectl get secret -n openclaw openclaw-gateway-auth -o jsonpath='{.data.token}' | openssl base64 -d -A)
echo "$OPENCLAW_URL?token=$OPENCLAW_TOKEN"
```

Control UI는 첫 접속 후 token을 저장하므로, 이후에는 query string 없이도 계속 사용할 수 있습니다.

## 설정

### Gateway Auth

non-loopback bind에서는 auth가 필수입니다. 이 chart는 기본적으로 token auth를 켭니다.

```yaml
gateway:
  bind: "lan"
  auth:
    mode: "token"
    existingSecretName: ""
    existingSecretKey: ""
    generateSecret: true
```

- `existingSecretName`을 주면 기존 Secret을 사용합니다.
- 비워두면 chart가 `RELEASE-gateway-auth` Secret을 생성합니다.
- `OPENCLAW_GATEWAY_TOKEN`은 Secret에서 env로 주입됩니다.

### API Keys

모델 API key는 `envFromSecret`으로 주입합니다.

```yaml
envFromSecretName: "openclaw-api-keys"

envFromSecret:
  - name: ANTHROPIC_API_KEY
    secretKey: claude-api-key
  - name: GEMINI_API_KEY
    secretKey: gemini-api-key
```

수동 Secret 예시:

```bash
kubectl create secret generic openclaw-api-keys \
  -n openclaw \
  --from-literal=claude-api-key='sk-...' \
  --from-literal=gemini-api-key='AI...'
```

External Secrets Operator를 쓰면 chart가 `ExternalSecret`도 생성할 수 있습니다.

```yaml
externalSecret:
  enabled: true
  secretStoreName: parameter-store
  secretStoreKind: ClusterSecretStore
  remoteKey: /openclaw
  targetSecretName: openclaw-api-keys
```

이 경우 `remoteKey`의 key/value들을 `targetSecretName`으로 extract 합니다.

### Agents

`values.agents`는 최신 OpenClaw config 형식인 `agents.defaults` + `agents.list[]`로 렌더됩니다.

```yaml
defaultAgentId: devops

agents:
  devops:
    model: "anthropic/claude-sonnet-4-6"
    soul: |
      You are a DevOps engineer specializing in Kubernetes and AWS.
```

- model은 `provider/model` 형식이어야 합니다.
- agent가 2개 이상이면 `defaultAgentId`가 필수입니다.
- 각 agent의 `SOUL.md`는 `<dataDir>/workspaces/<agentId>/SOUL.md`에 배치됩니다.
- Pod 재시작 시 values 기준으로 다시 덮어씌워집니다.

### Web Search

DuckDuckGo를 기본 fallback으로 바로 켤 수 있습니다.

```yaml
webSearch:
  enabled: true
  provider: "duckduckgo"
```

SearXNG를 쓰려면 provider와 base URL을 함께 지정합니다.

```yaml
webSearch:
  enabled: true
  provider: "searxng"
  searxng:
    baseUrl: "http://searxng.search.svc.cluster.local:8080"
    categories: "general,news"
    language: "en"
```

추가 provider credential은 `openclaw configure --section web` 또는 관련 env var로 설정하면 됩니다.

## OpenAI OAuth

OpenAI처럼 OAuth 기반 provider는 callback이 필요하므로 `port-forward`가 필요합니다.

터미널 1:

```bash
kubectl port-forward -n openclaw deploy/openclaw 1455:1455
```

터미널 2:

```bash
kubectl exec -it -n openclaw deploy/openclaw -- openclaw models auth login --provider openai
```

## 검증

```bash
helm lint . -f kkamji_local_values.yaml
helm template openclaw . -n openclaw -f kkamji_local_values.yaml
helm test openclaw -n openclaw
```
