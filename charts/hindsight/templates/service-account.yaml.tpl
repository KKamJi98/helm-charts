apiVersion: v1
kind: ServiceAccount
metadata:
  name: default
  labels:
    {{- include "kkamji-hindsight.labels" . | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-wave: "-20"
automountServiceAccountToken: false
