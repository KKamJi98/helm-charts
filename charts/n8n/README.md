# n8n umbrella chart

KKamJi homelab wrapper for n8n.

- Official n8n chart is vendored as `charts/n8n`.
- PostgreSQL and Valkey are Bitnami subchart dependencies.
- AWS SSM Parameter Store values are synced by ESO through `templates/external-secret.yaml`.
- Envoy Gateway API routing is rendered by `templates/http-route.yaml`.
- Kubernetes Ingress and Envoy BasicAuth/SecurityPolicy are intentionally not used; n8n handles its own application login.
