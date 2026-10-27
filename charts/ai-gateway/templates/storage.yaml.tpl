apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ai-gateway-auth
  annotations:
    helm.sh/resource-policy: keep
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: {{ .Values.storageClass | quote }}
  resources:
    requests:
      storage: 1Gi
