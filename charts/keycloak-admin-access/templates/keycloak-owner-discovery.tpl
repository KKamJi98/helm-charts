{{- $discovery := .Values.keycloakOwnerDiscovery -}}
{{- if and (ne (toJson $discovery) (toJson (dict "enabled" false))) (ne (toJson $discovery) (toJson (dict "enabled" true))) -}}
{{- fail "Owner discovery blocked: only boolean keycloakOwnerDiscovery.enabled is supported" -}}
{{- end -}}
{{- if $discovery.enabled -}}
{{- if or (ne .Release.Namespace "envoy-gateway-system") (ne .Release.Name "keycloak-admin-access") -}}
{{- fail "Owner discovery blocked: exact namespace/release identity required" -}}
{{- end -}}
{{- if not .Values.keycloakAdminPrivate.enabled -}}
{{- fail "Owner discovery blocked: existing private admin named Service ReferenceGrant is required" -}}
{{- end -}}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: keycloak-owner-enrollment-server-ingress
  namespace: keycloak
spec:
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: envoy-gateway-system
      podSelector:
        matchLabels:
          app.kubernetes.io/component: proxy
          gateway.envoyproxy.io/owning-gateway-name: keycloak-owner-enrollment
          gateway.envoyproxy.io/owning-gateway-namespace: envoy-gateway-system
          kkamji.net/access: keycloak-owner-enrollment
    ports:
    - port: 8080
      protocol: TCP
  podSelector:
    matchLabels:
      app: keycloak
      app.kubernetes.io/component: server
      app.kubernetes.io/instance: keycloak
      app.kubernetes.io/managed-by: keycloak-operator
  policyTypes:
  - Ingress
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  namespace: envoy-gateway-system
  name: keycloak-owner-enrollment
  annotations:
    external-dns.alpha.kubernetes.io/controller: keycloak-owner-disabled
spec:
  hostnames:
  - sso.kkamji.net
  parentRefs:
  - name: keycloak-owner-enrollment
    sectionName: https
    group: gateway.networking.k8s.io
    kind: Gateway
    namespace: envoy-gateway-system
  rules:
  - backendRefs:
    - group: ''
      kind: Service
      name: keycloak-service
      namespace: keycloak
      port: 8080
      weight: 1
    matches:
    - method: GET
      path:
        type: Exact
        value: /realms/kkamji/.well-known/openid-configuration
---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: keycloak-owner-enrollment-prometheus-ingress
  namespace: envoy-gateway-system
spec:
  endpointSelector:
    matchLabels:
      k8s:app.kubernetes.io/component: proxy
      k8s:gateway.envoyproxy.io/owning-gateway-name: keycloak-owner-enrollment
      k8s:gateway.envoyproxy.io/owning-gateway-namespace: envoy-gateway-system
      k8s:kkamji.net/access: keycloak-owner-enrollment
  ingress:
  - fromEndpoints:
    - matchLabels:
        k8s:io.kubernetes.pod.namespace: monitoring
        k8s:io.cilium.k8s.policy.serviceaccount: kube-prometheus-stack-prometheus
    toPorts:
    - ports:
      - port: "19001"
        protocol: TCP
      rules:
        http:
        - method: GET
          path: "^/stats/prometheus$"
{{- end }}
