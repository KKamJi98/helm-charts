{{/*
Expand the name of the chart.
*/}}
{{- define "argo-applications.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "argo-applications.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "argo-applications.labels" -}}
app.kubernetes.io/name: {{ include "argo-applications.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Merge source with defaults.
Usage: {{ include "argo-applications.mergeSource" (dict "defaults" .Values.defaults "app" $app) }}
Supports shorthand: app.path -> app.source.path
*/}}
{{- define "argo-applications.mergeSource" -}}
{{- $defaultSource := default dict .defaults.source -}}
{{- $appSource := default dict .app.source -}}
{{- $merged := deepCopy $defaultSource | merge $appSource -}}
{{- /* 단축 속성 지원: app.path -> source.path */ -}}
{{- if and .app.path (not (index $merged "path")) -}}
{{- $_ := set $merged "path" .app.path -}}
{{- end -}}
{{- toYaml $merged -}}
{{- end -}}

{{/*
Merge destination with defaults.
Usage: {{ include "argo-applications.mergeDestination" (dict "defaults" .Values.defaults "app" $app "appName" $appName) }}
Supports shorthand: app.namespace -> app.destination.namespace
*/}}
{{- define "argo-applications.mergeDestination" -}}
{{- $defaultDest := default dict .defaults.destination -}}
{{- $appDest := default dict .app.destination -}}
{{- $merged := deepCopy $defaultDest | merge $appDest -}}
{{- /* 단축 속성 지원: app.namespace -> destination.namespace */ -}}
{{- if and .app.namespace (not (index $merged "namespace")) -}}
{{- $_ := set $merged "namespace" .app.namespace -}}
{{- end -}}
{{- /* namespace 기본값: app.destination.namespace > app.namespace > defaults.destination.namespace > appName */ -}}
{{- if not (index $merged "namespace") -}}
{{- $_ := set $merged "namespace" .appName -}}
{{- end -}}
{{- toYaml $merged -}}
{{- end -}}

{{/*
Merge syncPolicy with defaults.
Usage: {{ include "argo-applications.mergeSyncPolicy" (dict "defaults" .Values.defaults "app" $app) }}
*/}}
{{- define "argo-applications.mergeSyncPolicy" -}}
{{- $defaultPolicy := .defaults.syncPolicy -}}
{{- if hasKey .app "syncPolicy" -}}
  {{- if kindIs "map" .app.syncPolicy -}}
    {{- $merged := deepCopy $defaultPolicy | merge .app.syncPolicy -}}
    {{- toYaml $merged -}}
  {{- else if eq .app.syncPolicy nil -}}
    {{- /* syncPolicy: null 이면 빈 값 반환 (수동 sync) */ -}}
  {{- else -}}
    {{- toYaml .app.syncPolicy -}}
  {{- end -}}
{{- else -}}
  {{- toYaml $defaultPolicy -}}
{{- end -}}
{{- end -}}

{{/*
Get finalizers.
Usage: {{ include "argo-applications.finalizers" (dict "defaults" .Values.defaults "app" $app) }}
*/}}
{{- define "argo-applications.finalizers" -}}
{{- if hasKey .app "finalizers" -}}
  {{- if .app.finalizers -}}
    {{- toYaml .app.finalizers -}}
  {{- end -}}
{{- else -}}
  {{- toYaml .defaults.finalizers -}}
{{- end -}}
{{- end -}}

{{/*
Check if application is enabled.
Default: true
*/}}
{{- define "argo-applications.isEnabled" -}}
{{- if hasKey . "enabled" -}}
  {{- .enabled -}}
{{- else -}}
  {{- true -}}
{{- end -}}
{{- end -}}
