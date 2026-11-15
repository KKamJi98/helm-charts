{{- define "keycloak-operator.guard" -}}
{{- if or (ne .Release.Namespace "keycloak") (ne .Release.Name "keycloak-operator") -}}
{{- fail "Keycloak preparation blocked: exact namespace/release identity required" -}}
{{- end -}}
{{- $expected := .Files.Get "files/preparation-profile.yaml" | fromYaml -}}
{{- if ne (toJson .Values) (toJson $expected) -}}
{{- fail "Keycloak preparation blocked: immutable supported-field profile mismatch" -}}
{{- end -}}
{{- end -}}
