{{- if .Values.mokaRecallOAuth.service.enabled }}
{{- if not .Values.mokaRecallOAuth.canaryEnabled }}
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
{{- end }}
