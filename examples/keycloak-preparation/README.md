# Keycloak 26.8.2 preparation candidate

LOCAL PREPARATION ONLY. Nothing here authorizes deployment, credentials, realm
import, external exposure or an application authentication/default switch.

This document describes the original local preparation profile and inactive
examples only. Its no-root-change and no-SecretStore statements do not describe
the separate production profiles. The approved management-root database phase,
optional/production-required ESO public-CA projection and remaining runtime gates
are documented in [phased deployment](../../docs/05_oidc-idp-preparation.md) and
[CA/production runbook](../../docs/oidc/03_db-public-ca-supply.md). These examples
remain inactive; a source review is not deployment authority or runtime acceptance.

## Paths and inactive ownership

- Operator: `charts/keycloak-operator`, release `keycloak-operator`, namespace
  `keycloak`. Thin locally owned wrapper, NOT an official application Helm chart.
- Server/DB/reference-only ESO/ingress policies: `charts/keycloak-idp`,
  release and Keycloak CR `keycloak`, namespace `keycloak`.
- The pre-existing `charts/keycloak` is a Bitnami 24.4.10 / Keycloak 26.1.2
  chart. It and its real dependency lock are retained byte-for-byte. DO NOT
  render/deploy that legacy path as this candidate. The new candidate is kept
  in its own sibling directory; no legacy chart migration/deletion or active
  application root change is part of this preparation.
- All six proposed Namespace/Application/HTTPS HTTPRoute/RealmImport/consumer
  reader manifests have `.inactive` suffixes outside active GitOps roots.
  `UNRESOLVED_REVIEWED_COMMIT` must remain unresolved until independent review
  and separate authorization. No automated sync, Application finalizers,
  CreateNamespace option, AppProject or root Application is added.
- `skip-reconcile` is effective for Argo Applications, not a Kubernetes admission
  control for other kinds. The suffix/location and no apply are essential.
- Both inactive Applications reuse existing `management` AppProject declarations
  from `charts/argocd/kkamji_local_values.yaml`. Its wildcard destinations,
  repositories and resource permissions are broad authority, NOT new isolation.
  Cross-Application order is a future gate: Namespace/CRDs established, Operator,
  database/ESO/trust prerequisites, then Keycloak; no sync-wave magic guarantees it.

## Immutable upstream and explicit overlays

Official namespace-scoped published YAML and all four CRDs are preserved by
SHA256 in `charts/keycloak-operator/vendor-manifest.json`. The resources commit
is `79ba77fd65bb05a8300cd1396d6be9806a0f290f`; Keycloak source commit is
`e514445f9dcdabc5bdcf67cab56c1e49655de067`. `vendor/LICENSE.txt` is retained.
The relocated pristine kustomization is provenance, not a runnable replacement
for this chart. Its CRD files are deliberately under Helm `crds/`.

Only the following Operator render overlays are owned locally:

1. Namespace `keycloak` on namespaced resources, and namespace on every
   ServiceAccount subject of RoleBindings/ClusterRoleBinding. This mirrors the
   published kustomization's namespace and `allServiceAccounts` transformer.
2. Immutable Operator image digest and both related-server image environment
   variables. Probes, resources, RBAC, watch variables, selectors and all other
   published fields are preserved. Tests compare the entire parsed bundle.

Four `JOSDK_WATCH_CURRENT` controller environments reconcile this namespace.
Installation still contains four cluster-scoped CRDs, five ClusterRoles and one
ClusterRoleBinding. That binding grants only `get config.openshift.io/ingresses`
for OpenShift discovery. Five namespace RoleBindings bind four controller roles
and Kubernetes `view`. Preview Client CRDs are installed because the published
bundle includes them, but no preview Client CR, feature flag or API is used.
Keycloak/RealmImport store `v2beta1`; the preview Client CRDs store `v2alpha1`.

The Operator can list/watch/read/create/delete namespace Secrets; RealmImport
also has patch/update. It is namespace-admin-equivalent trusted authority,
including access to the private CNPG CA Secret. Do not claim strict isolation
from `ca.key`, or keep unrelated credentials in this namespace. The app's
public-only CA volume is a separate, narrower data-plane boundary.

All chart values form an immutable preparation profile, not general-purpose
runtime tuning. JSON schema and template guards reject changed actual supported
fields, unknown keys, namespace/release drift, weak URL overrides and exposure.
The guard still runs with Helm schema checking disabled. Future design changes
must deliberately revise/review the profile, values, schema, tests and sources.
These guards are local rendering checks, NOT Kubernetes admission controls.

## Images, TLS and secrets

- Stock server digest `sha256:c68e286cacd87b942ac1939a0a1481461109d6acd3a57dc496969a319a76bbf0`
  explicitly uses `startOptimized: false`; an explicit stock image otherwise
  defaults to optimized startup in the Operator. No custom extensions/podTemplate.
- Operator digest `sha256:df890db951b595fe46f3f985301a38b76fcfcc264f06201c54dfaf28adeba19e`.
- Dedicated CNPG PostgreSQL `18.4-system-trixie` plus digest
  `sha256:42708a75345b7a48fdd9257b071830783a97fd228529196b6313187a7198e185`.
  The same pinned Keycloak source's supported-databases template lists 18.x,
  17.x, 16.x, 15.x and 14.x; PostgreSQL 18.4 is within that documented range.
  Public registry index response bytes were rehashed; images/layers were not run.
  No signature/attestation, CVE scan or pull/startup verification was performed.
  Release-pipeline revision labels are not the Keycloak source revision.
- No literal username/password, generated bootstrap secret, source Secret,
  SecretStore, IAM reader or SSM parameter is created here. Three ExternalSecrets
  use existing `parameter-store`, explicit JSON properties and Orphan/Retain:
  `/kkamji/keycloak/database` username/password -> `keycloak-db-app` basic-auth;
  `/kkamji/keycloak/bootstrap` username/password -> `keycloak-bootstrap-admin`;
  `/kkamji/keycloak/clients/kkamji-platform` client_secret ->
  `keycloak-oidc-client` key `client-secret`. The database username MUST be
  `keycloak` to match CNPG initdb owner. This local rendering does not provision
  or read the SSM source contents.
- Orphan/Retain preserves stale target data on deletion/failure; it is neither a
  backup nor proof of revocation. CNPG `Prune=false,Delete=false` is also only an
  Argo retention hint, not protection from Namespace/PVC/manual deletion.
- Bootstrap reference is explicit to avoid implicit generated initial-admin
  credentials. An existing master realm ignores bootstrap inputs. Temporary
  admin cleanup and supported recovery remain deployment gates. Signing keys
  persist in this dedicated database; no authentik runtime secret_key is reused.
- Supported `db-tls-mode=verify-server` maps to PostgreSQL JDBC `verify-full`
  and DefaultJavaSSLFactory. No `db.url` or extra JDBC SSL properties are allowed.
  Host is `keycloak-db-rw.keycloak.svc.cluster.local`; CNPG server SAN explicitly
  includes that host. Actual certificate/connection verification is pending.
- `truststores.database.secret.name=keycloak-db-client-trust`, `optional=false`,
  mounts the WHOLE Secret. It MUST contain ONLY public CA certificate/chain
  (`ca.crt`), never `ca.key`/private material. NEVER use `keycloak-db-ca` here.
  Java default roots remain additive, not a DB-exclusive trust allowlist.
- **Separate source/runtime gates**: the default local preparation profile
  leaves public-CA projection disabled. The optional ESO projection and both
  production profiles are described by the current CA/production runbook above;
  no new controller or CronJob is introduced. A missing trust Secret is
  nonoptional and must prevent startup. Schema cannot inspect actual contents.
  The initial preparation review marked derivation `UNIMPLEMENTED`; that is a
  historical status, not a claim about the implemented opt-in ESO source today.
  Parent runtime acceptance must prove public-only integrity/keyset, missing or
  wrong CA, wrong SAN, plaintext downgrade rejection, real verify-full success
  and CA renewal/reconnection. The Keycloak Operator's trust Secret polling
  does NOT itself derive/synchronize the public-only copy.

## Network and proxy proposal

No default HTTPRoute or Ingress. The inactive route proposes
`https://sso.kkamji.net` through existing Gateway
`envoy-gateway-system/kkamji`, listener `https`, to `keycloak-service:8080`.
Pinned Operator Service/controller code proves the default server labels, suffix
and HTTP port. The Operator's own Service is a different `:80 -> :8080` endpoint.
Management `9000` is never a route backend. Ingress generation is disabled.
The inactive public route matches ONLY `/realms/kkamji` and `/resources`. Admin
UI/API on 8080 and `/realms/master` remain outside that public route; management
9000 isolation alone would not protect those paths. Controlled private admin
access and live encoded-path/normalization/bypass tests remain deployment gates.

The server has strict full-URL hostname, edge HTTP enabled on 8080 and
`proxy.headers=xforwarded`. Its Operator-generated additive ingress policy is
explicitly disabled; the local three ingress-only NetworkPolicies instead provide:

- Default-deny ingress across the namespace, including Operator/import Pods.
- HTTP 8080 only from namespace `envoy-gateway-system` AND proxy component AND
  owning Gateway name/namespace labels matching `kkamji`/`envoy-gateway-system`.
- Management 9000 only from namespace-local `keycloak-operator` label.
- JGroups 7800/57800 only between matching server Pods.
- Dedicated DB 5432 only from this Keycloak server/import job, matching CNPG
  Operator pods in `cnpg-system`, and this cluster's peers. CNPG Operator/peers
  also get instance-manager 8000. No arbitrary namespace-wide source allows.
- This candidate does not manage egress and adds no allow-all egress policy.
  An otherwise empty namespace has unrestricted egress, but existing controls
  are not broadened by this chart. This is not an exfiltration control. Existing
  ingress policies remain additive; live CNI behavior/policy inventory are gates.

Actual Envoy/CNPG selectors come from parent read-only `cluster-metadata.json`.
No private CIDRs or trust-all proxy addresses are invented. Envoy forwarded-header
overwrite, actual source CIDRs, direct-access rejection, Gateway acceptance,
DNS/TLS ownership, management isolation and certificate coverage block exposure.
No listener, wildcard certificate, DNS or app auth defaults are changed.

## Resource and scheduling model

| Component | Count | Requests each | Limits each |
|---|---:|---|---|
| Operator | 1 | 300m CPU / 450Mi | 700m CPU / 450Mi |
| Keycloak server | 2 | 1 CPU / 2Gi | 2 CPU / 2Gi |
| Dedicated CNPG | 3 | 250m CPU / 1Gi | 1 CPU / 1Gi |
| Future import job | 1, inactive | 1 CPU / 2Gi | 2 CPU / 2Gi |

Steady six Pods: requests 3050m / 7618Mi; limits 7700m / 7618Mi.
One future import: seven Pods, requests 4050m / 9666Mi; limits 9700m / 9666Mi.
Operator's untouched default RollingUpdate may surge one Pod: steady plus surge
requests 3350m / 8068Mi; limits 8400m / 8068Mi. Concurrent import plus Operator
surge: eight Pods, requests 4350m / 10116Mi; limits 10400m / 10116Mi.
Storage is THREE 10Gi local-path PVCs, 30Gi total requested, not available disk.
Pinned CNPG code creates one main Postgres container and one REGULAR
`bootstrap-controller` init container, both using Cluster `spec.resources`.
Their effective per-resource max is still 250m/1Gi requests and 1CPU/1Gi limits,
not double. No candidate plugin, extension or steady sidecar is configured.
The init image is inherited from the existing CNPG Operator, observed by the
parent as `ghcr.io/cloudnative-pg/cloudnative-pg:1.30.0`; this chart does not own
or repin that running Operator. Its inherited image digest is a future gate.
Keycloak's supported stock spec adds no init/sidecar; the published Operator
also has one container and no init/sidecar. Mutating admission is not modeled.

CNPG initdb/replica bootstrap Jobs use the same resource vector and regular init.
One EXTRA concurrent CNPG Job/replacement Pod is a conservative reserve, not
proof the controller surges that way: steady plus that reserve is seven Pods,
3300m/8642Mi requests and 8700m/8642Mi limits. Import + Operator surge + that
one-DB reserve is nine Pods, 4600m/11140Mi requests and 11400m/11140Mi limits.
Concurrency, completed-Pod accounting, storage binding, mutable admission,
bootstrap order and maintenance replacement behavior are not proven live.
Bound/retest every additional concurrent Pod before deployment. A first-create
initdb Job does not mean there are already three running database Pods.

Server anti-affinity is REQUIRED per hostname and matches actual `app=keycloak`,
instance/managed-by/component labels. Supported nodeAffinity allows only
`k8s-w1`/`k8s-w2`; no tolerations allow the master NoSchedule taint. DB spread is
PREFERRED because three instances cannot have hard separation on two workers.
No claim is made that preferred DB spread guarantees one/two placement.

Import Jobs inherit the StatefulSet, replace `app` with `keycloak-realm-import`,
and use `spec.import.scheduling` to REPLACE affinity/tolerations/spread/priority.
The explicit override retains worker eligibility but removes server hard
anti-affinity. Including `app=keycloak` in the SERVER rule is also necessary:
otherwise existing servers' required anti-affinity can repel the incoming Job.
Explicit RealmImport `spec.resources` avoids the pinned `addResources` helper's
fallback ambiguity; do not assume CPU/2Gi requests are inherited when omitted.

`RecreateOnImageChange` is selected: image changes accept downtime, no blanket
rolling/zero-downtime promise. Auto is rejected by the preparation profile.
A supported future update-job scheduling override is present but does not select
Auto. If deliberately changed later, its regular init container and main
container execute serially: use per-resource max(old,new), NOT sum. At current
sizes one check Job would add 1 CPU / 2Gi requests, 2 CPU / 2Gi limits. Import and
future Auto check overlap would be 5050m / 11714Mi requests, 11700m / 11714Mi
limits, eight total Pods (six steady plus two distinct Jobs); this is
NOT SELECTED and needs a new budget/approval. No application surge is assumed
for the selected recreate image update; the six-Pod steady upper bound does not
promise availability during the zero-server interval.

Parent request headroom: w1 6575m / 8240.712890625Mi; w2 4795m /
3882.705078125Mi. A feasible REQUEST-ONLY example is w1 one server, two DBs,
Operator and one import (2800m / 6594Mi), w2 one server and one DB
(1250m / 3072Mi). This is not a placement instruction or scheduler proof.
For example two DBs plus one server already need 4096Mi on w2, exceeding that
snapshot's memory-request headroom. Existing w2 memory limits are 110%; that is
a residual risk, not real spare RAM. Performance/load/OOM/disk and maintenance
placement tests remain gates. Both workers share one physical Windows Hyper-V
host: replicas are not physical-failure HA. Off-host encrypted backups and a
restore drill, including retained signing/WebAuthn/owner mappings, are absent.

## Disabled realm/client and MFA activation gates

The `.inactive` RealmImport is CREATE-ONLY: realm `kkamji` and confidential client
`kkamji-platform` are DISABLED, registration/reset-password off, no brokers/users
or client flow overrides. Standard authorization-code flow is prepared with
PKCE S256 and EXACT callback `https://platform.kkamji.net/api/auth/oidc/callback`.
Authorization code/state naturally arrive in the callback URL query. Suppress
query strings in Envoy/application/access/error/trace logs; never claim the code
is absent from the URL. Future RP validation must prove this log handling.
Direct/implicit/service-account/device/CIBA/token-exchange/JWT/external-token grant
paths are off. Only `${OIDC_CLIENT_SECRET}` from a same-namespace Secret selector
appears in the seed; there is no literal or generated client credential.

WebAuthn UV `required`, RP ID `sso.kkamji.net`, entity name `KKamJi`, integrated
passwordless passkeys off are policy ONLY. No guessed JSON/browser-flow binding
is included. A **manual** activation/export/validation gate remains: duplicate
built-in Browser flow; preserve Username Password Form REQUIRED, Conditional 2FA
subflow REQUIRED, WebAuthn REQUIRED, OTP and recovery-code executions DISABLED.
Do not invent flow `enabled:false`. The realm/client stay disabled until the
actual exported built-in IDs/requirements and effective bindings are reviewed.

Required WebAuthn forces ENROLLMENT when absent, not deny-unenrolled. A password
holder may reach enrollment. Controlled owner enrollment, stable owner sub,
primary plus backup/recovery credential, and loss/revocation ceremony are human
gates. Cookie SSO can skip Forms, so review/revoke old sessions and test every
other entry path; no fresh-WebAuthn-per-RP-request claim. Test positive signed
claims plus wrong issuer/audience/subject, absent/cancelled WebAuthn,
direct-grant, cookie and recovery bypass negatives.

Reapplying a RealmImport does NOT update an existing realm, activate it, or
rotate a client credential. ESO updating its Secret does NOT rotate the Keycloak
client either. Subsequent activation/rotation require separately approved
supported Admin API/console operations AND exact readback. No import executes
here, and none is deleted. Future cleanup follows the upstream one-shot guide.
App authorization must be exact issuer `https://sso.kkamji.net/realms/kkamji`
PLUS the approved owner sub, not any IdP user. No platform code/auth switch.

## Offline verification only

`K` below denotes this local task evidence directory, not a pre-existing shell
variable. Set it before running the command:

```sh
K=/home/kkamji/.local/state/kkamji-platform/keycloak-idp-preparation-1571471993558147166
```

On another host, supply a separately verified Helm binary and writable TMPDIR.
Set `HELM_BIN` explicitly to the independently verified `v4.2.1+gd591a19` binary;
Helm 3.16 is not the final renderer. Do not run `install`, `upgrade`, apply or a
third-party image/binary as part of this candidate verification.

```sh
HELM_BIN="$K/tools/helm-v4.2.1/helm" TMPDIR="$K/test-tmp" \
  PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s tests -p test_keycloak_preparation.py -v
```

Tests perform strict lint/template with local values, Kubernetes 1.36.1,
`--include-crds --skip-tests`, exact vendor/overlay and authority comparison,
supported-field negative probes with/without schema, public-CA ref/TLS/ESO
checks, source-derived ingress and budget/affinity models, disabled seed and
pinned schema validation. Both dependencies PyYAML/jsonschema were already
available; no global install is required. No dependencies means no new Chart.lock.

The four pristine Keycloak CRDs are the authority for Keycloak types. Derived
CNPG 1.30 and ESO 2.4.1 public OpenAPI schemas, hashes, licenses and provenance
are under `schemas/`; source/code URLs and hashes are in `upstream-contracts.json`.
The offline validator recognizes implicit Kubernetes envelope fields and rejects
unknown declared spec fields; it does not emulate CEL/defaulting/admission or
prove runtime compatibility, Secret content, authorization, scheduling or CNI.
No live proof, image execution, credentials, provisioning, publication,
installation or application authentication changes are included.


## Separate disabled consumer contract

[consumer-contract/seven-clients.yaml.inactive](consumer-contract/seven-clients.yaml.inactive)
is a source-only, non-applyable seven-client/groups/secure-ref contract, not a
seventh Kubernetes manifest or a replacement for the historical create-only seed.
No users, owner mappings, secrets or flow IDs are provided. All service clients
remain disabled. Use the [controlled enrollment source checklist](../../docs/oidc/07_owner-enrollment-source.md)
for parent-owned private HTTPS, actual flow export/binding/session-cookie review,
human UV plus independent backup/recovery and supported Admin API readback/update/rotation.
