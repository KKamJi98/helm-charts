# OpenClaw Helm Chart

KubeADM 홈랩에 OpenClaw 자율 AI 에이전트를 배포하는 커스텀 Helm chart.

## 주요 구성

| 항목 | 설명 |
|------|------|
| Image | `ghcr.io/openclaw/openclaw` |
| Port | 18789 (gateway) |
| Strategy | Recreate (단일 인스턴스) |
| Storage | PVC (`resource-policy: keep`) |
| Secrets | ExternalSecret → AWS SSM Parameter Store |
| Agents | values에서 SOUL.md + 모델 라우팅 자동 생성 |

## 설치

```bash
helm install openclaw ./openclaw \
  -n openclaw --create-namespace \
  -f openclaw/kkamji_local_values.yaml
```

## 업그레이드

```bash
helm upgrade openclaw ./openclaw \
  -n openclaw \
  -f openclaw/kkamji_local_values.yaml
```

## 삭제

```bash
helm uninstall openclaw -n openclaw
```

> PVC는 `resource-policy: keep`으로 보존됩니다. 수동 삭제 필요:
> `kubectl delete pvc openclaw-data -n openclaw`

## 설정

### ExternalSecret (API Keys)

AWS SSM Parameter Store에 JSON으로 저장:

```
Path: /openclaw
Value: { "claude-api-key": "sk-...", "gemini-api-key": "AI..." }
```

`kkamji_local_values.yaml`에서 활성화:

```yaml
externalSecret:
  enabled: true
  secretStoreName: parameter-store
  remoteKey: /openclaw
```

### Agents

`values.agents`에 에이전트를 정의하면 SOUL.md와 `openclaw.json5` 모델 라우팅이 자동 생성됩니다.

```yaml
agents:
  devops:
    model: "anthropic:claude-sonnet-4-6"
    soul: |
      You are a DevOps engineer specializing in Kubernetes and AWS.
```

> SOUL.md는 매 Pod 재시작 시 chart values로 덮어씌워집니다.
> Pod 내 수정은 일시적이며, 영구 변경은 values 파일에서 관리하세요.

### OpenAI OAuth

OpenAI는 OAuth 방식으로 Pod에 직접 접속하여 로그인:

```bash
kubectl exec -it -n openclaw deploy/openclaw -- /bin/sh
```

## 검증

```bash
helm lint ./openclaw -f openclaw/kkamji_local_values.yaml
helm template openclaw ./openclaw -n openclaw -f openclaw/kkamji_local_values.yaml
```
