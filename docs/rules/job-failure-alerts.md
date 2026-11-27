---
title: Job failure alert recovery exception
updated: 2026-11-27
type: runbook
status: current
---

# Job failure alert recovery exception

## Scope

The local `kube-prometheus-stack` values replace only the upstream `KubeJobFailed`
rule using `defaultRules.disabled.KubeJobFailed` and an additional rule of the same
name. All other upstream rules remain enabled. The original failed-Job selector,
`for: 15m`, warning severity, labels and annotations are preserved.

The replacement excludes a failed Job only when all of this evidence exists:

1. Namespace is exactly `real-life-rpg`.
2. `kube_job_owner` identifies controller owner kind `CronJob` and owner name
   `real-life-rpg-scheduler`. A name prefix alone is never an exclusion.
3. A positive `kube_job_status_start_time` exists.
4. The exact CronJob has a positive `kube_cronjob_status_last_successful_time`
   strictly later than that Job's start time, in the same cluster and namespace.

No later success, zero timestamps, missing owner/start/success metadata, a new
failure after recovery, another CronJob or another namespace preserve the default
alert. Missing metadata fails open toward alerting, not toward silence. Exporter
replicas are aggregated before matching; exporter labels on actual alerts are
unchanged. No Alertmanager silence, route, repeat interval, Job history limit or
failed Job deletion is involved.

This is a failed-Job recovery exception, not a new dead-man alert. A missing
success metric alone, without a failed Job, does not generate `KubeJobFailed`.
The observed CronJob uses `concurrencyPolicy: Forbid`; the comparison models a
later successful run. Do not generalize this start-time comparison to overlapping
CronJobs without reviewing completion/failure ordering.

## Read-only source evidence

On 2026-11-27 at approximately 09:39 KST, context `kkamji-lab`, namespace
`real-life-rpg` had five retained failed scheduler Jobs ending in `29928510`,
`29928525`, `29928540`, `29928555`, and `29928570`. Their positive failed-condition
series remained present after subsequent successful scheduler Jobs. The observed
last-success timestamp was `1795739403`; the failed Jobs' start timestamps ranged
from `1795710600` to `1795714200`. The CronJob schedule was `*/15 * * * *`.

The active rule was `kube_job_failed{job="kube-state-metrics",namespace=~".*"} > 0`,
with a 900-second pending period, warning severity and no keep-firing delay.
Read-only instant evaluation against the same live metrics returned five results
for the upstream expression and zero for the candidate. This is expression
validation, not deployed-rule, notification or Alertmanager delivery proof.

## Offline verification

Use Helm `4.2.1`, matching the GitOps renderer, and promtool `3.15.0`, matching the
observed Prometheus build. Install PyYAML and jsonschema in an isolated tool
environment (this candidate used PyYAML `6.0.3` and jsonschema `4.25.1`). Set
`HELM_BIN` and `PROMTOOL_BIN` to the verified binaries, then run from the repo root:

```bash
python -m unittest discover -s tests -p 'test_kube_job_failed_rules.py' -v
"$HELM_BIN" lint charts/kube-prometheus-stack --namespace monitoring \
  -f charts/kube-prometheus-stack/kkamji_local_values.yaml
python -m unittest discover -s tests -p 'test_grafana_pvc*.py' -v
python -m unittest discover -s tests -p 'test_keycloak_current_main.py' -v
git diff --check
```

The test extracts the actual rendered rule and runs `promtool check rules` and
`promtool test rules`. The static fixture covers pending/firing, recovery,
new-failure/refiring, another recovery, missing/zero metadata, equal timestamps,
other workloads, exporter labels/replicas, cluster isolation, and historical
silence beyond twelve hours. All rendered rules are also parsed together.

The immutable full-chart comparison against
`fc09262727ab1cd6e6bd9f7247166a70f8b601e2` permits exactly removal of the old
`KubeJobFailed` entry and addition of the one-rule PrometheusRule. Full rendering
with CRDs changes from 141 to 142 objects, or 131 to 132 without CRDs. Vendor
archive, Chart.yaml, Chart.lock, all other rules, every workload, storage, Secret,
route and receiver remain identical. Rendered Secret values are never logged or
persisted. Only local monitoring whole-render counts/hashes in older regression
checks are rebased; fixed Grafana Deployment/Pod, storage guard, crypto and
original `main9a.json` oracles are retained.

The first historical-failure test was observed failing against the upstream rule
before the values edit, then passing against the rendered replacement. Fixtures
use synthetic timestamps for repeatable lifecycle checks; actual queried series
and exact validation logs belong in task-local evidence, not application secrets.

## Deployment and rollback boundary

This candidate is local and uncommitted. It is not permission to push, merge,
refresh Argo CD, apply rules, delete Jobs or change the CronJob. Final-commit docs
freshness/coupling and remote CI cannot be claimed before an authorized commit.
A future approved GitOps rollout must verify both rule-resource updates converge,
only one active `KubeJobFailed` exists, actual historical alerts resolve, and a
new genuine failure still follows the 15-minute pending period. Moving the rule
between resources can reset pending state during rollout; local tests do not
prove delivery transitions or eliminate that rollout window.

Rollback is the Git inverse of the values change and its regression baseline
updates. It restores the original upstream behavior, including retained failed
Jobs alerting until removed; it does not remove or modify any Job.

## Primary references

- [Prometheus rule unit testing](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
- [kube-state-metrics Job metrics](https://github.com/kubernetes/kube-state-metrics/blob/v2.17.0/docs/metrics/workload/job-metrics.md)
- [kube-state-metrics CronJob metrics](https://github.com/kubernetes/kube-state-metrics/blob/v2.17.0/docs/metrics/workload/cronjob-metrics.md)

Metric availability and the rendered default expression were checked against the
actual running cluster and the pinned vendored chart, not assumed from these
reference versions. Last-success is an experimental kube-state-metrics metric;
its disappearance conservatively restores default failed-Job alerting.
