{{- $discovery := .Values.keycloakOwnerDiscovery -}}
{{- if and (ne (toJson $discovery) (toJson (dict "enabled" false))) (ne (toJson $discovery) (toJson (dict "enabled" true))) -}}
{{- fail "Owner discovery blocked: only boolean keycloakOwnerDiscovery.enabled is supported" -}}
{{- end -}}
{{- if $discovery.enabled -}}
{{- if or (ne .Release.Namespace "envoy-gateway-system") (ne .Release.Name "envoy-gateway") -}}
{{- fail "Owner discovery blocked: exact namespace/release identity required" -}}
{{- end -}}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: keycloak-owner-enrollment-deny-ingress
  namespace: envoy-gateway-system
spec:
  podSelector:
    matchLabels:
      kkamji.net/access: keycloak-owner-enrollment
  policyTypes:
  - Ingress
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyProxy
metadata:
  name: keycloak-owner-enrollment
  namespace: envoy-gateway-system
spec:
  concurrency: 1
  logging:
    level:
      default: warn
  mergeGateways: false
  provider:
    kubernetes:
      envoyDeployment:
        container:
          resources:
            limits:
              cpu: 500m
              memory: 256Mi
            requests:
              cpu: 100m
              memory: 128Mi
        pod:
          labels:
            kkamji.net/access: keycloak-owner-enrollment
        replicas: 1
      envoyService:
        annotations:
          external-dns.alpha.kubernetes.io/controller: keycloak-owner-disabled
        type: ClusterIP
    type: Kubernetes
  telemetry:
    accessLog:
      disable: true
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  namespace: envoy-gateway-system
  name: keycloak-owner-enrollment
  annotations:
    external-dns.alpha.kubernetes.io/controller: keycloak-owner-disabled
spec:
  gatewayClassName: envoy
  infrastructure:
    parametersRef:
      group: gateway.envoyproxy.io
      kind: EnvoyProxy
      name: keycloak-owner-enrollment
  listeners:
  - allowedRoutes:
      namespaces:
        from: Same
      kinds:
      - group: gateway.networking.k8s.io
        kind: HTTPRoute
    hostname: sso.kkamji.net
    name: https
    port: 443
    protocol: HTTPS
    tls:
      certificateRefs:
      - group: ''
        kind: Secret
        name: wildcard-kkamji-net-tls
      mode: Terminate
{{- end }}
