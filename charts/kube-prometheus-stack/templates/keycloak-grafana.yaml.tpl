{{- $sso := .Values.keycloakSSO.grafana }}
{{- if not (has $sso.mode (list "legacy" "canary" "only")) }}
{{- fail "keycloakSSO.grafana.mode must be legacy, canary or only" }}
{{- end }}
{{- $native := index .Values "kube-prometheus-stack" "grafana" "grafana.ini" | default dict }}
{{- if and (eq $sso.mode "legacy") ((index $native "auth.jwt" | default dict).enabled | default false) }}
{{- fail "legacy rollback must remove the Grafana JWT overlay, not only change its mode" }}
{{- end }}
{{- if ne $sso.mode "legacy" }}
{{- if ne .Release.Namespace "monitoring" }}
{{- fail "Keycloak Grafana must use namespace monitoring" }}
{{- end }}
{{- if not (and (kindIs "bool" .Values.keycloakSSO.backendTLSReady) .Values.keycloakSSO.backendTLSReady) }}
{{- fail "Grafana requires keycloakSSO.backendTLSReady after native Backend/TLS readback" }}
{{- end }}
{{- if not (and (kindIs "bool" $sso.dataPreservationReady) $sso.dataPreservationReady) }}
{{- fail "Grafana canary requires dataPreservationReady after backup/PVC migration; auth changes replace the Pod" }}
{{- end }}
{{- if not (and (kindIs "bool" $sso.accessLogsSafe) $sso.accessLogsSafe) }}
{{- fail "Grafana requires accessLogsSafe after parent verifies shared access logs exclude query/headers/cookies/tokens" }}
{{- end }}
{{- $grafana := index .Values "kube-prometheus-stack" "grafana" }}
{{- $ini := index $grafana "grafana.ini" }}
{{- $jwt := index $ini "auth.jwt" | default dict }}
{{- range $bag := list ($grafana.env | default dict) ($grafana.envValueFrom | default dict) ($grafana.envRenderSecret | default dict) }}
{{- range $key, $_ := $bag }}
{{- if or (hasPrefix "GF_AUTH_" $key) (hasPrefix "GF_SECURITY_CSRF_" $key) (has $key (list "GF_SERVER_ROOT_URL" "GF_SERVER_ROUTER_LOGGING")) }}
{{- fail "Grafana auth/server/CSRF INI must not be shadowed by GF_* environment overrides" }}
{{- end }}
{{- end }}
{{- end }}
{{- if or $grafana.envFromSecrets $grafana.envFromConfigMaps $grafana.envFromSecret $grafana.envFromConfigMap }}
{{- fail "Grafana SSO requires explicit env refs, not bulk environment sources that can shadow auth settings" }}
{{- end }}
{{- if or (ne $jwt.enabled true) (ne $jwt.header_name "X-Grafana-Keycloak-Id-Token") (ne $jwt.jwk_set_url "https://sso.kkamji.net/realms/kkamji/protocol/openid-connect/certs") (ne $jwt.tls_skip_verify_insecure false) }}
{{- fail "Grafana requires native JWT with the exact dedicated header/HTTPS JWKS and strict TLS" }}
{{- end }}
{{- if or (ne $jwt.username_claim "") (ne $jwt.email_claim "") (ne $jwt.email_attribute_path "") (ne $jwt.username_attribute_path "$__env{KEYCLOAK_GRAFANA_USERNAME_ATTRIBUTE_PATH}") (ne $jwt.expect_claims "$__env{KEYCLOAK_GRAFANA_EXPECT_CLAIMS}") }}
{{- fail "Grafana requires cleared username/email claims and private Secret-backed owner predicates" }}
{{- end }}
{{- if or (ne $jwt.auto_sign_up false) (ne $jwt.url_login false) (ne $jwt.skip_org_role_sync true) (ne $jwt.allow_assign_grafana_admin false) (ne $jwt.groups_attribute_path "") (ne $jwt.role_attribute_path "") (ne $jwt.org_attribute_path "") }}
{{- fail "Grafana must preserve the existing user/org/admin/team identity without signup, URL JWT or role sync" }}
{{- end }}
{{- if or (ne (index $ini "server" "root_url") "https://grafana.kkamji.net") (ne (index $ini "server" "router_logging") false) (ne (index $ini "auth" "oauth_allow_insecure_email_lookup") false) (ne (index $ini "auth.anonymous" "enabled") false) (ne (index $ini "auth.proxy" "enabled") false) (ne (index $ini "auth.generic_oauth" "enabled") false) (ne (index $ini "security" "cookie_secure") true) }}
{{- fail "Grafana requires exact HTTPS origin and no anonymous/proxy/Generic OAuth/email fallback or router request logging" }}
{{- end }}
{{- if or (ne (index $ini "security" "csrf_always_check") true) (ne ((index $ini "security" "csrf_trusted_origins") | default "") "") (ne ((index $ini "security" "csrf_additional_headers") | default "") "") }}
{{- fail "Grafana cookie-to-JWT transport requires native CSRF checks without extra trusted origins or headers" }}
{{- end }}
{{- if or (ne (index $ini "auth.basic" "enabled") true) (ne (index $ini "auth" "disable_login") false) }}
{{- fail "Grafana internal Basic is required by unchanged reload sidecars" }}
{{- end }}
{{- range $env, $key := dict "KEYCLOAK_GRAFANA_USERNAME_ATTRIBUTE_PATH" "username_attribute_path" "KEYCLOAK_GRAFANA_EXPECT_CLAIMS" "expect_claims" }}
{{- $ref := index $grafana.envValueFrom $env "secretKeyRef" }}
{{- if or (ne $ref.name "grafana-keycloak-identity") (ne $ref.key $key) ($ref.optional | default false) }}
{{- fail "Grafana owner mapping must use both non-optional dedicated Secret property refs" }}
{{- end }}
{{- end }}
{{- if eq $sso.mode "only" }}
{{- if not (and (kindIs "bool" $sso.cutoverApproved) $sso.cutoverApproved) }}
{{- fail "only requires keycloakSSO.grafana.cutoverApproved after owner/recovery, legacy session revoke and machine-client proof" }}
{{- end }}
{{- if ne (index $ini "auth" "disable_login_form") true }}
{{- fail "only requires disable_login_form=true to unregister native form auth" }}
{{- end }}
{{- else if ne (index $ini "auth" "disable_login_form") false }}
{{- fail "canary must preserve the normal public legacy password path" }}
{{- end }}
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: grafana-keycloak-oidc
  namespace: {{ .Release.Namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: grafana-keycloak-oidc
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
    - secretKey: client-secret
      remoteRef:
        key: /kkamji/keycloak/clients/grafana
        property: client_secret
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: grafana-keycloak-identity
  namespace: {{ .Release.Namespace }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: parameter-store
    kind: ClusterSecretStore
  target:
    name: grafana-keycloak-identity
    creationPolicy: Orphan
    deletionPolicy: Retain
    template:
      type: Opaque
  data:
    - secretKey: username_attribute_path
      remoteRef:
        key: /kkamji/keycloak/consumers/grafana
        property: username_attribute_path
    - secretKey: expect_claims
      remoteRef:
        key: /kkamji/keycloak/consumers/grafana
        property: expect_claims
{{- if eq $sso.mode "only" }}
---
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: HTTPRouteFilter
metadata:
  name: grafana-deny-public-basic
  namespace: {{ .Release.Namespace }}
spec:
  directResponse:
    statusCode: 403
    contentType: text/plain
    body:
      type: Inline
      inline: Public password authentication is disabled. Use Keycloak.
{{- end }}
{{- end }}
