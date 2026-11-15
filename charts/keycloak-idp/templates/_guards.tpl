{{- define "keycloak.guard" -}}
{{- if or (ne .Release.Namespace "keycloak") (ne .Release.Name "keycloak") -}}
{{- fail "Keycloak preparation blocked: exact namespace/release identity required" -}}
{{- end -}}
{{- $expected := .Files.Get "files/preparation-profile.yaml" | fromYaml -}}
{{- $projection := deepCopy $expected -}}
{{- $_ := set $projection "publicCaProjection" (dict "enabled" true) -}}
{{- $production := mergeOverwrite (deepCopy $expected) (.Files.Get "files/production-profile.yaml" | fromYaml) -}}
{{- $application := deepCopy $production -}}
{{- $_ := set $application "productionPhase" "application" -}}
{{- if and (ne (toJson .Values) (toJson $expected)) (ne (toJson .Values) (toJson $projection)) (ne (toJson .Values) (toJson $production)) (ne (toJson .Values) (toJson $application)) -}}
{{- fail "Keycloak preparation blocked: immutable supported-field profile mismatch" -}}
{{- end -}}
{{- end -}}
