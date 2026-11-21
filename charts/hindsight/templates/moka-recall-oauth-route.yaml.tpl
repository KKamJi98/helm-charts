{{- $public := .Values.mokaRecallOAuth.publicEnabled }}
{{- $canonical := (and .Values.exposure.enabled (eq .Release.Namespace "hindsight") (eq .Values.exposure.hostname "hindsight.kkamji.net") (eq .Values.exposure.gateway.name "kkamji") (eq .Values.exposure.gateway.namespace "envoy-gateway-system") (eq .Values.exposure.gateway.sectionName "https")) }}
{{- if and $public (not .Values.mokaRecallOAuth.canaryEnabled) }}
{{- fail "Moka OAuth public route requires the synthetic canary workload" }}
{{- end }}
{{- if and $public (not $canonical) }}
{{- fail "Moka OAuth requires the existing Hindsight HTTPS listener and namespace" }}
{{- end }}
{{- if $canonical }}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: HTTPRouteFilter
metadata:
  name: hindsight-moka-recall-closed
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
  name: hindsight-moka-recall-oauth
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
        - path: {type: Exact, value: /.well-known/oauth-authorization-server/moka-recall}
        - path: {type: Exact, value: /.well-known/oauth-protected-resource/moka-recall/mcp}
        - path: {type: Exact, value: /moka-recall/authorize}
        - path: {type: Exact, value: /moka-recall/token}
        - path: {type: Exact, value: /moka-recall/register}
        - path: {type: Exact, value: /moka-recall/consent}
        - path: {type: Exact, value: /moka-recall/google/callback}
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
          name: hindsight-moka-recall-oauth
          port: 8000
          weight: 1
      timeouts: {request: 20s, backendRequest: 18s}
    {{- end }}
    - matches:
        - path: {type: PathPrefix, value: /moka-recall}
        - path: {type: PathPrefix, value: /.well-known/oauth-authorization-server/moka-recall}
        - path: {type: PathPrefix, value: /.well-known/oauth-protected-resource/moka-recall}
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.envoyproxy.io
            kind: HTTPRouteFilter
            name: hindsight-moka-recall-closed
{{- end }}
