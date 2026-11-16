{{- $sso := .Values.keycloakSSO.grafana }}
{{- if ne $sso.mode "legacy" }}
{{- if or (ne .Values.gatewayRoutes.grafana.host "grafana.kkamji.net") (ne .Values.gatewayRef.name "kkamji") (ne .Values.gatewayRef.namespace "envoy-gateway-system") (ne .Values.gatewayRef.sectionName "https") }}
{{- fail "Grafana SSO requires its exact hostname and approved HTTPS Gateway" }}
{{- end }}
{{- $target := "grafana" }}
{{- if eq $sso.mode "canary" }}{{- $target = "grafana-keycloak-canary" }}{{- end }}
{{- $remove := include "grafana-keycloak.untrustedHeaders" . | fromJsonArray }}
{{- if eq $sso.mode "canary" }}
# A controlled browser must set this exact non-secret selector on EVERY app request,
# including callbacks, assets, fetches and WebSocket handshakes. No path/host rewrite.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: grafana-keycloak-canary
  namespace: {{ .Release.Namespace }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ .Values.gatewayRef.name }}
      namespace: {{ .Values.gatewayRef.namespace }}
      sectionName: {{ .Values.gatewayRef.sectionName }}
  hostnames: [grafana.kkamji.net]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /}
          headers:
            - name: X-KKamJi-SSO-Canary
              type: Exact
              value: grafana
      filters:
        - type: RequestHeaderModifier
          requestHeaderModifier:
            remove: [X-KKamJi-SSO-Canary]
      backendRefs:
        - group: ""
          kind: Service
          name: {{ .Values.gatewayRoutes.grafana.backend.name }}
          port: {{ .Values.gatewayRoutes.grafana.backend.port }}
          weight: 1
---
{{- end }}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: grafana-machine-api
  namespace: {{ .Release.Namespace }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ .Values.gatewayRef.name }}
      namespace: {{ .Values.gatewayRef.namespace }}
      sectionName: {{ .Values.gatewayRef.sectionName }}
  hostnames: [grafana.kkamji.net]
  rules:
    - matches:
        # Exact supported prefix: clients/api_key.go uses HasPrefix("Bearer ").
        # Do not impose token-format constraints on current or legacy native tokens.
        - path: {type: PathPrefix, value: /api}
          headers:
            - name: Authorization
              type: RegularExpression
              value: '^Bearer .+$'
        - path: {type: PathPrefix, value: /apis}
          headers:
            - name: Authorization
              type: RegularExpression
              value: '^Bearer .+$'
      filters:
        - type: RequestHeaderModifier
          requestHeaderModifier:
            # Explicit Bearer credentials remain authoritative; browser cookies/origin do not.
            remove: {{ concat $remove (list "Cookie" "Origin") | toJson }}
      backendRefs:
        - group: ""
          kind: Service
          name: {{ .Values.gatewayRoutes.grafana.backend.name }}
          port: {{ .Values.gatewayRoutes.grafana.backend.port }}
          weight: 1
{{- if eq $sso.mode "only" }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: grafana-public-basic-deny
  namespace: {{ .Release.Namespace }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ .Values.gatewayRef.name }}
      namespace: {{ .Values.gatewayRef.namespace }}
      sectionName: {{ .Values.gatewayRef.sectionName }}
  hostnames: [grafana.kkamji.net]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /}
          headers:
            - name: Authorization
              type: RegularExpression
              value: '(?i)^basic[ \t]+.*$'
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.envoyproxy.io
            kind: HTTPRouteFilter
            name: grafana-deny-public-basic
{{- end }}
---
# OAuth's parseCookies canonicalizes duplicate names before Lua can observe them.
# This more-specific raw-header route has NO OAuth/JWT/Lua policy, so it rejects
# ambiguity before that normalization. Comma catches combined duplicate headers.
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: grafana-keycloak-cookie-reject
  namespace: {{ .Release.Namespace }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ .Values.gatewayRef.name }}
      namespace: {{ .Values.gatewayRef.namespace }}
      sectionName: {{ .Values.gatewayRef.sectionName }}
  hostnames: [grafana.kkamji.net]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /}
          headers:
            {{- if eq $sso.mode "canary" }}
            - name: X-KKamJi-SSO-Canary
              type: Exact
              value: grafana
            {{- end }}
            - name: Authorization
              type: RegularExpression
              value: '^.+$'
            - name: Cookie
              type: RegularExpression
              value: '^([ \t]*|.*;[ \t]*)GrafanaKeycloakIdToken[ \t]*=[^;]*(;[^;]*)*;[ \t]*GrafanaKeycloakIdToken[ \t]*=.*$|^.*,.*$'
        - path: {type: PathPrefix, value: /}
          headers:
            {{- if eq $sso.mode "canary" }}
            - name: X-KKamJi-SSO-Canary
              type: Exact
              value: grafana
            {{- end }}
            - name: Cookie
              type: RegularExpression
              value: '^([ \t]*|.*;[ \t]*)GrafanaKeycloakIdToken[ \t]*=[^;]*(;[^;]*)*;[ \t]*GrafanaKeycloakIdToken[ \t]*=.*$|^.*,.*$'
      filters:
        - type: ExtensionRef
          extensionRef:
            group: gateway.envoyproxy.io
            kind: HTTPRouteFilter
            name: grafana-keycloak-cookie-reject
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: HTTPRouteFilter
metadata:
  name: grafana-keycloak-cookie-reject
  namespace: {{ .Release.Namespace }}
spec:
  directResponse:
    statusCode: 400
    contentType: text/plain
    body:
      type: Inline
      inline: Ambiguous SSO cookie.
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: Backend
metadata:
  name: grafana-keycloak-provider
  namespace: {{ .Release.Namespace }}
spec:
  endpoints:
    - fqdn:
        hostname: sso.kkamji.net
        port: 443
  tls:
    sni: sso.kkamji.net
    wellKnownCACertificates: System
    insecureSkipVerify: false
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: grafana-keycloak
  namespace: {{ .Release.Namespace }}
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ $target }}
  oidc:
    provider:
      issuer: https://sso.kkamji.net/realms/kkamji
      authorizationEndpoint: https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/auth
      tokenEndpoint: https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/token
      backendRefs:
        - group: gateway.envoyproxy.io
          kind: Backend
          name: grafana-keycloak-provider
          port: 443
          weight: 1
    clientID: grafana
    clientSecret:
      name: grafana-keycloak-oidc
      group: ""
      kind: Secret
    scopes: [openid, groups]
    redirectURL: https://grafana.kkamji.net/oauth2/keycloak-callback
    logoutPath: /oauth2/keycloak-logout
    cookieNames:
      idToken: GrafanaKeycloakIdToken
    cookieConfig:
      sameSite: Lax
    forwardAccessToken: false
    passThroughAuthHeader: false
    disableTokenEncryption: false
    refreshToken: true
  jwt:
    optional: false
    providers:
      # IR Name is p.Name; xDS PayloadInMetadata is irProvider.Name, unchanged.
      - name: grafana-keycloak-owner
        issuer: https://sso.kkamji.net/realms/kkamji
        audiences: [grafana]
        remoteJWKS:
          uri: https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/certs
          cacheDuration: 300s
          backendRefs:
            - group: gateway.envoyproxy.io
              kind: Backend
              name: grafana-keycloak-provider
              port: 443
              weight: 1
        extractFrom:
          cookies: [GrafanaKeycloakIdToken]
  authorization:
    defaultAction: Deny
    rules:
      - name: signed-grafana-admins
        action: Allow
        principal:
          jwt:
            provider: grafana-keycloak-owner
            claims:
              - name: groups
                valueType: StringArray
                values: [/grafana-admins]
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: EnvoyExtensionPolicy
metadata:
  name: grafana-keycloak-bridge
  namespace: {{ .Release.Namespace }}
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ $target }}
  lua:
    - type: Inline
      inline: |
{{ .Files.Get "files/grafana-keycloak.lua" | indent 8 }}
{{- end }}
