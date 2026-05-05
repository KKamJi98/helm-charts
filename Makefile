SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

# 기본값 — 필요 시 override:  make setup NAMESPACE=other RELEASE=other
NAMESPACE      ?= argocd
RELEASE        ?= argocd
UMBRELLA_CHART ?= charts/argocd
VALUES         ?= $(UMBRELLA_CHART)/kkamji_local_values.yaml
FIELD_MANAGER  ?= argocd-controller

# 색상
B := \033[1m
G := \033[32m
Y := \033[33m
R := \033[31m
N := \033[0m

.DEFAULT_GOAL := help

# ============================================================
# 부트스트랩 정책 (중요)
# ------------------------------------------------------------
# - helm install/upgrade 는 사용하지 않는다.
#   * 이유: SSA(Server-Side Apply) 환경에서 helm 매니저가 모든 필드의
#     ownership 을 잡아버리면, 이후 ArgoCD self-sync 가 stale 필드를
#     제거하지 못해 cert-manager annotation/tls 같은 잔재가 남는다.
# - 신규 클러스터에서도 'helm template | kubectl apply --server-side
#   --field-manager=argocd-controller' 한 번이면 충분하다.
#   ArgoCD 가 root Application 들을 즉시 만들고, 그 중 하나가 argocd
#   자기 자신을 self-manage 한다 (charts/argocd → argocd Application
#   in charts/argo-applications/management_local_values.yaml).
# - 일상 변경은 git push → ArgoCD self-sync. Makefile 재실행 불필요.
# ============================================================

##@ 메인

.PHONY: setup
setup: deps bootstrap ## 신규 클러스터 일회성 부트스트랩 (deps + bootstrap)

.PHONY: deps
deps: ## umbrella chart 의존성 갱신 (argo-cd, argo-projects)
	@printf "$(B)$(G)==> helm dependency update $(UMBRELLA_CHART)$(N)\n"
	helm dependency update $(UMBRELLA_CHART)

.PHONY: bootstrap
bootstrap: ## helm template + kubectl apply --server-side (helm release secret 미생성, manager=argocd-controller)
	@printf "$(B)$(G)==> bootstrap $(RELEASE) into $(NAMESPACE) (SSA, fieldManager=$(FIELD_MANAGER))$(N)\n"
	kubectl create ns $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -
	helm template $(RELEASE) $(UMBRELLA_CHART) \
		-n $(NAMESPACE) \
		-f $(VALUES) \
	  | kubectl apply -n $(NAMESPACE) \
			--server-side \
			--field-manager=$(FIELD_MANAGER) \
			--force-conflicts \
			-f -
	@printf "$(Y)부트스트랩 완료. 이후 변경은 git push → ArgoCD self-sync 로 진행하세요.$(N)\n"
	@printf "$(R)WARN: 운영 중 helm install/upgrade 를 돌리지 마세요 (SSA ownership drift 발생).$(N)\n"

##@ 운영

.PHONY: refresh
refresh: ## 모든 root Application에 hard refresh
	@printf "$(B)$(G)==> hard refresh on root applications$(N)\n"
	@for r in argocd management-root automation-root personal-root kuberca-root; do \
	  kubectl -n $(NAMESPACE) annotate app $$r argocd.argoproj.io/refresh=hard --overwrite 2>/dev/null || true; \
	done

.PHONY: status
status: ## AppProject + Application 현황 한눈에
	@bash scripts/status.sh $(NAMESPACE)

.PHONY: template
template: ## helm template 으로 매니페스트 검증 (apply 없이)
	helm template $(RELEASE) $(UMBRELLA_CHART) -n $(NAMESPACE) -f $(VALUES) | head -100
	@printf "$(Y)full output 보려면: helm template $(RELEASE) $(UMBRELLA_CHART) -n $(NAMESPACE) -f $(VALUES)$(N)\n"

##@ 복구

.PHONY: recover-secrets
recover-secrets: bootstrap ## argocd-cm/argocd-secret 등이 사라졌을 때 재apply 후 pod 재시작
	@printf "$(B)$(G)==> rollout restart all argocd workloads$(N)\n"
	kubectl -n $(NAMESPACE) rollout restart deploy
	kubectl -n $(NAMESPACE) rollout restart statefulset

.PHONY: unstick-projects
unstick-projects: ## AppProject가 Pending deletion으로 stuck인 경우 finalizer 제거
	@printf "$(Y)WARN: 5~30초 동안 'project does not exist' 일시 오류 가능 — 곧 ArgoCD 재생성$(N)\n"
	@for proj in argocd kuberca management automation personal; do \
	  if kubectl -n $(NAMESPACE) get appproject $$proj -o jsonpath='{.metadata.deletionTimestamp}' 2>/dev/null | grep -q .; then \
	    printf "  $(R)finalizer 제거: $$proj$(N)\n"; \
	    kubectl -n $(NAMESPACE) patch appproject $$proj --type=json \
	      -p='[{"op":"remove","path":"/metadata/finalizers"}]' || true; \
	  fi; \
	done
	@$(MAKE) refresh

.PHONY: detect-helm-ownership
detect-helm-ownership: ## (진단) argocd 네임스페이스에서 manager=helm 잔존 리소스 탐지
	@printf "$(B)$(G)==> scan stale 'manager: helm' fields in $(NAMESPACE)$(N)\n"
	@command -v jq >/dev/null || { echo "jq 필요"; exit 1; }
	@for kind in deployment statefulset daemonset service ingress configmap secret \
	             serviceaccount role rolebinding networkpolicy hpa pdb certificate; do \
	  for name in $$(kubectl -n $(NAMESPACE) get $$kind -o name 2>/dev/null); do \
	    has=$$(kubectl -n $(NAMESPACE) get $$name --show-managed-fields -o json 2>/dev/null \
	      | jq -r '[.metadata.managedFields[]? | select(.manager=="helm")] | length'); \
	    if [ -n "$$has" ] && [ "$$has" != "0" ]; then echo "$$name"; fi; \
	  done; \
	done
	@printf "$(Y)결과가 비어있어야 정상. 잔존 시 git history 의 helm install/upgrade 흔적 점검.$(N)\n"

##@ 유틸

.PHONY: lint
lint: ## helm lint
	@for c in $$(ls -d charts/*/); do \
	  printf "$(B)$(G)==> lint $$c$(N)\n"; \
	  helm lint $$c || true; \
	done

.PHONY: help
help: ## 이 도움말 표시
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make $(B)$(G)<target>$(N)\n"} \
		/^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(B)$(G)%-22s$(N) %s\n", $$1, $$2 } \
		/^##@/ { printf "\n$(B)$(Y)%s$(N)\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@printf "\n$(B)변수 override:$(N) make setup RELEASE=foo NAMESPACE=bar\n\n"
