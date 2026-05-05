# alloy

![Version: 1.5.0](https://img.shields.io/badge/Version-1.5.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v1.12.0](https://img.shields.io/badge/AppVersion-v1.12.0-informational?style=flat-square)

Grafana Alloy

## Requirements

| Repository | Name | Version |
|------------|------|---------|
|  | crds | 0.0.0 |

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| alloy.clustering.enabled | bool | `false` | Deploy Alloy in a cluster to allow for load distribution. |
| alloy.clustering.name | string | `""` | Name for the Alloy cluster. Used for differentiating between clusters. |
| alloy.clustering.portName | string | `"http"` | Name for the port used for clustering, useful if running inside an Istio Mesh |
| alloy.configMap.content | string | `""` | Content to assign to the new ConfigMap.  This is passed into `tpl` allowing for templating from values. |
| alloy.configMap.create | bool | `true` | Create a new ConfigMap for the config file. |
| alloy.configMap.key | string | `nil` | Key in ConfigMap to get config from. |
| alloy.configMap.name | string | `nil` | Name of existing ConfigMap to use. Used when create is false. |
| alloy.enableHttpServerPort | bool | `true` | Enables Grafana Alloy container's http server port. |
| alloy.enableReporting | bool | `true` | Enables sending Grafana Labs anonymous usage stats to help improve Grafana Alloy. |
| alloy.envFrom | list | `[]` | Maps all the keys on a ConfigMap or Secret as environment variables. https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.24/#envfromsource-v1-core |
| alloy.extraArgs | list | `[]` | Extra args to pass to `alloy run`: https://grafana.com/docs/alloy/latest/reference/cli/run/ |
| alloy.extraEnv | list | `[]` | Extra environment variables to pass to the Alloy container. |
| alloy.extraPorts | list | `[]` | Extra ports to expose on the Alloy container. |
| alloy.hostAliases | list | `[]` | Host aliases to add to the Alloy container. |
| alloy.initialDelaySeconds | int | `10` | Initial delay for readiness probe. |
| alloy.lifecycle | object | `{}` | Set lifecycle hooks for the Grafana Alloy container. |
| alloy.listenAddr | string | `"0.0.0.0"` | Address to listen for traffic on. 0.0.0.0 exposes the UI to other containers. |
| alloy.listenPort | int | `12345` | Port to listen for traffic on. |
| alloy.listenScheme | string | `"HTTP"` | Scheme is needed for readiness probes. If enabling tls in your configs, set to "HTTPS" |
| alloy.livenessProbe | object | `{}` | Set livenessProbe for the Grafana Alloy container. |
| alloy.mounts.dockercontainers | bool | `false` | Mount /var/lib/docker/containers from the host into the container for log collection. |
| alloy.mounts.extra | list | `[]` | Extra volume mounts to add into the Grafana Alloy container. Does not affect the watch container. |
| alloy.mounts.varlog | bool | `false` | Mount /var/log from the host into the container for log collection. |
| alloy.resources | object | `{}` | Resource requests and limits to apply to the Grafana Alloy container. |
| alloy.securityContext | object | `{}` | Security context to apply to the Grafana Alloy container. |
| alloy.stabilityLevel | string | `"generally-available"` | Minimum stability level of components and behavior to enable. Must be one of "experimental", "public-preview", or "generally-available". |
| alloy.storagePath | string | `"/tmp/alloy"` | Path to where Grafana Alloy stores data (for example, the Write-Ahead Log). By default, data is lost between reboots. |
| alloy.timeoutSeconds | int | `1` | Timeout for readiness probe. |
| alloy.uiPathPrefix | string | `"/"` | Base path where the UI is exposed. |
| configReloader.customArgs | list | `[]` | Override the args passed to the container. |
| configReloader.enabled | bool | `true` | Enables automatically reloading when the Alloy config changes. |
| configReloader.image.digest | string | `""` | SHA256 digest of image to use for config reloading (either in format "sha256:XYZ" or "XYZ"). When set, will override `configReloader.image.tag` |
| configReloader.image.registry | string | `"quay.io"` | Config reloader image registry (defaults to docker.io) |
| configReloader.image.repository | string | `"prometheus-operator/prometheus-config-reloader"` | Repository to get config reloader image from. |
| configReloader.image.tag | string | `"v0.81.0"` | Tag of image to use for config reloading. |
| configReloader.resources | object | `{"requests":{"cpu":"10m","memory":"50Mi"}}` | Resource requests and limits to apply to the config reloader container. |
| configReloader.securityContext | object | `{}` | Security context to apply to the Grafana configReloader container. |
| controller.affinity | object | `{}` | Affinity configuration for pods. |
| controller.autoscaling.enabled | bool | `false` | Creates a HorizontalPodAutoscaler for controller type deployment. Deprecated: Please use controller.autoscaling.horizontal instead |
| controller.autoscaling.horizontal | object | `{"enabled":false,"maxReplicas":5,"minReplicas":1,"scaleDown":{"policies":[],"selectPolicy":"Max","stabilizationWindowSeconds":300},"scaleUp":{"policies":[],"selectPolicy":"Max","stabilizationWindowSeconds":0},"targetCPUUtilizationPercentage":0,"targetMemoryUtilizationPercentage":80}` | Configures the Horizontal Pod Autoscaler for the controller. |
| controller.autoscaling.horizontal.enabled | bool | `false` | Enables the Horizontal Pod Autoscaler for the controller. |
| controller.autoscaling.horizontal.maxReplicas | int | `5` | The upper limit for the number of replicas to which the autoscaler can scale up. |
| controller.autoscaling.horizontal.minReplicas | int | `1` | The lower limit for the number of replicas to which the autoscaler can scale down. |
| controller.autoscaling.horizontal.scaleDown.policies | list | `[]` | List of policies to determine the scale-down behavior. |
| controller.autoscaling.horizontal.scaleDown.selectPolicy | string | `"Max"` | Determines which of the provided scaling-down policies to apply if multiple are specified. |
| controller.autoscaling.horizontal.scaleDown.stabilizationWindowSeconds | int | `300` | The duration that the autoscaling mechanism should look back on to make decisions about scaling down. |
| controller.autoscaling.horizontal.scaleUp.policies | list | `[]` | List of policies to determine the scale-up behavior. |
| controller.autoscaling.horizontal.scaleUp.selectPolicy | string | `"Max"` | Determines which of the provided scaling-up policies to apply if multiple are specified. |
| controller.autoscaling.horizontal.scaleUp.stabilizationWindowSeconds | int | `0` | The duration that the autoscaling mechanism should look back on to make decisions about scaling up. |
| controller.autoscaling.horizontal.targetCPUUtilizationPercentage | int | `0` | Average CPU utilization across all relevant pods, a percentage of the requested value of the resource for the pods. Setting `targetCPUUtilizationPercentage` to 0 will disable CPU scaling. |
| controller.autoscaling.horizontal.targetMemoryUtilizationPercentage | int | `80` | Average Memory utilization across all relevant pods, a percentage of the requested value of the resource for the pods. Setting `targetMemoryUtilizationPercentage` to 0 will disable Memory scaling. |
| controller.autoscaling.maxReplicas | int | `5` | The upper limit for the number of replicas to which the autoscaler can scale up. |
| controller.autoscaling.minReplicas | int | `1` | The lower limit for the number of replicas to which the autoscaler can scale down. |
| controller.autoscaling.scaleDown.policies | list | `[]` | List of policies to determine the scale-down behavior. |
| controller.autoscaling.scaleDown.selectPolicy | string | `"Max"` | Determines which of the provided scaling-down policies to apply if multiple are specified. |
| controller.autoscaling.scaleDown.stabilizationWindowSeconds | int | `300` | The duration that the autoscaling mechanism should look back on to make decisions about scaling down. |
| controller.autoscaling.scaleUp.policies | list | `[]` | List of policies to determine the scale-up behavior. |
| controller.autoscaling.scaleUp.selectPolicy | string | `"Max"` | Determines which of the provided scaling-up policies to apply if multiple are specified. |
| controller.autoscaling.scaleUp.stabilizationWindowSeconds | int | `0` | The duration that the autoscaling mechanism should look back on to make decisions about scaling up. |
| controller.autoscaling.targetCPUUtilizationPercentage | int | `0` | Average CPU utilization across all relevant pods, a percentage of the requested value of the resource for the pods. Setting `targetCPUUtilizationPercentage` to 0 will disable CPU scaling. |
| controller.autoscaling.targetMemoryUtilizationPercentage | int | `80` | Average Memory utilization across all relevant pods, a percentage of the requested value of the resource for the pods. Setting `targetMemoryUtilizationPercentage` to 0 will disable Memory scaling. |
| controller.autoscaling.vertical | object | `{"enabled":false,"recommenders":[],"resourcePolicy":{"containerPolicies":[{"containerName":"alloy","controlledResources":["cpu","memory"],"controlledValues":"RequestsAndLimits","maxAllowed":{},"minAllowed":{}}]},"updatePolicy":null}` | Configures the Vertical Pod Autoscaler for the controller. |
| controller.autoscaling.vertical.enabled | bool | `false` | Enables the Vertical Pod Autoscaler for the controller. |
| controller.autoscaling.vertical.recommenders | list | `[]` | List of recommenders to use for the Vertical Pod Autoscaler. Recommenders are responsible for generating recommendation for the object. List should be empty (then the default recommender will generate the recommendation) or contain exactly one recommender. |
| controller.autoscaling.vertical.resourcePolicy | object | `{"containerPolicies":[{"containerName":"alloy","controlledResources":["cpu","memory"],"controlledValues":"RequestsAndLimits","maxAllowed":{},"minAllowed":{}}]}` | Configures the resource policy for the Vertical Pod Autoscaler. |
| controller.autoscaling.vertical.resourcePolicy.containerPolicies | list | `[{"containerName":"alloy","controlledResources":["cpu","memory"],"controlledValues":"RequestsAndLimits","maxAllowed":{},"minAllowed":{}}]` | Configures the container policies for the Vertical Pod Autoscaler. |
| controller.autoscaling.vertical.resourcePolicy.containerPolicies[0].controlledResources | list | `["cpu","memory"]` | The controlled resources for the Vertical Pod Autoscaler. |
| controller.autoscaling.vertical.resourcePolicy.containerPolicies[0].controlledValues | string | `"RequestsAndLimits"` | The controlled values for the Vertical Pod Autoscaler. Needs to be either RequestsOnly or RequestsAndLimits. |
| controller.autoscaling.vertical.resourcePolicy.containerPolicies[0].maxAllowed | object | `{}` | The maximum allowed values for the pods. |
| controller.autoscaling.vertical.resourcePolicy.containerPolicies[0].minAllowed | object | `{}` | Defines the min allowed resources for the pod |
| controller.autoscaling.vertical.updatePolicy | string | `nil` | Configures the update policy for the Vertical Pod Autoscaler. |
| controller.dnsPolicy | string | `"ClusterFirst"` | Configures the DNS policy for the pod. https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/#pod-s-dns-policy |
| controller.enableStatefulSetAutoDeletePVC | bool | `false` | Whether to enable automatic deletion of stale PVCs due to a scale down operation, when controller.type is 'statefulset'. |
| controller.extraAnnotations | object | `{}` | Annotations to add to controller. |
| controller.extraContainers | list | `[]` | Additional containers to run alongside the Alloy container and initContainers. |
| controller.extraLabels | object | `{}` | Extra labels to add to the controller. |
| controller.hostNetwork | bool | `false` | Configures Pods to use the host network. When set to true, the ports that will be used must be specified. |
| controller.hostPID | bool | `false` | Configures Pods to use the host PID namespace. |
| controller.initContainers | list | `[]` |  |
| controller.minReadySeconds | int | `10` | How many additional seconds to wait before considering a pod ready. |
| controller.nodeSelector | object | `{}` | nodeSelector to apply to Grafana Alloy pods. |
| controller.parallelRollout | bool | `true` | Whether to deploy pods in parallel. Only used when controller.type is 'statefulset'. |
| controller.podAnnotations | object | `{}` | Extra pod annotations to add. |
| controller.podDisruptionBudget | object | `{"enabled":false,"maxUnavailable":null,"minAvailable":null}` | PodDisruptionBudget configuration. |
| controller.podDisruptionBudget.enabled | bool | `false` | Whether to create a PodDisruptionBudget for the controller. |
| controller.podDisruptionBudget.maxUnavailable | string | `nil` | Maximum number of pods that can be unavailable during a disruption. Note: Only one of minAvailable or maxUnavailable should be set. |
| controller.podDisruptionBudget.minAvailable | string | `nil` | Minimum number of pods that must be available during a disruption. Note: Only one of minAvailable or maxUnavailable should be set. |
| controller.podLabels | object | `{}` | Extra pod labels to add. |
| controller.priorityClassName | string | `""` | priorityClassName to apply to Grafana Alloy pods. |
| controller.replicas | int | `1` | Number of pods to deploy. Ignored when controller.type is 'daemonset'. |
| controller.terminationGracePeriodSeconds | string | `nil` | Termination grace period in seconds for the Grafana Alloy pods. The default value used by Kubernetes if unspecifed is 30 seconds. |
| controller.tolerations | list | `[]` | Tolerations to apply to Grafana Alloy pods. |
| controller.topologySpreadConstraints | list | `[]` | Topology Spread Constraints to apply to Grafana Alloy pods. |
| controller.type | string | `"daemonset"` | Type of controller to use for deploying Grafana Alloy in the cluster. Must be one of 'daemonset', 'deployment', or 'statefulset'. |
| controller.updateStrategy | object | `{}` | Update strategy for updating deployed Pods. |
| controller.volumeClaimTemplates | list | `[]` | volumeClaimTemplates to add when controller.type is 'statefulset'. |
| controller.volumes.extra | list | `[]` | Extra volumes to add to the Grafana Alloy pod. |
| crds.create | bool | `true` | Whether to install CRDs for monitoring. |
| extraObjects | list | `[]` | Extra k8s manifests to deploy |
| fullnameOverride | string | `nil` | Overrides the chart's computed fullname. Used to change the full prefix of resource names. |
| global.image.pullSecrets | list | `[]` | Optional set of global image pull secrets. |
| global.image.registry | string | `""` | Global image registry to use if it needs to be overridden for some specific use cases (e.g local registries, custom images, ...) |
| global.podSecurityContext | object | `{}` | Security context to apply to the Grafana Alloy pod. |
| image.digest | string | `nil` | Grafana Alloy image's SHA256 digest (either in format "sha256:XYZ" or "XYZ"). When set, will override `image.tag`. |
| image.pullPolicy | string | `"IfNotPresent"` | Grafana Alloy image pull policy. |
| image.pullSecrets | list | `[]` | Optional set of image pull secrets. |
| image.registry | string | `"docker.io"` | Grafana Alloy image registry (defaults to docker.io) |
| image.repository | string | `"grafana/alloy"` | Grafana Alloy image repository. |
| image.tag | string | `nil` | Grafana Alloy image tag. When empty, the Chart's appVersion is used. |
| ingress.annotations | object | `{}` |  |
| ingress.enabled | bool | `false` | Enables ingress for Alloy (Faro port) |
| ingress.extraPaths | list | `[]` |  |
| ingress.faroPort | int | `12347` |  |
| ingress.hosts[0] | string | `"chart-example.local"` |  |
| ingress.labels | object | `{}` |  |
| ingress.path | string | `"/"` |  |
| ingress.pathType | string | `"Prefix"` |  |
| ingress.tls | list | `[]` |  |
| nameOverride | string | `nil` | Overrides the chart's name. Used to change the infix in the resource names. |
| namespaceOverride | string | `nil` | Overrides the chart's namespace. |
| networkPolicy.egress[0] | object | `{}` |  |
| networkPolicy.enabled | bool | `false` |  |
| networkPolicy.flavor | string | `"kubernetes"` |  |
| networkPolicy.ingress[0] | object | `{}` |  |
| networkPolicy.policyTypes[0] | string | `"Ingress"` |  |
| networkPolicy.policyTypes[1] | string | `"Egress"` |  |
| rbac.clusterRules | list | `[{"apiGroups":[""],"resources":["nodes","nodes/proxy","nodes/metrics"],"verbs":["get","list","watch"]},{"nonResourceURLs":["/metrics"],"verbs":["get"]}]` | The rules to create for the ClusterRole objects. |
| rbac.clusterRules[0] | object | `{"apiGroups":[""],"resources":["nodes","nodes/proxy","nodes/metrics"],"verbs":["get","list","watch"]}` | Rules required for the `discovery.kubernetes` component. |
| rbac.clusterRules[1] | object | `{"nonResourceURLs":["/metrics"],"verbs":["get"]}` | Rules required for accessing metrics endpoint. |
| rbac.create | bool | `true` | Whether to create RBAC resources for Alloy. |
| rbac.namespaces | list | `[]` | If set, only create Roles and RoleBindings in the given list of namespaces, rather than ClusterRoles and ClusterRoleBindings. If not using ClusterRoles, bear in mind that Alloy will not be able to discover cluster-scoped resources such as Nodes. |
| rbac.rules | list | `[{"apiGroups":["","discovery.k8s.io","networking.k8s.io"],"resources":["endpoints","endpointslices","ingresses","pods","services"],"verbs":["get","list","watch"]},{"apiGroups":[""],"resources":["pods","pods/log","namespaces"],"verbs":["get","list","watch"]},{"apiGroups":["monitoring.grafana.com"],"resources":["podlogs"],"verbs":["get","list","watch"]},{"apiGroups":["monitoring.coreos.com"],"resources":["prometheusrules"],"verbs":["get","list","watch"]},{"apiGroups":["monitoring.coreos.com"],"resources":["alertmanagerconfigs"],"verbs":["get","list","watch"]},{"apiGroups":["monitoring.coreos.com"],"resources":["podmonitors","servicemonitors","probes","scrapeconfigs"],"verbs":["get","list","watch"]},{"apiGroups":[""],"resources":["events"],"verbs":["get","list","watch"]},{"apiGroups":[""],"resources":["configmaps","secrets"],"verbs":["get","list","watch"]},{"apiGroups":["apps","extensions"],"resources":["replicasets"],"verbs":["get","list","watch"]}]` | The rules to create for the ClusterRole or Role objects. |
| rbac.rules[0] | object | `{"apiGroups":["","discovery.k8s.io","networking.k8s.io"],"resources":["endpoints","endpointslices","ingresses","pods","services"],"verbs":["get","list","watch"]}` | Rules required for the `discovery.kubernetes` component. |
| rbac.rules[1] | object | `{"apiGroups":[""],"resources":["pods","pods/log","namespaces"],"verbs":["get","list","watch"]}` | Rules required for the `loki.source.kubernetes` component. |
| rbac.rules[2] | object | `{"apiGroups":["monitoring.grafana.com"],"resources":["podlogs"],"verbs":["get","list","watch"]}` | Rules required for the `loki.source.podlogs` component. |
| rbac.rules[3] | object | `{"apiGroups":["monitoring.coreos.com"],"resources":["prometheusrules"],"verbs":["get","list","watch"]}` | Rules required for the `mimir.rules.kubernetes` component. |
| rbac.rules[4] | object | `{"apiGroups":["monitoring.coreos.com"],"resources":["alertmanagerconfigs"],"verbs":["get","list","watch"]}` | Rules required for the `mimir.alerts.kubernetes` component. |
| rbac.rules[5] | object | `{"apiGroups":["monitoring.coreos.com"],"resources":["podmonitors","servicemonitors","probes","scrapeconfigs"],"verbs":["get","list","watch"]}` | Rules required for the `prometheus.operator.*` components. |
| rbac.rules[6] | object | `{"apiGroups":[""],"resources":["events"],"verbs":["get","list","watch"]}` | Rules required for the `loki.source.kubernetes_events` component. |
| rbac.rules[7] | object | `{"apiGroups":[""],"resources":["configmaps","secrets"],"verbs":["get","list","watch"]}` | Rules required for the `remote.kubernetes.*` components. |
| rbac.rules[8] | object | `{"apiGroups":["apps","extensions"],"resources":["replicasets"],"verbs":["get","list","watch"]}` | Rules required for the `otelcol.processor.k8sattributes` component. |
| service.annotations | object | `{}` |  |
| service.clusterIP | string | `""` | Cluster IP, can be set to None, empty "" or an IP address |
| service.enabled | bool | `true` | Creates a Service for the controller's pods. |
| service.internalTrafficPolicy | string | `"Cluster"` | Value for internal traffic policy. 'Cluster' or 'Local' |
| service.nodePort | int | `31128` | NodePort port. Only takes effect when `service.type: NodePort` |
| service.type | string | `"ClusterIP"` | Service type |
| serviceAccount.additionalLabels | object | `{}` | Additional labels to add to the created service account. |
| serviceAccount.annotations | object | `{}` | Annotations to add to the created service account. |
| serviceAccount.automountServiceAccountToken | bool | `true` |  |
| serviceAccount.create | bool | `true` | Whether to create a service account for the Grafana Alloy deployment. |
| serviceAccount.name | string | `nil` | The name of the existing service account to use when serviceAccount.create is false. |
| serviceMonitor.additionalLabels | object | `{}` | Additional labels for the service monitor. |
| serviceMonitor.enabled | bool | `false` |  |
| serviceMonitor.interval | string | `""` | Scrape interval. If not set, the Prometheus default scrape interval is used. |
| serviceMonitor.metricRelabelings | list | `[]` | MetricRelabelConfigs to apply to samples after scraping, but before ingestion. ref: https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/api.md#relabelconfig |
| serviceMonitor.relabelings | list | `[]` | RelabelConfigs to apply to samples before scraping ref: https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/api.md#relabelconfig |
| serviceMonitor.tlsConfig | object | `{}` | Customize tls parameters for the service monitor |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
