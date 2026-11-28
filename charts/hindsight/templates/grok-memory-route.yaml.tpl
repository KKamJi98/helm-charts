{{- $cfg := .Values.grokMemory -}}
{{- $public := $cfg.publicEnabled -}}
{{- $authMode := ($cfg.authMode | default "oauth") -}}
{{- $canonical := (and .Values.exposure.enabled (eq .Release.Namespace "hindsight") (eq .Values.exposure.hostname "hindsight.kkamji.net") (eq .Values.exposure.gateway.name "kkamji") (eq .Values.exposure.gateway.namespace "envoy-gateway-system") (eq .Values.exposure.gateway.sectionName "https")) -}}
{{- if and $public (not $cfg.enabled) }}
{{- fail "Grok Memory public route requires grokMemory.enabled=true" }}
{{- end }}
{{- if and $cfg.enabled (not $canonical) }}
{{- fail "Grok Memory requires the existing Hindsight HTTPS listener and namespace" }}
{{- end }}
{{- if and $canonical $cfg.enabled }}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: HTTPRouteFilter
metadata:
  name: hindsight-grok-memory-closed
  namespace: hindsight
spec:
  directResponse:
    statusCode: 404
    header:
      set:
        - {name: Cache-Control, value: no-store}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: hindsight-grok-memory
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "10"
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: kkamji
      namespace: envoy-gateway-system
      sectionName: https
  hostnames: [hindsight.kkamji.net]
  rules:
    {{- if $public }}
    - matches:
        {{- if eq $authMode "oauth" }}
        - path: {type: Exact, value: /.well-known/oauth-authorization-server/grok-memory}
        - path: {type: Exact, value: /.well-known/oauth-protected-resource/grok-memory/mcp}
        - path: {type: Exact, value: /grok-memory/authorize}
        - path: {type: Exact, value: /grok-memory/token}
        - path: {type: Exact, value: /grok-memory/register}
        - path: {type: Exact, value: /grok-memory/consent}
        - path: {type: Exact, value: /grok-memory/google/callback}
        {{- end }}
        - path: {type: Exact, value: /grok-memory/mcp}
      filters:
        - type: ResponseHeaderModifier
          responseHeaderModifier:
            set:
              - {name: Strict-Transport-Security, value: max-age=86400}
              - {name: X-Content-Type-Options, value: nosniff}
              - {name: Referrer-Policy, value: no-referrer}
              - {name: Cache-Control, value: no-store}
      backendRefs:
        - group: ""
          kind: Service
          name: hindsight-grok-memory
          port: 8000
          weight: 1
      timeouts: {request: 65s, backendRequest: 60s}
    {{- end }}
    - matches:
        - path: {type: PathPrefix, value: /grok-memory}
        - path: {type: PathPrefix, value: /.well-known/oauth-authorization-server/grok-memory}
        - path: {type: PathPrefix, value: /.well-known/oauth-protected-resource/grok-memory}
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.envoyproxy.io
            kind: HTTPRouteFilter
            name: hindsight-grok-memory-closed
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  name: hindsight-grok-memory-limits
  namespace: hindsight
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: hindsight-grok-memory
  requestBuffer:
    limit: 64Ki
  rateLimit:
    type: Local
    local:
      rules:
        - limit:
            requests: 60
            unit: Minute
{{- end }}
