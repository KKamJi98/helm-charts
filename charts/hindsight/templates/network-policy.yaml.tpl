{{- $root := . -}}
{{- range $component := list "api" "control-plane" "model-init" }}
---
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: {{ $root.Values.name }}-{{ $component }}
  labels:
    {{- include "kkamji-hindsight.labels" $root | nindent 4 }}
  annotations:
    argocd.argoproj.io/sync-wave: "-10"
spec:
  endpointSelector:
    matchLabels:
      app.kubernetes.io/name: {{ $root.Values.name }}
      app.kubernetes.io/instance: {{ $root.Release.Name }}
      app.kubernetes.io/component: {{ $component }}
  {{- if ne $component "model-init" }}
  ingress:
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: {{ $root.Values.exposure.gateway.namespace }}
            gateway.envoyproxy.io/owning-gateway-name: {{ $root.Values.exposure.gateway.name }}
      toPorts:
        - ports:
            - port: {{ ternary "8888" "3000" (eq $component "api") | quote }}
              protocol: TCP
    {{- if eq $component "api" }}
    - fromEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: {{ $root.Release.Namespace }}
            app.kubernetes.io/name: {{ $root.Values.name }}
            app.kubernetes.io/instance: {{ $root.Release.Name }}
            app.kubernetes.io/component: control-plane
      toPorts:
        - ports:
            - port: "8888"
              protocol: TCP
    {{- end }}
  {{- else }}
  ingress: []
  {{- end }}
  egress:
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: kube-system
            k8s-app: kube-dns
      toPorts:
        - ports:
            - port: "53"
              protocol: UDP
            - port: "53"
              protocol: TCP
          rules:
            dns:
              - matchPattern: "**.cluster.local"
              {{- if eq $component "api" }}
              - matchName: api.openai.com
              - matchName: auth.openai.com
              {{- else if eq $component "model-init" }}
              - matchName: huggingface.co
              - matchPattern: "*.huggingface.co"
              - matchPattern: "*.hf.co"
              - matchPattern: "*.xethub.hf.co"
              {{- end }}
    {{- if eq $component "control-plane" }}
    - toEndpoints:
        - matchLabels:
            k8s:io.kubernetes.pod.namespace: {{ $root.Release.Namespace }}
            app.kubernetes.io/name: {{ $root.Values.name }}
            app.kubernetes.io/instance: {{ $root.Release.Name }}
            app.kubernetes.io/component: api
      toPorts:
        - ports:
            - port: "8888"
              protocol: TCP
    {{- else }}
    - toFQDNs:
      {{- if eq $component "api" }}
        - matchName: api.openai.com
        - matchName: auth.openai.com
      {{- else }}
        - matchName: huggingface.co
        - matchPattern: "*.huggingface.co"
        - matchPattern: "*.hf.co"
        - matchPattern: "*.xethub.hf.co"
      {{- end }}
      toPorts:
        - ports:
            - port: "443"
              protocol: TCP
    {{- end }}
{{- end }}
