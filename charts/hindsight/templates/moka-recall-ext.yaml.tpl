{{- $mokaSvc := .Values.mokaRecallOAuth.service.enabled -}}
{{- $grok := .Values.grokMemory.enabled -}}
{{- $retain := or (and $mokaSvc .Values.mokaRecallOAuth.service.retainEnabled) (and $grok .Values.grokMemory.retainEnabled) -}}
{{- if or $mokaSvc $grok }}
{{- if and $mokaSvc (not .Values.mokaRecallOAuth.canaryEnabled) }}
{{- fail "The Moka recall extension requires the Moka OAuth workload" }}
{{- end }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.name }}-moka-recall-ext
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
data:
  hindsight_moka_recall_ext.py: |
    {{- .Files.Get "files/hindsight_moka_recall_ext.py" | nindent 4 }}
{{- if and $grok (not $mokaSvc) }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: hindsight-moka-recall-oauth-api-key
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef: {name: parameter-store, kind: ClusterSecretStore}
  target:
    name: hindsight-moka-recall-oauth-api-key
    creationPolicy: Orphan
    deletionPolicy: Retain
    template: {type: Opaque}
  data:
    - secretKey: recall_api_key
      remoteRef:
        key: /kkamji/automation/hindsight/recall-tunnel/runtime
        property: recall_api_key
    {{- if $retain }}
    - secretKey: retain_api_key
      remoteRef:
        key: /kkamji/automation/hindsight/recall-tunnel/runtime
        property: retain_api_key
    {{- end }}
{{- end }}
{{- end }}
