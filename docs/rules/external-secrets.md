---
title: External Secrets rules
updated: 2026-08-24
type: rule
status: current
---

# External Secrets rules

ESO 매니페스트를 고칠 때 함께 확인한다. 아래 항목은 전부 실제로 밟은 함정이다.

- ClusterExternalSecret 파생 자식 ExternalSecret 은 `refreshInterval` 이 Go 표준형으로 정규화된다(`1h` -> `1h0m0s`). 직접 정의한 ExternalSecret 은 리터럴 문자열을 유지한다.
- `creationPolicy: Owner` 는 ownerReference 를 설정한다 -> ExternalSecret 을 삭제하면 `deletionPolicy: Retain` 이어도 타깃 Secret 이 함께 GC 된다.
- repo 에 정의가 없고 `kubectl.kubernetes.io/last-applied-configuration` 만 있는 ExternalSecret 은 수동 생성된 orphan 일 수 있다 (GitOps 관리 대상 아님 -> 정리 후보).
- SSM ParameterStore 키 네이밍: `/kkamji/<component>/<purpose>` (예: `/kkamji/external-dns/aws-credentials`). 다중 키 자격증명은 SecureString JSON 1개 + `dataFrom.extract` 로 분해한다.
- ExternalSecret/CES 가 부트스트랩 직후 webhook race 로 실패하면 refresh(1h)를 기다리지 말고 `kubectl annotate ... force-sync=$(date +%s)` 로 즉시 reconcile 한다.
- argocd admin 비밀번호는 ESO Merge(argocd-admin-password-es)가 SSM bcrypt 해시(/kkamji/argocd/admin-password-bcrypt)로 고정한다. argocd-secret 의 admin.password 를 수동 수정하지 않는다.
