{{- include "keycloak.guard" . }}
{{- $production := eq .Values.preparationProfile "keycloak-26.8.2-production" }}
{{- if or (not $production) (eq .Values.productionPhase "application") }}
apiVersion: k8s.keycloak.org/v2beta1
kind: Keycloak
metadata:
  name: keycloak
  namespace: keycloak
{{- if $production }}
  annotations:
    argocd.argoproj.io/sync-wave: '1'
{{- end }}
spec:
{{ toYaml .Values.keycloak | indent 2 }}
---
{{- end }}
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata:
  name: keycloak-db
  namespace: keycloak
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
spec:
{{ toYaml .Values.database | indent 2 }}
