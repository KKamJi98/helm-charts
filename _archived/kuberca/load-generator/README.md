# Load Generator (k6)

Helm chart to run k6 load against Bookinfo services.

Autoscaling is disabled by default. `load-generator` is intended to keep a predictable total load profile, so the default mode is a single Deployment with `replicaCount`. If `autoscaling.enabled=true`, the chart renders an HPA and leaves `Deployment.spec.replicas` unmanaged so Kubernetes HPA can control the replica count.

## Values

- `replicaCount`: default Deployment replica count
- `autoscaling.enabled`: enable HorizontalPodAutoscaler generation
- `autoscaling.minReplicas`: minimum replica count for HPA
- `autoscaling.maxReplicas`: maximum replica count for HPA
- `autoscaling.targetCPUUtilizationPercentage`: CPU utilization target for HPA
- `target.baseUrl`: productpage service base URL
- `target.detailsBaseUrl`: details service base URL
- `target.ratingsBaseUrl`: ratings service base URL
- `target.weights.productpage`: productpage traffic weight
- `target.weights.details`: details traffic weight
- `target.weights.ratings`: ratings traffic weight
- `target.rps`: requests per second (RPS)
- `target.duration`: k6 duration
- `target.preAllocatedVUs`: k6 pre-allocated VUs
- `target.maxVUs`: k6 max VUs
- `image.repository`, `image.tag`, `image.pullPolicy`: k6 image settings

## Optional autoscaling profile

- `autoscaling.minReplicas=1`
- `autoscaling.maxReplicas=5`
- `autoscaling.targetCPUUtilizationPercentage=60`
