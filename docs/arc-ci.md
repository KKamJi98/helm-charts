---
title: Repository-scoped ARC rollout and evidence
updated: 2026-10-19T02:04:44+09:00
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


## Completed temporary 3Gi compilation measurement window

The owner explicitly authorized changing only the shared namespace memory sums
of ci-pr/arc-job-budget: requests.memory1Gi to3Gi, limits.memory1536Mi to3Gi.
CPU/Pod/storage quota, PSS/network/auth/other workloads remain unchanged.
One token-free hardened standalone BQL release-compilation Job runs at j1 with
request=limit3Gi. This is not a full CI resource/preflight/CEL reduction.
A same-owner bounded controller must restore both Git desired memory fields and
verify Argo Synced/Healthy plus actual quota equality after success, OOM, failure
or interruption. No direct kubectl quota patch or selfHeal suppression is used.
No higher budget, VM/node resize, paid usage, security or IAM grant is authorized.


## Restore shared memory budget

This commit returns the temporary namespace sums to requests.memory1Gi and
limits.memory1536Mi. The standalone compilation outcome is separate evidence;
this restore does not claim full CI success. CPU/Pod/storage/security/auth and
existing workloads remain unchanged. Actual quota and Argo convergence must be
verified against this source revision before closing the window.


## Non-Docker static tool preparation

The Platform light template gains a token-free uid1001/NNP1/dropALL/RuntimeDefault
read-only init container. It copies only checksum-verified Helm4.2.1 from the
existing pinned toolchain image into the existing per-job work/toolcache path.
No daemon, host socket/path, extra capabilities, new egress, pool/namespace,
credential or quota field is introduced. Main runner/SDK/auth/resource/volume
settings and the BQL light template stay unchanged. Non-restartable init requests
and limits are below the existing regular container, so effective job scheduling
requests/limits do not increase. This tool copy does not qualify Docker/full CI.
The OCI index/AMD64 manifest/CRI config chain must be read back before source
activation; the node-local immutable reference is not registry publication.


## Restricted non-Docker frontend validation

The Platform job uses the same verified SDK-derived toolchain image in an explicit
non-Docker role. Its trusted launch checks uid1001/NNP1/cap0/Seccomp2/no token/no
host socket, asserts the private Docker socket absent, records Node/Chrome
versions and starts the unchanged official SDK. It never starts RootlessKit or
Docker and is not the8Gi full-Docker runner/preflight/CEL qualification.
Regular resources/security/volumes/SA and BQL light are unchanged. A256Mi init
limit remains below the regular512Mi limit, so effective Pod budget is unchanged.
Node26.7.0 and Helm4.2.1 toolcache entries point to verified image tools. Locked
public npm packages were fetched by a trusted isolated metadata-only npm ci
--ignore-scripts process, then COPY-only assembled into a local immutable image.
The job copies only public cache content, verifies the source lock hash and runs
its original npm ci/test/typecheck/build or three E2E shards with npm offline.
No registry egress or browser sandbox/namespace/capability exception is added.
This preparation does not claim fresh network npm audit or actual CI success.


## Frontend Node heap evidence and bounded budget

Native043bb767 run39013869533 installed npm packages, then aborted134 during
tsc -b in the composite E2E preparation step at a roughly256MB V8 heap limit,
before Playwright executed. The step label alone did not identify the command.
Sampled kernel OOM was0; no seccomp/PID/namespace relaxation was inferred.
The stuck SDK-session-conflict run was cancelled for complete logs, not passed.
The Platform non-Docker job memory reservation becomes1Gi and cap1536Mi, both
within the unchanged existing namespace hard budget. This is a provisional
frontend envelope, not a measured minimum or BQL/full-Docker8Gi reduction.
CPU/storage/namespace quota, source checks/shards/timeouts and all security
contexts stay unchanged. Startup records actual V8 heap limit; the same source
failed/cancelled jobs must be rerun and verified before claiming recovery.


## Verified data-only font recovery for geometry failures

At the same043bb767 source, the bounded heap profile passed973 web tests,
typecheck/build and E2E shard2. Shards1/3 retained exact geometry assertions and
failed at877px versus844px focus height and a2-line title versus1 at1024px.
The toolchain only had Liberation fonts; fc-match system-ui/sans-serif/Korean
fell back to Liberation Mono. A data-only child adds checksum-verified
architecture-all DejaVu/Noto core/CJK/emoji font files without package scripts.
fc-match now selects Noto Sans and Noto Sans CJK. SDK/Chrome/Node/npm/source,
resource limits, permissions, policies and all assertions remain unchanged.
The same-source font-only attempt3 replay passed all188 original E2E tests
across3 shards; font metadata/image digest alone was not used as the gate.
Original API/image hosted failures still prevent full CI success.


## Verified boundary and remaining blockers

The approved BQL single j1 trial at request=limit3Gi OOMKilled/137 with zero
verified release outputs. PR17 temporarily expanded only shared memory totals;
PR18 restored requests.memory1Gi/limits.memory1536Mi through normal GitOps.
Source/live quota equality and Argo Synced/Healthy were verified after cleanup.
CPU/Pod/storage quota, VM/node memory and security permissions did not change.
The OOM-clipped3Gi peak proves neither a successful minimum nor8Gi necessity.

Platform source043bb767 run39013869533 is the original CI, not a smoke alias.
Attempt3 actually passed native gate/static, Python108, web973/typecheck/build
and all3 original E2E shards (188 tests). The same source/CSS/assertions and
Chrome/Node/runtime/resources were retained; only font data resolved the exact
prior two geometry failures. Native runner/job verdicts remain distinct from
workflow-level success.
API/image-pr remain hosted pre-start payment failures, not code-test failures;
ci-ok retains its real failure aggregation and PR136 stays draft/unmerged.
No protection rule, original assertion, test selection, matrix or timeout was
weakened, and the canary workflow remains manual-only.

This is a restricted non-Docker validation role, not full Docker8Gi guard
qualification. The stock NNP0/capSETUID+SETGID/raw API design is not adopted.
All-thread outer privilege removal and a byte-identified filtered Docker API
implementation/escape/compatibility evidence remain unresolved. Outside the
separately approved fixed diagnostic below, production namespace/capability/
syscall/profile/host access changes remain unauthorized.

Images use verified node-local immutable references with imagePullPolicy=Never;
no registry publication or credential transfer was performed. Image-GC/node
recovery and general production runner distribution are not solved merely by
this bounded validation. Current App/ESO/controller credential inputs are already
resolved and must not be re-entered or treated as an old profile blocker.


## Explicit5Gi first and bounded Docker lab approval

The owner now authorizes one5Gi/j1 BQL trial on an existing safe worker, not
necessarily k8s-w2. Discover capacity/image-eligible workers and let node affinity
restrict scheduling to that verified set; preserve512Mi scheduling and1Gi
actual reserve, CPU/Pod/storage/security/source/release12bin contracts.
Only shared memory quota totals temporarily become5Gi/5Gi; restore1Gi/1536Mi
through normal GitOps even on OOM/failure/interruption and verify actual/Argo.
Workload relocation is permitted when needed, not a requirement to move services.
The separately approved180s trusted Docker lab includes namespace, NNP0/cap2,
Localhost6-call profile and Pod UID/GID mapping hypotheses. It does not approve
privileged/SYS_ADMIN/host socket/Unconfined/Unmasked, credential exposure,
untrusted application execution or production full CI before drop/API proof.


## Restore shared memory budget

This commit returns the temporary namespace sums to requests.memory1Gi and
limits.memory1536Mi. The standalone compilation outcome is separate evidence;
this restore does not claim full CI success. CPU/Pod/storage/security/auth and
existing workloads remain unchanged. Actual quota and Argo convergence must be
verified against this source revision before closing the window.


## Verified5Gi compilation and bounded lab result

This cap2 evidence and permission hold are historical. The later explicit
SETFCAP diagnostic authorization/result below supersedes only that hold.

The single5Gi/j1 trial compiled the original source and all12 release binaries.
Cargo returned0, wall412.40s, CPU410.65s, cgroup peak3.371Gi, largest child
maxrss3.179Gi and OOM deltas0. Downloaded ELF x86-64/mode0555, size and SHA256
were verified for every output. Lock/security/CPU/storage contracts stayed intact.
This is standalone compilation, not the full BQL workflow, not a proven minimum
and not permission to weaken the existing full candidate guards.

Only currently safe/image-eligible workers were admitted by affinity. No existing
workload relocation was necessary. Normal PR24 expanded only shared memory and
PR25 restored1Gi/1536Mi. Actual used0 and Argo source/Healthy/Synced matched.
The local wrapper's exit1 was an asynchronous quota-used readback race AFTER
compile/export success, not an OOM or compilation failure. A bounded convergence
wait now has positive/stale and negative/nonconvergence regression checks; the
successful compile was not needlessly rerun.

The authorized fixed180s lab ran with actual hostUsersfalse, trusted NNP0 and
only SETUID/GID, job NNP1/cap0, readonly roots and native-matched six-call profile.
Stock SUID mapping helper failed opening uid_map. A byte-identical helper variant
removed SUID and used only per-helper SETUID/GID file capabilities; it opened the
file but failed writing uid_map with EPERM. Neither attempt initialized Docker,
ran application source or proved post-init drop/API/network isolation.

The proposed full65536-ID mapping includes parent UID0. Linux5.12+ requires
CAP_SETFCAP for that mapping; current approved bounding set excludes it. This
is a definite missing prerequisite of this mapping design, not proof it is the
only remaining failure. See https://man7.org/linux/man-pages/man7/user_namespaces.7.html .
No CAP_SETFCAP, SYS_ADMIN, Unmasked, Unconfined or host access was added. Do not
shrink the UID model or claim a minimum/sufficient capability set just to pass.
All owned lab Pods/namespace and the created node profile were removed and read
back absent. Verified local image caches remain artifacts, not active authority.
A new narrow permission decision is needed before another broader lab step;
operational full CI stays unqualified, and neither canary nor subset is full CI.


## Explicit SETFCAP scope - isolated rootless core initialization verified

The owner separately approved SETFCAP ONLY for the same fixed180s trusted
role and mapping helper. Bounding is exactly SETUID/GID/FCAP, observer NNP1
and cap0, readonly/no-token/hostUsersfalse/procMountDefault and native-matched
six-call Localhost unchanged. No outer SYS_ADMIN/NET_ADMIN/DAC_OVERRIDE,
Unmasked, Unconfined, device or host access was added. No application source
or operational ARC/JIT job was run.

The original UID-helper failure advanced to detached-network-namespace bind
failure. The actual Docker entrypoint supports DETACH_NETNS0; that official
configuration preserved slirp while avoiding the persistent bind. Missing ip
and omitted sbin PATH were image packaging defects, corrected with signed
Ubuntu iproute2 and existing iptables. The normal slirp path then reached
TUN creation, where actual Pod /dev/net/tun was absent. Node device presence
does not mean it was allocated into the Pod.

A clearly separate netnone diagnostic isolated daemon prerequisites from TUN.
The complete map puts image parentUID0 at nestedUID1; image SUID4755 mount
and umount changed the intended nested identity. Removing just their SUID
bits, retaining exact binary bytes and every runtime authority, fixed that
transition. This did not add an outer capability or reduce UID coverage.

Under that isolated netnone variant, actual Docker29.9.1 initialized and the
fixed version/info observer passed; trusted and observer native exits were0.
Nested UID/GID maps covered all65536 IDs. Kernel capabilities in a child user
namespace were observed and are not host capabilities or proof of post-init
all-thread privilege removal. The parent remains NNP0/bounding3 in this
authorized diagnostic; effective0 by itself is not privilege-drop success.

This result is NOT the original network/bridge/port/cache/image contract,
container execution, API authorization/escape/peer-negative proof or full CI.
Do not turn netnone into a workflow skip or qualifying flag. Existing BQL5Gi
ELF12 proof and restored1Gi/1536Mi/used0 remain valid; no compilation rerun.
All owned lab Pods/namespace and created node profile were removed/read back.

Normal networking remains blocked on a NEW TUN device-allocation boundary.
Current containerd defaults do not grant TUN in the device cgroup, and kubelet
does not copy arbitrary Pod annotations into CRI container CDI annotations.
A file mount or Pod CDI annotation is not enough. Device-plugin/DRA allocation
requires a separately reviewed scope; no plugin, host registration socket,
CDI spec, node configuration, namespace-policy exception or device access was
applied. An upstream privileged/whole-dev example is not a safe template.
Proposed nonprivileged/single-device adaptation is source-only and not ready
for deployment until its exact image and new authority are verified/authorized.
Operational full CI, post-init drop and per-job API isolation remain partial.

## Isolated full-runner staging

The latest owner approval includes trusted-only `procMount: Unmasked` validation
and the same-role CI operating rollout after qualification. Fixed native Docker
checks passed pull, build/cache, container, bridge, published port, bind mount,
named volume and absence of the node profile in the daemon filesystem. Both
consumer exits were0. This is not original full CI or a GitHub JIT startup result.

A native Kubernetes1.36.1 proof separately verified a shared Pod-level memory
request/limit5Gi and CPU limit2 for two containers. Both cgroup ancestor limits
and quota usage were5Gi, not two5Gi budgets. QoS was Burstable, not Guaranteed.
ARC0.15.0's installed CRD carries the Pod resources field. The proof Pod and its
namespace were removed, with existing ci-pr quota unchanged.

`charts/arc-runtime` installs the versioned trusted seccomp profile on worker
nodes and registers only `kkamji.net/arc-tun`, one slot per node. The pinned
Device Plugin is UID0/cap0/NNP1/read-only, not a privileged container. The pinned
0.2.0 binary accepts `--listen=:8080`, not `--listen-address`; CLI parity is
regression checked. Its
namespace admits only the necessary host registration/device discovery mounts;
the fixed installer also writes the dedicated seccomp file. Both components
have no Kubernetes token. Do not remove that file while any running Pod uses it.

`charts/arc-full` packages the existing official0.15 controller and two scale-set
charts with local locked dependencies. Its controller watches only ci-full;
the existing arc-system controller still watches ci-pr. Global CRDs remain
owned by the existing controller Application; the full Application skips CRDs.
The existing approved SSM source is referenced by ESO in ci-full, without
manual value read/copy or IAM/key changes. Both namespace targets still share
one GitHub App authority, not isolated credentials. Reusable auth defaults off;
local reuse is explicit, Orphan/Retain preserves the target during rollback.

SDK work and daemon data use distinct per-Pod emptyDir volumes. Only the work
path and API socket cross the SDK/daemon boundary. The SDK private HOME and
registration files are not mounted into the daemon. SDK seeding copies only
the verified immutable runner files, bin and externals, never image credential
paths. SDK is UID1001/NNP1/cap0/read-only/RuntimeDefault. The trusted native
sidecar is UID1001/NNP0, bounded to SETUID/SETGID/SETFCAP, Unmasked and the pinned
Localhost profile. Those trusted privileges last for the job, not initialization
only; no all-thread privilege-drop claim is made. Neither role uses host PID,
network, IPC, host Docker socket or a mounted Kubernetes token. The outer Pod
uses hostUsersfalse/full65536 and a shared5Gi budget. Inner Docker API authority
is delegated for that job only; it is not a node daemon.

Fresh capacity snapshots selected w2 for the current5Gi/14Gi ephemeral envelope;
this is measured eligibility, not a requirement that future runners always use
w2. The new small control Pods are placed on w1. SDK startup checks node memory
reserve1Gi and disk reserve5Gi before repository code. Controller/listener surge
headroom is separate from the one heavy-job memory/TUN quota. Public CI egress
excludes private, node, loopback, link-local, CGNAT and metadata ranges; only
control roles can reach the API. No external endpoint or persistent cache is added.

Reusable scale-set defaults keep min0/max0. Both local repository pools now
allow min0/max1 after the common fixed runtime and actual Platform SDK/JIT/GHA
cache qualification. BQL first gets its own trusted canary before normal routing.
All normal CI Jobs will use the full pool rather than overlap a w2 light Job with
a5Gi heavy Job. Existing light canaries and ci-pr quota/policies remain intact.

The SDK and seed use the already verified frontend image0d5, which has system
Chrome/font parity. Its managed SDK/Worker DLLs, startup scripts and Docker CLI
match the qualified helper image exactly. The daemon remains on image0a and the
same profile/privileges. SDK private HOME only receives immutable SDK files;
normal npm cache is writable there and online, not an image-auth/cache copy.
This avoids transferring a large extra toolchain into w1's smaller disk budget.
No w1 large-image import, low disk reserve or image rebuild is hidden here. Two
fixed SDK Pods actually passed non-root/NNP1/cap0/read-only/no-token/no-TUN,
private HOME/node-profile/socket isolation, private TCP denial, fresh job graph,
and native-sidecar recovery. All three roles exited0, the daemon restarted once
per job, data persisted only within that job, and both Pod directories were
removed. This is actual fixed runtime qualification, not GitHub JIT/full CI.

The docker-container BuildKit driver was denied at privileged sysfs mount.
Do not relax host/sysfs policy to make that mode pass. The native Docker29
containerd image store and embedded docker driver actually passed build/load/run
plus local cache export, builder-prune, external cache import and RUN CACHED.
Official Docker cache documentation supports gha with this driver when that
store is enabled; actual GHA cache export/import still needs the GitHub canary.
Keep original cache parameters/tests, never replace this gate with a local-only
claim. Do not route normal CI until actual SDK/JIT/cache startup is verified. Canary or local fixed probes never replace the
original job/needs/matrix/timeouts/tests and release binary contracts. Full CI
and permanent operational health remain unverified at this source-staging step.
Rollback keeps both maxima0, restores routing, removes only owned workload/helper
resources, and removes an unchanged owned profile only after no Pod references
it. Namespace pruning is disabled and authentication targets are retained.

## ARC0.15 JIT workspace mapping

The first original BQL run stopped before Rust tests: its checkout landed under
private SDK HOME, outside the daemon's shared work mount. Docker correctly could
not create that path on its read-only root. Matching upstream
[ARC0.15 source](https://github.com/actions/actions-runner-controller/blob/gha-runner-scale-set-0.15.0/controllers/actions.github.com/ephemeralrunner_controller.go)
assigns JIT WorkFolder from the runner container workingDir. Set workingDir to
/home/runner/_work, the existing shared work path, not private /home/runner.

This is a workspace mapping fix, not a permission, Rust assertion or memory fix.
Keep SDK HOME unshared, the same work/socket/data volumes, approved roles,
profiles and shared5Gi/CPU2. The rendered two-repository path regression first
failed and then passed. Original BQL CI must be rerun on the same source after
the GitOps fix; the initial exit125 and cancelled siblings remain failed evidence.

## Bounded BQL Docker storage and pressure-aware startup

The corrected original BQL checkout reached Tier A. Its Pod was then evicted
because private docker-data exceeded10Gi, not memory OOM or a Rust assertion.
The failed attempt is retained and stopped; a truncated budget is not a proven
minimum. The next bounded candidate is Docker data12Gi and SDK4Gi, aggregate
Job ephemeral limit16Gi, namespace limit18Gi including control/surge. Memory
stays shared5Gi/CPU2 and all source tests/timeouts/parallelism remain unchanged.

Before repository code, require free disk >=16Gi + max(5Gi, filesystem15%+1Gi).
Matching kubelet1.36.1 Linux source uses imagefs15% when the live config/flags do
not override it. The native preflight confirmed this candidate fits. This raises
the original fixed14Gi+5Gi guard; it never lowers it to force a run. The paired
BQL workflow disables incremental intermediates, not any checks or release
outputs. No node resize, image/cache deletion, PVC/host volume or shared job data.
Private emptyDirs still die with their own Pod; native data/logical Docker size
and final original CI results must establish whether this candidate succeeds.

## BQL whole-workspace private storage continuation

The original825 CI source-qualification20 active cases, release12 producers plus
one separate operator tool, Tier B, proof receipts and Python recorders passed.
The actual release archive SHA256, all ELF64/x86_64 payload checksums and0555
modes were parent-verified. Tier A instead lost its runner when docker-data
exceeded12Gi; the retained Pod event says EmptyDir eviction. This is not a Rust
assertion or evidence of a memory minimum. The capped data observation is not a
successful required-storage measurement.

The next BQL-only candidate raises private Docker data/daemon limit to16Gi,
keeps SDK4Gi and shared Pod5Gi/CPU2, and raises the aggregate namespace ephemeral
limit18Gi to22Gi for the20Gi Job plus control/surge. Platform keeps its exact
original Pod template and12Gi+4Gi allocation. YAML inheritance preserves the
other BQL roles, mounts, image pins, requests and security fields unchanged.

The SDK requires20Gi + max(5Gi, filesystem15%+1Gi) before BQL repository code.
Platform retains its16Gi base. The BQL template must declare exactly one literal
20Gi budget, never an absent/duplicate/under-sized or Secret-referenced alias.
Unknown budgets fail closed. The shared5Gi+1Gi memory reserve and all native
security checks remain unchanged; no pressure guard is lowered to admit work.

Only the task-owned retired measurement image tag was removed after zero live
references and verified immutable recovery export. Operating full/light images
remain; no shared image prune, node resize/restart, PVC/host volume or key change.
Actual free space must pass the stronger preflight after the competing Job's own
cleanup; projected reclaimed space is not a successful execution gate.

After exact-head checks, GitOps readback and fresh capacity, rerun only failed
original Tier A/dependent verdict on the same825 source. Keep all independent
successes and original tests/oracles/needs/timeouts/release contracts. A successful
candidate must still complete the original main workflow after normal merge.
Rollback drains only owned BQL work, restores BQL12Gi/guard16Gi and namespace18Gi
through GitOps, and retains controllers, authentication and finalizers. Do not
interrupt another repository's busy runner or delete its data to make room.

## BQL private test scratch within the same20Gi Pod limit

The bounded16Gi original Tier A attempt still hit its EmptyDir ceiling after
277 test binaries were built;275 captured target summaries had no failures, but
the final serial targets/S2 completion were not verified. Retain this failure.
Do not call a higher cap a minimum, discard tests, strip ELFs or prune node data.

Keep Docker data16Gi, SDK4Gi, shared5Gi/CPU2, Pod aggregate20Gi and namespace22Gi.
Only BQL daemon-tmp grows512Mi to3Gi, disk-backed under that SAME aggregate limit;
Platform's Pod template stays exact. The existing trusted UID1001 role prepares
/tmp/arc-bql-scratch as its own sticky1777 parent using O_NOFOLLOW and fd chmod,
with no chown or new capability. A normal Ubuntu UID1000 helper creates0700 child
state and the paired workflow binds just that child at the original HOME cache
scratch base. This separates temporary real-ELF copies from Cargo's data graph,
not from the Pod's accounting or before-repository pressure guard.

Actual native root/caller ancestry, UID1000/0700, ELF SHA/0500 execution and RO
refusal passed in a token-free fixed probe, followed by namespace/Pod cleanup.
The BusyBox /home65534 refusal and argv0 fixture error were preserved, not
whitelisted or reported as runtime permission failures. This is FS evidence only;
the original complete Ubuntu workload must still validate all contracts.

There is no new volume type, mount propagation, host path, Secret, device, role
or controller/auth change. Disk3Gi/never-memory and pool budgets fail closed.
Keep the actual20Gi+pressure/memory6Gi start guards. Deploy this preparation
before its workflow; roll back the workflow before shrinking scratch, drain only
owned work, and preserve other repositories and controller/finalizer cleanup.

## Two full runner slots across both workers

Measured on 2026-10-18: one BQL gate run on ARC took about two hours because
its six jobs ran one after another (Tier A 34m, Tier B 13m, release 8m, proof
receipts 8m), while the same jobs on hosted runners ran in parallel in about
25 minutes. Each full pool had `maxRunners: 1`, the namespace quota admitted
one 5Gi runner, and runners were pinned to k8s-w2 only because the runner
images existed only there. The images now come from GHCR
([ARC runner images](arc-runner-images.md)), so that pin is gone.

- Runner Pods require `kubernetes.io/hostname` In `k8s-w1`, `k8s-w2`. Both
  workers run `arc-runtime` (same seccomp profile hash, one
  `kkamji.net/arc-tun` slot each), so the slot request keeps one runner per
  node. Listeners and the controller stay on k8s-w1.
- Each pool allows `maxRunners: 2`. `ci-full/full-budget` admits exactly two
  runners: `requests.kkamji.net/arc-tun` 2, pods 6, CPU 1400m/6, memory
  10752Mi/11Gi, ephemeral 5Gi/42Gi. These are the live single-runner usage
  (control 200m/1, 256Mi/512Mi, 192Mi/768Mi; BQL runner 500m/2, 5Gi/5Gi,
  2Gi/20Gi) times two runners plus the same margins as before.
- A third runner is rejected by quota, not left Pending on a node. ARC 0.15
  requeues a quota-rejected runner Pod every 30s and recreates the ephemeral
  runner before its JIT registration expires, so the job waits instead of
  failing. The two pools share the two slots without a fairness guarantee.
- Per-Pod budgets, security contexts, the 5Gi memory and 20Gi disk start
  guards and the validator are unchanged. Before this change k8s-w1 had
  8.0GiB MemAvailable and 65GB free disk, above both guards.
- Rollback: revert the commit. Running jobs keep their Pods; ARC skips busy
  runners when it replaces an outdated runner set.

## Runner CPU limit 4 after the 8 vCPU workers

Before 2026-10-18 the workers had 3 vCPU (2.4 allocatable) and runner Pods a
CPU limit of 2. Over three days runner Pods were CFS-throttled in 14-21% of
periods (Platform runner containers, BQL up to 19%), BQL peaked at 1.95 cores
and node busy time reached 84-86% while hypervisor steal stayed 0%. The owner
raised k8s-w1 and k8s-w2 to 8 vCPU (7400m allocatable). The runner Pod CPU
limit is now 4 for both pools; requests stay 500m, so scheduling and the
guarantees of other workloads are unchanged. `ci-full/full-budget`
`limits.cpu` is 10 (two runners at 4 plus control 1 and the same 1 margin).
BQL keeps `CARGO_BUILD_JOBS=1` until memory headroom for parallel builds is
measured; its memory peak was 4.98GiB of the 5Gi limit.

## BQL Docker data 30Gi (owner decision)

On 2026-10-18 the owner raised the BQL Docker data budget from 16Gi to 30Gi.
Measured peaks in the last full gate run were below the old limit (Docker data
6.71GiB in source qualification, 3.87GiB in Tier B; Tier A was not sampled),
so this adds headroom; it does not fix a measured failure.

- BQL `docker-data` sizeLimit and the `dind` ephemeral limit are 30Gi. With the
  SDK 4Gi the Pod aggregate and `ARC_JOB_EPHEMERAL_GIB` are 34. Platform keeps
  12Gi/16. The validator, `sdk-entry.py` and tests pin 30Gi/34 and reject 16Gi/20.
- The start guard now needs free disk >= 34Gi + max(5Gi, 15% + 1Gi), 49.4GiB on
  the 95.7GiB worker root filesystems. Free disk at the change: k8s-w1 57.7GiB,
  k8s-w2 63.0GiB. A node below the guard fails the job before any repository
  code runs; it does not wait. Watch node free disk: kubelet image GC starts only
  at 85% usage, well after this guard trips.
- `ci-full/full-budget` `limits.ephemeral-storage` is 70Gi (two BQL Pods at 34Gi
  plus control 768Mi and the same 1280Mi margin). Other quota values are unchanged.

## Sized slots: one Platform and one BQL runner per worker

With two shared slots the pools still waited on each other: on 2026-10-18 a
Platform runner sat quota-rejected while two BQL jobs held both slots. The owner
then raised k8s-w1 and k8s-w2 to 16GiB memory (14.77GiB allocatable) and the
worker disks from 100GB to 160GB (root filesystem 155GiB, grown online with
`growpart`, `pvresize` and `lvextend -r`; kubelet restarted to report the new
ephemeral capacity).

- `arc-runtime` advertises two `kkamji.net/arc-tun` slots per worker (the device
  plugin group `count` is 2; both share `/dev/net/tun`).
- Each pool requires anti-affinity against its own runners on
  `kubernetes.io/hostname`, so a worker holds at most one Platform and one BQL
  runner. Both pools keep `maxRunners: 2`.
- Pod memory is per pool: Platform 3584Mi (measured peak 2.76GiB), BQL 7Gi
  (peak 4.98GiB at the old 5Gi limit with `CARGO_BUILD_JOBS=1`; the headroom is
  for parallel builds after it is measured). One of each plus the 4.19GiB that
  other workloads requested on the busiest worker is 14.69GiB. A runner that
  does not fit waits as Pending; it does not fail.
- The memory start guard reads `ARC_POD_MEMORY_MIB` and needs node
  MemAvailable >= Pod budget + 1Gi (4.5GiB Platform, 8GiB BQL). The validator
  pins the variable to each pool's Pod memory. A Pod from the old template has
  no variable and keeps the old 6GiB guard during the rollout.
- Disk start guards are unchanged (Platform 16Gi, BQL 34Gi plus max(5Gi, 15% +
  1Gi)): 40.3GiB and 58.3GiB on the 155GiB root. Both budgets plus the margin
  (74.3GiB) fit next to the 30-40GiB already used (110GiB and 119GiB free after
  the growth).
- `ci-full/full-budget` admits four runners: pods 8, CPU 2400m/18, memory
  22016Mi/22Gi, ephemeral 9Gi/102Gi, `arc-tun` 4 (two BQL and two Platform Pods
  plus control and the same margins as before).
- Rollout: merge when no full runner is busy if possible. ARC skips busy runners
  when it replaces the runner sets; the device plugin restart keeps allocated
  devices. Rollback: revert the commit (the disk and memory growth stay).

## Platform Docker data 30Gi

On 2026-10-19 the Platform Rust backend PR evicted its api job twice: first
the 6Gi `work` volume, then, after cargo moved into a Docker volume, the 12Gi
`docker-data` volume (a fresh Rust debug build is 12G). The Platform side
reduced the build to 2.4G with `CARGO_PROFILE_DEV_DEBUG=0`; this change is
headroom, matching BQL.

- Platform `docker-data` sizeLimit and the `dind` ephemeral limit are 30Gi and
  the SDK declares `ARC_JOB_EPHEMERAL_GIB` 34, like BQL. The validator now
  requires the 30Gi/34 budget for both pools; `work` stays 6Gi.
- Start guard per job: 34Gi + max(5Gi, 15% + 1Gi) = 58.3GiB free on the 155GiB
  root. One runner of each pool on a worker needs 34 + 34 + 24.3 = 92.3GiB next
  to the 30-40GiB in use (free 110GiB and 119GiB after the disk growth).
- `ci-full/full-budget` `limits.ephemeral-storage` is 138Gi (four Pods at 34Gi
  plus control 768Mi and the 1280Mi margin). Other quota values are unchanged.

## terraform-lab runner

On 2026-10-19 the owner moved terraform-lab (private) to the homelab because
GitHub-hosted jobs of private repositories no longer start (account spending
limit). Its plan, apply, GitHub and destroy workflows need no Docker.

- Scale set `terraform-lab-light` in `ci-pr`, rendered from `charts/arc-light`
  with `terraform_lab_values.yaml` (Argo app `arc-terraform-lab-light`).
  `maxRunners: 1`, web-tools image (unzip, python3, curl, git, jq), no Docker,
  no Kubernetes API token, 512Mi/2Gi memory and a 3Gi work volume for provider
  plugins, either worker.
- Only its Pods carry `arc.kkamji.net/egress: terraform`. The foundation policy
  `arc-terraform-egress` adds DNS and HTTPS for `**.amazonaws.com` (Cilium
  1.19 `**.` matches several labels, which EKS endpoints need),
  `releases.hashicorp.com`, `registry.terraform.io` and `app.terraform.io` to
  those Pods only. Every other ci-pr Pod keeps the GitHub-only egress.
- `arc-system/arc-control-budget` holds the controller, three listeners and one
  controller rollout surge (pods 5, CPU 350m/1750m, memory 448Mi/896Mi,
  ephemeral 320Mi/640Mi). The first rollout left it exactly full (4/4), so a
  controller upgrade could not surge.
- `ci-pr/arc-job-budget` now admits two Pods: one light job (1Gi/1536Mi, so two
  light Pods still never fit together) plus the terraform Pod (512Mi/2Gi).
- AWS access stays per job through GitHub OIDC; the role trust policy is scoped
  to `repo:KKamJi98/terraform-lab:*` and needs no change for self-hosted
  runners. The ARC GitHub App installation must include terraform-lab (owner
  action) before the listener can register.
- Rollback: set the Argo app `enabled: false` (or revert), then point the
  workflows back to `ubuntu-latest`.
