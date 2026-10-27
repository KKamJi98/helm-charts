{{- include "kkamji-hindsight.validate" . }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.name }}-bootstrap
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
data:
  seed_auth.py: |
    {{- .Files.Get "files/seed_auth.py" | nindent 4 }}
  model-files.json: |
    {{- .Values.model.filesSha256 | toPrettyJson | nindent 4 }}
