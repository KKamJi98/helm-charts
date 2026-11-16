---
title: Controlled Keycloak owner enrollment source checklist
updated: 2026-11-17T01:39:57+09:00
type: runbook
status: current
---

# Controlled Keycloak owner enrollment source checklist

## Source boundary

This is a procedure for the parent, not an enrollment implementation, flow export,
activation permission or runtime verdict. `runtimeAccepted=false` and
`dataMigrationAccepted=false` describe this source task, not a reversal of the
parent's completed Grafana storage acceptance. Normal consumer modes remain
legacy; `accessLogsSafe`, `dataPreservationReady` and `cutoverApproved` remain false
in source. Do not fabricate an owner predicate or mark any ceremony complete.

The [disabled seven-client contract](../../examples/keycloak-preparation/consumer-contract/seven-clients.yaml.inactive)
is intentionally not a Kubernetes manifest or ready-to-send Admin API payload.
It records Keycloak 26.8.2, fixed realm/issuer, exact confidential Code + S256
clients, empty default client scopes and explicit optional scopes, three groups,
ID-token-only full-path group membership, and existing SSM/ESO reference names.
It contains no actual credential, owner identity, user, default-group membership,
flow graph, execution ID or new public route. `openid` is the OIDC request scope,
not a fabricated Keycloak client-scope object. Argo and the four generic edges
may request the existing built-in `profile` scope; Grafana requests only
`openid groups` and must have no inherited profile/email default mappers.

## Create-only versus update and rotation

- Preserve the historical [one-client disabled RealmImport](../../examples/keycloak-preparation/realm-import.yaml.inactive)
  and its six inactive-manifest regression tests. It is a create-only seed, not
  an updater. The separate contract lives in a subdirectory so the existing
  manifest inventory still means exactly six Kubernetes examples.
- Before any future operation the parent privately reads the exact realm/client
  IDs and effective configuration using the supported 26.8.2 Admin API or console.
  Determine whether creation or update is needed. Do not reapply RealmImport to
  update an existing realm, create seven additional live clients, or rotate secrets.
- The parent performs separately authorized, bounded Admin API/console changes
  while all service clients stay disabled, then reads back the exact targets.
  Check callbacks/origins, Code + S256, all disabled alternate grants, signing,
  effective default/optional scopes and all inherited/client-level mappers.
- Only the parent resolves credential material from the named existing SSM/ESO
  references. Contract `existingESORef` is a reference in its consumer namespace,
  not a cross-namespace RealmImport placeholder or a new keycloak-namespace reader.
  It does not prove that a parameter or target exists or is Ready. No new Store,
  IAM grant, copied Secret or credential value is supplied by this source.
- Rotation must coordinate the IdP client credential and consumer's approved
  source reference, then verify exact state and old-credential rejection. ESO
  refresh alone does not change Keycloak. Orphan/Retain deletion or a failed ESO
  refresh can leave the old credential usable; neither proves revocation.
- Read back the groups mapper and issued signed ID-token shape privately. The
  pinned mapper forces multivalued group strings; full paths are mandatory.
  Check no groups claim in access tokens, userinfo, introspection or lightweight
  access tokens. Do not guess unsupported JSON-type mapper fields.

## Controlled enrollment, parent-owned and human-operated

All boxes below are pending source instructions, not completed evidence.

- [ ] Parent obtains the one genuinely missing human input: the new owner's
  login ID. Display name is optional. Never request a password, credential seed,
  recovery code, private key, exact subject or private mapping expression in chat.
- [ ] Confirm the intended person is the existing application owner. Keep all
  seven service clients disabled and all consumer legacy paths unchanged.
- [ ] Use the parent's existing private HTTPS `sso.kkamji.net` origin through the
  private management Gateway, not a new hostname, public admin route, global
  Backend enablement or weakened TLS. Open only the realm access necessary for
  the controlled ceremony. Keep public registration and reset-password disabled;
  do not create users, groups, default admins or default memberships automatically.
- [ ] Clone the actual built-in Browser flow from this server version; privately
  export and review the real graph/execution IDs and effective realm/client
  bindings before release. Do not invent IDs or rely on a `REQUIRED` label alone.
  Preserve the intent: Username Password Form REQUIRED, Conditional 2FA subflow
  REQUIRED, WebAuthn REQUIRED; OTP and recovery-code executions DISABLED.
  WebAuthn RP ID is `sso.kkamji.net`, user verification is required, integrated
  passwordless passkeys are off. Do not add a weaker TOTP alternative.
- [ ] Review every alternative entry and session-cookie bypass, including existing
  SSO sessions, Forms/cookie ordering, registration actions, client overrides,
  direct grants, reset/recovery, federation/brokers and account-console behavior.
  Revoke inappropriate old sessions. Required WebAuthn can invite an unenrolled
  password holder to enroll; it is not by itself deny-unenrolled or a proven
  fresh-WebAuthn-per-request policy. Stop release if the exported effective graph
  or any bypass cannot be explained and negatively tested.
- [ ] The owner personally completes private initial login/password setup and
  real WebAuthn user verification. Register an independent backup/recovery
  credential under the same reviewed strong-factor policy, without enabling OTP
  or recovery-code executions. Prove loss/recovery/revocation with the owner;
  source flags, an agent or an unrelated Google/AWS login cannot substitute.
- [ ] After same-owner confirmation the parent privately derives the exact opaque
  issuer/subject pair. Assign only that owner to `/argocd-admins`,
  `/grafana-admins`, `/homelab-admins`; never make membership default. No
  `email_verified` spoofing, name/email/GitHub inference or email-only admin link.
- [ ] Parent derives the private Grafana predicates from trusted readback, mapping
  to the SAME existing login, numeric user ID, UID, organization, permissions and
  ownership. Do not create/relabel an account to make the test pass. Keep actual
  subject/login/ID/predicate values out of Git, reports and tool diagnostics.
- [ ] Parent validates strong-factor success and absent/cancelled-factor,
  unjoined-user, wrong issuer/audience/subject, direct-grant, stale cookie,
  callback/state replay/expiry, recovery and IdP-outage denials. Actual off-host
  populated owner/MFA restore, TLS/log privacy, UI7, revoke and native machine
  auth tests remain runtime gates. The accepted storage migration is not reopened.
- [ ] Only after separate parent decisions may an individual service client and
  its controlled consumer canary be opened. Acknowledgements do not prove TLS,
  log privacy, identity, enrollment, recovery or any runtime acceptance.

Hindsight here means the native Hindsight UI. Independent Hindsight-dot Google
OAuth, private epoch/DCR/Redis storage and native API/client-key auth are not
changed and cannot provide Keycloak owner evidence. See the
[consumer composition plan](02_consumer-sso-plan.md) for per-app exclusions and
[private HTTPS contract](04_private-admin-https.md) for the existing access boundary.

## Fixed primary-source contracts

- [Keycloak 26.8.2 group membership mapper](https://github.com/keycloak/keycloak/blob/26.8.2/services/src/main/java/org/keycloak/protocol/oidc/mappers/GroupMembershipMapper.java)
- [Keycloak 26.8.2 token inclusion keys](https://github.com/keycloak/keycloak/blob/26.8.2/services/src/main/java/org/keycloak/protocol/oidc/mappers/OIDCAttributeMapperHelper.java)
- The existing vendored 26.8.2 RealmImport schema and
  [manual built-in flow gate](../../examples/keycloak-preparation/README.md#disabled-realmclient-and-mfa-activation-gates)
  remain the local source contract. No flow is implemented or bound by this task.
