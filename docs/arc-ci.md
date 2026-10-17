---
title: Repository-scoped ARC rollout and evidence
updated: 2026-10-17T15:35:49+09:00
type: runbook
status: current
---

# Repository-scoped ARC rollout

The approved foundation/project stage was observed Synced/Healthy at revision
30401e13df849ce222ac63876baa6f2dcd2e0f3f. This revision enables the controller
after namespace/policy preparation. The owner completed direct secure input; exact SSM metadata was read back without
fetching values. Foundation auth is now Synced/Healthy and the canonical
ExternalSecret reports Ready/SecretSynced. The two light Application source flags
are enabled for the approved registration stage. Registration/listener readiness,
canary jobs and full CI remain separate runtime checks. BQL light canary39001288294 and Platform light canary39006129183 have actual
success evidence. Full original CI remains unverified and is not replaced by smoke.
Platform temporary trusted-branch trigger was restored to manual-only.

## Controller-first staging

The actual Argo CD umbrella must carry `argo-projects.projects.arc-ci`; the
standalone argo-projects local values are not imported automatically. The
umbrella project is enabled under the explicit initial CRD/RBAC/network/GitOps
approval. Existing projects and Argo CD
version/vendor remain unchanged.

The reusable foundation defaults `githubAuth.enabled=false`, so a default install
creates no ExternalSecret. Approved local values opt into authentication only
after the owner-input metadata and trust checks. After owner acceptance of the existing Store trust boundary,
explicit key choice and secure owner input metadata, confirm the arcSsmReuse
gates before enabling githubAuth and then repository scale sets. New IAM grants
are not an automatic prerequisite.
This separates control-plane activation from authentication/registration.
Foundation is already enabled. Controller activation is covered by the explicit
initial approval; both light scale sets now opt into the approved registration
stage after ESO Ready. A source change is not evidence of successful runner
registration or CI execution.

## Exact configuration

Chart0.15.0 controller and two repository scale sets use official OCI-verified
chart contents and digest-pinned images. Public digests are recorded in
`charts/arc-controller/oci-lock.json`. Helm's encoded token-scope request returned
403; the standard anonymous OCI bearer exchange succeeded without new credentials.
Manifest bytes and chart layers were SHA256-verified. Chart.yaml packaging changed
formatting only;39 chart files matched source or equivalent Chart metadata.

Namespaces are arc-system (one controller/two listeners) and ci-pr (job Pods and
registration Secrets). Controller watches only ci-pr. Four CRDs and namespaced
management Roles are required, with no ClusterRole. The management Roles can
create Pods/Secrets/serviceaccounts/Roles/RoleBindings in these namespaces;
this is sensitive persistent access. Job SA arc-light-job has no RoleBinding
and no mounted Kubernetes token. No Docker mode, host socket/mount/network or PVC.

Scale sets are kkamji-platform-light and binance-quant-lab-light, each min0/max1.
These settings alone allow two jobs. Shared ResourceQuota ci-pr/arc-job-budget
sets pods=1, imposing ONE non-terminal admitted job Pod across both sets.
Controller/listeners live outside that quota. Runner SA cannot create more Pods.
Quota-denied reconciliation must recover after completion/cancellation and fairness
is not guaranteed; validate both repos together before expanding. Workflow
concurrency groups do not coordinate repositories. Heavy CI is not routed here yet.

All components initially select k8s-w2. Controller request128Mi/limit256Mi,
each listener64Mi/128Mi, sole job256Mi/512Mi. Aggregate request512Mi/limit1024Mi,
CPU request450m/limit2. Job disk-backed emptyDir1536Mi, ephemeral-storage limit2Gi.
Jobs and listeners select arc-ci-nonpreempting with preemptionPolicy Never.
This opt-in PriorityClass has value0 and globalDefault=false; it cannot preempt
existing workloads and changes no other Pod priority. Restricted/v1.36 PSS remains.
The class is default-off in the reusable foundation chart and enabled only in
its local values. The arc-ci project adds only scheduling.k8s.io/PriorityClass.
Without the matching class, actual Priority admission rejected a standalone
Pod declaring Never; Helm rendering alone did not validate scheduling admission.
2026-10-15 observed w2 usage3010Mi/59%, allocatable5057Mi, requests2537Mi/50%.
Using aggregate limits leaves roughly1023Mi in that snapshot, not a peak guarantee.
Recheck MemoryPressure, peak service/host usage, and disk headroom before activation.
No VM changes are included. Heavy compilation requires a separately measured budget.

## Credentials and network approval

The user separately approved creation/installation of a private ARC GitHub App
on exactly the two repositories; saved permissions and selected repositories
were read back successfully. Administration read/write and Metadata read are
the only grants. No key generation/input, registration or CI was performed.
This completed approval does not authorize those later steps. Follow the
[GitHub App security review](arc-github-app.md) for the precise proposed grant,
shared-key authority, secure storage, rotation and recovery.

Canonical authentication is one SecureString JSON at `/kkamji/arc/github-app`
through the existing `parameter-store`. Both light sets reference
`ci-pr/arc-github-app-auth`; one App key is shared authority, not repository
credential isolation. Authentication remains off pending the owner Store trust,
key selection and secure-input metadata gates. No value is created or read by
this source change. Existing Store principal linkage must not be inferred from
its Secret reference alone. The ARC target uses Orphan/Retain to avoid owner
garbage collection; it does not expand IAM or create another reader/Store.

Policies default-deny both namespaces; DNS/GitHub/Actions/log-artifact destinations
are explicit Cilium FQDN rules. Only management Pods reach kube-apiserver; job
Pods deny host/remote-node/API. DNS/CDN/Service NAT enforcement needs canary
validation. No exchange, trading host, AWS metadata, npm or Maven job egress.
Node-level image pulls require GHCR reachability separately. No public service.

## Workload audit and migration boundary

Both repositories are private and currently use ubuntu-24.04 hosted runners.
Platform uses Java25/Gradle9.8.1, Node26.7.0, PostgreSQL Docker and image contract.
Its main image job publishes GHCR images/digests and triggers Argo CD; this is
excluded from the PR job pool and remains unchanged.

BQL source276e9a6 has four jobs: tier-a150min, tier-b240min,
source-qualification330min, release90min. Ubuntu26.04 Docker image pins Rust1.99.0.
Tier A sets cargo jobs2/test threads2, Tier B/qualification cargo jobs2; release
has no cargo-jobs cap. There is no Actions build cache or workflow concurrency.
Each job rebuilds the image and copies source to a fresh home. Qualification uses
archived8fa5646 Python oracle, CPython3.11.15 and pinned packages. Release builds
the listed CLIs and uploads SHA256SUMS/BUILDINFO for30days; it does not deploy.
No operational secret is referenced; permissions contents:read. Existing jobs
call host sysctl and disable container seccomp/AppArmor/systempaths for bwrap.
They CANNOT be moved unchanged to this restricted shared pool. No host sysctl,
privileged exception or fake test pass is approved. Rust offline harness forbids
exchange networking, but the existing job bootstrap downloads toolchains/packages.
Keep those phases distinct. Never start trading/protection/paper operational services.

Heavy migration must preserve bwrap/seccomp assertions using a reviewed isolated
execution environment, cap Cargo/Gradle/test workers, bound total memory, and
isolate repo/ref caches. Merely changing runs-on or removing failing sandbox tests
is not acceptable. The shared Pod quota remains the cross-repo admission gate;
if Kubernetes job hooks are later introduced, auxiliary Pods need a new quota design.

## Staged activation and rollback

1. Review exact CRDs/RBAC/PSS/Cilium policies and two credential grants with owner.
2. With the initial controller-only approval, wire/enable the actual umbrella arc-ci
   project and enable foundation with githubAuth=false, then controller. Verify
   namespaces, policies, quotas, CRDs and controller readiness; create no auth
   ExternalSecrets or runner registrations in this phase. After explicit secure
   authentication/registration approval and owner input, enable githubAuth,
   verify ESO metadata/Ready, and then enable each repository scale set.
3. Merge/enable separate manual canary workflows only after registration approval.
   Verify nonroot/no API token/no Docker socket and record runner identity/cgroups.
   Dispatch both and demonstrate only one non-terminal runner Pod, then cancellation
   and cleanup. This is canary evidence, NOT full CI success.
4. Independently approve the heavy-workflow migration and run every required
   workflow on ARC. Keep publisher/trading boundaries intact. Until then rollout
   is incomplete even when light canaries pass.

Rollback starts by min0/max0 on both sets, cancel/drain jobs and remove routing.
Keep controller alive for scale-set finalizers/runner deregistration, then disable
sets/controller. Revoke credentials through the secure owner flow. Do not blanket
delete namespaces, CRDs or shared ESO resources. Hosted fallback can still be
blocked by billing; do not change required-check policy to manufacture success.

## Evidence required before reporting complete

For EACH repo capture workflow name, run URL, commit, job id, runner name/labels,
ARC pod UID/node, image digest, requests/limits, peak memory/CPU/disk, outcome,
failure fixes and cleanup readback. Record light canary and full workflows
separately. GitHub-hosted success is not ARC success. No successful run exists yet.
Provide verified records to the separate blog owner; this change does not edit it.

## Historical preparation and limited diagnostic approval

The following capacity/queue notes originated before controller activation.
Subsequent controller and App installation evidence is recorded above; neither
is proof of ARC job execution. Full CI remains unexecuted.

A separate approval covers the opt-in class/project grant and one unregistered
ci-pr diagnostic Pod on the selected worker, at most180seconds/500mCPU/512Mi.
It overrides the runner command, uses the pinned official public base image,
mounts no API token/host path/socket or credential, and retains RuntimeDefault,
nonroot, drop ALL and no privilege escalation. Collect its exact exit/logs and
delete only that owned Pod. No registry publish, key creation/input, registration,
full CI, VM change or security-profile relaxation is included. Revalidate after
class synchronization; the old no-class server dry-run was correctly rejected.
A namespace primitive pass still does not qualify Docker, bwrap projection or CI.

### Shared quota behavior and recovery

Pinned upstream source1945b42820760eb50893c8da77fdfc42cf8dad45,
`controllers/actions.github.com/ephemeralrunner_controller.go:413-441`, explicitly
handles Forbidden errors containing `exceeded quota:`: retry after30seconds;
when the EphemeralRunner creation timestamp is over10minutes old, delete that
runner object so the set can recreate it. Other Forbidden errors become failures.
This quota path does not use the separate5/10/20/40/80second failed-Pod backoff.
Source evidence supports bounded scheduled retries, not a fair shared queue or a
guarantee against event-driven reconciliations. Long jobs can cause repeated
registration/object churn for the other repository. No dedicated quota test was
found in the inspected controller tests; no two-repository runtime test was run.

Keep pods=1 as a hard safety ceiling, not the production scheduling mechanism.
Initial controlled execution should admit one repository at a time, with the
other set min0/max0 through approved GitOps changes. For automatic full CI, either
provide measured capacity for each repo's one runner or separately design and
validate a fair cross-repository dispatcher. A shared GitHub concurrency string
does not coordinate repositories. Neither option is implemented or approved here.

Before automatic routing, test both dispatch orders, a job held beyond10minutes,
completion, cancellation while queued/running, and controller restart. Capture
Pod counts, quota usage, queue age, ARC events, runner registrations and controller
CPU/log rate. Acceptance requires both repos eventually execute, no overlapping
nonterminal job Pods, and no orphan registrations after cancellation. A test must
not be reported passed merely because quota rejected the second runner.

Recovery: stop new dispatch/routing, set both min0/max0 through GitOps, cancel the
queued run and drain the active run, retain the controller for finalizer cleanup,
then inspect quota used/hard, Pods, EphemeralRunners and GitHub runner metadata.
Only after cleanup and an explicit bounded rerun, enable one set. Do not raise
quota, force-remove finalizers, delete unrelated Pods or disable policies to make
the queue move. Stuck termination requires diagnosis, not assuming the budget is
free. Operational recovery writes still require the approved rollout scope.

Upstream references:
- [Pinned quota handling](https://github.com/actions/actions-runner-controller/blob/1945b42820760eb50893c8da77fdfc42cf8dad45/controllers/actions.github.com/ephemeralrunner_controller.go#L413)
- [Kubernetes quota semantics](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
- [GitHub routing and communication](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)

### Full CI stages and capacity candidates

These are initial profiling envelopes, not verified minimums. Job memory includes
all sidecars; add the controller/two-listener512Mi aggregate limit separately.
Limits must not be increased on the current worker without a fresh peak budget.
The last w2 snapshot has about2GiB unused before ARC overhead;4-8GiB jobs do not
fit that evidence. CPU purchase alone does not increase VM memory allocation.

| Stage | Candidate job CPU / RAM / scratch | Required implementation and evidence |
|---|---|---|
| Shell canary, gate, ci-ok | 1CPU /512Mi /2GiB | Canary only is prepared. Gate needs git/gh/jq and preserved check semantics. |
| Platform static | 1CPU /1GiB /4GiB | Preinstall pinned Python/Helm/git/gitleaks; put Helm setup before tests that invoke Helm; profile full-history scan. |
| Platform web | 2CPU /2GiB /8GiB | Node26.7, npm lock; cap Vitest workers; run install/test/typecheck/build, record cgroup peak. |
| Platform E2E | 2CPU /3GiB /10GiB | Prebuilt Chrome/dependencies; workers1; serialize existing3shards or prove equivalent single complete suite. |
| Platform API | 2CPU /4GiB /10GiB | Java25/Gradle9.8.1; max-workers1 initially, explicit compiler/test heaps; replace Docker DB commands with ephemeral nonroot PostgreSQL sidecar and readiness/cleanup tests. |
| Platform image-pr | 2CPU /8GiB /20GiB | Preserve all build/load/network/volume/root-chown contract checks. A rootless image builder alone cannot run the existing Docker contract. Isolated runtime still unresolved. |
| BQL fmt/check/build, then Tier A/B/qualification/release | 2CPU /8GiB /20GiB | Prebuilt Ubuntu26.04/Rust1.99 image, cargo jobs1 then measured2; tests1 initially; cap release too. Sandbox compatibility below is a blocker for full test tiers. |

Sequential jobs avoid aggregate peaks but do not make an individual oversized
job fit. JVM heaps are only part of total memory; compilers, native code, browser,
DB and page cache must be included. Record cold/warm peak memory, CPU throttling,
scratch growth, node MemoryPressure and host/VM headroom before choosing final
requests/limits. No current full workflow runs-on change is included.

Platform completion requires gate/static/api/web/all E2E shards/image-pr/ci-ok
on the intended execution environment with existing skip/failure semantics.
The main image publisher has packages/contents write and causes GitOps deployment;
prepare its separate trusted execution path, but do not publish/deploy under PR
pool approval. BQL completion requires all four existing gate jobs, including
source-qualification and release artifact validation. Canary success is not either
repository's full CI success.

### Egress additions to review by stage

The existing GitHub/Actions HTTPS rules remain necessary. Add DNS names alongside
HTTPS443 rules only for the approved stage. These are candidates derived from
workflow manifests; redirects/CNAMEs must be observed and reviewed, not silently
replaced with unrestricted internet. Prefer digest-pinned toolchain images so
apt/toolchain download access belongs to a separate reviewed image build phase.

| Stage | Additional destination candidates |
|---|---|
| Platform web/E2E | registry.npmjs.org from package-lock; nodejs.org if setup-node cannot use an immutable preinstalled toolchain. Preinstall Chrome to avoid runtime browser/apt downloads. |
| Platform static | get.helm.sh if Helm is not preinstalled; gitleaks release download uses GitHub release destinations already allowed. |
| Platform API | services.gradle.org and downloads.gradle.org for wrapper; plugins.gradle.org and plugins-artifacts.gradle.org for plugin resolution; repo.maven.apache.org for Maven Central; corretto.aws if Java is downloaded at runtime. Verify actual redirects first. |
| BQL dependency/bootstrap | index.crates.io/static.crates.io; sh.rustup.rs/static.rust-lang.org if toolchain not prebuilt; astral.sh plus its observed GitHub redirects; pypi.org/files.pythonhosted.org for pinned oracle packages. |
| Image preparation/build | Docker Hub registry/auth/blob-CDN endpoints for Ubuntu/PostgreSQL/base images, and Ubuntu package mirrors for apt. Resolve exact current destinations in the builder environment before policy approval; no broad wildcard proposal. |
| Trusted publisher only | ghcr.io/pkg-containers.githubusercontent.com and any required package endpoints, separate write credentials and cache trust boundary. Not PR pool. |

Node image-pull traffic is separate from Pod egress. A PostgreSQL sidecar uses
loopback within one Pod; separate DB Pods would require narrowly selected DB
ingress/egress and quota redesign. Never allow exchanges, trading hosts, metadata
services or operational Vault access to satisfy a failed CI dependency download.

### BQL sandbox compatibility

`rust/crates/executor-bridge/src/git_metadata_snapshot.rs:543-590` invokes bwrap
with --unshare-all, --proc /proc, read-only FD-backed binds and cap-drop ALL.
These enforce the Git metadata sandbox, not optional test cosmetics. The workflow
comment and commands disable host AppArmor userns restriction and container
seccomp/AppArmor/masked proc paths so nested unprivileged namespaces and a fresh
proc mount work. Nonroot UID alone does not grant those kernel operations.
The existing restricted Pod with RuntimeDefault is not demonstrated compatible.

An independent local Docker diagnosis identified builtin seccomp as the immediate
namespace blocker: unshare(0) and namespace clone fail, while ordinary clone and
/proc/self/exe re-exec succeed, matching the actual engine-commit profile. Local
AppArmor is disabled; userns support, positive limits, subuid/subgid and mapping
helpers exist. The NNP/zero-capability multi-ID mapping helper barrier is a
predicted later failure, not an observed helper-stage failure. Do not copy these
Docker results to Kubernetes RuntimeDefault. The user prefers Kubernetes: obtain
actual node evidence before any explicit decision about an unvalidated VM design.
Custom seccomp comparisons are prepared-only and remain unauthorized.

A native ephemeral unprivileged Ubuntu26.04 VM with supported user namespaces
avoids nested Docker restrictions while retaining bwrap and no-network assertions,
but new VM changes are outside current approval. A Kubernetes alternative needs
runtime/user-namespace support plus narrowly reviewed AppArmor/seccomp profiles
and evidence for the fresh proc mount; hostUsers:false alone is not proof. Such
profiles/node configuration alter the current restricted proposal and need separate
approval. No privileged mode, host sysctl, unconfined profile or test removal is
being proposed as an automatic workaround. Build/fmt can be validated separately,
but cannot be substituted for the sandbox-dependent test gates.

### Credential input and metadata-only verification

GitHub App input is specified in the [security review](arc-github-app.md).
App creation/installation and private-key input require precise separate security
confirmation. Keep only metadata in chat and evidence. One App on both repositories
shares private-key authority; copied Secrets do not provide credential isolation.
Do not paste values, screenshots containing them or credential-bearing argv.

Read-only live ClusterSecretStore metadata confirms parameter-store uses
external-secrets/awssm-secret keys access-key and secret-access-key, not a declared
role ARN. Those Secret values were not read. This reference alone cannot identify
the IAM principal or prove either new path is allowed. Existing store Ready is
also not proof of new-path authorization.
The earlier preparation host's CLI/profile observation is historical, not a
claim about the current executor. No AWS login or credential extraction is
authorized by this document; IAM/KMS and new-path metadata remain unverified.

With an authorized personal AWS metadata session, verify the actual ESO principal
from owner-provided identity or matching audit metadata, its inline/attached policy
versions, permissions boundary/SCP context, and exact SSM resource ARNs. Check
ssm:GetParameter/GetParameters as used by the provider; for a customer-managed
KMS key also inspect DescribeKey/GetKeyPolicy, kms:Decrypt and encryption-context/
ViaService conditions. Parameter DescribeParameters supplies type/key metadata
without the secret value. Do not call GetParameter(s), decrypt, read Kubernetes
Secret data, or assume a different local AWS identity represents ESO. If effective
policy cannot be established, mark it unverified and have the owner approve an
exact principal/resource/key delta, never wildcard IAM widening. After owner
input, ESO Ready and target Secret metadata can verify reconciliation without
printing secret data; no such reconciliation has happened yet.


## Temporary 3Gi compilation measurement window

The owner explicitly authorized changing only the shared namespace memory sums
of ci-pr/arc-job-budget: requests.memory1Gi to3Gi, limits.memory1536Mi to3Gi.
CPU/Pod/storage quota, PSS/network/auth/other workloads remain unchanged.
One token-free hardened standalone BQL release-compilation Job runs at j1 with
request=limit3Gi. This is not a full CI resource/preflight/CEL reduction.
A same-owner bounded controller must restore both Git desired memory fields and
verify Argo Synced/Healthy plus actual quota equality after success, OOM, failure
or interruption. No direct kubectl quota patch or selfHeal suppression is used.
No higher budget, VM/node resize, paid usage, security or IAM grant is authorized.
