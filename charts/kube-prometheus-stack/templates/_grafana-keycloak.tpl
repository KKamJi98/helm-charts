{{/* Shared Grafana-only sanitation names; never identity inputs. */}}
{{- define "grafana-keycloak.untrustedHeaders" -}}
{{- list "X-Grafana-Keycloak-Id-Token" "X-Grafana-Keycloak-Subject" "X-Grafana-Existing-Login" "X-Grafana-User" "X-Grafana-Role" "X-WEBAUTH-USER" "X-Forwarded-User" "X-Forwarded-Email" "X-Forwarded-Groups" "X-Auth-Request-User" "X-Auth-Request-Email" "X-Auth-Request-Groups" "X-JWT-Assertion" "X-KKamJi-SSO-Canary" | toJson -}}
{{- end -}}
