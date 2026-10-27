---
title: Memory API adoption status
updated: 2026-10-25T21:01:25+09:00
type: decision
status: current
---

# Memory API 도입 상태

## 결정

현재 Mem0 운영 승격은 보류합니다. `memory.kkamji.net`은 역할 기반 후속 주소이며, 이번 source에는 Mem0 Application/Deployment/HTTPRoute나 DNS 등록이 없습니다. 실제 대화 ingestion과 Hermes 설정 변경도 하지 않습니다.

기존 맞춤 API/provider adapter/보강 이미지는 실험 후보였습니다. 공식 구성 branch에 포함하지 않았고 실제 클러스터에 배포하지 않았습니다. 실험 worktree와 별도 비공개 source snapshot은 보존합니다. 기존 GHCR 실험 artifact를 현재 운영 이미지로 재사용하지 않습니다.

## 확인한 upstream 경계

- [공식 server image](https://hub.docker.com/r/mem0/mem0-api-server/tags)는 확인 시 `latest`만 제공하며 마지막 push는 2025-09-10입니다. 현행 server 2.2.1과 일치하는 maintained versioned artifact로 취급하지 않습니다.
- [2.2.1 공식 server requirements](https://github.com/mem0ai/mem0/blob/v2.2.1/server/requirements.txt)는 FastAPI 0.115.8, Pydantic 2.10.4, Uvicorn 0.34.0 등을 고정합니다. FastAPI는 Starlette >=0.40.0,<0.46.0을 요구합니다.
- 이 범위에서 제공되는 최신 stable Starlette는 0.45.3이었습니다. OSV는 여러 advisory record를 반환했습니다. alias가 중복되므로 record 수를 고유 CVE 수로 표시하지 않습니다.
- 이 상태를 최신 patched framework라고 주장하지 않습니다. server dependencies를 강제로 바꾸거나 자체 인증/추출 API를 다시 작성해서 official-only라는 이름으로 배포하지 않습니다.
- 공식 server는 API/JWT 상태용 PostgreSQL을 추가로 사용합니다. SDK 기본 Qdrant 조합을 stock server 구성이라고 부르지 않습니다. 추후 도입 시 기본 pgvector와 외부 공식 embedding API 등 지원 경로를 다시 평가합니다.

## 재개 조건

1. 유지되는 versioned upstream artifact 또는 수용 가능한 공식 source build/release 정책을 정합니다. source code와 dependency 변경 책임을 명확히 나눕니다.
2. Starlette 등 서버 경계 취약점과 patched compatibility를 확인합니다. 진짜 호환 범위를 우회하는 영구 dependency override를 만들지 않습니다.
3. CPU embedding과 한국어 검색, vector dimensions, truncation, auth/owner isolation을 공식 지원 인터페이스로 확인합니다.
4. ChatGPT 구독 경로의 strict JSON 형식 지원은 미확정입니다. [gateway](01_ai-gateway.md)의 합성 응답 성공과 Mem0 memory extraction 성공을 구분합니다. 빈 memories 배열이나 HTTP 200만으로 합격시키지 않습니다.
5. 합성 create/search/재시작 지속성을 확인한 뒤에만 별도 real-ingestion 승인을 검토합니다. 이 결정은 유료 SaaS나 API credit 사용 승인이 아닙니다.
