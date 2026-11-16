{{- if not (kindIs "bool" .Values.grafanaPvcPreparation) -}}
{{- fail "Grafana PVC preparation: only boolean grafanaPvcPreparation is supported" -}}
{{- end -}}
{{- if .Values.grafanaPvcPreparation -}}
{{- $stack := index .Subcharts "kube-prometheus-stack" -}}
{{- if not (eq (toJson $stack.Values.grafana.enabled) "true") -}}
{{- fail "Grafana PVC preparation: the existing Grafana subchart must remain enabled" -}}
{{- end -}}
{{- $grafana := index $stack.Subcharts "grafana" -}}
{{- if or (ne .Release.Namespace "monitoring") $stack.Values.namespaceOverride $grafana.Values.namespaceOverride $grafana.Values.nameOverride $grafana.Values.fullnameOverride -}}
{{- fail "Grafana PVC preparation: monitoring namespace and native release-derived Grafana identity required" -}}
{{- end -}}
{{- $persistence := dict "type" "pvc" "enabled" false "volumeName" "" "accessModes" (list "ReadWriteOnce") "size" "10Gi" "finalizers" (list "kubernetes.io/pvc-protection") "extraPvcLabels" (dict) "disableWarning" false "persistentVolumeClaimRetentionPolicy" (dict) "inMemory" (dict "enabled" false) "lookupVolumeName" true -}}
{{- if or (ne (toJson $grafana.Values.persistence) (toJson $persistence)) (ne (toJson $grafana.Values.useStatefulSet) "false") -}}
{{- fail "Grafana PVC preparation: pinned persistence defaults and Deployment/emptyDir must remain unchanged" -}}
{{- end -}}
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ include "grafana.fullname" $grafana }}
  namespace: {{ include "grafana.namespace" $grafana }}
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: {{ $grafana.Values.persistence.size | quote }}
{{- end -}}
