{{- include "keycloak.guard" . }}
{{- if eq .Values.preparationProfile "keycloak-26.8.2-production" }}
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: keycloak-backup-s3
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-wave: '-1'
spec:
  refreshPolicy: Periodic
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: keycloak-backup-s3
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      engineVersion: v2
      mergePolicy: Merge
      type: Opaque
      data:
        AWS_REGION: ap-northeast-2
  data:
  - secretKey: ACCESS_KEY_ID
    remoteRef:
      key: /kkamji/keycloak/backup-s3
      property: access_key_id
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
  - secretKey: ACCESS_SECRET_KEY
    remoteRef:
      key: /kkamji/keycloak/backup-s3
      property: secret_access_key
      conversionStrategy: Default
      decodingStrategy: None
      metadataPolicy: None
---
apiVersion: postgresql.cnpg.io/v1
kind: ScheduledBackup
metadata:
  name: keycloak-db-backup
  namespace: keycloak
spec:
  schedule: '0 0 18 * * *'
  backupOwnerReference: cluster
  cluster:
    name: keycloak-db
  method: barmanObjectStore
  immediate: false
  suspend: false
{{- end }}
