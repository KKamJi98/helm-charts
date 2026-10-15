---
title: Repository-scoped ARC rollout and evidence
updated: 2026-10-15
type: runbook
status: current
---

# Repository-scoped ARC rollout

This candidate is disabled. It prepares ARC for KKamJi98/kkamji-platform and
KKamJi98/binance-quant-lab on kkamji-lab. Neither canary nor full CI has run on ARC.
Do not replace this statement with an operating-success claim until evidence exists.

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
Job preemptionPolicy Never; restricted/v1.36 namespace PSS; no workload eviction.
2026-10-15 observed w2 usage3010Mi/59%, allocatable5057Mi, requests2537Mi/50%.
Using aggregate limits leaves roughly1023Mi in that snapshot, not a peak guarantee.
Recheck MemoryPressure, peak service/host usage, and disk headroom before activation.
No VM changes are included. Heavy compilation requires a separately measured budget.

## Credentials and network approval

Two distinct fine-grained PAT candidates: each selects only its matching repository,
Administration read/write + Metadata read, expiry30days. Registration Secrets are
ci-pr/arc-platform-auth and ci-pr/arc-bql-auth, sourced by existing ESO
parameter-store from /kkamji/arc/platform-auth and /kkamji/arc/bql-auth in
ap-northeast-2. Values must be entered directly through the approved secure SSM
flow as SecureString JSON with github_token. Never paste values in chat, PRs or
command arguments. No token/SSM write was performed. Existing ESO IAM/KMS rights
for these exact paths must be verified; no implicit IAM expansion is authorized.
Owner ExternalSecrets can garbage-collect target Secrets despite deletionPolicy Retain.

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
2. Through approved GitOps commits enable foundation, verify both ESO Secrets and
   CNI rules; then controller; then each scale set. No direct helm install/upgrade.
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
