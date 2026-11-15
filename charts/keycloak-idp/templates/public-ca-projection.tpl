{{- include "keycloak.guard" . }}
{{- if .Values.publicCaProjection.enabled }}
# Only the existing ESO controller requests short-lived tokens for this reader.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: keycloak-db-ca-reader
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-3'
automountServiceAccountToken: false
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: keycloak-db-ca-reader
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-3'
rules:
- apiGroups: ['']
  resources: [secrets]
  resourceNames: [keycloak-db-ca]
  verbs: [get]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: keycloak-db-ca-reader
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-3'
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: keycloak-db-ca-reader
subjects:
- kind: ServiceAccount
  name: keycloak-db-ca-reader
  namespace: keycloak
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: keycloak-db-ca-token-request
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-3'
rules:
- apiGroups: ['']
  resources: [serviceaccounts/token]
  resourceNames: [keycloak-db-ca-reader]
  verbs: [create]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: keycloak-db-ca-token-request
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-3'
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: keycloak-db-ca-token-request
subjects:
- kind: ServiceAccount
  name: external-secrets
  namespace: external-secrets
---
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: keycloak-db-ca
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-2'
spec:
  provider:
    kubernetes:
      remoteNamespace: keycloak
      server:
        url: https://kubernetes.default.svc
        caProvider:
          type: ConfigMap
          name: kube-root-ca.crt
          key: ca.crt
      auth:
        serviceAccount:
          name: keycloak-db-ca-reader
---
# Same wave as the CNPG Cluster: a negative wave here would wait for a CA
# that the not-yet-created database must generate. Initial app gating is manual.
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: keycloak-db-client-trust
  namespace: keycloak
spec:
  refreshPolicy: Periodic
  refreshInterval: 1m
  secretStoreRef:
    name: keycloak-db-ca
    kind: SecretStore
  target:
    name: keycloak-db-client-trust
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
  - secretKey: ca.crt
    remoteRef:
      key: keycloak-db-ca
      property: ca.crt
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
{{- end }}
