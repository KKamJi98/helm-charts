{{/*
Expand the name of the chart.
*/}}
{{- define "openclaw.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "openclaw.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "openclaw.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "openclaw.labels" -}}
helm.sh/chart: {{ include "openclaw.chart" . }}
{{ include "openclaw.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "openclaw.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openclaw.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "openclaw.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "openclaw.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Return the configured OpenClaw data directory.
*/}}
{{- define "openclaw.dataDir" -}}
{{- default "/home/node/.openclaw" .Values.dataDir -}}
{{- end }}

{{/*
Resolve the default agent id. Require explicit selection when multiple agents exist.
*/}}
{{- define "openclaw.defaultAgentId" -}}
{{- $agents := .Values.agents | default dict -}}
{{- $agentIds := keys $agents | sortAlpha -}}
{{- $configured := .Values.defaultAgentId | default "" -}}
{{- if $configured -}}
  {{- if not (hasKey $agents $configured) -}}
    {{- fail (printf "defaultAgentId %q is not defined in values.agents" $configured) -}}
  {{- end -}}
  {{- $configured -}}
{{- else if gt (len $agentIds) 1 -}}
  {{- fail "defaultAgentId is required when more than one agent is defined" -}}
{{- else if eq (len $agentIds) 1 -}}
  {{- index $agentIds 0 -}}
{{- end -}}
{{- end }}

{{/*
Resolve the gateway auth secret name when shared-secret auth is enabled.
*/}}
{{- define "openclaw.gatewayAuthSecretName" -}}
{{- $mode := .Values.gateway.auth.mode | default "token" -}}
{{- if or (eq $mode "token") (eq $mode "password") -}}
  {{- if .Values.gateway.auth.existingSecretName -}}
    {{- .Values.gateway.auth.existingSecretName -}}
  {{- else if .Values.gateway.auth.generateSecret -}}
    {{- printf "%s-gateway-auth" (include "openclaw.fullname" .) -}}
  {{- else -}}
    {{- fail (printf "gateway.auth.mode=%q requires gateway.auth.existingSecretName or gateway.auth.generateSecret=true" $mode) -}}
  {{- end -}}
{{- end -}}
{{- end }}

{{/*
Resolve the gateway auth secret key.
*/}}
{{- define "openclaw.gatewayAuthSecretKey" -}}
{{- if .Values.gateway.auth.existingSecretKey -}}
{{- .Values.gateway.auth.existingSecretKey -}}
{{- else if eq (.Values.gateway.auth.mode | default "token") "password" -}}
password
{{- else -}}
token
{{- end -}}
{{- end }}
