{{- include "keycloak.guard" . }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: keycloak-default-deny-ingress
  namespace: keycloak
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress: []

---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: keycloak-server-ingress
  namespace: keycloak
spec:
  podSelector:
    matchLabels: &id001
      app: keycloak
      app.kubernetes.io/instance: keycloak
      app.kubernetes.io/managed-by: keycloak-operator
      app.kubernetes.io/component: server
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
          gateway.envoyproxy.io/owning-gateway-name: kkamji
          gateway.envoyproxy.io/owning-gateway-namespace: envoy-gateway-system
    ports:
    - protocol: TCP
      port: 8080
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: keycloak
      podSelector:
        matchLabels:
          app.kubernetes.io/name: keycloak-operator
    ports:
    - protocol: TCP
      port: 9000
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: keycloak
      podSelector:
        matchLabels: *id001
    ports:
    - protocol: TCP
      port: 7800
    - protocol: TCP
      port: 57800

---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: keycloak-db-ingress
  namespace: keycloak
spec:
  podSelector:
    matchLabels:
      cnpg.io/cluster: keycloak-db
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: keycloak
      podSelector:
        matchLabels:
          app.kubernetes.io/instance: keycloak
          app.kubernetes.io/managed-by: keycloak-operator
        matchExpressions:
        - key: app
          operator: In
          values:
          - keycloak
          - keycloak-realm-import
    ports:
    - protocol: TCP
      port: 5432
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: cnpg-system
      podSelector:
        matchLabels:
          app.kubernetes.io/name: cloudnative-pg
          app.kubernetes.io/instance: cloudnative-pg
    ports:
    - protocol: TCP
      port: 5432
    - protocol: TCP
      port: 8000
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: keycloak
      podSelector:
        matchLabels:
          cnpg.io/cluster: keycloak-db
    ports:
    - protocol: TCP
      port: 5432
    - protocol: TCP
      port: 8000
