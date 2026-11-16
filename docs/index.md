---
title: Docs index
updated: 2026-11-17T01:39:57+09:00
type: architecture
status: current
---

# Docs index

문서 하나당 한 줄. 여기 없는 `docs/**/*.md` 는 CI 가 막는다.

## Operations

- [Platform resource baseline](04_resource-baseline.md) - 실제 사용량, Grafana 데이터 보존, HPA와 memory limit 경계, 렌더 및 GitOps rollout 검증.

- [Makefile operations](operations.md) - Makefile 타깃 표와 기본 변수. `Makefile` 이나 `scripts/` 를 고치면 같이 고친다.
- [Argo CD upgrades](argocd-upgrades.md) - 버전 핀, Helm 4/확장 호환성, 검증 및 롤백 경로.
- [Official AI gateway](01_ai-gateway.md) - 공식 LiteLLM 이미지, 내부 접근, 새 OAuth와 수동 GitOps 운영.
- [Memory API adoption status](02_memory-api-status.md) - Mem0 운영 보류 근거와 공식 경로 재개 조건.
- [Hindsight dot candidate](05_hindsight-dot.md) - Disabled dedicated OAuth/MCP staging, secret trust boundary, Cilium acceptance and rollback.
- [Private Hindsight](03_hindsight.md) - 개인 UI/API/MCP 설계, 전용 인증과 단일 writer, 배포 후 인수 및 복구 절차.

- [Keycloak OIDC preparation and phased deployment](05_oidc-idp-preparation.md) - 전용 DB 단계, 별도 앱 활성화, MFA/복구와 기존 인증 보존.
- [Platform OIDC client contract](oidc/01_platform-client-contract.md) - 고정 issuer/owner, PKCE/state/nonce와 세션 폐기.
- [Staged Keycloak consumer SSO](oidc/02_consumer-sso-plan.md) - Disabled current-main integration, retained-PVC composition and native machine-auth boundaries.
- [Controlled Keycloak owner enrollment](oidc/07_owner-enrollment-source.md) - Seven disabled clients, signed groups, private parent-owned enrollment and pending human/runtime gates.
- [Keycloak DB public CA and backup](oidc/03_db-public-ca-supply.md) - 공개 CA 공급/회전, production 단계와 외부 백업/복원 gate.
- [Private Keycloak admin HTTPS candidate](oidc/04_private-admin-https.md) - 별도 ClusterIP proxy, DNS suppression과 narrow route/NP의 source 계약 및 미완료 runtime gate.
- [Grafana PVC preparation only](oidc/05_grafana-pvc-preparation.md) - 고정 PVC 준비 profile과 기존 emptyDir/전체 monitoring 회귀 계약, 후속 후보와 데이터 보전 gate의 구분.
- [Grafana native PVC activation candidate](oidc/06_grafana-pvc-activation.md) - existingClaim/Recreate 후보, 전체 141개 보존 계약, Draft PR/CI와 운영 전환 분리, 최종 copy/crypto/write 정합성 인수 전 main 병합 금지, PVC 보존 rollback.

## Rules

- [External Secrets rules](rules/external-secrets.md) - ESO 함정, ownerReference GC, SSM 키 네이밍.
- [Gateway API routing rules](rules/gateway-api-routing.md) - 플랫폼과 서비스 차트의 소유 경계, 신규 서비스 온보딩, SSA diff 방지.

## Decisions

- [ESO secrets centralization design](specs/2026-05-06-eso-secrets-centralization-design.md) - 시크릿 중앙화 설계.
- [ArgoCD notifications improvement](specs/2026-06-08-argocd-notifications-improvement.md) - 알림 개선 설계.
- [Alerting quality improvements](specs/2026-06-12-alerting-quality-improvements.md) - 알림 품질 개선 설계.

- [ARC rollout](arc-ci.md) - Qualified full SDK/JIT and BQL private scratch/ELF candidate within unchanged shared5Gi and20Gi Pod accounting.
- [ARC GitHub App](arc-github-app.md) - Approved App installation, shared authority, separately approved secure input, rotation and recovery.
- [CI cache registry](ci-cache.md) - zot for ci-full jobs: Docker Hub mirror, network boundary, sizing, fail-open timings and rollback.
- [ARC runner images](arc-runner-images.md) - Recipe, content check, private GHCR publishing and rollback for the runner and rootless Docker images.
