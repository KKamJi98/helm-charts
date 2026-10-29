{{- if .Values.exposure.enabled }}
{{- range $suffix, $requests := dict "ui" 300 "api" 120 }}
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
  rateLimit:
    type: Local
    local:
      rules:
        - limit:
            requests: {{ $requests }}
            unit: Minute
{{- end }}
{{- end }}
