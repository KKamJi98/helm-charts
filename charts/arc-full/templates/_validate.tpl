{{- define "arc-full.validate" -}}
{{- if and .Values.githubAuth.enabled (not .Values.githubAuth.existingSourceReuseApproved) -}}
{{- fail "ARC full auth blocked: confirm reuse of the existing owner-approved source; never input or inspect values" -}}
{{- end -}}
{{- if ne .Values.controller.flags.watchSingleNamespace "ci-full" -}}
{{- fail "ARC full boundary: controller must watch only ci-full" -}}
{{- end -}}
{{- range $name := list "platform" "bql" -}}
{{- $p := (index $.Values $name).template.spec -}}
{{- if or (ne $p.hostUsers false) $p.hostPID $p.hostNetwork $p.hostIPC $p.shareProcessNamespace $p.automountServiceAccountToken -}}
{{- fail "ARC full boundary: private user/PID/network/IPC namespaces and no API token are required" -}}
{{- end -}}
{{- $memory := "3584Mi" -}}
{{- $memoryMiB := "3584" -}}
{{- if eq $name "bql" -}}
{{- $memory = "7Gi" -}}
{{- $memoryMiB = "7168" -}}
{{- end -}}
{{- if or (ne $p.resources.requests.memory $memory) (ne $p.resources.limits.memory $memory) -}}
{{- fail "ARC full boundary: Pod memory budget must match the pool slot (Platform3584Mi, BQL7Gi)" -}}
{{- end -}}
{{- if or (ne (len $p.containers) 1) (ne (len $p.initContainers) 2) -}}
{{- fail "ARC full boundary: only the seed, trusted daemon and SDK roles are allowed" -}}
{{- end -}}
{{- $sdk := index $p.containers 0 -}}
{{- $daemon := index $p.initContainers 1 -}}
{{- $s := $sdk.securityContext -}}
{{- $t := $daemon.securityContext -}}
{{- $dockerLimit := "12Gi" -}}
{{- $scratchLimit := "512Mi" -}}
{{- if eq $name "bql" -}}
{{- $dockerLimit = "30Gi" -}}
{{- $scratchLimit = "3Gi" -}}
{{- end -}}
{{- if or (ne (dig "resources" "limits" "ephemeral-storage" "" (default (dict) $daemon)) $dockerLimit) (ne (dig "resources" "limits" "ephemeral-storage" "" (default (dict) $sdk)) "4Gi") -}}
{{- fail "ARC full boundary: pool Docker budget plus SDK4Gi must match the startup disk guard" -}}
{{- end -}}
{{- $budgetEnv := list -}}
{{- range $env := $sdk.env -}}
{{- if eq $env.name "ARC_JOB_EPHEMERAL_GIB" -}}
{{- $budgetEnv = append $budgetEnv $env -}}
{{- end -}}
{{- end -}}
{{- $memoryEnv := list -}}
{{- range $env := $sdk.env -}}
{{- if eq $env.name "ARC_POD_MEMORY_MIB" -}}
{{- $memoryEnv = append $memoryEnv $env -}}
{{- end -}}
{{- end -}}
{{- if or (ne (len $memoryEnv) 1) (hasKey (index $memoryEnv 0) "valueFrom") (ne (toString (index $memoryEnv 0).value) $memoryMiB) -}}
{{- fail "ARC full boundary: the memory start guard must use the pool Pod budget" -}}
{{- end -}}
{{- if eq $name "bql" -}}
{{- if ne (len $budgetEnv) 1 -}}
{{- fail "ARC full boundary: BQL must declare one34Gi startup budget" -}}
{{- end -}}
{{- $budget := index $budgetEnv 0 -}}
{{- if or (hasKey $budget "valueFrom") (not (kindIs "string" $budget.value)) (ne (toString $budget.value) "34") -}}
{{- fail "ARC full boundary: BQL startup budget must remain34Gi" -}}
{{- end -}}
{{- else if ne (len $budgetEnv) 0 -}}
{{- fail "ARC full boundary: Platform must retain its original16Gi startup budget" -}}
{{- end -}}
{{- if or (ne $sdk.name "runner") (ne $s.procMount "Default") $s.allowPrivilegeEscalation $s.privileged (not $s.readOnlyRootFilesystem) (ne (len (default (list) $s.capabilities.add)) 0) (ne (join "," $s.capabilities.drop) "ALL") -}}
{{- fail "ARC full boundary: SDK must keep Default/NNP1/cap0/read-only" -}}
{{- end -}}
{{- if or (ne $daemon.name "dind") (ne $daemon.restartPolicy "Always") (ne $t.procMount "Unmasked") (not $t.allowPrivilegeEscalation) $t.privileged (not $t.readOnlyRootFilesystem) (ne (join "," (sortAlpha $t.capabilities.add)) "SETFCAP,SETGID,SETUID") -}}
{{- fail "ARC full boundary: only trusted native sidecar may use approved Unmasked/three capabilities" -}}
{{- end -}}
{{- if or (ne (int $s.runAsUser) 1001) (ne (int $t.runAsUser) 1001) (ne $s.seccompProfile.type "RuntimeDefault") (ne $t.seccompProfile.type "Localhost") (ne $t.seccompProfile.localhostProfile "arc-docker-runtime-v2.json") -}}
{{- fail "ARC full boundary: approved UID and role-specific seccomp profiles are required" -}}
{{- end -}}
{{- range $volume := $p.volumes -}}
{{- if not $volume -}}
{{- fail "ARC full boundary: empty volume entries are not allowed" -}}
{{- end -}}
{{- if and (eq $volume.name "docker-data") (ne $volume.emptyDir.sizeLimit $dockerLimit) -}}
{{- fail "ARC full boundary: private Docker data must match the pool limit" -}}
{{- end -}}
{{- if and (eq $volume.name "daemon-tmp") (or (ne $volume.emptyDir.sizeLimit $scratchLimit) (ne (default "" $volume.emptyDir.medium) "")) -}}
{{- fail "ARC full boundary: private scratch must match the pool disk limit, never memory" -}}
{{- end -}}
{{- if not (or (hasKey $volume "emptyDir") (hasKey $volume "configMap")) -}}
{{- fail "ARC full boundary: no host/PVC/Secret volume is allowed in SDK Pods" -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
