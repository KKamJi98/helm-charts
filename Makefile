SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

# 기본값 — 필요 시 override:  make setup NAMESPACE=other RELEASE=other
NAMESPACE      ?= argocd
RELEASE        ?= argocd
UMBRELLA_CHART ?= charts/argocd
VALUES         ?= $(UMBRELLA_CHART)/kkamji_local_values.yaml
TIMEOUT        ?= 10m

# 색상
B := \033[1m
G := \033[32m
Y := \033[33m
R := \033[31m
N := \033[0m

.DEFAULT_GOAL := help

##@ 메인

.PHONY: setup
setup: deps install ## 신규/재설치 클러스터 부트스트랩 (deps + install)

.PHONY: deps
deps: ## umbrella chart 의존성 갱신 (argo-cd, argo-projects)
	@printf "$(B)$(G)==> helm dependency update $(UMBRELLA_CHART)$(N)\n"
	helm dependency update $(UMBRELLA_CHART)

.PHONY: install
install: ## helm upgrade --install (--take-ownership 포함)
	@printf "$(B)$(G)==> helm upgrade --install $(RELEASE) ($(NAMESPACE))$(N)\n"
	helm upgrade --install $(RELEASE) $(UMBRELLA_CHART) \
		-n $(NAMESPACE) \
		--create-namespace \
		-f $(VALUES) \
		--take-ownership \
		--wait --timeout $(TIMEOUT)

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

.PHONY: recover-ownership
recover-ownership: ## ArgoCD self-sync로 만든 리소스에 helm ownership annotation 주입 (helm upgrade 거부 시)
	@bash scripts/recover-ownership.sh $(NAMESPACE) $(RELEASE)

.PHONY: recover-secrets
recover-secrets: install ## argocd-cm/argocd-secret 등이 사라졌을 때 helm으로 재생성 후 pod 재시작
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
