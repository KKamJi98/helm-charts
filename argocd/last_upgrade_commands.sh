# https://artifacthub.io/packages/helm/argo/argo-cd

helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm upgrade --install -n argocd argocd -f kkamji_values.yaml argo/argo-cd --version 8.1.2
