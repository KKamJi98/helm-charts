# redis-ha

![Version: 4.34.11](https://img.shields.io/badge/Version-4.34.11-informational?style=flat-square) ![AppVersion: 8.2.1](https://img.shields.io/badge/AppVersion-8.2.1-informational?style=flat-square)

This Helm chart provides a highly available Redis implementation with a master/slave configuration and uses Sentinel sidecars for failover management

**Homepage:** <https://redis.io/>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| dandydeveloper | <aaron.layfield@gmail.com> |  |

## Source Code

* <https://redis.io/download>
* <https://github.com/DandyDeveloper/charts/blob/master/charts/redis-ha>
* <https://github.com/oliver006/redis_exporter>

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| additionalAffinities | object | `{}` | Additional affinities to add to the Redis server pods. # Ref: https://kubernetes.io/docs/concepts/configuration/assign-pod-node/#affinity-and-anti-affinity |
| affinity | string | `""` | Override all other affinity settings for the Redis server pods with a string. |
| auth | bool | `false` | Configures redis with AUTH (requirepass & masterauth conf params) |
| authKey | string | `"auth"` | Defines the key holding the redis password in existing secret. |
| authSecretAnnotations | object | `{}` | Annotations for auth secret |
| configmap.labels | object | `{}` | Custom labels for the redis configmap |
| configmapTest.image | object | `{"repository":"koalaman/shellcheck","tag":"v0.10.0"}` | Image for redis-ha-configmap-test hook |
| configmapTest.image.repository | string | `"koalaman/shellcheck"` | Repository of the configmap shellcheck test image. |
| configmapTest.image.tag | string | `"v0.10.0"` | Tag of the configmap shellcheck test image. |
| configmapTest.resources | object | `{}` | Resources for the ConfigMap test pod |
| containerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}}` | Security context to be added to the Redis containers. |
| emptyDir | object | `{}` | Configuration of `emptyDir`, used only if persistentVolume is disabled and no hostPath specified |
| existingSecret | string | `nil` | An existing secret containing a key defined by `authKey` that configures `requirepass` and `masterauth` in the conf parameters (Requires `auth: enabled`, cannot be used in conjunction with `.Values.redisPassword`) |
| exporter.address | string | `"localhost"` | Address/Host for Redis instance. Exists to circumvent issues with IPv6 dns resolution that occurs on certain environments |
| exporter.enabled | bool | `false` | If `true`, the prometheus exporter sidecar is enabled |
| exporter.extraArgs | object | `{}` | Additional args for redis exporter |
| exporter.image | string | `"quay.io/oliver006/redis_exporter"` | Exporter image |
| exporter.livenessProbe.httpGet.path | string | `"/metrics"` | Exporter liveness probe httpGet path |
| exporter.livenessProbe.httpGet.port | int | `9121` | Exporter liveness probe httpGet port |
| exporter.livenessProbe.initialDelaySeconds | int | `15` | Initial delay in seconds for liveness probe of exporter |
| exporter.livenessProbe.periodSeconds | int | `15` | Period in seconds after which liveness probe will be repeated |
| exporter.livenessProbe.timeoutSeconds | int | `3` | Timeout seconds for liveness probe of exporter |
| exporter.port | int | `9121` | Exporter port |
| exporter.portName | string | `"exporter-port"` | Exporter port name |
| exporter.pullPolicy | string | `"IfNotPresent"` | Exporter image pullPolicy |
| exporter.readinessProbe.httpGet.path | string | `"/metrics"` | Exporter readiness probe httpGet path |
| exporter.readinessProbe.httpGet.port | int | `9121` | Exporter readiness probe httpGet port |
| exporter.readinessProbe.initialDelaySeconds | int | `15` | Initial delay in seconds for readiness probe of exporter |
| exporter.readinessProbe.periodSeconds | int | `15` | Period in seconds after which readiness probe will be repeated |
| exporter.readinessProbe.successThreshold | int | `2` | Success threshold for readiness probe of exporter |
| exporter.readinessProbe.timeoutSeconds | int | `3` | Timeout seconds for readiness probe of exporter |
| exporter.resources | object | `{}` | cpu/memory resource limits/requests |
| exporter.scrapePath | string | `"/metrics"` | Exporter scrape path |
| exporter.script | string | `""` | A custom custom Lua script that will be mounted to exporter for collection of custom metrics. Creates a ConfigMap and sets env var `REDIS_EXPORTER_SCRIPT`. |
| exporter.serviceMonitor.disableAPICheck | bool | `false` | Disable API Check on ServiceMonitor |
| exporter.serviceMonitor.enabled | bool | `false` | When set true then use a ServiceMonitor to configure scraping |
| exporter.serviceMonitor.endpointAdditionalProperties | object | `{}` | Set additional properties for the ServiceMonitor endpoints such as relabeling, scrapeTimeout, tlsConfig, and more. |
| exporter.serviceMonitor.interval | string | `""` | Set how frequently Prometheus should scrape (default is 30s) |
| exporter.serviceMonitor.labels | object | `{}` | Set labels for the ServiceMonitor, use this to define your scrape label for Prometheus Operator |
| exporter.serviceMonitor.metricRelabelings | list | `[]` |  |
| exporter.serviceMonitor.namespace | string | `.Release.Namespace` | Set the namespace the ServiceMonitor should be deployed |
| exporter.serviceMonitor.relabelings | list | `[]` |  |
| exporter.serviceMonitor.telemetryPath | string | `""` | Set path to redis-exporter telemtery-path (default is /metrics) |
| exporter.serviceMonitor.timeout | string | `""` | Set timeout for scrape (default is 10s) |
| exporter.tag | string | `"v1.67.0"` | Exporter image tag |
| extraContainers | list | `[]` | Extra containers to include in StatefulSet |
| extraInitContainers | list | `[]` | Extra init containers to include in StatefulSet |
| extraLabels | object | `{}` | Labels added here are applied to all created resources |
| extraVolumes | list | `[]` | Extra volumes to include in StatefulSet |
| fullnameOverride | string | `""` | Full name of the Redis HA Resources |
| global.compatibility | object | `{"openshift":{"adaptSecurityContext":"auto"}}` | Openshift compatibility options |
| global.priorityClassName | string | `""` | Default priority class for all components |
| haproxy.IPv6.enabled | bool | `true` | Enable HAProxy parameters to bind and consume IPv6 addresses. Enabled by default. |
| haproxy.additionalAffinities | object | `{}` | Additional affinities to add to the haproxy pods. |
| haproxy.affinity | string | `""` | Override all other affinity settings for the haproxy pods with a string. |
| haproxy.annotations | object | `{}` | HAProxy template annotations |
| haproxy.checkFall | int | `1` | haproxy.cfg `check fall` setting |
| haproxy.checkInterval | string | `"1s"` | haproxy.cfg `check inter` setting |
| haproxy.containerPort | int | `6379` | Modify HAProxy deployment container port |
| haproxy.containerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}}` | Security context to be added to the HAProxy containers. |
| haproxy.customConfig | string | `nil` | Allows for custom config-haproxy.cfg file to be applied. If this is used then default config will be overwriten |
| haproxy.deploymentAnnotations | object | `{}` | HAProxy deployment annotations |
| haproxy.deploymentStrategy | object | `{"type":"RollingUpdate"}` | Deployment strategy for the haproxy deployment |
| haproxy.emptyDir | object | `{}` | Configuration of `emptyDir` |
| haproxy.enabled | bool | `false` | Enabled HAProxy LoadBalancing/Proxy |
| haproxy.extraConfig | string | `nil` | Allows to place any additional configuration section to add to the default config-haproxy.cfg |
| haproxy.hardAntiAffinity | bool | `true` | Whether the haproxy pods should be forced to run on separate nodes. |
| haproxy.image.pullPolicy | string | `"IfNotPresent"` | HAProxy Image PullPolicy |
| haproxy.image.repository | string | `"public.ecr.aws/docker/library/haproxy"` | HAProxy Image Repository |
| haproxy.image.tag | string | `"3.0.8-alpine"` | HAProxy Image Tag |
| haproxy.imagePullSecrets | list | `[]` | Reference to one or more secrets to be used when pulling images ref: https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/ |
| haproxy.init.resources | object | `{}` | Extra init resources |
| haproxy.labels | object | `{}` | Custom labels for the haproxy pod |
| haproxy.lifecycle | object | `{}` | Container lifecycle hooks. Ref: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/ |
| haproxy.metrics.enabled | bool | `false` | HAProxy enable prometheus metric scraping |
| haproxy.metrics.port | int | `9101` | HAProxy prometheus metrics scraping port |
| haproxy.metrics.portName | string | `"http-exporter-port"` | HAProxy metrics scraping port name |
| haproxy.metrics.scrapePath | string | `"/metrics"` | HAProxy prometheus metrics scraping path |
| haproxy.metrics.serviceMonitor.disableAPICheck | bool | `false` | Disable API Check on ServiceMonitor |
| haproxy.metrics.serviceMonitor.enabled | bool | `false` | When set true then use a ServiceMonitor to configure scraping |
| haproxy.metrics.serviceMonitor.endpointAdditionalProperties | object | `{}` | Set additional properties for the ServiceMonitor endpoints such as relabeling, scrapeTimeout, tlsConfig, and more. |
| haproxy.metrics.serviceMonitor.interval | string | `""` | Set how frequently Prometheus should scrape (default is 30s) |
| haproxy.metrics.serviceMonitor.labels | object | `{}` | Set labels for the ServiceMonitor, use this to define your scrape label for Prometheus Operator |
| haproxy.metrics.serviceMonitor.namespace | string | `.Release.Namespace` | Set the namespace the ServiceMonitor should be deployed |
| haproxy.metrics.serviceMonitor.telemetryPath | string | `""` | Set path to redis-exporter telemtery-path (default is /metrics) |
| haproxy.metrics.serviceMonitor.timeout | string | `""` | Set timeout for scrape (default is 10s) |
| haproxy.networkPolicy.annotations | object | `{}` | Annotations for Haproxy NetworkPolicy |
| haproxy.networkPolicy.egressRules | list | `[]` | user can define egress rules too, uses the same structure as ingressRules |
| haproxy.networkPolicy.enabled | bool | `false` | whether NetworkPolicy for Haproxy should be created |
| haproxy.networkPolicy.ingressRules | list | `[]` | user defined ingress rules that Haproxy should permit into. uses the format defined in https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#label-selectors |
| haproxy.networkPolicy.labels | object | `{}` | Labels for Haproxy NetworkPolicy |
| haproxy.podAnnotations | object | `{}` | Annotations to be added to the HAProxy deployment pods |
| haproxy.podDisruptionBudget | object | `{}` | Pod Disruption Budget ref: https://kubernetes.io/docs/tasks/run-application/configure-pdb/ |
| haproxy.priorityClassName | string | `""` | Kubernetes priorityClass name for the haproxy pod |
| haproxy.readOnly | object | `{"enabled":false,"port":6380}` | Enable read-only redis-slaves |
| haproxy.readOnly.enabled | bool | `false` | Enable if you want a dedicated port in haproxy for redis-slaves |
| haproxy.readOnly.port | int | `6380` | Port for the read-only redis-slaves |
| haproxy.replicas | int | `3` | Number of HAProxy instances |
| haproxy.resources | object | `{}` | HAProxy resources |
| haproxy.securityContext | object | `{"fsGroup":99,"runAsNonRoot":true,"runAsUser":99}` | Security context to be added to the HAProxy deployment. |
| haproxy.service.annotations | string | `nil` | HAProxy service annotations |
| haproxy.service.externalIPs | object | `{}` | HAProxy external IPs |
| haproxy.service.externalTrafficPolicy | string | `nil` | HAProxy service externalTrafficPolicy value (haproxy.service.type must be LoadBalancer) |
| haproxy.service.labels | object | `{}` | HAProxy service labels |
| haproxy.service.loadBalancerIP | string | `nil` | HAProxy service loadbalancer IP |
| haproxy.service.loadBalancerSourceRanges | list | `[]` | List of CIDR's allowed to connect to LoadBalancer |
| haproxy.service.nodePort | int | `nil` | HAProxy service nodePort value (haproxy.service.type must be NodePort) |
| haproxy.service.type | string | `"ClusterIP"` | HAProxy service type "ClusterIP", "LoadBalancer" or "NodePort" |
| haproxy.serviceAccount.automountToken | bool | `true` |  |
| haproxy.serviceAccount.create | bool | `true` | Specifies whether a ServiceAccount should be created |
| haproxy.serviceAccountName | string | `"redis-sa"` | HAProxy serviceAccountName |
| haproxy.servicePort | int | `6379` | Modify HAProxy service port |
| haproxy.stickyBalancing | bool | `false` | HAProxy sticky load balancing to Redis nodes. Helps with connections shutdown. |
| haproxy.tests.resources | object | `{}` | Pod resources for the tests against HAProxy. |
| haproxy.timeout.check | string | `"2s"` | haproxy.cfg `timeout check` setting |
| haproxy.timeout.client | string | `"330s"` | haproxy.cfg `timeout client` setting |
| haproxy.timeout.connect | string | `"4s"` | haproxy.cfg `timeout connect` setting |
| haproxy.timeout.server | string | `"330s"` | haproxy.cfg `timeout server` setting |
| haproxy.tls | object | `{"certMountPath":"/tmp/","enabled":false,"keyName":null,"secretName":""}` | Enable TLS termination on HAproxy, This will create a volume mount |
| haproxy.tls.certMountPath | string | `"/tmp/"` | Path to mount the secret that contains the certificates. haproxy |
| haproxy.tls.enabled | bool | `false` | If "true" this will enable TLS termination on haproxy |
| haproxy.tls.keyName | string | `nil` | Key file name |
| haproxy.tls.secretName | string | `""` | Secret containing the .pem file |
| hardAntiAffinity | bool | `true` | Whether the Redis server pods should be forced to run on separate nodes. # This is accomplished by setting their AntiAffinity with requiredDuringSchedulingIgnoredDuringExecution as opposed to preferred. # Ref: https://kubernetes.io/docs/concepts/configuration/assign-pod-node/#inter-pod-affinity-and-anti-affinity-beta-feature |
| hostPath.chown | bool | `true` | if chown is true, an init-container with root permissions is launched to change the owner of the hostPath folder to the user defined in the security context |
| hostPath.path | string | `""` | Use this path on the host for data storage. path is evaluated as template so placeholders are replaced |
| image.pullPolicy | string | `"IfNotPresent"` | Redis image pull policy |
| image.repository | string | `"public.ecr.aws/docker/library/redis"` | Redis image repository |
| image.tag | string | `"8.2.1-alpine"` | Redis image tag |
| imagePullSecrets | list | `[]` | Reference to one or more secrets to be used when pulling redis images |
| init.resources | object | `{}` | Extra init resources |
| labels | object | `{}` | Custom labels for the redis pod |
| nameOverride | string | `""` | Name override for Redis HA resources |
| networkPolicy.annotations | object | `{}` | Annotations for NetworkPolicy |
| networkPolicy.egressRules | list | `[{"ports":[{"port":53,"protocol":"UDP"},{"port":53,"protocol":"TCP"}],"selectors":[{"namespaceSelector":{}},{"ipBlock":{"cidr":"169.254.0.0/16"}}]}]` | user can define egress rules too, uses the same structure as ingressRules |
| networkPolicy.egressRules[0].selectors[0] | object | `{"namespaceSelector":{}}` | Allow all destinations for DNS traffic |
| networkPolicy.enabled | bool | `false` | whether NetworkPolicy for Redis StatefulSets should be created. when enabled, inter-Redis connectivity is created |
| networkPolicy.ingressRules | list | `[]` | User defined ingress rules that Redis should permit into. Uses the format defined in https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#label-selectors |
| networkPolicy.labels | object | `{}` | Labels for NetworkPolicy |
| nodeSelector | object | `{}` | Node labels for pod assignment |
| persistentVolume.accessModes | list | `["ReadWriteOnce"]` | Persistent volume access modes |
| persistentVolume.annotations | object | `{}` | Annotations for the volume |
| persistentVolume.enabled | bool | `true` | Enable persistent volume |
| persistentVolume.labels | object | `{}` | Labels for the volume |
| persistentVolume.size | string | `"10Gi"` | Persistent volume size |
| persistentVolume.storageClass | string | `nil` | redis-ha data Persistent Volume Storage Class |
| podDisruptionBudget | object | `{}` | Pod Disruption Budget rules |
| podManagementPolicy | string | `"OrderedReady"` | The statefulset pod management policy |
| priorityClassName | string | `""` | Kubernetes priorityClass name for the redis-ha-server pod |
| prometheusRule.additionalLabels | object | `{}` | Additional labels to be set in metadata. |
| prometheusRule.enabled | bool | `false` | If true, creates a Prometheus Operator PrometheusRule. |
| prometheusRule.interval | string | `"10s"` | How often rules in the group are evaluated (falls back to `global.evaluation_interval` if not set). |
| prometheusRule.namespace | string | `nil` | Namespace which Prometheus is running in. |
| prometheusRule.rules | list | `[]` | Rules spec template (see https://github.com/prometheus-operator/prometheus-operator/blob/master/Documentation/api.md#rule). |
| rbac.create | bool | `true` | Create and use RBAC resources |
| redis.annotations | object | `{}` | Annotations for the redis statefulset |
| redis.authClients | string | `""` | It is possible to disable client side certificates authentication when "authClients" is set to "no" |
| redis.config | object | see values.yaml | Any valid redis config options in this section will be applied to each server, For multi-value configs use list instead of string (for example loadmodule) (see below) |
| redis.config.maxmemory | string | `"0"` | Max memory to use for each redis instance. Default is unlimited. |
| redis.config.maxmemory-policy | string | `"volatile-lru"` | Max memory policy to use for each redis instance. Default is volatile-lru. |
| redis.config.min-replicas-max-lag | int | `5` | Value in seconds |
| redis.config.repl-diskless-sync | string | `"yes"` | When enabled, directly sends the RDB over the wire to slaves, without using the disk as intermediate storage. Default is false. |
| redis.config.save | string | `"900 1"` | Please note that local (on-disk) RDBs will still be created when re-syncing with a new slave. The only way to prevent this is to enable diskless replication. |
| redis.customArgs | list | `[]` | Allows overriding the redis container arguments |
| redis.customCommand | list | `[]` | Allows overriding the redis container command |
| redis.customConfig | string | `nil` | Allows for custom redis.conf files to be applied. If this is used then `redis.config` is ignored |
| redis.disableCommands | list | `["FLUSHDB","FLUSHALL"]` | Array with commands to disable |
| redis.envFrom | list | `[]` | Load environment variables from ConfigMap/Secret |
| redis.extraVolumeMounts | list | `[]` | additional volumeMounts for Redis container |
| redis.lifecycle | object | see values.yaml | Container Lifecycle Hooks for redis container Ref: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/ |
| redis.livenessProbe | object | `{"enabled":true,"failureThreshold":5,"initialDelaySeconds":30,"periodSeconds":15,"successThreshold":1,"timeoutSeconds":15}` | Liveness probe parameters for redis container |
| redis.livenessProbe.enabled | bool | `true` | Enable the Liveness Probe |
| redis.livenessProbe.failureThreshold | int | `5` | Failure threshold for liveness probe |
| redis.livenessProbe.initialDelaySeconds | int | `30` | Initial delay in seconds for liveness probe |
| redis.livenessProbe.periodSeconds | int | `15` | Period in seconds after which liveness probe will be repeated |
| redis.livenessProbe.successThreshold | int | `1` | Success threshold for liveness probe |
| redis.livenessProbe.timeoutSeconds | int | `15` | Timeout seconds for liveness probe |
| redis.masterGroupName | string | `"mymaster"` | Redis convention for naming the cluster group: must match `^[\\w-\\.]+$` and can be templated |
| redis.podAnnotations | object | `{}` | Annotations to be added to the redis statefulset pods |
| redis.port | int | `6379` | Port to access the redis service |
| redis.readinessProbe | object | `{"enabled":true,"failureThreshold":5,"initialDelaySeconds":30,"periodSeconds":15,"successThreshold":1,"timeoutSeconds":15}` | Readiness probe parameters for redis container |
| redis.readinessProbe.enabled | bool | `true` | Enable the Readiness Probe |
| redis.readinessProbe.failureThreshold | int | `5` | Failure threshold for readiness probe |
| redis.readinessProbe.initialDelaySeconds | int | `30` | Initial delay in seconds for readiness probe |
| redis.readinessProbe.periodSeconds | int | `15` | Period in seconds after which readiness probe will be repeated |
| redis.readinessProbe.successThreshold | int | `1` | Success threshold for readiness probe |
| redis.readinessProbe.timeoutSeconds | int | `15` | Timeout seconds for readiness probe |
| redis.resources | object | `{}` | CPU/Memory for master/slave nodes resource requests/limits |
| redis.startupProbe | object | `{"enabled":true,"failureThreshold":5,"initialDelaySeconds":30,"periodSeconds":15,"successThreshold":1,"timeoutSeconds":15}` | Startup probe parameters for redis container |
| redis.startupProbe.enabled | bool | `true` | Enable Startup Probe |
| redis.startupProbe.failureThreshold | int | `5` | Failure threshold for startup probe |
| redis.startupProbe.initialDelaySeconds | int | `30` | Initial delay in seconds for startup probe |
| redis.startupProbe.periodSeconds | int | `15` | Period in seconds after which startup probe will be repeated |
| redis.startupProbe.successThreshold | int | `1` | Success threshold for startup probe |
| redis.startupProbe.timeoutSeconds | int | `15` | Timeout seconds for startup probe |
| redis.terminationGracePeriodSeconds | int | `60` | Increase terminationGracePeriodSeconds to allow writing large RDB snapshots. (k8s default is 30s) ref: https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-forced |
| redis.tlsPort | int | `nil` | TLS Port to access the redis service |
| redis.tlsReplication | bool | `nil` | Configures redis with tls-replication parameter, if true sets "tls-replication yes" in redis.conf |
| redis.updateStrategy | object | `{"type":"RollingUpdate"}` | Update strategy for Redis StatefulSet # ref: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#update-strategies |
| redisPassword | string | `nil` | A password that configures a `requirepass` and `masterauth` in the conf parameters (Requires `auth: enabled`) |
| replicas | int | `3` | Number of redis master/slave |
| restore.existingSecret | bool | `false` | Set existingSecret to true to use secret specified in existingSecret above |
| restore.redis.source | string | `""` |  |
| restore.s3.access_key | string | `""` | Restore init container - AWS AWS_ACCESS_KEY_ID to access restore.s3.source |
| restore.s3.region | string | `""` | Restore init container - AWS AWS_REGION to access restore.s3.source |
| restore.s3.secret_key | string | `""` | Restore init container - AWS AWS_SECRET_ACCESS_KEY to access restore.s3.source |
| restore.s3.source | string | `""` | Restore init container - AWS S3 location of dump - i.e. s3://bucket/dump.rdb or false |
| restore.ssh.key | string | `""` | Restore init container - SSH private key to scp restore.ssh.source to init container. Key should be in one line separated with \n. i.e. `-----BEGIN RSA PRIVATE KEY-----\n...\n...\n-----END RSA PRIVATE KEY-----` |
| restore.ssh.source | string | `""` | Restore init container - SSH scp location of dump - i.e. user@server:/path/dump.rdb or false |
| restore.timeout | int | `600` | Timeout for the restore |
| ro_replicas | string | `""` | Comma separated list of slaves which never get promoted to be master. Count starts with 0. Allowed values 1-9. i.e. 3,4 - 3th and 4th redis slave never make it to be master, where master is index 0. |
| schedulerName | string | `""` | Use an alternate scheduler, e.g. "stork". ref: https://kubernetes.io/docs/tasks/administer-cluster/configure-multiple-schedulers/ |
| securityContext | object | `{"fsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}` | Security context to be added to the Redis StatefulSet. |
| sentinel.auth | bool | `false` | Enables or disables sentinel AUTH (Requires `sentinel.password` to be set) |
| sentinel.authClients | string | `""` | It is possible to disable client side certificates authentication when "authClients" is set to "no" |
| sentinel.authKey | string | `"sentinel-password"` | The key holding the sentinel password in an existing secret. |
| sentinel.config | object | see values.yaml | Valid sentinel config options in this section will be applied as config options to each sentinel (see below) |
| sentinel.customArgs | list | `[]` |  |
| sentinel.customCommand | list | `[]` |  |
| sentinel.customConfig | string | `""` | Allows for custom sentinel.conf files to be applied. If this is used then `sentinel.config` is ignored |
| sentinel.existingSecret | string | `""` | An existing secret containing a key defined by `sentinel.authKey` that configures `requirepass` in the conf parameters (Requires `sentinel.auth: enabled`, cannot be used in conjunction with `.Values.sentinel.password`) |
| sentinel.extraVolumeMounts | list | `[]` | additional volumeMounts for Sentinel container |
| sentinel.lifecycle | object | `{}` | Container Lifecycle Hooks for sentinel container. Ref: https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/ |
| sentinel.livenessProbe.enabled | bool | `true` |  |
| sentinel.livenessProbe.failureThreshold | int | `5` | Failure threshold for liveness probe |
| sentinel.livenessProbe.initialDelaySeconds | int | `30` | Initial delay in seconds for liveness probe |
| sentinel.livenessProbe.periodSeconds | int | `15` | Period in seconds after which liveness probe will be repeated |
| sentinel.livenessProbe.successThreshold | int | `1` | Success threshold for liveness probe |
| sentinel.livenessProbe.timeoutSeconds | int | `15` | Timeout seconds for liveness probe |
| sentinel.password | string | `nil` | A password that configures a `requirepass` in the conf parameters (Requires `sentinel.auth: enabled`) |
| sentinel.port | int | `26379` | Port to access the sentinel service |
| sentinel.quorum | int | `2` | Minimum number of nodes expected to be live. |
| sentinel.readinessProbe.enabled | bool | `true` |  |
| sentinel.readinessProbe.failureThreshold | int | `5` | Failure threshold for readiness probe |
| sentinel.readinessProbe.initialDelaySeconds | int | `30` | Initial delay in seconds for readiness probe |
| sentinel.readinessProbe.periodSeconds | int | `15` | Period in seconds after which readiness probe will be repeated |
| sentinel.readinessProbe.successThreshold | int | `3` | Success threshold for readiness probe |
| sentinel.readinessProbe.timeoutSeconds | int | `15` | Timeout seconds for readiness probe |
| sentinel.resources | object | `{}` | CPU/Memory for sentinel node resource requests/limits |
| sentinel.startupProbe | object | `{"enabled":true,"failureThreshold":3,"initialDelaySeconds":5,"periodSeconds":10,"successThreshold":1,"timeoutSeconds":15}` | Startup probe parameters for redis container |
| sentinel.startupProbe.enabled | bool | `true` | Enable Startup Probe |
| sentinel.startupProbe.failureThreshold | int | `3` | Failure threshold for startup probe |
| sentinel.startupProbe.initialDelaySeconds | int | `5` | Initial delay in seconds for startup probe |
| sentinel.startupProbe.periodSeconds | int | `10` | Period in seconds after which startup probe will be repeated |
| sentinel.startupProbe.successThreshold | int | `1` | Success threshold for startup probe |
| sentinel.startupProbe.timeoutSeconds | int | `15` | Timeout seconds for startup probe |
| sentinel.tlsPort | int | `nil` | TLS Port to access the sentinel service |
| sentinel.tlsReplication | bool | `nil` | Configures sentinel with tls-replication parameter, if true sets "tls-replication yes" in sentinel.conf |
| serviceAccount.annotations | object | `{}` | Annotations to be added to the service account for the redis statefulset |
| serviceAccount.automountToken | bool | `false` | opt in/out of automounting API credentials into container. Ref: https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/ |
| serviceAccount.create | bool | `true` | Specifies whether a ServiceAccount should be created |
| serviceAccount.name | string | `""` | The name of the ServiceAccount to use. If not set and create is true, a name is generated using the redis-ha.fullname template |
| serviceLabels | object | `{}` | Custom labels for redis service |
| splitBrainDetection.interval | int | `60` | Interval between redis sentinel and server split brain checks (in seconds) |
| splitBrainDetection.resources | object | `{}` | splitBrainDetection resources |
| splitBrainDetection.retryInterval | int | `10` |  |
| sysctlImage.command | list | `[]` | sysctlImage command to execute |
| sysctlImage.enabled | bool | `false` | Enable an init container to modify Kernel settings |
| sysctlImage.mountHostSys | bool | `false` | Mount the host `/sys` folder to `/host-sys` |
| sysctlImage.pullPolicy | string | `"Always"` | sysctlImage Init container pull policy |
| sysctlImage.registry | string | `"public.ecr.aws/docker/library"` | sysctlImage Init container registry |
| sysctlImage.repository | string | `"busybox"` | sysctlImage Init container name |
| sysctlImage.resources | object | `{}` | sysctlImage resources |
| sysctlImage.tag | string | `"1.34.1"` | sysctlImage Init container tag |
| tls.caCertFile | string | `"ca.crt"` | Name of CA certificate file |
| tls.certFile | string | `"redis.crt"` | Name of certificate file |
| tls.dhParamsFile | string | `nil` | Name of Diffie-Hellman (DH) key exchange parameters file (Example: redis.dh) |
| tls.keyFile | string | `"redis.key"` | Name of key file |
| tolerations | list | `[]` |  |
| topologySpreadConstraints.enabled | bool | `false` | Enable topology spread constraints |
| topologySpreadConstraints.maxSkew | string | `""` | Max skew of pods tolerated |
| topologySpreadConstraints.topologyKey | string | `""` | Topology key for spread constraints |
| topologySpreadConstraints.whenUnsatisfiable | string | `""` | Enforcement policy, hard or soft |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
