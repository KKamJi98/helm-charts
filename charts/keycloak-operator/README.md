# Locally owned Keycloak Operator preparation wrapper

Not an official Keycloak Helm chart. LOCAL PREPARATION ONLY, no installation.

- Namespace/release fixed to `keycloak` / `keycloak-operator`.
- Official 26.8.2 namespace-scoped bundle and four CRDs are byte-preserved.
  `vendor-manifest.json` records immutable source URLs and SHA256.
- Local render overlays are namespace/ServiceAccount-subject namespace and
  immutable Operator/related-server images ONLY. Published requests, limits,
  probes, watch environment and RBAC remain unchanged.
- Four namespace-current controllers, but four CRDs, five ClusterRoles and a
  narrow OpenShift-discovery ClusterRoleBinding remain cluster-scoped objects.
  Namespace Secret/workload authority is broad, namespace-admin-equivalent.
- `values.yaml`, `kkamji_local_values.yaml` and `files/preparation-profile.yaml`
  are a pinned preparation snapshot, enforced by schema and template guards.
- No dependency lock is needed: there are no Helm dependencies. Helm `crds/`
  does not itself upgrade installed CRDs; future Argo SSA ownership/sequencing
  needs explicit review and established CRDs before controller/CR reconciliation.
- The relocated pristine kustomization/README/license are provenance files, not
  a second installation path. Do not run the legacy Bitnami Keycloak chart.

See [candidate boundaries, resources and deployment gates](../../examples/keycloak-preparation/README.md)
and `tests/test_keycloak_preparation.py`. Use explicit verified Helm 4.2.1 and
local values for lint/render, never `helm install/upgrade` or cluster apply.
