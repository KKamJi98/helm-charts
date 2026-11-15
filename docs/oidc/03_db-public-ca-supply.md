---
title: Keycloak database public CA supply
updated: 2026-11-16T04:36:04+09:00
type: runbook
status: current
---

# Keycloak database public CA supply

## Source-prepared, not runtime accepted

This adds an opt-in public CA projection to `charts/keycloak-idp`. It does not
install anything or assert production TLS acceptance. Parent integration must
register this document and update the older preparation documents that still
call the projection unimplemented. Their earlier review does not cover this delta.

`publicCaProjection.enabled` defaults to `false` in all three preparation value
snapshots. The default render remains byte-identical: Operator 18 objects and
IdP 8 objects. Setting only this boolean to `true` adds 7 namespaced objects,
for IdP 15. Existing app/DB objects, images, credentials, namespace and network
policies are unchanged. This flag is not an initial-app-start acceptance gate.

An offline CA-only render uses the same local values file plus
`--set publicCaProjection.enabled=true`. The local profile accepts only that
boolean change. The separate production profile below accepts only two exact
phases and requires the same public CA supply plus declared off-host backup.
Source names, endpoints and permission scopes are not user-configurable. No
new controller, image, watchdog, CronJob or egress rule is introduced. All live
actions below belong to the parent operator, not this source-only implementation.

## Narrow production activation contract

The unchanged default profile is `keycloak-26.8.2-local-only`. The explicit
production enum is `keycloak-26.8.2-production`, selected by applying
`charts/keycloak-idp/production-values.yaml` **after** `kkamji_local_values.yaml`.
Its independent canonical overlay is `files/production-profile.yaml`. Both the
values schema and template guard require the exact production backup contract,
`publicCaProjection.enabled=true`, and one of two phases. Missing CA, missing
backup, unknown fields, wrong endpoint/credential refs or arbitrary profile
overrides are rejected rather than silently discarded, including when Helm
schema validation is bypassed. No rendered production object says local-only.

| Explicit profile/phase | IdP objects | App CR | Backup |
| --- | --- | --- | --- |
| Local default | 8 | Present, still unaccepted preparation | Absent |
| Local plus CA flag | 15 | Present, still unaccepted preparation | Absent |
| Production, `productionPhase: database` | 16 | **Absent** | Required |
| Production, `productionPhase: application` | 17 | Present, sync-wave 1 | Required |

The production overlay deliberately starts in **database** phase. It renders
the DB, credential references, public-CA reader/Store/projection, ingress-only
policies, backup ExternalSecret and ScheduledBackup, but no Keycloak app.
The app/database images, resources, 2-app/3-DB counts, worker-node affinity,
app anti-affinity, tokenless app, HTTPS hostname, JDBC `verify-full` mapping,
private management and disabled ingress are unchanged. There is no Namespace,
Application, route or realm/client import. No owner or MFA state is generated.

An offline production render is:

```sh
helm template keycloak charts/keycloak-idp -n keycloak \
  -f charts/keycloak-idp/kkamji_local_values.yaml \
  -f charts/keycloak-idp/production-values.yaml \
  --kube-version 1.36.1 --include-crds --skip-tests
```

Only after parent acceptance of the first phase may the reviewed rollout add
`--set productionPhase=application`, or its equivalent explicit GitOps value.
The phase is an operator decision, **not proof of live readiness**. Before that
switch, the parent must verify DB readiness, credential/Store/ExternalSecret
states, actual target `{ca.crt}` public-only content and single writer, and the
backup/WAL/recovery gates below. Both production phases keep CA and backup
required. Initial database phase is not an automatic pause/rollback switch for
an already deployed app: a pruned Keycloak CR could remove the app. Do not
revert a live production installation to local defaults to disable a feature.

### Backup references, region, catalog and schedule

The parent supplied nonsecret foundation metadata: bucket
`kkamji-keycloak-pg-backup`, region `ap-northeast-2`, destination
`s3://kkamji-keycloak-pg-backup/keycloak`, and SecureString JSON path
`/kkamji/keycloak/backup-s3`. This leaf did not query or provision AWS or inspect
credential values. The parent's verified bucket/IAM state is a prerequisite,
not a result of these offline chart checks. Do not recreate the bucket, IAM
user, policy or SSM parameter from this chart.

Production alone adds `ExternalSecret keycloak/keycloak-backup-s3`, using the
existing `parameter-store` ClusterSecretStore, Orphan/Retain and explicit
properties:

| Target key | Source |
| --- | --- |
| `ACCESS_KEY_ID` | `/kkamji/keycloak/backup-s3`, property `access_key_id` |
| `ACCESS_SECRET_KEY` | Same JSON, property `secret_access_key` |
| `AWS_REGION` | Public template literal `ap-northeast-2` |

`target.template.mergePolicy: Merge` is intentional: it retains the two fetched
properties while adding the public region. This is **not** target
`creationPolicy: Merge`; creation remains Orphan. With a nonempty template and
default template Replace policy, the fetched credentials would be omitted.[16]
No whole-JSON extraction, credential literal, session token or secret value is
stored in source. The parent must inspect the real target's exact three keys
without printing their values and confirm consumer access/current credentials.
As with the CA target, retention is not revocation or proof of fresh data.

Pinned CNPG 1.30 accepts `backup.barmanObjectStore.s3Credentials.region` only as
a SecretKeySelector (`name`, `key`), not a literal region. The profile points all
three selectors at `keycloak-backup-s3`. Its pinned CRD supports gzip and AES256
in **both** `data` and `wal`; those exact fields are enabled.[18]
`destinationPath` is fixed to the path above; `serverName` is deliberately
omitted, preserving the Cluster-name default `keycloak-db`. Recovery must use
that same server/catalog identity.[18][20]

The native `barmanObjectStore` path is intentionally retained for the existing
CNPG 1.30. It is deprecated upstream but supported in this pinned release;
this change does not upgrade CNPG, introduce a plugin, or add a controller.[20]
`retentionPolicy: 30d` is a recovery window, not a promise to delete every
object exactly 30 days after creation. CNPG retains the first valid base backup
needed before the recovery-window boundary and removes obsolete backups after
a later completed backup.[20]
The parent-reported bucket lifecycle is current 37 days/noncurrent 30 days;
that policy is not rendered or modified here, and real recoverability must be
verified independently. The AWS setup pattern was read from the platform
runbook without copying its IAM policy or deprecated pod-exec instructions.

The `keycloak-db-backup` ScheduledBackup uses method `barmanObjectStore`,
`immediate: false`, `suspend: false` and seconds-first schedule
`0 0 18 * * *`. This is daily 18:00 UTC, or next-day 03:00 KST when the CNPG
scheduler uses UTC. The parent must verify the installed operator's effective
time basis and the actual next scheduled timestamp; the schema alone does not
prove local timezone or successful execution.[19][21][22]
`backupOwnerReference: cluster` is supported and makes the generated Backup
resource owned by `keycloak-db`, rather than by the schedule. Removing a
schedule therefore does not itself garbage-collect these Backup records; this
is a Kubernetes record lifecycle decision, not an S3 retention guarantee.[21]
The Cluster's existing `Prune=false,Delete=false` annotation remains unchanged.

### Backup and application acceptance still belong to the parent

Before production authentication cutover, verify an actual off-host base backup,
WAL archival continuity, backup status/catalog identity, permitted object access,
retention behavior and an **isolated restore** using the same `keycloak-db`
server name. Do not restore over this source Cluster/PVC. Ensure the database
image actually contains the pinned in-tree backup tooling and observe any
archiving/restart effect when changing a live Cluster. The pinned object-store
docs defer authentication execution to Barman; schema support is not proof of
AWS authentication, TLS or a working backup.[23]

Application phase still requires both replacement app Pods/fresh connections
and before/after wrong-CA, wrong-hostname and downgrade rejection. Different
CA-key rotation remains the separately reviewed overlap procedure below. An
AWS foundation, successful render, ScheduledBackup CR or `SecretSynced` state
is not production completion. Parent owns live acceptance, human MFA, final
combined independent review, publication and cutover; the earlier 52-file
preparation review does not approve these production changes.

The follow-up offline suite is `tests/test_keycloak_production_profile.py`.
It covers all four renders, exact refs/counts, unchanged security fields,
duplicate-key/object rejection, strict pinned Cluster/ESO/ScheduledBackup schema
checks and fail-closed production gates. The ScheduledBackup test fixture is
an unchanged `v1` OpenAPI schema derived from the pinned CRD, not a deployed
CRD/vendor update.[19]
A controlled private-scratch guard-removal mutant makes the missing-CA/backup/
phase tests fail; the real source passes. No mutant was written into this
chart. The original 28 CA/preparation tests remain unchanged. Follow-up
commands, manifests, snapshots/hashes, scan output and derivation proof are
kept under the existing private CA evidence's `production-profile/` child;
the original CA-v1 evidence is preserved.

## Exact supply and authority

The fixed flow is:

```text
keycloak/keycloak-db-ca:ca.crt
  -> existing ESO controller, Kubernetes provider
  -> keycloak/keycloak-db-client-trust:ca.crt
  -> Keycloak spec.truststores.database.secret (optional=false)
```

CNPG 1.30 source commit `ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf`
returns the Cluster name plus the `-ca` suffix when `serverCASecret` is absent;
therefore this existing `keycloak-db` Cluster generates `keycloak-db-ca`.
`ensureCASecret` creates and owns that Secret.[7][8][9]
CNPG's default CA Secret contains **both** `ca.crt` and `ca.key`.[11]

The new ServiceAccount `keycloak-db-ca-reader` has
`automountServiceAccountToken: false`, no token Secret and no workload. Its
namespaced Role grants exactly core `secrets`, verb `get`, resourceNames
`[keycloak-db-ca]`. A separate namespaced Role grants only
`create serviceaccounts/token`, resourceNames `[keycloak-db-ca-reader]`, to
the existing `external-secrets/external-secrets` ServiceAccount. No ClusterRole,
cluster binding, wildcard, Secret list/watch/write, impersonation or new
permission to read the app/bootstrap credentials is added. This describes the
**new grants**, not the controller's pre-existing effective permissions.

ESO 2.4.1 commit `bb86f97bf24b47d2c797816e042ac37a85e802de` uses its
controller client for TokenRequest, requests a 3600-second expiration, and uses
the resulting short-lived token for the provider client. No audience override is
set; the API server's audience/expiration acceptance remains a runtime gate.[1]
The HTTPS endpoint is fixed to `https://kubernetes.default.svc`; the CA comes
from the local `kube-root-ca.crt` ConfigMap, key `ca.crt`. ESO builds this client
with `Insecure: false` and reads the CA via the existing controller client.[1]
The CAProvider namespace is intentionally omitted: a namespaced SecretStore
rejects an explicitly populated CAProvider namespace in this pinned API.[2]

Kubernetes 1.36.1 request parsing extracts the ServiceAccount name from the named
`.../serviceaccounts/keycloak-db-ca-reader/token` URL, even for POST. RBAC
matches both the `serviceaccounts/token` subresource and that name. Thus this
named TokenRequest does not require an unrestricted collection-create grant.[5][6]
This is source proof, not an executed API authorization test.

### Provider validation and its existing-cluster prerequisite

The pinned provider first creates a **SelfSubjectRulesReview** for `keycloak`.
It accepts a returned core Secret `get` rule without discarding rules that have
`resourceNames`; there is no list/watch requirement for this explicit fetch.
Only if a successful rules review contains no matching rule does it try an
unnamed Secret-get SelfSubjectAccessReview. If the rules-review call itself
fails, it returns an error rather than using that fallback.[2]

Stock Kubernetes binds `system:basic-user` to authenticated identities and
allows creating their own access/rules reviews.[4]
These review APIs are cluster-scoped; a namespaced Role pretending to grant them
would not fix a denied review. This chart adds no review ClusterRoleBinding.
If that default self-review authority is removed or the rules resolver cannot
return the named get rule, **stop** and record the exact Store error. Do not
broaden Secret permissions or add cluster-wide review authority silently.

### Public-only target, not field-level source isolation

ESO's `GetSecret` fetches the **whole named source Secret** before selecting
`remoteRef.property`; it returns the direct `ca.crt` data entry when present.[3]
Kubernetes Secret RBAC is not key-level. The dedicated reader and the ESO process
can therefore encounter the source private key. This design prevents its
**projection/mount into the application**, not controller/namespace-admin access
to it. The existing Keycloak Operator's broader Secret authority is unchanged.

The only mapping is `ca.crt <- keycloak-db-ca:ca.crt`, with no `dataFrom`, find,
whole-JSON extraction, templateFrom, key material, static token or raw CA bytes.
The target is Opaque with `creationPolicy: Orphan`, `deletionPolicy: Retain`,
`refreshPolicy: Periodic`, `refreshInterval: 1m`. The app still mounts the whole
**target** Secret, never the source. The pinned Operator builds that whole-Secret
volume and records it among the watched resources.[12]

Orphan/Retain is not an assertion about a pre-existing live Secret's keyset.
ESO 2.4.1 `ApplyTemplate` clears the data map for non-Merge creation policies,
then inserts the explicit data map here; a successful mutable reconciliation is
expected to converge to the single projected key.[16]
Before reconciliation, on immutable/update failures, with another writer, or
after this ExternalSecret is removed, a retained Secret may still hold stale or
unmanaged data. **Before enabling the app**, the parent must read back the actual
target's key names and require exactly `{ca.crt}`, validate that its content is
public PEM certificates only, and establish a single writer. Stop on `ca.key`,
any private-key PEM, unrelated key, unexpected owner or immutable target. Do not
assume the manifest/schema is a live-keyset proof. Retain on source loss is not
revocation, fresh trust, or a reason to keep accepting new database connections.

## Renewal versus root-key rotation

### Normal CNPG certificate renewal: supplied automatically, observed at runtime

Pinned CNPG `renewCASecret` parses the existing CA private key, passes it to
`RenewCertificate`, then writes only `ca.crt` back. `RenewCertificate` retains
the existing key/public key and changes certificate validity/serial/signature;
this is **certificate renewal with the same private key**, not root-key
rotation.[9][10]
The documented defaults are 90-day validity and renewal within 7 days of expiry,
configurable by the CNPG operator. The docs describe PostgreSQL certificate
reload, not Java truststore reload.[11]

The expected chain is CNPG public cert renewal -> next successful ESO refresh ->
public target update -> Keycloak Operator detects changed target -> app rolling
restart. Each arrow still needs live evidence. Poll intervals are not a bounded
end-to-end SLO when reconciliation, admission or startup can fail.

### Keycloak: restart-based uptake, not proven in-process Java reload

In pinned Keycloak 26.8.2 source commit
`e514445f9dcdabc5bdcf67cab56c1e49655de067`, `addTruststores` adds the target
Secret to watched resources. `WatchedResources.annotateDeployment` reads those
resources and puts their hash on the **StatefulSet Pod template**.[12][13]
The controller requeues ready watched workloads at the configured poll interval;
the pinned default is 60 seconds.[14][17]
With the image unchanged, `RecreateOnImageChange` selects rolling update;
the dependent resource returns the updated StatefulSet for that path.[15][12]
Despite legacy class/method names containing "Deployment", the resource here is
a StatefulSet. The source supports restart-based uptake. An updated Secret,
mounted file or successful ESO condition alone does **not** prove Java/JDBC
trust reloading. Parent acceptance must observe the Pod-template hash, both
replacement Pods reaching ready, and newly established JDBC/TLS connections.

### A different CA key: explicit old/new public-root overlap required

This chart does not implement automatic root-key rotation. The single-property
projection cannot retain an old root after the source changes to a new root.
Hand-editing the target while projection is active is unsafe: the next
successful non-Merge reconciliation replaces its data.[16]
Deleting CNPG's autogenerated CA is not the renewal procedure above.

Use this parent-owned maintenance sequence only after a separately reviewed
CNPG certificate/ownership and recovery plan exists. Both shipped production
phases require `publicCaProjection.enabled: true` in their schema and template
guard, so step 2 cannot run with either production profile alone. It requires a
separately reviewed maintenance candidate and explicit writer-handoff plan. Do
not weaken the production guard to improvise this transition:

1. Inventory existing trust/leaf validity, all DB instances, Keycloak Pods,
   clients and replication users. Capture baseline fresh-connection success,
   unrelated/wrong-CA rejection, wrong-hostname rejection and downgrade
   rejection. Keep `db-tls-mode=verify-server` (PostgreSQL JDBC `verify-full`)
   and the exact existing hostname. Have a tested database recovery route.
2. Set this flag false through the approved rollout path and explicitly verify
   the projection ExternalSecret is gone, no reconcile is in flight and its
   Orphan/Retain target remains. Merely setting a Helm value without confirming
   removal is not a writer handoff. Do not delete the target, DB or PVC.
3. The approved certificate operator supplies **only public** old-root plus
   new-root PEM certificates in the target's existing `ca.crt`. Keep the actual
   keyset exactly `{ca.crt}`. Do not insert a private key or rely on an unmanaged
   second data key surviving ESO. Wait for the Operator-driven hash change,
   all app Pod replacements and fresh connections before changing DB identity.
4. Transition CNPG certificates using its supported certificate inputs under
   that separate plan. CNPG documents user-provided `serverCASecret` and
   `serverTLSSecret`; those modes and their ownership handoff are **not enabled
   by this chart's immutable DB profile**.[11]
   The plan must include every server leaf, reload, SAN, any shared
   client/replication CA and the return to the fixed source Secret name. Do not
   silently widen this reader's names or edit an auto-managed CA and assume all
   leaves were reissued. If that transition is unprepared, stop or choose a
   separately approved outage/recovery path, not an improvised online rotation.
5. With both public roots trusted, switch all DB leaf identities and establish
   new connections from every app Pod. Verify server chains/SANs and rerun
   wrong-CA, wrong-hostname and downgrade rejection. Existing pooled connections
   alone are not proof. Preserve overlap until no consumer depends on old leaves.
6. Remove the old public root from the target only after those checks. Observe
   another complete app restart and fresh connections; verify a leaf requiring
   the retired root is rejected, alongside the other negative cases. Allow for
   existing default Java trust anchors; do not claim exclusive DB-CA pinning.
7. Re-enable projection only after the parent verifies that the fixed
   `keycloak-db-ca:ca.crt` now supplies exactly the intended public trust chain,
   the CNPG ownership mode is reconciled, and no manual writer remains. Read
   back target keys/content, ESO state, app restart and fresh positive/negative
   connection results again. Otherwise leave the explicitly owned maintenance
   supply in place and keep the unfinished gate visible.

This is a bounded manual overlap/handoff procedure, not a tested zero-downtime
root-key-rotation feature. No private key/certificate/token generation or live
rotation was performed by this source task.

## Parent runtime acceptance, still open

- Confirm installed ESO is the pinned provider API/behavior, and the existing
  controller identity is still `external-secrets/external-secrets`.
- Check **effective** reader authorization: named source get allowed; other
  Secret names/namespaces, list/watch/write denied. Test exact named
  TokenRequest allowance for the existing controller and other-SA denial;
  account for pre-existing controller privileges rather than attributing their
  removal to this additive Role. Confirm self-review and Store Ready.
- Confirm trusted API HTTPS/root ConfigMap and token audience/TTL acceptance.
  Do not log API tokens or read/print source private material to perform checks.
- Stage DB and projection first; create/start the Keycloak app only after the
  actual public-only target passes inspection. An all-at-once chart sync is
  **not** this gate. The CA ExternalSecret stays in DB wave 0 so it cannot
  deadlock a later DB creation by waiting for an as-yet nonexistent source.
- Confirm source/target public certificate fingerprints and validity match;
  verify `{ca.crt}` is the target's entire data keyset and PEM is public-only.
- Observe normal same-key CA renewal propagation, both app Pod replacements and
  fresh JDBC `verify-full` success. Require wrong-CA/wrong-hostname/downgrade
  rejection before and after renewal and any separately approved key rotation.
- Monitor expiry, ESO error/stale-target state, unavailable source, failed
  rolling restart and database reconnection. A retained old target is not a
  healthy automatic-supply result.

## Offline evidence and limitations

`tests/test_keycloak_ca_projection.py` runs with the already available Python
dependencies and verified Helm 4.2.1. The new activation test was observed RED
before implementation and GREEN afterward. The new 9-test suite validates the
unchanged default and activated renders/lint, exact names/namespace/API endpoint,
public property and app mount, no additional egress, tokenless/named-resource
RBAC, negative permission matrix, and fail-closed overrides even with Helm schema
validation disabled. All existing 19 preparation tests run unchanged.

SecretStore and ExternalSecret `v1` schemas are rendered offline from the existing
ESO `external-secrets-2.4.1.tgz`, guarded by SHA256
`d432db5dd4935cc8032f6fbc1c3f33b4baaa08db2be76de41e6cf3ea651fe574`.
The tests validate both objects and reject deliberately unknown/malformed
fields using the existing stricter local schema helper. This is not API-server
CEL/defaulting, admission/webhook, actual authorization, controller execution,
CNPG/Java execution or runtime rotation proof. No cloud/cluster/SSH/browser,
real database, Secret store or credential operation was performed.

Raw commands/exits, public source snapshots/hashes, before/final file hashes,
RED/GREEN output, scan adjudication and the new-delta report are kept in the
parent-owned private task evidence, not in public chart files. The parent still
owns final diff/independent review, docs index/coupling integration and all
production acceptance and publication decisions.

## Sources

[1] https://raw.githubusercontent.com/external-secrets/external-secrets/bb86f97bf24b47d2c797816e042ac37a85e802de/runtime/esutils/k8s_rest_config.go
[2] https://raw.githubusercontent.com/external-secrets/external-secrets/bb86f97bf24b47d2c797816e042ac37a85e802de/providers/v1/kubernetes/validate.go
[3] https://raw.githubusercontent.com/external-secrets/external-secrets/bb86f97bf24b47d2c797816e042ac37a85e802de/providers/v1/kubernetes/client.go
[4] https://raw.githubusercontent.com/kubernetes/kubernetes/v1.36.1/plugin/pkg/auth/authorizer/rbac/bootstrappolicy/policy.go
[5] https://raw.githubusercontent.com/kubernetes/kubernetes/v1.36.1/staging/src/k8s.io/apiserver/pkg/endpoints/request/requestinfo.go
[6] https://raw.githubusercontent.com/kubernetes/kubernetes/v1.36.1/plugin/pkg/auth/authorizer/rbac/rbac.go
[7] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/api/v1/cluster_funcs.go
[8] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/api/v1/cluster_types.go
[9] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/internal/controller/cluster_pki.go
[10] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/pkg/certs/certs.go
[11] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/docs/src/certificates.md
[12] https://raw.githubusercontent.com/keycloak/keycloak/e514445f9dcdabc5bdcf67cab56c1e49655de067/operator/src/main/java/org/keycloak/operator/controllers/KeycloakDeploymentDependentResource.java
[13] https://raw.githubusercontent.com/keycloak/keycloak/e514445f9dcdabc5bdcf67cab56c1e49655de067/operator/src/main/java/org/keycloak/operator/controllers/WatchedResources.java
[14] https://raw.githubusercontent.com/keycloak/keycloak/e514445f9dcdabc5bdcf67cab56c1e49655de067/operator/src/main/java/org/keycloak/operator/controllers/KeycloakController.java
[15] https://raw.githubusercontent.com/keycloak/keycloak/e514445f9dcdabc5bdcf67cab56c1e49655de067/operator/src/main/java/org/keycloak/operator/update/impl/RecreateOnImageChangeUpdateLogic.java
[16] https://raw.githubusercontent.com/external-secrets/external-secrets/bb86f97bf24b47d2c797816e042ac37a85e802de/pkg/controllers/externalsecret/externalsecret_controller_template.go
[17] https://raw.githubusercontent.com/keycloak/keycloak/e514445f9dcdabc5bdcf67cab56c1e49655de067/operator/src/main/resources/application.properties
[18] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/config/crd/bases/postgresql.cnpg.io_clusters.yaml
[19] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/config/crd/bases/postgresql.cnpg.io_scheduledbackups.yaml
[20] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/docs/src/appendixes/backup_barmanobjectstore.md
[21] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/docs/src/backup.md
[22] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/internal/controller/scheduledbackup_controller.go
[23] https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/ec38e6ef0cb37186ac5c4922fd8da1a768e5c9bf/docs/src/appendixes/object_stores.md
