#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)
HELM_BIN=${HELM_BIN:-helm}
PYTHON_BIN=${PYTHON_BIN:-python3}
work=$(mktemp -d)
trap 'rm -r -- "$work"' EXIT
"$HELM_BIN" template arc-foundation "$ROOT/charts/arc-foundation" -n arc-system > "$work/default.yaml"
"$HELM_BIN" template arc-foundation "$ROOT/charts/arc-foundation" -n arc-system -f "$ROOT/charts/arc-foundation/kkamji_local_values.yaml" > "$work/local.yaml"
"$HELM_BIN" template argo-projects "$ROOT/charts/argo-projects" -n argocd -f "$ROOT/charts/argo-projects/kkamji_local_values.yaml" > "$work/projects.yaml"
for chart in arc-light arc-bql-light; do
  "$HELM_BIN" template "$chart" "$ROOT/charts/$chart" -n ci-pr -f "$ROOT/charts/$chart/kkamji_local_values.yaml" > "$work/$chart.yaml"
done
"$PYTHON_BIN" - "$work" <<'PY'
from pathlib import Path
import sys
import yaml
root = Path(sys.argv[1])
def docs(name):
    return [x for x in yaml.safe_load_all((root / name).read_text()) if x]
assert not any(x['kind'] == 'PriorityClass' for x in docs('default.yaml'))
local = docs('local.yaml')
classes = [x for x in local if x['kind'] == 'PriorityClass']
assert len(classes) == 1, 'local foundation must create one opt-in PriorityClass'
pc = classes[0]
assert pc['metadata']['name'] == 'arc-ci-nonpreempting'
assert pc['value'] == 0 and pc['globalDefault'] is False
assert pc['preemptionPolicy'] == 'Never'
assert not any(x['kind'] in ['ExternalSecret', 'Secret'] for x in local)
project = next(x for x in docs('projects.yaml') if x['metadata']['name'] == 'arc-ci')
assert {'group': 'scheduling.k8s.io', 'kind': 'PriorityClass'} in project['spec']['clusterResourceWhitelist']
assert len(project['spec']['clusterResourceWhitelist']) == 3
for name in ['arc-light.yaml', 'arc-bql-light.yaml']:
    runner = next(x for x in docs(name) if x['kind'] == 'AutoscalingRunnerSet')
    for spec in [runner['spec']['template']['spec'], runner['spec']['listenerTemplate']['spec']]:
        assert spec['priorityClassName'] == 'arc-ci-nonpreempting'
        assert spec['preemptionPolicy'] == 'Never'
print('PASS: opt-in class, no global priority change, narrow project grant, both listener/runner links, no auth resources')
PY
if "$HELM_BIN" template arc-foundation "$ROOT/charts/arc-foundation" --set-string priorityClass.enabled=false >/dev/null 2>&1; then
  printf 'priorityClass boolean schema unexpectedly accepted a string\n' >&2
  exit 1
fi
