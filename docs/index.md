---
title: Docs index
updated: 2026-08-24
type: architecture
status: current
---

# Docs index

문서 하나당 한 줄. 여기 없는 `docs/**/*.md` 는 CI 가 막는다.

## Operations

- [Makefile operations](operations.md) - Makefile 타깃 표와 기본 변수. `Makefile` 이나 `scripts/` 를 고치면 같이 고친다.

## Rules

- [External Secrets rules](rules/external-secrets.md) - ESO 함정, ownerReference GC, SSM 키 네이밍.
- [Gateway API routing rules](rules/gateway-api-routing.md) - 플랫폼과 서비스 차트의 소유 경계, 신규 서비스 온보딩, SSA diff 방지.

## Decisions

- [ESO secrets centralization design](specs/2026-05-06-eso-secrets-centralization-design.md) - 시크릿 중앙화 설계.
- [ArgoCD notifications improvement](specs/2026-06-08-argocd-notifications-improvement.md) - 알림 개선 설계.
- [Alerting quality improvements](specs/2026-06-12-alerting-quality-improvements.md) - 알림 품질 개선 설계.
