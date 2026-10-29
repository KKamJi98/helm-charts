{{- $root := . -}}
{{- range $entry := list
  (dict "name" .Values.auth.apiSecretName "keys" (dict "HINDSIGHT_API_TENANT_API_KEY" "api_key"))
  (dict "name" .Values.auth.controlPlaneSecretName "keys" (dict "HINDSIGHT_CP_DATAPLANE_API_KEY" "api_key" "HINDSIGHT_CP_ACCESS_KEY" "ui_access_key"))
  (dict "name" (printf "%s-gateway-ui-auth" .Values.name) "keys" (dict ".htpasswd" "ui_htpasswd"))
}}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ $entry.name }}
  labels:
    {{- include "kkamji-hindsight.labels" $root | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: {{ $root.Values.auth.refreshInterval }}
  secretStoreRef:
    name: {{ $root.Values.auth.secretStoreName }}
    kind: ClusterSecretStore
  target:
    name: {{ $entry.name }}
    creationPolicy: Orphan
    deletionPolicy: Retain
  data:
  {{- range $key, $property := $entry.keys }}
    - secretKey: {{ $key | quote }}
      remoteRef:
        key: {{ $root.Values.auth.ssmKey }}
        property: {{ $property }}
  {{- end }}
{{- end }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ .Values.name }}-gateway-api-auth
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: {{ .Values.auth.refreshInterval }}
  secretStoreRef:
    name: {{ .Values.auth.secretStoreName }}
    kind: ClusterSecretStore
  target:
    name: {{ .Values.name }}-gateway-api-auth
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      engineVersion: v2
      mergePolicy: Replace
      type: Opaque
      data:
        owner: {{ `{{ .api_key }}` | quote }}
  data:
    - secretKey: api_key
      remoteRef:
        key: {{ .Values.auth.ssmKey }}
        property: api_key
{{- if .Values.exposure.enabled }}
{{- range $entry := list
  (dict "name" (printf "%s-google-oidc" .Values.name) "keys" (dict "client-secret" "oidc_client_secret"))
  (dict "name" (printf "%s-gateway-client-keys" .Values.name) "keys" (dict "wsl_claude" "wsl_claude" "wsl_hermes" "wsl_hermes" "mac_claude" "mac_claude" "mac_hermes" "mac_hermes"))
}}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ $entry.name }}
  labels:
    {{- include "kkamji-hindsight.labels" $root | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: {{ $root.Values.auth.refreshInterval }}
  secretStoreRef:
    name: {{ $root.Values.auth.secretStoreName }}
    kind: ClusterSecretStore
  target:
    name: {{ $entry.name }}
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
  {{- range $key, $property := $entry.keys }}
    - secretKey: {{ $key | quote }}
      remoteRef:
        key: {{ required "exposure requires auth.edgeSsmKey" $root.Values.auth.edgeSsmKey | quote }}
        property: {{ $property }}
  {{- end }}
{{- end }}
{{- end }}
