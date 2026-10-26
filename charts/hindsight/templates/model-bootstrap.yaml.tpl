apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.name }}-model-bootstrap
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
data:
  prepare_model.py: |
    {{- .Files.Get "files/prepare_model.py" | nindent 4 }}
  files-sha256.json: |
    {{- .Values.model.filesSha256 | toPrettyJson | nindent 4 }}
