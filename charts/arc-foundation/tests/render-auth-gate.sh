#!/usr/bin/env bash
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
HELM_BIN=${HELM_BIN:-helm}
count_secrets() { awk '$0 == "kind: ExternalSecret" {n++} END {print n+0}'; }
defaults=$("$HELM_BIN" template arc-foundation "$ROOT" -n arc-system -f "$ROOT/kkamji_local_values.yaml")
[ "$(printf '%s\n' "$defaults" | count_secrets)" -eq 0 ]
enabled=$("$HELM_BIN" template arc-foundation "$ROOT" -n arc-system -f "$ROOT/kkamji_local_values.yaml" --set githubAuth.enabled=true)
[ "$(printf '%s\n' "$enabled" | count_secrets)" -eq 2 ]
if "$HELM_BIN" template arc-foundation "$ROOT" -n arc-system --set-string githubAuth.enabled=false >/dev/null 2>&1; then
  printf 'auth boolean schema unexpectedly accepted a string\n' >&2
  exit 1
fi
printf 'PASS: auth default off, explicit opt-in produces 2 references, malformed boolean rejected\n'
