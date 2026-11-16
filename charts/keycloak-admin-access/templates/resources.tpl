{{- if and (ne (toJson .Values) (toJson (dict "keycloakAdminPrivate" (dict "enabled" false)))) (ne (toJson .Values) (toJson (dict "keycloakAdminPrivate" (dict "enabled" true)))) -}}
{{- fail "Private admin blocked: only boolean keycloakAdminPrivate.enabled is supported" -}}
{{- end -}}
{{- if .Values.keycloakAdminPrivate.enabled -}}
{{- if or (ne .Release.Namespace "envoy-gateway-system") (ne .Release.Name "keycloak-admin-access") -}}
{{- fail "Private admin blocked: exact namespace/release identity required" -}}
{{- end -}}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: keycloak-admin-private
  namespace: envoy-gateway-system
  annotations:
    external-dns.alpha.kubernetes.io/controller: keycloak-admin-private-disabled
spec:
  hostnames:
    - sso.kkamji.net
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: keycloak-admin-private
      namespace: envoy-gateway-system
      sectionName: https
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - group: ""
          kind: Service
          name: keycloak-service
          namespace: keycloak
          port: 8080
          weight: 1
---
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: keycloak-admin-private
  namespace: keycloak
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: envoy-gateway-system
  to:
    - group: ""
      kind: Service
      name: keycloak-service
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: keycloak-admin-private-server-ingress
  namespace: keycloak
spec:
  podSelector:
    matchLabels:
      app: keycloak
      app.kubernetes.io/component: server
      app.kubernetes.io/instance: keycloak
      app.kubernetes.io/managed-by: keycloak-operator
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: envoy-gateway-system
          podSelector:
            matchLabels:
              app.kubernetes.io/component: proxy
              gateway.envoyproxy.io/owning-gateway-name: keycloak-admin-private
              gateway.envoyproxy.io/owning-gateway-namespace: envoy-gateway-system
              kkamji.net/access: keycloak-admin-private
      ports:
        - protocol: TCP
          port: 8080
{{- end }}
