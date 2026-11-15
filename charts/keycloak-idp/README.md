# Locally owned Keycloak 26.8.2 IdP chart

This chart preserves the pre-existing Bitnami `charts/keycloak` untouched.
The candidate path is `charts/keycloak-idp`, not `charts/keycloak`. No Helm
install/upgrade or human-MFA action is performed by this source alone. The
default local preparation profile does not declare an active GitOps Application,
Namespace, public route or realm/client import. The current management root
separately selects the production database phase; see the
[phased GitOps deployment](../../docs/05_oidc-idp-preparation.md). That declaration
does not prove actual DB readiness, backup/restore or owner login acceptance.

## Exact supported profiles

| Values | IdP objects | Meaning |
| --- | --- | --- |
| `kkamji_local_values.yaml` | 8 | Unchanged local preparation; backup absent |
| Same plus `publicCaProjection.enabled=true` | 15 | Public CA supply only; backup absent |
| Same plus `production-values.yaml` | 16 | Production database phase; **no app CR** |
| Production plus `productionPhase=application` | 17 | Explicit app activation after parent runtime acceptance |

The production overlay must follow `kkamji_local_values.yaml`. It selects the
exact `keycloak-26.8.2-production` enum and requires public-only CA projection
and the fixed off-host backup. Its default `productionPhase: database` stages
the DB, ESO credential references, public CA supply and daily backup schedule
before any Keycloak app exists. Application phase is a separate reviewed
operator decision, not an automatic assertion that live gates have passed.

Both schema and independent template guard preserve the image digests,
2-app/3-DB sizing, resources, worker affinity/anti-affinity, tokenless app,
strict HTTPS/JDBC verify-full behavior, private management and disabled
ingress. No egress allow-all, unsupported podTemplate or weak JDBC URL is added.
Production requires the exact backup bucket/prefix, named credential selectors,
gzip/AES256 data and WAL, 30-day retention window and daily schedule. All
credential material remains outside source; only refs/public metadata are here.

Do not pass the CNPG whole CA Secret to the app: it contains `ca.key`.
The optional ESO Kubernetes provider maps only `ca.crt` to the existing whole-
Secret app truststore target. The parent must inspect the actual target's
keys/public content and verify restart/fresh JDBC behavior before app activation.
Normal same-key certificate renewal is distinct from unproven automatic
root-key rotation. Backup declarations do not prove base backup, WAL or restore.
Do not revert a live app to database/local mode as an implicit rollback.

See [CA and production activation contract](../../docs/oidc/03_db-public-ca-supply.md)
for exact references, ordering, rotation overlap, runtime acceptance and pinned
schema provenance. Tests: `test_keycloak_preparation.py`,
`test_keycloak_ca_projection.py`, `test_keycloak_production_profile.py`.
The prior preparation review does not approve this new production delta;
combined independent review, live acceptance and publication remain parent-owned.
