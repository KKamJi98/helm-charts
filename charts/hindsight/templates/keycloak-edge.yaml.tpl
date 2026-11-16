{{- if .Values.exposure.enabled }}
{{- $root := . }}
{{- $entries := list (dict "client" "hindsight-ui" "route" "hindsight-ui" "host" "hindsight.kkamji.net" "cookie" "HindsightKeycloakIdToken" "namespace" "hindsight" "mode" .Values.keycloakSSO.mode "backend" (dict "name" "hindsight-control-plane" "port" .Values.server.controlPlane.service.port) "gateway" .Values.exposure.gateway) }}
{{- range $entry := $entries }}
{{- $mode := $entry.mode }}
{{- if not (has $mode (list "legacy" "canary" "only")) }}
{{- fail "keycloakSSO mode must be legacy, canary or only" }}
{{- end }}
{{- if ne $mode "legacy" }}
{{- if not $root.Values.keycloakSSO.backendTLSReady }}
{{- fail "Keycloak edge requires keycloakSSO.backendTLSReady after shared extensionApis.enableBackend and hostname-validated TLS readback" }}
{{- end }}
{{- if ne $root.Release.Namespace $entry.namespace }}
{{- fail "Keycloak consumer must use its approved namespace" }}
{{- end }}
{{- if or (ne $entry.gateway.name "kkamji") (ne $entry.gateway.namespace "envoy-gateway-system") (ne $entry.gateway.sectionName "https") }}
{{- fail "Keycloak edge requires the approved HTTPS Gateway listener" }}
{{- end }}
{{- if or (ne $root.Values.name "hindsight") (ne $root.Values.exposure.hostname $entry.host) }}
{{- fail "Keycloak Hindsight UI requires its exact approved name/HTTPS hostname" }}
{{- end }}
{{- $route := $entry.route }}
{{- if eq $mode "canary" }}
{{- $route = printf "%s-keycloak-canary" $entry.client }}
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ $route }}
  namespace: {{ $root.Release.Namespace }}
spec:
  parentRefs:
    - group: gateway.networking.k8s.io
      kind: Gateway
      name: {{ $entry.gateway.name }}
      namespace: {{ $entry.gateway.namespace }}
      sectionName: {{ $entry.gateway.sectionName }}
  hostnames: [{{ $entry.host | quote }}]
  rules:
    - matches:
        - path: {type: PathPrefix, value: /sso-canary}
      filters:
        - type: URLRewrite
          urlRewrite:
            path: {type: ReplacePrefixMatch, replacePrefixMatch: /}
        - type: RequestHeaderModifier
          requestHeaderModifier:
            remove: [X-Forwarded-User, X-Forwarded-Email, X-Forwarded-Groups, X-Auth-Request-User, X-Auth-Request-Email, X-Auth-Request-Groups]
      backendRefs:
        - group: ""
          kind: Service
          name: {{ $entry.backend.name }}
          port: {{ $entry.backend.port }}
          weight: 1
    - matches:
        - path: {type: Exact, value: /oauth2/keycloak-callback}
        - path: {type: Exact, value: /oauth2/keycloak-logout}
      backendRefs:
        - group: ""
          kind: Service
          name: {{ $entry.backend.name }}
          port: {{ $entry.backend.port }}
          weight: 1
{{- end }}
---
# Explicit Backend TLS avoids the URL-only helper's CA-only (no SAN) validation.
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: Backend
metadata:
  name: {{ $entry.client }}-keycloak-provider
  namespace: {{ $root.Release.Namespace }}
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
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ $entry.client }}-keycloak-oidc
  namespace: {{ $root.Release.Namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: {{ $entry.client }}-keycloak-oidc
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
    - secretKey: client-secret
      remoteRef:
        key: {{ printf "/kkamji/keycloak/clients/%s" $entry.client | quote }}
        property: client_secret
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: {{ $entry.client }}-keycloak
  namespace: {{ $root.Release.Namespace }}
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ $route }}
  oidc:
    provider:
      issuer: https://sso.kkamji.net/realms/kkamji
      authorizationEndpoint: https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/auth
      tokenEndpoint: https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/token
      backendRefs:
        - group: gateway.envoyproxy.io
          kind: Backend
          name: {{ $entry.client }}-keycloak-provider
          port: 443
          weight: 1
    clientID: {{ $entry.client }}
    clientSecret:
      name: {{ $entry.client }}-keycloak-oidc
      group: ""
      kind: Secret
    scopes: [openid, profile, groups]
    redirectURL: {{ printf "https://%s/oauth2/keycloak-callback" $entry.host | quote }}
    logoutPath: /oauth2/keycloak-logout
    cookieNames:
      idToken: {{ $entry.cookie }}
    cookieConfig:
      sameSite: Lax
    forwardAccessToken: false
    passThroughAuthHeader: false
    disableTokenEncryption: false
    refreshToken: true
  jwt:
    optional: false
    providers:
      - name: keycloak-owner
        issuer: https://sso.kkamji.net/realms/kkamji
        audiences: [{{ $entry.client }}]
        remoteJWKS:
          uri: https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/certs
          cacheDuration: 300s
          backendRefs:
            - group: gateway.envoyproxy.io
              kind: Backend
              name: {{ $entry.client }}-keycloak-provider
              port: 443
              weight: 1
        extractFrom:
          cookies: [{{ $entry.cookie }}]
  authorization:
    defaultAction: Deny
    rules:
      - name: signed-homelab-admins
        action: Allow
        principal:
          jwt:
            provider: keycloak-owner
            claims:
              - name: groups
                valueType: StringArray
                values: [/homelab-admins]
{{- end }}
{{- end }}
{{- end }}
