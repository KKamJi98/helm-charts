{{- if .Values.exposure.enabled }}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyExtensionPolicy
metadata:
  name: {{ .Values.name }}-response-security-headers
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .Values.name }}-ui
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .Values.name }}-api
  lua:
    - type: Inline
      inline: |
        function envoy_on_response(response_handle)
          local headers = response_handle:headers()
          headers:replace("strict-transport-security", "max-age=86400")
          headers:replace("x-content-type-options", "nosniff")
          headers:replace("referrer-policy", "no-referrer")
        end
{{- end }}
