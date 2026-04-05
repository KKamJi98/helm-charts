# OpenClaw Helm Chart

KubeADM 홈랩에 OpenClaw 자율 AI 에이전트를 배포하는 커스텀 Helm chart.

## 주요 구성

| 항목 | 설명 |
|------|------|
| Image | `ghcr.io/openclaw/openclaw` |
| Port | 18789 (gateway WebSocket) |
| Strategy | Recreate (단일 인스턴스) |
| Storage | PVC (`resource-policy: keep`) |
| Secrets | `envFromSecret` + `optional: true` (Secret 없어도 기동 가능) |
| Agents | values에서 SOUL.md + 모델 라우팅 자동 생성 |
| Gateway Bind | `gateway.bind: "lan"` (0.0.0.0, env `OPENCLAW_GATEWAY_BIND`) |

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

### Gateway

Gateway bind address는 `gateway.bind`로 설정합니다. Kubernetes 환경에서는 `"lan"` (0.0.0.0)이 필수입니다.

```yaml
gateway:
  bind: "lan"   # Options: "loopback", "lan", "tailnet", "auto"
```

ConfigMap(`openclaw.json5`)과 환경변수(`OPENCLAW_GATEWAY_BIND`) 양쪽으로 적용됩니다.

### Health Probes

Gateway가 loopback에 바인딩될 수 있으므로 probe는 exec 방식으로 컨테이너 내부에서 `127.0.0.1`을 직접 호출합니다.

| Probe | Endpoint | 용도 |
|-------|----------|------|
| startupProbe | `/healthz` | 초기화 완료 대기 (최대 ~155초) |
| livenessProbe | `/healthz` | 프로세스 생존 확인 |
| readinessProbe | `/readyz` | 트래픽 수신 가능 확인 |

### API Keys (envFromSecret)

`envFromSecret`로 Secret에서 환경변수를 주입합니다. `optional: true`로 설정되어 **Secret이 없어도 Pod는 정상 기동**됩니다.

```yaml
envFromSecretName: "openclaw-api-keys"   # 기본 Secret 이름

envFromSecret:
  - name: ANTHROPIC_API_KEY
    secretKey: claude-api-key
  - name: GEMINI_API_KEY
    secretKey: gemini-api-key
    # secretName: my-other-secret  # per-entry override 가능
```

Secret 생성 방법 (선택):

```bash
# 수동 생성
kubectl create secret generic openclaw-api-keys \
  -n openclaw \
  --from-literal=claude-api-key='sk-...' \
  --from-literal=gemini-api-key='AI...'
```

ExternalSecrets operator 사용 시 별도 ExternalSecret 리소스를 생성하면 됩니다.

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

OpenAI는 OAuth 방식으로 인증합니다. Pod에 직접 접속하여 로그인:

```bash
kubectl exec -it -n openclaw deploy/openclaw -- openclaw models auth login --provider openai
```

## 초기 세팅

### 1. 설치 후 Pod 상태 확인

```bash
kubectl get pods -n openclaw
# STATUS: Running, READY: 1/1 확인
```

### 2. OpenClaw 설정 (openclaw config)

Pod에 접속하여 모델/프로바이더 설정:

```bash
kubectl exec -it -n openclaw deploy/openclaw -- openclaw config
```

### 3. 모델 프로바이더 인증

#### API Key 방식

Secret으로 API key를 주입하는 방식. [API Keys (envFromSecret)](#api-keys-envfromsecret) 섹션 참고.

#### OAuth 방식 (OpenAI 등)

OAuth 인증은 브라우저 콜백이 필요하므로 **port-forward**가 필수입니다.

**터미널 1** — callback 포트 포워딩:

```bash
kubectl port-forward -n openclaw deploy/openclaw 1455:1455
```

**터미널 2** — 인증 시작:

```bash
kubectl exec -it -n openclaw deploy/openclaw -- openclaw models auth login --provider openai
```

OAuth 로그인 URL이 출력되면 맥북 브라우저에서 열어 인증을 완료합니다.
콜백이 `localhost:1455`로 돌아오며, port-forward를 통해 Pod로 전달됩니다.

> **주의**: port-forward 없이 진행하면 콜백이 Pod 내부 localhost로 향하므로 브라우저에서 접근할 수 없습니다.

### 4. 인증 확인

```bash
kubectl exec -n openclaw deploy/openclaw -- openclaw models list
```

## 검증

```bash
helm lint ./openclaw -f openclaw/kkamji_local_values.yaml
helm template openclaw ./openclaw -n openclaw -f openclaw/kkamji_local_values.yaml
```
