{{- if .Values.exposure.enabled }}
{{- range $suffix := list "ui" "api" }}
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  name: {{ $.Values.name }}-{{ $suffix }}-limits
  labels:
    {{- include "kkamji-hindsight.labels" $ | nindent 4 }}
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ $.Values.name }}-{{ $suffix }}
  # Buffers request bodies only. Streaming uploads/upgrades are not supported.
  requestBuffer:
    limit: 1Mi
{{- end }}
{{- end }}
