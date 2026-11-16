{{- $sso := .Values.keycloakSSO }}
{{- if not (has $sso.mode (list "legacy" "canary" "only")) }}
{{- fail "keycloakSSO mode must be legacy, canary or only" }}
{{- end }}
{{- if ne $sso.mode "legacy" }}
{{- if ne .Release.Namespace "argocd" }}
{{- fail "Keycloak Argo CD is pinned to namespace argocd" }}
{{- end }}
{{- $cm := .Values.argocd.configs.cm }}
{{- $oidc := fromYaml (index $cm "oidc.config" | default "") }}
{{- if or (ne $oidc.issuer "https://sso.kkamji.net/realms/kkamji") (ne $oidc.clientID "argocd") (ne $oidc.clientSecret "$argocd-keycloak-oidc:client-secret") (ne $oidc.enablePKCEAuthentication true) }}
{{- fail "Keycloak Argo CD requires the native canary overlay with exact issuer/client/Secret and PKCE" }}
{{- end }}
{{- if or (ne (index $cm "url") "https://argocd.kkamji.net") (ne (toString (index $cm "oidc.tls.insecure.skip.verify")) "false") (ne (toString (index $cm "users.anonymous.enabled")) "false") }}
{{- fail "Keycloak Argo CD requires exact HTTPS origin, strict TLS and no anonymous access" }}
{{- end }}
{{- $rbac := .Values.argocd.configs.rbac }}
{{- if or (ne (index $rbac "policy.default") "role:no-access") (ne (trim (index $rbac "policy.csv")) "g, /argocd-admins, role:admin") (ne $rbac.scopes "[groups]") }}
{{- fail "Keycloak Argo CD requires group-only default-deny RBAC" }}
{{- end }}
{{- if eq $sso.mode "only" }}
{{- if not $sso.adminTokenMigrationConfirmed }}
{{- fail "only requires keycloakSSO.adminTokenMigrationConfirmed after owner/recovery and machine-token audit" }}
{{- end }}
{{- if ne (toString (index $cm "admin.enabled")) "false" }}
{{- fail "only requires admin.enabled=false" }}
{{- end }}
{{- range $key, $value := $cm }}
{{- if and (hasPrefix "accounts." $key) (contains "login" (toString $value)) }}
{{- fail "only must remove local login capability; preserve apiKey-only machine accounts" }}
{{- end }}
{{- end }}
{{- else if ne (toString (index $cm "admin.enabled")) "true" }}
{{- fail "canary must retain admin recovery login" }}
{{- end }}
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: argocd-keycloak-oidc
  namespace: {{ .Release.Namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: argocd-keycloak-oidc
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
      metadata:
        labels:
          app.kubernetes.io/part-of: argocd
  data:
    - secretKey: client-secret
      remoteRef:
        key: /kkamji/keycloak/clients/argocd
        property: client_secret
{{- end }}
