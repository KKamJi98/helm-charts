---
title: Repository-scoped ARC rollout and evidence
updated: 2026-10-18T00:14:12+09:00
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
Device Plugin is UID0/cap0/NNP1/read-only, not a privileged container. Its
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

Both new scale sets intentionally keep min0/max0. Do not route normal CI here
until actual SDK startup, Docker API isolation/lifecycle, exact resource and
GitHub JIT qualification pass. Canary or local fixed probes never replace the
original job/needs/matrix/timeouts/tests and release binary contracts. Full CI
and permanent operational health remain unverified at this source-staging step.
Rollback keeps both maxima0, restores routing, removes only owned workload/helper
resources, and removes an unchanged owned profile only after no Pod references
it. Namespace pruning is disabled and authentication targets are retained.
