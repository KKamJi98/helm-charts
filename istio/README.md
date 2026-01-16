# Istio Helm Charts

Istio 1.28.2 버전 Helm 차트 설치 가이드

## 구성 요소

| Chart | Version | Description |
|-------|---------|-------------|
| base | 1.28.2 | Istio CRDs 및 클러스터 리소스 |
| istiod | 1.28.2 | Istio Control Plane (Pilot) |

## 사전 요구사항

- Kubernetes 1.26+
- Helm 3.6+
- kubectl configured

## 설치 순서

### 1. Namespace 생성

```bash
kubectl create namespace istio-system
```

### 2. Istio Base (CRDs) 설치

```bash
helm install istio-base ./base \
  -n istio-system \
  -f base/kkamji-local-values.yaml
```

**검증:**
```bash
kubectl get crds | grep istio
```

### 3. Istiod (Control Plane) 설치

```bash
helm install istiod ./istiod \
  -n istio-system \
  -f istiod/kkamji-local-values.yaml \
  --wait
```

**검증:**
```bash
kubectl get pods -n istio-system
kubectl get svc -n istio-system
```

## 업그레이드

```bash
# Base 업그레이드
helm upgrade istio-base ./base \
  -n istio-system \
  -f base/kkamji-local-values.yaml

# Istiod 업그레이드
helm upgrade istiod ./istiod \
  -n istio-system \
  -f istiod/kkamji-local-values.yaml
```

## 삭제 (역순)

```bash
# 1. Istiod 삭제
helm uninstall istiod -n istio-system

# 2. Base 삭제
helm uninstall istio-base -n istio-system

# 3. Namespace 삭제 (선택사항)
kubectl delete namespace istio-system
```

## 사이드카 인젝션 활성화

특정 네임스페이스에 사이드카 자동 주입 활성화:

```bash
kubectl label namespace <namespace> istio-injection=enabled
```

## 유용한 명령어

```bash
# Istio 상태 확인
kubectl get pods -n istio-system

# Istiod 로그 확인
kubectl logs -n istio-system -l app=istiod -f

# 사이드카 인젝션 상태 확인
kubectl get namespace -L istio-injection

# Istio 프록시 상태 확인
istioctl proxy-status
```

## 참고 문서

- [Istio 공식 Helm 설치 가이드](https://istio.io/latest/docs/setup/install/helm/)
- [Istio 릴리즈 노트](https://istio.io/latest/news/releases/)
