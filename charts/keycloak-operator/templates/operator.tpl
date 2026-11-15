{{- include "keycloak-operator.guard" . -}}
{{- $root := . -}}
{{- range $part := splitList "\n---\n" (.Files.Get "vendor/kubernetes/kubernetes.yml") -}}
{{- $object := fromYaml $part -}}
{{- if $object.kind -}}
{{- if has $object.kind (list "ServiceAccount" "RoleBinding" "Service" "Deployment") -}}
{{- $_ := set $object.metadata "namespace" $root.Release.Namespace -}}
{{- end -}}
{{- if has $object.kind (list "RoleBinding" "ClusterRoleBinding") -}}
{{- range $subject := $object.subjects -}}
{{- if eq $subject.kind "ServiceAccount" -}}
{{- $_ := set $subject "namespace" $root.Release.Namespace -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- if eq $object.kind "Deployment" -}}
{{- range $container := $object.spec.template.spec.containers -}}
{{- $_ := set $container "image" $root.Values.images.operator -}}
{{- range $env := $container.env -}}
{{- if has $env.name (list "kc.operator.keycloak.image" "RELATED_IMAGE_KEYCLOAK") -}}
{{- $_ := set $env "value" $root.Values.images.keycloak -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end }}
---
{{ toYaml $object }}
{{ end -}}
{{- end -}}
