#!/usr/bin/env/ bash

set -euo pipefail

echo "###########################################"
echo "# Deploying Helm charts..."
echo "###########################################"

helm upgrade --install kcd-2025-mookup . \
  -n kcd --create-namespace \
  -f kcd_west_values.yaml \
  --set fullnameOverride=kcd-2025-mookup \
  --kube-context kkamji-west

helm upgrade --install kcd-2025-mookup . \
  -n kcd --create-namespace \
  -f kcd_east_values.yaml \
  --set fullnameOverride=kcd-2025-mookup \
  --kube-context kkamji-east

echo "###########################################"
echo "# Check Kubernetes Resources (kkamji-west)"
echo "###########################################"

kubectl get deploy,po,svc,cm -n kcd --context kkamji-west

echo "###########################################"
echo "# Check Kubernetes Resources (kkamji-east)"
echo "###########################################"

kubectl get deploy,po,svc,cm -n kcd --context kkamji-east