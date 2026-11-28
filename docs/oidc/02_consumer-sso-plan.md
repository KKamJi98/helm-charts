---
title: Staged Keycloak consumer SSO
updated: 2026-11-29
type: architecture
status: current
---

# Staged Keycloak consumer SSO

## Monitoring alert-only regression update

2026-11-27 local candidate: [Job failure recovery exception](../rules/job-failure-alerts.md)
relocates only `KubeJobFailed` and changes its expression. Normal local render
counts become 132/142 (without/with CRDs). Only monitoring whole-object/raw
counts and hashes are rebased after exact full-render comparison against
`fc09262727ab1cd6e6bd9f7247166a70f8b601e2`; Grafana Deployment/Pod hashes,
storage/crypto/sidecar guards, default profile and immutable `main9a.json` stay
unchanged. This does not reopen storage, SSO or runtime acceptance.

2026-11-29 coupling note: Hindsight opt-in bidirectional `retain_summary` and isolated
`grokMemory` templates (`charts/hindsight/`) leave Keycloak consumer SSO routes,
OIDC clients, and default `kkamji_local_values.yaml` renders unchanged.

## Scope and current state

This is an offline source candidate for the six active non-Platform human UIs.
It does not assert that Keycloak, realm clients, credentials, SSM parameters or
ESO targets exist. The issuer is exactly
`https://sso.kkamji.net/realms/kkamji`, without a trailing slash.
The Platform client is a provisioning contract only here; its code is owned separately.
No cluster, cloud, browser, user database or real Secret was accessed for this change.

Pins are unchanged: Argo CD chart 10.10.5 / app v3.5.5,
kube-prometheus-stack 92.3.0 / Grafana 13.2.3-distroless pin,
Cilium 1.19.3, Hindsight 1.1.0 and Envoy Gateway 1.8.1.
Do not upgrade or reformat vendor archives to enable this candidate.

All wrapper defaults remain `legacy`. The immutable current-main baseline is
`9a2e266300e72cfd6e1ece62a2897a73780aa603`, not the older consumer WIP.
Normal local values render the same objects: 68 Argo, 54 Cilium, 28 native
Hindsight and 131 monitoring objects (`--skip-tests`), or 141 monitoring objects
with `--include-crds`. Full-object hashes, fixed storage guards and the previous
immutable storage/crypto/sidecar oracles remain regression requirements.

The [Moka recall connection](../03_hindsight.md#모카chatgpt-읽기-전용-recall-연동)
is separate from this Keycloak migration. Its Hindsight Application overlay adds
the Moka OAuth companion resources, exact-path public OAuth routes, a
recall-only API extension and a Secure MCP Tunnel sidecar that serves OAuth
discovery for the public hindsight.kkamji.net origin only. Client registration
accepts only ChatGPT's documented OAuth callback URIs. It does not change the Hindsight UI login, the native
API/MCP key checks, or any Keycloak realm, client, policy, or credential. The
original Hindsight local values still render the native baseline without the
opt-in Moka overlay.

The Hindsight LLM concurrency value (`runtime.llmMaxConcurrent`,
[runbook](../03_hindsight.md#llm-동시-호출-2026-11-21)) changes one environment
variable of the API container. The Hindsight object count in the oracle, the UI
login, the routes and every Keycloak object are unchanged. Because the API
StatefulSet differs by that one value, the Hindsight entry of the render oracle
(`tests/fixtures/keycloak-consumers/main9a.json`) was re-baselined in the same
change; the other three charts keep the hashes captured at the recorded base.
The retain reasoning effort value (`runtime.retainReasoningEffort`,
[runbook](../03_hindsight.md#retain-추출-reasoning-effort-2026-11-22)) sets one
environment variable on the same container (initially `medium`, later raised to
`high`) and re-baselines the same entry; nothing else in the oracle moves.
The Hindsight model value (`runtime.model` in the local values,
[runbook](../03_hindsight.md#llm-model-gpt-62-sol-2026-11-22)) changes the value of
one existing environment variable of that container, so the same entry is
re-baselined once more; the object count and every other chart are unchanged.
Adding `wsl_agy` and `mac_agy` to the `hindsight-gateway-client-keys`
ExternalSecret updates only that one ExternalSecret object in the Hindsight
render, so the same entry is re-baselined again; the object count, UI login,
routes and every other chart remain unchanged.
On 2026-11-23, homelab non-HA, Istio Ambient Mode compatibility, and resource right-sizing
([Homelab Kubernetes resource and non-HA optimization](../07_homelab-resource-optimization.md))
re-baselined the `argocd` (68 -> 63 objects: unused Dex removed, ApplicationSet
scaled to 0, controller/repo/server/redis/notifications resources bounded),
`cilium` (54 -> 52 objects: single worker-only operator, `debug=false`,
`bgpControlPlane=false`, `cni.exclusive=false`, `socketLB.hostNamespaceOnly=true`,
`bpf.masquerade=false`, `installNoConntrackIptablesRules=false`, operator/Hubble
resources bounded), and `hindsight`
(30 objects: API CPU req `1 -> 150m`, mem limit `6Gi -> 4Gi`, control-plane
`100m/256Mi -> 10m/96Mi`), and `kube-prometheus-stack` (131 / 141 objects:
Alertmanager `5m/80Mi` lim `192Mi`, Prometheus `25m/768Mi` lim `1536Mi`,
`kubeApiServer` unused high-cardinality histogram bucket drop, and removal of
legacy Istio sidecar `envoy-stats` scrape job after [Ambient Mode cutover](../08_istio-ambient-mesh.md))
entries in `tests/fixtures/keycloak-consumers/main9a.json` using verified Helm 4.2.1.
No Keycloak realm, client, SSO switch, Gateway route, Grafana deployment/PVC, or
`storageGuardSha256` oracle changed.

Grafana's parent-accepted native retained PVC, one replica, Recreate with
`rollingUpdate: null`, fixed existingClaim/local-path/RWO/10Gi, disabled chown and
`Prune=false,Delete=false` are preserved. Older emptyDir/no-production prose is
historical and does not reopen the completed storage migration. Authentication
still remains legacy. All Grafana source acknowledgement flags remain false;
no storage fact grants owner/MFA, log privacy or consumer cutover acceptance.
The JWT overlay's config checksum and two private Secret env refs change the Pod
when eventually selected. This source stage selects no active overlay/root.

The separate [seven-client source contract](../../examples/keycloak-preparation/consumer-contract/seven-clients.yaml.inactive)
and [controlled owner-enrollment checklist](07_owner-enrollment-source.md) add no
live realm/user/client or flow implementation. The original one-client create-only
seed is preserved. Existing realms and client rotation require supported Admin
API/console update and exact readback, not RealmImport reapply or ESO refresh.

## Seven-client provisioning contract

All clients are distinct confidential clients. Use Authorization Code Flow,
require PKCE `S256`, disable implicit flow, direct grants and service accounts,
and register only the exact HTTPS callback below. No wildcard redirect URI or
wildcard web origin is needed. No consumer needs a `.kkamji.net` cookie Domain.
Do not enable the clients before owner enrollment, recovery and IdP policy tests.

| Client ID | Consumer namespace | Exact callback | Requested scopes | Admission |
|---|---|---|---|---|
| `argocd` | `argocd` | `https://argocd.kkamji.net/auth/callback` | `openid profile groups` | `/argocd-admins` -> `role:admin`; default `role:no-access` |
| `grafana` | `monitoring` | `https://grafana.kkamji.net/oauth2/keycloak-callback` | `openid groups` | signed `/grafana-admins` + private verified owner subject; preserve existing user/roles |
| `hindsight-ui` | `hindsight` | `https://hindsight.kkamji.net/oauth2/keycloak-callback` | `openid profile groups` | signed `groups` contains exact `/homelab-admins` |
| `hubble` | `kube-system` | `https://hubble.kkamji.net/oauth2/keycloak-callback` | `openid profile groups` | signed `groups` contains exact `/homelab-admins` |
| `prometheus` | `monitoring` | `https://prometheus.kkamji.net/oauth2/keycloak-callback` | `openid profile groups` | signed `groups` contains exact `/homelab-admins` |
| `alertmanager` | `monitoring` | `https://alertmanager.kkamji.net/oauth2/keycloak-callback` | `openid profile groups` | signed `groups` contains exact `/homelab-admins` |
| `kkamji-platform` | parent-owned | `https://platform.kkamji.net/api/auth/oidc/callback` | `openid` initially | parent-owned exact issuer + subject allowlist |

Platform's proposed post-logout redirect is
`https://platform.kkamji.net/login`. This worker does not implement Platform or
register that redirect. Edge logout is local `/oauth2/keycloak-logout`, not a
claim of realm-wide logout. Do not add wildcard post-logout URIs or put ID tokens
in logout URLs. Native Argo/Grafana global logout is a separate acceptance item.

For the six consumers, attach an optional OIDC client scope named `groups`
(`protocol=openid-connect`) and request it as shown. In that scope use a
`oidc-group-membership-mapper` protocol mapper with:

- `claim.name=groups`, `full.path=true`, `id.token.claim=true`.
- `access.token.claim=false`, `userinfo.token.claim=false`.
- A JSON array of full group paths in the **signed ID token**, not a string,
  email-domain rule, request header or arbitrary realm role.
- Only the owner is joined to `/argocd-admins`, `/grafana-admins` and
  `/homelab-admins`. Do not assign these groups to realm defaults.

Keycloak's normal signed ID token supplies exact `iss`, per-client `aud`, stable
`sub`, `exp` and `typ=ID`. Verify the issued token's actual shape before enabling
a consumer; do not invent a subject or mark an email verified to make linking work.
Grafana requests no profile/email scope. Its client must also remove profile/email
from **default client scopes**: merely omitting them from a request does not disable
default mappers. The Lua guard rejects name/email/profile claims before they can
rewrite the existing owner. Platform does not require the groups scope under its contract.

### PKCE evidence and limits

- Argo CD v3.5.5 supports `enablePKCEAuthentication: true` in its native OIDC config;
  its implementation uses `oauth2.S256ChallengeOption` and a server-side verifier.
- Grafana v2 uses Gateway OIDC for S256 and Grafana native JWT for the final
  verified identity. Generic OAuth is disabled, not a fallback. Its signature-only
  first-callback verifier was insufficient for mandatory expiry validation.
- Envoy Gateway 1.8.1 pins Envoy **v1.38.1** by its own API defaults. That Envoy
  OAuth2 filter generates a verifier/challenge, sends `S256` and exchanges the
  verifier. There is no invented `oidc.pkce` SecurityPolicy field. The pinned
  Gateway schema supports OIDC + cookie-extracted JWT + StringArray authorization.
- Argo interactive CLI SSO is not proven by the confidential browser client.
  If needed, the parent must separately assess Argo's public CLI client contract;
  existing machine-token CLI authentication is not rewritten here.
- Platform's S256 requirement belongs to its separate implementation/contract;
  this worker has not verified its running RP.

The edge filter order is OAuth2/OIDC, JWT authentication, then authorization.
Envoy decrypts the encrypted session-token cookie before the JWT filter reads it.
The candidate keeps token encryption enabled; it does not weaken this to make
JWT extraction work. JWT validates signature, issuer, audience and token lifetime;
authorization consumes the verified provider metadata, not forwarded headers.

## Credentials and retention

Each of the six consumer ExternalSecrets uses existing `parameter-store`,
`data[].remoteRef.key=/kkamji/keycloak/clients/<client-id>`,
`remoteRef.property=client_secret`, and target
`<client-id>-keycloak-oidc` with key `client-secret`.
Targets are Opaque, `creationPolicy: Orphan`, `deletionPolicy: Retain`.
The parent provisions each dedicated SSM SecureString JSON; no values are in source.
The Platform client has its own parent-owned credential mapping.

Argo CD reads `$argocd-keycloak-oidc:client-secret`; its target Secret template
sets `app.kubernetes.io/part-of=argocd`, required by the pinned settings selector.
It does not merge this credential into `argocd-secret` or rotate its signing key.
Grafana no longer receives the OIDC client secret in its application environment;
Gateway consumes that dedicated Secret. The separate
`/kkamji/keycloak/consumers/grafana` SecureString JSON exposes only properties
`username_attribute_path` and `expect_claims` to `grafana-keycloak-identity`,
Opaque/Orphan/Retain. Custom `KEYCLOAK_GRAFANA_*` env refs and `$__env{...}`
INI expansion avoid logging private predicates as `GF_*` startup overrides.
Existing admin inputs remain unchanged.
All old Google, Hindsight native/per-client API, shared BasicAuth and admin
ExternalSecrets remain available for deliberate rollback; nothing deletes or replaces them.
Orphan/Retain also means deleting an ExternalSecret is **not** credential revocation.

## Rollout switches

No active Application root is edited here. The parent must explicitly select the
overlay/value changes in each Application after runtime prerequisite readback.
Always compose the chart's `kkamji_local_values.yaml` first.

### Argo CD native OIDC

- Default: `keycloakSSO.mode=legacy`, no new SSO resources.
- Canary (active in `management_local_values.yaml` since 2026-11-24 R5): append `charts/argocd/keycloak-canary-values.yaml`.
  Admin recovery remains enabled, native Keycloak is available, group RBAC is
  fail-closed, anonymous access is off and issuer TLS verification is on.
- Final: additionally append `keycloak-only-values.yaml` and set
  `keycloakSSO.adminTokenMigrationConfirmed=true` only after the parent confirms
  owner login, recovery and machine-token dependencies. This disables `admin`.
  Other local `accounts.*` entries with `login` capability are rejected in final
  mode; retain `apiKey`-only machine accounts and project tokens as appropriate.

Disabling an account can affect its existing machine tokens. This worker cannot
inspect live Argo accounts/tokens. No in-repo Argo admin-token consumer was found
in the scoped source scan, but that is not a live dependency inventory. Audit and
migrate any admin-dependent automation before final approval. Keep webhook
credentials and API/project tokens intact; do not rotate the signing key to log out people.
The upstream Argo chart checksums the CM in workloads, so native auth changes can
roll Argo components; this is not presented as a no-restart runtime change.

### Grafana v2: Gateway OIDC/cookie JWT, native Lua and Grafana JWT

The other five consumers retain v1 behavior. Grafana's normal defaults remain
`keycloakSSO.grafana.mode=legacy`. This v2 replaces only its Generic OAuth candidate.
There is no auth proxy, extra image/controller or unsupported DB pre-bind.

- Canary: append `charts/kube-prometheus-stack/keycloak-canary-values.yaml`.
  Parent must acknowledge `keycloakSSO.backendTLSReady=true`,
  `keycloakSSO.grafana.dataPreservationReady=true` and
  `keycloakSSO.grafana.accessLogsSafe=true` only after actual prerequisite readback.
  Auth changes replace the Pod: preserve the already accepted PVC/data baseline;
  actual owner/log/TLS prerequisites remain separate and closed in source.
- Final: append `keycloak-only-values.yaml` as well and set
  `keycloakSSO.grafana.cutoverApproved=true` only after owner SSO, recovery,
  same-user data preservation, machine clients and old human-session revocation.
  A flag is an acknowledgement, not proof produced by Helm.
- Rollback to legacy requires removing the JWT overlays, not only overriding mode.
  Existing old credential inputs remain; no signing key or admin password is rotated.

#### Canary retains the actual normal public password path

The canary is a separate same-host HTTPRoute matching exact header
`X-KKamJi-SSO-Canary: grafana` with path prefix `/`. The ordinary route stays
outside OIDC and preserves existing form/password and session behavior, while
stripping spoofed JWT/proxy headers. No new hostname, root URL change, path prefix
mount or URLRewrite is introduced. The selector is not secret or an identity claim;
selecting it chooses the stricter SSO route while legacy remains intentionally available.

The parent's controlled Aside browser must supply that header on **every Grafana
request**, including top-level navigation, the exact callback, assets, fetch/XHR,
redirects and WebSocket handshakes. Apply it only to the Grafana origin; it is not
required on the IdP origin. If that browser capability cannot be proved, stop this
canary path rather than silently making the normal route mandatory OIDC.
A callback missing the header does not prove SSO: it reaches the legacy app instead.

Lua mutations can clear Envoy's route cache. The script therefore preserves this
routing selector until the canary route's router-stage HeaderModifier removes it.
Removing it inside Lua would reselect legacy and strip the validated JWT. Final
public Basic denial is likewise a separate direct-response HTTPRoute with no
OIDC/Lua attachment, so mutation cannot turn that denial into a backend request.

#### Verified metadata and minimal Lua guard

Gateway OIDC scopes are exactly `openid groups`; callback is exactly
`https://grafana.kkamji.net/oauth2/keycloak-callback`. The host-only encrypted
ID-token cookie is `GrafanaKeycloakIdToken`. No schema-only `forwardIDToken`
feature, cookie Domain or auth-header passthrough is used.

The pinned translator preserves provider `p.Name` and sets `PayloadInMetadata`
to that name. The script reads only
`envoy.filters.http.jwt_authn["grafana-keycloak-owner"]`, not caller headers.
Pinned ordering is OAuth2 8, JWT 9, Lua slot 12 and RBAC 301. Runtime xDS/filter
order and encrypted-cookie decryption still require parent readback.

`files/grafana-keycloak.lua` is only transport plus presence/literal guards:

- Require finite numeric exp/iat, exact issuer, a single grafana audience,
  Keycloak typ=ID, nonempty string sub, typed exact admin-group membership and
  exact azp=grafana. No JWT decoding, signatures, clock logic or cjson/module.
- Reject profile fields (including name/email) before native JWT/UserSync can
  rewrite existing attributes. Parent must configure the client without default
  profile/email scopes; any unexpected profile claim fails closed.
- Remove caller token/proxy headers, Cookie and Authorization, then copy exactly
  one compact decrypted ID-token cookie into `X-Grafana-Keycloak-Id-Token`.
  The browser retains its Gateway cookies; none is sent to Grafana for fallback.
- OAuth canonicalizes cookie names into a map before Lua. A more-specific raw
  Cookie direct-response route therefore rejects duplicate target cookies and
  combined-header comma ambiguity **before** OAuth normalization. The script's
  additional count check protects the post-OAuth input. Neither reject route
  has a SecurityPolicy/EnvoyExtensionPolicy attached.
- Do not log claims, headers, cookies or tokens; denials contain only fixed text.

#### CSRF boundary for cookie-to-header transport

The Gateway consumes browser cookies and forwards the verified JWT in a dedicated
header. Grafana must therefore set `security.csrf_always_check=true`; its pinned
native middleware otherwise skips Origin checks when the Grafana login cookie is
absent. Keep `csrf_trusted_origins` and `csrf_additional_headers` empty. The chart
rejects disabling these checks or shadowing them with `GF_SECURITY_CSRF_*` inputs.

Browser requests retain Origin for native same-host validation. The separate Bearer
machine route preserves Authorization but removes Cookie, identity inputs and
Origin. A valid native machine credential does not acquire a browser-cookie Origin
constraint, and an invalid Bearer cannot fall back to the removed browser session.
No new auth-proxy trust or arbitrary trusted Origin is introduced.

The parent regression observed missing protection RED before adding the settings,
and machine-Origin sanitation RED before adding that filter. The exact pinned
Grafana CSRF middleware and host parser passed 24 component HTTP-shape cases across
the frozen pre-fix security profile and actual rendered canary/final INI. The
next-handler marker is synthetic: these checks do not claim running Grafana,
real-token authorization or live browser/callback acceptance.
Primary source: https://github.com/grafana/grafana/blob/v13.2.3/pkg/middleware/csrf/csrf.go

#### Private explicit owner mapping; preserve the existing user

No actual owner subject, login or UID belongs in Git. Parent supplies this exact
SSM JSON input path and properties after verifying the IdP subject and existing
Grafana owner metadata, without email linking or changing email_verified:

```text
/kkamji/keycloak/consumers/grafana
  username_attribute_path: <JMESPath string returning the unchanged existing login>
  expect_claims: <JSON object encoded as a string, not a nested mapping>
```

The username predicate must require numeric exp/iat, exact issuer/verified owner
sub, one approved client audience, exact azp=grafana, typ=ID and typed exact
`/grafana-admins`, returning only the existing owner's unchanged login.
The expect_claims JSON must bind exact issuer, grafana audience, verified sub, Keycloak type and azp=grafana. It must not contain a static pretend current-time check. Parent
must test the actual private expressions and verify the resolved **same numeric
user ID**, UID, login, org/admin roles, email/name, preferences and ownership.
A conflicting existing `(jwt, sub)` association or protected/provisioned user is
a gate, not a reason to disable protection or invent a DB migration.

Grafana native JWT clears username_claim/email_claim/email_attribute_path before
reading the private username expression. Both native pinned defaults and a prior
sub/email-selector layer were exercised with actual ini.v1, Grafana's expander
and readAuthJWTSettings logic. Missing private mapping does not fall back to sub
or email. The custom env names are not `GF_*`; bulk or conflicting GF auth/server
environment overrides are rejected by the wrapper.

`auto_sign_up=false`, `url_login=false`, `skip_org_role_sync=true`, no group/team
sync and `allow_assign_grafana_admin=false` preserve the existing account rather
than create or privilege another realm user. Header auth.proxy, anonymous and
Generic OAuth are off. Only the fixed HTTPS JWKS is trusted, with TLS verification.
The native validator checks signature and exp/nbf/iat with its clock tolerance;
required-time presence is separately enforced by Lua/private predicates because
the registered-claims validator alone permits missing dates. Pinned Keycloak 26.8.2 sets issuedFor(client ID) on the access token and copies it
to the ID token azp; absent/null azp is rejected rather than silently treated as absent.
No OIDC nonce is
requested; optional Code Flow nonce absence is not a replay finding.

The exact owner sub is **not claimed to be in public Gateway policy**: signed,
owner-only-provisioned group membership is checked at Gateway and private native
expect_claims/predicate checks the subject before user lookup. A wrong subject
cannot become an owner through old session/Basic fallback: strict browser traffic
has no Cookie/Authorization, and final mode unregisters the form client. Old human
sessions must still be revoked and real negative tests performed by the parent.

#### Preserve machine identities and close only human legacy paths

Both reload sidecars retain their exact `grafana-auth` refs and call localhost:3000
with Basic. `auth.basic=true` and `auth.disable_login=false` stay in place.
Final `disable_login_form=true` unregisters the native form client; public Basic
receives a separate 403 direct response. No admin password, signing key or token
is rotated. Public Basic `api_key` transport, if used, must be migrated to Bearer
with the same token before final mode; do not silently claim that transport survives.

A separate machine HTTPRoute matches native case-sensitive `Authorization:
Bearer <nonempty token>` on `/api` and `/apis` (the latter preserves v13's unified
API). It has no browser policy or Lua. It strips Cookie and all new JWT/proxy
identity headers but preserves Authorization. No token-format regex beyond the
actual native prefix is imposed. Thus fake Bearer + old session cookie cannot
fall through to the owner, while valid native service/API tokens retain their
own principal. This separation is mandatory because native JWT priority 20 is
before service-token priority 30; injecting the owner's ID token into machine
requests would substitute the owner principal. Native token-store validation and
actual sidecar reload/metrics/client workflows remain parent runtime tests.

#### Logging is an explicit shared-runtime prerequisite

The Lua script never logs values and Grafana router_logging is false. The owned
v1.8.1 BackendTrafficPolicy API has no access-log override; this chart does not
invent one or alter the parent-owned EnvoyProxy. Before accessLogsSafe, parent must
verify the shared access log format excludes query/Authorization/Cookie/JWT and
identity headers/metadata, including callback code/state. Also inspect data-plane
application logs: pinned Envoy's decrypt-error path can log the encrypted cookie
at error level. Do not run real malformed-cookie tests until that logging boundary
is safe. Grafana's pinned request middleware also still emits non-200/304
completion records when router_logging=false; that flag is not a universal access
log switch. Parent must cover authenticated request context and Referer/error
records as well. Its log level "critical" aliases "error", not "off"; this chart
introduces no unsupported suppression setting. If strict zero-userinfo logging
cannot be met with approved runtime controls, keep the logging gate closed and
resolve that concrete acceptance blocker. The flag and synthetic no-logging test
are not live log-redaction proof.

### Four native Gateway edge UIs

- Hubble: `charts/cilium`, `keycloakSSO.mode=legacy|canary|only`.
- Hindsight UI: `charts/hindsight`, same switch; `exposure.enabled=false` stays off.
- Prometheus/Alertmanager: `charts/kube-prometheus-stack`, independent
  `keycloakSSO.prometheus.mode` and `keycloakSSO.alertmanager.mode` switches.

Every non-legacy edge mode additionally requires `keycloakSSO.backendTLSReady=true`.
This is a parent readback acknowledgement, **not evidence produced by Helm**.

Canary adds only `/sso-canary` (prefix stripped), exact
`/oauth2/keycloak-callback` and `/oauth2/keycloak-logout` on the existing hostname.
The legacy main route and its old policy are unchanged. This proves the Gateway
auth boundary; apps with absolute assets/redirects can return to their legacy main
route, so it is not full-UI cutover proof. No wildcard host or disabled app is added.

Final retargets the Keycloak policy to the existing human route, removes only its
legacy Basic/Google policy, and removes the canary route. Cookies are host-only
with explicit distinct ID-token names. JWT extracts **only that cookie**;
`optional=false`, exact issuer/client audience, deny-by-default and exact signed
group authorization remain mandatory. Token/header forwarding and auth-header
passthrough are off. Forged identity headers are removed on UI backend requests.
There is no automatic legacy fallback when the IdP is down.

### Strict upstream TLS prerequisite

Grafana uses the same prerequisite as the four edge UIs below.
The pinned Gateway's URL-only `buildXdsUpstreamTLSSocket` sets a trusted CA and SNI
but **does not set a SAN matcher**. Do not call that full hostname verification.
Instead, the candidate creates a namespaced native `Backend` per edge client with
FQDN `sso.kkamji.net:443`, `tls.sni=sso.kkamji.net`, system CAs and
`insecureSkipVerify=false`. Both OIDC token exchange and remote JWKS reference it.
Static exact auth/token endpoints avoid relying on provider-discovered replacements.
The pinned full Backend TLS translator emits the exact DNS SAN matcher from SNI.

The parent must enable/read back the shared controller setting
`gateway-helm.config.envoyGateway.extensionApis.enableBackend=true`, ensure the
Backend CRD is installed/served, then inspect Accepted/ResolvedRefs and actual xDS
SAN validation. That shared chart is intentionally outside this worker's scope.
Wrong-CA and wrong-host certificates must fail runtime tests before marking
`backendTLSReady`. Do not remove Backend refs or disable TLS checks to work around
a missing platform capability. PKCE and signed-group support themselves are present;
no oauth2-proxy or new authentication bypass is needed.

## Machine/API and data boundaries

- `hindsight-api` HTTPRoute and `hindsight-api-owner` SecurityPolicy are unchanged:
  `/v1` and `/mcp` continue using the existing per-client edge key plus native
  Authorization policy. They are never targeted by browser OIDC. Native SSM refs,
  bearer handling, client-key extraction, native auth env and control-plane API
  access are unchanged. The control plane's existing native UI access-key gate
  is also retained inside the new browser boundary, not weakened or removed.
- No Service, scrape target, ServiceMonitor/PodMonitor, Prometheus/Alertmanager
  object, webhook credential, Hubble gRPC service or API token is rewritten for SSO.
- Internal Prometheus/Alertmanager APIs and scrapes retain their Service paths.
  Public callers using the old shared BasicAuth require a parent dependency audit
  before final mode; the source worker cannot establish that no such callers exist.
- Preservation of the accepted Grafana PVC/data baseline, private native-JWT owner mapping, legacy-session
  revocation and backup are parent-owned gates, not accomplished by an auth values file.

## Offline verification and runtime gates

Observed RED/GREEN covers the v1 edge contracts and v2 native JWT/Secret refs,
Lua bridge and Gateway routes. Negative Lua/route characterization includes controlled
missing-iat and selector-removal mutations. Actual LuaJIT 5.1-compatible tests use
realistic Envoy handle mocks; standalone Go checks use the pinned native temporal
validator, INI/env parsing, JMESPath and RE2, not a fake running Grafana server. The focused suite renders actual charts, checks Grafana private property refs, checks wrong issuer/group/callback/TLS/final-mode guards, machine exclusions,
Secret refs and the actual pinned SecurityPolicy/Backend/HTTPRouteFilter/EnvoyExtensionPolicy schemas.
Unknown CRD fields are rejected, including a deliberately invented `oidc.enablePKCE`.
This structural check is not Kubernetes CEL, controller translation or browser proof.

```bash
# HELM must resolve to the parent's verified Helm 4.2.1 binary.
HELM=/path/to/helm-v4.2.1/helm HELM_BIN=/path/to/helm-v4.2.1/helm uv run --no-project \
  --with pyyaml --with jsonschema --with jmespath --with lupa \
  python -m unittest discover -s tests -p "test_*keycloak*.py" -v
```

Earlier frozen-consumer evidence is historical and reused only where inputs are
unchanged. Current-main composition adds an immutable 9a render oracle and real
retained-PVC plus canary/final positive, negative and source-mutation tests.
Synthetic fixture acknowledgements are labeled as such, not parent acceptance.
The focused [consumer CI](../../.github/workflows/keycloak-consumer-lint.yml) runs
consumer/Grafana/composition/seven-client tests using the existing runner/tool
pins; the separate PVC workflow preserves the original storage regressions.
Safe logs, exact native exits and final candidate hashes belong to task evidence,
not Git. Index/coupling are integrated additively, but draft docs lint is static
only: final committed-HEAD `--base origin/main` freshness/coupling and independent
composition review remain parent gates. No source review is runtime acceptance.

Before final legacy disable, the parent still needs actual ESO/provider/client
readback, S256 traces, signed-claim shape, owner + MFA + recovery, unjoined-user
and wrong-token/header rejection, callback/state replay/expiry checks, IdP outage,
TLS failures, cookie scope/encryption/logout/session revocation and all six UI
workflows. Recheck native APIs, webhooks, Grafana sidecar reloads, service tokens,
scrapes and restored data after each canary/final transition. Runtime acceptance
cannot be inferred from offline renders, confirmation booleans or source tests.

## Primary pinned references

- [Argo CD v3.5.5 Keycloak setup](https://github.com/argoproj/argo-cd/blob/v3.5.5/docs/operator-manual/user-management/keycloak.md)
- [Argo CD v3.5.5 OIDC implementation](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/oidc/oidc.go)
- [Argo CD v3.5.5 settings and Secret selector](https://github.com/argoproj/argo-cd/blob/v3.5.5/util/settings/settings.go)
- [Grafana v13.2.3 Generic OAuth](https://github.com/grafana/grafana/blob/v13.2.3/docs/sources/setup-grafana/configure-access/configure-authentication/generic-oauth/index.md)
- [Grafana v13.2.3 signature validator](https://github.com/grafana/grafana/blob/v13.2.3/pkg/login/social/connectors/social_base.go)
- [Grafana v13.2.3 provider/role data sources](https://github.com/grafana/grafana/blob/v13.2.3/pkg/login/social/connectors/generic_oauth.go)
- [Grafana v13.2.3 native auth registration](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/authn/authnimpl/registration.go)
- [Gateway v1.8.1 OIDC translation](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/oidc.go)
- [Gateway v1.8.1 JWT and URL TLS helper](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/jwt.go)
- [Gateway v1.8.1 full Backend TLS/SAN translation](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/translator.go)
- [Gateway v1.8.1 filter ordering](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/httpfilters.go)
- [Gateway v1.8.1 signed-claim authorization](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/xds/translator/authorization.go)
- [Gateway v1.8.1 Backend enablement gate](https://github.com/envoyproxy/gateway/blob/v1.8.1/internal/gatewayapi/backend.go)
- [Gateway v1.8.1 default Envoy image pin](https://github.com/envoyproxy/gateway/blob/v1.8.1/api/v1alpha1/envoyproxy_types.go)
- [Envoy v1.38.1 OAuth2 PKCE and cookie decryption](https://github.com/envoyproxy/envoy/blob/v1.38.1/source/extensions/filters/http/oauth2/filter.cc)
- [Keycloak 26.8.2 group mapper](https://github.com/keycloak/keycloak/blob/26.8.2/services/src/main/java/org/keycloak/protocol/oidc/mappers/GroupMembershipMapper.java)
- [Keycloak 26.8.2 ID-token construction](https://github.com/keycloak/keycloak/blob/26.8.2/services/src/main/java/org/keycloak/protocol/oidc/TokenManager.java)

The vendored dependency templates/values and Gateway CRDs in this checkout are
the primary chart-field/schema references. Their archives and version pins are untouched.

## Grafana v2 additional primary references

- [Grafana 13.2.3 native JWT settings](https://github.com/grafana/grafana/blob/v13.2.3/pkg/setting/setting_jwt.go)
- [Grafana 13.2.3 native JWT client and selector precedence](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/authn/clients/jwt.go)
- [Grafana 13.2.3 JWT temporal and expected-claim validation](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/auth/jwt/validation.go)
- [Grafana 13.2.3 API-key Bearer parsing](https://github.com/grafana/grafana/blob/v13.2.3/pkg/services/authn/clients/api_key.go)
- [Grafana 13.2.3 config env expansion](https://github.com/grafana/grafana/blob/v13.2.3/pkg/setting/expanders.go)
- [Envoy 1.38.1 cookie map canonicalization](https://github.com/envoyproxy/envoy/blob/v1.38.1/source/common/http/utility.cc)
- [Envoy 1.38.1 Lua header/metadata API](https://github.com/envoyproxy/envoy/blob/v1.38.1/source/extensions/filters/http/lua/wrappers.cc)
- [Envoy 1.38.1 Lua route-cache behavior](https://github.com/envoyproxy/envoy/blob/v1.38.1/source/extensions/filters/http/lua/lua_filter.h)
