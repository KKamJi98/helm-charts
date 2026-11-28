{{- $cfg := .Values.mokaRecallOAuth }}
{{- $svc := $cfg.service }}
{{- if $cfg.canaryEnabled }}
{{- if not (and (eq .Release.Namespace "hindsight") (eq .Values.name "hindsight") (eq .Values.auth.secretStoreName "parameter-store")) }}
{{- fail "Moka OAuth can only run beside the existing Hindsight service" }}
{{- end }}
{{- if $svc.enabled }}
{{- if or (not $cfg.publicEnabled) (ne (toString $cfg.deadlineUnix) "") }}
{{- fail "Moka OAuth service mode requires the public OAuth route and no canary deadline" }}
{{- end }}
{{- if not (regexMatch "^ghcr.io/openai/tunnel-client@sha256:[0-9a-f]{64}$" (toString $svc.tunnelImage)) }}
{{- fail "Moka OAuth service mode requires the pinned tunnel-client image" }}
{{- end }}
{{- if not (regexMatch "^10\\.0\\.1\\.[0-9]{1,3}$" (toString $svc.gatewayAddress)) }}
{{- fail "Moka OAuth service mode requires the private Gateway address" }}
{{- end }}
{{- if not (regexMatch "^tunnel_[0-9a-f]{32}$" (toString $svc.tunnelId)) }}
{{- fail "Moka OAuth service mode requires one OpenAI tunnel ID" }}
{{- end }}
{{- else if or (and $cfg.publicEnabled (not (regexMatch "^[1-9][0-9]{9}$" (toString $cfg.deadlineUnix)))) (and (not $cfg.publicEnabled) (ne (toString $cfg.deadlineUnix) "")) }}
{{- fail "Moka OAuth requires a fixed Unix deadline only for the attended window" }}
{{- end }}
{{- if not (regexMatch "^ghcr.io/kkamji98/hindsight-dot@sha256:[0-9a-f]{64}$" $cfg.image) }}
{{- fail "Moka OAuth requires the pinned FastMCP runtime image" }}
{{- end }}
{{- $name := "hindsight-moka-recall-oauth" }}
{{- $files := .Files.Glob "files/moka_oauth_*.py" }}
{{- $runtimeKey := "/kkamji/automation/hindsight/recall-tunnel/runtime" }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $name }}-source
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
data:
  {{- $files.AsConfig | nindent 2 }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ $name }}
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef: {name: parameter-store, kind: ClusterSecretStore}
  target:
    name: {{ $name }}
    creationPolicy: Orphan
    deletionPolicy: Retain
    template: {type: Opaque}
  data:
    - secretKey: client_id
      remoteRef:
        key: /kkamji/automation/hindsight/recall-tunnel/google-oauth
        property: client_id
    - secretKey: client_secret
      remoteRef:
        key: /kkamji/automation/hindsight/recall-tunnel/google-oauth
        property: client_secret
    - secretKey: owner_sub
      remoteRef:
        key: /kkamji/automation/hindsight/dot
        property: owner_sub
    {{- if $svc.enabled }}
    {{- range $k := list "recall_api_key" "jwt_signing_key" "storage_encryption_key" }}
    - secretKey: {{ $k }}
      remoteRef:
        key: {{ $runtimeKey }}
        property: {{ $k }}
    {{- end }}
    {{- if $svc.retainEnabled }}
    - secretKey: retain_api_key
      remoteRef:
        key: {{ $runtimeKey }}
        property: retain_api_key
    {{- end }}
    {{- end }}
{{- if $svc.enabled }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ $name }}-api-key
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef: {name: parameter-store, kind: ClusterSecretStore}
  target:
    name: {{ $name }}-api-key
    creationPolicy: Orphan
    deletionPolicy: Retain
    template: {type: Opaque}
  data:
    - secretKey: recall_api_key
      remoteRef:
        key: {{ $runtimeKey }}
        property: recall_api_key
    {{- if or $svc.retainEnabled (and .Values.grokMemory.enabled .Values.grokMemory.retainEnabled) }}
    - secretKey: retain_api_key
      remoteRef:
        key: {{ $runtimeKey }}
        property: retain_api_key
    {{- end }}
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ $name }}-tunnel
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  refreshInterval: 1h
  secretStoreRef: {name: parameter-store, kind: ClusterSecretStore}
  target:
    name: {{ $name }}-tunnel
    creationPolicy: Orphan
    deletionPolicy: Retain
    template: {type: Opaque}
  data:
    # Raw dedicated runtime key (not JSON), stored 2026-11-21 without overwrite.
    - secretKey: control_plane_api_key
      remoteRef:
        key: /kkamji/automation/hindsight/recall-tunnel/openai-api-key
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ $name }}-grants
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-options: Prune=false,Delete=false
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: {{ required "storage.storageClass is required" .Values.storage.storageClass | quote }}
  resources:
    requests:
      storage: 64Mi
{{- end }}
---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: {{ $name }}
  namespace: hindsight
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  endpointSelector:
    matchLabels:
      app.kubernetes.io/name: {{ $name }}
  ingress:
    {{- if $cfg.publicEnabled }}
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: envoy-gateway-system
            gateway.envoyproxy.io/owning-gateway-name: kkamji
      toPorts:
        - ports: [{port: "8000", protocol: TCP}]
    {{- if $svc.enabled }}
    - fromEntities: [host]
      toPorts:
        - ports: [{port: "8000", protocol: TCP}, {port: "8080", protocol: TCP}]
    {{- end }}
  egress:
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s-app: kube-dns
      toPorts:
        - ports: [{port: "53", protocol: UDP}, {port: "53", protocol: TCP}]
          rules:
            dns:
              - matchName: oauth2.googleapis.com
              - matchName: www.googleapis.com
              {{- if $svc.enabled }}
              - matchName: api.openai.com
              - matchPattern: "**.cluster.local"
              {{- end }}
    - toFQDNs:
        - matchName: oauth2.googleapis.com
        - matchName: www.googleapis.com
        {{- if $svc.enabled }}
        - matchName: api.openai.com
        {{- end }}
      toPorts:
        - ports: [{port: "443", protocol: TCP}]
    {{- if $svc.enabled }}
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: hindsight
            app.kubernetes.io/name: {{ .Values.name }}
            app.kubernetes.io/instance: {{ .Release.Name }}
            app.kubernetes.io/component: api
      toPorts:
        - ports: [{port: "8888", protocol: TCP}]
    # tunnel-client reads the public OAuth metadata through the Gateway VIP
    # (hostAliases below); Cilium enforces this after the Service translation.
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: envoy-gateway-system
            gateway.envoyproxy.io/owning-gateway-name: kkamji
      toPorts:
        - ports: [{port: "10443", protocol: TCP}]
    {{- end }}
    {{- else }}
    - fromEntities: [host]
      toPorts:
        - ports: [{port: "8000", protocol: TCP}]
  egressDeny:
    - toEntities: [all]
    {{- end }}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $name }}
  namespace: hindsight
spec:
  type: ClusterIP
  selector: {app.kubernetes.io/name: {{ $name }}}
  ports: [{name: oauth, port: 8000, targetPort: oauth, protocol: TCP}]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $name }}
  namespace: hindsight
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector:
    matchLabels: {app.kubernetes.io/name: {{ $name }}}
  template:
    metadata:
      annotations:
        checksum/moka-oauth-source: {{ $files.AsConfig | sha256sum }}
      labels: {app.kubernetes.io/name: {{ $name }}}
    spec:
      automountServiceAccountToken: false
      {{- if $svc.enabled }}
      enableServiceLinks: false
      nodeSelector:
        {{- toYaml .Values.runtime.nodeSelector | nindent 8 }}
      hostAliases:
        - ip: {{ $svc.gatewayAddress | quote }}
          hostnames: [hindsight.kkamji.net]
      {{- end }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: oauth-canary
          image: {{ $cfg.image | quote }}
          imagePullPolicy: IfNotPresent
          command: [python, -I, -B, -c, "import sys; sys.path.insert(0, '/opt/moka-oauth'); from moka_oauth_runner import main; main()"]
          env:
            - name: MOKA_CANARY_MODE
              value: {{ ternary "service" (ternary "attended-window" "private-metadata" $cfg.publicEnabled) $svc.enabled | quote }}
            - name: MOKA_CANARY_DEADLINE_UNIX
              value: {{ $cfg.deadlineUnix | quote }}
            {{- if and $svc.enabled $svc.retainEnabled }}
            - name: MOKA_RETAIN_ENABLED
              value: "true"
            {{- end }}
            - {name: HOME, value: /tmp}
            - {name: TMPDIR, value: /tmp}
          ports: [{name: oauth, containerPort: 8000, protocol: TCP}]
          readinessProbe:
            httpGet: {port: oauth, path: /.well-known/oauth-authorization-server/moka-recall}
            initialDelaySeconds: 1
            periodSeconds: 2
          resources:
            requests: {cpu: 50m, memory: 96Mi}
            limits: {cpu: 250m, memory: 256Mi}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          volumeMounts:
            - {name: source, mountPath: /opt/moka-oauth, readOnly: true}
            - {name: google-oauth, mountPath: /run/moka-oauth, readOnly: true}
            - {name: tmp, mountPath: /tmp}
            {{- if $svc.enabled }}
            - {name: grants, mountPath: /var/lib/moka-oauth}
            {{- end }}
        {{- if $svc.enabled }}
        - name: tunnel-client
          image: {{ $svc.tunnelImage | quote }}
          imagePullPolicy: IfNotPresent
          env:
            - {name: CONTROL_PLANE_TUNNEL_ID, value: {{ $svc.tunnelId | quote }}}
            - {name: CONTROL_PLANE_BASE_URL, value: "https://api.openai.com"}
            - name: CONTROL_PLANE_API_KEY
              valueFrom:
                secretKeyRef: {name: {{ $name }}-tunnel, key: control_plane_api_key}
            - {name: MCP_SERVER_URL, value: "http://127.0.0.1:8001/mcp"}
            - {name: MCP_OAUTH_TRUSTED_ORIGINS, value: "https://hindsight.kkamji.net"}
            # ChatGPT fetches OAuth discovery through the tunnel's Harpoon channel:
            # register the loopback PRM source and the public OAuth origin only.
            - {name: HARPOON_ALLOW_PLAINTEXT_HTTP, value: "true"}
            - {name: HARPOON_OAUTH_FORWARD_ORIGINS, value: "https://hindsight.kkamji.net"}
            - {name: MCP_STARTUP_WAIT_TIMEOUT, value: 60s}
            - {name: HEALTH_LISTEN_ADDR, value: ":8080"}
            - {name: LOG_FORMAT, value: json}
            - {name: LOG_LEVEL, value: info}
            - {name: HOME, value: /tmp}
            - {name: XDG_CONFIG_HOME, value: /tmp/config}
          ports: [{name: tunnel-health, containerPort: 8080, protocol: TCP}]
          livenessProbe:
            httpGet: {port: tunnel-health, path: /healthz}
            initialDelaySeconds: 5
            periodSeconds: 10
          # No readinessProbe: Pod readiness gates the public OAuth Service, and
          # tunnel-client /readyz depends on that OAuth metadata and on OpenAI.
          resources:
            requests: {cpu: 20m, memory: 32Mi}
            limits: {cpu: 250m, memory: 128Mi}
          securityContext:
            runAsNonRoot: true
            runAsUser: 10002
            runAsGroup: 10002
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          volumeMounts:
            - {name: tunnel-tmp, mountPath: /tmp}
        {{- end }}
      volumes:
        - name: source
          configMap: {name: {{ $name }}-source}
        - name: google-oauth
          secret:
            secretName: {{ $name }}
            defaultMode: 288
        - name: tmp
          emptyDir: {medium: Memory, sizeLimit: 16Mi}
        {{- if $svc.enabled }}
        - name: grants
          persistentVolumeClaim: {claimName: {{ $name }}-grants}
        - name: tunnel-tmp
          emptyDir: {medium: Memory, sizeLimit: 16Mi}
        {{- end }}
{{- end }}
