{{- $cfg := .Values.grokMemory -}}
{{- if $cfg.enabled }}
{{- if not (and (eq .Release.Namespace "hindsight") (eq .Values.name "hindsight") (eq .Values.auth.secretStoreName "parameter-store")) }}
{{- fail "Grok Memory can only run beside the existing Hindsight service" }}
{{- end }}
{{- $authMode := ($cfg.authMode | default "oauth") -}}
{{- if not (or (eq $authMode "oauth") (eq $authMode "bearer")) }}
{{- fail "Grok Memory authMode must be oauth or bearer" }}
{{- end }}
{{- if not (regexMatch "^ghcr.io/kkamji98/hindsight-dot@sha256:[0-9a-f]{64}$" (toString $cfg.image)) }}
{{- fail "Grok Memory requires the pinned FastMCP runtime image" }}
{{- end }}
{{- $uris := $cfg.allowedRedirectUris | default list -}}
{{- if eq $authMode "oauth" }}
{{- if or (eq (len $uris) 0) (gt (len $uris) 4) }}
{{- fail "Grok Memory oauth mode requires 1..4 HTTPS allowedRedirectUris" }}
{{- end }}
{{- range $u := $uris }}
{{- if not (regexMatch "^https://[^\\s@#]+$" (toString $u)) }}
{{- fail "Grok Memory allowedRedirectUris entries must be canonical HTTPS URIs" }}
{{- end }}
{{- end }}
{{- end }}
{{- $name := "hindsight-grok-memory" }}
{{- $files := .Files.Glob "files/moka_oauth_*.py" }}
{{- $sharedRuntimeKey := "/kkamji/automation/hindsight/recall-tunnel/runtime" }}
{{- $grokRuntimeKey := "/kkamji/automation/hindsight/grok-memory/runtime" }}
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
    - secretKey: recall_api_key
      remoteRef:
        key: {{ $sharedRuntimeKey }}
        property: recall_api_key
    {{- if $cfg.retainEnabled }}
    - secretKey: retain_api_key
      remoteRef:
        key: {{ $sharedRuntimeKey }}
        property: retain_api_key
    {{- end }}
    {{- if eq $authMode "oauth" }}
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
    {{- range $k := list "jwt_signing_key" "storage_encryption_key" }}
    - secretKey: {{ $k }}
      remoteRef:
        key: {{ $grokRuntimeKey }}
        property: {{ $k }}
    {{- end }}
    {{- else }}
    - secretKey: mcp_bearer_token
      remoteRef:
        key: {{ $grokRuntimeKey }}
        property: mcp_bearer_token
    {{- end }}
{{- if eq $authMode "oauth" }}
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
    {{- end }}
    - fromEntities: [host]
      toPorts:
        - ports: [{port: "8000", protocol: TCP}]
  egress:
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s-app: kube-dns
      toPorts:
        - ports: [{port: "53", protocol: UDP}, {port: "53", protocol: TCP}]
          rules:
            dns:
              - matchPattern: "**.cluster.local"
              {{- if eq $authMode "oauth" }}
              - matchName: oauth2.googleapis.com
              - matchName: www.googleapis.com
              {{- end }}
    {{- if eq $authMode "oauth" }}
    - toFQDNs:
        - matchName: oauth2.googleapis.com
        - matchName: www.googleapis.com
      toPorts:
        - ports: [{port: "443", protocol: TCP}]
    {{- end }}
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: hindsight
            app.kubernetes.io/name: {{ .Values.name }}
            app.kubernetes.io/instance: {{ .Release.Name }}
            app.kubernetes.io/component: api
      toPorts:
        - ports: [{port: "8888", protocol: TCP}]
---
apiVersion: v1
kind: Service
metadata:
  name: {{ $name }}
  namespace: hindsight
spec:
  type: ClusterIP
  selector: {app.kubernetes.io/name: {{ $name }}}
  ports: [{name: mcp, port: 8000, targetPort: mcp, protocol: TCP}]
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
        checksum/grok-memory-source: {{ $files.AsConfig | sha256sum }}
      labels: {app.kubernetes.io/name: {{ $name }}}
    spec:
      automountServiceAccountToken: false
      enableServiceLinks: false
      nodeSelector:
        {{- toYaml .Values.runtime.nodeSelector | nindent 8 }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile: {type: RuntimeDefault}
      containers:
        - name: grok-memory
          image: {{ $cfg.image | quote }}
          imagePullPolicy: IfNotPresent
          command: [python, -I, -B, -c, "import sys; sys.path.insert(0, '/opt/grok-memory'); from moka_oauth_runner import main; main()"]
          env:
            - name: MOKA_CANARY_MODE
              value: grok-service
            - name: GROK_AUTH_MODE
              value: {{ $authMode | quote }}
            - name: GROK_RETAIN_ENABLED
              value: {{ ternary "true" "false" $cfg.retainEnabled | quote }}
            {{- if eq $authMode "oauth" }}
            - name: GROK_ALLOWED_REDIRECT_URIS
              value: {{ $uris | toJson | quote }}
            {{- end }}
            - {name: HOME, value: /tmp}
            - {name: TMPDIR, value: /tmp}
          ports: [{name: mcp, containerPort: 8000, protocol: TCP}]
          readinessProbe:
            {{- if eq $authMode "oauth" }}
            httpGet: {port: mcp, path: /.well-known/oauth-authorization-server/grok-memory}
            {{- else }}
            tcpSocket: {port: mcp}
            {{- end }}
            initialDelaySeconds: 1
            periodSeconds: 5
          resources:
            requests: {cpu: 50m, memory: 96Mi}
            limits: {cpu: 250m, memory: 256Mi}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities: {drop: [ALL]}
          volumeMounts:
            - {name: source, mountPath: /opt/grok-memory, readOnly: true}
            - {name: secrets, mountPath: /run/grok-memory, readOnly: true}
            - {name: tmp, mountPath: /tmp}
            {{- if eq $authMode "oauth" }}
            - {name: grants, mountPath: /var/lib/grok-memory}
            {{- end }}
      volumes:
        - name: source
          configMap: {name: {{ $name }}-source}
        - name: secrets
          secret:
            secretName: {{ $name }}
            defaultMode: 288
        - name: tmp
          emptyDir: {medium: Memory, sizeLimit: 16Mi}
        {{- if eq $authMode "oauth" }}
        - name: grants
          persistentVolumeClaim: {claimName: {{ $name }}-grants}
        {{- end }}
{{- end }}
