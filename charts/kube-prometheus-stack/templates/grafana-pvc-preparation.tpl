{{- if not (kindIs "bool" .Values.grafanaPvcPreparation) -}}
{{- fail "Grafana PVC preparation: only boolean grafanaPvcPreparation is supported" -}}
{{- end -}}
{{- $stack := index .Subcharts "kube-prometheus-stack" -}}
{{- if and (not .Values.grafanaPvcPreparation) $stack.Values.grafana.enabled -}}
{{- $grafana := index $stack.Subcharts "grafana" -}}
{{- if $grafana.Values.persistence.enabled -}}
{{- fail "Grafana PVC preparation: native activation requires the retained preparation PVC" -}}
{{- end -}}
{{- end -}}
{{- if .Values.grafanaPvcPreparation -}}
{{- if not (eq (toJson $stack.Values.grafana.enabled) "true") -}}
{{- fail "Grafana PVC preparation: the existing Grafana subchart must remain enabled" -}}
{{- end -}}
{{- $grafana := index $stack.Subcharts "grafana" -}}
{{- if or (ne .Release.Namespace "monitoring") $stack.Values.namespaceOverride $grafana.Values.namespaceOverride $grafana.Values.nameOverride $grafana.Values.fullnameOverride -}}
{{- fail "Grafana PVC preparation: monitoring namespace and native release-derived Grafana identity required" -}}
{{- end -}}
{{- $persistence := dict "type" "pvc" "enabled" false "volumeName" "" "accessModes" (list "ReadWriteOnce") "size" "10Gi" "finalizers" (list "kubernetes.io/pvc-protection") "extraPvcLabels" (dict) "disableWarning" false "persistentVolumeClaimRetentionPolicy" (dict) "inMemory" (dict "enabled" false) "lookupVolumeName" true -}}
{{- $strategy := dict "type" "RollingUpdate" -}}
{{- if $grafana.Values.persistence.enabled -}}
{{- $_ := set $persistence "enabled" true -}}
{{- $_ := set $persistence "existingClaim" "{{ include \"grafana.fullname\" . }}" -}}
{{- $_ := set $persistence "storageClassName" "local-path" -}}
{{- $strategy = dict "type" "Recreate" "rollingUpdate" nil -}}
{{- if ne (toJson $grafana.Values.initChownData.enabled) "false" -}}
{{- fail "Grafana PVC preparation: native activation must disable initChownData; ownership is a separate verified copy gate" -}}
{{- end -}}
{{- end -}}
{{- if or (ne (toJson $grafana.Values.persistence) (toJson $persistence)) (ne (toJson $grafana.Values.useStatefulSet) "false") (ne (toJson $grafana.Values.replicas) "1") (ne (toJson $grafana.Values.autoscaling.enabled) "false") (ne (toJson $grafana.Values.deploymentStrategy) (toJson $strategy)) -}}
{{- fail "Grafana PVC preparation: only pinned emptyDir preparation or fixed native existingClaim/Recreate activation with one Deployment writer is supported" -}}
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
