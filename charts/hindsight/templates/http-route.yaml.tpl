{{- if .Values.exposure.enabled }}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ .Values.name }}-ui
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ .Values.exposure.gateway.name }}
      namespace: {{ .Values.exposure.gateway.namespace }}
      sectionName: {{ .Values.exposure.gateway.sectionName }}
  hostnames: [{{ .Values.exposure.hostname | quote }}]
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /
      backendRefs:
        - group: ""
          kind: Service
          name: {{ .Values.name }}-control-plane
          port: {{ .Values.server.controlPlane.service.port }}
          weight: 1
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ .Values.name }}-api
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ .Values.exposure.gateway.name }}
      namespace: {{ .Values.exposure.gateway.namespace }}
      sectionName: {{ .Values.exposure.gateway.sectionName }}
  hostnames: [{{ .Values.exposure.hostname | quote }}]
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: /v1
        - path:
            type: PathPrefix
            value: /mcp
      backendRefs:
        - group: ""
          kind: Service
          name: {{ .Values.name }}-api
          port: 8888
          weight: 1
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: {{ .Values.name }}-ui-owner
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .Values.name }}-ui
  basicAuth:
    users:
      name: {{ .Values.name }}-gateway-ui-auth
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: {{ .Values.name }}-api-owner
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .Values.name }}-api
  apiKeyAuth:
    credentialRefs:
      - name: {{ .Values.name }}-gateway-api-auth
        group: ""
        kind: Secret
    extractFrom:
      - headers: [Authorization]
    sanitize: false
{{- end }}
