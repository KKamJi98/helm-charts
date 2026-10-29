{{- if .Values.exposure.enabled }}
{{- $oidc := .Values.exposure.oidc | default dict }}
{{- if ne ($oidc.clientID | default "") "47443292322-rlsttvfbbvbp3lg5icerudodded0i7ev.apps.googleusercontent.com" }}
{{- fail "exposure requires the approved Google OIDC clientID" }}
{{- end }}
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
      filters:
        - type: ResponseHeaderModifier
          responseHeaderModifier:
            set:
              - name: Strict-Transport-Security
                value: max-age=86400
              - name: X-Content-Type-Options
                value: nosniff
              - name: Referrer-Policy
                value: no-referrer
      timeouts:
        request: 600s
        backendRequest: 600s
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
      filters:
        - type: ResponseHeaderModifier
          responseHeaderModifier:
            set:
              - name: Strict-Transport-Security
                value: max-age=86400
              - name: X-Content-Type-Options
                value: nosniff
              - name: Referrer-Policy
                value: no-referrer
      timeouts:
        request: 600s
        backendRequest: 600s
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
  oidc:
    provider:
      issuer: https://accounts.google.com
    clientID: {{ .Values.exposure.oidc.clientID | quote }}
    clientSecret:
      name: {{ .Values.name }}-google-oidc
      group: ""
      kind: Secret
    scopes: [openid, email]
    redirectURL: {{ printf "https://%s/oauth2/callback" .Values.exposure.hostname | quote }}
    logoutPath: /oauth2/logout
    cookieNames:
      idToken: HindsightGoogleIdToken
    cookieConfig:
      sameSite: Lax
    forwardAccessToken: false
    passThroughAuthHeader: false
    disableTokenEncryption: false
    refreshToken: true
  jwt:
    optional: false
    providers:
      - name: google-owner
        issuer: https://accounts.google.com
        audiences: [{{ .Values.exposure.oidc.clientID | quote }}]
        remoteJWKS:
          uri: https://www.googleapis.com/oauth2/v3/certs
          cacheDuration: 300s
        extractFrom:
          cookies: [HindsightGoogleIdToken]
  authorization:
    defaultAction: Deny
    rules:
      - name: exact-owner-email
        action: Allow
        principal:
          jwt:
            provider: google-owner
            claims:
              - name: email
                valueType: String
                values: [rlaxowl5460@gmail.com]
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
      - name: {{ .Values.name }}-gateway-client-keys
        group: ""
        kind: Secret
    extractFrom:
      - headers: [X-Hindsight-Client-Key]
    sanitize: true
    forwardClientIDHeader: X-Hindsight-Client-ID
{{- end }}
