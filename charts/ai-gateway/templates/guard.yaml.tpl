{{- if eq .Release.Namespace "default" }}{{ fail "use the approved dedicated namespace" }}{{ end -}}
{{- if ne (int .Values.proxy.replicaCount) 1 }}{{ fail "auth requires exactly one proxy replica" }}{{ end -}}
{{- if ne (int .Values.proxy.numWorkers) 1 }}{{ fail "auth requires exactly one worker" }}{{ end -}}
{{- if ne .Values.proxy.strategy.type "Recreate" }}{{ fail "auth requires Recreate" }}{{ end -}}
{{- if or .Values.proxy.autoscaling.enabled .Values.proxy.keda.enabled }}{{ fail "auth autoscaling is forbidden" }}{{ end -}}
{{- if or .Values.proxy.db.deployStandalone .Values.proxy.db.useExisting .Values.proxy.redis.enabled }}{{ fail "this gateway is database-free" }}{{ end -}}
{{- if or .Values.proxy.ingress.enabled (ne .Values.proxy.service.type "ClusterIP") }}{{ fail "public exposure needs a separate reviewed change" }}{{ end -}}
{{- if ne .Values.proxy.masterkeySecretName .Values.serviceSecret }}{{ fail "master key reference must match serviceSecret" }}{{ end -}}
{{- if not .Values.proxy.securityContext.readOnlyRootFilesystem }}{{ fail "read-only root is required" }}{{ end -}}
{{- if ne .Values.proxy.podSecurityContext.fsGroupChangePolicy "OnRootMismatch" }}{{ fail "preserve private auth permissions across restarts" }}{{ end -}}
{{- if not (regexMatch "@sha256:[a-f0-9]{64}$" .Values.proxy.image.tag) }}{{ fail "pin the official image digest" }}{{ end -}}
{{- if .Values.proxy.proxy_config.general_settings.allow_client_side_credentials }}{{ fail "client credential override is forbidden" }}{{ end -}}
{{- if ne (len .Values.proxy.proxy_config.model_list) 1 }}{{ fail "configure one explicit provider route" }}{{ end -}}
{{- $model := (first .Values.proxy.proxy_config.model_list).litellm_params.model }}
{{- if or (eq $model "chatgpt/OPERATOR_MODEL_REQUIRED") (not (hasPrefix "chatgpt/" $model)) }}{{ fail "pass the reviewed local subscription values explicitly" }}{{ end -}}
{{- if or .Values.proxy.proxy_config.router_settings.fallbacks .Values.proxy.proxy_config.litellm_settings.fallbacks }}{{ fail "automatic model fallback is forbidden" }}{{ end -}}
