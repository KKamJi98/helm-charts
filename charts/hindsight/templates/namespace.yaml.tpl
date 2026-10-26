apiVersion: v1
kind: Namespace
metadata:
  name: {{ .Release.Namespace }}
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
  annotations:
    argocd.argoproj.io/sync-wave: "-30"
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
