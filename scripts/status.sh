#!/usr/bin/env bash
#
# ArgoCD AppProject + Application 상태 한눈에.
#
# Usage:
#   scripts/status.sh [NAMESPACE]
#
set -euo pipefail
NAMESPACE="${1:-argocd}"

B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'

echo
printf "%s%s== AppProjects (%s) ==%s\n" "$B" "$G" "$NAMESPACE" "$N"
kubectl -n "$NAMESPACE" get appproject -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.deletionTimestamp}{"\n"}{end}' \
  | awk -F'\t' 'BEGIN{printf "%-15s %s\n", "NAME", "DELETION"} {printf "%-15s %s\n", $1, ($2=="" ? "-" : $2 " (STUCK)")}'

echo
printf "%s%s== Applications by project ==%s\n" "$B" "$G" "$N"
kubectl -n "$NAMESPACE" get app -o jsonpath='{range .items[*]}{.spec.project}{"\t"}{.metadata.name}{"\t"}{.status.sync.status}{"\t"}{.status.health.status}{"\n"}{end}' \
  | sort \
  | awk -F'\t' 'BEGIN{printf "%-12s %-26s %-10s %s\n", "PROJECT", "NAME", "SYNC", "HEALTH"} {printf "%-12s %-26s %-10s %s\n", $1, $2, $3, $4}'

echo
printf "%s%s== 비정상 Application ==%s\n" "$B" "$Y" "$N"
out=$(kubectl -n "$NAMESPACE" get app -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.sync.status}{"\t"}{.status.health.status}{"\n"}{end}' \
  | awk -F'\t' '$2 != "Synced" || $3 != "Healthy"')
if [[ -z "$out" ]]; then
  printf "%s  모든 Application 정상%s\n" "$G" "$N"
else
  echo "$out" | awk -F'\t' 'BEGIN{printf "%-26s %-10s %s\n", "NAME", "SYNC", "HEALTH"} {printf "%-26s %-10s %s\n", $1, $2, $3}'
fi

echo
printf "%s%s== ExternalSecret (argocd repo creds) ==%s\n" "$B" "$G" "$N"
kubectl -n "$NAMESPACE" get externalsecret 2>/dev/null \
  | awk 'NR==1 || /github-app/' \
  || echo "  (none)"

echo
