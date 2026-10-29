{{- define "kkamji-hindsight.labels" -}}
app.kubernetes.io/name: {{ .Values.name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "kkamji-hindsight.approvedImage" -}}
{{- $image := required "runtime.image must be an approved digest-pinned image" .Values.runtime.image -}}
{{- $approved := list "ghcr.io/vectorize-io/hindsight:1.1.0@sha256:50311d02b4d5d2b7c5242bd336edf8735df8374eaad496a92f49c83b37d2aa06" "ghcr.io/kkamji98/hindsight-security:1.1.0-20261029@sha256:99f91e62f5e870d91a2e03bb3fce695541dff694dac6dcdb692319f462060074" -}}
{{- if not (has $image $approved) -}}
{{- fail "runtime.image must match an explicitly reviewed image digest" -}}
{{- end -}}
{{- $image -}}
{{- end -}}

{{- define "kkamji-hindsight.validate" -}}
{{- if ne .Values.name .Values.server.fullnameOverride }}
{{- fail "name must match server.fullnameOverride so Control Plane uses the single-writer API Service" }}
{{- end }}
{{- if or .Values.server.api.enabled .Values.server.worker.enabled .Values.server.postgresql.enabled .Values.server.autoscaling.enabled }}
{{- fail "upstream API, worker, PostgreSQL and autoscaling must remain disabled" }}
{{- end }}
{{- if or .Values.server.ingress.enabled .Values.server.gatewayApi.enabled }}
{{- fail "only the owner-protected wrapper routes may be exposed" }}
{{- end }}
{{- if or (empty .Values.runtime.model) (empty .Values.runtime.reasoningEffort) }}
{{- fail "runtime.model and runtime.reasoningEffort must come from the canonical model policy" }}
{{- end }}
{{- range $name, $digest := .Values.model.filesSha256 }}
{{- if not (regexMatch "^[0-9a-f]{64}$" $digest) }}
{{- fail (printf "invalid public model SHA256 for %s" $name) }}
{{- end }}
{{- end }}
{{- end }}
