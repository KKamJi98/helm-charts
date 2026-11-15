{{- include "keycloak.guard" . }}
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: keycloak-db-app
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-1'
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: keycloak-db-app
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: kubernetes.io/basic-auth
  data:
  - secretKey: username
    remoteRef:
      key: /kkamji/keycloak/database
      property: username
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
  - secretKey: password
    remoteRef:
      key: /kkamji/keycloak/database
      property: password
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None

---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: keycloak-bootstrap-admin
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-1'
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: keycloak-bootstrap-admin
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
  - secretKey: username
    remoteRef:
      key: /kkamji/keycloak/bootstrap
      property: username
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
  - secretKey: password
    remoteRef:
      key: /kkamji/keycloak/bootstrap
      property: password
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None

---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: keycloak-oidc-client
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-1'
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: keycloak-oidc-client
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
  - secretKey: client-secret
    remoteRef:
      key: /kkamji/keycloak/clients/kkamji-platform
      property: client_secret
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
