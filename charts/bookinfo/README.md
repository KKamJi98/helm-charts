# Bookinfo (Istio sample)

This chart packages the upstream Bookinfo manifests from Istio.

Sources:
- https://istio.io/latest/docs/examples/bookinfo/
- https://raw.githubusercontent.com/istio/istio/release-1.28/samples/bookinfo/platform/kube/bookinfo.yaml
- https://raw.githubusercontent.com/istio/istio/release-1.28/samples/bookinfo/networking/bookinfo-gateway.yaml

## Values

- `gateway.enabled`: Toggle the Bookinfo Gateway/VirtualService.
- `ingress.enabled`: Enable nginx ingress for productpage.
- `ingress.annotations`: Add nginx ingress annotations (basic-auth 포함 가능).
- `ingress.hosts`: Host list (e.g., `kuberca-demo.kkamji.net`).

Note: `nginx.ingress.kubernetes.io/auth-secret`가 `basic-auth`를 참조할 경우,
`k8s-resources/external-secrets/cluster-external-secret/basic-auth-ces.yaml`로부터
Secret이 생성되어야 합니다.
