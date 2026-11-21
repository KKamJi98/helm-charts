{{- $cfg := .Values.mokaRecallOAuth }}
{{- if $cfg.canaryEnabled }}
{{- if not (and (eq .Release.Namespace "hindsight") (eq .Values.name "hindsight") (eq .Values.auth.secretStoreName "parameter-store")) }}
{{- fail "Moka OAuth can only run beside the existing Hindsight service" }}
{{- end }}
{{- if or (and $cfg.publicEnabled (not (regexMatch "^[1-9][0-9]{9}$" (toString $cfg.deadlineUnix)))) (and (not $cfg.publicEnabled) (ne (toString $cfg.deadlineUnix) "")) }}
{{- fail "Moka OAuth requires a fixed Unix deadline only for the attended window" }}
{{- end }}
{{- if not (regexMatch "^ghcr.io/kkamji98/hindsight-dot@sha256:[0-9a-f]{64}$" $cfg.image) }}
{{- fail "Moka OAuth requires the pinned FastMCP runtime image" }}
{{- end }}
{{- $name := "hindsight-moka-recall-oauth" }}
{{- $files := .Files.Glob "files/moka_oauth_*.py" }}
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
  egress:
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s-app: kube-dns
      toPorts:
        - ports: [{port: "53", protocol: UDP}, {port: "53", protocol: TCP}]
          rules:
            dns: [{matchName: oauth2.googleapis.com}, {matchName: www.googleapis.com}]
    - toFQDNs: [{matchName: oauth2.googleapis.com}, {matchName: www.googleapis.com}]
      toPorts:
        - ports: [{port: "443", protocol: TCP}]
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
              value: {{ ternary "attended-window" "private-metadata" $cfg.publicEnabled | quote }}
            - name: MOKA_CANARY_DEADLINE_UNIX
              value: {{ $cfg.deadlineUnix | quote }}
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
      volumes:
        - name: source
          configMap: {name: {{ $name }}-source}
        - name: google-oauth
          secret:
            secretName: {{ $name }}
            defaultMode: 288
        - name: tmp
          emptyDir: {medium: Memory, sizeLimit: 16Mi}
{{- end }}
