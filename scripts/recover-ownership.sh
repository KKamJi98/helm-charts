#!/usr/bin/env bash
#
# helm upgrade가 "resource exists and cannot be imported into the current
# release" 에러를 낼 때 사용.
# ArgoCD self-sync가 만든 리소스에 helm ownership annotation/label을 주입하여
# 다음 helm upgrade가 정상 인수하도록 한다.
#
# Usage:
#   scripts/recover-ownership.sh [NAMESPACE] [RELEASE]
#
set -euo pipefail

NAMESPACE="${1:-argocd}"
RELEASE="${2:-argocd}"

KINDS=(appproject application externalsecret)

printf "namespace=%s release=%s\n" "$NAMESPACE" "$RELEASE"
printf "주입 대상 kinds: %s\n\n" "${KINDS[*]}"

count_total=0
count_patched=0

for kind in "${KINDS[@]}"; do
  while IFS= read -r name; do
    [[ -z "$name" ]] && continue
    count_total=$((count_total + 1))

    # 이미 helm-managed면 skip
    current_release=$(kubectl -n "$NAMESPACE" get "$kind" "$name" \
      -o jsonpath='{.metadata.annotations.meta\.helm\.sh/release-name}' 2>/dev/null || true)

    if [[ "$current_release" == "$RELEASE" ]]; then
      printf "  ✓ %-25s/%s (이미 helm-managed)\n" "$kind" "$name"
      continue
    fi

    printf "  → patch %-22s/%s\n" "$kind" "$name"
    kubectl -n "$NAMESPACE" annotate "$kind" "$name" \
      "meta.helm.sh/release-name=$RELEASE" \
      "meta.helm.sh/release-namespace=$NAMESPACE" \
      --overwrite >/dev/null
    kubectl -n "$NAMESPACE" label "$kind" "$name" \
      "app.kubernetes.io/managed-by=Helm" \
      --overwrite >/dev/null
    count_patched=$((count_patched + 1))
  done < <(kubectl -n "$NAMESPACE" get "$kind" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n')
done

printf "\n총 %d개 리소스 검사, %d개에 ownership 주입 완료.\n" "$count_total" "$count_patched"
printf "이제 'make install' 또는 'make setup' 실행 가능.\n"
